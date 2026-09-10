"""
HAP-47 PoC：split_even 貪婪拆分是不是已經到局部頂了？

背景見 HAP47_SPLIT_ALGORITHM_RESEARCH.md 第 0/4 節。這支腳本**不改動 src/ 任何檔案**，
只 import 既有工具函式（傳播器、近地點判定、計分函式），拿 `outputs/best_98.31_split5_rebalanced/`
現有五棒解當 warm start，換一種決策變數表示法——不是現行 `split_even()` 的「先固定球座標方向、
平均分配大小」，而是把「每段滑行時間 + 每棒 ECI Δv 三分量」共 21 個自由度一次丟給
`scipy.optimize.minimize(method='SLSQP')`，用顯式不等式約束（不是 fitness 裡的懲罰項）
逼近局部最優，目標函數直接用正式的 `calculate_score`。

判準：
- 顯著改善（分數明顯上升，或同分但 Δv/時間餘裕變大）→ split_even 確實留了次優空間，
  值得推進 NLP 拆分器（HAP-47 §4 建議方案）。
- SLSQP 幾步內停住、改善 <0.1% → 現行 98.31 已經在這個局部漏斗的頂點，
  `PROJECT_AUDIT_20260909.md` 的「精度不是新解」判斷得到支持。

注意（見研究備忘錄 §6）：這只驗證「從已知最佳解出發，這個局部有沒有改善空間」，
不是全域最優性證明。

用法：
    cd /Users/corn/Documents/Program/ODC_Program
    python scratch_overnight/hap47_poc_nlp_split.py
"""
import os
import sys
import json
import time

import numpy as np
from scipy.optimize import minimize

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from src.propagator import get_r0_v0, propagate  # noqa: E402
from src.core_math import fast_norm, fast_cross, reaches_perigee  # noqa: E402
from src.scorer import calculate_score  # noqa: E402

# ----------------------------------------------------------------------------
# 常數：全部照抄 optimizer.py 的內部安全邊界（不是規則原始值），確保跟
# best_98.31_split5_rebalanced 那組解站在同一套約束下比較，不會靠「多給的餘裕」
# 製造假的改善。見 optimizer.py:364/383-384/398-399/359/385。
# ----------------------------------------------------------------------------
MU = 398600.4418          # km^3/s^2，跟 optimizer.py:344 一致
RE_VAL = 6378.137
MIN_PERIAPSIS = RE_VAL + 100.0      # optimizer.py:359
MIN_COAST_TIME = 100.0              # rules.MIN_MANEUVER_INTERVAL_SEC，見 configs/contest_pcsplit.json
MAX_DV_SOFT = 1.500 - 0.002         # km/s，optimizer.py:383-384 (MAX_DV_MARGIN_MPS 預設 2.0 m/s)
MISS_TOLERANCE_SOFT = 5.0 - 1.5     # km，optimizer.py:398-399 (內部 1.5km 安全邊界)
GRAVITY_DEGREE = 0                  # configs/contest_pcsplit.json 的 strategy.GRAVITY_DEGREE=0（點質量）

CONFIG = json.load(open(os.path.join(_REPO_ROOT, "configs", "contest_pcsplit.json")))
ORBIT_A = CONFIG["orbit_A"]
ORBIT_B = CONFIG["orbit_B"]
K_T, C_T = CONFIG["rules"]["k_t"], CONFIG["rules"]["C_t"]
K_V, C_V = CONFIG["rules"]["k_v"], CONFIG["rules"]["C_v"]

# ----------------------------------------------------------------------------
# best_98.31_split5_rebalanced 的原始解（從 outputs/best_98.31_split5_rebalanced/
# output_submit.txt 手動抄出：每棒 VNB Δv 分量 (km/s) + Propagate ElapsedSecs）。
# 沒有存成 JSON/原始決策向量，這是唯一的可靠來源——見 run_history.jsonl 只存
# 分數不存決策向量的既有落差。
# ----------------------------------------------------------------------------
BURNS_VNB_KMS = [
    np.array([1.1880976, -0.0550462, 0.9107130]),
    np.array([-0.8496736, -0.7373216, 0.3319201]),
    np.array([-0.7156509, -0.8802771, 0.2916271]),
    np.array([-0.4978773, -1.0427140, 0.1995895]),
    np.array([-0.1654737, -1.1641059, 0.0427397]),
]
# COAST_AFTER_BURN[i] = 第 i 棒燒完之後、下一棒（或抵達量測點）之前的滑行秒數
COAST_AFTER_BURN = [2264.16031, 100.0, 100.0, 100.0, 3111.28753]
T0_WARM = 0.0  # 第一棒之前沒有滑行


