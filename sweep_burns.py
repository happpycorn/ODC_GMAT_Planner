"""
sweep_burns.py —— 掃描「這個情境到底需要燒幾次」的輔助工具。

背景（詳見對話/STATUS.md）：MAX_BURNS 每多一個數字，決策變數維度線性增加、族群
大小也跟著線性放大，但 MAXITER (世代數) 不會跟著長——維度越高的案例在同樣的世代
預算下天生越吃虧，直接把「粗略掃過的分數」拿來下結論會冤枉高燃燒次數的案例
(實測過：6 次燒在 MAXITER=1000 下明顯輸 2 次燒，把 MAXITER 拉到 3000 後反而小幅
超過，證實純粹是預算不夠，不是 6 次燒真的比較差)。

所以這裡分兩階段，不是為了求快而犧牲正確性：
  1. 粗掃 (coarse)：MAXITER 刻意調低，快速跑過一個寬範圍的燃燒次數，只用來找
     「大概從哪裡開始不再明顯進步」的粗略訊號，不能直接拿來當最終結論。
  2. 精細驗證 (fine)：只針對粗掃找出來的候選窗口，用 config 原本的 MAXITER (使用者
     已經調過、信任的預算) 重新跑一次「公平」的比較，這一步的數字才能真的拿來下結論。

用法：
    uv run sweep_burns.py --config configs/practice_scenario.json
    uv run sweep_burns.py --config configs/practice_scenario.json --burns 1-8 --coarse-iters 400

跑完會印出兩張趨勢表 + 一個建議的 MAX_BURNS 範圍，用 --output-config 可以直接把
建議寫成一份新的 config 檔。
"""
import os
import sys
import copy
import json
import time
import argparse
import warnings
import multiprocessing

from src.optimizer import MissionOptimizer
from src.config_validator import validate_config, ConfigValidationError

# main.py 已經有讀取+驗證 config 的邏輯，這裡直接借用，不要重複寫一份容易兩邊不同步。
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from main import load_or_create_config  # noqa: E402


def parse_burns_arg(spec: str) -> list:
    """把 "1-8" 或 "1,2,3,5" 這種字串轉成整數清單。"""
    if "-" in spec and "," not in spec:
        lo, hi = spec.split("-")
        return list(range(int(lo), int(hi) + 1))
    return [int(x) for x in spec.split(",")]


def parse_args():
    parser = argparse.ArgumentParser(
        description="掃描一個情境需要燒幾次才夠，兩階段：粗掃找候選範圍 → 用真實預算精細驗證"
    )
    parser.add_argument("--config", default=os.path.join("configs", "config.json"),
                         help="要分析的情境設定檔 (預設 configs/config.json)")
    parser.add_argument("--burns", default="1-6",
                         help="粗掃要測的燃燒次數範圍，例如 '1-6' 或 '1,2,4,8' (預設 1-6)")
    parser.add_argument("--coarse-iters", type=int, default=300,
                         help="粗掃階段用的 MAXITER，刻意調低換速度 (預設 300)")
    parser.add_argument("--window", type=int, default=2,
                         help="精細驗證階段，候選燃燒次數往上延伸幾格 (預設 2，"
                              "即 [elbow-1, elbow, elbow+1, elbow+2])")
    parser.add_argument("--plateau-tol", type=float, default=0.05,
                         help="判斷「已經追上最佳分數」的容忍度 (0~100 分量表，預設 0.05)")
    parser.add_argument("--output-config", default=None,
                         help="把建議的 MAX_BURNS 寫成一份新的 config 檔存到這個路徑 (選填)")
    return parser.parse_args()


def run_stage(config: dict, burns: list, maxiter: int, popsize=None, label: str = "") -> dict:
    """跑一次 MissionOptimizer.run_study()，只回傳 burn_case_results (不管最終贏家的完整任務規劃)。"""
    stage_config = copy.deepcopy(config)
    stage_config["optimization"]["MAX_BURNS"] = burns
    stage_config["optimization"]["MAXITER"] = maxiter
    if popsize is not None:
        stage_config["optimization"]["POPSIZE"] = popsize
    try:
        validate_config(stage_config)
    except ConfigValidationError as exc:
        print(f"❌ 內部產生的設定檔驗證失敗 (不應該發生，回報這個 bug): {exc}")
        sys.exit(1)

    print(f"\n{'='*60}\n{label} — MAX_BURNS={burns}, MAXITER={maxiter}\n{'='*60}")
    optimizer = MissionOptimizer(stage_config)
    t0 = time.perf_counter()
    optimizer.run_study()
    elapsed = time.perf_counter() - t0
    print(f"⏳ {label} 耗時 {elapsed:.1f} 秒")
    return optimizer.burn_case_results


