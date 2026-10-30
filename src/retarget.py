"""全攝動 B 平面重瞄準（`main.py --from-mission <path> --retarget-full-perturbation`，2026-10-19）。

Python 端用 J2–J4 搜尋拆棒，排位賽官方驗證開 EGM96 20×20、潮汐、阻力、日月、SRP、相對論。
同一組脈衝放進全攝動，短任務偏 0.5–1.3 km，22.6 h 的 hyper_far 偏到 111 km
（docs/research/PERTURBATION_GAP_20261019.md）。這裡在 GMAT 全攝動下用 DifferentialCorrector 改一棒，
只消掉垂直於相對速度的兩個分量（B 平面），再重播、重新判定合法性。

流程（全部串行，同一時間只有一個 GMAT 行程）：
1. 原方案全攝動重播（密集報表）→ d_min、預定攔截時刻的相對速度 → B 平面基底。
2. B 平面 DC 改第 idx 棒。
3. 新方案全攝動重播 → d_min、最近點時刻 t_cpa、攔截前最低高度。
4. 最後一段滑行改成停在 t_cpa（沿相對速度的落差只差幾秒，不花 Δv 修；停在最近點才讓
   繳交腳本自己報的 MissDistance 等於 d_min）。
5. 判定：DC 收斂、d_min ≤ 5 km、Earth-safe、t_cpa ≤ T_max、單棒/總 Δv 不失格
   （src.scorer.assess_legality，跟 Master 1cd196d 的失格判定同一個函式）。
任何一項不過 → accepted = False，呼叫端保留原方案並大聲警告。

燃燒值在判定與重播前先四捨五入到 7 位小數（km/s）：繳交腳本就是這樣寫的，判定要看的是
真正會被寫出去的值（7 位小數的捨入最多讓單棒大小差 ~9e-5 m/s，比 1e-5 的容許量大）。
"""
import math
import os
import re
import subprocess
import time
from pathlib import Path

import numpy as np

from src.scorer import assess_legality
from src.script_generator import full_perturbation_script

MISS_KM = 5.0          # 規則：Δr ≤ 5 km 算攔截成功
EXT_SEC = 600.0        # 預定攔截時刻後再多傳 10 分鐘，最近點可能晚到（hyper_far 晚 62 s）
MAX_STEP = 60.0        # 重播報表每步一列；步長限 60 s 讓 Hermite 內插夠準
STOP_ALT_KM = 50.0     # B 掉到這個高度就停（攔截後常鑽進大氣，MSISE 會讓積分器卡死）
BPLANE_TOL_KM = 0.05   # DC 的 Achieve 容許 0.02 km；讀回殘差超過這個就不算收斂
GMAT_TIMEOUT_SEC = 900.0
BURN_DECIMALS = 7      # script_generator 寫燃燒分量用 .7f（km/s）
TIME_DECIMALS = 5      # 滑行時間用 .5f


def round_burns(burns):
    return [[round(float(c), BURN_DECIMALS) for c in b] for b in burns]


def round_times(times):
    return [round(float(t), TIME_DECIMALS) for t in times]


def burn_times(times):
    """每棒的點火時刻（times[i] 是第 i 棒之前的滑行，times[-1] 是最後一棒之後的滑行）。"""
    return [float(t) for t in np.cumsum(times[:-1])]


def bplane_basis(v_rel):
    """垂直於相對速度的兩個單位向量。"""
    v = np.asarray(v_rel, dtype=float)
    n = float(np.linalg.norm(v))
    if not math.isfinite(n) or n < 1e-9:
        raise ValueError(f"相對速度太小（{n:.3g} km/s），B 平面沒有定義")
    u = v / n
    a = np.array([0.0, 0.0, 1.0]) if abs(u[2]) < 0.9 else np.array([1.0, 0.0, 0.0])
    e1 = np.cross(u, a)
    e1 /= np.linalg.norm(e1)
    return [e1.tolist(), np.cross(u, e1).tolist()]


