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

粗掃階段本身也會踩到同一個「維度越高越吃虧」的問題——如果整個 --burns 範圍都套
同一個 --coarse-iters，低燃燒次數 (維度低，很快收斂) 跟高燃燒次數 (維度高，同樣
代數還沒收斂) 比出來的分數本身就不公平，可能讓 find_elbow 提早停在一個被低估的
燃燒次數，害精細驗證階段的 --window 根本不會碰到真正該測的範圍。所以粗掃階段的
MAXITER 預設會依 decision_variable_dims (4×燃燒次數+1) 依比例分配：--coarse-iters
是套在「這次範圍裡維度最小的燃燒次數」上的世代數，其他燃燒次數依維度比例往上調
(細節見 scaled_coarse_iters)。這樣同樣測 --burns 1-8，不用为了公平而放寬 --window
去補找漏掉的高燃燒次數，粗掃階段本身就會給每個燃燒次數一個合理的世代數。

另外一個「分數高不等於真的需要多棒」的陷阱 (2026-08-15 加的檢查)：多棒解很常
退化成單棒——決策向量裡中間棒的 Δv 恰好是 0 (種子的空燒結構，L-SHADE 沒離開過
那個起點)，這種解跟低燃燒次數方案本質上是同一個，分數差異來自別的自由度而不是
多棒策略。實測在三組不同的極限測資上都看到這個現象 (見 STATUS.md「2026-08-15
白天」那節)。所以兩張趨勢表都多印一欄「實際用到」幾棒，結論那段也會在建議值
其實是退化解的時候明講——不然照著建議把 MAX_BURNS 開大只是浪費搜尋時間。
反過來說，如果每一棒都有實際燃燒 (例如單棒在物理上就不可能合法的情境)，那才是
真的需要多棒。

用法：
    uv run sweep_burns.py --config configs/config.json
    uv run sweep_burns.py --config configs/weird_test.json --burns 1-8 --coarse-iters 80
    uv run sweep_burns.py --config configs/weird_test.json --burns 1-8 --coarse-iters 80 --coarse-popsize 8

