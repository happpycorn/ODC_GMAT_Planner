"""撞地球安檢的驗證：比的必須是「這段弧實際飛過的最小半徑」，不是密切軌道的近地點。

背景 (2026-08-28)：官方公布範例題目的參考解之後才發現，舊版 `check_constraints`
無條件比密切軌道的近地點半徑，等於把「把一發超過每棒上限的大燒拆成兩段幾乎同向的燒」
這整個家族判 0 分——而那正是繞過 ΔV_lim 的標準手法，官方自己的參考解就是那一類
（中間軌道近地點 5,517 km，在地表以下，但只飛 100 秒就被第二棒拉回來）。

實測影響：修正前，這題在 5,600 秒以內完全找不到合法解；修正後找到 2,224.7 m/s /
3,185 秒，比官方參考解還好一點。

這份測試不用手算常數當期望值，而是拿**暴力掃描實際軌跡的最小半徑**當基準，
逐一比對新判定的結論——驗的是邏輯本身，不是某幾個抄下來的數字。

跑法：uv run python tests/test_arc_safety.py
"""

import math
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import warnings
warnings.filterwarnings("ignore")
from src.core_math import (check_constraints, reaches_perigee, propagate_dop853,
                           fast_norm)

MU = 398600.4418
RE = 6378.137
MIN_PERI = RE + 100.0

FAILS = []


def check(name, cond):
    print(("  ✅ " if cond else "  ❌ ") + name)
    if not cond:
        FAILS.append(name)


def true_min_radius(r0, v0, dt, n=600):
    """暴力掃描：這段弧上實際飛到的最小半徑（純二體，跟安檢的假設一致）。"""
    lo = float("inf")
    for t in np.linspace(0.0, dt, n):
        r, _ = propagate_dop853(np.asarray(r0, dtype=np.float64),
                                np.asarray(v0, dtype=np.float64),
                                float(t), 60.0, MU, 0.0, 0.0, 0.0, RE)
        lo = min(lo, fast_norm(r))
    return lo


def new_verdict(r0, v0, dt):
    """優化器現在用的判定：弧內會經過近地點就比近地點半徑，否則檢查弧的兩端。"""
    r0 = np.asarray(r0, dtype=np.float64)
    v0 = np.asarray(v0, dtype=np.float64)
    if reaches_perigee(r0, v0, MU, dt):
        return check_constraints(r0, v0, MU, MIN_PERI)
    if fast_norm(r0) < MIN_PERI:
        return False
    r_end, _ = propagate_dop853(r0, v0, float(dt), 60.0, MU, 0.0, 0.0, 0.0, RE)
    return fast_norm(r_end) >= MIN_PERI


def state_at_true_anomaly(a, e, nu_deg):
    """在軌道面內、給定真近點角的位置速度（測試用，不需要三維姿態）。"""
    nu = math.radians(nu_deg)
    p = a * (1 - e * e)
    r = p / (1 + e * math.cos(nu))
    h = math.sqrt(MU * p)
    r_vec = np.array([r * math.cos(nu), r * math.sin(nu), 0.0])
    vr = MU / h * e * math.sin(nu)
    vt = h / r
    v_vec = np.array([vr * math.cos(nu) - vt * math.sin(nu),
                      vr * math.sin(nu) + vt * math.cos(nu), 0.0])
    return r_vec, v_vec


print("── 新判定 vs 暴力掃描實際軌跡：結論必須一致 ──")
# 涵蓋：近地點在地表以下/以上、從不同真近點角出發、長短不一的弧
CASES = []
for a, e in ((10000.0, 0.5), (8000.0, 0.30), (7500.0, 0.18), (12000.0, 0.62)):
    for nu in (0.0, 60.0, 120.0, 180.0, 240.0, 300.0):
        period = 2 * math.pi * math.sqrt(a ** 3 / MU)
        for frac in (0.02, 0.15, 0.5, 1.2):
            CASES.append((a, e, nu, period * frac))

agree = disagree = 0
examples = []
for a, e, nu, dt in CASES:
    r0, v0 = state_at_true_anomaly(a, e, nu)
    if fast_norm(r0) < MIN_PERI:
        continue                                  # 起點就在地下，不是有效測資
    truth = true_min_radius(r0, v0, dt) >= MIN_PERI
    got = new_verdict(r0, v0, dt)
    if truth == got:
        agree += 1
    else:
        disagree += 1
        if len(examples) < 5:
            examples.append((a, e, nu, dt, truth, got))

check(f"{agree + disagree} 組情境全部一致（不一致 {disagree} 組）", disagree == 0)
for ex in examples:
    print(f"       不一致：a={ex[0]}, e={ex[1]}, nu={ex[2]}, dt={ex[3]:.0f}"
          f" -> 實際 {ex[4]}, 判定 {ex[5]}")

print("\n── 舊判定會漏掉、新判定能救回來的那一類 ──")
# 近地點在地表以下，但弧很短、根本飛不到近地點
r0, v0 = state_at_true_anomaly(10000.0, 0.42, 175.0)   # rp = 5,800 km，在地表以下
rp_km = 10000.0 * (1 - 0.42)
check(f"這組的密切近地點 {rp_km:,.0f} km 確實在門檻以下", rp_km < MIN_PERI)
check("舊判定（無條件比近地點）會擋掉", not check_constraints(r0, v0, MU, MIN_PERI))
short = 100.0
check(f"實際飛 {short:.0f} 秒的最小半徑安全", true_min_radius(r0, v0, short) >= MIN_PERI)
check("新判定放行（正確）", new_verdict(r0, v0, short))

print("\n── 真的會撞地球的必須擋下來 ──")
long_dt = 2 * math.pi * math.sqrt(10000.0 ** 3 / MU)   # 整整一圈，一定經過近地點
check(f"同一組軌道飛滿一圈，實際會低於門檻", true_min_radius(r0, v0, long_dt) < MIN_PERI)
check("新判定擋下（正確）", not new_verdict(r0, v0, long_dt))

print("\n── reaches_perigee 本身 ──")
r_ap, v_ap = state_at_true_anomaly(10000.0, 0.5, 180.0)     # 遠地點
half = math.pi * math.sqrt(10000.0 ** 3 / MU)               # 半個週期 = 遠地點到近地點
check("遠地點出發、飛半個週期 -> 會經過近地點", reaches_perigee(r_ap, v_ap, MU, half * 1.01))
check("遠地點出發、飛不到半個週期 -> 不會經過", not reaches_perigee(r_ap, v_ap, MU, half * 0.9))
r_c = np.array([7000.0, 0.0, 0.0])
v_c = np.array([0.0, math.sqrt(MU / 7000.0), 0.0])
check("正圓軌道 -> 沒有近地點可言，永遠回 False",
      not reaches_perigee(r_c, v_c, MU, 1e6))

print()
if FAILS:
    print(f"❌ {len(FAILS)} 項失敗：" + "、".join(FAILS))
    sys.exit(1)
print("✅ 全部通過")
