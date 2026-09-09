# src/_reference_propagators.py
"""封存的傳播器（2026-09-09，HAP-65）。

`propagate_rk45`（+ `rk45_step`）跟 `propagate_encke`（+ `encke_f` /
`encke_delta_accel` / `encke_rk45_step`）是 2026-08-14 探索期產物，跟
`core_math.propagate_dop853` 交叉驗證過、正確，但比 DOP853 慢。2026-09-09
全專案盤點（`PROJECT_AUDIT_20260909.md` §3）確認**現役程式與 scratch_overnight
都沒有任何地方 import 這兩組傳播器**（`main.py`/`src/propagator.py` 只呼叫
`propagate_dop853`）——純參考殘留，抽出來只是讓 `core_math.py` 少 430 行死碼，
不是因為它們有問題。細節/推導過程見 STATUS.md「重力場模型可設定」跟
「Encke's method」那幾節，這裡不重複貼。

需要更快傳播器時的取捨紀錄還留著：DOP853 換上主線後兩者都沒有繼續投資的理由
（見 STATUS.md 對應段落結尾的「不建議再花力氣」）。
"""
import math
import numpy as np
from numba import njit
from poliastro.core.propagation.farnocchia import farnocchia_coe
from poliastro.core.elements import rv2coe, coe2rv

from src.core_math import fast_dynamics, perturbation_accel


@njit(fastmath=True, inline='always')
def rk45_step(t: float, state: np.ndarray, h: float, mu: float, j2: float, j3: float, j4: float, re: float):
    """
    Dormand-Prince RK5(4)7M 單步 (跟 scipy 的 RK45/MATLAB 的 ode45 同一族係數，
    Dormand & Prince 1980)。7 段斜率 k1~k7，用兩組不同權重分別算出 5 階解 y5
    (實際採用的解) 跟嵌入的 4 階解 y4，兩者的差拿來當這一步的局部誤差估計——
    這是 propagate_rk45() 用來決定「這步準不準、步長該放大還是縮小」的依據。
    所有係數都是直接寫成分數相除 (例如 35.0/384.0)，不是四捨五入過的小數，
    照抄可以直接對照任何一份 Dormand-Prince 係數表逐項核對。
    回傳 (y5, err_vec)。
    """
    k1 = fast_dynamics(t, state, mu, j2, j3, j4, re)

    s2 = state + h * (1.0/5.0) * k1
    k2 = fast_dynamics(t + h * (1.0/5.0), s2, mu, j2, j3, j4, re)

    s3 = state + h * (3.0/40.0 * k1 + 9.0/40.0 * k2)
    k3 = fast_dynamics(t + h * (3.0/10.0), s3, mu, j2, j3, j4, re)

    s4 = state + h * (44.0/45.0 * k1 - 56.0/15.0 * k2 + 32.0/9.0 * k3)
    k4 = fast_dynamics(t + h * (4.0/5.0), s4, mu, j2, j3, j4, re)

    s5 = state + h * (19372.0/6561.0 * k1 - 25360.0/2187.0 * k2 + 64448.0/6561.0 * k3 - 212.0/729.0 * k4)
    k5 = fast_dynamics(t + h * (8.0/9.0), s5, mu, j2, j3, j4, re)

    s6 = state + h * (9017.0/3168.0 * k1 - 355.0/33.0 * k2 + 46732.0/5247.0 * k3 + 49.0/176.0 * k4 - 5103.0/18656.0 * k5)
    k6 = fast_dynamics(t + h, s6, mu, j2, j3, j4, re)

    # 5 階解 (b7=0，不需要 k7)
    y5 = state + h * (35.0/384.0 * k1 + 500.0/1113.0 * k3 + 125.0/192.0 * k4
                       - 2187.0/6784.0 * k5 + 11.0/84.0 * k6)

    # k7 是 FSAL (First Same As Last)：c7=1、a7i=b_i，所以剛好等於 f(t+h, y5)，
    # 只用來算嵌入的 4 階解 (bhat7 != 0)，不影響 y5 本身。
    k7 = fast_dynamics(t + h, y5, mu, j2, j3, j4, re)

    y4 = state + h * (5179.0/57600.0 * k1 + 7571.0/16695.0 * k3 + 393.0/640.0 * k4
                       - 92097.0/339200.0 * k5 + 187.0/2100.0 * k6 + 1.0/40.0 * k7)

    err_vec = y5 - y4
    return y5, err_vec


