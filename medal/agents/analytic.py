"""解析 / 啟發式 agent：不用訓練、規則一公布就能用的保底大腦，也是 RL 的對手與基準。

* LambertPursuer —— 每回合對「躲者從現在起純滑行」的預測星曆解最省 Δv 的攔截
  （TOF × 圈數 × 分支掃描 + J2 打靶），超過這一發的上限就先推一部分、下回合重規劃
  （receding horizon）。`time_weight_mps` 決定「早點抓到」值多少 Δv。
* DvEvader —— 候選脈衝（RSW 方向 × 大小）逐一模擬自己這個窗口，挑讓
  「追者攔截所需 Δv − 追者剩餘燃料」最大者（燃料消耗戰，見 METHODOLOGY §5）。

多發規則（burns_per_turn > 1）的「間隔存活」放寬（`gap_survival`，環境變數 ODC_GAP_SURVIVAL）：
窗口內這一發之後還會再被問一發時，這一發推完的中間軌道不必撐到比賽結束，只要撐過間隔、
而且間隔後還救得回來（見 next_burn_gap / gap_burn_survives；docs/notes/multi_burn_survival.md）。
"""
import math
import os
from itertools import product

import numpy as np

from agents.base import Agent, rsw_to_eci_dv
from agents.scan_reuse import reuse_call, scoped_decision
from physics.coast import closest_approach
from physics.core_math import check_constraints, reaches_perigee
from physics.intercept import _refine_tof, best_lambert, intercept_scan, min_intercept, shoot_j2
from physics.propagator import propagate


SAFETY_MARGIN_KM = 50.0


def safe_radius(game, margin_km=SAFETY_MARGIN_KM):
    return game.crash_radius + margin_km


STRICT_SURVIVAL_ENV = "ODC_STRICT_SURVIVAL"
# 預設開（2026-10-22 使用者決定，E25）：orbit_survives 在「近地點低於門檻、但剩餘時間內不經過近地點」時
# 再檢查 horizon 結束時的二體半徑（docs/notes/orbit_survives_fix.md）。ODC_STRICT_SURVIVAL=0 回到舊行為
# （舊行為與 2026-10-21 以前的結果逐位元相同）。
STRICT_SURVIVAL_DEFAULT = 1


def strict_survival_enabled():
    """ODC_STRICT_SURVIVAL 開關（evaluate.py 的子行程會繼承）：1 = orbit_survives 也檢查弧終點、0 = 舊行為；
    未設定（或看不懂的值）時用 STRICT_SURVIVAL_DEFAULT。每次呼叫都重讀，只有漏判那一支會呼叫。"""
    v = os.environ.get(STRICT_SURVIVAL_ENV, "").strip().lower()
    if v in ("1", "true", "on", "yes"):
        return True
    if v in ("0", "false", "off", "no"):
        return False
    return bool(STRICT_SURVIVAL_DEFAULT)


def _radius_after_coast(r, v, mu, dt):
    """二體：從 (r, v) 純滑行 dt 秒後的地心距離（km）。給 orbit_survives「dt 內不經過近地點」那一支用；
    比能量 >= 0 時（那一支代表正在往外飛，半徑單調增加）回傳 inf。純 float 運算（~10 µs）。"""
    x, y, z = float(r[0]), float(r[1]), float(r[2])
    vx, vy, vz = float(v[0]), float(v[1]), float(v[2])
    r_mag = math.sqrt(x * x + y * y + z * z)
    energy = (vx * vx + vy * vy + vz * vz) / 2.0 - mu / r_mag
    if energy >= 0.0:
        return math.inf
    a = -mu / (2.0 * energy)
    hx, hy, hz = y * vz - z * vy, z * vx - x * vz, x * vy - y * vx
    e = math.sqrt(max(0.0, 1.0 + 2.0 * energy * (hx * hx + hy * hy + hz * hz) / (mu * mu)))
    if e < 1e-12:
        return r_mag                                  # 正圓：半徑不變
    E0 = math.acos(min(1.0, max(-1.0, (1.0 - r_mag / a) / e)))
    if x * vx + y * vy + z * vz < 0.0:
        E0 = 2.0 * math.pi - E0                       # 正在往近地點掉（同 reaches_perigee）
    M = (E0 - e * math.sin(E0) + math.sqrt(mu / (a * a * a)) * dt) % (2.0 * math.pi)
    # Kepler 方程 E − e·sinE = M：f 單調遞增（f' = 1 − e·cosE > 0），Newton + [0, 2π] 夾擠，跳出區間就二分
    lo, hi = 0.0, 2.0 * math.pi
    E = min(hi, max(lo, M + 0.85 * e if math.sin(M) >= 0.0 else M - 0.85 * e))
    for _ in range(64):
        f = E - e * math.sin(E) - M
        if f > 0.0:
            hi = E
        else:
            lo = E
        E_new = E - f / (1.0 - e * math.cos(E))
        if not lo < E_new < hi:
            E_new = 0.5 * (lo + hi)
        if abs(E_new - E) < 1e-13:
            E = E_new
            break
        E = E_new
    return a * (1.0 - e * math.cos(E))


