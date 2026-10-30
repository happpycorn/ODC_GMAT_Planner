"""以既有傳播與 Lambert 修正重建燃燒紀錄
主要入口為 reconstruct_mission_logs。
"""
import math
import numpy as np
from odc.physics.core_math import (propagate_dop853, check_constraints, fast_norm,
                           to_vnb_frame, reaches_perigee, lambert_izzo,
                           izzo_max_revs, ephem_state, build_ephem_table, fixed_orbit_state,
                           build_wait_prefix, cached_wait_min_radius, arc_radius_from_end,
                           initial_wait_min_radius)


# --- 放在同一個檔案或 mission_evaluator.py 中的輔助函式 ---
def refine_lambert_burn(
    r_curr: np.ndarray, v1_guess: np.ndarray, r_target: np.ndarray, t_flight: float,
    mu: float, j2_val: float, j3_val: float, j4_val: float, re_val: float,
    dt: float = 10.0, tol_km: float = 0.05, max_iter: int = 8, fd_eps: float = 1e-4
):
    """
    Lambert (izzo) 給的 v1_guess 是「無擾動二體」下的理論解。
    這裡用含 J2(+J3+J4，視 GRAVITY_DEGREE 而定) 的高精度傳播器 (propagate_dop853)
    當作真實模型，對 v1_guess 做牛頓法微分修正 (有限差分算 3x3 Jacobian) ——
    邏輯上等同 GMAT 的 Target/Vary/Achieve (DC1) 在做的事，只是搬進 Python，
    讓我們不用真的打開 GMAT 也能拿到「加入重力擾動後仍收斂」的最終 Δv 與誤差。
    回傳: (v1_corrected, converged, final_miss_km, iterations)
    """
    v1 = v1_guess.copy()

    for it in range(max_iter):
        r_pred, _ = propagate_dop853(r_curr, v1, t_flight, dt, mu, j2_val, j3_val, j4_val, re_val)
        residual = r_target - r_pred
        miss = fast_norm(residual)
        if miss <= tol_km:
            return v1, True, miss, it

        # 有限差分 Jacobian：d(r_pred)/d(v1)，跟 GMAT Perturbation=0.0001 同量級
        jac = np.empty((3, 3), dtype=np.float64)
        for k in range(3):
            dv = np.zeros(3, dtype=np.float64)
            dv[k] = fd_eps
            r_pert, _ = propagate_dop853(r_curr, v1 + dv, t_flight, dt, mu, j2_val, j3_val, j4_val, re_val)
            jac[:, k] = (r_pert - r_pred) / fd_eps

        try:
            delta_v = np.linalg.solve(jac, residual)
        except np.linalg.LinAlgError:
            break
        v1 = v1 + delta_v

    r_pred, _ = propagate_dop853(r_curr, v1, t_flight, dt, mu, j2_val, j3_val, j4_val, re_val)
    miss = fast_norm(r_target - r_pred)
    return v1, miss <= tol_km, miss, max_iter


