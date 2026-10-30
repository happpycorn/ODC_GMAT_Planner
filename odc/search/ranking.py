"""提供任務分層排名、平手判定與 REVS 候選挑選
主要入口為 tiebreak_rank_key、_mission_rank_key。
"""


# ── 規則第 6 節：平手判定 ─────────────────────────────────────────────────
# 官方規則 (Regulations_PrelimRound §6 Tie-Breaking Rules) 寫得很明確：
#   優先序 1  Δr_min (Minimum Relative Distance)   小者排前面
#   優先序 2  ΔV_team (Total Velocity Increment)   少者排前面
#   優先序 3  T_team  (Mission Completion Time)    短者排前面
#   優先序 4  設計理論 —— 同分隊伍上台講 5 分鐘軌道設計方法論 (程式管不到)
# 也就是說「分數一樣」時決定名次的不是 Score，工具挑方案時就必須照這個順序挑。

# 兩個分數算不算「打平」的門檻。預設取極小 (1e-9)：官方會用自己的驗證程式重算
# 分數，我們無從得知他們比到第幾位，預設只在浮點數等級真的一模一樣時才動用平手規則。
#
# 但這個門檻有實測上的理由可以調大 (strategy.TIEBREAK_SCORE_EPS)：實測 playground
# 情境，瞄準偏移從 0 拉到 3.5km (規則允許的極限) 對分數的影響只有 **0.001 分**，
# 遠小於搜尋本身的重跑變異 (~0.02 分)。也就是說工具預設會為了 0.001 分白白讓出
# 3.5km 的距離優勢——而規則第 6 節的優先序 1 是**硬性**的字典序比較，3.5km 輸給
# 0km 沒有商量餘地。如果官方的驗證程式把分數四捨五入到小數點後兩位 (我們不知道)，
# 那 0.001 分根本不存在，這筆交易就是純虧。
#
# 所以：想賭「官方比到小數點後兩位」就把它設成 0.005，工具會在分數差 0.005 以內
# 時改以 Δr 為準；想保守就維持預設。這是個賭注，工具不替你決定，但把數量級講清楚。
SCORE_TIE_EPS = 1e-9

# 比 Δr_min 時的有效解析度（公尺）。低於這個量級的差距不是優勢，是雜訊：
#   * GMAT DifferentialCorrector 的 Achieve Tolerance 是每軸 0.01 km = 10 m，
#     Python 端算出 1 公分的差距根本傳不到交出去的腳本裡；
#   * 而且本專案實測過 Python 模型與 GMAT 的殘餘落差最大到 863 m（見
#     MISS_TOLERANCE_SOFT 那段的說明），比 10 m 大兩個數量級。
# 不做這個量化的話會發生實測看過的荒謬情況：兩個方案的 Δr 差 1 公分，工具就為此
# 選了棒數比較多、而且多出來那棒是 Δv≈0 空燒的版本——多開的棒數在 GMAT 只會增加
# 不收斂的風險，換來一個根本不存在的距離優勢。
# 只量化 Δr、不量化 ΔV_team/T_team：後兩者是計分函式**直接**在最佳化的量，搜尋
# 交出來的值有意義；Δr 則因為計分被 max(Δr, 5) 地板夾住，在 5km 內對分數毫無梯度，
# 搜尋會把它留在任意位置——只有這一項會出現「數字有差但差距沒有意義」的狀況。
TIEBREAK_MISS_RESOLUTION_M = 10.0