def from_vnb(r_vec, v_vec, dv_vnb):
    """VNB 分量 -> ECI Δv 向量。跟 core_math.to_vnb_frame 用同一組基底
    （v_hat/n_hat/b_hat），方向相反，core_math 沒有現成的反向函式，抄同一段算法。"""
    v_hat = v_vec / fast_norm(v_vec)
    h = fast_cross(r_vec, v_vec)
    n_hat = h / fast_norm(h)
    b_hat = fast_cross(v_hat, n_hat)
    return dv_vnb[0] * v_hat + dv_vnb[1] * n_hat + dv_vnb[2] * b_hat


def osculating_periapsis_km(r, v):
    """密切軌道近地點半徑。跟 core_math.check_constraints 內部算法完全同一條公式
    （core_math.py:50-62），只是那邊回傳 bool，這裡要連續值餵給 SLSQP 當約束。"""
    r_mag = fast_norm(r)
    v2 = v[0] ** 2 + v[1] ** 2 + v[2] ** 2
    h = fast_cross(r, v)
    h2 = h[0] ** 2 + h[1] ** 2 + h[2] ** 2
    eps = v2 / 2.0 - MU / r_mag
    e = np.sqrt(max(0.0, 1.0 + (2.0 * eps * h2) / (MU ** 2)))
    return h2 / (MU * (1.0 + e))


def arc_min_radius_km(r0, v0, r1, dt):
    """複刻 optimizer.py 的 arc_safe（optimizer.py:1037-1042）：
    這段弧「安全性判定該看哪個半徑」，跟正式 fast_fitness_evaluator 用同一套邏輯
    （reaches_perigee 決定要不要看密切近地點，不用就看兩端）。"""
    if reaches_perigee(r0, v0, MU, dt):
        return osculating_periapsis_km(r0, v0)
    return min(fast_norm(r0), fast_norm(r1))


# ----------------------------------------------------------------------------
# 決策變數: x = [t0, dt1, dt2, dt3, dt4, dt_final, dv0(3), dv1(3), dv2(3), dv3(3), dv4(3)]
#   t0        滑到第一棒之前的秒數
#   dt1..dt4  棒與棒之間的滑行秒數（4 個，MIN_COAST_TIME 下限）
#   dt_final  最後一棒之後、抵達量測點之前的滑行秒數
#   dv0..dv4  每棒 ECI Δv 向量 (km/s)，直接聯合優化方向+大小，不再是「先固定方向
#             網格、再貪婪均分大小」
# ----------------------------------------------------------------------------
N_BURNS = 5


def unpack(x):
    t0 = x[0]
    dts = x[1:5]
    dt_final = x[5]
    dvs = x[6:].reshape(N_BURNS, 3)
    return t0, dts, dt_final, dvs


def pack(t0, dts, dt_final, dvs):
    return np.concatenate([[t0], dts, [dt_final], np.asarray(dvs).ravel()])


def simulate(x, A_r0, A_v0, B_r0, B_v0):
    t0, dts, dt_final, dvs = unpack(x)
    r, v = propagate(MU, B_r0, B_v0, t0, GRAVITY_DEGREE)
    arcs = [(B_r0, B_v0, r, v, t0)]

    total_dv = 0.0
    for i in range(N_BURNS):
        v = v + dvs[i]
        total_dv += fast_norm(dvs[i])
        dt = dts[i] if i < 4 else dt_final
        r_next, v_next = propagate(MU, r, v, dt, GRAVITY_DEGREE)
        arcs.append((r, v, r_next, v_next, dt))
        r, v = r_next, v_next

    T_team = t0 + float(np.sum(dts)) + dt_final
    A_r, _ = propagate(MU, A_r0, A_v0, T_team, GRAVITY_DEGREE)
    miss_km = fast_norm(r - A_r)
    return dict(r_final=r, T_team=T_team, total_dv=total_dv, miss_km=miss_km, arcs=arcs)


def reconstruct_warm_start(A_r0, A_v0, B_r0, B_v0):
    """把 outputs/best_98.31_split5_rebalanced 的 VNB 燒法轉成本腳本的 ECI 決策
    向量，順便當一次正確性檢查（Δv 分量、T_team、miss_km 應該對得上 SUMMARY.md）。"""
    r, v = B_r0.copy(), B_v0.copy()
    dvs = []
    for i in range(N_BURNS):
        dv_eci = from_vnb(r, v, BURNS_VNB_KMS[i])
        dvs.append(dv_eci)
        v = v + dv_eci
        r, v = propagate(MU, r, v, COAST_AFTER_BURN[i], GRAVITY_DEGREE)

    x0 = pack(T0_WARM, np.array(COAST_AFTER_BURN[:4]), COAST_AFTER_BURN[4], np.array(dvs))
    sim = simulate(x0, A_r0, A_v0, B_r0, B_v0)
    return x0, sim


