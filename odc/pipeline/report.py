"""呈現計分分項並保存本次任務的執行紀錄
主要入口為 print_score_breakdown、append_run_history。
"""
import os
import math
import json
import datetime
from odc.search.optimizer import MissionOptimizer
from odc.search.revs import run_study_over_revs
from odc.search.replay import reconstruct_mission_logs
from odc.search.ranking import _mission_rank_key, over_dv_count, is_disqualified
from odc.runlog import log, setup as setup_logging


def append_run_history(config, mission_info, execution_time, gmat_result=None,
                        fixed_script_result=None, fixed_script_source=None,
                        path=os.path.join("outputs", "run_history.jsonl")):
    """把這次執行的結果 (連同用的 config) 附加成一行 JSON，累積成可回頭比較的執行紀錄。"""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    record = {
        "timestamp": datetime.datetime.now().isoformat(timespec="seconds"),
        "num_burns": mission_info["num_burns"],
        "score": round(float(mission_info["score"]), 4),
        "delta_v_mps": round(float(mission_info["total_dv_mps"]), 2),
        "t_team_sec": round(float(mission_info["T_team"]), 2),
        "miss_km": round(float(mission_info["miss_km"]), 6),
        "penalty_count": int(mission_info["penalty_count"]),
        "over_dv_count": over_dv_count(mission_info),
        "disqualified": is_disqualified(mission_info),
        "official_score": mission_info.get("official_score"),
        "dc_converged": bool(mission_info["dc_converged"]),
        "execution_time_sec": round(execution_time, 2),
        "orbit_A": config["orbit_A"],
        "orbit_B": config["orbit_B"],
        "rules": config["rules"],
        "strategy": config.get("strategy", {}),
        "optimization": config["optimization"],
    }
    if gmat_result is not None:
        record["gmat_verified"] = {
            "intercept_success": gmat_result["intercept_success"],
            "targeter_converged": gmat_result["targeter_converged"],
            "miss_km": round(gmat_result["miss_km"], 6),
            "t_team_sec": round(gmat_result["t_team_sec"], 2),
            "final_burn_dv_mps": round(gmat_result["final_burn_dv_mps"], 2),
            "final_burn_legal": gmat_result["final_burn_legal"],
        }
    # 固定燃燒版本 (outputs/output_submit.txt，沒有求解器) 的驗證結果——正式提交前
    # 檢查這個欄位是不是 intercept_success/final_burn_legal 都 true，比 gmat_verified
    # 那個 (DC 版本) 更接近實際要繳交的東西。
    if fixed_script_result is not None:
        record["fixed_script_verified"] = {
            # "gmat_dc"：一般版本乾淨通過，燃燒值來自 GMAT DC 收斂後的答案 (最可信)。
            # "python_fallback"：一般版本 (DC) 沒有乾淨通過 (通常是 DC 的 Vary 邊界卡在
            # 合法 Δv 範圍、搆不到 Python 認為需要的值)，改用 Python 自己算出的燃燒值
            # 繞過 DC 直接驗證——這種情況下 final_burn_legal 可能是 false，代表這個方案
            # 命中但超標：初賽是扣 10 分/次，排位賽起是失格 (run_output_stage 不會產生固定版)。
            "source": fixed_script_source,
            "intercept_success": fixed_script_result["intercept_success"],
            "miss_km": round(fixed_script_result["miss_km"], 6),
            "t_team_sec": round(fixed_script_result["t_team_sec"], 2),
            "final_burn_dv_mps": round(fixed_script_result["final_burn_dv_mps"], 2),
            "final_burn_legal": fixed_script_result["final_burn_legal"],
        }
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
    log.info(f"📒 執行紀錄已附加到 {path}")