def reconstruct_mission_logs(x, num_burns, min_coast_time, T_max, A_r0, A_v0, B_r0, B_v0,
                              mu, j2_val, j3_val, j4_val, re_val, lambert_max_revs=0,
                              min_periapsis=None, ephem=None):
    """
    一步一步重播最佳解，並把 VNB 轉換和時間記錄下來。
    因為不用 JIT，可以盡情使用 list 和 dict。

    2026-09-09：重播時**一併套用跟 `fast_fitness_evaluator` 完全相同的 Earth-safe
    判定**（每段燒後的弧用 `reaches_perigee` + `check_constraints`）。動機見
    HAP-48 / memory `odc-collision-check-verification-gap`：初賽證實「軌跡穿過地表」
    是官方失格線，但這條重播路徑（算成績、餵 script_generator、產繳交腳本）先前
    **完全不檢查碰撞**，會讓一個鑽地球的解（例如作廢的 99.996）在重播/GMAT 都亮綠燈。
    這裡回傳 `earth_safe` / `min_arc_radius_km`，讓上游可以在繳交前擋下。
    `min_periapsis` 不給時預設 = 地球半徑 + 100 km（跟 optimizer 的 self.MIN_PERIAPSIS 對齊）。
    """
    if min_periapsis is None:
        min_periapsis = re_val + 100.0

    burn_logs = []
    times = [0.0]
    dt = 60.0  # DOP853 初始步長猜測 (自適應積分器會自己調整實際步長)

    # Earth-safe 追蹤：earth_safe 是硬性閘門 (任何一段弧鑽到 min_periapsis 以下就 False)，
    # min_arc_radius_km 是所有弧裡實際到達過的最小半徑 (拿來印清楚的診斷數字)。
    earth_safe = True
    min_arc_radius_km = float("inf")

    def _check_earth_arc(r_start, v_after, t_arc, r_end):
        """一段「燒完之後滑行 t_arc」的弧安不安全，判定邏輯跟 fast_fitness_evaluator
        逐字一致：弧內會經過近地點就比密切近地點半徑，否則比兩端取小的半徑。"""
        nonlocal earth_safe, min_arc_radius_km
        if reaches_perigee(r_start, v_after, mu, t_arc):
            r_mag = fast_norm(r_start)
            v2 = v_after[0] * v_after[0] + v_after[1] * v_after[1] + v_after[2] * v_after[2]
            h = np.cross(r_start, v_after)
            h2 = h[0] * h[0] + h[1] * h[1] + h[2] * h[2]
            eps = v2 / 2.0 - mu / r_mag
            e = math.sqrt(max(0.0, 1.0 + 2.0 * eps * h2 / (mu * mu)))
            arc_min = h2 / (mu * (1.0 + e))          # 密切近地點半徑
        else:
            arc_min = min(fast_norm(r_start), fast_norm(r_end))
        if arc_min < min_arc_radius_km:
            min_arc_radius_km = arc_min
        if arc_min < min_periapsis:
            earth_safe = False

    current_time = float(x[0])
    times.append(current_time)
    r_curr, v_curr = fixed_orbit_state(B_r0, B_v0, current_time, mu, j2_val, j3_val, j4_val, re_val, ephem, 1)
    min_arc_radius_km = initial_wait_min_radius(B_r0, B_v0, current_time, r_curr, mu, ephem)
    earth_safe = min_arc_radius_km >= min_periapsis

    idx = 1
    for i in range(1, num_burns):
        # 跟 fast_fitness_evaluator 一致的球座標 (r, theta, phi) -> 直角座標轉換
        dv_r, dv_theta, dv_phi = x[idx], x[idx+1], x[idx+2]
        coast_frac = x[idx+3]
        idx += 4

        sin_theta = math.sin(dv_theta)
        dv_vec = np.array([
            dv_r * sin_theta * math.cos(dv_phi),
            dv_r * sin_theta * math.sin(dv_phi),
            dv_r * math.cos(dv_theta)
        ])

        dv_mag = dv_r
        dv_vnb = to_vnb_frame(r_curr, v_curr, dv_vec)
        
        burn_logs.append({"time": current_time, "dv_vec": dv_vec, "dv_vnb": dv_vnb, "dv_mag": dv_mag, "type": f"Burn {i}"})
        v_curr_new = v_curr + dv_vec
        r_burn = r_curr  # 這段弧的起點 (燒的位置)，propagate 後 r_curr 會被覆寫

        max_coast = T_max - current_time - min_coast_time
        t_coast = min_coast_time + coast_frac * (max_coast - min_coast_time) if max_coast > min_coast_time else min_coast_time

        r_curr, v_curr = propagate_dop853(r_curr, v_curr_new, t_coast, dt, mu, j2_val, j3_val, j4_val, re_val)
        _check_earth_arc(r_burn, v_curr_new, t_coast, r_curr)
        current_time += t_coast
        times.append(current_time)
        
    final_leg_frac = x[-4]
    max_final = T_max - current_time
    t_final_leg = min_coast_time + final_leg_frac * (max_final - min_coast_time) if max_final > min_coast_time else min_coast_time
    intercept_time = current_time + t_final_leg

    r_A_target, _ = fixed_orbit_state(A_r0, A_v0, intercept_time, mu, j2_val, j3_val, j4_val, re_val, ephem, 0)

    # 跟 fast_fitness_evaluator 一致：Lambert 瞄準的是 A 附近容許球內的偏移點
    # (offset_r/theta/phi)，不是 A 的精確位置，藉此換取更省油的轉移。
    offset_r, offset_theta, offset_phi = x[-3], x[-2], x[-1]
    sin_ot = math.sin(offset_theta)
    offset_vec = np.array([
        offset_r * sin_ot * math.cos(offset_phi),
        offset_r * sin_ot * math.sin(offset_phi),
        offset_r * math.cos(offset_theta)
    ])
    r_aim = r_A_target + offset_vec

    # 順向/逆向都算一次，取 Δv 較小的那個當初始猜測 (跟 fast_fitness_evaluator 邏輯一致)。
    # 這裡理論上不太會撞到 izzo 的 Failed to converge (fast_fitness_evaluator 已經把
    # 會崩潰的候選解擋在搜尋階段淘汰掉了，能走到重播這一步的解本來就是搜尋階段判定
    # 「算得出來」的那個)，但還是接住例外，萬一真的撞到給一句看得懂的錯誤，不要噴
    # poliastro 內部的 raw traceback。
    # 分支的挑法必須跟 fast_fitness_evaluator **完全一致**：圈數 M、lowpath、順/逆向
    # 全部掃過取 Δv 最小的。2026-08-28 加多圈轉移時差點只改搜尋端沒改這裡——那會讓
    # 搜尋照多圈解評分、重播跟產生出來的 GMAT 腳本卻是不繞圈的解，回報的數字跟實際
    # 交出去的東西對不起來。加了 lambert_max_revs 參數就一定要兩邊一起改。
    v1_guess = None
    best_guess_dv = float("inf")
    used_retrograde = False
    for m_rev in range(0, int(lambert_max_revs) + 1):
        for lowpath in (True, False):
            if m_rev == 0 and not lowpath:
                continue                       # M=0 只有一組解
            for prograde in (True, False):
                try:
                    v_try, _ = lambert_izzo(mu, r_curr, r_aim, t_final_leg, M=m_rev,
                                    prograde=prograde, lowpath=lowpath)
                except Exception:
                    continue
                d_try = fast_norm(v_try - v_curr)
                if d_try < best_guess_dv:
                    best_guess_dv = d_try
                    v1_guess = v_try
                    used_retrograde = not prograde

    if v1_guess is None:
        raise RuntimeError(
            "重播最佳解時，izzo Lambert 求解器所有分支都沒收斂 (Failed to converge)——"
            "理論上不該發生 (搜尋階段已經會淘汰這種候選解)，如果真的看到這個訊息，"
            "代表這組解的幾何非常邊緣，回報這個狀況並檢查是不是要換一組軌道參數重跑。"
        )

    # 用含 J2 的高精度模型微分修正 Lambert 的理想化猜測值 (等同 GMAT DC1 在做的事)。
    # 注意：這裡修正的目標是瞄準點 r_aim，不是 A 的真實位置，回傳的 miss_km 只代表
    # 「有沒有準確命中瞄準點」，不是最終真正跟 A 差多遠 —— 後者要另外算 (見下)。
    v1_req, dc_converged, _miss_from_aim_km, _dc_iters = refine_lambert_burn(
        r_curr, v1_guess, r_aim, t_final_leg, mu, j2_val, j3_val, j4_val, re_val
    )

    dv_final_vec = v1_req - v_curr
    dv_final_mag = fast_norm(dv_final_vec)
    dv_final_vnb = to_vnb_frame(r_curr, v_curr, dv_final_vec)

    # 真正跟 A 的距離：用修正後的 v1_req 實際傳播一次，量測最終位置跟 A 真實位置
    # (不是瞄準點) 的距離 —— 這才是規則真正在乎、也是計分公式要用的 Δr。
    r_final_actual, _ = propagate_dop853(r_curr, v1_req, t_final_leg, 10.0, mu, j2_val, j3_val, j4_val, re_val)
    # 收尾 Lambert 弧的 Earth-safe 判定 —— 這是最容易鑽地球的一段 (作廢的 99.996 兩棒解
    # 就是這段近地點掉到地表下 2,470 km)，也是這個閘門最關鍵的用途。
    _check_earth_arc(r_curr, v1_req, t_final_leg, r_final_actual)
    miss_km = fast_norm(r_final_actual - r_A_target)

    burn_logs.append({"time": current_time, "dv_vec": dv_final_vec, "dv_vnb": dv_final_vnb, "dv_mag": dv_final_mag, "type": "Final Burn"})
    times.append(intercept_time)

    # r_aim 一併回傳：GMAT script 的打靶目標要瞄準這個點，不能只瞄準 A 的真實位置，
    # 不然 GMAT 自己的 DC 會把我們刻意換來的省油設計修正掉 (詳見 script_generator)。
    return burn_logs, times, miss_km, dc_converged, r_aim, used_retrograde, earth_safe, min_arc_radius_km