def orbit_survives(game, side, dv_eci_mps, horizon=None, margin_km=SAFETY_MARGIN_KM, strict=None):
    """施加 dv 之後純滑行 horizon 秒（預設到 T_max）會不會掉到「撞地高度 + 安全裕度」以下。

    密切軌道近地點在門檻之上 → 安全；否則看剩餘時間內會不會真的飛過近地點
    （同 Planner 的 reaches_perigee 分拆法，二體近似）：會 → 不安全；不會 → 舊行為直接判安全。

    strict（None = 跟 ODC_STRICT_SURVIVAL 開關，預設開）：不會飛過近地點時，這段弧的最低點是兩端取小
    （reaches_perigee 說明裡的另一半），所以再要求 horizon 結束時的二體半徑也 ≥ 門檻。舊行為漏掉
    「近地點在地底下、還沒到近地點就先穿過撞地高度」（E22 對稱規則 seed 1 第 3 局；E23 飛掠局的撞地）。
    起點不檢查：推力改不了它，而且此刻還沒撞地。

    ⚠️ 安全裕度是 2026-09-15 對打評測抓到的：零裕度時追者把近地點壓在 101–110 km 高度
    （撞地線 100 km），二體判斷說安全，但 J2 讓近地點在幾圈內緩慢下沉，最後真的再入。
    """
    r = game.r(side)
    v = game.v(side) + np.asarray(dv_eci_mps, dtype=np.float64) / 1000.0
    h = game.time_left if horizon is None else horizon
    if check_constraints(r, v, game.mu, game.crash_radius + margin_km):
        return True
    if reaches_perigee(r, v, game.mu, h):
        return False
    if not (strict_survival_enabled() if strict is None else strict):
        return True                                   # 舊行為（ODC_STRICT_SURVIVAL=0）
    return _radius_after_coast(r, v, game.mu, h) >= game.crash_radius + margin_km


def rescue_burn(game, side):
    """目前軌道撐不到比賽結束時，找最小的一發讓它恢復安全（沒有就回傳 None）。"""
    cap = game.burn_cap(side)
    if cap <= 0.0:
        return None
    for frac in (0.02, 0.05, 0.1, 0.2, 0.35, 0.5, 0.75, 1.0):
        for d in _direction_set("full"):
            dv = rsw_to_eci_dv(game, side, d * frac * cap)
            if orbit_survives(game, side, dv):
                return dv
    return None


GAP_SURVIVAL_ENV = "ODC_GAP_SURVIVAL"
# 預設關（docs/notes/multi_burn_survival.md）：250 m/s 多發幾乎不觸發；1500 m/s 多發常觸發但追者沒變強
# （放寬的一發之後多半只能救命），level 1 還會在 rollout 規劃器全輸、選零候選時讓追者停在撞地軌道上。
GAP_SURVIVAL_DEFAULT = 0


def gap_survival_level():
    """ODC_GAP_SURVIVAL 開關（evaluate.py 的子行程會繼承）：0 = 嚴格（舊行為）、1 = 撐過間隔且救得回來、
    2 = 再加上「間隔後一發補得完同一個攔截」；未設定時用 GAP_SURVIVAL_DEFAULT。"""
    v = os.environ.get(GAP_SURVIVAL_ENV, "").strip().lower()
    if v in ("1", "true", "on", "yes"):
        return 1
    if v == "2":
        return 2
    if v in ("0", "false", "off", "no"):
        return 0
    return GAP_SURVIVAL_DEFAULT


