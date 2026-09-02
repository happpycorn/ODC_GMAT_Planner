"""旋轉不變性：把整個問題（A/B 的位置速度 + 決策向量裡的燃燒方向）剛體旋轉，
分數必須完全一樣——但只在旋轉真的是該物理模型的對稱操作時才該一樣。

為什麼這是個「會抓 frame bug」的測試
────────────────────────────────────
fitness 的每一步都在同一個慣性座標系裡：狀態是慣性的、燃燒方向
`dv_vec = [r·sinθcosφ, r·sinθsinφ, r·cosθ]` 直接加到慣性速度上（沒有引用 r_curr/
v_curr，不是 RTN/LVLH 局部系）、傳播跟 Lambert 也都在慣性系。既然整條管線自洽地
待在一個座標系，把整個宇宙一起轉一個角度就**不該**改變任何物理量。如果轉了會變，
代表某處偷偷依賴了絕對方向（寫死的參考軸、element→Cartesian 的慣例對不上傳播器、
J 項套錯軸……）——那就是 frame bug，會直接扭曲真實測資的分數。

★ 一定要小心的物理陷阱（否則會誤報 bug）★
────────────────────────────────────────
重力模型不是球對稱的。J2/J3/J4 是繞**慣性 Z 軸**的軸對稱擾動（赤道隆起），所以：

  • 點質量（GRAVITY_DEGREE=0）：RHS f(r,v)=[v, -μr/|r|³] 對**任意** SO(3) 旋轉
    equivariant，任意旋轉都是對稱 → 分數必須不變。用這個掃「離開赤道面」的 frame bug。

  • 開了 J（GRAVITY_DEGREE≥2）：只有**繞 Z 軸**的旋轉保住赤道隆起的指向，才是對稱
    → 只有 Rz 分數該不變。任意 3D 旋轉會把軌道傾出赤道面，J 擾動本來就該讓分數改變，
    那**不是** bug。把這個誤當成 frame bug 去「修」核心物理才是災難。

所以本測試分兩組：點質量測任意旋轉、開 J 測 Rz。並且額外驗一件事——開 J 時任意旋轉
**確實會**改變分數，以此證明「重力模型真的是軸對稱、不是被我們不小心寫成球對稱」，
也證明這個測試不是恆真地空跑。

評估器用 opt._fitness_wrapper（暫時替換 opt 的狀態向量），這樣 baseline 跟旋轉後
共用同一套 scalar_params 組法，兩者只差在旋轉本身。決策向量在 fitness 層直接餵，
完全避開搜尋的多執行緒不確定性。

跑法：uv run python tests/test_rotation_invariance.py
"""

import math
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import warnings
warnings.filterwarnings("ignore")

from src.optimizer import MissionOptimizer, decision_variable_dims
from src.propagator import get_r0_v0

FAILS = []


def check(name, cond):
    print(("  ✅ " if cond else "  ❌ ") + name)
    if not cond:
        FAILS.append(name)


# ── 旋轉矩陣工具 ──────────────────────────────────────────────────────────
def rot_z(angle):
    c, s = math.cos(angle), math.sin(angle)
    return np.array([[c, -s, 0.0], [s, c, 0.0], [0.0, 0.0, 1.0]])


def rand_rotation(rng):
    """隨機 SO(3)：對隨機矩陣做 QR，固定號誌讓行列式 = +1（真旋轉、非鏡射）。"""
    A = rng.standard_normal((3, 3))
    Q, R = np.linalg.qr(A)
    Q = Q @ np.diag(np.sign(np.diag(R)))     # 讓 QR 唯一、可重現
    if np.linalg.det(Q) < 0:                 # 排除鏡射
        Q[:, 0] = -Q[:, 0]
    return Q


def spherical_to_vec(r, theta, phi):
    """跟 fast_fitness_evaluator 裡的球座標→Cartesian 慣例逐字一致。"""
    st = math.sin(theta)
    return np.array([r * st * math.cos(phi),
                     r * st * math.sin(phi),
                     r * math.cos(theta)])


