"""
HAP-67 Stage 2：確定性拆棒後處理器。

把「一發超過每棒 ΔV 上限的攔截機動」拆成 N 發合法子燒——**段數是算出來的**
(`ceil(|Δv| / cap)` 起跳、不夠再往上加)，不是像舊的 `optimizer._generate_planechange_
split_seed_candidates` 那樣被 `num_burns` 綁死 (那裡 `n_final = num_burns - 1`，是把「要拆
幾棒」當成搜尋前就得猜的輸入；本模組把它改回它本來的身分——**拆棒的輸出**)。

設計原則 (見 docs/HAP67_SPLIT_PIPELINE_PLAN.md)：
- **只負責 feasibility**：找到任何一組合法 (每段 ≤cap、每段弧 Earth-safe、命中鎖定的 A(T))
  的分解就回傳，好不好留給 Stage 3 (NLP 精修)。
- **鎖住 A(T)**：抵達點與抵達時刻固定，每段都向前重解 Lambert 瞄準同一個 A(T)——所以這套
  天生適用「終端攔截棒」這個最難的情形 (終端棒的終點是硬約束)。
- 物理判定 (碰撞、Lambert 分支) 跟 `fast_fitness_evaluator` / `split_even` **逐字一致**，
  不在第二個地方重寫一份，避免兩邊漂移。

這裡是純幾何/力學的分解器，不碰計分、不碰搜尋。輸出要再過 `fast_fitness_evaluator` 重驗
Earth-safe (唯一抓得到撞地球的，見 odc-collision-check-verification-gap 記憶)。
"""
import concurrent.futures
import functools
import math
import multiprocessing
import time
import numpy as np
from scipy.optimize import minimize
from scipy.optimize._numdiff import approx_derivative

from src.core_math import (propagate_dop853, check_constraints, fast_norm,
                           reaches_perigee, lambert_izzo)
from src.scorer import calculate_score


def _lam_best(r0, r1, tof, vref, mu, max_revs):
    """掃所有 Lambert 分支 (圈數 M / lowpath / 順逆向)，回傳「相對 vref 最省 Δv」的到達前
    速度 v_needed 與該 Δv 大小。分支政策跟 fast_fitness_evaluator / split_even 完全一致。"""
    best, bv = 1e18, None
    for m in range(max_revs + 1):
        for lp in range(2):
            if m == 0 and lp == 1:
                continue                      # M=0 只有一組解
            for pg in range(2):
                try:
                    vt, _ = lambert_izzo(mu, r0, r1, float(tof), M=m,
                                 prograde=(pg == 0), lowpath=(lp == 0))
                except Exception:
                    continue
                d = fast_norm(vt - vref)
                if d < best:
                    best, bv = d, vt
    return bv, best


def _shoot_final(r, v_guess, target, tof, mu, j2, j3, j4, re,
                 tol_km=1e-4, max_iter=12, h=1e-5):
    """終端段 shooting 修正：從 Lambert 的二體猜測 `v_guess` 出發，用 Newton（有限差分 Jacobian）
    修正燒後速度，讓 J2–J4 傳播 `tof` 秒後真的落在 `target`。回傳 (v, miss_km)。

    C4 E4 發現（docs/C4_TERMINAL_SPLIT_AWARE_PLAN.md §6.2）：`hyper_far` 終端段 ~8.4 h，二體 Lambert
    瞄準、J2–J4 傳播會偏 338～377 km，貪婪拆棒每個段數都被命中驗證拒掉。不拆的單棒解靠 GMAT DC
    修這個偏差，拆棒器這裡做同一件事。只在有攝動時呼叫——二體時 Lambert 本來就精確命中。
    每步做回溯線搜尋（miss 沒變小就步長減半），避免長弧的非線性讓 Newton 發散。
    """
    def end_pos(vv):
        return propagate_dop853(r, vv, float(tof), 60.0, mu, j2, j3, j4, re)[0]

    v = np.array(v_guess, dtype=np.float64)
    err = end_pos(v) - target
    miss = fast_norm(err)
    for _ in range(max_iter):
        if miss <= tol_km:
            break
        J = np.empty((3, 3))
        for k in range(3):
            dv = np.zeros(3)
            dv[k] = h
            J[:, k] = (end_pos(v + dv) - target - err) / h
        try:
            step = np.linalg.solve(J, err)
        except np.linalg.LinAlgError:
            break
        alpha, improved = 1.0, False
        for _ls in range(6):
            v_try = v - alpha * step
            err_try = end_pos(v_try) - target
            miss_try = fast_norm(err_try)
            if miss_try < miss:
                v, err, miss, improved = v_try, err_try, miss_try, True
                break
            alpha *= 0.5
        if not improved:
            break
    return v, miss


def _arc_safe(r, v, dtt, mu, j2, j3, j4, re, min_periapsis):
    """一段「從 (r,v) 滑行 dtt」的弧安不安全，判定邏輯跟 fast_fitness_evaluator 一致：
    弧內真的會經過近地點才比近地點半徑，否則檢查兩端取小。"""
    if reaches_perigee(r, v, mu, dtt):
        return check_constraints(r, v, mu, min_periapsis)
    r_end, _ = propagate_dop853(r, v, float(dtt), 60.0, mu, j2, j3, j4, re)
    return fast_norm(r) >= min_periapsis and fast_norm(r_end) >= min_periapsis