def next_burn_gap(game, side):
    """多發規則下，`side` 推完這一發後本窗口還會不會再被問一發：會 → 回傳間隔秒數，不會 → None。

    跟 game.core.plan_turn 的問法一致：從窗口開頭每隔 min_burn_gap_sec 問一次、一個窗口最多問
    burns_per_turn 次（推零也用掉一次），下一問的時刻要在窗口內。agent 看不到這是第幾問，所以取
    「窗口內已過秒數 / 間隔」與「已下的非零發數」的大者保守估計（rollout 從窗口中途接手也不會高估）。"""
    R = game.rules
    gap = float(R.min_burn_gap_sec)
    if R.burns_per_turn <= 1 or gap <= 0.0 or game.done or game.mover != side:
        return None
    off, n_used, _ = game._window_used()
    asked = max(n_used, int(math.floor(off / gap + 1e-6)))
    if asked + 1 >= R.burns_per_turn:
        return None
    win = game._win_len if game.mid_window else game.next_window()
    if off + gap >= win - 1e-9 or gap >= game.time_left:
        return None
    return gap


def gap_burn_survives(game, side, dv_eci_mps, gap, margin_km=SAFETY_MARGIN_KM, target=None, max_revs=1):
    """窗口內 gap 秒後還能再推一發時的放寬存活條件（初賽官方範例解那招：中間軌道近地點在地表下）：

    (a) 推完這發滑行 gap 秒：這段弧的最低點不低於撞地高度 + 裕度（二體精確：弧內經過近地點看
        近地點，否則看兩端），引擎實際滑行也沒撞地；
    (b) gap 秒後用剩下的單發上限／燃料救得回來：不推就撐到比賽結束，或 rescue_burn 找得到一發。
    每一發都要確認 (b)，所以窗口最後一發一定有嚴格安全的退路。
    (c) target=(目標位置, 從現在起的 TOF) 時（level 2）：gap 秒後一發（≤ 單發上限）就能補完到同一個目標、
        而且補完的軌道過得了嚴格檢查（或就在這個窗口內抓到）——避免「推一大發、下一發只能救命」。"""
    dv = np.array(dv_eci_mps, dtype=np.float64).reshape(3)
    r = game.r(side)
    v = game.v(side) + dv / 1000.0
    r_min = game.crash_radius + margin_km
    sim = game.clone()
    sim.history = []
    sim.sub_burn(dv, gap)
    if sim.done:                                  # 間隔內捕獲 / 對手撞地 / 時間到：沒有自己撞地就行
        return sim.outcome != f"crash_{side}"
    if not check_constraints(r, v, game.mu, r_min):
        if reaches_perigee(r, v, game.mu, gap):
            return False
        if min(float(np.linalg.norm(r)), float(np.linalg.norm(sim.r(side)))) < r_min:
            return False
    if target is not None and not _completable(sim, side, target[0], target[1] - gap, max_revs):
        return False
    if orbit_survives(sim, side, np.zeros(3)):
        return True
    return rescue_burn(sim, side) is not None


def _completable(sim, side, r_target, tof_left, max_revs):
    """sim 此刻一發（≤ 單發上限）就能在 tof_left 秒後到 r_target，且補完的軌道過得了嚴格檢查或就在窗口內抓到。"""
    if tof_left <= 60.0:
        return False
    d, v1 = best_lambert(sim.mu, sim.r(side), sim.v(side), np.asarray(r_target, dtype=np.float64),
                         float(tof_left), int(max_revs), safe_radius(sim))
    if not math.isfinite(d) or d * 1000.0 > sim.burn_cap(side):
        return False
    return tof_left <= sim.next_window() or orbit_survives(sim, side, (v1 - sim.v(side)) * 1000.0)


def _coast_wins_window(game, side):
    """不推、滑完這個窗口剩下的部分，比賽會不會以我方勝結束（間隔放寬後的中間軌道上用）。"""
    sim = game.clone()
    sim.history = []
    sim.sub_burn(np.zeros(3), math.inf)
    return sim.winner == side


