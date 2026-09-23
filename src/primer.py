"""攔截版二體 primer vector 診斷（C1，2026-09-22）。

**定位：羅盤，不是 solver、不是失格線。** 只回答一件事——「這條（可能次優的）解，沿途
有沒有哪一段 `|p(t)| > 1`（＝該處插一發中途脈衝能降總成本 / 現有節點放錯位置）」。設計/
理論依據見 `docs/C1_PRIMER_VECTOR_STUDY.md`。第一版**只在二體模型算**（決定性弧段短、J2
在該尺度動不了結論），純診斷輸出，不改任何搜尋行為。

核心數學（兩點都在 study 文件，這裡只記結論）
─────────────────────────────────────────
1. primer `p(t)` 與位置擾動 `δr(t)` **用同一個狀態轉移矩陣 (STM)**——因為 `p̈ = G(t)·p`
   跟 `δr̈ = G(t)·δr` 是同一條線性方程（G = 重力梯度 ∂(-μr/|r|³)/∂r）。所以
       p(t)  = Φrr(t,t_i)·p_i + Φrv(t,t_i)·ṗ_i
   其中 Φrr=∂r(t)/∂r_i、Φrv=∂r(t)/∂v_i 是**狀態** STM 的分塊（Prussing/Conway）。
2. 每段 coast 弧是個兩點邊界問題：已知 p_i、p_{i+1}（弧兩端的 primer），解出 ṗ_i =
   Φrv(t_{i+1})⁻¹·(p_{i+1} − Φrr(t_{i+1})·p_i)，再用上式取樣整段 |p(t)|。

邊界值（**攔截變體，跟 rendezvous 不同**）
─────────────────────────────────────────
- 每個脈衝時刻：Lawden 條件 `p = Δv/|Δv|`（primer 與推力同向、|p|=1）。
- **攔截末端（末端速度自由、scorer 又無速度成本）**：橫截條件給 `λ_v(t_f)=0`，即
  **`p(t_f) = 0`**。這是攔截跟 rendezvous 的關鍵差異：末端不需為匹配速度而燒，最後一段
  coast 收在 primer=0，不是收在單位向量。
"""
import numpy as np
from scipy.integrate import solve_ivp


def _deriv_state_stm(t, y, mu):
    """[r(3), v(3), Φ(6×6 flatten=36)] 的導數：二體 + 變分方程 dΦ/dt = A(t)·Φ。"""
    r = y[0:3]
    v = y[3:6]
    Phi = y[6:].reshape(6, 6)
    rn = np.linalg.norm(r)
    a = -mu * r / rn**3
    # 重力梯度 G = ∂a/∂r = -μ/rn³ (I − 3 r r^T / rn²)
    G = -mu / rn**3 * (np.eye(3) - 3.0 * np.outer(r, r) / rn**2)
    A = np.zeros((6, 6))
    A[0:3, 3:6] = np.eye(3)
    A[3:6, 0:3] = G
    dPhi = A @ Phi
    return np.concatenate([v, a, dPhi.ravel()])


def _arc_stm(r_i, v_i, dt, mu, n_samp):
    """從 (r_i, v_i) 積分 dt，回傳在 n_samp 個時間點的 (ts, states, Φ列表)。dense=True。"""
    y0 = np.concatenate([r_i, v_i, np.eye(6).ravel()])
    sol = solve_ivp(_deriv_state_stm, (0.0, dt), y0, args=(mu,),
                    dense_output=True, rtol=1e-10, atol=1e-12, method="DOP853")
    ts = np.linspace(0.0, dt, n_samp)
    Phis = []
    for tt in ts:
        y = sol.sol(tt)
        Phis.append(y[6:].reshape(6, 6))
    return ts, Phis


def _unit(x):
    n = np.linalg.norm(x)
    return x / n if n > 1e-12 else np.zeros(3)


