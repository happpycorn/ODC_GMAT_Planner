"""提供搜尋適應度、期限防護與決策向量尺寸
主要入口為 fast_fitness_evaluator。
"""
import math
import numpy as np
from numba import njit
from poliastro.core.iod import izzo  # 只給 njit 的 fast_fitness_evaluator 用；Python 端走 core_math.lambert_izzo
import inspect
import threading
import time
from odc.split.burn_splitter import legalize_route
from odc.scoring.scorer import (calculate_score, ranked_search_score, assess_legality,
                        SEARCH_FAIL_SCORE_RANKED, DV_LIMIT_TOL_MPS)
from odc.physics.core_math import (propagate_dop853, check_constraints, fast_norm,
                           to_vnb_frame, reaches_perigee, lambert_izzo,
                           izzo_max_revs, ephem_state, build_ephem_table, fixed_orbit_state,
                           build_wait_prefix, cached_wait_min_radius, arc_radius_from_end,
                           initial_wait_min_radius)
import numba as nb


class _PrimerSearchTimeout(Exception):
    """僅限 C2 fast 的評估期限；保留已評估的 incumbent，交回 anytime 解。"""


class _DeadlineFitness:
    """mealpy 原生 max_time 只在代末檢查；補上初始化/代內評估前的期限檢查。"""

    def __init__(self, fitness, deadline):
        self.fitness = fitness
        self.deadline = deadline
        self.best_x = None
        self.best_fitness = float("inf")
        self.lock = threading.Lock()

    def __call__(self, x):
        if time.monotonic() >= self.deadline:
            raise _PrimerSearchTimeout
        value = self.fitness(x)
        with self.lock:
            if value < self.best_fitness:
                self.best_x = np.asarray(x, dtype=np.float64).copy()
                self.best_fitness = float(value)
        return value


