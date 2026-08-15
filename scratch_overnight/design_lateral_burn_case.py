"""
設計一組「必須側向燃燒 + 必須多棒」的測資 —— 而且用參數掃描找，不用猜的。

動機：2026-08-15 加的階梯種子 (_generate_ladder_seed_candidates) 只會沿速度方向
燒 (爬升型)，涵蓋不到「需要在慢速點做平面轉向」的解。要驗證那個涵蓋範圍限制，
得先有一組真的逼得出側向燃燒的測資。

設計難點 (今天已經栽過兩次的地方)：純位置攔截不需要平面匹配——任兩個軌道平面必然
相交於節線，B 只要在 A 通過節線時抵達就好，完全不用轉平面。而且最後一棒的 Lambert
本來就可以是側向的。所以「需要側向」真正的意思是：**中間棒**需要側向，也就是
最後一棒的 Lambert 需求 (含平面外分量) 超過上限，而且沿切向拆成多棒也救不了
(問題出在方向不是大小)，必須先在慢速點預付一部分轉向。

要卡在一個很窄的中間帶：
  - A 太遠 -> B 乾脆一路爬到節線交會，爬升比轉平面便宜，測不到側向
  - A 太近 -> B 還沒進慢速區就到了，直接 Lambert 硬幹，也測不到側向
兩個槓桿：A 的半徑範圍、A 的 AOP (決定節線落在 A 軌道的哪個位置：0=近地點、
180=遠地點、90=半通徑)。

所以這支腳本不先猜一組再驗證，而是掃 (SMA, AOP, INC) 的組合，對每組量三個數字：
  (a) 單棒最小 Δv           -> 想確認超標
  (b) 純切向多棒的最好結果   -> **關鍵**：如果切向就能解，這組測不到側向，淘汰
  (c) 含側向的構造能不能解   -> 想確認有解
只有 (a) 超標、(b) 做不到、(c) 做得到 的組合才是我們要的。
"""
import sys, os, math, itertools
import numpy as np

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

import warnings
warnings.filterwarnings("ignore")
from src.core_math import propagate_dop853, fast_norm, check_constraints
from poliastro.core.iod import izzo
from poliastro.bodies import Earth
from poliastro.twobody import Orbit
from astropy import units as u

MU = 398600.4418
RE = 6378.137
CAP = 1500.0          # m/s，每棒上限
MIN_COAST = 100.0
MIN_PERI = RE + 100.0

B_SMA, B_ECC, B_INC = 7000.0, 0.001, 0.0


def build(sma, ecc, inc, raan, aop, ta):
    o = Orbit.from_classical(Earth, sma*u.km, ecc*u.one, inc*u.deg,
                              raan*u.deg, aop*u.deg, ta*u.deg)
    return (o.r.to(u.km).value.astype(np.float64),
            o.v.to(u.km/u.s).value.astype(np.float64))


def lam(mu, r0, v0, r_t, tof):
    best = float("inf")
    for pro in (True, False):
        try:
            v1, _ = izzo(mu, r0, r_t, float(tof), M=0, prograde=pro,
                          lowpath=True, numiter=35, rtol=1e-8)
        except Exception:
            continue
        best = min(best, fast_norm(v1 - v0))
    return best * 1000.0


def single_burn_min(A_r0, A_v0, B_r0, B_v0, T_max, n=70):
    dt = 60.0
    best, legal = float("inf"), 0
    for tb in np.linspace(0.0, T_max*0.85, n):
        r_b, v_b = propagate_dop853(B_r0, B_v0, float(tb), dt, MU, 0,0,0, RE)
        mf = T_max - tb
        if mf < 600:
            continue
        for ft in np.linspace(600.0, mf, n):
            r_a, _ = propagate_dop853(A_r0, A_v0, float(tb+ft), dt, MU, 0,0,0, RE)
            d = lam(MU, r_b, v_b, r_a, ft)
            if math.isfinite(d):
                best = min(best, d)
                if d <= CAP:
                    legal += 1
    return best, legal


def tangential_ladder_best(A_r0, A_v0, B_r0, B_v0, T_max, max_kicks=3):
    """純切向多棒 (階梯種子涵蓋得到的那一類)：能不能解？"""
    dt = 60.0
    b_per = 2*math.pi*math.sqrt(B_SMA**3/MU)
    best = None
    for t_wait in np.linspace(0.0, b_per, 4, endpoint=False):
        for mags in itertools.product(np.arange(600.0, CAP+1, 300.0), repeat=max_kicks):
            r_c, v_c = propagate_dop853(B_r0, B_v0, float(t_wait), dt, MU, 0,0,0, RE)
            t_now, acc, ok = float(t_wait), 0.0, True
            for m in mags:
                vh = v_c / fast_norm(v_c)
                v_new = v_c + vh*(m/1000.0)
                if not check_constraints(r_c, v_new, MU, MIN_PERI):
                    ok = False; break
                sp = fast_norm(v_new)**2/2 - MU/fast_norm(r_c)
                if sp >= 0:
                    ok = False; break
                a_n = -MU/(2*sp)
                per = 2*math.pi*math.sqrt(a_n**3/MU)
                if t_now + per >= T_max - 600:
                    ok = False; break
                r_c, v_c = propagate_dop853(r_c, v_new, per, dt, MU, 0,0,0, RE)
                t_now += per; acc += m
            if not ok:
                continue
            mf = T_max - t_now
            if mf < 600:
                continue
            for ft in np.linspace(600.0, min(mf, T_max*0.6), 22):
                r_a, _ = propagate_dop853(A_r0, A_v0, float(t_now+ft), dt, MU, 0,0,0, RE)
                d = lam(MU, r_c, v_c, r_a, ft)
                if d <= CAP:
                    tot = acc + d
                    if best is None or tot < best:
                        best = tot
    return best