def tiebreak_rank_key(score: float, miss_km: float, dv_mps: float, t_team: float,
                      floor_miss: bool = False, eps: float = None) -> tuple:
    """規則第 6 節的排名鍵，數值越小排越前面 (跟 mealpy 的 min 方向一致)。

    floor_miss 對應規則本身的一個歧義，兩種讀法都說得通，而且會給出不同的贏家：

      floor_miss=False (預設)：優先序 1 比**原始**最近距離。
          理由是規則第 6 節用的符號是 d_min,team，跟第 4/5 節計分用的 Δr_min 不同，
          而且官方把它列在優先序 1 —— 如果套第 4 節的 max(Δr, 5) 地板，所有成功
          攔截的隊伍這一項全都等於 5，優先序 1 對「成功組」就完全失效了。

      floor_miss=True：優先序 1 直接沿用第 4 節定義的 Δr_min = max(Δr(T_team), 5)。
          這個讀法下優先序 1 只能分出**沒攔截成功**的隊伍 (Δr > 5 但分數都被壓到 0)，
          成功組會直接落到優先序 2 比 ΔV_team。

    規則沒有講清楚是哪一種，所以工具不替你決定：兩種讀法選出不同贏家時 run_study()
    會明講，讓人自己看數字定案。這比偷偷選一種然後假裝沒有歧義誠實。
    """
    dr = max(miss_km, 5.0) if floor_miss else miss_km
    # 量化到 GMAT 打靶真的分辨得出來的解析度，見 TIEBREAK_MISS_RESOLUTION_M
    dr = round(dr * 1000.0 / TIEBREAK_MISS_RESOLUTION_M)
    # 分數先量化再比，浮點數尾巴的雜訊不該被當成真實差距。eps 可以由設定檔調大
    # (strategy.TIEBREAK_SCORE_EPS)，見 SCORE_TIE_EPS 的說明。
    e = SCORE_TIE_EPS if eps is None else max(float(eps), 1e-12)
    return (-round(score / e), dr, dv_mps, t_team)


def over_dv_count(mission_info) -> int:
    """單棒超標的棒數 (失格條件)。2026-10-19 之前的存檔沒有 over_dv_count，那時的
    penalty_count 就是單棒超標次數 (間隔違規在參數化下不會發生)，退回讀它。"""
    return int(mission_info.get("over_dv_count", mission_info.get("penalty_count", 0)) or 0)


def is_disqualified(mission_info) -> bool:
    """最終交件判定是否失格 (單棒或總 Δv 超標；Earth-safe 另外有閘門)。舊存檔沒有
    disqualified 欄位時，用單棒超標推回來 (舊存檔沒有總 Δv 上限)。"""
    if "disqualified" in mission_info:
        return bool(mission_info["disqualified"])
    return over_dv_count(mission_info) > 0


def mission_rank_score(mission_info, split_est=False):
    """挑贏家用的分數：split_est=True (SPLIT_AWARE_TERMINAL 開) 時用拆後估計
    score_split_est，否則用真實分數。舊的 mission_info 沒有這個欄位就退回 score。"""
    if split_est:
        return float(mission_info.get("score_split_est", mission_info["score"]))
    return float(mission_info["score"])


def _mission_rank_key(mission_info, floor_miss=False, eps=None, split_est=False):
    """把 refine_trajectory 交回的 mission_info 轉成規則第 6 節的排名鍵（越小越前面）。
    欄位對照：score / miss_km(Δr_min) / total_dv_mps(ΔV_team) / T_team。
    split_est=True 時 score 換成拆後估計（C4，見 mission_rank_score）。"""
    return tiebreak_rank_key(
        mission_rank_score(mission_info, split_est), float(mission_info["miss_km"]),
        float(mission_info["total_dv_mps"]), float(mission_info["T_team"]),
        floor_miss=floor_miss, eps=eps)


def pick_best_across_revs(candidates, eps=None, split_est=False):
    """從多趟 run_study() 的結果裡照規則第 6 節挑一趟交出去。

    candidates: 依序 [(revs, burns, times, mission_info), ...]。成功的那趟 burns/times
      不是 None 且 mission_info 是 dict；run_study() 全軍覆沒時回傳的是
      (None, None, (None, None))，這裡當失敗略過。

    回傳 (index, floor_disagrees)：index 是選中的候選在 candidates 裡的位置；
    floor_disagrees 標記規則第 6 節優先序 1 的另一種讀法（floor_miss=True，見
    tiebreak_rank_key）會不會選出不同的贏家——會的話交給呼叫端講白，不偷偷替
    使用者決定。全部失敗時 index 指向最後一趟（讓呼叫端照樣回傳那個失敗結果）。

    獨立成純函式是為了可測試：真的各跑一趟 REVS 太貴，這段的重點「兩趟成績誰勝出」
    餵假 mission_info 就驗得到（見 tests/test_tiebreak.py）。
    """
    def ok(c):
        _, burns, times, mi = c
        return burns is not None and times is not None and isinstance(mi, dict)

    viable = [i for i, c in enumerate(candidates) if ok(c)]
    if not viable:
        return len(candidates) - 1, False

    best = min(viable, key=lambda i: _mission_rank_key(candidates[i][3], eps=eps,
                                                       split_est=split_est))
    alt = min(viable, key=lambda i: _mission_rank_key(candidates[i][3], floor_miss=True, eps=eps,
                                                      split_est=split_est))
    return best, (alt != best)
