"""
排位賽路徑的參數邊界掃描：雙曲線 A 在哪些參數下工具還可信、哪裡開始不行。

`probe_hyperbolic_A.py` 只測了一組參數 (ECC=1.2, rp=10,000km, INC=30)，證明「這條路
跑得通」。但官方還沒公布任何數字，實際題目可能落在很不一樣的地方，所以要先知道
**邊界在哪**。跟先前那次橢圓的 SMA/ECC 極限掃描是同一個做法。

每組只跑三件便宜的事，不跑完整最佳化 (那樣一組要 5 分鐘，掃不完)：
  1. 傳播精度 —— 對照 farnocchia 解析解 (純二體有解析解，可以直接量對錯)
  2. Lambert 收斂率 + 最小單棒 Δv —— 求解器吃不吃得下這個幾何
  3. 能量下限 —— 封閉解，判斷單棒可不可能

T_max 的取法跟 probe 一致：以「到近地點的時間」為基準抓 2 倍，讓窗口對稱包住飛越。
這是自己編的規則 (官方未公告)，但至少對每組情境是一致的，可以互相比較。
"""

import sys, os, math, time, itertools
import numpy as np

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

import warnings
warnings.filterwarnings("ignore")
from src.core_math import propagate_dop853, fast_norm
from poliastro.core.propagation import farnocchia
from poliastro.core.iod import izzo
from poliastro.bodies import Earth
from poliastro.twobody import Orbit
from astropy import units as u

MU = 398600.4418
RE = 6378.137
CAP = 1500.0


def build(sma, ecc, inc, raan, aop, ta):
    o = Orbit.from_classical(Earth, sma*u.km, ecc*u.one, inc*u.deg,
                              raan*u.deg, aop*u.deg, ta*u.deg)
    return (o.r.to(u.km).value.astype(np.float64),
            o.v.to(u.km/u.s).value.astype(np.float64),
            float(o.t_p.to(u.s).value))


def entry_ta(ecc, frac=0.89):
    """進場真近點角：取漸近線極限的 frac 倍 (負值 = 尚未通過近地點)。
    直接用固定角度 (例如 -130 度) 不行 —— ECC 越大漸近線極限越小，
    ECC=5 的極限只有 101.5 度，-130 度是不存在的位置。"""
    return -math.degrees(math.acos(-1.0/ecc)) * frac


def prop_accuracy(r0, v0, T_max):
    worst = 0.0
    for frac in (0.25, 0.5, 0.75, 1.0):
        t = T_max*frac
        r_num, _ = propagate_dop853(r0, v0, t, 60.0, MU, 0, 0, 0, RE)
        r_ana, _ = farnocchia(MU, r0, v0, t)
        worst = max(worst, float(np.linalg.norm(np.asarray(r_num) - np.asarray(r_ana))))
    return worst * 1000.0        # 公尺


def lambert_scan(A_r0, A_v0, B_r0, B_v0, T_max, n=34):
    conv = tot = legal = 0
    best = float("inf")
    for tb in np.linspace(0.0, T_max*0.7, n):
        r_b, v_b = propagate_dop853(B_r0, B_v0, float(tb), 60.0, MU, 0, 0, 0, RE)
        mf = T_max - tb
        if mf < 600:
            continue
        for ft in np.linspace(600.0, mf, n):
            r_a, _ = propagate_dop853(A_r0, A_v0, float(tb+ft), 60.0, MU, 0, 0, 0, RE)
            for pro in (True, False):
                tot += 1
                try:
                    v1, _ = izzo(MU, r_b, r_a, float(ft), M=0, prograde=pro,
                                  lowpath=True, numiter=35, rtol=1e-8)
                except Exception:
                    continue
                d = fast_norm(v1 - v_b)*1000.0
                if math.isfinite(d):
                    conv += 1
                    best = min(best, d)
                    if d <= CAP:
                        legal += 1
    return conv, tot, legal, best


def energy_floor(A_r0, A_v0, B_sma):
    """B 圓軌道 -> A 近地點的能量下限 (封閉解)。"""
    r = fast_norm(A_r0); v = fast_norm(A_v0)
    en = v*v/2 - MU/r
    h = fast_norm(np.cross(A_r0, A_v0))
    a = -MU/(2*en)
    ecc = math.sqrt(max(0.0, 1 + 2*en*h*h/(MU*MU)))
    rp_a = a*(1-ecc)
    if B_sma >= rp_a:
        return 0.0
    v_now = math.sqrt(MU/B_sma)
    v_need = math.sqrt(MU*(2/B_sma - 2/(B_sma + rp_a)))
    return max(0.0, v_need - v_now)*1000.0