# ---------------------------------------------------------------- GMAT 執行
def run_gmat(console, script_txt, folder, tag, timeout=GMAT_TIMEOUT_SEC):
    """寫 folder/tag.script、跑 GmatConsole，stdout/stderr 存檔。不丟例外，失敗看 returncode。"""
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    script = (folder / f"{tag}.script").resolve()
    script.write_text(script_txt, encoding="ascii")
    console = os.path.abspath(os.path.expanduser(console))
    started = time.perf_counter()
    if not os.path.exists(console):
        out = dict(returncode=None, stdout="", stderr=f"找不到 GmatConsole：{console}")
    else:
        try:
            p = subprocess.run([console, "--exit", "--run", str(script)],
                               cwd=os.path.dirname(console), capture_output=True, text=True,
                               timeout=timeout)
            out = dict(returncode=p.returncode, stdout=p.stdout or "", stderr=p.stderr or "")
        except subprocess.TimeoutExpired as exc:
            def _s(x):
                return x.decode("utf-8", "replace") if isinstance(x, bytes) else (x or "")
            out = dict(returncode=None, stdout=_s(exc.stdout), stderr=f"TIMEOUT {timeout}s")
        except OSError as exc:
            out = dict(returncode=None, stdout="", stderr=f"呼叫 GmatConsole 失敗：{exc}")
    (folder / f"{tag}.stdout.txt").write_text(out["stdout"], encoding="utf-8")
    (folder / f"{tag}.stderr.txt").write_text(out["stderr"], encoding="utf-8")
    out["wall_sec"] = round(time.perf_counter() - started, 2)
    out["script"] = str(script)
    return out


def _tail(out, n=12):
    return "\n".join((out["stdout"] + "\n" + out["stderr"]).strip().splitlines()[-n:])


# ---------------------------------------------------------------- 重播後處理
def read_dense_rows(path):
    """密集報表 → (n, 13) 陣列：t, rB, vB, rA, vA。格式不對的列略過。"""
    rows = []
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            parts = line.split()
            if len(parts) != 13:
                continue
            try:
                vals = [float(x) for x in parts]
            except ValueError:
                continue
            if all(math.isfinite(v) for v in vals):
                rows.append(vals)
    return np.array(rows, dtype=float).reshape(-1, 13)


def _hermite(t0, t1, p0, v0, p1, v1, s):
    """三次 Hermite：s ∈ [0,1] 的陣列 → 位置 (len(s), 3)。"""
    h = t1 - t0
    s = s[:, None]
    return ((2 * s**3 - 3 * s**2 + 1) * p0 + (s**3 - 2 * s**2 + s) * h * v0
            + (-2 * s**3 + 3 * s**2) * p1 + (s**3 - s**2) * h * v1)


def analyze_dense(rows, t_plan, sub=64):
    """最小距離、最近點時刻、預定攔截時刻的相對位置/速度，以及攔截（t_cpa）前 B 的最低地心距。"""
    if len(rows) < 2:
        raise ValueError("重播報表不到兩列")
    t = rows[:, 0]
    rB, vB, rA, vA = rows[:, 1:4], rows[:, 4:7], rows[:, 7:10], rows[:, 10:13]
    s = np.linspace(0.0, 1.0, sub + 1)
    seg_t, seg_d, seg_rb = [], [], []
    for i in range(len(t) - 1):
        if t[i + 1] - t[i] <= 1e-6:      # 燃燒前後同一時刻兩列：速度不連續，不內插
            continue
        dr = _hermite(t[i], t[i + 1], rB[i] - rA[i], vB[i] - vA[i],
                      rB[i + 1] - rA[i + 1], vB[i + 1] - vA[i + 1], s)
        rb = _hermite(t[i], t[i + 1], rB[i], vB[i], rB[i + 1], vB[i + 1], s)
        seg_t.append(t[i] + s * (t[i + 1] - t[i]))
        seg_d.append(np.linalg.norm(dr, axis=1))
        seg_rb.append(np.linalg.norm(rb, axis=1))
    if not seg_t:
        raise ValueError("重播報表沒有可內插的區段")
    T, D, RB = np.concatenate(seg_t), np.concatenate(seg_d), np.concatenate(seg_rb)
    k = int(np.argmin(D))
    # 最近點附近再細化（60 s / 64 ≈ 1 s；相對速度 km/s 級時要細到 ms）
    i = min(max(int(np.searchsorted(t, T[k], side="right") - 1), 0), len(t) - 2)
    d_min, t_cpa = float(D[k]), float(T[k])
    ss = np.linspace(0.0, 1.0, 20001)
    for j in (i - 1, i, i + 1):
        if 0 <= j < len(t) - 1 and t[j + 1] - t[j] > 1e-6:
            dd = np.linalg.norm(_hermite(t[j], t[j + 1], rB[j] - rA[j], vB[j] - vA[j],
                                         rB[j + 1] - rA[j + 1], vB[j + 1] - vA[j + 1], ss), axis=1)
            m = int(np.argmin(dd))
            if dd[m] < d_min:
                d_min, t_cpa = float(dd[m]), float(t[j] + ss[m] * (t[j + 1] - t[j]))
    jp = np.nonzero(np.abs(t - t_plan) < 1e-3)[0]
    dr_plan = (rB[jp[0]] - rA[jp[0]]).tolist() if len(jp) else None
    dv_plan = (vB[jp[-1]] - vA[jp[-1]]).tolist() if len(jp) else None
    pre = T <= t_cpa + 1e-9
    stopped_early = bool(t[-1] < min(t_plan, t_cpa) - 1e-3)
    return {
        "d_min_km": d_min, "t_cpa_sec": t_cpa, "t_plan_sec": float(t_plan),
        "d_at_plan_km": float(np.linalg.norm(dr_plan)) if dr_plan is not None else None,
        "dr_plan_km": dr_plan, "dv_rel_plan_kms": dv_plan,
        "min_radius_before_intercept_km": float(RB[pre].min()),
        "stopped_early": stopped_early, "n_rows": int(len(t)),
    }