def rotate_dir(r, theta, phi, R):
    """把 (r,θ,φ) 代表的向量旋轉 R，回傳新的 (θ',φ')；r 不變（R 是正交的）。"""
    if r < 1e-12:                    # 零向量方向無意義，原樣退回
        return theta, phi
    w = R @ spherical_to_vec(r, theta, phi)
    new_theta = math.acos(max(-1.0, min(1.0, w[2] / r)))
    new_phi = math.atan2(w[1], w[0])
    return new_theta, new_phi


def rotate_solution(x, num_burns, R):
    """把決策向量裡所有慣性方向（中間棒 Δv、最後瞄準偏移）旋轉 R。

    幅度（dv_r / offset_r）、時間（t_wait / coast_frac / final_leg_frac）全部不動，
    只有方向的 (θ,φ) 跟著狀態一起轉——這正是「整個宇宙剛體旋轉」的意思。
    """
    x = np.asarray(x, dtype=np.float64).copy()
    idx = 1
    for _ in range(1, num_burns):                 # 中間棒：dv_r, dv_theta, dv_phi, coast
        x[idx + 1], x[idx + 2] = rotate_dir(x[idx], x[idx + 1], x[idx + 2], R)
        idx += 4
    x[-2], x[-1] = rotate_dir(x[-3], x[-2], x[-1], R)   # 最後瞄準偏移 offset_(r,θ,φ)
    return x


# ── 用 opt 當評估器，但餵指定的狀態向量 ──────────────────────────────────
def eval_with(opt, vectors4, x, num_burns):
    """暫時把 opt 的 A/B 狀態換成 vectors4，用 _fitness_wrapper 算 fitness（= -分數）。

    刻意重用 _fitness_wrapper 而不是自己組 scalar_params——scalar 陣列的索引佈局
    很脆（LAMBERT_MAX_REVS 就是後來補在 index 13 的），baseline 跟旋轉後共用同一份
    組法才能保證兩者只差在旋轉。"""
    old = (opt.A_r0, opt.A_v0, opt.B_r0, opt.B_v0)
    opt.A_r0, opt.A_v0, opt.B_r0, opt.B_v0 = vectors4
    try:
        return float(opt._fitness_wrapper(num_burns)(x))
    finally:
        opt.A_r0, opt.A_v0, opt.B_r0, opt.B_v0 = old


def make_opt(orbit_A, orbit_B, gravity_degree):
    """同一組軌道、指定重力階數，建一個 optimizer。optimization 區塊隨便填，
    本測試只用它的 fitness 評估，不跑搜尋。"""
    config = {
        "orbit_A": orbit_A, "orbit_B": orbit_B,
        "rules": {"MAX_DV_MPS": 1500.0, "MIN_MANEUVER_INTERVAL_SEC": 100.0,
                  "T_MAX_PERIOD_MULTIPLE": 4.0,
                  "k_t": 0.0001, "C_t": 11000.0, "k_v": 0.005, "C_v": 1200.0},
        "strategy": {"GRAVITY_DEGREE": gravity_degree, "MISS_TOLERANCE_KM": 5.0},
        "optimization": {"MAX_BURNS": [1, 2, 3], "MAXITER": 1, "POPSIZE": 5,
                         "NUM_THREADS": 1, "MAX_EARLY_STOP": 1, "TOL": 0.01, "SEED": 0},
    }
    return MissionOptimizer(config)


def sample_feasible(opt, num_burns, rng, want, max_tries=4000, min_score=1.0):
    """在 bounds 內隨機取樣，留下 fitness < -min_score（分數 > min_score）的可行解。

    分數為 0 的解（撞地球 / Lambert 不收斂）拿來測旋轉不變性是空的（0==0 恆真），
    一定要拿有實際分數的解才有鑑別力。中間棒的 Δv 上界壓到 0.3 km/s 提高可行率
    （大 Δv 容易把中間軌道近地點打到地表以下 → 0 分），角度/時間/偏移仍取滿範圍。"""
    lb, ub = opt._generate_bounds(num_burns)
    lb, ub = np.array(lb), np.array(ub)
    dims = decision_variable_dims(num_burns)
    base = (opt.A_r0, opt.A_v0, opt.B_r0, opt.B_v0)
    out = []
    for _ in range(max_tries):
        x = lb + rng.random(dims) * (ub - lb)
        # 中間棒 Δv（每 4 格的第 1 格，從 index 1 起）壓小，提高可行率
        idx = 1
        for _b in range(1, num_burns):
            x[idx] = rng.random() * 0.3
            idx += 4
        f = eval_with(opt, base, x, num_burns)
        if f < -min_score:
            out.append(x)
            if len(out) >= want:
                break
    return out