if __name__ == "__main__":
    # 掃描維度：離心率、近地點半徑、傾角、B 的軌道高度
    CASES = []
    # (a) 離心率掃描 —— 從剛過拋物線到很快的飛越
    for ecc in (1.05, 1.2, 1.5, 2.0, 3.0, 5.0):
        CASES.append(("ECC 掃描", ecc, 10000.0, 30.0, 7000.0))
    # (b) 近地點掃描 —— 從擦地到 B 遠遠構不到
    for rp in (7000.0, 10000.0, 15000.0, 25000.0, 40000.0):
        CASES.append(("近地點掃描", 1.2, rp, 30.0, 7000.0))
    # (c) 傾角掃描 —— 含逆行
    for inc in (0.0, 30.0, 60.0, 90.0, 135.0):
        CASES.append(("傾角掃描", 1.2, 10000.0, inc, 7000.0))
    # (d) B 高度掃描
    for bs in (6700.0, 7000.0, 9000.0, 12000.0):
        CASES.append(("B 高度掃描", 1.2, 10000.0, 30.0, bs))

    print("=" * 104)
    print("雙曲線 A 參數邊界掃描（排位賽路徑）")
    print("=" * 104)
    print(f"{'分組':<12}{'ECC':>6}{'近地點':>9}{'INC':>6}{'B_SMA':>8}"
          f"{'T_max(s)':>10}{'傳播誤差':>11}{'收斂率':>9}{'合法%':>8}"
          f"{'最小單棒':>10}{'能量下限':>10}  判定")
    print("-" * 104)

    t0 = time.time()
    rows = []
    for group, ecc, rp, inc, b_sma in CASES:
        sma = -rp/(ecc - 1.0)
        ta = entry_ta(ecc)
        try:
            A_r0, A_v0, t_p = build(sma, ecc, inc, 0.0, 0.0, ta)
        except Exception as e:
            print(f"{group:<12}{ecc:>6.2f}{rp:>9,.0f}{inc:>6.0f}{b_sma:>8,.0f}"
                  f"   建軌道失敗: {type(e).__name__}", flush=True)
            continue
        B_r0, B_v0, _ = build(b_sma, 0.001, 0.0, 0.0, 0.0, 0.0)
        T_max = 2.0 * (-t_p)          # 對稱包住飛越

        err = prop_accuracy(A_r0, A_v0, T_max)
        conv, tot, legal, best = lambert_scan(A_r0, A_v0, B_r0, B_v0, T_max)
        floor = energy_floor(A_r0, A_v0, b_sma)

        if err > 5000.0:
            verdict = "x 傳播誤差超過 5km 門檻"
        elif conv == 0:
            verdict = "x Lambert 完全不收斂"
        elif legal == 0 and floor > CAP:
            verdict = "- 單棒不可能（下限超上限）"
        elif legal == 0:
            verdict = "- 單棒無解（要多棒）"
        else:
            verdict = "OK 單棒可解"

        rows.append((group, ecc, rp, inc, b_sma, T_max, err, conv/tot*100,
                     legal/tot*100, best, floor, verdict))
        print(f"{group:<12}{ecc:>6.2f}{rp:>9,.0f}{inc:>6.0f}{b_sma:>8,.0f}"
              f"{T_max:>10,.0f}{err:>10.3f}m{conv/tot*100:>8.1f}%"
              f"{legal/tot*100:>7.2f}%{best:>10,.0f}{floor:>10,.0f}  {verdict}",
              flush=True)

    print("-" * 104)
    print(f"總耗時 {time.time()-t0:.1f}s，{len(rows)} 組")

    print("\n=== 摘要 ===")
    worst_err = max(rows, key=lambda r: r[6])
    print(f"最大傳播誤差：{worst_err[6]:.3f} m "
          f"(ECC={worst_err[1]}, 近地點={worst_err[2]:,.0f}km) "
          f"—— {'全部遠低於 5km 門檻' if worst_err[6] < 5000 else '有超標！'}")
    worst_conv = min(rows, key=lambda r: r[7])
    print(f"最低 Lambert 收斂率：{worst_conv[7]:.1f}% "
          f"(ECC={worst_conv[1]}, 近地點={worst_conv[2]:,.0f}km, INC={worst_conv[3]:.0f})")
    n_multi = sum(1 for r in rows if "多棒" in r[11] or "不可能" in r[11])
    print(f"需要多棒的組合：{n_multi}/{len(rows)}")