def split_intercept(r0, v0, t0, target, T, nseg, *, cap, min_coast,
                    mu, j2, j3, j4, re, min_periapsis, max_revs, miss_tol):
    """從 (r0, v0, t0) 用 `nseg` 段等量合法燒，打到固定的 `target` 於固定時刻 `T`。

    結構 (跟 optimizer.split_even 相同)：前 (nseg-1) 段每段間隔 `min_coast`、把「當下打到
    target 還需要的速度改變」按剩餘段數平均分一份 (但夾在 cap 內)，逐步把速度向量彎向攔截解；
    最後一段滑行剩下的 (T - t)、必須恰好 ≤cap 才算成功。每段弧都要過 Earth-safe。

    **命中驗證 (HAP-67，跟 split_even 的關鍵差別)**：split_even 當年是「種子」，只要當個
    夠好的起點、精確命中交給下游 L-SHADE/L-BFGS 收尾即可，所以它從不驗證真的打中。但這裡是
    **獨立後處理器**，回傳的解要能直接交出去，沒有下游會替它修 miss——所以最後一段打完要把
    軌跡傳播到 T、確認 `|r_end - target| ≤ miss_tol` 才算成功 (貪婪逐段的方向可能在分支間
    翻來翻去而漂掉，實測過會漂到上萬 km 卻通過 cap/Earth-safe 檢查)。

    回傳 (kicks, coasts)：kicks 是各段 ECI Δv 向量 (km/s)、coasts 是前 (nseg-1) 段的滑行秒數
    (最後一段的滑行 = T - 打完倒數第二段的時刻，由呼叫端自己算)。找不到合法分解回傳 None。
    """
    r, v, t = np.array(r0, dtype=np.float64), np.array(v0, dtype=np.float64), float(t0)
    kicks, coasts = [], []
    for s in range(nseg - 1):
        vd, _ = _lam_best(r, target, T - t, v, mu, max_revs)
        if vd is None:
            return None
        need = vd - v
        nn = fast_norm(need)
        if nn < 1e-12:
            return None
        step = min(cap, nn / (nseg - s))       # 剩餘需求平均分給剩下的段
        kk = need / nn * step
        if not _arc_safe(r, v + kk, min_coast, mu, j2, j3, j4, re, min_periapsis):
            return None
        kicks.append(kk)
        coasts.append(min_coast)
        r, v = propagate_dop853(r, v + kk, float(min_coast), 60.0, mu, j2, j3, j4, re)
        t += min_coast
        if fast_norm(r) < min_periapsis:
            return None
    vd, dvm = _lam_best(r, target, T - t, v, mu, max_revs)
    if vd is None:
        return None
    if j2 != 0.0 or j3 != 0.0 or j4 != 0.0:
        # 攝動下二體 Lambert 會偏（長終端段可達數百 km），先 shooting 修正再驗 (見 _shoot_final)。
        # 二體時完全不走這裡，結果與修正前逐位元相同。
        vd, _ = _shoot_final(r, vd, target, T - t, mu, j2, j3, j4, re)
        dvm = fast_norm(vd - v)
    if dvm > cap or not _arc_safe(r, vd, T - t, mu, j2, j3, j4, re, min_periapsis):
        return None
    # 命中驗證：最後一段打完真的落在 target 容許球內才算數 (見 docstring)。
    r_end, _ = propagate_dop853(r, vd, float(T - t), 60.0, mu, j2, j3, j4, re)
    if fast_norm(r_end - target) > miss_tol:
        return None
    kicks.append(vd - v)
    return kicks, coasts


def legalize_intercept(r0, v0, t0, target, T, *, cap, min_coast,
                       mu, j2, j3, j4, re, min_periapsis, max_revs,
                       miss_tol=5.0, max_seg=12):
    """把「從 (r0,v0,t0) 到 target@T」的攔截合法化：段數從物理下限 `ceil(|Δv_single| / cap)`
    往上掃到 `max_seg`，回傳第一組成功的分解 (含用了幾段)。

    這就是相對舊 split_even 的關鍵改變——舊的段數被 num_burns 鎖死，這裡讓段數由「需要多少」
    自己決定，所以 3× 上限的終端棒 (要 ≥4 段) 也拆得出來，不必人去改 MAX_BURNS。

    回傳 dict：{'nseg', 'kicks', 'coasts', 'single_dv_mps', 'seg_dv_mps'} 或 None (掃到上限
    仍失敗——代表這個幾何在 max_seg 段內拆不出合法解，呼叫端要誠實回報，不准偽造)。
    """
    v_needed, single_dv = _lam_best(r0, target, T - t0, v0, mu, max_revs)
    if v_needed is None:
        return None
    n_lo = max(1, math.ceil(single_dv / cap))
    for nseg in range(n_lo, max_seg + 1):
        out = split_intercept(r0, v0, t0, target, T, nseg, cap=cap, min_coast=min_coast,
                              mu=mu, j2=j2, j3=j3, j4=j4, re=re,
                              min_periapsis=min_periapsis, max_revs=max_revs, miss_tol=miss_tol)
        if out is not None:
            kicks, coasts = out
            return {
                "nseg": nseg,
                "kicks": kicks,
                "coasts": coasts,
                "single_dv_mps": single_dv * 1000.0,
                "seg_dv_mps": [fast_norm(k) * 1000.0 for k in kicks],
            }
    return None


# ───────────────────────────────────────────────────────────────────────────
# joint NLP 拆分器 (HAP-67 Stage 2 核心；HAP-47 §4 建議、PoC 驗證過的演算法)
#
# 跟上面貪婪 split_intercept 的關鍵差別：這裡把**全部 N 棒**（含終端棒）的「時刻/滑行、
# ECI Δv 向量」一起當自由變數丟進 SLSQP，命中 A(T) 是**約束**（不靠 Lambert 解終端棒），
# 目標函數直接用真實 `calculate_score`（總 Δv + 抵達時間，就是比賽分數）——所以它會在合法
# 的前提下把「拆棒多噴的 Δv」壓到最小。貪婪版降級為這裡的 warm start / N-finder。
#
# 決策向量佈局 (維度 4N+1)：x = [t0, dt_0..dt_{N-1}, dv_0(3)..dv_{N-1}(3)]
#   t0      第一棒前的等待秒數
#   dt_i    第 i 棒之後的滑行秒數 (dt_{N-1} = 最後一棒到量測點的滑行)
#   dv_i    第 i 棒的 ECI Δv 向量 (km/s)，方向+大小一起優化
# ───────────────────────────────────────────────────────────────────────────

def _osc_perigee(r, v, mu):
    """密切軌道近地點半徑 (km)。用連續量當約束，SLSQP 的有限差分梯度才抓得到
    「還差多少撞地球」。逃逸/拋物線 (a<=0) 回傳當下半徑 (這種弧不會往內鑽)。"""
    rr = fast_norm(r)
    energy = fast_norm(v) ** 2 / 2.0 - mu / rr
    if energy >= 0.0:
        return rr
    a = -mu / (2.0 * energy)
    e_vec = ((fast_norm(v) ** 2 - mu / rr) * r - np.dot(r, v) * v) / mu
    e = fast_norm(e_vec)
    return a * (1.0 - e)


def _arc_min_radius(r0, v0, dt, mu, j2, j3, j4, re):
    """一段弧的最小半徑 (km)：真的會經過近地點才回密切近地點，否則取兩端較小者。
    跟 fast_fitness_evaluator / _arc_safe 同一套幾何判定，只是回傳連續餘裕而非 bool。"""
    if reaches_perigee(r0, v0, mu, dt):
        return _osc_perigee(r0, v0, mu)
    r_end, _ = propagate_dop853(r0, v0, float(dt), 60.0, mu, j2, j3, j4, re)
    return min(fast_norm(r0), fast_norm(r_end))


def _simulate_free(x, N, mu, j2, j3, j4, re, A_r0, A_v0, B_r0, B_v0):
    """把 free-ECI 決策向量跑成一條軌跡。回傳 r_final / T_team / total_dv / miss_km /
    每棒 Δv 大小 / 每段弧最小半徑。目標函數與約束都讀這裡的結果。"""
    t0 = float(x[0])
    coasts = x[1:1 + N]
    dvs = x[1 + N:].reshape(N, 3)
    r, v = propagate_dop853(B_r0, B_v0, t0, 60.0, mu, j2, j3, j4, re)
    total_dv = 0.0
    dv_mags = np.empty(N)
    arc_minr = np.empty(N)
    for i in range(N):
        v = v + dvs[i]
        dv_mags[i] = fast_norm(dvs[i])
        total_dv += dv_mags[i]
        dt = float(coasts[i])
        arc_minr[i] = _arc_min_radius(r, v, dt, mu, j2, j3, j4, re)
        r, v = propagate_dop853(r, v, dt, 60.0, mu, j2, j3, j4, re)
    T_team = t0 + float(np.sum(coasts))
    r_A, _ = propagate_dop853(A_r0, A_v0, T_team, 60.0, mu, j2, j3, j4, re)
    return {
        "r_final": r, "T_team": T_team, "total_dv": total_dv,
        "miss_km": fast_norm(r - r_A), "dv_mags": dv_mags, "arc_minr": arc_minr,
    }