def pursuer_need(game, horizon=None, max_revs=2, pts_per_period=24, n_refine=2, refine_iters=10,
                 max_pts=160):
    """追者此刻一發攔截（假設躲者之後純滑行）、在 horizon 秒內抓到所需的最小 Δv（m/s）與 TOF。

    ⚠️ 2026-09-15 實測教訓：TOF 網格要跟軌道週期走（每週期 pts_per_period 點），固定點數在
    長 horizon 下會漏掉尖銳的極小值（24 點掃 26,000 s 回報 96 m/s，高解析是 5 m/s）。
    另外 horizon 拉到整個 T_max 時，多圈調相幾乎免費，這個量會飽和到個位數 m/s 失去
    鑑別力——所以局勢評估 / 塑形 / 躲者啟發式用「接下來幾個窗口內」的短 horizon 版本。
    """
    R = game.rules
    H = game.time_left if horizon is None else min(horizon, game.time_left)
    if H <= 60.0:
        return math.inf, 0.0
    T = game.period("pursuer")
    n = int(np.clip(math.ceil(H / T * pts_per_period), 8, max_pts))
    dv, tof, _ = min_intercept(game.mu, R.gravity_degree, game.r("pursuer"), game.v("pursuer"),
                               game.r("evader"), game.v("evader"), 60.0, H, n, max_revs,
                               game.crash_radius, n_refine, refine_iters)
    return float(dv) * 1000.0, float(tof)


def need_horizon(game, windows=4.0):
    """短 horizon：接下來 `windows` 個窗口，至少半個週期（太短會找不到任何可行轉移）。"""
    return max(windows * game.rules.window_sec, 0.5 * game.period("pursuer"))