@njit(fastmath=True, inline='always')
def propagate_rk45(
    r0: np.ndarray, v0: np.ndarray, tof: float, dt0: float,
    mu: float, j2: float, j3: float, j4: float, re: float,
    rtol: float = 1e-9, atol: float = 1e-6
):
    """
    Dormand-Prince RK5(4) 自適應步長軌道傳播器 (2026-08-14 取代原本固定 60 秒的
    古典 RK4——STATUS.md「拆解 GMAT 對不上的真正原因」那幾節查出來，固定步長在
    「繞很多圈」的情境下誤差比想像中大很多，例如一個普通 LEO 軌道傳播 3 天/44 圈，
    固定 60 秒步長誤差高達 17 公里)。

    跟被撤銷的 `ebaf728` 那次「步長跟 T_max 成比例放大」關鍵不同：這裡的步長完全
    由**這一步自己的局部誤差估計**決定 (跟 scipy RK45/solve_ivp 同一種混合
    相對/絕對容忍度、RMS norm 的誤差控制公式)，不是任何跟軌道規模/T_max 有關的
    全域啟發式——近地點 (曲率大、變化快) 自然會用小步，遠地點自然會用大步，不會
    重蹈「用整體平均步長硬套局部快速變化的一段」導致數值爆炸的問題。

    dt0: 初始步長猜測 (呼叫端沿用原本 dt=60/dt=10 那些值即可)，只影響最開頭幾步
    要花多少次嘗試才會收斂到合適的步長，不影響最終精度。
    rtol/atol: 混合容忍度，預設對這個問題的尺度 (公里/公里每秒) 夠緊，已經跟真實
    GMAT 交叉驗證過 (見 STATUS.md)。
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

    # 步長上下限：下限避免在病態情況下無窮迴圈 (逼近浮點精度極限就強制往前走)，
    # 上限就是剩餘時間本身 (不會需要比這更大的步)。
    min_h = 1e-6
    max_step_attempts = 100  # 單一步驟最多重試幾次才放棄繼續縮步長 (安全網，正常不會碰到)

    while t < tof:
        h = min(h, tof - t)
        if h < min_h:
            h = min_h

        accepted = False
        attempts = 0
        while not accepted and attempts < max_step_attempts:
            y5, err_vec = rk45_step(t, state, h, mu, j2, j3, j4, re)

            # 混合相對/絕對容忍度的 RMS 誤差 norm，跟 scipy 的 RK45 是同一種算法：
            # 每個分量各自算 (誤差 / (atol + rtol*量級))，取均方根。
            sc0 = atol + rtol * max(abs(state[0]), abs(y5[0]))
            sc1 = atol + rtol * max(abs(state[1]), abs(y5[1]))
            sc2 = atol + rtol * max(abs(state[2]), abs(y5[2]))
            sc3 = atol + rtol * max(abs(state[3]), abs(y5[3]))
            sc4 = atol + rtol * max(abs(state[4]), abs(y5[4]))
            sc5 = atol + rtol * max(abs(state[5]), abs(y5[5]))

            err_norm = math.sqrt(
                (err_vec[0]/sc0)**2 + (err_vec[1]/sc1)**2 + (err_vec[2]/sc2)**2 +
                (err_vec[3]/sc3)**2 + (err_vec[4]/sc4)**2 + (err_vec[5]/sc5)**2
            ) / math.sqrt(6.0)

            if err_norm <= 1.0 or h <= min_h:
                # 接受這步：誤差夠小 (或已經縮到步長下限、不能再縮了，強制接受避免卡死)。
                state = y5
                t += h
                accepted = True
                if err_norm < 1e-12:
                    factor = 5.0  # 誤差趨近 0 時的除零防護，直接給放大上限
                else:
                    factor = 0.9 * err_norm**(-0.2)  # 4 階誤差估計 -> 指數 -1/(4+1)
                    factor = min(5.0, max(0.2, factor))
                h = h * factor
            else:
                # 拒絕這步：縮小步長重試，不推進 t/state。
                factor = 0.9 * err_norm**(-0.2)
                factor = min(1.0, max(0.1, factor))
                h = max(h * factor, min_h)
                attempts += 1

    r_final = np.array([state[0], state[1], state[2]], dtype=np.float64)
    v_final = np.array([state[3], state[4], state[5]], dtype=np.float64)

    return r_final, v_final


# ==========================================================================
# Encke's method (2026-08-14)：解析二體參考軌道 (poliastro 的 farnocchia，精確
# Kepler 解) + 只對「真實軌跡 vs 參考軌道」的偏差量 delta_r 數值積分 + 定期校正
# (rectification)。跟 propagate_rk45 的差異：RK45 (Cowell 式) 要老老實實追蹤
# 衛星本身的快速軌道運動；Encke 把這一塊交給解析解處理 (零誤差、O(1) 速度、不管
# 繞幾圈都一樣快)，數值積分只需要處理「擾動累積造成的緩慢偏移」，理論上短弧線
# 幾乎零成本、長弧線 (繞很多圈) 也不會被快速運動拖慢。
# ==========================================================================

@njit(fastmath=True, inline='always')
def encke_f(q: float) -> float:
    """
    Encke 的「f 函數」，把 r_ref/rho^3 - r/r^3 這個原本會有大數相減精度損失問題
    的算式，改寫成數值穩定的形式。

    數學上 f(q) = 1 - (1+q)^(-1.5)，但這個原始形式在 q 很小時 (Encke 的實際使用
    情境：delta_r 遠小於參考軌道半徑，q 通常是 1e-6 甚至更小) 是兩個接近 1 的數
    相減，浮點數會損失精度 (q=1e-16 時直接算出 0.0，完全失真)。這裡用的是代數上
    完全等價、但不會有這種相減問題的形式：

        f(q) = q*(q + sqrt(1+q) + 2) / [(1+q)^1.5 * (1+sqrt(1+q))]

    推導/驗證方式：用 sympy 符號運算驗證這個形式跟 1-(1+q)^-1.5 代數上完全相等
    (simplify 後差為 0)，再用 mpmath 50 位精度當基準，比較兩種形式在 q 從 1e-2
    到 1e-16 的相對誤差——原始形式在 q<1e-8 附近開始明顯損失精度、q=1e-16 時
    誤差達到 100% (直接歸零)；這個穩定形式全程維持在機器精度等級 (~1e-16 相對
    誤差)。細節見 STATUS.md「Encke's method」那一節。
    """
    sq = math.sqrt(1.0 + q)
    return q * (q + sq + 2.0) / ((1.0 + q)**1.5 * (1.0 + sq))


@njit(fastmath=True, inline='always')
def encke_delta_accel(
    t_since_rect: float, delta_r: np.ndarray, delta_v: np.ndarray,
    p: float, ecc: float, inc: float, raan: float, argp: float, nu0: float,
    mu: float, j2: float, j3: float, j4: float, re: float
) -> np.ndarray:
    """
    Encke 偏差量 delta_r 的加速度方程式：

        delta_r_ddot = (mu/rho^3) * [f(q)*r - delta_r] + a_pert(r)

    其中 r_ref(t) 是參考軌道 (用軌道根數 p/ecc/inc/raan/argp/nu0 + farnocchia_coe
    解析算出，精確二體解)，rho=|r_ref|，r=r_ref+delta_r 是真實位置，
    q = delta_r·(2*r_ref+delta_r)/rho^2 (數值驗證過 r^2 == rho^2*(1+q) 這個
    代數恆等式)，a_pert 是 J2/J3/J4 造成的加速度 (不含二體項，見 perturbation_accel)。

    delta_r=0 時 (剛校正完) q=0、f(0)=0，這條式子直接退化成 delta_r_ddot=a_pert，
    符合直覺：偏差還是 0 的瞬間，唯一在起作用的就是擾動力本身。

    2026-08-14 效能修正：一開始的版本每次呼叫都用 farnocchia_rv(r_rect, v_rect, ...)，
    內部每次都重新做一次 r,v -> 軌道根數的轉換 (rv2coe)——但同一次校正區間內
    r_rect/v_rect 是固定的，根數也是固定的，只有 tof 在變。實測量到 farnocchia_rv
    單次呼叫 1.545 微秒，其中 rv2coe 那段就佔 0.498 微秒 (~32%)；一個 RK45 step
    要呼叫 7 次，代表每步浪費 7 次重複的根數轉換。改成呼叫端 (propagate_encke)
    在每次校正時算一次根數，這裡直接吃算好的根數、只呼叫 farnocchia_coe (解
    Kepler 方程) + coe2rv (根數轉回 r,v)，跳過重複的 rv2coe。
    """
    nu = farnocchia_coe(mu, p, ecc, inc, raan, argp, nu0, t_since_rect)
    r_ref, v_ref = coe2rv(mu, p, ecc, inc, raan, argp, nu)

    rho2 = r_ref[0]**2 + r_ref[1]**2 + r_ref[2]**2
    rho = rho2**0.5

    q = (delta_r[0]*(2.0*r_ref[0]+delta_r[0]) + delta_r[1]*(2.0*r_ref[1]+delta_r[1])
         + delta_r[2]*(2.0*r_ref[2]+delta_r[2])) / rho2
    fq = encke_f(q)

    r_true = r_ref + delta_r
    a_pert = perturbation_accel(r_true, mu, j2, j3, j4, re)

    coef = mu / (rho2 * rho)
    return coef * (fq * r_true - delta_r) + a_pert


@njit(fastmath=True, inline='always')
def encke_rk45_step(
    t: float, delta_state: np.ndarray, h: float,
    p: float, ecc: float, inc: float, raan: float, argp: float, nu0: float,
    mu: float, j2: float, j3: float, j4: float, re: float
):
    """
    跟 rk45_step 同一套 Dormand-Prince 係數，差別只在於「動力學函式」換成
    encke_delta_accel (delta 狀態的方程式)，不是 fast_dynamics (完整狀態的方程式)。
    delta_state = [dx,dy,dz, dvx,dvy,dvz]，t 是從上次校正點算起的秒數。
    p/ecc/inc/raan/argp/nu0 是上次校正點的軌道根數 (呼叫端算好傳進來，見
    encke_delta_accel 的說明)。
    """
    dr1, dv1 = delta_state[:3], delta_state[3:]
    da1 = encke_delta_accel(t, dr1, dv1, p, ecc, inc, raan, argp, nu0, mu, j2, j3, j4, re)
    k1 = np.empty(6, dtype=np.float64); k1[:3] = dv1; k1[3:] = da1

    s2 = delta_state + h * (1.0/5.0) * k1
    dr2, dv2 = s2[:3], s2[3:]
    da2 = encke_delta_accel(t + h*(1.0/5.0), dr2, dv2, p, ecc, inc, raan, argp, nu0, mu, j2, j3, j4, re)
    k2 = np.empty(6, dtype=np.float64); k2[:3] = dv2; k2[3:] = da2

    s3 = delta_state + h * (3.0/40.0 * k1 + 9.0/40.0 * k2)
    dr3, dv3 = s3[:3], s3[3:]
    da3 = encke_delta_accel(t + h*(3.0/10.0), dr3, dv3, p, ecc, inc, raan, argp, nu0, mu, j2, j3, j4, re)
    k3 = np.empty(6, dtype=np.float64); k3[:3] = dv3; k3[3:] = da3

    s4 = delta_state + h * (44.0/45.0*k1 - 56.0/15.0*k2 + 32.0/9.0*k3)
    dr4, dv4 = s4[:3], s4[3:]
    da4 = encke_delta_accel(t + h*(4.0/5.0), dr4, dv4, p, ecc, inc, raan, argp, nu0, mu, j2, j3, j4, re)
    k4 = np.empty(6, dtype=np.float64); k4[:3] = dv4; k4[3:] = da4

    s5 = delta_state + h * (19372.0/6561.0*k1 - 25360.0/2187.0*k2 + 64448.0/6561.0*k3 - 212.0/729.0*k4)
    dr5, dv5 = s5[:3], s5[3:]
    da5 = encke_delta_accel(t + h*(8.0/9.0), dr5, dv5, p, ecc, inc, raan, argp, nu0, mu, j2, j3, j4, re)
    k5 = np.empty(6, dtype=np.float64); k5[:3] = dv5; k5[3:] = da5

    s6 = delta_state + h * (9017.0/3168.0*k1 - 355.0/33.0*k2 + 46732.0/5247.0*k3 + 49.0/176.0*k4 - 5103.0/18656.0*k5)
    dr6, dv6 = s6[:3], s6[3:]
    da6 = encke_delta_accel(t + h, dr6, dv6, p, ecc, inc, raan, argp, nu0, mu, j2, j3, j4, re)
    k6 = np.empty(6, dtype=np.float64); k6[:3] = dv6; k6[3:] = da6

    y5 = delta_state + h * (35.0/384.0*k1 + 500.0/1113.0*k3 + 125.0/192.0*k4
                             - 2187.0/6784.0*k5 + 11.0/84.0*k6)
    dr7, dv7 = y5[:3], y5[3:]
    da7 = encke_delta_accel(t + h, dr7, dv7, p, ecc, inc, raan, argp, nu0, mu, j2, j3, j4, re)
    k7 = np.empty(6, dtype=np.float64); k7[:3] = dv7; k7[3:] = da7

    y4 = delta_state + h * (5179.0/57600.0*k1 + 7571.0/16695.0*k3 + 393.0/640.0*k4
                             - 92097.0/339200.0*k5 + 187.0/2100.0*k6 + 1.0/40.0*k7)

    return y5, y5 - y4


@njit(fastmath=True, inline='always')
def propagate_encke(
    r0: np.ndarray, v0: np.ndarray, tof: float, dt0: float,
    mu: float, j2: float, j3: float, j4: float, re: float,
    rtol: float = 1e-9, atol: float = 1e-6, rectify_threshold: float = 1e-3
):
    """
    Encke's method 完整傳播器：解析參考軌道 (farnocchia，二體精確解) + delta 的
    自適應數值積分 (encke_rk45_step) + 定期校正。

    rectify_threshold: |delta_r|/|r_ref| 超過這個比例就校正 (拿當下真實狀態重新
    當參考軌道起點、delta 歸零)。校正本身是精確的 (不引入誤差)，只是決定「多久
    重新拉一次基準」——校正太少次，delta 長太大會讓數值積分變貴 (小偏差的假設
    不成立了)；校正太頻繁，farnocchia 呼叫次數變多 (不過 farnocchia 本身很便宜，
    O(1) 微秒等級，不是主要開銷)。實測 (見 STATUS.md) 這個預設值在 LEO 尺度、
    3 天/44 圈的測試案例上跟 GMAT (Degree=4, Order=0) 只差 ~270m，比固定步長
    RK4 (17km) 或 RK45 (410m) 都更準。

    純二體 (j2=j3=j4=0) 情況下，delta 恆為 0 (q=0, f(q)=0, delta_r_ddot=0)，
    這個函式會直接退化成 farnocchia 本身的精確解，零誤差。
    """
    r0f = np.array([r0[0], r0[1], r0[2]], dtype=np.float64)
    v0f = np.array([v0[0], v0[1], v0[2]], dtype=np.float64)

    if tof <= 0.0:
        return r0f, v0f

    # 校正點的軌道根數 (只在初始化/每次校正時算一次，見 encke_delta_accel 說明
    # 的效能修正理由)。
    p, ecc, inc, raan, argp, nu0 = rv2coe(mu, r0f, v0f)

    t_rect = 0.0
    t = 0.0
    delta_state = np.zeros(6, dtype=np.float64)

    h = dt0 if dt0 > 0.0 else 60.0
    h = min(h, tof)

    min_h = 1e-6
    max_step_attempts = 100

    while t < tof:
        h = min(h, tof - t)
        if h < min_h:
            h = min_h

        t_since_rect = t - t_rect
        accepted = False
        attempts = 0
        while not accepted and attempts < max_step_attempts:
            y5, err_vec = encke_rk45_step(t_since_rect, delta_state, h,
                                           p, ecc, inc, raan, argp, nu0, mu, j2, j3, j4, re)

            sc0 = atol + rtol * max(abs(delta_state[0]), abs(y5[0]))
            sc1 = atol + rtol * max(abs(delta_state[1]), abs(y5[1]))
            sc2 = atol + rtol * max(abs(delta_state[2]), abs(y5[2]))
            sc3 = atol + rtol * max(abs(delta_state[3]), abs(y5[3]))
            sc4 = atol + rtol * max(abs(delta_state[4]), abs(y5[4]))
            sc5 = atol + rtol * max(abs(delta_state[5]), abs(y5[5]))

            err_norm = math.sqrt(
                (err_vec[0]/sc0)**2 + (err_vec[1]/sc1)**2 + (err_vec[2]/sc2)**2 +
                (err_vec[3]/sc3)**2 + (err_vec[4]/sc4)**2 + (err_vec[5]/sc5)**2
            ) / math.sqrt(6.0)

            if err_norm <= 1.0 or h <= min_h:
                delta_state = y5
                t += h
                t_since_rect = t - t_rect
                accepted = True
                if err_norm < 1e-12:
                    factor = 5.0
                else:
                    factor = 0.9 * err_norm**(-0.2)
                    factor = min(5.0, max(0.2, factor))
                h = h * factor
            else:
                factor = 0.9 * err_norm**(-0.2)
                factor = min(1.0, max(0.1, factor))
                h = max(h * factor, min_h)
                attempts += 1

        # 校正判斷：delta_r 相對參考軌道半徑的比例超過門檻，重新拉基準
        # (重新算一次根數，之後的 step 都用這組新根數，直到下次校正)。
        nu_now = farnocchia_coe(mu, p, ecc, inc, raan, argp, nu0, t - t_rect)
        r_ref_now, v_ref_now = coe2rv(mu, p, ecc, inc, raan, argp, nu_now)
        rho_now = (r_ref_now[0]**2 + r_ref_now[1]**2 + r_ref_now[2]**2)**0.5
        delta_r_now = delta_state[:3]
        delta_r_mag = (delta_r_now[0]**2 + delta_r_now[1]**2 + delta_r_now[2]**2)**0.5
        if delta_r_mag / rho_now > rectify_threshold:
            r_rect_new = r_ref_now + delta_state[:3]
            v_rect_new = v_ref_now + delta_state[3:]
            p, ecc, inc, raan, argp, nu0 = rv2coe(mu, r_rect_new, v_rect_new)
            t_rect = t
            delta_state = np.zeros(6, dtype=np.float64)

    nu_final = farnocchia_coe(mu, p, ecc, inc, raan, argp, nu0, t - t_rect)
    r_ref_final, v_ref_final = coe2rv(mu, p, ecc, inc, raan, argp, nu_final)
    r_final = r_ref_final + delta_state[:3]
    v_final = v_ref_final + delta_state[3:]

    return r_final, v_final