# ── 一組情境跑一遍 ────────────────────────────────────────────────────────
POINT_MASS_TOL = 1e-6      # 純二體對任意旋轉 equivariant，只剩浮點/積分器捨入
RZ_TOL = 1e-6             # J 對繞 Z 旋轉 equivariant，同上


def run_scenario(name, orbit_A, orbit_B, burns_list=(1, 2, 3)):
    print(f"\n══ 情境：{name} ══")
    rng = np.random.default_rng(12345)
    opt_pm = make_opt(orbit_A, orbit_B, gravity_degree=0)   # 點質量
    opt_j = make_opt(orbit_A, orbit_B, gravity_degree=4)    # J2+J3+J4

    rotations_arbitrary = [rand_rotation(rng) for _ in range(4)]
    rotations_z = [rot_z(a) for a in (0.3, 1.7, -2.4, math.pi)]

    max_diff_pm = 0.0
    max_diff_rz = 0.0
    arbitrary_j_changes = []      # 開 J 時任意旋轉造成的分數變化（該 > 0）
    n_solutions = 0

    for nb in burns_list:
        sols_pm = sample_feasible(opt_pm, nb, np.random.default_rng(100 + nb), want=4)
        sols_j = sample_feasible(opt_j, nb, np.random.default_rng(200 + nb), want=4)
        n_solutions += len(sols_pm) + len(sols_j)

        # (1) 點質量 + 任意旋轉 → 分數必須不變
        for x in sols_pm:
            base_f = eval_with(opt_pm, (opt_pm.A_r0, opt_pm.A_v0, opt_pm.B_r0, opt_pm.B_v0), x, nb)
            for R in rotations_arbitrary:
                vecs = (R @ opt_pm.A_r0, R @ opt_pm.A_v0, R @ opt_pm.B_r0, R @ opt_pm.B_v0)
                rot_f = eval_with(opt_pm, vecs, rotate_solution(x, nb, R), nb)
                max_diff_pm = max(max_diff_pm, abs(rot_f - base_f))

        # (2) 開 J + 繞 Z 旋轉 → 分數必須不變
        # (3) 開 J + 任意旋轉 → 分數本來就該變（赤道隆起），收集起來當「測試非空跑」佐證
        for x in sols_j:
            base_f = eval_with(opt_j, (opt_j.A_r0, opt_j.A_v0, opt_j.B_r0, opt_j.B_v0), x, nb)
            for R in rotations_z:
                vecs = (R @ opt_j.A_r0, R @ opt_j.A_v0, R @ opt_j.B_r0, R @ opt_j.B_v0)
                rot_f = eval_with(opt_j, vecs, rotate_solution(x, nb, R), nb)
                max_diff_rz = max(max_diff_rz, abs(rot_f - base_f))
            for R in rotations_arbitrary:
                vecs = (R @ opt_j.A_r0, R @ opt_j.A_v0, R @ opt_j.B_r0, R @ opt_j.B_v0)
                rot_f = eval_with(opt_j, vecs, rotate_solution(x, nb, R), nb)
                arbitrary_j_changes.append(abs(rot_f - base_f))

    check(f"[{name}] 取到有分數的可行解可測（{n_solutions} 個）", n_solutions >= 6)
    check(f"[{name}] 點質量：任意旋轉分數不變（max Δ={max_diff_pm:.2e} ≤ {POINT_MASS_TOL:g}）",
          max_diff_pm <= POINT_MASS_TOL)
    check(f"[{name}] 開 J：繞 Z 旋轉分數不變（max Δ={max_diff_rz:.2e} ≤ {RZ_TOL:g}）",
          max_diff_rz <= RZ_TOL)
    # 反向佐證：開 J 時任意旋轉「確實會」改變分數，證明 J 模型真的軸對稱、測試非空跑
    biggest = max(arbitrary_j_changes) if arbitrary_j_changes else 0.0
    check(f"[{name}] 佐證：開 J 時任意旋轉確實改變分數（max Δ={biggest:.2e} > 1e-3，"
          f"證明赤道隆起破壞了任意旋轉對稱、本測試非恆真）",
          biggest > 1e-3)