def intercept_primer_profile(r0, v0, impulses, t_intercept, mu, n_samp=41):
    """算一條攔截解的 primer 剖面。

    參數
    ----
    r0, v0 : 第一發脈衝**之前**的狀態（在第一發的時刻）。
    impulses : [(t_k, dv_vec_k), ...] 依時間排序的脈衝（絕對時刻秒、ECI Δv 向量 km/s）。
               第一發的 t 應等於 r0/v0 的時刻。
    t_intercept : 攔截時刻（最後一發之後 coast 到這裡命中目標）。
    mu : 重力參數。

    回傳 dict：
      'arcs'      : 每段 [{'kind','t0','t1','p_peak','p_end_norm','samples':(ts,|p|)}]
      'max_peak'  : 全程 |p| 峰值（>1 → 有段落該插棒 / 節點放錯）
      'verdict'   : 'optimal-ish' (max_peak ≤ 1+tol) 或 'add-node' (>)
      'worst_arc' : max_peak 落在第幾段
    """
    imp = sorted(impulses, key=lambda x: x[0])
    # 逐段建立 coast 弧的起點狀態（脈衝後）與該弧兩端 primer 邊界
    # 先把狀態串起來：從 r0,v0 在第一發時刻開始，套第一發 → coast → 套第二發 …… → coast 到攔截
    r = np.array(r0, dtype=float)
    v = np.array(v0, dtype=float)
    t = imp[0][0]
    arcs = []
    for idx, (tk, dvk) in enumerate(imp):
        # 套用這一發（假設狀態已 propagate 到 tk；呼叫端保證 impulses 的時刻與傳入狀態一致）
        v = v + np.asarray(dvk, dtype=float)
        p_start = _unit(dvk)
        # 這一發之後 coast 到「下一發」或「攔截」
        if idx + 1 < len(imp):
            t_next = imp[idx + 1][0]
            p_end = _unit(imp[idx + 1][1])   # 下一發：primer = 單位向量
            kind = "inter-impulse"
        else:
            t_next = t_intercept
            p_end = np.zeros(3)               # 攔截末端：primer = 0（速度自由）
            kind = "to-intercept"
        dt = t_next - tk
        if dt <= 1e-9:
            continue
        ts, Phis = _arc_stm(r, v, dt, mu, n_samp)
        Phi_f = Phis[-1]
        Frr_f, Frv_f = Phi_f[0:3, 0:3], Phi_f[0:3, 3:6]
        # 解 ṗ_i：p_end = Frr_f p_start + Frv_f ṗ_i
        pdot_i = np.linalg.solve(Frv_f, p_end - Frr_f @ p_start)
        pmag = []
        for Phi in Phis:
            Frr, Frv = Phi[0:3, 0:3], Phi[0:3, 3:6]
            p = Frr @ p_start + Frv @ pdot_i
            pmag.append(float(np.linalg.norm(p)))
        pmag = np.array(pmag)
        arcs.append({
            "kind": kind, "t0": tk, "t1": t_next,
            "p_peak": float(pmag.max()), "p_peak_frac": float(ts[int(pmag.argmax())] / dt),
            "p_end_norm": float(pmag[-1]),
            "samples": (t + ts, pmag),
        })
        # propagate 狀態到下一發時刻，供下一圈套用
        y0 = np.concatenate([r, v, np.eye(6).ravel()])
        sol = solve_ivp(_deriv_state_stm, (0.0, dt), y0, args=(mu,),
                        rtol=1e-10, atol=1e-12, method="DOP853")
        r = sol.y[0:3, -1]
        v = sol.y[3:6, -1]
        t = t_next

    max_peak = max((a["p_peak"] for a in arcs), default=0.0)
    worst = int(np.argmax([a["p_peak"] for a in arcs])) if arcs else -1
    tol = 1e-2
    return {
        "arcs": arcs,
        "max_peak": max_peak,
        "worst_arc": worst,
        "verdict": "optimal-ish" if max_peak <= 1.0 + tol else "add-node",
    }


# ─────────────────────────────────────────────────────────────────────────────
# C2（2026-09-22）：primer 說 add-node 時，把「該加哪、加在哪」翻成一顆搜尋種子。
# 這裡**只做決策向量的算術**（coast_frac ↔ 秒的換算是 T_max/min_coast 的純函數，
# 不需傳播），保持 primer.py 無 optimizer 依賴、可獨立單元測。接線見
# main._primer_guided_research（診斷贏家 → 開 SPLIT_AWARE + 注入這顆種子 → 重搜取優）。
# ─────────────────────────────────────────────────────────────────────────────
def _arc_schedule(x, num_burns, T_max, min_coast):
    """把標準決策向量解成每段 coast 弧的 (起點絕對時刻, 持續秒數)。

    弧的編號跟 `intercept_primer_profile` 一致：arc m（m=0..num_burns-2）是第 m 顆
    leading 燒之後的滑行，arc num_burns-1 是收尾 Lambert 弧（to-intercept）。純算術，
    coast_frac→秒的公式逐字對齊 `reconstruct_mission_logs` / `_generate_bounds`。
    """
    x = np.asarray(x, dtype=float)
    arcs = []
    cur = float(x[0])
    idx = 1
    for _ in range(num_burns - 1):
        cf = float(x[idx + 3]); idx += 4
        mx = T_max - cur - min_coast
        d = min_coast + cf * (mx - min_coast) if mx > min_coast else min_coast
        arcs.append((cur, d))
        cur += d
    flf = float(x[-4])
    mxf = T_max - cur
    d = min_coast + flf * (mxf - min_coast) if mxf > min_coast else min_coast
    arcs.append((cur, d))
    return arcs