def replay(console, orbit_A, orbit_B, burns, times, env, folder, tag, gravity_degree):
    report = (Path(folder) / f"{tag}.report").resolve()
    report.parent.mkdir(parents=True, exist_ok=True)
    report.unlink(missing_ok=True)       # 殘留的舊報表不能被當成這次的結果
    txt = full_perturbation_script(orbit_A, orbit_B, burns, times, env, gravity_degree=gravity_degree,
                                   report_path=str(report), ext_sec=EXT_SEC, max_step=MAX_STEP,
                                   stop_alt_km=STOP_ALT_KM)
    out = run_gmat(console, txt, folder, tag)
    res = {"tag": tag, "wall_sec": out["wall_sec"], "returncode": out["returncode"]}
    if out["returncode"] != 0 or not report.exists() or report.stat().st_size == 0:
        res["error"] = _tail(out)
        return res
    try:
        res.update(analyze_dense(read_dense_rows(report), sum(times)))
    except ValueError as exc:
        res["error"] = f"{exc}\n{_tail(out)}"
    return res


def run_bplane_dc(console, orbit_A, orbit_B, burns, times, env, idx, bplane, folder, tag,
                  gravity_degree):
    summary = (Path(folder) / f"{tag}.summary").resolve()
    summary.parent.mkdir(parents=True, exist_ok=True)
    summary.unlink(missing_ok=True)
    txt = full_perturbation_script(orbit_A, orbit_B, burns, times, env, gravity_degree=gravity_degree,
                                   retarget_idx=idx, bplane=bplane, summary_path=str(summary),
                                   max_step=MAX_STEP, stop_alt_km=STOP_ALT_KM)
    out = run_gmat(console, txt, folder, tag)
    m = re.search(r"Targeting Completed in (\d+) iterations", out["stdout"])
    res = {"tag": tag, "wall_sec": out["wall_sec"], "returncode": out["returncode"],
           "iterations": int(m.group(1)) if m else None, "converged": False}
    vals = []
    if summary.exists():
        try:
            vals = [float(x) for x in summary.read_text().split()[-6:]]
        except ValueError:
            vals = []
    if out["returncode"] != 0 or len(vals) != 6 or not all(math.isfinite(v) for v in vals):
        res["error"] = _tail(out)
        return res
    dr = np.array(vals[3:])
    resid = [float(dr @ np.array(e)) for e in bplane]
    res.update(burn_kms=vals[:3], dr_plan_km=vals[3:], bplane_residual_km=resid)
    said_no = "did not converge" in out["stdout"].lower()
    res["converged"] = (not said_no) and max(abs(r) for r in resid) < BPLANE_TOL_KM
    if not res["converged"]:
        res["error"] = ("GMAT 回報未收斂" if said_no else
                        f"B 平面殘差 {max(abs(r) for r in resid):.3f} km > {BPLANE_TOL_KM} km")
    return res


