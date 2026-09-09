# src/core_math.py
import math
import numpy as np
from numba import njit
from scipy.integrate._ivp.dop853_coefficients import A as _DOP853_A_FULL, C as _DOP853_C_FULL, E3 as _DOP853_E3, E5 as _DOP853_E5, N_STAGES as _DOP853_N_STAGES

# DOP853 (Hairer 版 8 階 Dormand-Prince，scipy 的 solve_ivp(method='DOP853') 用的
# 同一套係數) 的係數陣列——直接從 scipy 的原始碼匯入，不手動重刻 (12 段 stage 抄
# 錯的風險太高)。B 依照 scipy 原始碼的慣例存在展開版 A 矩陣的第 N_STAGES 列
# (`B = A[N_STAGES, :N_STAGES]`)，E3/E5 是內建的誤差估計係數 (長度 N_STAGES+1，
# 包含最後一段 f(t+h, y_new) 的貢獻)。這裡的切片只留下實際 stepping 需要的部分
# (完整陣列還有 dense output 插值用的額外幾段，這裡用不到)。
DOP853_N_STAGES = _DOP853_N_STAGES
DOP853_A = np.ascontiguousarray(_DOP853_A_FULL[:DOP853_N_STAGES, :DOP853_N_STAGES])
DOP853_B = np.ascontiguousarray(_DOP853_A_FULL[DOP853_N_STAGES, :DOP853_N_STAGES])
DOP853_C = np.ascontiguousarray(_DOP853_C_FULL[:DOP853_N_STAGES])
DOP853_E3 = np.ascontiguousarray(_DOP853_E3)
DOP853_E5 = np.ascontiguousarray(_DOP853_E5)