def _coast_frac(duration, start_time, T_max, min_coast):
    """把「這一段要滑 duration 秒、起點在 start_time」反解回 coast_frac∈[0,1]。"""
    span = T_max - start_time - min_coast
    if span <= 0.0:
        return 0.0
    return float(np.clip((duration - min_coast) / span, 0.0, 1.0))


def insert_node_seed(x, num_burns, arc_idx, frac, T_max, min_coast):
    """在 primer 指的弧上插一顆 Δv=0 的節點，回傳 (num_burns+1) 棒的決策向量種子。

    設計要點
    ────────
    - **插零燒不改軌跡**：新節點 Δv=0（球座標 r=0，方向無所謂），把 arc_idx 這段
      coast 依 `frac` 一切為二。因為總滑行時間不變、後續各燒的絕對時刻都不動，所以
      後面每一段的 coast_frac 保持原值，只有被切的那段改寫。重播出來的路徑跟原解
      幾乎重合，是個「合法、保守、就差一顆待 DE 去啟用的節點」的起點——正是
      primer 想表達的「這裡該有節點」。
    - **維持 100s 最短間隔**：兩個半段都夾到 ≥min_coast（切不動時退回等分，容忍
      種子微幅違規，反正會被 clip、DE 也會修）。
    - arc_idx 可指 leading 弧（0..num_burns-2）或收尾弧（num_burns-1）；後者等於在
      收尾 Lambert 前多插一顆 leading 燒。

    參數與 `_arc_schedule` 同慣例。回傳長度 = decision_variable_dims(num_burns+1)。
    """
    x = np.asarray(x, dtype=float)
    sched = _arc_schedule(x, num_burns, T_max, min_coast)
    c_start, D = sched[arc_idx]
    # frac 夾到兩個半段都 ≥ min_coast（切得動的話）
    if D > 2.0 * min_coast:
        lo, hi = min_coast / D, 1.0 - min_coast / D
        frac = float(np.clip(frac, lo, hi))
    else:
        frac = 0.5
    d1 = frac * D
    d2 = D - d1
    cf1 = _coast_frac(d1, c_start, T_max, min_coast)
    cf2 = _coast_frac(d2, c_start + d1, T_max, min_coast)
    zero_tuple = [0.0, 0.0, 0.0, cf1]   # Δv=0 的新節點 + 前半段 coast

    t0 = float(x[0])
    # 拆出原本的 leading tuples 與尾段
    lead = [list(x[1 + 4 * m: 1 + 4 * m + 4]) for m in range(num_burns - 1)]
    final_leg = float(x[-4])
    offsets = list(x[-3:])

    if arc_idx <= num_burns - 2:
        # 切 leading 弧 arc_idx：原 tuple 保留 Δv、coast 改成前半；插入零節點承接後半
        new_lead = []
        for m, tup in enumerate(lead):
            if m == arc_idx:
                t = list(tup); t[3] = cf1          # 原燒 → 前半段
                new_lead.append(t)
                z = [0.0, 0.0, 0.0, cf2]           # 零節點 → 後半段
                new_lead.append(z)
            else:
                new_lead.append(list(tup))
        new_final = final_leg
    else:
        # 切收尾弧：在 Lambert 前多一顆零 leading 燒（前半），final_leg 收後半
        z = list(zero_tuple)                       # 零節點 → 前半段（cf1）
        new_lead = [list(t) for t in lead] + [z]
        new_final = cf2

    out = [t0]
    for t in new_lead:
        out.extend(t)
    out.append(new_final)
    out.extend(offsets)
    return np.array(out, dtype=float)
