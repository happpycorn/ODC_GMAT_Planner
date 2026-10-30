"""保存與讀取拆前贏家，記錄無合法路線的診斷
主要入口為 save_winner_checkpoint、load_winner_checkpoint。
"""
import json
import datetime
from odc.pipeline.artifacts import (create_run_dir, save_mission, load_mission,
                                    write_json, file_digest, provenance)
import numpy as np
from odc.search.optimizer import MissionOptimizer
from odc.search.revs import run_study_over_revs
from odc.search.replay import reconstruct_mission_logs
from odc.search.ranking import _mission_rank_key, over_dv_count, is_disqualified
from odc.config.validator import validate_config, ConfigValidationError
from odc.scoring.scorer import calculate_score, assess_legality, DV_LIMIT_TOL_MPS
from odc.runlog import log, setup as setup_logging
from odc.gmat.verification import patch_report_level


def _to_jsonable(obj):
    """numpy 陣列/純量、tuple 轉成 json.dump 吃得下的型別（float 走 repr，逐位元可還原）。"""
    if isinstance(obj, dict):
        return {k: _to_jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, np.ndarray)):
        return [_to_jsonable(v) for v in obj]
    if isinstance(obj, np.generic):
        return obj.item()
    return obj


def save_winner_checkpoint(path, optimizer, burns, times, mission_info):
    """把「拆棒前」的 DE 贏家存檔（C3，2026-09-23）。

    動機：拆棒器（`legalize_violating_winner`）是搜尋之後的純後處理，但以前改它、調它都得
    重跑十幾分鐘到幾小時的搜尋才驗得到。存下贏家後，`main.py --from-winner <檔>` 直接從這裡
    接拆棒 + GMAT，幾分鐘一輪。存的 config 是**勝出那趟 optimizer 實際用的**（含 REVS 集成
    挑中的 LAMBERT_MAX_REVS、C2 重搜改過的 MAX_BURNS），重播才會跟原管線走同一條路。"""
    payload = {
        "schema_version": 1, "stage": "presplit", "provenance": provenance(),
        "saved_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "config": optimizer.config,
        "burns": burns, "times": times, "mission_info": mission_info,
    }
    write_json(path, _to_jsonable(payload))
    log.debug(f"💾 拆棒前贏家已存檔：{path}（可用 --from-winner 重播拆棒/GMAT）")


def load_winner_checkpoint(path):
    """讀回 `save_winner_checkpoint` 的存檔 → (config, burns, times, mission_info, optimizer)。"""
    with open(path, "r", encoding="utf-8") as f:
        p = json.load(f)
    if p.get("stage", "presplit") != "presplit" or p.get("schema_version", 1) != 1:
        raise ValueError("需要拆棒前 winner 存檔；拆棒後方案請用 --from-mission。")
    config = p["config"]
    validate_config(config)
    mi = p["mission_info"]
    mi["x"] = np.asarray(mi["x"], dtype=np.float64)
    mi["aim_point"] = tuple(mi["aim_point"])
    burns = [tuple(b) for b in p["burns"]]
    return config, burns, list(p["times"]), mi, MissionOptimizer(config)


# 排位賽模式下搜尋找不到合法路線（所有候選都在失格層）時的結束碼，跟一般錯誤（1）分開，
# 讓批次腳本 / 現場一眼分得出「沒有合法解」與「程式壞了」。
EXIT_NO_LEGAL_ROUTE = 3


class NoLegalRouteError(RuntimeError):
    """搜尋只找到失格層的候選（總 Δv 超標或單棒超出拆棒範圍）。不是程式錯誤，是這組題目在目前的
    預算 / 棒數 / T_max 下找不到合法解。"""