class LambertPursuer(Agent):
    name = "lambert_pursuer"

    def __init__(self, time_weight_mps=10.0, pts_per_period=24, max_revs=2, j2_shoot=True,
                 coast_if_captures=True, max_pts=240, horizon_frac=1.0, gap_survival=None):
        self.time_weight_mps = time_weight_mps   # 每晚一個窗口抓到，願意多付多少 m/s
        self.horizon_frac = horizon_frac         # 只考慮 TOF <= 剩餘時間 × frac 的攔截（至少一個窗口）
        self.pts_per_period = pts_per_period     # TOF 網格密度跟軌道週期走（固定點數會漏極小值）
        self.max_pts = max_pts
        self.max_revs = max_revs
        self.j2_shoot = j2_shoot
        self.coast_if_captures = coast_if_captures
        # 多發規則：窗口內還會再推時，中間軌道只需撐過間隔且救得回來（0/1/2，見 gap_survival_level；
        # None = 跟環境變數 ODC_GAP_SURVIVAL）
        self.gap_survival = gap_survival_level() if gap_survival is None else int(gap_survival)
        if time_weight_mps != 10.0:
            self.name = f"lambert_pursuer(w={time_weight_mps:g})"

    @scoped_decision
    def act(self, game, side):
        assert side == "pursuer"
        R = game.rules
        cap = game.burn_cap(side)
        if cap <= 0.0:
            return np.zeros(3)
        rp, vp, re, ve = game.r("pursuer"), game.v("pursuer"), game.r("evader"), game.v("evader")
        mu, gd = game.mu, R.gravity_degree
        relax = self.gap_survival > 0 and R.burns_per_turn > 1

        # 已經在滑行中會進捕獲球（這個窗口內）→ 不動，省油
        if self.coast_if_captures:
            if R.capture_mode == "endpoint":
                rp_w, _ = reuse_call(propagate, mu, rp, vp, game.next_window(), gd)
                re_w, _ = reuse_call(propagate, mu, re, ve, game.next_window(), gd)
                d_ca = float(np.linalg.norm(rp_w - re_w))
            else:
                d_ca, _, _ = reuse_call(closest_approach, rp, vp, re, ve, game.next_window(), 60.0, mu, gd)
            # 放寬時可能正在一條撐不久的中間軌道上：要確定滑完窗口真的先抓到、不是先撞地
            if d_ca <= 0.8 * R.capture_radius_km and \
                    (not relax or orbit_survives(game, side, np.zeros(3)) or _coast_wins_window(game, side)):
                return np.zeros(3)

        horizon = game.time_left
        if self.horizon_frac < 1.0:
            horizon = min(horizon, max(self.horizon_frac * horizon, game.next_window() + 120.0))
        if horizon <= 60.0:
            return np.zeros(3)
        endpoint = R.capture_mode == "endpoint"
        if endpoint:
            # 只在回合結束瞬間判定捕獲 → 攔截時刻必須落在回合邊界（本窗口末、之後每個窗口末）
            w = R.window_sec
            first = game.next_window()
            k_max = int((horizon - first) // w)
            if k_max < 0:
                return np.zeros(3)
            tof_lo, tof_hi, n_tof = first, first + k_max * w, k_max + 1
        else:
            n_tof = int(np.clip(math.ceil(horizon / game.period("pursuer") * self.pts_per_period), 8, self.max_pts))
            tof_lo, tof_hi = 60.0, horizon
        tofs, dvs, v1s, re_at, ve_at = reuse_call(intercept_scan, mu, gd, rp, vp, re, ve, tof_lo, tof_hi, n_tof,
                                                self.max_revs, safe_radius(game))
        dvs_mps = dvs * 1000.0
        if not np.any(np.isfinite(dvs_mps)):
            return np.zeros(3)
        score = dvs_mps + self.time_weight_mps * tofs / R.window_sec
        # 轉移弧本身已保證不撞地；但若 TOF 超過這個窗口，躲者有機會閃開，追者就會留在轉移
        # 軌道上——那條軌道得撐到比賽結束，否則是在賭命（實測過一局追者因此撞地）
        window = game.next_window()
        for j in range(len(tofs)):
            if np.isfinite(dvs_mps[j]) and tofs[j] > window and \
                    not orbit_survives(game, side, (v1s[j] - vp) * 1000.0):
                score[j] = np.inf
                dvs_mps[j] = np.inf
        if not np.any(np.isfinite(dvs_mps)):
            return np.zeros(3)
        feasible = dvs_mps <= cap
        if np.any(feasible):
            i = int(np.argmin(np.where(feasible, score, np.inf)))
        else:
            i = int(np.argmin(dvs_mps))

        # 在選中的 TOF 鄰域精修最小 Δv（endpoint 模式 TOF 被綁在回合邊界，不能精修）
        tof, v1 = tofs[i], v1s[i]
        if not endpoint:
            lo, hi = max(i - 1, 0), min(i + 1, len(tofs) - 1)
            d, tof_r, v1_r = _refine_tof(mu, gd, rp, vp, re_at[lo], ve_at[lo], tofs[lo], tofs[hi],
                                         self.max_revs, safe_radius(game), 12)
            if math.isfinite(d) and d * 1000.0 <= dvs_mps[i]:
                tof, v1 = tof_r, v1_r
        if self.j2_shoot and gd > 0:
            r_t, _ = reuse_call(propagate, mu, re, ve, tof, gd)
            v1_s, miss = shoot_j2(mu, gd, rp, v1, r_t, tof, 6, 1e-3)
            if math.isfinite(miss) and miss < 1.0:
                v1 = v1_s
        dv = (v1 - vp) * 1000.0
        mag = float(np.linalg.norm(dv))
        full = mag <= cap
        if not full:
            dv *= cap / mag
        # 完整解且在這個窗口內抓到 → 躲者來不及反應，弧已檢查過安全，直接推。
        # 其他情況（部分推力、或躲者還有機會閃開）推完的軌道必須撐到比賽結束：
        # 不行就減半重試；連不推都會再入的話改做救命推力。
        # 間隔放寬（多發、窗口內還會再被問）：撐過間隔且之後救得回來也算過（救命推力仍是嚴格的）。
        gap = next_burn_gap(game, side) if relax else None
        if gap is None:
            survives = orbit_survives
        else:
            target = []                           # level 2：第二發要補得完同一個攔截（目標位置用到才算）

            def survives(g, s, d):
                if orbit_survives(g, s, d):
                    return True
                if self.gap_survival >= 2 and not target:
                    target.append((reuse_call(propagate, mu, re, ve, tof, gd)[0], tof))
                return gap_burn_survives(g, s, d, gap, target=target[0] if target else None,
                                         max_revs=self.max_revs)
        if full and tof <= game.next_window():
            # 只有「真的會命中」才免檢查：J2 打靶沒收斂時 Lambert 二體解會偏幾公里，
            # 沒抓到就會留在一條可能撞地的轉移軌道上（copilot 演練抓到過）
            rp_t, _ = reuse_call(propagate, mu, rp, vp + dv / 1000.0, tof, gd)
            re_t, _ = reuse_call(propagate, mu, re, ve, tof, gd)
            if np.linalg.norm(rp_t - re_t) <= 0.5 * R.capture_radius_km or survives(game, side, dv):
                return dv
        if survives(game, side, dv):
            return dv
        for _ in range(8):
            dv *= 0.5
            if survives(game, side, dv):
                return dv
        rb = rescue_burn(game, side)
        return rb if rb is not None else np.zeros(3)


def _direction_set(kind):
    if kind == "axes":
        dirs = [np.array(d, dtype=float) for d in
                [(1, 0, 0), (-1, 0, 0), (0, 1, 0), (0, -1, 0), (0, 0, 1), (0, 0, -1)]]
    elif kind == "full":
        dirs = [np.array(d, dtype=float) for d in product((-1, 0, 1), repeat=3) if any(d)]
    else:
        raise ValueError(kind)
    return [d / np.linalg.norm(d) for d in dirs]


class EscapeEvader(Agent):
    """開局高能量逃逸：前 `n_escape` 個躲者回合沿 (徑向+沿軌道) 推滿，之後交給 DvEvader。

    來源（HAP-108 exploitability 重播）：針對 rollout 追者的反制躲者，機動類型跟一般躲者一樣
    （1061/1061 m/s 徑向+沿軌道），差別只在**第二發緊接著推**——兩三個回合內就把遠地點拉到
    追者追不到的高度，rollout 追者判斷所有候選都輸、乾脆不追。把它做成顯式對手模型，
    追者的 rollout 才會把「開局就逃」納入最壞情況。
    """
    name = "escape_evader"

    def __init__(self, n_escape=2, direction=(1.0, 1.0, 0.0), then="dv_evader_fast"):
        d = np.asarray(direction, dtype=float)
        self.dir = d / np.linalg.norm(d)
        self.n_escape = n_escape
        self.then_spec = then
        self._then = None
        self._done = 0

    def reset(self, seed=None):
        self._done = 0
        if self._then is not None:
            self._then.reset(seed)

    def act(self, game, side):
        assert side == "evader"
        if self._done < self.n_escape and game.burn_cap(side) > 0:
            dv = rsw_to_eci_dv(game, side, self.dir * game.burn_cap(side))
            for _ in range(6):
                if orbit_survives(game, side, dv):
                    self._done += 1
                    return dv
                dv = dv * 0.5
            self._done = self.n_escape
        if self._then is None:
            from agents import make_agent
            self._then = make_agent(self.then_spec)
        return self._then.act(game, side)


class DvEvader(Agent):
    name = "dv_evader"

    def __init__(self, directions="full", mags=(1.0, 0.4), fuel_weight=0.3, horizon_windows=4.0, max_revs=1):
        self.dirs = _direction_set(directions)
        self.mags = tuple(mags)
        self.fuel_weight = fuel_weight      # 每花 1 m/s 自己的油扣多少分（m/s 等價）
        self.horizon_windows = horizon_windows
        self.max_revs = max_revs
        if directions != "full" or tuple(mags) != (1.0, 0.4):
            self.name = f"dv_evader({directions},{len(self.mags)}mag)"

    def _score(self, g, spent):
        if g.done:
            return 1e9 if g.winner == "evader" else -1e9
        need, _ = pursuer_need(g, horizon=need_horizon(g, self.horizon_windows), max_revs=self.max_revs,
                               pts_per_period=16, n_refine=1)
        if not math.isfinite(need):
            return 1e8 - self.fuel_weight * spent
        return (need - g.fuel_left("pursuer")) - self.fuel_weight * spent

    def act(self, game, side):
        assert side == "evader"
        cap = game.burn_cap(side)
        best = (-math.inf, np.zeros(3))
        cands = [np.zeros(3)]
        if cap > 0.0:
            cands += [d * m * cap for d in self.dirs for m in self.mags]
        doomed = not orbit_survives(game, side, np.zeros(3))
        for k, dv_rsw in enumerate(cands):
            dv = rsw_to_eci_dv(game, side, dv_rsw)
            if (k > 0 or doomed) and not orbit_survives(game, side, dv):
                continue                      # 推完會在比賽結束前再入：直接淘汰
            g = game.clone()
            g.play_turn(dv)
            s = self._score(g, float(np.linalg.norm(dv_rsw)))
            if s > best[0]:
                best = (s, dv)
        if best[0] == -math.inf and doomed:
            rb = rescue_burn(game, side)
            return rb if rb is not None else np.zeros(3)
        return best[1]