跑完會印出兩張趨勢表 + 一個建議的 MAX_BURNS 範圍，用 --output-config 可以直接把
建議寫成一份新的 config 檔。
"""
import os
import sys
import copy
import json
import math
import time
import argparse
import warnings
import multiprocessing

from src.optimizer import MissionOptimizer, decision_variable_dims, effective_burns
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


def scaled_coarse_iters(burns: list, base_iters: int, min_iters: int = 20, max_iters: int = None) -> dict:
    """
    幫粗掃階段算一份「依決策變數維度分配」的世代預算 ({燃燒次數: 世代數})，取代
    整個範圍套同一個 MAXITER 的舊做法。

    base_iters 套用在這次範圍裡維度最小的燃燒次數上 (通常就是 min(burns))，其他
    燃燒次數依維度比例往上調——維度公式跟 MissionOptimizer._generate_bounds 共用
    同一個 decision_variable_dims()，不會兩邊兜不起來。min_iters 是下限，避免比例
    算出來的世代數太小 (例如刻意只測極少數幾個高燃燒次數時) 讓 L-SHADE 連基本的
    探索都做不到。

    這個縮放比例是從 STATUS.md 記錄的實測結果歸納出來的經驗法則 (6 棒需要把
    MAXITER 從 1000 拉到 3000 才追上 2 棒，維度比 25/9≈2.78、代數比 3 倍，大致
    吻合線性關係)，不是嚴謹推導的理論公式——粗掃階段本來就只是抓大概的候選範圍，
    不是精確工具，這裡追求的是「不要系統性冤枉高燃燒次數」，不是完美的公平性。

    max_iters (選填)：硬上限，不管維度比例算出來多大都不會超過這個值。沒有上限的
    話，--burns 涵蓋的燃燒次數範圍一大 (維度隨之飆高)，公平縮放是「往上補」不是
    「整體往下砍」，最貴的那個案例反而可能比舊版 flat MAXITER 還貴——而並行跑的
    情況下，總耗時是看最慢的那個案例，不是看總和，所以這個案例變貴會直接拖累整體
    等待時間。加上限犧牲一點對最高燃燒次數的公平性，換一個看得到的時間上限。
    """
    reference_dims = decision_variable_dims(min(burns))
    iters = {
        k: max(min_iters, round(base_iters * decision_variable_dims(k) / reference_dims))
        for k in burns
    }
    if max_iters is not None:
        iters = {k: min(v, max_iters) for k, v in iters.items()}
    return iters


def parse_args():
    parser = argparse.ArgumentParser(
        description="掃描一個情境需要燒幾次才夠，兩階段：粗掃找候選範圍 → 用真實預算精細驗證"
    )
    parser.add_argument("--config", default=os.path.join("configs", "config.json"),
                         help="要分析的情境設定檔 (預設 configs/config.json)")
    parser.add_argument("--burns", default="1-8",
                         help="粗掃要測的燃燒次數範圍，例如 '1-6' 或 '1,2,4,8' (預設 1-6)")
    parser.add_argument("--coarse-iters", type=int, default=80,
                         help="粗掃階段套在『維度最小的燃燒次數』上的世代數，其他"
                              "燃燒次數依維度比例往上調 (見 scaled_coarse_iters，"
                              "預設 80)")
    parser.add_argument("--coarse-popsize", type=int, default=None,
                         help="粗掃階段用的 POPSIZE，不給就沿用 config 原本的值。"
                              "跟 --coarse-iters 是獨立的兩個加速槓桿——調小這個能"
                              "再省一輪運算量，不影響 --coarse-iters 的維度縮放")
    parser.add_argument("--coarse-iters-cap", type=int, default=None,
                         help="粗掃階段每個燃燒次數的世代數硬上限，不給就不設上限。"
                              "--burns 範圍涵蓋很高的燃燒次數時，維度縮放會把預算"
                              "往上補，最貴的案例可能比舊版 flat MAXITER 還貴，"
                              "拖累整體等待時間 (並行跑，總耗時看最慢的案例)——設"
                              "這個可以換一個看得到的時間上限，代價是最高燃燒次數"
                              "之間的比較沒那麼公平")
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

    if isinstance(maxiter, dict):
        iters_desc = "MAXITER(依維度縮放)={" + ", ".join(f"{k}:{maxiter[k]}" for k in sorted(maxiter)) + "}"
    else:
        iters_desc = f"MAXITER={maxiter}"
    print(f"\n{'='*60}\n{label} — MAX_BURNS={burns}, {iters_desc}\n{'='*60}")
    optimizer = MissionOptimizer(stage_config)
    t0 = time.perf_counter()
    optimizer.run_study()
    elapsed = time.perf_counter() - t0
    print(f"⏳ {label} 耗時 {elapsed:.1f} 秒")
    return optimizer.burn_case_results


def print_score_table(results: dict, header: str):
    print(f"\n--- {header} ---")
    print(f"{'燃燒次數':>8} {'分數':>10} {'實際用到':>9} {'代數':>8} {'備註'}")
    if not results:
        print("  (沒有任何案例成功完成——可能撞地球/違規太多，檢查一下這個情境合不合理)")
        return
    best_k = max(results, key=lambda k: -results[k]["fitness"])
    any_degenerate = False
    for k in sorted(results):
        r = results[k]
        score = -r["fitness"]
        eff = effective_burns(k, r.get("best_x"))
        mark = " ⭐" if k == best_k else ""
        # 「實際用到」比設定的燃燒次數少 = 中間棒有人在空燒，標星號提醒
        degen = "" if eff == k else " ⚠"
        if eff != k:
            any_degenerate = True
        print(f"{k:>8} {score:>10.4f} {str(eff)+degen:>9} {r['epochs_run']:>8}{r['note']}{mark}")
    if any_degenerate:
        print("  ⚠ = 這個解的中間棒有 Δv≈0 的空燒，實際上等於更少棒的方案——"
              "它跟低燃燒次數方案的分數差異多半是雜訊，不是多棒優勢。")


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

    # 開掃之前先用能量下限剔掉「物理上不可能合法」的燃燒次數 (2026-08-15 加)。
    # 這是封閉解、微秒等級，但可以省下實打實的搜尋時間：如果 B 光是把軌道撐到碰得到 A
    # 就需要超過「棒數 × 每棒上限」的 Δv，那個案例注定只能找到違規解，掃它純粹浪費。
    # 更完整的可行性分析 (合法解有多稀有、多棒構造存不存在) 用 feasibility.py。
    probe_cfg = copy.deepcopy(config)
    probe_cfg["optimization"]["MAX_BURNS"] = [max(burns_range)]
    floor_mps = MissionOptimizer(probe_cfg).energy_floor_dv() * 1000.0
    if floor_mps > 0:
        cap_mps = float(config["rules"]["MAX_DV_MPS"])
        min_burns = math.ceil(floor_mps / cap_mps)
        dropped = [b for b in burns_range if b < min_burns]
        if dropped:
            kept = [b for b in burns_range if b >= min_burns]
            if not kept:
                print(f"❌ 能量下限 {floor_mps:,.0f} m/s 代表至少要 {min_burns} 棒，"
                      f"但 --burns 給的範圍 {burns_range} 全部低於這個下限——"
                      f"整個範圍都不可能有合法解，請往上調 (例如 --burns {min_burns}-{min_burns+3})。")
                sys.exit(1)
            print(f"ℹ️ 能量下限 {floor_mps:,.0f} m/s（每棒上限 {cap_mps:,.0f}）→ 至少需要 {min_burns} 棒；"
                  f"已從掃描範圍剔除 {dropped}（注定違規，掃了浪費時間）。")
            burns_range = kept

    # --- 第一階段：粗掃 ---
    # MAXITER 不是整個範圍套同一個數字，而是依決策變數維度分配 (見 scaled_coarse_iters
    # 的說明)——不然維度低的燃燒次數 (例如 1) 早早收斂，維度高的 (例如 8) 同樣代數還
    # 沒收斂完，粗掃出來的分數排序會系統性冤枉高燃燒次數。
    coarse_iters_map = scaled_coarse_iters(burns_range, args.coarse_iters, max_iters=args.coarse_iters_cap)
    coarse_results = run_stage(
        config, burns_range, coarse_iters_map, popsize=args.coarse_popsize, label="第一階段：粗掃"
    )
    print_score_table(coarse_results, "粗掃結果 (MAXITER 依維度縮放調低，數字僅供參考，不是最終結論)")

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
            # 2026-08-15：分數有差異不代表真的用到了多棒。實測過好幾次「贏家是多棒
            # 但中間棒 Δv=0」的情況——那種分數差異來自別的地方 (例如落在窄窗的位置、
            # 瞄準偏移找到不同的權衡點)，不是多棒本身的貢獻，照著建議把 MAX_BURNS
            # 開大只會浪費搜尋時間。這裡明講，不要讓使用者誤讀成「這個情境需要多棒」。
            best_eff = effective_burns(best_k, fine_results[best_k].get("best_x"))
            if best_eff < best_k:
                print(f"\n⚠️  但要注意：{best_k} 棒這個贏家**實際上只用到 {best_eff} 棒**"
                      f"（中間棒 Δv≈0 的空燒）。也就是說它跟 {best_eff} 棒方案本質上是"
                      f"同一個解，分數差異來自別的自由度而不是多棒策略——"
                      f"這個情境很可能 {best_eff} 棒就夠了，先用 MAX_BURNS=[{best_eff}] "
                      f"跑一次對照過再決定要不要真的開到 {best_k}。")
            else:
                print(f"（{best_k} 棒這個解的每一棒都有實際燃燒，是真的用到了多棒。）")

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