# ── RAAN 平移 ≡ Rz：把 get_r0_v0（六根數→Cartesian）也綁進旋轉不變性（HAP-41）──
#
# 上面的測試在 fitness 層直接餵旋轉後的「狀態向量」，繞過了六根數→Cartesian 這一段。
# 這裡補上：升交點赤經 RAAN 本來就是「繞慣性 Z 軸把整個軌道轉一個角度」，數學上
# 透視→ECI 是 Rz(RAAN)·Rx(inc)·Rz(argp)，所以 RAAN+Δ 等於在最左邊多乘一個 Rz(Δ)
# ——整個狀態（r 跟 v）都會是 Rz(Δ)·原狀態，對任何 inc/argp/ta 都成立。
# 若 get_r0_v0 的 frame 慣例錯了（角度單位、旋轉順序、某個符號），這個等式就會破。
def _elements_tuple(orb):
    return (orb["SMA"], orb["ECC"], orb["INC"], orb["RAAN"], orb["AOP"], orb["TA"])


def _shift_raan(orb, ddeg):
    o = dict(orb)
    o["RAAN"] = orb["RAAN"] + ddeg
    return o


def run_raan_shift_scenario(name, orbit_A, orbit_B):
    print(f"\n══ RAAN 平移 ≡ Rz（涵蓋 get_r0_v0）：{name} ══")
    shifts = (17.0, 90.0, -123.0, 180.0)

    # (1) 直接檢查 get_r0_v0 的 frame：RAAN+Δ 必須等於對狀態做 Rz(Δ)（相對誤差）
    max_direct = 0.0
    for orb in (orbit_A, orbit_B):
        r0, v0 = get_r0_v0(*_elements_tuple(orb))
        n_r, n_v = max(np.linalg.norm(r0), 1e-12), max(np.linalg.norm(v0), 1e-12)
        for ddeg in shifts:
            R = rot_z(math.radians(ddeg))
            r1, v1 = get_r0_v0(*_elements_tuple(_shift_raan(orb, ddeg)))
            max_direct = max(max_direct,
                             np.linalg.norm(r1 - R @ r0) / n_r,
                             np.linalg.norm(v1 - R @ v0) / n_v)
    check(f"[{name}] get_r0_v0：RAAN+Δ 等於 Rz(Δ)@狀態（max 相對誤差={max_direct:.2e} ≤ 1e-9）",
          max_direct <= 1e-9)

    # (2) 端到端：RAAN 平移 Δ、解跟著 Rz 轉，開 J 分數不變。
    # opt 用原始六根數建（T_max 只跟 SMA 有關、不受 RAAN 影響，所以拿同一個 opt 的
    # scalar_params 去評估平移後的狀態是對的），只把狀態向量換成平移後 get_r0_v0 的輸出。
    opt = make_opt(orbit_A, orbit_B, gravity_degree=4)
    max_e2e = 0.0
    n_solutions = 0
    for nb in (1, 2, 3):
        sols = sample_feasible(opt, nb, np.random.default_rng(300 + nb), want=3)
        n_solutions += len(sols)
        for x in sols:
            base_f = eval_with(opt, (opt.A_r0, opt.A_v0, opt.B_r0, opt.B_v0), x, nb)
            for ddeg in (17.0, 90.0, -123.0):
                R = rot_z(math.radians(ddeg))
                a_r, a_v = get_r0_v0(*_elements_tuple(_shift_raan(orbit_A, ddeg)))
                b_r, b_v = get_r0_v0(*_elements_tuple(_shift_raan(orbit_B, ddeg)))
                rot_f = eval_with(opt, (a_r, a_v, b_r, b_v), rotate_solution(x, nb, R), nb)
                max_e2e = max(max_e2e, abs(rot_f - base_f))
    check(f"[{name}] 端到端：RAAN 平移 Δ 後分數不變（{n_solutions} 解，max Δ={max_e2e:.2e} ≤ {RZ_TOL:g}）",
          max_e2e <= RZ_TOL)