def print_score_table(results: dict, header: str):
    print(f"\n--- {header} ---")
    print(f"{'燃燒次數':>8} {'分數':>10} {'代數':>12} {'備註'}")
    if not results:
        print("  (沒有任何案例成功完成——可能撞地球/違規太多，檢查一下這個情境合不合理)")
        return
    best_k = max(results, key=lambda k: -results[k]["fitness"])
    for k in sorted(results):
        r = results[k]
        score = -r["fitness"]
        mark = " ⭐" if k == best_k else ""
        print(f"{k:>8} {score:>10.4f} {r['epochs_run']:>12}{r['note']}{mark}")


def find_elbow(results: dict, tol: float) -> int:
    """由小到大掃燃燒次數，回傳第一個「分數已經追到全範圍最佳值附近」的燃燒次數。"""
    scores = {k: -r["fitness"] for k, r in results.items()}
    best_score = max(scores.values())
    for k in sorted(scores):
        if scores[k] >= best_score - tol:
            return k
    return max(scores)  # 理論上不會走到這裡


def main():
    multiprocessing.freeze_support()
    warnings.filterwarnings("ignore")
    args = parse_args()

    config = load_or_create_config(args.config)
    burns_range = sorted(set(parse_burns_arg(args.burns)))

    # --- 第一階段：粗掃 ---
    coarse_results = run_stage(
        config, burns_range, args.coarse_iters, label="第一階段：粗掃"
    )
    print_score_table(coarse_results, "粗掃結果 (MAXITER 調低，數字僅供參考，不是最終結論)")

    if not coarse_results:
        print("\n❌ 粗掃階段所有案例都失敗了，先確認 config 的軌道/規則參數合不合理。")
        sys.exit(1)

    elbow = find_elbow(coarse_results, args.plateau_tol)
    if elbow == max(burns_range):
        print(f"\n⚠️  分數在測試範圍上限 ({elbow} 次) 還在提升，可能還沒到頂，"
              f"建議用 --burns 把範圍往上延伸再掃一次 (例如 --burns {min(burns_range)}-{elbow+4})。")

    window = sorted(set(
        k for k in range(max(min(burns_range), elbow - 1), min(max(burns_range), elbow + args.window) + 1)
    ))

    # --- 第二階段：精細驗證 (用 config 原本信任的 MAXITER/POPSIZE，不打折) ---
    real_maxiter = config["optimization"]["MAXITER"]
    fine_results = run_stage(
        config, window, real_maxiter, label="第二階段：精細驗證 (真實預算)"
    )
    print_score_table(fine_results, "精細驗證結果 (這一步的數字才能拿來下結論)")

    # --- 結論與建議 ---
    if fine_results:
        fine_scores = {k: -r["fitness"] for k, r in fine_results.items()}
        best_k = max(fine_scores, key=fine_scores.get)
        best_score = fine_scores[best_k]
        saturated_ks = [k for k, s in fine_scores.items() if s >= best_score - args.plateau_tol]
        recommended = min(saturated_ks)

        print(f"\n{'='*60}\n結論\n{'='*60}")
        if len(saturated_ks) > 1:
            print(f"分數在燃燒次數 {sorted(saturated_ks)} 之間幾乎打平 (都在最佳分數 {best_score:.4f} 的 "
                  f"{args.plateau_tol} 分以內)——這個情境的 Δv/時間預算相對寬鬆，多燒不會多加分。")
            print(f"👉 建議 MAX_BURNS 用 [{recommended}]（最少夠用的那個），"
                  f"省下多餘的搜尋時間跟高維度案例不收斂的風險。")
            print(f"⚠️  但「分數打平」不代表 Δr_min/ΔV_team/T_team 這些原始數字也打平——"
                  f"規則的平手判定是先比 Δr_min，再比 ΔV_team，再比 T_team，不是比 Score。"
                  f"正式要交出去的方案，還是回頭看上面各階段印出來的 Mission Plan 細節，"
                  f"不要只看這個建議就定案；覺得這裡太寬鬆可以用 --plateau-tol 調小。")
        else:
            print(f"分數隨燃燒次數有明顯差異，最佳是 {best_k} 次 (分數 {best_score:.4f})——"
                  f"這個情境對燃燒次數敏感，值得把預算留給這附近。")
            print(f"👉 建議 MAX_BURNS 用 {window}（精細驗證測過的範圍），"
                  f"或至少包含 {best_k}。")

        if args.output_config:
            suggested = copy.deepcopy(config)
            suggested["optimization"]["MAX_BURNS"] = (
                [recommended] if len(saturated_ks) > 1 else window
            )
            with open(args.output_config, "w", encoding="utf-8") as f:
                json.dump(suggested, f, indent=4)
            print(f"\n📄 已把建議的 MAX_BURNS 寫進 {args.output_config}")


if __name__ == "__main__":
    main()
