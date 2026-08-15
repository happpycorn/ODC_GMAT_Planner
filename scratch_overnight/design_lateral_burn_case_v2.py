"""
設計「非側向燒不可」的測資 —— 第二版。

第一版 (design_lateral_burn_case.py) 12 組全部回報「側向也解不了」，但那個結論
是**我自己構造出來的假陰性**：純切向對照組給了 3 次爬升燒 (max_kicks=3)，側向組
卻只給 1 次爬升 (單一 climb 迴圈)，B 根本爬不到夠慢的遠地點就要轉平面，當然貴。
拿一個被綁手的構造去證明「側向沒用」，證不出東西來。

這一版的三個修正：

1. **側向組也給多次爬升**：n_climb 可調 (預設 2)，每次都在近地點沿速度方向燒
   (Oberth 最划算)，中間滑行整數個週期回到同一個近地點，最後一次爬升改滑半圈
   到遠地點再轉平面。總棒數 = n_climb + 1 (側向) + 1 (Lambert 收尾)。
2. **統計 break 原因**：第一版量出側向組 792 次迭代只花 0.09 秒 (每次 114us)，
   快得可疑 —— 代表絕大多數迭代在跑到 Lambert 之前就被約束擋掉了。如果真正的
   瓶頸是「時間裝不下」而不是「爬得不夠高」，那修爬升次數就是修錯地方。先量再說。
3. **擴大掃描範圍**：第一版結論那行自己就寫了要擴大。加上 A 的 ECC (0.1/0.3/0.5)
   跟 B 的軌道高度 (7,000/8,500 km) 兩個維度。

判定條件不變，要同時滿足三個才算命中：單棒不行、純切向多棒也不行、加了側向才行。
"""

import sys, os, math, time, itertools
from collections import Counter
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


def tangential_ladder_best(A_r0, A_v0, B_r0, B_v0, B_sma, T_max, max_kicks=3):
    """純切向多棒 (階梯種子涵蓋得到的那一類)：能不能解？"""
    dt = 60.0
    b_per = 2*math.pi*math.sqrt(B_sma**3/MU)
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


def lateral_construction_best(A_r0, A_v0, B_r0, B_v0, B_sma, T_max, A_h_hat,
                              n_climb=2, why=None):
    """
    含側向的構造：切向爬升 x n_climb -> 在遠地點做側向轉向 -> Lambert 收尾。

    前 n_climb-1 次爬升各滑行一整個週期回到同一個近地點 (維持 Oberth 效率)，
    最後一次爬升只滑半圈到遠地點 —— 那裡速度最慢，轉平面最便宜。

    why: 傳一個 Counter 進來就會統計每個迴圈是在哪一關被擋掉的。
    """
    dt = 60.0
    b_per = 2*math.pi*math.sqrt(B_sma**3/MU)
    climb_grid = np.arange(900.0, CAP+1, 200.0)
    best = None

    def note(k):
        if why is not None:
            why[k] += 1

    for t_wait in np.linspace(0.0, b_per, 3, endpoint=False):
        for mags in itertools.product(climb_grid, repeat=n_climb):
            r_c, v_c = propagate_dop853(B_r0, B_v0, float(t_wait), dt, MU, 0,0,0, RE)
            t_now, acc, ok = float(t_wait), 0.0, True

            for i, m in enumerate(mags):
                vh = v_c/fast_norm(v_c)
                v_new = v_c + vh*(m/1000.0)
                if not check_constraints(r_c, v_new, MU, MIN_PERI):
                    note("近地點違規"); ok = False; break
                sp = fast_norm(v_new)**2/2 - MU/fast_norm(r_c)
                if sp >= 0:
                    note("燒到逃逸"); ok = False; break
                a_n = -MU/(2*sp)
                per = 2*math.pi*math.sqrt(a_n**3/MU)
                # 最後一次爬升只滑半圈到遠地點，其餘滑整圈回近地點
                coast = per/2 if i == len(mags)-1 else per
                if t_now + coast >= T_max - 600:
                    note("時間裝不下爬升"); ok = False; break
                r_c, v_c = propagate_dop853(r_c, v_new, coast, dt, MU, 0,0,0, RE)
                t_now += coast; acc += m
            if not ok:
                continue

            # 此時在遠地點：把 B 的角動量轉向 A 的角動量
            h_b = np.cross(r_c, v_c); h_b /= fast_norm(h_b)
            axis = np.cross(h_b, A_h_hat)
            na = fast_norm(axis)
            if na < 1e-9:
                note("平面已重合"); continue
            axis /= na
            ang_tot = math.acos(float(np.clip(np.dot(h_b, A_h_hat), -1, 1)))

            hit_any = False
            for frac in (0.25, 0.4, 0.55, 0.7, 0.85, 1.0):
                ang = ang_tot*frac
                c, s = math.cos(ang), math.sin(ang)
                v_rot = (v_c*c + np.cross(axis, v_c)*s +
                         axis*np.dot(axis, v_c)*(1-c))
                dv_lat = fast_norm(v_rot - v_c)*1000.0
                if dv_lat > CAP:
                    note("側向燒超過單棒上限"); continue
                if not check_constraints(r_c, v_rot, MU, MIN_PERI):
                    note("側向後近地點違規"); continue
                mf = T_max - t_now - MIN_COAST
                if mf < 600:
                    note("時間裝不下收尾"); continue
                r_f, v_f = propagate_dop853(r_c, v_rot, MIN_COAST, dt, MU, 0,0,0, RE)
                for ft in np.linspace(600.0, min(mf, T_max*0.6), 22):
                    r_a, _ = propagate_dop853(A_r0, A_v0, float(t_now+MIN_COAST+ft),
                                               dt, MU, 0,0,0, RE)
                    d = lam(MU, r_f, v_f, r_a, ft)
                    if d <= CAP:
                        hit_any = True
                        tot = acc + dv_lat + d
                        if best is None or tot < best:
                            best = tot
            if not hit_any:
                note("走完全程但收尾 Lambert 都超上限")
    return best