# 這裡把所有不變的環境常數傳進來，避免 Numba 抓取外部全域變數
# nogil=True: 純數值運算 (內部呼叫的 propagate_dop853/izzo/calculate_score 也都是 njit)，
# 沒有碰任何 Python 物件，執行時可以釋放 GIL，讓 mealpy 的 'thread' 平行模式真的吃到多核。
@njit(nb.float64(nb.float64[:], nb.int64, nb.float64[:], nb.float64[:, :]), fastmath=True, cache=True, nogil=True)
def fast_fitness_evaluator(
    x: np.ndarray, num_burns: int, 
    scalars: np.ndarray, vectors: np.ndarray
) -> float:
    """
    100% 純 JIT 的適應度函數。沒有任何 Python 物件，直接吃 Mealpy 的一維陣列。
    """

    min_coast_time = scalars[0]
    T_max = scalars[1]
    mu = scalars[2]
    j2_val = scalars[3]
    j3_val = scalars[4]
    j4_val = scalars[5]
    re_val = scalars[6]
    min_periapsis = scalars[7]
    max_dv = scalars[8]
    k_t = scalars[9]
    C_t = scalars[10]
    k_v = scalars[11]
    C_v = scalars[12]
    # 最後一棒 Lambert 要考慮的最大圈數 (0 = 舊行為，只看不繞圈的直接轉移)。
    # 放在 scalars 最後面是為了讓既有的 13 個索引位置完全不動。
    lambert_max_revs = int(scalars[13])
    # 拆棒感知搜尋 (0 = 關，等同舊行為)。開啟時對超過 max_dv 的「中間棒」預付拆棒的
    # 最少代價——見下面迴圈裡的用法與 __init__ 的 SPLIT_AWARE_SEARCH 說明。同樣接在
    # scalars 尾端 (索引 14/15)，既有索引不動。
    split_aware = scalars[14]
    dv_overhead = scalars[15]
    # 終端棒拆後估計 (C4, 2026-09-24；0 = 關，等同舊行為)。索引 16/17/18 = 旗標、可拆上限
    # 倍數 K、Δv 預付係數。舊呼叫端 (測試/scratch) 只給 16 格——numba 不做邊界檢查，
    # 讀界外會拿到垃圾值，所以依長度判斷，不足就當關。
    split_term = 0.0
    term_max_factor = 1.0
    term_overhead = 1.0
    if scalars.shape[0] >= 19:
        split_term = scalars[16]
        term_max_factor = scalars[17]
        term_overhead = scalars[18]
    # 總 Δv 上限 (排位賽 rules.MAX_TOTAL_DV_MPS，km/s；0 = 沒有上限，初賽行為)。索引 19，
    # 舊呼叫端給不到 20 格就當沒上限。
    max_total_dv = 0.0
    if scalars.shape[0] >= 20:
        max_total_dv = scalars[19]
    # 排位賽模式 = 有總 Δv 上限 (2026-10-19 v2)。這個模式下單棒超標超出拆棒器範圍
    # (索引 20：split_limit，km/s，= 拆棒器最大段數 × MAX_DV_SOFT；不拆棒時 = MAX_DV_SOFT)
    # 跟總 Δv 超標一樣進失格層 (scorer.ranked_search_score)，搜尋失敗回 SEARCH_FAIL_SCORE_RANKED。
    # 初賽模式 (max_total_dv = 0) 下面全部等同舊行為。
    ranked = max_total_dv > 0.0
    split_limit = term_max_factor * max_dv
    if scalars.shape[0] >= 21:
        split_limit = scalars[20]
    fail = 0.0
    if ranked:
        fail = -SEARCH_FAIL_SCORE_RANKED
    violation = 0.0   # 單棒超出拆棒範圍的量 (m/s)，只有排位賽模式會累加

    A_r0 = vectors[0]
    A_v0 = vectors[1]
    B_r0 = vectors[2]
    B_v0 = vectors[3]

    # scalars[21:23] = (checkpoint step, checkpoint count)。前四列維持原 ABI；
    # 後面依序是 A、B 的交錯 r/v 表，各 2*n 列。舊的四列呼叫端安全退回直積分。
    ephem_dt = 0.0
    ephem_n = 0
    if scalars.shape[0] >= 23:
        ephem_dt = scalars[21]
        ephem_n = int(scalars[22])
    use_ephem = ephem_dt > 0.0 and ephem_n > 0 and vectors.shape[0] >= 4 + 4*ephem_n
    # 僅前 N-1 棒後的滑行容差；舊呼叫端不足 24 格時維持精確值。
    coast_rtol = 1e-12
    if scalars.shape[0] >= 24:
        coast_rtol = scalars[23]
    # SEARCH 開啟的新呼叫端才帶真實單棒上限與前導可拆上限；舊 ABI 不假設下游能拆前導棒。
    # 關閉時保留原本 max_dv (= SOFT) 的所有運算，包含數值安全邊界。
    # 只有 SPLIT_LEADING 也開時才附這兩格（見 _scalar_params）；primer 重搜單開 SEARCH 時走舊算法。
    single_dv_cap = max_dv
    leading_split_limit = 0.0
    split_leading_abi = split_aware > 0.5 and scalars.shape[0] >= 26
    if split_leading_abi:
        single_dv_cap = scalars[24] + DV_LIMIT_TOL_MPS / 1000.0
        leading_split_limit = scalars[25]

    total_dv = 0.0
    penalty_count = 0
    dt = 60.0  # DOP853 初始步長猜測 (自適應積分器會自己調整實際步長)

    # 1. 初始等待時間 (t_wait)
    current_time = float(x[0])
    
    # 傳播太空船 B 到第一次點火點
    if use_ephem:
        r_curr, v_curr = ephem_state(0.0, ephem_dt,
            vectors[4 + 2*ephem_n:4 + 4*ephem_n], current_time, mu, j2_val, j3_val, j4_val, re_val)
    else:
        r_curr, v_curr = propagate_dop853(B_r0, B_v0, current_time, dt, mu, j2_val, j3_val, j4_val, re_val)

    if use_ephem and vectors.shape[0] >= 4 + 5*ephem_n:
        wait_min = cached_wait_min_radius(current_time, r_curr, ephem_dt,
            vectors[4 + 2*ephem_n:4 + 4*ephem_n], vectors[4 + 4*ephem_n:], mu)
    else:
        wait_min = arc_radius_from_end(B_r0, B_v0, current_time, r_curr, mu)
    if wait_min < min_periapsis:
        return fail

    idx = 1
    # 2. 執行前 N-1 次機動 (如果 num_burns > 1)
    for _ in range(1, num_burns):
        # 球座標參數化 (r, theta, phi)：r 本身就是 Δv 大小，bounds 已經把 r 夾在
        # [0, MAX_DV_SOFT]，天生保證合規，不會再有「合成起來超標」的無效角落。
        dv_r = x[idx]
        dv_theta = x[idx+1]
        dv_phi = x[idx+2]
        coast_frac = x[idx+3]
        idx += 4

        sin_theta = math.sin(dv_theta)
        dv_vec = np.array([
            dv_r * sin_theta * math.cos(dv_phi),
            dv_r * sin_theta * math.sin(dv_phi),
            dv_r * math.cos(dv_theta)
        ], dtype=np.float64)

        dv_mag = dv_r  # 球座標半徑本身就是 Δv 大小，不用再算一次 norm
        total_dv += dv_mag

        if split_leading_abi:
            # 與 split_est_score 同尺：只對下游可拆的前導棒預付燃料。
            # presplit_leading 以原節點為中心排開，鎖定抵達時刻，不延長任務。
            # 不能只推進時鐘卻不傳播 r/v；那會讓同一 x 在搜尋與重播代表不同軌跡。
            if dv_mag > single_dv_cap:
                if leading_split_limit > 0.0 and dv_mag <= leading_split_limit:
                    if split_term > 0.5:  # 挑贏家使用拆後估計；否則保留原始軟懲罰
                        total_dv += dv_mag * (dv_overhead - 1.0)
                    else:
                        penalty_count += 1
                elif ranked:
                    limit = leading_split_limit if leading_split_limit > 0.0 else max_dv
                    violation += (dv_mag - limit) * 1000.0
                else:
                    penalty_count += 1
        elif split_aware > 0.5:
            # SPLIT_LEADING 關（primer 重搜單開 SEARCH）：保留舊算法，逐位元不變。已知問題：只推進
            # 時鐘、不傳播 r/v，搜尋與重播不同尺（docs/research/SPLIT_AWARE_SEARCH_FIX_20261029.md）。
            if dv_mag > max_dv:
                n_seg = math.ceil(dv_mag / max_dv)
                current_time += (n_seg - 1.0) * min_coast_time
                total_dv += dv_mag * (dv_overhead - 1.0)
        else:
            if dv_mag > max_dv:  # 關旗標時理論上不會發生 (bounds 已夾)，留著當防呆
                if ranked:      # 拆棒器只拆終端棒，前導棒超標拆不掉 → 失格層
                    violation += (dv_mag - max_dv) * 1000.0
                else:
                    penalty_count += 1  # 搜尋用軟懲罰；最終交件判定這是失格 (assess_legality)

        v_curr_new = v_curr + dv_vec

        # 計算這次的海岸滑行時間 (Coast Time)。要先算出來，下面的安檢才知道這段弧多長。
        max_coast = T_max - current_time - min_coast_time
        t_coast = min_coast_time
        if max_coast > min_coast_time:
            t_coast += coast_frac * (max_coast - min_coast_time)

        # 安檢：這段弧**實際飛過**的高度會不會撞地球。
        # 舊版 (2026-08-28 之前) 無條件比密切軌道的近地點半徑，跟太空船會不會真的飛到
        # 那裡無關——這會系統性地漏掉「把一發超過上限的大燒拆成兩段幾乎同向的燒」這整個
        # 家族，而那正是繞過 ΔV_lim 的標準手法。官方公布的範例參考解就是那一類：第一棒
        # 之後中間軌道近地點 5,517 km (地表以下)，100 秒後被第二棒拉回來，實際飛過的
        # 高度完全安全。改成：弧內真的會經過近地點才比近地點半徑，否則檢查弧的兩端
        # (不經過近地點時，弧上最小半徑就是兩端取小者，見 reaches_perigee)。
        if reaches_perigee(r_curr, v_curr_new, mu, t_coast):
            if not check_constraints(r_curr, v_curr_new, mu, min_periapsis):
                return fail # 直接判定 0 分 (極度差的適應度；排位賽模式低於失格層)

        # 傳播太空船 B 經過 Coast Time
        # 精確值保留原本的預設參數呼叫，避免 Numba 動態容差特化造成末位差異。
        if coast_rtol == 1e-12:
            r_curr, v_curr = propagate_dop853(r_curr, v_curr_new, t_coast, dt, mu, j2_val, j3_val, j4_val, re_val)
        else:
            r_curr, v_curr = propagate_dop853(r_curr, v_curr_new, t_coast, dt, mu, j2_val, j3_val, j4_val, re_val, coast_rtol)
        current_time += t_coast
        if fast_norm(r_curr) < min_periapsis:      # 這段弧的終點
            return fail

    # 3. 最後一次機動 (Lambert 攔截)
    # 決定最後一段飛行時間
    final_leg_frac = x[-4]
    max_final = T_max - current_time
    t_final_leg = min_coast_time
    if max_final > min_coast_time:
        t_final_leg += final_leg_frac * (max_final - min_coast_time)

    intercept_time = current_time + t_final_leg

    # 傳播太空船 A (目標) 到攔截時間點
    if use_ephem:
        r_A_target, _ = ephem_state(0.0, ephem_dt,
            vectors[4:4 + 2*ephem_n], intercept_time, mu, j2_val, j3_val, j4_val, re_val)
    else:
        r_A_target, _ = propagate_dop853(A_r0, A_v0, intercept_time, dt, mu, j2_val, j3_val, j4_val, re_val)

    # 規則只要求 Δr <= 門檻 (預設 5km)，Δr_min 超過命中點的部分不會多加分，所以不用
    # 死盯著 A 的精確位置打：球座標 (offset_r, offset_theta, offset_phi) 讓 Lambert
    # 改瞄準 A 附近容許球內、最省油的一點。offset_r 本身就是最終會落在的實際 Δr。
    offset_r = x[-3]
    offset_theta = x[-2]
    offset_phi = x[-1]
    sin_ot = math.sin(offset_theta)
    offset_vec = np.array([
        offset_r * sin_ot * math.cos(offset_phi),
        offset_r * sin_ot * math.sin(offset_phi),
        offset_r * math.cos(offset_theta)
    ], dtype=np.float64)
    r_aim = r_A_target + offset_vec

    # 呼叫 Poliastro 內建的純 Numba Lambert 求解器 (izzo)
    # izzo 回傳的是 (v1_req, v2_req)。順向/逆向兩種轉移都算一次，取 Δv 較小的那個 —
    # A/B 兩軌道傾角差大時，逆向解常常明顯省油，只算順向會漏掉更好的解。
    #
    # izzo 內部的 Householder/Halley 疊代對某些幾何 (轉移角接近 0°/180°、極端的
    # SMA 落差之類) 會直接丟 RuntimeError("Failed to converge")，不是回傳一個
    # 很爛的解——沒接住的話，L-SHADE 族群裡剛好抽到一個這種候選解，會讓整個
    # model.solve() 當掉，白白浪費掉那個燃燒次數案例已經算好的所有結果 (實測
    # 抓到過：測極端大 SMA 的情境時 3 個案例裡有 2 個因為這樣整組報廢)。跟
    # check_constraints 撞地球的處理方式一致：算不出來就當作這組候選解爛掉，
    # 回傳 0 分讓 L-SHADE 自然淘汰它，不要讓一個候選解拖垮整次搜尋。
    # 掃過所有的 Lambert 分支，取需要 Δv 最小的那個：
    #   * 順向 / 逆向 —— A/B 傾角差大時逆向常常明顯省油，只算順向會漏掉更好的解。
    #   * 圈數 M（多圈轉移）—— 2026-08-28 加。原本寫死 M=0，等於只看「不繞滿一圈就
    #     直接過去」的轉移。實測官方範例題目：M=0 最省的合法單棒要 430.1 m/s，
    #     M=1 只要 267.3 m/s（**省 38%**），代價是抵達時間從 6,145s 拉到 11,928s。
    #     T_max 是 A 的 4 個週期，多圈轉移本來就在規則允許的範圍內，沒有理由不看。
    #   * lowpath —— M=0 時只有一組解（lowpath 沒有意義），M>=1 時同一個飛行時間有
    #     兩組解，而且差很多（上面那組 267.3 就是 lowpath=False 才找得到的）。
    # 用 lambert_max_revs=0 可以退回舊行為。
    #
    # izzo 內部的 Householder/Halley 疊代對某些幾何 (轉移角接近 0°/180°、極端的
    # SMA 落差、圈數放太多導致飛行時間根本不夠) 會直接丟 RuntimeError，不是回傳一個
    # 很爛的解——沒接住的話，L-SHADE 族群裡剛好抽到一個這種候選解，會讓整個
    # model.solve() 當掉，白白浪費掉那個燃燒次數案例已經算好的所有結果 (實測
    # 抓到過：測極端大 SMA 的情境時 3 個案例裡有 2 個因為這樣整組報廢)。跟
    # 撞地球的處理方式一致：算不出來就跳過這個分支，全部分支都失敗才回傳 0 分。
    v1_req = np.zeros(3, dtype=np.float64)
    best_req_dv = 1.0e18
    found_any = False
    # 先算每個方向最多能繞幾圈，跳過 izzo 一定會丟 "No feasible solution" 的分支——numba 內
    # raise+catch 每次漏 ~1.8 KB (REVS=4 時 contest 單 run ~1.5 GB/min)，見 core_math.izzo_max_revs。
    # 預檢只跳「一定會丟」的分支 (拿不準就照呼叫)，跳過的全是原本會進 except 的，結果不變。
    m_max_pro = izzo_max_revs(mu, r_curr, r_aim, t_final_leg, True, 35, 1e-8)
    m_max_retro = izzo_max_revs(mu, r_curr, r_aim, t_final_leg, False, 35, 1e-8)
    for m_rev in range(0, lambert_max_revs + 1):
        for lp in range(0, 2):
            if m_rev == 0 and lp == 1:
                continue                      # M=0 只有一組解，不用算兩次
            for pg in range(0, 2):
                if m_rev > (m_max_pro if pg == 0 else m_max_retro):
                    continue
                try:
                    v_try, _ = izzo(
                        mu, r_curr, r_aim, t_final_leg,
                        M=m_rev, prograde=(pg == 0), lowpath=(lp == 0),
                        numiter=35, rtol=1e-8
                    )
                except Exception:
                    continue
                d_try = fast_norm(v_try - v_curr)
                if d_try < best_req_dv:
                    best_req_dv = d_try
                    v1_req = v_try
                    found_any = True

    if not found_any:
        return fail

    # 計算需要的最後一次推力
    dv_final_vec = v1_req - v_curr
    dv_final_mag = fast_norm(dv_final_vec)
    total_dv += dv_final_mag

    if dv_final_mag > single_dv_cap:
        if ranked and dv_final_mag > split_limit:
            # 排位賽模式、超出拆棒器範圍：拆不掉就是失格，進失格層 (超得越多分數越低)。
            violation += (dv_final_mag - split_limit) * 1000.0
        elif split_term > 0.5 and dv_final_mag <= term_max_factor * max_dv:
            # 終端棒拆後估計 (C4)：這發會被拆棒器 (legalize_route) 拆成多發合法燒，實測
            # 拆後分數只比「不扣罰分」少 ~0.003 分——照舊扣 10 分會讓搜尋拿錯的尺比家族
            # (contest：88.32 家族拆後 98.32，卻輸給合法但晚到的 89.25 家族)。改成預付
            # 拆棒的燃料代價；不加時間，拆棒器鎖定 A(T)，抵達時刻不變。超過 K 倍上限的
            # 仍扣分：段數多時拆棒器的暖啟與 Earth-safe 越難保證。
            total_dv += dv_final_mag * (term_overhead - 1.0)
        else:
            # 搜尋用軟懲罰 (−10)，不是官方扣分：排位賽單棒超標直接失格，但搜尋空間不能砍——
            # DE 要能找到超標路線再交給 AUTO_SPLIT_LEGALIZE 拆棒。最終判定見 assess_legality。
            penalty_count += 1

    # 最終安檢：同上，只有最後這段轉移弧真的會經過近地點時才比近地點半徑。
    # 弧的終點是瞄準點 (在 A 附近，半徑已知安全)，所以不用再檢查終點。
    if reaches_perigee(r_curr, v1_req, mu, t_final_leg):
        if not check_constraints(r_curr, v1_req, mu, min_periapsis):
            return fail

    # 4. 結算最終分數 (利用我們剛改好的 scorer)
    # min_distance_km 理論上就是 offset_r：Lambert 打的是瞄準點，瞄準點跟 A 的真實
    # 位置差 offset_r，只要 offset_r <= miss_tol (由 bounds 保證)，Δr_min 一律地板在
    # 5 (真正的規則門檻)，不會因為瞄準點刻意偏移而被扣分。
    score = calculate_score(
        min_distance_km=offset_r,
        total_time_sec=intercept_time,
        total_dv_mps=total_dv * 1000.0,
        penalty_count=penalty_count,
        k_t=k_t, C_t=C_t, k_v=k_v, C_v=C_v
    )
    # 排位賽模式：總 Δv 超標或單棒超出拆棒範圍 → 失格層 [−20, −10)，任何合法候選 (≥ 0) 都排在
    # 它前面 (scorer.ranked_search_score)。total_dv 含拆棒預付的 overhead，比實際總量略高——方向保守。
    if ranked:
        score = ranked_search_score(score, total_dv * 1000.0, max_total_dv * 1000.0, violation)

    # Mealpy 預設是找「最小值」，所以我們把分數加負號回傳
    return -score