def objective(x, A_r0, A_v0, B_r0, B_v0):
    sim = simulate(x, A_r0, A_v0, B_r0, B_v0)
    score = calculate_score(sim["miss_km"], sim["T_team"], sim["total_dv"] * 1000.0, 0, K_T, C_T, K_V, C_V)
    return -score


def constraint_dv_cap(x, A_r0, A_v0, B_r0, B_v0):
    _, _, _, dvs = unpack(x)
    return np.array([MAX_DV_SOFT - fast_norm(dv) for dv in dvs])


def constraint_periapsis(x, A_r0, A_v0, B_r0, B_v0):
    sim = simulate(x, A_r0, A_v0, B_r0, B_v0)
    return np.array([arc_min_radius_km(r0, v0, r1, dt) - MIN_PERIAPSIS for (r0, v0, r1, v1, dt) in sim["arcs"]])


def constraint_miss(x, A_r0, A_v0, B_r0, B_v0):
    sim = simulate(x, A_r0, A_v0, B_r0, B_v0)
    return np.array([MISS_TOLERANCE_SOFT - sim["miss_km"]])


def build_bounds(t_max_sec):
    lb = [0.0] + [MIN_COAST_TIME] * 4 + [0.0] + [-MAX_DV_SOFT] * (3 * N_BURNS)
    ub = [t_max_sec] + [t_max_sec] * 4 + [t_max_sec] + [MAX_DV_SOFT] * (3 * N_BURNS)
    return list(zip(lb, ub))