if __name__ == "__main__":
    A_SMAS = (22000.0, 28000.0, 36000.0)
    A_ECCS = (0.1, 0.3, 0.5)
    A_AOPS = (90.0, 180.0)
    A_INCS = (55.0, 70.0)
    B_SMAS = (7000.0, 8500.0)
    N_CLIMB = 2

    combos = list(itertools.product(B_SMAS, A_SMAS, A_ECCS, A_AOPS, A_INCS))
    print(f"=== 側向燃燒測資掃描 v2 (側向組 n_climb={N_CLIMB}，共 "
          f"{N_CLIMB+2} 棒) ===")
    print(f"共 {len(combos)} 組\n")
    print(f"{'B_SMA':>7}{'A_SMA':>8}{'ECC':>6}{'AOP':>5}{'INC':>5}"
          f"{'單棒min':>10}{'單棒合法':>9}{'純切向':>9}{'含側向':>9}  判定")
    print("-" * 92)

    why_all = Counter()
    winners = []
    t_start = time.time()

    for B_sma, sma, ecc, aop, inc in combos:
        B_r0, B_v0 = build(B_sma, 0.001, 0.0, 0, 0, 0)
        A_r0, A_v0 = build(sma, ecc, inc, 0.0, aop, 0.0)
        h_a = np.cross(A_r0, A_v0); h_a /= fast_norm(h_a)
        T_max = 4*2*math.pi*math.sqrt(sma**3/MU)

        sb, sl = single_burn_min(A_r0, A_v0, B_r0, B_v0, T_max)
        tan = tangential_ladder_best(A_r0, A_v0, B_r0, B_v0, B_sma, T_max)
        why = Counter()
        lat = lateral_construction_best(A_r0, A_v0, B_r0, B_v0, B_sma, T_max,
                                        h_a, n_climb=N_CLIMB, why=why)
        why_all.update(why)

        if sl > 0:
            verdict = "x 單棒就能解"
        elif tan is not None:
            verdict = "x 純切向能解 (測不到側向)"
        elif lat is None:
            verdict = "x 側向也解不了"
        else:
            verdict = "*** 只有側向能解 ***"
            winners.append((B_sma, sma, ecc, aop, inc, lat))
        t_s = f"{tan:,.0f}" if tan else "無解"
        l_s = f"{lat:,.0f}" if lat else "無解"
        print(f"{B_sma:>7,.0f}{sma:>8,.0f}{ecc:>6.1f}{aop:>5.0f}{inc:>5.0f}"
              f"{sb:>10,.0f}{sl:>9}{t_s:>9}{l_s:>9}  {verdict}", flush=True)

    print("\n" + "="*92)
    print(f"總耗時 {time.time()-t_start:.1f}s")

    print("\n=== 側向構造被擋在哪一關 (全部組合累計) ===")
    tot = sum(why_all.values()) or 1
    for k, v in why_all.most_common():
        print(f"  {k:<32} {v:>8,}  ({v/tot*100:5.1f}%)")

    if winners:
        print("\n符合條件的組合 (單棒不行、純切向不行、含側向才行)：")
        for B_sma, sma, ecc, aop, inc, lat in winners:
            print(f"  B: SMA={B_sma:,.0f} 圓 | A: SMA={sma:,.0f} ECC={ecc} "
                  f"INC={inc}deg AOP={aop}deg -> 含側向總 Delta-v = {lat:,.0f} m/s")
    else:
        print("\n沒有組合同時滿足三個條件。看上面的 break 統計判斷這是")
        print("『真的解不了』還是『構造又把自己綁住了』。")
