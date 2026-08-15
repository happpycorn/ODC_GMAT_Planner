"""
排位賽路徑的煙霧探針：A 是雙曲線飛越軌道時，各層元件會不會炸。

背景：`config_validator.py` / `optimizer.py` 已經做了輸入端準備 (放寬 SMA/ECC 值域、
接受 rules.T_MAX_SEC 覆寫)，但**整條流程從來沒有端到端跑過**。這支腳本一層一層戳，
先把「會炸的地方」找出來，再決定要不要修，比直接丟 main.py 進去然後看它在哪裡爆掉快。

注意：官方還沒公告排位賽的 T_max 怎麼定義，這裡的 T_MAX_SEC 是自己編的。
所以這支腳本能回答「程式會不會炸」，不能回答「數字對不對」。
"""

import sys, os, math, traceback
import numpy as np

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

import warnings
warnings.filterwarnings("ignore")

MU = 398600.4418
RE = 6378.137

# A：雙曲線飛越。ECC=1.2 -> SMA = -rp/(ECC-1)，取近地點 10,000 km。
A_SMA, A_ECC, A_INC, A_RAAN, A_AOP, A_TA = -50000.0, 1.2, 30.0, 0.0, 0.0, 230.0
# B：LEO 圓軌道
B_SMA, B_ECC, B_INC, B_RAAN, B_AOP, B_TA = 7000.0, 0.001, 0.0, 0.0, 0.0, 0.0

results = []


def check(name, fn):
    try:
        out = fn()
        results.append((name, "OK", out))
        print(f"[OK]   {name}: {out}", flush=True)
        return out
    except Exception as e:
        results.append((name, "FAIL", f"{type(e).__name__}: {e}"))
        print(f"[FAIL] {name}: {type(e).__name__}: {e}", flush=True)
        traceback.print_exc()
        return None


print("=" * 78)
print("排位賽路徑探針：A = 雙曲線飛越軌道")
print("=" * 78)
print(f"A: SMA={A_SMA:,.0f} ECC={A_ECC} INC={A_INC} TA={A_TA}")
print(f"   近地點半徑 = SMA*(1-ECC) = {A_SMA*(1-A_ECC):,.1f} km "
      f"(地表以上 {A_SMA*(1-A_ECC)-RE:,.1f} km)")
print(f"   漸近線極限 TA = +-{math.degrees(math.acos(-1/A_ECC)):.1f} deg")
print(f"B: SMA={B_SMA:,.0f} 圓軌道 INC={B_INC}")
print()

# ---------- 第 1 層：poliastro 建不建得出雙曲線軌道 ----------
from poliastro.bodies import Earth
from poliastro.twobody import Orbit
from astropy import units as u


def build(sma, ecc, inc, raan, aop, ta):
    o = Orbit.from_classical(Earth, sma*u.km, ecc*u.one, inc*u.deg,
                              raan*u.deg, aop*u.deg, ta*u.deg)
    return (o.r.to(u.km).value.astype(np.float64),
            o.v.to(u.km/u.s).value.astype(np.float64))


A_rv = check("1. poliastro 建雙曲線軌道",
             lambda: build(A_SMA, A_ECC, A_INC, A_RAAN, A_AOP, A_TA))
B_rv = check("1b. poliastro 建 B (對照)",
             lambda: build(B_SMA, B_ECC, B_INC, B_RAAN, B_AOP, B_TA))

if A_rv is None:
    print("\n第 1 層就失敗，後面不用測了")
    sys.exit(1)

A_r0, A_v0 = A_rv
B_r0, B_v0 = B_rv
print(f"     A 起始半徑 {np.linalg.norm(A_r0):,.1f} km，速率 {np.linalg.norm(A_v0):.4f} km/s")
print(f"     B 起始半徑 {np.linalg.norm(B_r0):,.1f} km，速率 {np.linalg.norm(B_v0):.4f} km/s")

# 比能量：雙曲線應該 > 0
sp_A = np.linalg.norm(A_v0)**2/2 - MU/np.linalg.norm(A_r0)
print(f"     A 比能量 = {sp_A:+.4f} km^2/s^2 "
      f"({'雙曲線 ✓' if sp_A > 0 else '不是雙曲線 ✗'})")

# ---------- 第 2 層：傳播器 ----------
from src.core_math import propagate_dop853, fast_norm

T_MAX_SEC = 40000.0    # 自己編的，官方還沒公告。
# 選這個值的理由：A 從 TA=-130 度出發，19,974s 後通過近地點 (10,000 km)，
# 而雙曲線軌跡對近地點對稱，所以 40,000s 剛好包住「進來 -> 掠過 -> 出去」
# 整段飛越。設太長 (試過 86,400s) 的話 A 會跑到 317,000 km 外，LEO 的 B
# 追不到，整個窗口都是無效區。


def prop_sweep():
    out = []
    for frac in (0.1, 0.25, 0.5, 0.75, 1.0):
        t = T_MAX_SEC*frac
        r, v = propagate_dop853(A_r0, A_v0, t, 60.0, MU, 0, 0, 0, RE)
        out.append((t, fast_norm(r), fast_norm(v)))
    return out


sweep = check("2. propagate_dop853 傳播雙曲線 A", prop_sweep)
if sweep:
    print(f"     {'t (s)':>10}{'半徑 (km)':>14}{'速率 (km/s)':>14}")
    for t, rr, vv in sweep:
        print(f"     {t:>10,.0f}{rr:>14,.1f}{vv:>14.4f}")