def run_optimization():
    """跑完整個 warm start 重建 + SLSQP 局部優化，回傳所有中間量——CLI 用
    `python hap47_poc_nlp_split.py` 直接印報告；`hap47_poc_gmat_verify.py` import
    這個函式去拿 SLSQP 解，轉成 GMAT script 做真正的驗證（見該檔案說明）。"""
    A_r0, A_v0 = get_r0_v0(ORBIT_A["SMA"], ORBIT_A["ECC"], ORBIT_A["INC"], ORBIT_A["RAAN"], ORBIT_A["AOP"], ORBIT_A["TA"])
    B_r0, B_v0 = get_r0_v0(ORBIT_B["SMA"], ORBIT_B["ECC"], ORBIT_B["INC"], ORBIT_B["RAAN"], ORBIT_B["AOP"], ORBIT_B["TA"])

    Ta_sec = 2.0 * np.pi * np.sqrt(ORBIT_A["SMA"] ** 3 / MU)
    T_max = 4.0 * Ta_sec

    print("=== 1. 重建 warm start（應該對得上 SUMMARY.md：Δv≈6191.5 m/s, T_team≈5675.4s, miss≈3.5km）===")
    x0, sim0 = reconstruct_warm_start(A_r0, A_v0, B_r0, B_v0)
    dv_each = [fast_norm(dv) * 1000.0 for dv in unpack(x0)[3]]
    print(f"每棒 Δv (m/s): {[round(d, 1) for d in dv_each]}")
    print(f"總 Δv = {sim0['total_dv']*1000.0:.1f} m/s, T_team = {sim0['T_team']:.1f} s, miss = {sim0['miss_km']*1000.0:.1f} m")
    score0 = calculate_score(sim0["miss_km"], sim0["T_team"], sim0["total_dv"] * 1000.0, 0, K_T, C_T, K_V, C_V)
    print(f"重建解分數 = {score0:.4f}（應該非常接近官方記錄的 98.31，容許積分器/取數誤差）")

    print("\n=== 2. 檢查 warm start 是否已經滿足所有約束（Earth-safe / Δv cap / miss）===")
    dv_margin = constraint_dv_cap(x0, A_r0, A_v0, B_r0, B_v0)
    peri_margin = constraint_periapsis(x0, A_r0, A_v0, B_r0, B_v0)
    miss_margin = constraint_miss(x0, A_r0, A_v0, B_r0, B_v0)
    print(f"Δv 上限餘裕 (km/s，全部應該 ≥0): {np.round(dv_margin, 4)}")
    print(f"近地點餘裕 (km，全部應該 ≥0): {np.round(peri_margin, 1)}")
    print(f"命中容許餘裕 (km，應該 ≥0): {np.round(miss_margin, 3)}")
    if np.min(dv_margin) < 0 or np.min(peri_margin) < 0 or np.min(miss_margin) < 0:
        print("⚠️ warm start 本身不滿足約束——先檢查 VNB 重建/單位有沒有算錯，SLSQP 的結果不能信任。")

    print("\n=== 3. SLSQP 局部聯合優化（跟 split_even 完全不同的搜尋，同一套約束）===")
    t_start = time.time()
    result = minimize(
        objective,
        x0,
        args=(A_r0, A_v0, B_r0, B_v0),
        method="SLSQP",
        bounds=build_bounds(T_max),
        constraints=[
            {"type": "ineq", "fun": constraint_dv_cap, "args": (A_r0, A_v0, B_r0, B_v0)},
            {"type": "ineq", "fun": constraint_periapsis, "args": (A_r0, A_v0, B_r0, B_v0)},
            {"type": "ineq", "fun": constraint_miss, "args": (A_r0, A_v0, B_r0, B_v0)},
        ],
        options={"maxiter": 200, "ftol": 1e-10},
    )
    elapsed = time.time() - t_start

    sim1 = simulate(result.x, A_r0, A_v0, B_r0, B_v0)
    score1 = calculate_score(sim1["miss_km"], sim1["T_team"], sim1["total_dv"] * 1000.0, 0, K_T, C_T, K_V, C_V)
    dv_margin1 = constraint_dv_cap(result.x, A_r0, A_v0, B_r0, B_v0)
    peri_margin1 = constraint_periapsis(result.x, A_r0, A_v0, B_r0, B_v0)
    miss_margin1 = constraint_miss(result.x, A_r0, A_v0, B_r0, B_v0)
    feasible = np.min(dv_margin1) >= -1e-6 and np.min(peri_margin1) >= -1e-3 and np.min(miss_margin1) >= -1e-6

    print(f"SLSQP 結束：success={result.success}, message={result.message!r}, "
          f"iterations={result.nit}, 耗時={elapsed:.1f}s")
    print(f"優化後：總 Δv = {sim1['total_dv']*1000.0:.1f} m/s, T_team = {sim1['T_team']:.1f} s, "
          f"miss = {sim1['miss_km']*1000.0:.1f} m")
    print(f"優化後分數 = {score1:.4f}（feasible={feasible}）")
    print(f"Δv 上限餘裕: {np.round(dv_margin1, 4)}")
    print(f"近地點餘裕: {np.round(peri_margin1, 1)}")
    t0_1, dts_1, dt_final_1, dvs_1 = unpack(result.x)
    dv_each_1 = [fast_norm(dv) * 1000.0 for dv in dvs_1]
    print(f"優化後每棒 Δv (m/s): {[round(d, 1) for d in dv_each_1]}")
    print(f"優化後 t0={t0_1:.1f}s, 棒間滑行={np.round(dts_1, 1)}s, 最後滑行={dt_final_1:.1f}s")

    print("\n=== 4. 判準 ===")
    if not feasible:
        print("❌ SLSQP 找到的『改善』違反約束（近地點/Δv/miss 至少一項為負）——不算數，"
              "要嘛收緊 ftol/加 warm start 附近的信任域，要嘛這條路先擱置。")
    else:
        rel_improve = (score1 - score0) / max(score0, 1e-9)
        print(f"分數變化：{score0:.4f} -> {score1:.4f}（相對改善 {rel_improve*100:.3f}%）")
        if rel_improve > 0.001:
            print("✅ 顯著改善（>0.1%）——split_even 確實留了次優空間，值得推進 HAP-47 §4 的 NLP 拆分器。")
        else:
            print("⚪ 改善 <0.1%（或没有改善）——現行 98.31 在這個局部已經到頂，"
                  "支持 PROJECT_AUDIT_20260909.md『精度不是新解』的判斷。")

    out = {
        "warm_start": {"score": score0, "total_dv_mps": sim0["total_dv"] * 1000.0,
                        "T_team_sec": sim0["T_team"], "miss_m": sim0["miss_km"] * 1000.0},
        "slsqp_result": {"score": score1, "total_dv_mps": sim1["total_dv"] * 1000.0,
                          "T_team_sec": sim1["T_team"], "miss_m": sim1["miss_km"] * 1000.0,
                          "feasible": bool(feasible), "success": bool(result.success),
                          "nit": int(result.nit), "elapsed_sec": elapsed},
    }
    out_path = os.path.join(_REPO_ROOT, "scratch_overnight", "hap47_poc_nlp_split_result.json")
    with open(out_path, "w") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)
    print(f"\n結果存到 {out_path}（gitignore 已涵蓋 scratch_overnight/*.json，不會進版控）")

    return dict(A_r0=A_r0, A_v0=A_v0, B_r0=B_r0, B_v0=B_v0, T_max=T_max,
                x0=x0, sim0=sim0, score0=score0,
                result=result, x1=result.x, sim1=sim1, score1=score1, feasible=feasible)


if __name__ == "__main__":
    run_optimization()