def lateral_construction_best(A_r0, A_v0, B_r0, B_v0, T_max, A_h_hat):
    """
    含側向的構造：切向爬升 -> 在遠地點做側向轉向 (朝 A 的平面) -> Lambert 收尾。
    側向方向取「把 B 的角動量轉向 A 的角動量」那個方向的分量。
    """
    dt = 60.0
    b_per = 2*math.pi*math.sqrt(B_SMA**3/MU)
    best = None
    for t_wait in np.linspace(0.0, b_per, 3, endpoint=False):
        for climb in np.arange(900.0, CAP+1, 200.0):
            r_c, v_c = propagate_dop853(B_r0, B_v0, float(t_wait), dt, MU, 0,0,0, RE)
            vh = v_c/fast_norm(v_c)
            v1 = v_c + vh*(climb/1000.0)
            if not check_constraints(r_c, v1, MU, MIN_PERI):
                continue
            sp = fast_norm(v1)**2/2 - MU/fast_norm(r_c)
            if sp >= 0:
                continue
            a1 = -MU/(2*sp); per1 = 2*math.pi*math.sqrt(a1**3/MU)
            if t_wait + per1/2 >= T_max - 600:
                continue
            # 滑到遠地點 (半圈) —— 最慢的地方，轉向最便宜
            r_ap, v_ap = propagate_dop853(r_c, v1, per1/2, dt, MU, 0,0,0, RE)
            t_ap = t_wait + per1/2
            # 側向燃燒：把速度往 A 的軌道平面法向的反向轉 (即減少平面外分量)
            h_b = np.cross(r_ap, v_ap); h_b /= fast_norm(h_b)
            axis = np.cross(h_b, A_h_hat)
            na = fast_norm(axis)
            if na < 1e-9:
                continue
            axis /= na
            ang_tot = math.acos(float(np.clip(np.dot(h_b, A_h_hat), -1, 1)))
            for frac in (0.4, 0.7, 1.0):
                ang = ang_tot*frac
                c, s = math.cos(ang), math.sin(ang)
                v_rot = (v_ap*c + np.cross(axis, v_ap)*s +
                         axis*np.dot(axis, v_ap)*(1-c))
                dv_lat = fast_norm(v_rot - v_ap)*1000.0
                if dv_lat > CAP:
                    continue
                if not check_constraints(r_ap, v_rot, MU, MIN_PERI):
                    continue
                mf = T_max - t_ap - MIN_COAST
                if mf < 600:
                    continue
                r_f, v_f = propagate_dop853(r_ap, v_rot, MIN_COAST, dt, MU, 0,0,0, RE)
                for ft in np.linspace(600.0, min(mf, T_max*0.6), 22):
                    r_a, _ = propagate_dop853(A_r0, A_v0, float(t_ap+MIN_COAST+ft),
                                               dt, MU, 0,0,0, RE)
                    d = lam(MU, r_f, v_f, r_a, ft)
                    if d <= CAP:
                        tot = climb + dv_lat + d
                        if best is None or tot < best:
                            best = tot
    return best


if __name__ == "__main__":
    B_r0, B_v0 = build(B_SMA, B_ECC, B_INC, 0, 0, 0)
    print(f"B: SMA={B_SMA:,.0f} 圓軌道 INC=0 (v={math.sqrt(MU/B_SMA):.3f} km/s)")
    print(f"{'A_SMA':>8}{'AOP':>6}{'INC':>6}{'單棒min':>10}{'單棒合法':>9}"
          f"{'純切向':>10}{'含側向':>10}  判定")
    print("-" * 78)

    winners = []
    for sma, aop, inc in itertools.product((22000.0, 28000.0, 36000.0),
                                            (90.0, 180.0),
                                            (55.0, 70.0)):
        A_r0, A_v0 = build(sma, 0.1, inc, 0.0, aop, 0.0)
        h_a = np.cross(A_r0, A_v0); h_a /= fast_norm(h_a)
        T_max = 4*2*math.pi*math.sqrt(sma**3/MU)
        sb, sl = single_burn_min(A_r0, A_v0, B_r0, B_v0, T_max)
        tan = tangential_ladder_best(A_r0, A_v0, B_r0, B_v0, T_max)
        lat = lateral_construction_best(A_r0, A_v0, B_r0, B_v0, T_max, h_a)

        if sl > 0:
            verdict = "✗ 單棒就能解"
        elif tan is not None:
            verdict = "✗ 純切向能解 (測不到側向)"
        elif lat is None:
            verdict = "✗ 側向也解不了 (太難)"
        else:
            verdict = "✅ 只有側向能解"
            winners.append((sma, aop, inc, lat))
        t_s = f"{tan:,.0f}" if tan else "無解"
        l_s = f"{lat:,.0f}" if lat else "無解"
        print(f"{sma:>8,.0f}{aop:>6.0f}{inc:>6.0f}{sb:>10,.0f}{sl:>9}"
              f"{t_s:>10}{l_s:>10}  {verdict}")

    print("\n" + "="*78)
    if winners:
        print("符合條件的組合 (單棒不行、純切向不行、含側向才行)：")
        for sma, aop, inc, lat in winners:
            print(f"  A: SMA={sma:,.0f} ECC=0.1 INC={inc}deg AOP={aop}deg"
                  f"  -> 含側向解總 Δv = {lat:,.0f} m/s")
        print("\n這些就是能驗證『階梯種子只會切向燒』這個涵蓋範圍限制的測資。")
    else:
        print("沒有組合同時滿足三個條件——要再擴大掃描範圍 (A 的 ECC、B 的軌道高度)")
        print("或接受『這個規則設定下很難逼出必須側向的情境』這個結論本身就是發現。")