def save_no_legal_route(path, optimizer):
    """把最接近合法的失格候選存成 `no_legal_route.json`（stage = "no_legal_route"，
    `--from-mission` 讀不進去，所以不會被拿去產繳交腳本），並印出違規量與下一步建議。"""
    nlr = optimizer.no_legal_route
    opt = optimizer
    with patch_report_level(opt):
        burns, times, mi = opt._replay_mission(nlr["x"], nlr["burns"])
    dvs = [float(np.linalg.norm(b)) * 1000.0 for b in burns]
    cap, soft = opt.MAX_DV * 1000.0, opt.MAX_DV_SOFT * 1000.0
    split_lim = opt.SPLIT_LIMIT * 1000.0
    over = [{"burn": i + 1, "dv_mps": d, "over_cap_mps": d - cap,
             "splittable": (i == len(dvs) - 1 and d <= split_lim)
             or (opt.SPLIT_LEADING and i < len(dvs) - 1 and d <= opt.LEADING_SPLIT_LIMIT * 1000.0)}
            for i, d in enumerate(dvs) if d > cap + DV_LIMIT_TOL_MPS]
    total = float(mi["total_dv_mps"])
    total_cap = opt.MAX_TOTAL_DV_MPS
    total_excess = None if total_cap is None else max(total - total_cap, 0.0)
    next_steps = [
        "加大搜尋預算：optimization.MAXITER（預設 600）、POPSIZE",
        "多跑幾顆種子：strategy.SEED_PORTFOLIO_N 或換 optimization.SEED",
        "放寬 optimization.MAX_BURNS（多棒讓每棒小、總 Δv 可能更省）",
        "核對 rules.T_MAX_SEC 與計分參數有沒有抄錯（check_problem.py）",
        "用 feasibility.py 看能量 / Δv 下限：下限本身就超過總 Δv 上限時，這題在目前 T_max 內沒有合法解",
    ]
    payload = {
        "schema_version": 1, "stage": "no_legal_route", "provenance": provenance(),
        "saved_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "_說明": "排位賽規則下失格，不可繳交；只供檢查。--from-mission 讀不進去（stage 不是 mission）。",
        "config": opt.config, "burns": burns, "times": times, "mission_info": mi,
        "violations": {
            "per_burn_dv_mps": dvs, "max_dv_mps": cap, "max_dv_soft_mps": soft,
            "splitter_limit_mps": split_lim, "over_cap_burns": over,
            "total_dv_mps": total, "max_total_dv_mps": total_cap, "total_dv_excess_mps": total_excess,
            "dq_reasons": mi.get("dq_reasons"), "search_score": float(mi["score"]),
        },
        "next_steps": next_steps,
    }
    write_json(path, _to_jsonable(payload))
    lines = ["\n" + "🔴" * 30,
             "  找不到合法路線：所有候選都會被排位賽規則判失格（總 Δv 超標或單棒超出拆棒範圍）。",
             f"  最接近合法的候選：{len(dvs)} 棒、總 Δv {total:,.1f} m/s"
             + ("" if total_cap is None else f"（上限 {total_cap:,.0f}，超 {total_excess:,.1f}）")
             + f"、T {float(mi['T_team']):,.0f} s"]
    for o in over:
        lines.append(f"    第 {o['burn']} 棒 {o['dv_mps']:,.1f} m/s，超過單棒上限 {o['over_cap_mps']:,.1f} m/s"
                     + ("（拆棒範圍內）" if o["splittable"] else
                        f"（超出拆棒範圍 {split_lim:,.0f} m/s）" if o["burn"] == len(dvs) else
                        f"（超出前導棒拆棒範圍 {opt.LEADING_SPLIT_LIMIT * 1000.0:,.0f} m/s）"
                        if opt.SPLIT_LEADING else "（前導棒，拆棒器只拆終端棒）"))
    lines += [f"  已存檔（不可繳交、不產生任何腳本）：{path}", "  下一步："]
    lines += [f"    • {t}" for t in next_steps]
    lines.append("🔴" * 30)
    log.error("\n".join(lines))
    return path