def main():
    # 用非退化幾何（有傾角/離心率/RAAN/AOP），旋轉才動得到東西；赤道圓軌道測不出來。
    print("=== 旋轉不變性測試（HAP-30）===")
    print("點質量 → 任意旋轉不變；開 J → 只有繞 Z 不變（見檔頭物理說明）")

    # official_sample：唯一一組官方題目（六根數官方原文）
    run_scenario(
        "official_sample",
        {"SMA": 6978.0, "ECC": 0.0, "INC": 45.0, "RAAN": 0.0, "AOP": 0.0, "TA": 0.0},
        {"SMA": 6878.0, "ECC": 0.0, "INC": 135.0, "RAAN": 30.0, "AOP": 0.0, "TA": 60.0},
    )
    # playground：中等難度、有離心率跟一般化的 RAAN/AOP/TA
    run_scenario(
        "playground",
        {"SMA": 13000.0, "ECC": 0.3, "INC": 28.0, "RAAN": 60.0, "AOP": 40.0, "TA": 150.0},
        {"SMA": 7200.0, "ECC": 0.02, "INC": 0.0, "RAAN": 0.0, "AOP": 0.0, "TA": 0.0},
    )
    # 極端傾角差（A 極軌 90°、B 赤道），逼出跨平面的方向處理
    run_scenario(
        "polar_vs_equatorial",
        {"SMA": 9375.0, "ECC": 0.2, "INC": 90.0, "RAAN": 0.0, "AOP": 0.0, "TA": 0.0},
        {"SMA": 6800.0, "ECC": 0.001, "INC": 0.0, "RAAN": 0.0, "AOP": 0.0, "TA": 200.0},
    )

    # HAP-41：把 get_r0_v0（六根數→Cartesian）也綁進來——RAAN 平移 ≡ 繞 Z 旋轉。
    print("\n" + "─" * 60)
    print("RAAN 平移 ≡ Rz：涵蓋 get_r0_v0，補上 fitness 層測不到的那一段")
    run_raan_shift_scenario(
        "official_sample",
        {"SMA": 6978.0, "ECC": 0.0, "INC": 45.0, "RAAN": 0.0, "AOP": 0.0, "TA": 0.0},
        {"SMA": 6878.0, "ECC": 0.0, "INC": 135.0, "RAAN": 30.0, "AOP": 0.0, "TA": 60.0},
    )
    run_raan_shift_scenario(
        "playground",
        {"SMA": 13000.0, "ECC": 0.3, "INC": 28.0, "RAAN": 60.0, "AOP": 40.0, "TA": 150.0},
        {"SMA": 7200.0, "ECC": 0.02, "INC": 0.0, "RAAN": 0.0, "AOP": 0.0, "TA": 0.0},
    )
    run_raan_shift_scenario(
        "polar_vs_equatorial",
        {"SMA": 9375.0, "ECC": 0.2, "INC": 90.0, "RAAN": 0.0, "AOP": 0.0, "TA": 0.0},
        {"SMA": 6800.0, "ECC": 0.001, "INC": 0.0, "RAAN": 0.0, "AOP": 0.0, "TA": 200.0},
    )

    print()
    if FAILS:
        print(f"❌ {len(FAILS)} 項失敗：" + "、".join(FAILS))
        sys.exit(1)
    print("✅ 全部通過")


if __name__ == "__main__":
    main()