# 拆棒器 (burn_splitter.legalize_route) 終端棒最多拆幾段。main.legalize_violating_winner 用預設值
# 呼叫，所以直接讀它的預設參數——拆棒器改段數上限時，搜尋端的「可拆範圍」自動跟著變。
SPLITTER_MAX_SEG = int(inspect.signature(legalize_route).parameters["max_seg"].default)
# 初賽模式 (沒設 MAX_TOTAL_DV_MPS) 的 C4 可拆倍數。1500 m/s 上限時定的經驗值 (E1–E4)，
# 保留它讓初賽情境逐位元不變；排位賽模式改用 SPLITTER_MAX_SEG (見 MissionOptimizer.__init__)。
PRELIM_TERMINAL_MAX_FACTOR = 5.0


def decision_variable_dims(num_burns: int) -> int:
    """
    _generate_bounds() 產生的決策變數維度：1 (t_wait) + 4*(num_burns-1) (中間燃燒的
    r/theta/phi/coast_frac) + 1 (final_leg_frac) + 3 (瞄準點偏移
    offset_r/theta/phi) = 4*num_burns + 1。

    抽成獨立函式 (不只是 _generate_bounds 內部算好就算了) 是因為 sweep_burns.py 的
    粗掃階段需要靠這個維度數去幫不同燃燒次數案例分配「公平」的世代預算——維度公式
    只准在這裡改一處，兩邊才不會兜不起來 (_generate_bounds 底部有一個 assert 會在
    公式不同步時立刻炸出來，不會安靜地算錯)。
    """
    return 4 * num_burns + 1