# SLSQP 求解用的約束餘裕（判 feasible 仍用真實邊界，見 joint_nlp_split docstring）。
# 分數對命中距離在 5 km 內是平的，miss 餘裕免費；cap 餘裕 0.02 m/s/棒，代價 <1e-5 分。
_NLP_CAP_MARGIN = 2e-5     # km/s
_NLP_MISS_MARGIN = 5e-3    # km
_NLP_PERI_MARGIN = 1e-3    # km


def _simulate_free_reuse(x, N, mu, j2, j3, j4, re, A_r0, A_v0, B_r0, B_v0):
    """`_simulate_free` 的逐位元等價版（SPLITTER_SPEED，2026-10-19）：原版每段弧傳播兩次——
    `_arc_min_radius` 為了取弧末半徑傳播一次、主迴圈再用**同樣的輸入**傳播一次。這裡傳播一次、
    兩邊共用。propagate_dop853 是純函式，輸出逐位元相同（tests/test_burn_splitter.py 驗）。"""
    t0 = float(x[0])
    coasts = x[1:1 + N]
    dvs = x[1 + N:].reshape(N, 3)
    r, v = propagate_dop853(B_r0, B_v0, t0, 60.0, mu, j2, j3, j4, re)
    total_dv = 0.0
    dv_mags = np.empty(N)
    arc_minr = np.empty(N)
    for i in range(N):
        v = v + dvs[i]
        dv_mags[i] = fast_norm(dvs[i])
        total_dv += dv_mags[i]
        dt = float(coasts[i])
        r_end, v_end = propagate_dop853(r, v, dt, 60.0, mu, j2, j3, j4, re)
        if reaches_perigee(r, v, mu, dt):
            arc_minr[i] = _osc_perigee(r, v, mu)
        else:
            arc_minr[i] = min(fast_norm(r), fast_norm(r_end))
        r, v = r_end, v_end
    T_team = t0 + float(np.sum(coasts))
    r_A, _ = propagate_dop853(A_r0, A_v0, T_team, 60.0, mu, j2, j3, j4, re)
    return {
        "r_final": r, "T_team": T_team, "total_dv": total_dv,
        "miss_km": fast_norm(r - r_A), "dv_mags": dv_mags, "arc_minr": arc_minr,
    }


# ── 快速有限差分（SPLITTER_SPEED，2026-10-19；數據見 docs/SPLITTER_SPEED_20261020.md）────────────
# SLSQP 沒給 jac 時，目標函數與三組約束**各自**做一次 2-point 有限差分：同一個 x 附近同樣的
# 4N+1 個擾動點，被 4 個函式各算一遍，而 joint_nlp_split 的 metrics 快取只存一筆，全部 miss——
# 每次迭代要跑 4×(4N+1) 條完整軌跡。快速路徑把「目標 + 全部約束」疊成一個向量，用 scipy 同一支
# approx_derivative、同樣的步長（abs_step = SLSQP 預設 eps）與邊界做**一次**差分，再切回各自的
# Jacobian。每個元素的算術（f(x+h e_i) − f0）/ dx_i 跟原路徑完全相同，所以 SLSQP 走出的每一步
# 逐位元一致，只是軌跡少算 3/4；擾動點還可以分給行程池並行算（fork 出來的子行程共用父行程已編譯
# 好的 numba 機器碼，數值也逐位元一致）。
_FD_EPS = float(np.sqrt(np.finfo(np.float64).eps))   # = scipy SLSQP 的預設 eps
_FD_CTX = None


def _nlp_stack(m, cap, min_periapsis, miss_tol, k_t, C_t, k_v, C_v):
    """[目標, c_cap..., c_peri..., c_miss]，各項算術跟 joint_nlp_split 的閉包逐字相同。"""
    obj = -calculate_score(m["miss_km"], m["T_team"], m["total_dv"] * 1000.0,
                           0, k_t, C_t, k_v, C_v)
    return np.concatenate(([obj],
                           (cap - _NLP_CAP_MARGIN) - m["dv_mags"],
                           m["arc_minr"] - (min_periapsis + _NLP_PERI_MARGIN),
                           [(miss_tol - _NLP_MISS_MARGIN) - m["miss_km"]]))


def _fd_init(ctx):
    global _FD_CTX
    _FD_CTX = ctx


def _fd_eval(N, x):
    """行程池 worker：算一個擾動點的疊合向量。物理常數由 _fd_init 放進全域。"""
    c = _FD_CTX
    m = _simulate_free_reuse(x, N, c["mu"], c["j2"], c["j3"], c["j4"], c["re"],
                             c["A_r0"], c["A_v0"], c["B_r0"], c["B_v0"])
    return _nlp_stack(m, c["cap"], c["min_periapsis"], c["miss_tol"],
                      c["k_t"], c["C_t"], c["k_v"], c["C_v"])


