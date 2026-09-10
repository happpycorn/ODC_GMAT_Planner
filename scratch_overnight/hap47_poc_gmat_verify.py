"""
HAP-47 PoC 第二步：把 hap47_poc_nlp_split.py 的 SLSQP 解餵進真正的 GMAT,看那 0.0033 分的
「改善」在 GMAT 的高精度求解器/微分修正器下還在不在——不能只信 Python 自己的簡化二體積分器
（見對話裡的提醒：Python 重建 98.31 解本身就有 0.0044 分的積分器噪訊，比 SLSQP 找到的改善還大）。

不改動 src/ 任何檔案，直接重用 script_generator()/run_gmat_verification()（main.py 既有
的無頭驗證管線，跟 best_98.31_split5_rebalanced 當初驗證用的是同一套)。

用法：
    cd /Users/corn/Documents/Program/ODC_Program
    python scratch_overnight/hap47_poc_gmat_verify.py
"""
import os
import sys

import numpy as np

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # 讓 `import hap47_poc_nlp_split` 找得到

from hap47_poc_nlp_split import (  # noqa: E402
    run_optimization, unpack, GRAVITY_DEGREE, MU, ORBIT_A, ORBIT_B, K_T, C_T, K_V, C_V,
)
from src.core_math import to_vnb_frame, fast_norm  # noqa: E402
from src.propagator import propagate  # noqa: E402
from src.script_generator import script_generator  # noqa: E402
from main import run_gmat_verification, GMAT_CONSOLE_DEFAULT  # noqa: E402


def prevburn_states(x, B_r0, B_v0):
    """複刻 hap47_poc_nlp_split.simulate() 的迴圈，但回傳每一棒『燒之前』的 (r, v)——
    這才是 GMAT Axes=VNB 用來定義那一棒座標系的狀態（燒完之後 v 已經變了，不能拿來轉換）。"""
    t0, dts, dt_final, dvs = unpack(x)
    r, v = propagate(MU, B_r0, B_v0, t0, GRAVITY_DEGREE)
    states = []
    for i in range(5):
        states.append((r.copy(), v.copy()))
        v = v + dvs[i]
        dt = dts[i] if i < 4 else dt_final
        r, v = propagate(MU, r, v, dt, GRAVITY_DEGREE)
    return states


def main():
    opt = run_optimization()
    if not opt["feasible"]:
        print("SLSQP 解本身不可行，不驗證了。")
        return

    x1 = opt["x1"]
    B_r0, B_v0 = opt["B_r0"], opt["B_v0"]
    t0, dts, dt_final, dvs = unpack(x1)
    # script_generator 要的 times = [coast0..coast3, coast4, final_leg]（見該檔案
    # for i in range(len(burns)-1) 那段迴圈）。注意：times[0] 是「進第一棒之前」的滑行——
    # 跟 script_generator 的 times[0]（第一次 Propagate 的 ElapsedSecs）語意一致，因為
    # ShipB 的 epoch 本來就是 t=0，兩者都是「從 0 開始算」，直接用 t0 沒問題。
    times = [t0] + list(dts) + [dt_final]

    states = prevburn_states(x1, B_r0, B_v0)
    burns_vnb = []
    for i, (r_pre, v_pre) in enumerate(states):
        v, n, b = to_vnb_frame(r_pre, v_pre, dvs[i])
        burns_vnb.append((float(v), float(n), float(b)))

    aim_point = tuple(float(c) for c in opt["sim1"]["r_final"])

    print("=== 產生 GMAT 驗證腳本（一般變體，含 DC，跟 best_98.31 當初驗證同一套）===")
    print(f"times = {[round(t, 3) for t in times]}")
    print(f"每棒 VNB Δv (m/s) = {[round(fast_norm(np.array(b)) * 1000.0, 1) for b in burns_vnb]}")

    script_generator(
        ORBIT_A["SMA"], ORBIT_A["ECC"], ORBIT_A["INC"], ORBIT_A["RAAN"], ORBIT_A["AOP"], ORBIT_A["TA"],
        ORBIT_B["SMA"], ORBIT_B["ECC"], ORBIT_B["INC"], ORBIT_B["RAAN"], ORBIT_B["AOP"], ORBIT_B["TA"],
        burns_vnb, times, aim_point=aim_point,
        max_dv=1.5, gravity_degree=GRAVITY_DEGREE,
        output_filename="hap47_poc_verify.txt",
    )

    print("\n=== 呼叫 GmatConsole 無頭驗證 ===")
    gmat_result = run_gmat_verification(GMAT_CONSOLE_DEFAULT, os.path.join("outputs", "hap47_poc_verify.txt"))
    if gmat_result is None:
        print("GMAT 驗證沒有跑成功（看上面的錯誤訊息），這個 PoC 沒辦法用 GMAT 蓋章。")
        return

    print(f"\nGMAT 結果：")
    print(f"  T_team        = {gmat_result['t_team_sec']:.2f} s")
    print(f"  Δr_min        = {gmat_result['miss_km']*1000:.1f} m")
    print(f"  InterceptSuccess = {gmat_result['intercept_success']}")
    print(f"  Targeter 收斂    = {gmat_result['targeter_converged']}")
    print(f"  最後一棒 Δv (GMAT 收斂後) = {gmat_result['final_burn_dv_mps']:.1f} m/s")
    print(f"  最後一棒合規      = {gmat_result['final_burn_legal']}")

    print(f"\nPython (SLSQP) 端預測：total Δv = {opt['sim1']['total_dv']*1000:.1f} m/s "
          f"(其中最後一棒 {fast_norm(dvs[-1])*1000:.1f} m/s), T_team = {opt['sim1']['T_team']:.2f} s, "
          f"分數 = {opt['score1']:.4f}")

    if gmat_result["targeter_converged"] and gmat_result["intercept_success"] and gmat_result["final_burn_legal"]:
        from src.scorer import calculate_score
        total_dv_gmat = sum(fast_norm(np.array(b)) for b in burns_vnb[:-1]) * 1000.0 + gmat_result["final_burn_dv_mps"]
        score_gmat = calculate_score(gmat_result["miss_km"], gmat_result["t_team_sec"], total_dv_gmat, 0,
                                      K_T, C_T, K_V, C_V)
        print(f"\n用 GMAT 實際收斂的最後一棒重算分數 = {score_gmat:.4f}")
        print(f"（跟官方記錄 98.31 比較：{'贏' if score_gmat > 98.31 else '沒有贏' if score_gmat < 98.31 else '打平'} "
              f"{abs(score_gmat - 98.31):.4f} 分）")
    else:
        print("\n⚠️ GMAT 沒有乾淨收斂/命中/合規——不能用這個結果宣稱任何改善，"
              "SLSQP 找到的解在 GMAT 的高精度模型下站不住。")


if __name__ == "__main__":
    main()