def effective_burns(num_burns: int, x, dv_floor_mps: float = 1.0) -> int:
    """
    這個解「實際上」用了幾棒——中間棒 Δv 小到可以忽略的不算。

    多棒解很常退化成單棒：決策向量裡中間棒的 Δv 欄位恰好是 0，是分段貪婪種子放進去的
    「空燒」結構，L-SHADE 從頭到尾沒離開過那個起點 (2026-08-15 在三組不同的極限測資上
    都觀察到)。這種解跟單棒解的分數差異只是雜訊，不是多棒帶來的優勢，但光看 fitness
    完全分不出來，得拆開決策向量才知道。

    中間棒 i 的 Δv 大小就是 x[1+4i] (單位 km/s，見 _generate_bounds 的陣列結構)，
    不用重新傳播就能讀出來。最後一棒是 Lambert 解出來的、一定是實際燃燒，所以基數從 1 起算。

    放在模組層級是因為 main.py (印任務規劃時) 跟 sweep_burns.py (判斷建議值可不可信時)
    都要用，維度公式只准在這個檔案裡定義一次。
    """
    if x is None:
        return num_burns  # 沒有解向量就不做判斷，回報原本的燃燒次數
    count = 1
    for i in range(num_burns - 1):
        if float(x[1 + 4 * i]) * 1000.0 > dv_floor_mps:
            count += 1
    return count
