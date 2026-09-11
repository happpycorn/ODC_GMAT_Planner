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
import math
import numpy as np
from poliastro.core.iod import izzo
from scipy.optimize import minimize

from src.core_math import (propagate_dop853, check_constraints, fast_norm,
                           reaches_perigee)
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
                    vt, _ = izzo(mu, r0, r1, float(tof), M=m,
                                 prograde=(pg == 0), lowpath=(lp == 0),
                                 numiter=35, rtol=1e-8)
                except Exception:
                    continue
                d = fast_norm(vt - vref)
                if d < best:
                    best, bv = d, vt
    return bv, best


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
    if vd is None or dvm > cap or not _arc_safe(r, vd, T - t, mu, j2, j3, j4, re, min_periapsis):
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


def joint_nlp_split(x0, N, *, cap, min_coast, mu, j2, j3, j4, re, min_periapsis,
                    A_r0, A_v0, B_r0, B_v0, k_t, C_t, k_v, C_v,
                    T_max, miss_tol, maxiter=80):
    """對一個 N 棒暖啟 `x0` (free-ECI 佈局) 做 SLSQP 聯合優化，回傳優化後的解與指標。

    目標 = -calculate_score(miss, T_team, 總Δv, penalty=0)；約束 (ineq ≥0)：每棒 ≤cap、
    每段弧近地點 ≥安全、命中 A(T) ≤容許。棒數 N 固定 (離散段數由呼叫端對候選 N 各跑一次取最好)。

    回傳 dict（含 x / score / total_dv_mps / T_team / miss_km / dv_mps / feasible），或 None
    (SLSQP 後仍不可行)。penalty=0 是因為 cap 約束保證合規；若 SLSQP 沒壓進 cap，feasible 會是
    False、由呼叫端丟掉。
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
        return cap - metrics(x)["dv_mags"]                 # 每棒 ≤cap

    def c_peri(x):
        return metrics(x)["arc_minr"] - min_periapsis      # 每段弧 Earth-safe

    def c_miss(x):
        return np.array([miss_tol - metrics(x)["miss_km"]])  # 命中 A(T)

    # 邊界：t0∈[0,T_max]；棒間滑行∈[min_coast,T_max]、最後一段∈[0,T_max]；dv 各分量∈[-cap,cap]。
    lb = [0.0] + [min_coast] * (N - 1) + [0.0] + [-cap] * (3 * N)
    ub = [T_max] + [T_max] * N + [cap] * (3 * N)
    bounds = list(zip(lb, ub))

    res = minimize(objective, x0, method="SLSQP", bounds=bounds,
                   constraints=[{"type": "ineq", "fun": c_cap},
                                {"type": "ineq", "fun": c_peri},
                                {"type": "ineq", "fun": c_miss}],
                   options={"maxiter": maxiter, "ftol": 1e-10})
    x1 = np.clip(res.x, np.array(lb), np.array(ub))
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
    }


def legalize_route(t0, leading_dvs, leading_coasts, terminal_coast, target, *,
                   cap, min_coast, mu, j2, j3, j4, re, min_periapsis, max_revs,
                   A_r0, A_v0, B_r0, B_v0, k_t, C_t, k_v, C_v, T_max,
                   miss_tol, n_span=1, max_seg=14, maxiter=80):
    """Stage 2 對外單一入口：吃一條「前導合法棒 + 一發(可能超標的)終端攔截」的 route，
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
        for cand in (_eval_free(x0, N, cap, min_periapsis, mu, j2, j3, j4, re,
                                A_r0, A_v0, B_r0, B_v0, k_t, C_t, k_v, C_v, miss_tol),
                     joint_nlp_split(x0, N, cap=cap, min_coast=min_coast, mu=mu, j2=j2, j3=j3,
                                     j4=j4, re=re, min_periapsis=min_periapsis, A_r0=A_r0, A_v0=A_v0,
                                     B_r0=B_r0, B_v0=B_v0, k_t=k_t, C_t=C_t, k_v=k_v, C_v=C_v,
                                     T_max=T_max, miss_tol=miss_tol, maxiter=maxiter)):
            if cand["feasible"] and (best is None or cand["score"] > best["score"]):
                best = cand
    return best


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