def print_score_breakdown(mission_info, optimizer):
    """把最終分數拆成三塊，並印出當前工作點的「交換率」（HAP-38）。

    純加印，完全不改任何計算：三塊的公式跟 odc/scorer.calculate_score 逐字一致，
    輸入直接取 mission_info 裡計分當下用的同一組值（T_team 就是計分用的 intercept_time、
    total_dv_mps/miss_km/penalty_count 也都是），所以三塊加起來一定等於 mission_info
    ["score"]——會順手驗一次，對不上就印警告（代表某處算法漂移了，該查）。

    「交換率」= 計分 sigmoid 在當前工作點的斜率。時間/燃料兩項都是 S=25/(1+e^{k(x-C)})，
    dS/dx = -k·(25-S)·S/25，所以：
      • 每早到 1 秒的價值   = k_t·(25-score_time)·score_time/25   分/秒
      • 每省 1 m/s 的價值   = k_v·(25-score_dv)·score_dv/25       分/(m/s)
    兩者相除就是「省 1 秒 相當於 省多少 m/s」——比賽當天決定「要不要燒油換早到」時，
    這個數字直接告訴你損益平衡點，不用再自己心算 sigmoid。飽和（斜率≈0）時價值趨近 0，
    那一項再怎麼推都幾乎不加分，也一眼看得出來。
    """
    dr = float(mission_info["miss_km"])            # km
    T = float(mission_info["T_team"])              # s（= 計分用的 intercept_time）
    dv = float(mission_info["total_dv_mps"])       # m/s
    # penalty_count = 機動間隔違規 (官方扣分)；單棒超標是失格，score 裡只是搜尋用的軟懲罰。
    # 2026-10-19 之前的存檔沒有 over_dv_count，那時 penalty_count 本身就是單棒超標次數。
    n_over = over_dv_count(mission_info)
    pen = int(mission_info["penalty_count"]) if "over_dv_count" in mission_info else 0
    k_t, C_t = optimizer.k_t, optimizer.C_t
    k_v, C_v = optimizer.k_v, optimizer.C_v

    score_dist = 50.0 * math.exp(-(max(dr, 5.0) - 5.0) / 100.0)
    score_time = 25.0 / (1.0 + math.exp(min(k_t * (T - C_t), 700.0)))
    score_dv = 25.0 / (1.0 + math.exp(min(k_v * (dv - C_v), 700.0)))
    penalty = pen * 10.0
    soft = n_over * 10.0
    total = max(score_dist + score_time + score_dv - penalty - soft, 0.0)
    # 排位賽模式的失格層 (總 Δv 超標 / 單棒超出拆棒範圍)：搜尋用分數 < 0，只看違規量、不是上面
    # 幾項相加 (scorer.ranked_search_score)，直接照記錄的分數印。
    dq_tier = bool(getattr(optimizer, "RANKING_RULES", False)) and float(mission_info["score"]) < 0.0
    if dq_tier:
        total = float(mission_info["score"])

    # 每單位的邊際價值（sigmoid 斜率，恆為非負，代表「往好的方向改」能拿回的分數）
    val_per_sec = k_t * (25.0 - score_time) * score_time / 25.0     # 分 / 秒
    val_per_mps = k_v * (25.0 - score_dv) * score_dv / 25.0         # 分 / (m/s)

    lines = [f"\n── 分數拆解與交換率 {'─' * 30}",
             f"  距離   {score_dist:>6.2f} / 50   (Δr_min {dr*1000:,.0f} m；≤5,000 m 時地板滿分 50)",
             f"  時間   {score_time:>6.2f} / 25   (T {T:,.0f} s vs C_t {C_t:,.0f} s；每早到 1 s ≈ +{val_per_sec:.4g} 分)",
             f"  燃料   {score_dv:>6.2f} / 25   (ΔV {dv:,.0f} m/s vs C_v {C_v:,.0f} m/s；每省 1 m/s ≈ +{val_per_mps:.4g} 分)",
             f"  違規   {-penalty:>6.2f}        ({pen} 次機動間隔違規 × -10)"]
    if is_disqualified(mission_info):
        if dq_tier:
            lines.append("  失格層        (總 Δv 超標或單棒超出拆棒範圍：搜尋用分數只看超標量，"
                         "任何合法解都排在它前面)")
        elif n_over:
            lines.append(f"  超標   {-soft:>6.2f}        ({n_over} 棒單棒超標 × -10，搜尋用軟懲罰)")
        lines += [f"  {'─' * 5}",
                  f"  合計   {total:>6.2f}        (搜尋用分數)",
                  "  🔴 失格：" + "；".join(mission_info.get("dq_reasons") or ["單棒 Δv 超標"])
                  + "——沒有官方分數，不可繳交。"]
    else:
        lines += [f"  {'─' * 5}",
                  f"  合計   {total:>6.2f} / 100"]

    # 交換率：省 1 秒 相當於 省多少 m/s（燃料/時間邊際價值之比）
    if val_per_mps > 1e-12 and val_per_sec > 1e-12:
        mps_per_sec = val_per_sec / val_per_mps
        lines.append(f"  ⇄ 交換率：省 1 秒 ≈ 省 {mps_per_sec:,.2f} m/s"
                     f"（花 ≤{mps_per_sec:,.2f} m/s 換早到 1 秒才划算；反過來省 1 m/s ≈ 早到 "
                     f"{1.0/mps_per_sec:,.2f} 秒）")
    else:
        which = []
        if val_per_sec <= 1e-12:
            which.append("時間項已飽和（再早到幾乎不加分）")
        if val_per_mps <= 1e-12:
            which.append("燃料項已飽和（再省油幾乎不加分）")
        lines.append(f"  ⇄ 交換率：{'、'.join(which)}——這一側推不動分數了。")
    log.info("\n".join(lines))

    # 自我驗算：三塊必須加得回 mission_info 記錄的分數（對不上代表算法漂移）
    recorded = float(mission_info["score"])
    if abs(total - recorded) > 1e-6:
        log.warning(f"⚠️ 拆解 {total:.6f} 與記錄分數 {recorded:.6f} 不一致"
                    f"（差 {abs(total-recorded):.2e}）——計分算法可能有處漂移了，請查。")