# ---------------------------------------------------------------- 主流程
def retarget_full_perturbation(*, config, burns, times, idx, env, console, folder,
                               max_dv_mps, min_interval_sec, max_total_dv_mps, t_max_sec,
                               min_radius_km, score_fn, gravity_degree=4, runner=None):
    """在全攝動下 B 平面重瞄準第 idx 棒並重新判定。回傳 dict（全部可 JSON 化）。

    score_fn(leg, miss_km, t_team) → legality_fields 那種 dict（含 official_score），由呼叫端
    用 optimizer.legality_fields 提供，計分參數就跟求解時一樣。runner 是測試用的替身，
    簽名同 {"replay": replay, "dc": run_bplane_dc}。"""
    runner = runner or {"replay": replay, "dc": run_bplane_dc}
    orbit_A, orbit_B = config["orbit_A"], config["orbit_B"]
    n = len(burns)
    if not -n <= idx < n:
        raise ValueError(f"--retarget-burn {idx} 超出範圍（這個方案有 {n} 棒，索引 0..{n - 1}）")
    idx %= n
    burns0 = round_burns(burns)
    times0 = round_times(times)
    t_burns = burn_times(times0)
    res = {"retarget_idx": idx, "accepted": False, "reasons": [],
           "original": {"burns": burns0, "times": times0}}

    def legality(bs, t_team, d_min):
        mags = [math.sqrt(sum(c * c for c in b)) * 1000.0 for b in bs]
        leg = assess_legality(mags, t_burns, max_dv_mps, min_interval_sec, max_total_dv_mps)
        out = dict(leg, burn_dv_mps=mags, headroom_mps=[max_dv_mps - m for m in mags])
        out.update(score_fn(leg, d_min, t_team))
        return out

    before = runner["replay"](console, orbit_A, orbit_B, burns0, times0, env, folder,
                              "original_replay", gravity_degree)
    res["original"]["replay"] = before
    if "error" in before:
        err = before["error"].strip().splitlines()
        res["reasons"].append("原方案全攝動重播失敗" + (f"：{err[-1]}" if err else ""))
        return res
    res["original"]["legality"] = legality(burns0, before["t_plan_sec"], before["d_min_km"])
    if before["dv_rel_plan_kms"] is None:
        res["reasons"].append("原方案重播在預定攔截時刻前就停了（B 掉到 50 km 以下？）")
        return res
    try:
        basis = bplane_basis(before["dv_rel_plan_kms"])
    except ValueError as exc:
        res["reasons"].append(str(exc))
        return res
    res["bplane_basis"] = basis

    dc = runner["dc"](console, orbit_A, orbit_B, burns0, times0, env, idx, basis, folder,
                      f"bplane_dc_b{idx}", gravity_degree)
    res["dc"] = dc
    if not dc["converged"]:
        res["reasons"].append(f"B 平面 DC 沒有收斂：{dc.get('error', '')}".strip())
        return res
    new_burns = [list(b) for b in burns0]
    new_burns[idx] = [round(float(c), BURN_DECIMALS) for c in dc["burn_kms"]]
    after = runner["replay"](console, orbit_A, orbit_B, new_burns, times0, env, folder,
                             "retargeted_replay", gravity_degree)
    res["retargeted_replay"] = after
    if "error" in after:
        err = after["error"].strip().splitlines()
        res["reasons"].append("重瞄準後全攝動重播失敗" + (f"：{err[-1]}" if err else ""))
        return res

    # 最後一段滑行停在最近點（見模組說明第 4 點）
    new_times = list(times0)
    new_times[-1] = round(after["t_cpa_sec"] - (t_burns[-1] if t_burns else 0.0), TIME_DECIMALS)
    t_team = float(sum(new_times))
    leg = legality(new_burns, t_team, after["d_min_km"])
    old_mag = math.sqrt(sum(c * c for c in burns0[idx])) * 1000.0
    new_mag = leg["burn_dv_mps"][idx]
    res["retargeted"] = {
        "burns": new_burns, "times": new_times, "t_team_sec": t_team,
        "d_min_km": after["d_min_km"], "legality": leg,
        "burn_change": {"old_mps": old_mag, "new_mps": new_mag,
                        "vector_change_mps": 1000.0 * math.dist(burns0[idx], new_burns[idx]),
                        "total_dv_change_mps": leg["total_dv_mps"] - res["original"]["legality"]["total_dv_mps"]},
    }
    reasons = res["reasons"]
    if after["d_min_km"] > MISS_KM:
        reasons.append(f"重瞄準後 d_min {after['d_min_km']:.3f} km > {MISS_KM:g} km")
    if after["stopped_early"] or after["min_radius_before_intercept_km"] < min_radius_km - 1e-3:
        reasons.append(f"攔截前 B 最低地心距 {after['min_radius_before_intercept_km']:,.1f} km "
                       f"< {min_radius_km:,.1f} km（Earth-safe 不過）")
    if t_max_sec is not None and t_team > t_max_sec + 1e-6:
        reasons.append(f"最近點時刻 {t_team:,.1f} s 超過 T_max {t_max_sec:,.1f} s")
    if new_times[-1] <= 0:
        reasons.append("最近點落在最後一棒之前")
    if leg["disqualified"]:
        reasons += [f"失格：{r}" for r in leg["dq_reasons"]]
    res["accepted"] = not reasons
    return res