# ---------- 第 2b 層：跟解析解比對 (純二體有解析解) ----------
from poliastro.core.propagation import farnocchia


def prop_accuracy():
    worst = 0.0
    for frac in (0.25, 0.5, 1.0):
        t = T_MAX_SEC*frac
        r_num, _ = propagate_dop853(A_r0, A_v0, t, 60.0, MU, 0, 0, 0, RE)
        r_ana, _ = farnocchia(MU, A_r0, A_v0, t)
        worst = max(worst, float(np.linalg.norm(np.asarray(r_num) - np.asarray(r_ana))))
    return f"最大誤差 {worst*1000:.3f} m (對照 farnocchia 解析解)"


check("2b. 雙曲線傳播精度", prop_accuracy)

# ---------- 第 3 層：Lambert ----------
from poliastro.core.iod import izzo


def lambert_grid():
    hits, best = 0, float("inf")
    total = 0
    for tb in np.linspace(0.0, T_MAX_SEC*0.7, 40):
        r_b, v_b = propagate_dop853(B_r0, B_v0, float(tb), 60.0, MU, 0, 0, 0, RE)
        mf = T_MAX_SEC - tb
        if mf < 600:
            continue
        for ft in np.linspace(600.0, mf, 40):
            r_a, _ = propagate_dop853(A_r0, A_v0, float(tb+ft), 60.0, MU, 0, 0, 0, RE)
            for pro in (True, False):
                total += 1
                try:
                    v1, _ = izzo(MU, r_b, r_a, float(ft), M=0, prograde=pro,
                                  lowpath=True, numiter=35, rtol=1e-8)
                except Exception:
                    continue
                d = fast_norm(v1 - v_b)*1000.0
                if math.isfinite(d):
                    hits += 1
                    best = min(best, d)
    return (f"{hits:,}/{total:,} 組收斂 ({hits/total*100:.1f}%)，"
            f"最小單棒 Δv = {best:,.1f} m/s")


check("3. Lambert 瞄準雙曲線目標", lambert_grid)

# ---------- 第 4 層：MissionOptimizer 初始化 + 能量下限 ----------
from src.optimizer import MissionOptimizer

cfg = {
    "orbit_A": {"SMA": A_SMA, "ECC": A_ECC, "INC": A_INC,
                "RAAN": A_RAAN, "AOP": A_AOP, "TA": A_TA},
    "orbit_B": {"SMA": B_SMA, "ECC": B_ECC, "INC": B_INC,
                "RAAN": B_RAAN, "AOP": B_AOP, "TA": B_TA},
    "rules": {"MAX_DV_MPS": 1500.0, "MIN_MANEUVER_INTERVAL_SEC": 100.0,
              "T_MAX_SEC": T_MAX_SEC,
              "k_t": 0.000002, "C_t": 1800000.0, "k_v": 0.001, "C_v": 4000.0},
    "strategy": {"GRAVITY_DEGREE": 4, "MISS_TOLERANCE_KM": 5.0},
    "optimization": {"MAX_BURNS": [1, 2], "MAXITER": 60, "POPSIZE": 8,
                     "NUM_THREADS": 8, "MAX_EARLY_STOP": 40, "TOL": 0.02,
                     "SEED": 42},
}

opt = check("4. MissionOptimizer 初始化 (T_MAX_SEC 覆寫)",
            lambda: MissionOptimizer(cfg))
if opt is not None:
    print(f"     T_max = {opt.T_max:,.1f}s")

if opt is not None:
    # 這兩個是 MissionOptimizer 的方法，不是模組層函式
    check("4b. _orbit_radius_range 對雙曲線 A (遠地點應為 inf)",
          lambda: "A 半徑範圍 %.1f ~ %s km" % (
              opt._orbit_radius_range(A_r0, A_v0)[0],
              f"{opt._orbit_radius_range(A_r0, A_v0)[1]:,.1f}"
              if math.isfinite(opt._orbit_radius_range(A_r0, A_v0)[1]) else "inf"))
    check("4c. _orbit_radius_range 對 B (對照)",
          lambda: "B 半徑範圍 %.1f ~ %.1f km" % opt._orbit_radius_range(B_r0, B_v0))
    check("4d. energy_floor_dv 對雙曲線 A",
          lambda: "能量下限 %.1f m/s" % (opt.energy_floor_dv()*1000.0))

# ---------- 第 5 層：config_validator ----------
from src.config_validator import validate_config


def run_validator():
    try:
        validate_config(cfg)
        return "通過，沒有攔下來"
    except Exception as e:
        return f"攔下來了：{e}"


check("5. config_validator", run_validator)

# ---------- 第 6 層：GMAT script 產生器 (雙曲線六根數寫得出來嗎) ----------
from src import script_generator as sg


def gen_script_names():
    return "script_generator 可呼叫的入口: " + ", ".join(
        n for n in dir(sg) if not n.startswith("_") and callable(getattr(sg, n)))


check("6. script_generator 模組載入", gen_script_names)

print()
print("=" * 78)
print("總結")
print("=" * 78)
for name, status, detail in results:
    mark = "OK  " if status == "OK" else "FAIL"
    print(f"  [{mark}] {name}")
    if status == "FAIL":
        print(f"         {detail}")
n_fail = sum(1 for _, s, _ in results if s == "FAIL")
print(f"\n{len(results)-n_fail}/{len(results)} 層通過"
      + ("" if n_fail == 0 else f"，{n_fail} 層需要修"))