class FDPool:
    """快速有限差分的執行器。`workers<=1` 時序列算（仍省 3/4 的軌跡），>1 時開 fork 行程池。

    用法：`with FDPool(workers, ctx) as fd: joint_nlp_split(..., fd_map=fd)`。ctx 是物理與計分常數
    （見 `_fd_eval`）。行程池用 fork：子行程繼承父行程**已經編譯好**的 numba 機器碼，不會各自
    重新編譯或讀快取（冷編 vs 讀快取會差 1 ulp，見 numba-cache-state-breaks-seed-repro 記憶）。
    平台沒有 fork 時退回序列。"""

    def __init__(self, workers, ctx):
        self.workers = max(1, int(workers))
        self.ctx = ctx
        self._ex = None

    def __enter__(self):
        if self.workers > 1 and "fork" in multiprocessing.get_all_start_methods():
            self._ex = concurrent.futures.ProcessPoolExecutor(
                max_workers=self.workers, mp_context=multiprocessing.get_context("fork"),
                initializer=_fd_init, initargs=(self.ctx,))
        return self

    def __exit__(self, *exc):
        if self._ex is not None:
            self._ex.shutdown(wait=True)
            self._ex = None
        return False

    def jacobian(self, N, x, f0, bounds):
        """疊合向量在 x 的 2-point Jacobian，參數與 SLSQP 內部的差分完全相同。"""
        if self._ex is None:
            _fd_init(self.ctx)   # 序列：本行程自己當 worker
            mapper = map
        else:
            def mapper(f, it):
                xs = list(it)
                return list(self._ex.map(f, xs, chunksize=max(1, -(-len(xs) // self.workers))))
        return approx_derivative(functools.partial(_fd_eval, N), x, method="2-point",
                                 abs_step=_FD_EPS, f0=f0, bounds=bounds, workers=mapper)


def joint_nlp_split(x0, N, *, cap, min_coast, mu, j2, j3, j4, re, min_periapsis,
                    A_r0, A_v0, B_r0, B_v0, k_t, C_t, k_v, C_v,
                    T_max, miss_tol, maxiter=1000, fd_map=None, deadline=None,
                    require_feasible=False):
    """對一個 N 棒暖啟 `x0` (free-ECI 佈局) 做 SLSQP 聯合優化，回傳優化後的解與指標。

    目標 = -calculate_score(miss, T_team, 總Δv, penalty=0)；約束 (ineq ≥0)：每棒 ≤cap、
    每段弧近地點 ≥安全、命中 A(T) ≤容許。棒數 N 固定 (離散段數由呼叫端對候選 N 各跑一次取最好)。

    回傳 dict（含 x / score / total_dv_mps / T_team / miss_km / dv_mps / feasible），或 None
    (SLSQP 後仍不可行)。penalty=0 是因為 cap 約束保證合規；若 SLSQP 沒壓進 cap，feasible 會是
    False、由呼叫端丟掉。

    maxiter 與約束餘裕（C3，2026-09-23；數據見 docs/C3_CONVEX_SPLITTER_PLAN.md §6）：
    - maxiter 預設 1000：此題收斂要 236~823 次迭代，舊值 80 讓**每一次**都被截斷（status=9）。
    - SLSQP 對**略緊**的約束求解（`_NLP_*_MARGIN`），出來再用**真實**約束判 feasible。截斷/收斂
      點常貼著約束邊界、差 1e-3 量級（miss 3.501 vs 3.5、單棒 1498.01 vs 1498.00），用真實邊界
      求解時這種擦邊解會被判不可行丟掉、退回差 0.01 分的 greedy 暖啟——拆後分數的抖動主因。
    """
    x0 = np.asarray(x0, dtype=np.float64)
    _cache = {}

    def metrics(x):
        key = x.tobytes()
        if key not in _cache:
            _cache.clear()
            _cache[key] = _simulate_free(x, N, mu, j2, j3, j4, re, A_r0, A_v0, B_r0, B_v0)
        return _cache[key]

    def objective(x):
        m = metrics(x)
        return -calculate_score(m["miss_km"], m["T_team"], m["total_dv"] * 1000.0,
                                0, k_t, C_t, k_v, C_v)

    def c_cap(x):
        return (cap - _NLP_CAP_MARGIN) - metrics(x)["dv_mags"]            # 每棒 ≤cap

    def c_peri(x):
        return metrics(x)["arc_minr"] - (min_periapsis + _NLP_PERI_MARGIN)  # 每段弧 Earth-safe

    def c_miss(x):
        return np.array([(miss_tol - _NLP_MISS_MARGIN) - metrics(x)["miss_km"]])  # 命中 A(T)

    # 邊界：t0∈[0,T_max]；棒間滑行∈[min_coast,T_max]、最後一段∈[0,T_max]；dv 各分量∈[-cap,cap]。
    lb = [0.0] + [min_coast] * (N - 1) + [0.0] + [-cap] * (3 * N)
    ub = [T_max] + [T_max] * N + [cap] * (3 * N)
    bounds = list(zip(lb, ub))

    cons = [{"type": "ineq", "fun": c_cap},
            {"type": "ineq", "fun": c_peri},
            {"type": "ineq", "fun": c_miss}]
    jac = None
    if fd_map is not None:
        # 快速路徑（見 FDPool 上方說明）：值與 Jacobian 都從同一個疊合向量切出來，逐位元等價。
        lb_a, ub_a = np.array(lb, dtype=np.float64), np.array(ub, dtype=np.float64)
        _scache, _jcache = {}, {}

        def stack(x):
            key = x.tobytes()
            if key not in _scache:
                _scache.clear()
                m = _simulate_free_reuse(x, N, mu, j2, j3, j4, re, A_r0, A_v0, B_r0, B_v0)
                _scache[key] = _nlp_stack(m, cap, min_periapsis, miss_tol, k_t, C_t, k_v, C_v)
            return _scache[key]

        def jac_all(x):
            xc = np.clip(x, lb_a, ub_a)      # 跟 SLSQP 內部差分一樣先夾回邊界（gh11403）
            key = xc.tobytes()
            if key not in _jcache:
                _jcache.clear()
                # approx_derivative 回傳 J_transposed.T（F-order），J[0] 是有 stride 的 view；
                # scipy 1.16 的 SLSQP C 核心直接讀 g 的記憶體、不看 stride，會讀到錯的數字。
                _jcache[key] = np.ascontiguousarray(
                    fd_map.jacobian(N, xc, stack(xc), (lb_a, ub_a)))
            return _jcache[key]

        def objective(x):
            return stack(x)[0]

        def jac(x):
            return jac_all(x)[0]

        cons = [{"type": "ineq", "fun": lambda x: stack(x)[1:1 + N],
                 "jac": lambda x: jac_all(x)[1:1 + N]},
                {"type": "ineq", "fun": lambda x: stack(x)[1 + N:1 + 2 * N],
                 "jac": lambda x: jac_all(x)[1 + N:1 + 2 * N]},
                {"type": "ineq", "fun": lambda x: stack(x)[1 + 2 * N:],
                 "jac": lambda x: jac_all(x)[1 + 2 * N:]}]

    budget_hit = False
    if deadline is None:
        res = minimize(objective, x0, method="SLSQP", bounds=bounds, jac=jac,
                       constraints=cons, options={"maxiter": maxiter, "ftol": 1e-10})
        x_end = res.x
    else:
        # 牆鐘預算（anytime）：scipy 1.16 的 SLSQP 不理 StopIteration，用自己的例外跳出，
        # 交最後一個主迭代點。SLSQP 走不可行路徑，那一點可能不可行：`require_feasible`（呼叫端
        # 手上還沒有任何合法解）時，到期後要等到某個主迭代點用**真實約束**判可行才跳出——
        # 預算是軟的，但絕不因為預算交出不合法的結果（10-20 實測：不這樣做 s4 會退回超標原解）。
        last = [np.asarray(x0, dtype=np.float64)]

        def _cb(xk):
            last[0] = xk
            if time.monotonic() > deadline:
                if require_feasible:
                    mk = _simulate_free_reuse(np.clip(xk, np.array(lb), np.array(ub)), N, mu, j2,
                                              j3, j4, re, A_r0, A_v0, B_r0, B_v0)
                    if not (float(np.max(mk["dv_mags"])) <= cap + 1e-6
                            and float(np.min(mk["arc_minr"])) >= min_periapsis - 1e-3
                            and mk["miss_km"] <= miss_tol + 1e-6):
                        return
                raise _BudgetExceeded

        try:
            res = minimize(objective, x0, method="SLSQP", bounds=bounds, jac=jac, callback=_cb,
                           constraints=cons, options={"maxiter": maxiter, "ftol": 1e-10})
            x_end = res.x
        except _BudgetExceeded:
            x_end, budget_hit = last[0], True
    x1 = np.clip(x_end, np.array(lb), np.array(ub))
    m = _simulate_free(x1, N, mu, j2, j3, j4, re, A_r0, A_v0, B_r0, B_v0)
    feasible = (float(np.max(m["dv_mags"])) <= cap + 1e-6
                and float(np.min(m["arc_minr"])) >= min_periapsis - 1e-3
                and m["miss_km"] <= miss_tol + 1e-6)
    return {
        "x": x1, "N": N, "feasible": bool(feasible),
        "score": calculate_score(m["miss_km"], m["T_team"], m["total_dv"] * 1000.0,
                                 0, k_t, C_t, k_v, C_v),
        "total_dv_mps": m["total_dv"] * 1000.0, "T_team": m["T_team"],
        "miss_km": m["miss_km"], "dv_mps": [d * 1000.0 for d in m["dv_mags"]],
        **({"budget_hit": True} if budget_hit else {}),
    }


class _BudgetExceeded(Exception):
    """joint_nlp_split 的牆鐘預算到期（見 legalize_route 的 `wall_budget`）。"""


def _past(deadline):
    return deadline is not None and time.monotonic() > deadline


def _slot_after_capped(leading_dvs, leading_coasts, cap, min_coast, tol=1e-6):
    """前導棒重排：丟掉 Δv≈0 的空燒，並在每發**貼著 cap** 的前導棒後 `min_coast` 處補一個 Δv=0 空位。

    C3（2026-09-23）發現：contest 路線的第一棒想燒超過 cap、被夾在 1498 m/s；joint NLP 只要在它後面
    100 s 有個空位，就會把溢出的 ~50 m/s 放進去（同一路線 98.3174 → 98.3190）。DE 留下的空燒位置是
    隨機的（1270 s 用不上、100 s 才用得上），不能靠它。空位的後續滑行要 ≥ min_coast 才補。
    回傳 (dvs, coasts)；沒有任何改變時回傳 None。
    """
    dvs, coasts, changed = [], [], False
    for dv, c in zip(leading_dvs, leading_coasts):
        dv = np.asarray(dv, dtype=np.float64); c = float(c)
        if fast_norm(dv) < tol:
            # 緊跟在貼 cap 棒後的空燒（間隔 ≤1.5×min_coast）本身就是有用的空位，保留；
            # 其餘空燒位置隨機、用不上，併進前一段滑行。第一發就是空燒也保留（t0 由呼叫端管）。
            is_slot = (dvs and fast_norm(dvs[-1]) >= cap - 1e-6
                       and coasts[-1] <= 1.5 * min_coast)
            if coasts and not is_slot:
                coasts[-1] += c
                changed = True
                continue
            dvs.append(dv); coasts.append(c)
            continue
        if fast_norm(dv) >= cap - 1e-6 and c >= 2.0 * min_coast:
            dvs += [dv, np.zeros(3)]
            coasts += [min_coast, c - min_coast]
            changed = True
        else:
            dvs.append(dv); coasts.append(c)
    return (dvs, coasts) if changed else None


def legalize_route(t0, leading_dvs, leading_coasts, terminal_coast, target, *,
                   cap, min_coast, mu, j2, j3, j4, re, min_periapsis, max_revs,
                   A_r0, A_v0, B_r0, B_v0, k_t, C_t, k_v, C_v, T_max,
                   miss_tol, n_span=1, max_seg=14, maxiter=1000, slot_after_capped=True,
                   fast_fd=False, workers=1, starts=None, prune_reopt_tol=None,
                   prune_reopt_maxiter=None, wall_budget=None):
    """Stage 2 對外單一入口（見 `_legalize_route_core`）。

    `slot_after_capped=True`（預設）先用 `_slot_after_capped` 重排前導棒：丟掉無用空燒、在貼 cap
    的前導棒後補空位給 NLP 分擔溢出量；重排版拆不出合法解才退回原樣。

    SPLITTER_SPEED（2026-10-19）的開關，預設全關＝舊路徑逐位元不變：
    - `fast_fd=True`：joint NLP 改用疊合有限差分（逐位元等價、軌跡少算 3/4，見 `FDPool`）。
    - `workers>1`：拆棒器可以用幾個行程。有多個起點時一個起點一個行程（`_run_start`）；只有一個
      起點時把有限差分的擾動點分給行程池（要配 fast_fd）。結果都跟 workers=1 逐位元相同。
    - `starts`：多起點拆棒。每個元素 f 把終端棒的起點往前挪 f×(n_lo−1)×min_coast 秒
      （n_lo = 終端棒單發 Δv / cap 無條件進位，也就是連續燒的長度），各自拆完取分數最高的 feasible 解。
      貪婪拆棒只會從原本的脈衝時刻**往後**排燒，整串燒偏晚；f=0.5 讓它大致以原脈衝為中心。
      None 或 (0.0,) = 只拆原路線（舊行為）。
    - `prune_reopt_tol`（km/s）：拆完把 |Δv| < 這個值的棒剔掉，對剩下的棒數再跑一次 joint NLP
      （`prune_reopt_maxiter`，預設同 maxiter），feasible 且分數不低於原解 − `_PRUNE_REOPT_SLACK` 就換掉。
      處理「NLP 解貼在命中容許邊界、prune_null_burns 剔不掉 0.1 m/s 空棒」的殘留空燒。
    - `wall_budget`（秒）：隨時可交（anytime）。貪婪暖啟一定照跑（那是第一個合法解）；超過預算後
      SLSQP 在下一個主迭代跳出、交最後的迭代點，還沒開始的 NLP（下一個段數、退回原樣的那趟、
      其他起點、剔空棒重最佳化）全部略過，回傳到目前為止最好的 feasible 解。**結果跟機器快慢有關、
      不可逐位元重現**；沒觸發時（拆得比預算快）跟沒設一樣。
    """
    kw = dict(cap=cap, min_coast=min_coast, mu=mu, j2=j2, j3=j3, j4=j4, re=re,
              min_periapsis=min_periapsis, max_revs=max_revs, A_r0=A_r0, A_v0=A_v0,
              B_r0=B_r0, B_v0=B_v0, k_t=k_t, C_t=C_t, k_v=k_v, C_v=C_v, T_max=T_max,
              miss_tol=miss_tol, n_span=n_span, max_seg=max_seg, maxiter=maxiter)
    if (not fast_fd and starts is None and prune_reopt_tol is None and wall_budget is None
            and workers <= 1):
        return _legalize_route_slots(t0, leading_dvs, leading_coasts, terminal_coast, target,
                                     slot_after_capped=slot_after_capped, **kw)
    deadline = None if wall_budget is None else time.monotonic() + float(wall_budget)
    ctx = dict(mu=mu, j2=j2, j3=j3, j4=j4, re=re, A_r0=A_r0, A_v0=A_v0, B_r0=B_r0, B_v0=B_v0,
               cap=cap, min_periapsis=min_periapsis, miss_tol=miss_tol,
               k_t=k_t, C_t=C_t, k_v=k_v, C_v=C_v)
    if fast_fd or workers > 1:
        # 開行程池前先在本行程跑一次模擬，確保 fork 時 numba 函式都已編譯（子行程直接繼承）。
        _simulate_free_reuse(np.concatenate([[float(t0)], [float(terminal_coast)], np.zeros(3)]), 1,
                             mu, j2, j3, j4, re, A_r0, A_v0, B_r0, B_v0)
    shifts = list(_shifted_routes(t0, leading_dvs, leading_coasts, terminal_coast, target,
                                  starts, cap=cap, min_coast=min_coast, mu=mu, j2=j2, j3=j3,
                                  j4=j4, re=re, max_revs=max_revs, B_r0=B_r0, B_v0=B_v0))
    results = None
    if workers > 1 and len(shifts) > 1 and "fork" in multiprocessing.get_all_start_methods():
        # 起點之間互不相干：一個起點一個行程（fork，子行程內序列疊合差分），比把差分點分給行程池
        # 有效率（每次迭代不用來回傳 4N+1 個點）。結果跟依序跑逐位元相同，挑選順序也一樣。
        global _START_JOB
        _START_JOB = (shifts, dict(kw, slot_after_capped=slot_after_capped, deadline=deadline),
                      ctx if fast_fd else None)
        try:
            with concurrent.futures.ProcessPoolExecutor(
                    max_workers=min(workers, len(shifts)),
                    mp_context=multiprocessing.get_context("fork")) as ex:
                results = list(ex.map(_run_start, range(len(shifts))))
        finally:
            _START_JOB = None
    with FDPool(workers if (fast_fd and results is None) else 1, ctx) as pool:
        fd = pool if fast_fd else None
        best = None
        for i, shifted in enumerate(shifts):
            if results is not None:
                res = results[i]
            else:
                if best is not None and _past(deadline):
                    best["budget_hit"] = True
                    break
                res = _legalize_route_slots(*shifted, slot_after_capped=slot_after_capped,
                                            fd_map=fd, deadline=deadline, **kw)
            if res is not None and res["feasible"] and (best is None or res["score"] > best["score"]):
                best = res
                best["start_shift_sec"] = float(shifted[3]) - float(terminal_coast)
        if best is not None and prune_reopt_tol is not None and not _past(deadline):
            pr = prune_reopt(best["x"], best["N"], tol=prune_reopt_tol,
                             maxiter=prune_reopt_maxiter or maxiter, fd_map=fd,
                             cap=cap, min_coast=min_coast, mu=mu, j2=j2, j3=j3, j4=j4, re=re,
                             min_periapsis=min_periapsis, A_r0=A_r0, A_v0=A_v0, B_r0=B_r0,
                             B_v0=B_v0, k_t=k_t, C_t=C_t, k_v=k_v, C_v=C_v, T_max=T_max,
                             miss_tol=miss_tol)
            if pr is not None and pr["score"] >= best["score"] - _PRUNE_REOPT_SLACK:
                pr.update({k: best[k] for k in ("start_shift_sec", "budget_hit") if k in best})
                best = pr
    if best is not None and _past(deadline):
        best["budget_hit"] = True
    return best


# 平行多起點：fork 前放進全域，子行程只收起點編號（routes / kw 不必 pickle）。
_START_JOB = None


def _run_start(i):
    shifts, kw, ctx = _START_JOB
    if ctx is None:
        return _legalize_route_slots(*shifts[i], **kw)
    with FDPool(1, ctx) as fd:
        return _legalize_route_slots(*shifts[i], fd_map=fd, **kw)


# prune_reopt 接受「分數掉一點點」的上限：剔掉的都是 <1 m/s 的空棒，重最佳化理論上不會更差，
# 但 SLSQP 收斂點會飄 1e-6 量級；1e-4 分遠小於官方比到的小數位，換一份乾淨的繳交腳本值得。
_PRUNE_REOPT_SLACK = 1e-4


def _terminal_state(t0, leading_dvs, leading_coasts, *, mu, j2, j3, j4, re, B_r0, B_v0):
    """B 從 t0 走過前導棒/滑行後的終端棒起點 (r, v, t)。跟 `_legalize_route_core` 步驟 1 相同。"""
    r, v = propagate_dop853(np.array(B_r0, dtype=np.float64), np.array(B_v0, dtype=np.float64),
                            float(t0), 60.0, mu, j2, j3, j4, re)
    t = float(t0)
    for dv, ct in zip(leading_dvs, leading_coasts):
        v = v + np.asarray(dv, dtype=np.float64)
        r, v = propagate_dop853(r, v, float(ct), 60.0, mu, j2, j3, j4, re)
        t += float(ct)
    return r, v, t


def _shifted_routes(t0, leading_dvs, leading_coasts, terminal_coast, target, starts, *,
                    cap, min_coast, mu, j2, j3, j4, re, max_revs, B_r0, B_v0):
    """多起點拆棒的各個起點（見 legalize_route 的 `starts`）。抵達時刻與 target 不動，只把終端棒
    起點往前挪：最後一段前導滑行（沒有前導棒時是 t0）減 δ、終端滑行加 δ。挪不動（前導滑行
    已經貼 min_coast）就夾到能挪的最大值；挪完跟已列過的起點重複就跳過。"""
    yield (t0, leading_dvs, leading_coasts, terminal_coast, target)
    fracs = [float(f) for f in (starts or ()) if float(f) > 0.0]
    if not fracs:
        return
    r_t, v_t, t_term = _terminal_state(t0, leading_dvs, leading_coasts, mu=mu, j2=j2, j3=j3,
                                       j4=j4, re=re, B_r0=B_r0, B_v0=B_v0)
    _, single = _lam_best(r_t, target, float(terminal_coast), v_t, mu, max_revs)
    n_lo = max(1, math.ceil(single / cap)) if single < 1e17 else 1
    room = (float(leading_coasts[-1]) - min_coast) if len(leading_dvs) else float(t0)
    seen = {0.0}
    for f in fracs:
        d = min(f * (n_lo - 1) * min_coast, max(room, 0.0))
        d = round(d, 6)
        if d <= 0.0 or d in seen:
            continue
        seen.add(d)
        if len(leading_dvs):
            lc = list(leading_coasts)
            lc[-1] = float(lc[-1]) - d
            yield (t0, leading_dvs, lc, float(terminal_coast) + d, target)
        else:
            yield (float(t0) - d, leading_dvs, leading_coasts, float(terminal_coast) + d, target)


def prune_reopt(x, N, *, tol, maxiter, fd_map, cap, min_coast, mu, j2, j3, j4, re, min_periapsis,
                A_r0, A_v0, B_r0, B_v0, k_t, C_t, k_v, C_v, T_max, miss_tol):
    """剔除 |Δv| < tol 的棒後對剩下的棒數重跑 joint NLP（SPLITTER_SPEED 3，見 legalize_route）。
    候選 = 剔除版本身、剔除版的 NLP 結果；回傳 feasible 中分數最高者（`_eval_free` 格式），
    沒東西可剔或都不可行回 None。"""
    xd, Nd = drop_null_burns(x, N, tol)
    if Nd == N:
        return None
    ev = functools.partial(_eval_free, N=Nd, cap=cap, min_periapsis=min_periapsis, mu=mu, j2=j2,
                           j3=j3, j4=j4, re=re, A_r0=A_r0, A_v0=A_v0, B_r0=B_r0, B_v0=B_v0,
                           k_t=k_t, C_t=C_t, k_v=k_v, C_v=C_v, miss_tol=miss_tol)
    cands = [ev(xd)]
    # 剔掉的殘量乘上長滑行會讓命中點偏掉，原解又貼在命中容許邊界上（hyper_far p0：剔完就不可行、
    # SLSQP 從不可行點也爬不回來）。先用最後一棒把命中點拉回原解的位置，再從那裡重最佳化。
    target = _simulate_free_reuse(x, N, mu, j2, j3, j4, re, A_r0, A_v0, B_r0, B_v0)["r_final"]
    xr = _retarget_last(xd, Nd, target, cap, mu, j2, j3, j4, re, B_r0, B_v0)
    if xr is not None:
        cands.append(ev(xr))
    x_nlp = xr if xr is not None else xd
    cands.append(joint_nlp_split(x_nlp, Nd, cap=cap, min_coast=min_coast, mu=mu, j2=j2, j3=j3, j4=j4,
                                 re=re, min_periapsis=min_periapsis, A_r0=A_r0, A_v0=A_v0,
                                 B_r0=B_r0, B_v0=B_v0, k_t=k_t, C_t=C_t, k_v=k_v, C_v=C_v,
                                 T_max=T_max, miss_tol=miss_tol, maxiter=maxiter, fd_map=fd_map))
    best = None
    for cand in cands:
        if cand["feasible"] and (best is None or cand["score"] > best["score"]):
            best = cand
    return best


def _retarget_last(x, N, target, cap, mu, j2, j3, j4, re, B_r0, B_v0):
    """把 free-ECI 解的最後一棒用 `_shoot_final` 重新瞄準 `target`（抵達時刻不變），回傳新的 x；
    重瞄後超過 cap 或沒修到 1 m 內回 None。"""
    x = np.asarray(x, dtype=np.float64).copy()
    coasts = x[1:1 + N]
    dvs = x[1 + N:].reshape(N, 3)
    r, v = propagate_dop853(B_r0, B_v0, float(x[0]), 60.0, mu, j2, j3, j4, re)
    for i in range(N - 1):
        r, v = propagate_dop853(r, v + dvs[i], float(coasts[i]), 60.0, mu, j2, j3, j4, re)
    v_new, miss = _shoot_final(r, v + dvs[N - 1], target, float(coasts[N - 1]),
                               mu, j2, j3, j4, re, tol_km=1e-6)
    dv_new = v_new - v
    if miss > 1e-3 or fast_norm(dv_new) > cap:
        return None
    x[1 + N + 3 * (N - 1):] = dv_new
    return x


def _legalize_route_slots(t0, leading_dvs, leading_coasts, terminal_coast, target, *,
                          slot_after_capped=True, **kw):
    """`legalize_route` 原本的主體：先試 `_slot_after_capped` 重排版，拆不出才退回原樣。"""
    if slot_after_capped:
        aug = _slot_after_capped(leading_dvs, leading_coasts, kw["cap"], kw["min_coast"])
        if aug is not None:
            res = _legalize_route_core(t0, aug[0], aug[1], terminal_coast, target, **kw)
            if res is not None and res["feasible"]:
                return res
            if res is not None and _past(kw.get("deadline")):
                return res
    return _legalize_route_core(t0, leading_dvs, leading_coasts, terminal_coast, target, **kw)


def _legalize_route_core(t0, leading_dvs, leading_coasts, terminal_coast, target, *,
                         cap, min_coast, mu, j2, j3, j4, re, min_periapsis, max_revs,
                         A_r0, A_v0, B_r0, B_v0, k_t, C_t, k_v, C_v, T_max,
                         miss_tol, n_span=1, max_seg=14, maxiter=1000, fd_map=None,
                         deadline=None):
    """Stage 2 核心：吃一條「前導合法棒 + 一發(可能超標的)終端攔截」的 route，
    回傳**合法化 + joint-NLP 優化後**的最佳解（free-ECI），或 None（拆不出）。

    流程：
      1. 把 B 從 t0 傳過前導棒/滑行，算出終端棒起點 (r_t, v_t, t_term) 與抵達時刻 T_arr。
      2. 貪婪 `legalize_intercept` 把終端攔截拆成合法段（動態段數 = N-finder + warm start）。
      3. 對候選段數（found .. found+n_span）各組一個 free-ECI warm start、跑 `joint_nlp_split`，
         取 feasible 且分數最高者。

    `leading_dvs`/`leading_coasts`：前導棒的 ECI Δv 向量與各自之後的滑行秒數（長度相同）。
    `terminal_coast`：終端棒打完到量測點的滑行秒數。`target`：要命中的點（通常 A(T_arr)）。
    """
    # 1. 傳播到終端棒起點
    r, v, t = np.array(B_r0, dtype=np.float64), np.array(B_v0, dtype=np.float64), 0.0
    r, v = propagate_dop853(r, v, float(t0), 60.0, mu, j2, j3, j4, re)
    t = float(t0)
    for dv, ct in zip(leading_dvs, leading_coasts):
        v = v + np.asarray(dv, dtype=np.float64)
        r, v = propagate_dop853(r, v, float(ct), 60.0, mu, j2, j3, j4, re)
        t += float(ct)
    r_t, v_t, t_term = r.copy(), v.copy(), t
    T_arr = t_term + float(terminal_coast)

    # 2. 貪婪拆終端，拿到可行段數下限
    g = legalize_intercept(r_t, v_t, t_term, target, T_arr, cap=cap, min_coast=min_coast,
                           mu=mu, j2=j2, j3=j3, j4=j4, re=re, min_periapsis=min_periapsis,
                           max_revs=max_revs, miss_tol=miss_tol, max_seg=max_seg)
    if g is None:
        return None
    nseg0 = g["nseg"]

    # 3. 對候選段數各跑一次 joint NLP，取分數最高的 feasible 解
    best = None
    for nseg in range(nseg0, min(nseg0 + n_span, max_seg) + 1):
        gg = (g if nseg == nseg0 else
              _greedy_at(r_t, v_t, t_term, target, T_arr, nseg, cap, min_coast,
                         mu, j2, j3, j4, re, min_periapsis, max_revs, miss_tol))
        if gg is None:
            continue
        N = len(leading_dvs) + nseg
        dvs = list(leading_dvs) + gg["kicks"]
        final_leg = T_arr - (t_term + (nseg - 1) * min_coast)
        coasts = list(leading_coasts) + [min_coast] * (nseg - 1) + [final_leg]
        x0 = np.concatenate([[t0], np.array(coasts), np.array(dvs).ravel()])
        # 候選 1：greedy 暖啟本身（split_intercept 保證它合法+命中，是可行解的保底）。
        # 候選 2：joint NLP 精修結果。SLSQP 有時會把可行暖啟推到邊界外（有限差分梯度在
        # 多圈傳播上有雜訊），那一步就不可行——這時**不能**把暖啟一起丟掉，所以兩個都評，
        # 取 feasible 且分數最高者。
        cands = [_eval_free(x0, N, cap, min_periapsis, mu, j2, j3, j4, re,
                            A_r0, A_v0, B_r0, B_v0, k_t, C_t, k_v, C_v, miss_tol)]
        if _past(deadline) and (best is not None or cands[0]["feasible"]):
            cands[0]["budget_hit"] = True          # 預算已到：只收 greedy 暖啟，不再開 NLP
        else:
            cands.append(joint_nlp_split(x0, N, cap=cap, min_coast=min_coast, mu=mu, j2=j2, j3=j3,
                                         j4=j4, re=re, min_periapsis=min_periapsis, A_r0=A_r0,
                                         A_v0=A_v0, B_r0=B_r0, B_v0=B_v0, k_t=k_t, C_t=C_t, k_v=k_v,
                                         C_v=C_v, T_max=T_max, miss_tol=miss_tol, maxiter=maxiter,
                                         fd_map=fd_map, deadline=deadline,
                                         require_feasible=(best is None
                                                           and not cands[0]["feasible"])))
        for cand in cands:
            if cand["feasible"] and (best is None or cand["score"] > best["score"]):
                best = cand
    return best


def drop_null_burns(x, N, tol=1e-6):
    """把 free-ECI 解裡 |Δv| < tol (km/s) 的空燒剔除，滑行時間併進前一段（第一棒空就併進 t0）。

    joint NLP 收斂後常把多餘的段壓到 0（C3：contest 的 A1 解帳面 7 棒、實燒 5 棒）；DE 也會
    留下 Δv≈0 的空燒棒。它們合規（間隔只會變長）但會讓繳交腳本出現「Δv=0 的 Maneuver」、
    讓評審困惑，且空的最後一棒會變成 GMAT DC 打靶棒。軌跡完全不變：空燒不改速度，合併的只是
    傳播時間切點。回傳 (x_new, N_new)；全部都空（不該發生）時原樣回傳。
    """
    x = np.asarray(x, dtype=np.float64)
    t0 = float(x[0])
    coasts = [float(c) for c in x[1:1 + N]]
    dvs = x[1 + N:].reshape(N, 3)
    keep_dv, keep_coast = [], []
    for i in range(N):
        if fast_norm(dvs[i]) < tol:
            if keep_coast:
                keep_coast[-1] += coasts[i]
            else:
                t0 += coasts[i]
            continue
        keep_dv.append(dvs[i].copy())
        keep_coast.append(coasts[i])
    if not keep_dv or len(keep_dv) == N:
        return x, N
    n = len(keep_dv)
    return np.concatenate([[t0], np.array(keep_coast), np.array(keep_dv).ravel()]), n


def prune_null_burns(x, N, cap, min_periapsis, mu, j2, j3, j4, re,
                     A_r0, A_v0, B_r0, B_v0, k_t, C_t, k_v, C_v, miss_tol, tols=(5e-5, 1e-9)):
    """`drop_null_burns` 的安全版：依序試每個門檻 (km/s)，剔除後用**真實約束重評**
    （cap / 近地點 / 命中 ≤miss_tol），第一個仍 feasible 的就採用；回傳 `_eval_free` 格式的
    dict（分數/Δr/Δv 全是剔除後重算的，前後自洽），沒東西可剔或都不可行回 None（沿用原解）。

    為什麼門檻不能只取「真的 0」：joint NLP 用有限差分梯度，多餘段只會壓到 mm/s 級
    （contest 實測終端殘留 1.8 mm/s），不是 0。但 mm/s 乘上數千秒滑行就是好幾 m 的位置差
    （實測剔 1 mm/s 級 → Δr 偏 1.5 m），所以剔完必須重評、不能假設軌跡不變。50 mm/s 上限
    最多偏 ~150 m，對 3.5 km 瞄準點 vs 5 km 規則門檻綽綽有餘；GMAT DC 也會對最後一發實燒重打靶。
    """
    for tol in tols:
        xd, Nd = drop_null_burns(x, N, tol)
        if Nd == N:
            continue
        ev = _eval_free(xd, Nd, cap, min_periapsis, mu, j2, j3, j4, re,
                        A_r0, A_v0, B_r0, B_v0, k_t, C_t, k_v, C_v, miss_tol)
        if ev["feasible"]:
            return ev
    return None


def _eval_free(x, N, cap, min_periapsis, mu, j2, j3, j4, re,
               A_r0, A_v0, B_r0, B_v0, k_t, C_t, k_v, C_v, miss_tol):
    """把一個 free-ECI 解評成跟 joint_nlp_split 同形狀的 dict（不優化，只算分數+可行性）。
    用來把 greedy 暖啟當候選，確保可行的 greedy 解不會因為 NLP 那步變差就被丟掉。"""
    m = _simulate_free(x, N, mu, j2, j3, j4, re, A_r0, A_v0, B_r0, B_v0)
    feasible = (float(np.max(m["dv_mags"])) <= cap + 1e-6
                and float(np.min(m["arc_minr"])) >= min_periapsis - 1e-3
                and m["miss_km"] <= miss_tol + 1e-6)
    return {
        "x": np.asarray(x, dtype=np.float64), "N": N, "feasible": bool(feasible),
        "score": calculate_score(m["miss_km"], m["T_team"], m["total_dv"] * 1000.0,
                                 0, k_t, C_t, k_v, C_v),
        "total_dv_mps": m["total_dv"] * 1000.0, "T_team": m["T_team"],
        "miss_km": m["miss_km"], "dv_mps": [d * 1000.0 for d in m["dv_mags"]],
    }


def _greedy_at(r0, v0, t0, target, T, nseg, cap, min_coast, mu, j2, j3, j4, re,
               min_periapsis, max_revs, miss_tol):
    """強制用指定 nseg 拆，回傳跟 legalize_intercept 同形狀的 dict 或 None。"""
    out = split_intercept(r0, v0, t0, target, T, nseg, cap=cap, min_coast=min_coast,
                          mu=mu, j2=j2, j3=j3, j4=j4, re=re, min_periapsis=min_periapsis,
                          max_revs=max_revs, miss_tol=miss_tol)
    if out is None:
        return None
    kicks, coasts = out
    return {"nseg": nseg, "kicks": kicks, "coasts": coasts}