@njit(fastmath=True, inline='always')
def fast_cross(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    return np.array([
        a[1]*b[2] - a[2]*b[1],
        a[2]*b[0] - a[0]*b[2],
        a[0]*b[1] - a[1]*b[0]
    ], dtype=np.float64)

@njit(fastmath=True, inline='always')
def fast_norm(v: np.ndarray) -> float:
    return math.sqrt(v[0]**2 + v[1]**2 + v[2]**2)

@njit(fastmath=True, inline='always')
def to_vnb_frame(r_vec: np.ndarray, v_vec: np.ndarray, dv_inertial: np.ndarray) -> np.ndarray:
    v_norm = fast_norm(v_vec)
    v_hat = v_vec / v_norm

    h = fast_cross(r_vec, v_vec)
    h_norm = fast_norm(h)
    n_hat = h / h_norm

    b_hat = fast_cross(v_hat, n_hat)

    dv_v = dv_inertial[0]*v_hat[0] + dv_inertial[1]*v_hat[1] + dv_inertial[2]*v_hat[2]
    dv_n = dv_inertial[0]*n_hat[0] + dv_inertial[1]*n_hat[1] + dv_inertial[2]*n_hat[2]
    dv_b = dv_inertial[0]*b_hat[0] + dv_inertial[1]*b_hat[1] + dv_inertial[2]*b_hat[2]
    
    return np.array([dv_v, dv_n, dv_b], dtype=np.float64)

@njit(fastmath=True, inline='always')
def check_constraints(r: np.ndarray, v: np.ndarray, mu: float, min_rp: float) -> bool:
    r2 = r[0]**2 + r[1]**2 + r[2]**2
    v2 = v[0]**2 + v[1]**2 + v[2]**2
    r_mag = math.sqrt(r2)
    
    h = fast_cross(r, v)
    h2 = h[0]**2 + h[1]**2 + h[2]**2
    
    epsilon = (v2 / 2.0) - (mu / r_mag)
    e = math.sqrt(max(0.0, 1.0 + (2.0 * epsilon * h2) / (mu**2)))
    rp = h2 / (mu * (1.0 + e))
    
    return rp >= min_rp  

@njit(fastmath=True, inline='always')
def reaches_perigee(r: np.ndarray, v: np.ndarray, mu: float, dt: float) -> bool:
    """接下來 dt 秒內，會不會真的飛過近地點。

    為什麼需要這個 (2026-08-28)：`check_constraints` 比的是**密切軌道**的近地點半徑，
    跟太空船會不會真的飛到那裡完全無關。這太嚴，而且會系統性地漏掉一整個解的家族——
    把一發超過每棒上限的大燒**拆成兩段幾乎同向的燒**，是繞過 ΔV_lim 的標準手法，而
    中間那個暫態軌道的近地點常常落在地表以下。太空船只在上面待 100 秒（機動間隔下限），
    根本到不了近地點，實際飛過的高度完全安全。

    官方 2026-08-28 公布的範例參考解正是這一類：第一棒 1,500 m/s 之後中間軌道的近地點
    是 5,517 km（地表以下 860 km），100 秒後被第二棒拉回來，總共 2,241 m/s、3,212 秒
    完成攔截。舊版的判定會把它直接判 0 分。

    有了這個判斷，安檢就可以拆成兩半（兩者都便宜、而且合起來是**精確**的）：
      * 弧內會經過近地點 -> 用 check_constraints 比近地點半徑；
      * 弧內不經過近地點 -> 這段弧的最小半徑就是「起點、終點取小的那個」
        （中間就算越過遠地點也只會更高），檢查兩端即可。

    純二體的 Kepler 關係；J2 在 100 秒尺度上改不動這個判斷。
    """
    r_mag = fast_norm(r)
    v2 = v[0]*v[0] + v[1]*v[1] + v[2]*v[2]
    energy = v2 / 2.0 - mu / r_mag
    rv = r[0]*v[0] + r[1]*v[1] + r[2]*v[2]

    if energy >= 0.0:
        # 雙曲線/拋物線：正在往內掉就當作會通過近地點 (保守)，正在往外飛就不會
        return rv < 0.0

    a = -mu / (2.0 * energy)
    h = fast_cross(r, v)
    h2 = h[0]*h[0] + h[1]*h[1] + h[2]*h[2]
    e = math.sqrt(max(0.0, 1.0 + (2.0 * energy * h2) / (mu * mu)))
    if e < 1e-12:
        return False                      # 正圓：沒有近地點可言，半徑恆定

    # 偏近點角 E：用 r = a(1 - e cosE) 反解，象限由 r·v 決定
    cos_E = (1.0 - r_mag / a) / e
    if cos_E > 1.0:
        cos_E = 1.0
    elif cos_E < -1.0:
        cos_E = -1.0
    E = math.acos(cos_E)
    if rv < 0.0:
        E = 2.0 * math.pi - E             # 正在往近地點掉
    M = E - e * math.sin(E)               # Kepler 方程
    n = math.sqrt(mu / (a * a * a))
    t_to_perigee = (2.0 * math.pi - M) / n
    return t_to_perigee <= dt


@njit(fastmath=True, inline='always')
def compute_dv_mag(v1_req: np.ndarray, v1: np.ndarray):
    dv = v1_req - v1
    return dv, fast_norm(dv)

@njit(fastmath=True, inline='always')
def perturbation_accel(r: np.ndarray, mu: float, j2: float, j3: float, j4: float, re: float) -> np.ndarray:
    """
    只回傳 J2+J3+J4 zonal harmonic 造成的加速度，**不含二體項** (-mu*r/r^3)。
    從原本 `fast_dynamics` 拆出來 (2026-08-14，為了 Encke's method 準備)——
    Encke 只需要「擾動」這一小塊 (二體的部分交給解析 Kepler 解處理)，`fast_dynamics`
    (Cowell/RK45 用) 則是這個函式的結果再疊加二體項，兩條路徑共用同一份 J2/J3/J4
    公式，不會有兩邊各自維護一份、久了對不齊的風險。

    公式推導/交叉驗證過程 (跟已驗證的 J2 公式、poliastro 的 J3 實作逐項比對過)
    見 STATUS.md 2026-08-14「重力場模型可設定」那一節，這裡不重複貼。
    J2/J3/J4 係數直接從 GMAT 用的 JGM2.cof 反算，j3/j4 傳 0.0 代表關閉該項。
    """
    x, y, z = r[0], r[1], r[2]

    r2 = x**2 + y**2 + z**2
    r1 = r2**0.5
    s = z / r1  # sin(地心緯度)

    ax, ay, az = 0.0, 0.0, 0.0

    # --- J2 ---
    factor2 = -1.5 * j2 * (mu / r2) * (re / r1)**2
    z2_r2_5 = 5.0 * s * s

    ax += factor2 * (1.0 - z2_r2_5) * (x / r1)
    ay += factor2 * (1.0 - z2_r2_5) * (y / r1)
    az += factor2 * (3.0 - z2_r2_5) * (z / r1)

    r4 = r2 * r2
    s2 = s * s

    # --- J3 ---
    if j3 != 0.0:
        r5 = r4 * r1
        r6 = r4 * r2
        s3 = s2 * s
        re3 = re * re * re
        f3_xy = 2.5 * mu * j3 * re3 / r6 * (7.0 * s3 - 3.0 * s)
        ax += f3_xy * x
        ay += f3_xy * y
        az += 0.5 * mu * j3 * re3 / r5 * (35.0 * s2 * s2 - 30.0 * s2 + 3.0)

    # --- J4 ---
    if j4 != 0.0:
        r6 = r4 * r2
        r7 = r6 * r1
        s4 = s2 * s2
        re4 = re * re * re * re
        f4_xy = 1.875 * mu * j4 * re4 / r7 * (21.0 * s4 - 14.0 * s2 + 1.0)
        ax += f4_xy * x
        ay += f4_xy * y
        az += 0.625 * mu * j4 * re4 / r6 * s * (63.0 * s4 - 70.0 * s2 + 15.0)

    return np.array([ax, ay, az], dtype=np.float64)


@njit(fastmath=True, inline='always')
def fast_dynamics(t: float, state: np.ndarray, mu: float, j2: float, j3: float, j4: float, re: float) -> np.ndarray:
    """
    完整動力學 (二體 + J2/J3/J4 擾動)，給 Cowell 式的直接數值積分用 (DOP853，見
    `propagate_dop853`；封存的 RK45 版 `propagate_rk45` 見
    `src/_reference_propagators.py`)。二體項在這裡、擾動項委派給
    `perturbation_accel`——兩者的推導/驗證過程見該函式的說明。
    """
    x, y, z = state[0], state[1], state[2]
    vx, vy, vz = state[3], state[4], state[5]

    r2 = x**2 + y**2 + z**2
    r1 = r2**0.5

    mu_r3 = mu / (r1 * r2)
    ax = -mu_r3 * x
    ay = -mu_r3 * y
    az = -mu_r3 * z

    a_pert = perturbation_accel(state[:3], mu, j2, j3, j4, re)
    ax += a_pert[0]
    ay += a_pert[1]
    az += a_pert[2]

    out = np.empty(6, dtype=np.float64)
    out[0], out[1], out[2] = vx, vy, vz
    out[3], out[4], out[5] = ax, ay, az

    return out

# ==========================================================================
# DOP853 (2026-08-14)：Hairer 的 8 階 Dormand-Prince，跟 scipy 的
# `solve_ivp(method='DOP853')` 同一套係數/演算法 (也是 GMAT 常見預設積分器
# `RungeKutta89`/`PrinceDormand78` 那個檔次——GMAT 用更高階的方法，不是意外)。
# 動機：RK5(4) 對這種平滑的軌道動力學問題可能「殺雞用牛刀」——階數越高，同樣步長
# 容許的誤差越小，理論上平滑問題用更高階方法能用更少的步數達到一樣的精度。
#
# 12 段 stage、係數表比 RK45 大很多，這裡刻意不手動展開每一段 (抄錯的風險太高，
# Encke 的 f(q) 已經有過一次教訓)，改用迴圈搭配上面直接從 scipy 匯入的係數陣列
# (A/B/C/E3/E5)——這些數字是 scipy 自己在用、被廣泛驗證過的，不是我們重新推導的。
# 移植正確性驗證方式：拿同一個測試 ODE，比較這裡的實作結果跟直接呼叫
# `scipy.integrate.solve_ivp(method='DOP853')` 的輸出，3 天/44 圈的傳播只差
# 4.7 公分 (純 Python 原型階段測的，數字見 STATUS.md)，確認移植正確後才搬進來
# 用 numba 重寫。誤差估計公式 (err5/err3 混合、非簡單 RMS) 照抄 scipy
# `Dop853._estimate_error_norm` 的邏輯，不是自己發明的。
# ==========================================================================

@njit(fastmath=True, inline='always')
def dop853_step(t: float, state: np.ndarray, h: float, mu: float, j2: float, j3: float, j4: float, re: float):
    """
    單步 DOP853。回傳 (y_new, K)，K 是 shape (13,6) 的中間 stage 陣列 (含最後一段
    f(t+h, y_new))，呼叫端用 K 配合 E3/E5 算誤差估計 (見 dop853_error_norm)。
    """
    K = np.empty((DOP853_N_STAGES + 1, 6), dtype=np.float64)
    K[0] = fast_dynamics(t, state, mu, j2, j3, j4, re)

    for s in range(1, DOP853_N_STAGES):
        dy = np.zeros(6, dtype=np.float64)
        for j in range(s):
            a = DOP853_A[s, j]
            if a != 0.0:
                dy += a * K[j]
        dy *= h
        K[s] = fast_dynamics(t + DOP853_C[s] * h, state + dy, mu, j2, j3, j4, re)

    dy_final = np.zeros(6, dtype=np.float64)
    for j in range(DOP853_N_STAGES):
        dy_final += DOP853_B[j] * K[j]
    y_new = state + h * dy_final

    f_new = fast_dynamics(t + h, y_new, mu, j2, j3, j4, re)
    K[DOP853_N_STAGES] = f_new

    return y_new, K


@njit(fastmath=True, inline='always')
def dop853_error_norm(K: np.ndarray, h: float, scale: np.ndarray) -> float:
    """
    DOP853 專用的誤差估計，跟 scipy `Dop853._estimate_error_norm` 完全一致
    (混合兩個不同階數的誤差估計 err5/err3，不是簡單的 RMS norm——這是 Hairer
    原始演算法設計的一部分，照抄不修改)。
    """
    err5 = np.zeros(6, dtype=np.float64)
    err3 = np.zeros(6, dtype=np.float64)
    for j in range(DOP853_N_STAGES + 1):
        e5 = DOP853_E5[j]
        e3 = DOP853_E3[j]
        if e5 != 0.0:
            err5 += e5 * K[j]
        if e3 != 0.0:
            err3 += e3 * K[j]
    err5 = err5 / scale
    err3 = err3 / scale

    err5_norm2 = err5[0]**2 + err5[1]**2 + err5[2]**2 + err5[3]**2 + err5[4]**2 + err5[5]**2
    err3_norm2 = err3[0]**2 + err3[1]**2 + err3[2]**2 + err3[3]**2 + err3[4]**2 + err3[5]**2

    if err5_norm2 == 0.0 and err3_norm2 == 0.0:
        return 0.0

    denom = err5_norm2 + 0.01 * err3_norm2
    return abs(h) * err5_norm2 / math.sqrt(denom * 6.0)


@njit(fastmath=True, inline='always')
def propagate_dop853(
    r0: np.ndarray, v0: np.ndarray, tof: float, dt0: float,
    mu: float, j2: float, j3: float, j4: float, re: float,
    rtol: float = 1e-12, atol: float = 1e-9
):
    """
    DOP853 自適應步長軌道傳播器。跟 `propagate_rk45` 一樣是「Cowell 式」直接對
    完整狀態數值積分 (不是 Encke 那種只積分偏差量)，差別只在於用 8 階而不是
    5 階的方法——同樣的步長控制骨架 (SAFETY/MIN_FACTOR/MAX_FACTOR 數值也跟 scipy
    的 RungeKutta 基底類一致)，換一套精度更高、每步更貴的係數表。

    容忍度為什麼是 1e-12/1e-9 而不是更寬鬆的值 (2026-08-15 收緊，原本是 1e-9/1e-6)：
    使用者回報一個 GMAT 對不上的案例，Python 預測命中 3,499.8m、GMAT 實測 88,228m。
    純二體有解析解 (farnocchia) 可以直接當基準量，查出來是**積分誤差**，而且誤差
    幾乎全部產生在近地點通過的瞬間——SMA=70,000/ECC=0.9 的軌道 (近地點 7,000km，
    速度 10.4 km/s) 傳播 4 圈：

        通過 0.5 次近地點 ->   0.00 km
        通過 1 次         ->   0.08 km
        通過 2 次         ->  18.95 km
        通過 3 次         ->  38.35 km
        通過 4 次         ->  90.35 km   <-- 對得上使用者看到的 88 km

    決定誤差的是**近地點通過次數**，不是總傳播時長。`weird_test.json` 的 A 軌道
    (SMA=150,000/ECC=0.93) 在舊容忍度下更慘，跨越 T_max 誤差 223 km。

    收緊到 1e-12/1e-9 之後上述全部歸零 (跟解析解差 0.000 km)。代價是傳播變慢
    1.8~2.9 倍。低偏心軌道在舊容忍度下本來就已經精確 (誤差 0.00 km)，等於白付這個
    成本——但「安靜地算錯」比「慢一點」嚴重太多，而且高偏心情境完全看不出來哪裡不對
    (Python 自己回報命中 3.5km，是拿 GMAT 對照才發現差 88km)，所以預設選安全的那邊。
    真的需要速度時可以在呼叫端明確放寬。
    """
    state = np.empty(6, dtype=np.float64)
    state[0], state[1], state[2] = r0[0], r0[1], r0[2]
    state[3], state[4], state[5] = v0[0], v0[1], v0[2]

    if tof <= 0.0:
        r_final = np.array([state[0], state[1], state[2]], dtype=np.float64)
        v_final = np.array([state[3], state[4], state[5]], dtype=np.float64)
        return r_final, v_final

    t = 0.0
    h = dt0 if dt0 > 0.0 else 60.0
    h = min(h, tof)

    min_h = 1e-8
    safety = 0.9
    min_factor = 0.2
    max_factor = 10.0
    error_exponent = -1.0 / 8.0  # error_estimator_order=7 -> -1/(7+1)
    max_step_attempts = 100

    while t < tof:
        h = min(h, tof - t)
        if h < min_h:
            h = min_h

        accepted = False
        attempts = 0
        step_rejected = False
        while not accepted and attempts < max_step_attempts:
            y_new, K = dop853_step(t, state, h, mu, j2, j3, j4, re)

            scale = np.empty(6, dtype=np.float64)
            for i in range(6):
                scale[i] = atol + rtol * max(abs(state[i]), abs(y_new[i]))

            e_norm = dop853_error_norm(K, h, scale)

            if e_norm < 1.0 or h <= min_h:
                if e_norm == 0.0:
                    factor = max_factor
                else:
                    factor = min(max_factor, safety * e_norm**error_exponent)
                if step_rejected:
                    factor = min(1.0, factor)
                state = y_new
                t += h
                accepted = True
                h = h * factor
            else:
                h = h * max(min_factor, safety * e_norm**error_exponent)
                step_rejected = True
                attempts += 1
                if h < min_h:
                    h = min_h

    r_final = np.array([state[0], state[1], state[2]], dtype=np.float64)
    v_final = np.array([state[3], state[4], state[5]], dtype=np.float64)

    return r_final, v_final