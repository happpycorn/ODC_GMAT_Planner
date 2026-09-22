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
