"""組合候選種子與任務評估，保留搜尋及精修流程
主要入口為 MissionOptimizer。
"""
# 此模組負責任務路線搜尋、精修與重播。
# 主要入口為 MissionOptimizer，計算本體沿用原實作。


import os
import math
import logging
import numpy as np
import concurrent.futures
import multiprocessing
import queue
import threading
import time
from typing import Tuple
from scipy.optimize import minimize
from mealpy import FloatVar
from mealpy.evolutionary_based.SHADE import L_SHADE
from odc.physics.propagator import get_r0_v0
from odc.scoring.scorer import (calculate_score, ranked_search_score, assess_legality,
                        SEARCH_FAIL_SCORE_RANKED, DV_LIMIT_TOL_MPS)
from odc.physics.core_math import (propagate_dop853, check_constraints, fast_norm,
                           to_vnb_frame, reaches_perigee, lambert_izzo,
                           izzo_max_revs, ephem_state, build_ephem_table, fixed_orbit_state,
                           build_wait_prefix, cached_wait_min_radius, arc_radius_from_end,
                           initial_wait_min_radius)
from odc.runlog import log, is_verbose
from tqdm import tqdm
from odc.search.fitness import PRELIM_TERMINAL_MAX_FACTOR, SPLITTER_MAX_SEG, _DeadlineFitness, _PrimerSearchTimeout, decision_variable_dims, effective_burns, fast_fitness_evaluator
from odc.search.mission_eval import MissionEvalMixin
from odc.search.ranking import SCORE_TIE_EPS, is_disqualified, mission_rank_score, tiebreak_rank_key
from odc.search.seeds import SeedCandidatesMixin


class MissionOptimizer(SeedCandidatesMixin, MissionEvalMixin):
    def __init__(self, config):
        self.config = config
        # run_study() 跑完後，這裡會存每個 MAX_BURNS 案例的 (raw_fitness, epochs_run, note)，
        # 不只是最終贏家——sweep_burns.py 用這個畫「燃燒次數 vs 分數」的趨勢表。
        # main.py 的正常流程不需要這個，只是額外多存一份，不影響 run_study() 原本的回傳值。
        self.burn_case_results: dict = {}
        # 這趟 run_study() 的「大塊報告」(🚀 開跑行、任務規劃表、Python 預測、✅完成、
        # 平手/proxy 診斷) 要用哪個 log 層級印。單跑時 = INFO (直接顯示)；REVS 集成時
        # run_study_over_revs 會把每趟壓成 DEBUG，只在最後把勝出那趟的報告以 INFO 重印
        # 一次，避免 console 上同一份報告印兩遍 (見 run_study_over_revs)。
        self._report_level = logging.INFO
        # config 分兩塊環境設定：rules (主辦方規定/公告，我們不能改) 跟 strategy
        # (我們自己的任務設計選項，不是規則要求)。詳見 main.py 的 DEFAULT_CONFIG 註解。
        rules = config["rules"]
        strategy = config.get("strategy", {})
        self.SEARCH_COAST_RTOL = float(strategy.get("SEARCH_COAST_RTOL", 1e-12))

        # 從 config 提取環境常數 (避免每次呼叫都查字典)
        self.k_t = rules.get("k_t", 0.0001)
        self.C_t = rules.get("C_t", 11000.0)
        self.k_v = rules.get("k_v", 0.005)
        self.C_v = rules.get("C_v", 1200.0)

        # 物理常數與限制
        self.MU = 398600.4418          # 地球標準重力參數
        # GRAVITY_DEGREE：重力場模型要算到第幾階 zonal harmonic，不確定哪一輪/哪個
        # 場景實際會開多少階擾動時用 config 切換，不用改程式碼 (2026-08-14 從原本的
        # USE_J2 布林值換成這個，因為比賽當天用的重力場設定不一定跟我們現在假設的
        # 一樣，開放成可調的階數比單純 on/off 更貼近實際情況)。
        # 0 = 純點質量, 2 = J2 (原本 USE_J2=true 的行為), 3 = J2+J3, 4 = J2+J3+J4。
        # J2/J3/J4 三個係數直接從 GMAT 用的同一份 JGM2.cof 重力場檔案反算，跟 GMAT
        # 端 (script_generator 的 gravity_degree 參數) 用同一組數字、同步切換——
        # GMAT 那邊 Order 固定收在 0 (只算 zonal 不算 tesseral)，確保兩邊算的是
        # 完全一樣的物理模型，不會再有「GMAT 有 J3/J4 但 Python 沒有」的落差。
        self.GRAVITY_DEGREE = int(strategy.get("GRAVITY_DEGREE", 2))
        self.J2_VAL = 1.08262668e-3 if self.GRAVITY_DEGREE >= 2 else 0.0
        self.J3_VAL = -2.5323078e-6 if self.GRAVITY_DEGREE >= 3 else 0.0
        self.J4_VAL = -1.62042999e-6 if self.GRAVITY_DEGREE >= 4 else 0.0
        self.RE_VAL = 6378.137
        self.MIN_PERIAPSIS = self.RE_VAL + 100.0
        # ΔV_lim、機動間隔下限、T_max 的週期倍數：這三個是規則規定的數字 (初賽規則
        # 第 2、3 節：ΔV_lim=1500 m/s、間隔≥100s、T_max=4×T_A)，放進 config["rules"]
        # 跟 k_t/C_t/k_v/C_v 放一起，不寫死在程式碼裡——如果晉級賽的規則數字不一樣，
        # 改 config 就好，不用回來改這裡。預設值等於目前初賽規則的數字。
        self.MAX_DV = float(rules.get("MAX_DV_MPS", 1500.0)) / 1000.0  # 換算成 km/s，下面全部用 km/s
        # 搜尋/微調階段用的「內部目標」比規則的真實上限更嚴一點 (預設留 10 m/s 安全
        # 邊界)，避免 NLP 微調的數值梯度在邊界上把解推過真正的 ΔV_lim 那一側才被扣分。
        # 最終回報/合規判定 (_replay_mission) 仍然用 self.MAX_DV 這個真實規則上限去算。
        #
        # 2026-08-29：預設從 10 改成 2。理由是結構性的——最佳解如果是「把一發大燒拆成
        # 兩段」（繞過 ΔV_lim 的標準手法），就會有棒數**頂到上限**，那時邊界多少就是
        # 直接損失多少。官方範例題目實測第一棒 1,490.0 -> 1,498.0，白賺 8 m/s。
        #
        # 實測（四組會頂到上限的情境，固定 SEED=777，margin = 10 / 2 / 0.5）：
        #   official_sample  90.21 / 90.21 / 90.43
        #   perigee_kick     89.28 / 89.28 / 89.28
        #   hard_mode        92.30 / 92.44 / 86.43
        #   lateral_burn     96.26 / 96.32 / 96.17
        #   -> 三個設定**違規次數全部是 0**，縮小邊界沒有讓 NLP 把解推過真正的 1500。
        #   -> 分數總和 368.05 / 368.25 / 363.31。但分數差落在重跑變異帶內，
        #      **不是**改預設的理由；理由是上面那個「頂到上限就直接損失」的結構事實。
        #   -> 0.5 在 hard_mode 掉 6 分（改邊界會改變搜尋空間的縮放，落到不同盆地），
        #      所以不要一路壓到 0。2 是有收益又不動到搜尋行為的點。
        self.MAX_DV_MARGIN_MPS = max(0.0, float(strategy.get("MAX_DV_MARGIN_MPS", 2.0)))
        self.MAX_DV_SOFT = max(0.0, self.MAX_DV - self.MAX_DV_MARGIN_MPS / 1000.0)
        self.MIN_COAST_TIME = float(rules.get("MIN_MANEUVER_INTERVAL_SEC", 100.0))
        # 總 Δv 上限 (排位賽規則：≤ 3 km/s，超過失格)。選填，沒填 / null = 沒有上限 (初賽行為)。
        # 搜尋時是軟懲罰 (fast_fitness_evaluator 索引 19)，最終判定 (assess_legality) 是失格。
        _tot = rules.get("MAX_TOTAL_DV_MPS")
        self.MAX_TOTAL_DV_MPS = None if _tot is None else float(_tot)

        # 拆棒感知搜尋 (2026-09-11, HAP-67；預設關，關掉時下面全部等同舊行為)。
        # 動機：規則只管「每次機動 ΔV ≤ 上限」，不管「軌道節點的總衝量」。一發 2500 m/s
        # 的中間棒不是 infeasible——它可以拆成 2×1250、間隔 ≥100s，每段合法、零違規
        # (見 docs 的 burn-split 方法與 HAP-47 joint-NLP 拆分器)。但舊版用 bounds 把中間棒
        # 的 dv_r 硬夾在 MAX_DV_SOFT，等於把「需要大衝量、靠拆棒實現」的整族解從搜尋空間
        # 切掉。開這個旗標且 SPLIT_LEADING 可用時：(1) _generate_bounds 放寬中間棒上界；
        # (2) 可拆前導棒預付 ΔV overhead，與重播的拆後估計相同。拆棒器固定抵達時刻，
        # 所以不另加任務時間；間隔可行性與拆後軌跡安全仍須實拆驗證。未開 SPLIT_LEADING
        # （primer 重搜單開 SEARCH）時保留舊算法：只推進時鐘、預付 overhead，已知不同尺。
        self.SPLIT_AWARE_SEARCH = bool(strategy.get("SPLIT_AWARE_SEARCH", False))
        self.SPLIT_AWARE_MAX_FACTOR = max(1, int(strategy.get("SPLIT_AWARE_MAX_FACTOR", 3)))
        self.SPLIT_AWARE_DV_OVERHEAD = max(1.0, float(strategy.get("SPLIT_AWARE_DV_OVERHEAD", 1.02)))
        # 搜尋後的 route-first 合法化開關。main.py 真正執行拆棒時仍以同一個 config 值
        # 為準；optimizer 也保存一份，讓 preflight 能正確解讀「低於直接合法棒數」的案例：
        # 開啟時它們不是該刪的浪費，而是刻意保留給後處理拆棒的路線候選。
        self.AUTO_SPLIT_LEGALIZE = bool(strategy.get("AUTO_SPLIT_LEGALIZE", True))
        # 前導棒等分只在實際會拆棒時生效；可拆上限對齊搜尋端的 hard_cap。
        self.SPLIT_LEADING = bool(strategy.get("SPLIT_LEADING", False)) and self.AUTO_SPLIT_LEGALIZE
        self.LEADING_SPLIT_LIMIT = self.SPLIT_AWARE_MAX_FACTOR * self.MAX_DV
        # 終端棒拆後估計 (C4, 2026-09-24；見 docs/research/C4_TERMINAL_SPLIT_AWARE_PLAN.md)。
        # 開啟時：(1) fast_fitness_evaluator 對超標但 ≤ K×cap 的終端棒不扣 10 分，改預付
        # 拆棒燃料；(2) 各棒數案例 / REVS 集成 / C2 挑贏家改比 score_split_est (拆後估計)。
        # 只在 AUTO_SPLIT_LEGALIZE 也開時生效——不會拆，就不能拿拆後分數當尺。
        # 2026-09-25 起預設開（E1–E4 通過、拆棒器攝動 shooting、退路重搜；見計劃書 §6.5–6.7）。
        self.SPLIT_AWARE_TERMINAL = (bool(strategy.get("SPLIT_AWARE_TERMINAL", True))
                                     and self.AUTO_SPLIT_LEGALIZE)
        # 可拆上限倍數 K：終端棒 ≤ K × MAX_DV_SOFT 算「拆棒器拆得掉」。排位賽模式 (有總 Δv 上限)
        # 預設 = 拆棒器最大段數 SPLITTER_MAX_SEG (250 m/s 時 14 × 248 = 3,472 m/s；舊的固定 5 倍
        # 只有 1,240 m/s，把拆得掉的路線當成不可拆，見 docs/research/RANKING_MC_20261019.md)。初賽模式維持
        # 5 倍 (逐位元同舊行為)。config 有寫就照 config。
        self.RANKING_RULES = self.MAX_TOTAL_DV_MPS is not None
        self.SPLIT_AWARE_TERMINAL_MAX_FACTOR = max(1.0, float(strategy.get(
            "SPLIT_AWARE_TERMINAL_MAX_FACTOR",
            float(SPLITTER_MAX_SEG) if self.RANKING_RULES else PRELIM_TERMINAL_MAX_FACTOR)))
        # 拆棒器能處理的單棒上限 (km/s)。排位賽模式下終端棒超過它、或前導棒超過 MAX_DV_SOFT，
        # 搜尋分數進失格層 (scorer.ranked_search_score)；不拆棒 (AUTO_SPLIT_LEGALIZE 關) 時任何
        # 超標都拆不掉。初賽模式不用這個值 (超標照舊每棒 −10)。
        self.SPLIT_LIMIT = (self.SPLIT_AWARE_TERMINAL_MAX_FACTOR * self.MAX_DV_SOFT
                            if self.AUTO_SPLIT_LEGALIZE else self.MAX_DV_SOFT)
        self.SPLIT_AWARE_TERMINAL_DV_OVERHEAD = max(
            1.0, float(strategy.get("SPLIT_AWARE_TERMINAL_DV_OVERHEAD", 1.0)))
        # 2.3 退路：旗標開、贏家帶可拆終端違規時，run_study 記下「真實分數最高的零違規
        # 候選」(未精修)，拆棒失敗時 main 改交它。見 _pick_best_case / main._legalize_stage。
        self.legal_backup = None
        # 排位賽模式下所有棒數案例都在失格層時，_pick_best_case 記下最接近合法的那個
        # ({"burns", "x", "fitness"})，main 存成 no_legal_route.json 給人檢查 (不產生腳本)。
        self.no_legal_route = None

        # 攔截容許範圍：規則只要求 Δr ≤ 這個值，超出的精準度不會多加分 (Δr_min 會被
        # 地板夾住)，開放讓最後一棒 Lambert 瞄準這個球內最省油的點，而不是死盯著 A
        # 的精確位置。設成彈性可調，戰況緊繃時可以縮小 (甚至設 0 退回精準瞄準)。
        #
        # 內部再留 1.5km 的安全邊界 (MISS_TOLERANCE_SOFT)。理由：GMAT 打靶的 Achieve
        # Tolerance 每軸 0.01km，理論最差合起來只有 ~17m，但實測跨多種軌道幾何做壓力
        # 測試後發現，J2 以外的殘餘模型落差不是穩定的幾十公分等級——SMA 差距懸殊
        # (例如 LEO 對到接近 GEO 高度) 的情境實測落差衝到 863m。1.5km 比目前觀察到
        # 的最大落差多留將近一倍緩衝，犧牲一點理論上可榨出的省油空間換安全感。
        # 這仍然是「目前測過的情境」歸納出來的經驗值，不是嚴謹上界，正式測資公布後
        # 拿到真實軌道參數，最好針對那組實際場景再測一次確認這個邊界仍然夠用。
        self.MISS_TOLERANCE_KM = max(0.0, min(5.0, float(strategy.get("MISS_TOLERANCE_KM", 5.0))))
        self.MISS_TOLERANCE_SOFT = max(0.0, self.MISS_TOLERANCE_KM - 1.5)

        # 規則第 6 節優先序 1 的收尾微調 (見 _tiebreak_polish)：在分數一分都不少的
        # 前提下把瞄準偏移壓小。預設開啟，代價是精修階段多跑一次 L-BFGS-B (上限 30
        # 代)；很貴的情境想省這段時間就設 false。
        self.TIEBREAK_POLISH = bool(strategy.get("TIEBREAK_POLISH", True))

        # HAP-47：joint NLP 拆分器精修家族的開關 (見 _generate_nlp_refined_seed_candidates)。
        # 對既有種子 (relay/ladder/pcsplit) 做一次帶顯式不等式約束 (近地點餘裕/命中容許/
        # Lambert DC 收斂) 的 SLSQP 局部聯合優化——跟後面本來就會跑的 L-BFGS-B 精修不同：
        # L-BFGS-B 只有 box bounds，近地點違規靠 fitness 裡的懲罰擋 (階梯函數、沒有連續
        # 梯度)，貼不了邊界；SLSQP 有連續的近地點餘裕當約束，才找得到「幾棒貼滿上限、
        # 一棒省下來」這種貼邊解 (HAP47_SPLIT_ALGORITHM_RESEARCH.md §7.1 GMAT 驗證過確實
        # 比 split_even 均分多省一點)。預設開；沒經過大規模場景驗證，留關掉的口子。
        self.ENABLE_NLP_SPLIT_REFINE = bool(strategy.get("ENABLE_NLP_SPLIT_REFINE", True))
        # 每個棒數案例 DE 跑完後，對每顆種子再單獨跑一次 L-BFGS-B (見 _optimize_burn_case)。
        # 跟上面的 SLSQP 部分重疊 (審計 P4)，留開關給消融用；預設開 = 舊行為。
        self.SEED_LBFGS_POLISH = bool(strategy.get("SEED_LBFGS_POLISH", True))

        # 最後一棒 Lambert 要考慮的最大圈數。規則的 T_max = 4 x A 的週期，所以最多
        # 也就塞得下約 4 圈，預設就取 4（2026-08-29 從 0 改過來）。
        #
        # 為什麼**單點評估**可以放心開：分支選擇是在**固定的 t_final_leg** 下取需求
        # Δv 最小的那條，同一個決策向量的抵達時間不變、時間分不變，只是燃料可能更
        # 便宜。也就是說，對同一個決策向量而言，開多圈是嚴格更大的搜尋空間，不可能
        # 讓那一點的分數變差。
        #
        # 實測（2026-08-29）：
        #   官方範例題目（同 SEED=42，只差這個開關）：Score 90.21 -> 90.43
        #   known_planechange：84.7 -> 62.4 m/s（省 26%，而且正好命中閉合構造解）
        #   known_phasing（MAX_BURNS=[1]）：1,490.0 -> 70.6 m/s（省 21 倍——那條轉移
        #     繞了約 4 圈，M=0 根本表達不出來）
        # 成本：每次評估 REVS=4 對 REVS=0 是 1.01 倍（飛行時間不夠繞圈時 izzo 直接
        # 失敗、退出得很快），端到端跑完的總時間量不出差異。
        # 分支本身經 ESA pykep 交叉驗證，1,552 條解最大偏差 5.2e-14 km/s（見
        # scripts/research/xcheck_lambert_pykep.py）。
        #
        # ⚠️ 但這個「不可能變差」只在**單點評估**成立，不能推廣到「開多圈的搜尋結果
        # 不可能變差」（HAP-42，2026-09-03）：L-SHADE 是隨機搜尋，多圈把適應度地形
        # 變複雜（多出 local optima），族群可能收斂到不同、且最終精修分數更差的
        # 盆地——同 SEED 下 REVS=4 的最佳解實測比 REVS=0 少 1.45 分，完整 600 代救不
        # 回（scripts/research/monotonicity_harness.py），porkchop 對拍又獨立
        # 看到 3/8 幾何 REVS=0 贏 REVS=4。**per-point dominance ≠ 搜尋結果 dominance。**
        # 這個脆弱性的實際因應是 `run_study_over_revs`／`REVS_ENSEMBLE`（預設開）：
        # 同 SEED 各跑 REVS=0 與這裡設的值，取兩者較好的，見該函式開頭的說明。
        #
        # 設 0 可以退回 2026-08-28 之前的行為（也讓 REVS_ENSEMBLE 自動退成單跑）。
        self.LAMBERT_MAX_REVS = max(0, int(strategy.get("LAMBERT_MAX_REVS", 4)))

        # 「分數算不算打平」的門檻，見 SCORE_TIE_EPS 的說明。預設 1e-9 (只認浮點數
        # 等級的完全相同)，調大等於賭官方比分數時會四捨五入。
        self.TIEBREAK_SCORE_EPS = max(1e-12, float(strategy.get("TIEBREAK_SCORE_EPS",
                                                                SCORE_TIE_EPS)))

        # 初始化軌道
        self.A_r0, self.A_v0 = get_r0_v0(
            config["orbit_A"]["SMA"], config["orbit_A"]["ECC"], config["orbit_A"]["INC"],
            config["orbit_A"]["RAAN"], config["orbit_A"]["AOP"], config["orbit_A"]["TA"]
        )
        self.B_r0, self.B_v0 = get_r0_v0(
            config["orbit_B"]["SMA"], config["orbit_B"]["ECC"], config["orbit_B"]["INC"],
            config["orbit_B"]["RAAN"], config["orbit_B"]["AOP"], config["orbit_B"]["TA"]
        )
        
        # 演算法設定
        self.burns = config["optimization"]["MAX_BURNS"]
        # MAXITER 通常是單一整數 (所有燃燒次數案例共用同一個世代預算)，但也接受
        # {燃燒次數: 世代數} 字典——sweep_burns.py 的粗掃階段用這個依決策變數維度
        # 分配公平預算 (見 _maxiter_for 的說明)。一般手寫 config 幾乎不會用到字典
        # 形式，這裡不強制轉型，交給 _maxiter_for 統一處理兩種情況。
        self.maxiter = config["optimization"]["MAXITER"]
        self.popsize = config["optimization"]["POPSIZE"]
        self.num_threads = config["optimization"]["NUM_THREADS"]
        self.mes = config["optimization"]["MAX_EARLY_STOP"]
        self.tol = config["optimization"]["TOL"]
        # 預設跑滿 MAXITER，維持既有搜尋行為；只有明確啟用才套用早停條件。
        self.early_stop_enabled = config["optimization"].get("EARLY_STOP_ENABLED", False)
        # 固定隨機種子讓同一組設定可以重現一樣的結果，方便比較「改了東西到底有沒有用」。
        # 不設 (null/None) 就維持每次隨機，想探索不同解可以拿掉這個欄位。
        self.seed = config["optimization"].get("SEED")

        # C2（2026-09-22）：外部注入的搜尋種子 {燃燒次數: [決策向量, ...]}，預設空。
        # primer 診斷贏家判定 add-node 時，main._primer_guided_research 把「該加節點」
        # 翻成一顆插棒種子塞進來（見 primer.insert_node_seed），保證它一定進初始族群。
        # 是 numpy 陣列的純資料 dict，spawn 到子行程時隨 self 一起 pickle，跨行程沒問題。
        self.external_seeds = {}
        # Oracle seeds never activate primer fast mode or its deadline.
        self.oracle_seeds = {}

        # 計算時間上限 (T_max = T_MAX_PERIOD_MULTIPLE × A 的軌道週期，見上面的說明)。
        # 這個公式只在 A 是橢圓/圓軌道 (SMA>0, ECC<1，初賽) 時有意義——A 是雙曲線
        # 軌道 (SMA<0, ECC>1，排位賽) 時沒有週期可言，這裡直接對負數開根號會炸掉
        # (NaN/複數)。排位賽的 T_max 定義方式官方目前還沒公告，所以這裡不猜公式，
        # 改成要求 config 用 rules.T_MAX_SEC 直接指定秒數覆寫——公告後不管公式是
        # 什麼，把算出來的秒數填進 config 就好，不用等程式碼跟著改。
        a_sma = config["orbit_A"]["SMA"]
        ecc_A = config["orbit_A"]["ECC"]
        t_max_override = rules.get("T_MAX_SEC")
        is_hyperbolic_A = a_sma <= 0 or ecc_A >= 1.0
        if t_max_override is not None:
            self.Ta_sec = None  # 雙曲線/覆寫情境下「A 的週期」沒有意義，不計算
            self.T_max = float(t_max_override)
        elif is_hyperbolic_A:
            raise ValueError(
                "orbit_A 是雙曲線/拋物線軌道 (SMA<=0 或 ECC>=1)，沒有軌道週期，"
                "T_max 不能用 4×週期公式推算 (這是排位賽場景，見 STATUS.md)。"
                "請在 config 的 rules.T_MAX_SEC 直接指定官方公告的 T_max 秒數。"
            )
        else:
            self.Ta_sec = 2.0 * np.pi * np.sqrt(a_sma**3 / self.MU)
            self.T_max = float(rules.get("T_MAX_PERIOD_MULTIPLE", 4.0)) * self.Ta_sec
    
        self.EPHEM_CACHE = bool(strategy.get("EPHEM_CACHE", True))
        self.EPHEM_CACHE_STEP_SEC = float(strategy.get("EPHEM_CACHE_STEP_SEC", 60.0))
        if not math.isfinite(self.EPHEM_CACHE_STEP_SEC) or self.EPHEM_CACHE_STEP_SEC <= 0.0:
            raise ValueError("strategy.EPHEM_CACHE_STEP_SEC 必須是有限的正數")
        self.ephem = None
        self.ephem_build_seconds = 0.0
        if self.EPHEM_CACHE:
            # NLP: t0<=T_max，每個 coast<=T_max；貼 cap 的前導棒最多各補一空位。
            # N<=2*(max_burns-1)+SPLITTER_MAX_SEG，故 (N+1)*T_max 涵蓋所有試探。
            # 多留一步給有限差分；另涵蓋搜尋在 T_max 後被迫加的最短滑行。
            max_burns = max(self.burns)
            self.ephem_end_time = max(
                (2*(max_burns - 1) + SPLITTER_MAX_SEG + 1)*self.T_max,
                self.T_max + max_burns*self.MIN_COAST_TIME
            ) + self.EPHEM_CACHE_STEP_SEC
            started = time.perf_counter()
            args = (self.EPHEM_CACHE_STEP_SEC, self.ephem_end_time,
                    self.MU, self.J2_VAL, self.J3_VAL, self.J4_VAL, self.RE_VAL)
            self.ephem = (self.EPHEM_CACHE_STEP_SEC,
                          build_ephem_table(self.A_r0, self.A_v0, *args),
                          build_ephem_table(self.B_r0, self.B_v0, *args))
            self.ephem += (build_wait_prefix(self.ephem[2], self.ephem[0], self.MU),)
            self.ephem_build_seconds = time.perf_counter() - started
        self._vectors = np.vstack([self.A_r0, self.A_v0, self.B_r0, self.B_v0]
                                  + ([] if self.ephem is None else list(self.ephem[1:])))

    def state_A(self, t):
        return fixed_orbit_state(self.A_r0, self.A_v0, t, self.MU, self.J2_VAL,
                                 self.J3_VAL, self.J4_VAL, self.RE_VAL, self.ephem, 0)

    def state_B(self, t):
        """B 第一棒之前的初始軌道狀態。"""
        return fixed_orbit_state(self.B_r0, self.B_v0, t, self.MU, self.J2_VAL,
                                 self.J3_VAL, self.J4_VAL, self.RE_VAL, self.ephem, 1)

    def _vector_params(self):
        # 旋轉不變性等呼叫端會暫換初始狀態；這時既有表不適用，四列佈局使 evaluator
        # 自動走原本的直接傳播。正常搜尋只回傳已打包好的陣列，不複製整張表。
        initial = (self.A_r0, self.A_v0, self.B_r0, self.B_v0)
        if not all(np.array_equal(state, self._vectors[i]) for i, state in enumerate(initial)):
            return np.vstack(initial)
        return self._vectors

    def _generate_bounds(self, num_burns: int) -> Tuple[list, list]:
        """
        產生純陣列的上下界。中間燃燒用球座標 (r, theta, phi, coast_frac) 參數化：
        r (Δv 大小) 直接夾在 [0, MAX_DV_SOFT]，theta/phi 決定方向，天生 100% 落在
        合規球內，不像舊版的立方體邊界 (xyz 各自 ±MAX_DV) 會留下「合成超標」的無效角落。

        陣列結構: [t_wait, (r,theta,phi,coast_frac)*(num_burns-1), final_leg_frac,
                   offset_r, offset_theta, offset_phi]
        最後三個 (offset_r/theta/phi) 是最後一棒 Lambert 瞄準點相對 A 真實位置的球座標
        偏移量，r 夾在 [0, MISS_TOLERANCE_SOFT] —— 天生保證瞄準點落在規則允許的命中
        容許範圍內，讓優化器自己決定要不要用這個容許範圍去換更省油的轉移。
        """
        # 中間棒 dv_r 的上界：預設夾在 MAX_DV_SOFT (天生合規)；開拆棒感知搜尋時放寬，讓 DE
        # 能提出「靠拆棒實現」的大衝量節點 (代價由 fitness 的拆棒 surrogate 預付)。放寬幅度
        # 由 energy_floor 動態算 (B1)，不再是永遠 3×MAX_DV——見 _split_aware_dv_ub。
        dv_ub = self.MAX_DV_SOFT
        if self.SPLIT_AWARE_SEARCH:
            dv_ub = self._split_aware_dv_ub()
        lb = [0.0]
        ub = [self.T_max]
        for _ in range(1, num_burns):
            lb.extend([0.0, 0.0, 0.0, 0.0])
            ub.extend([dv_ub, math.pi, 2.0 * math.pi, 1.0])
        lb.append(0.0)
        ub.append(1.0)
        lb.extend([0.0, 0.0, 0.0])
        ub.extend([self.MISS_TOLERANCE_SOFT, math.pi, 2.0 * math.pi])
        assert len(lb) == decision_variable_dims(num_burns), (
            "決策變數維度公式跟 _generate_bounds 的實際陣列長度兜不起來——"
            "改了其中一邊記得同步改 decision_variable_dims()"
        )
        return lb, ub

    def _maxiter_for(self, num_burns: int) -> int:
        """
        self.maxiter 通常是一個整數 (所有燃燒次數案例共用同一個世代預算)，但也可以是
        一個 {燃燒次數: 世代數} 字典——sweep_burns.py 的粗掃階段會傳這種字典進來：
        決策變數維度隨燃燒次數線性長，同一個世代預算對高維度案例天生不公平 (棒數越多
        越吃虧，實測過 6 棒在 MAXITER=1000 下明顯輸 2 棒，拉到 3000 才追上，見
        STATUS.md「新增 sweep_burns.py」那節)，字典讓每個燃燒次數依維度分配到不同的
        世代數，粗掃階段的分數比較才公平，不用事後拉大 --window 去補系統性偏差。
        """
        if isinstance(self.maxiter, dict):
            if num_burns not in self.maxiter:
                raise ValueError(
                    f"optimization.MAXITER 是字典，但沒有 {num_burns} 這個燃燒次數的"
                    f"世代預算 (現有的 key: {sorted(self.maxiter.keys())})"
                )
            return int(self.maxiter[num_burns])
        return int(self.maxiter)

    @staticmethod
    def _attach_progress_reporting(model, progress_queue, case_id):
        """
        幫子行程裡的 mealpy 模型「掛」一個世代回報鉤子。

        mealpy 的 Optimizer.solve() 每跑完一代都會呼叫一次 self.track_optimize_step()
        (不管 log_to 是不是 None——log_to=None 只是讓它內部的 logger.info() 不印東西，
        呼叫本身照樣每代都發生)，這是唯一一個「每代結束」都保證會經過的掛勾點。這裡
        monkeypatch 單一 instance 的 bound method (不是繼承整個 L_SHADE class、也不改
        mealpy 原始碼)，讓它在原本行為之後，多把 (case_id, epoch) 塞進跨行程共享的
        progress_queue，範圍降到最小。

        progress_queue 用 multiprocessing.Manager().Queue()（不是普通的
        multiprocessing.Queue()）——後者只有在「行程建立當下」當參數傳入才能正確跨行程
        共享，ProcessPoolExecutor 的 worker 是已經活著的行程，事後再把它 pickle 送進去
        會直接丟 RuntimeError；Manager 的 proxy 物件本來就是設計成能在任意時間點被
        pickle、送到已經在跑的行程，在 spawn (macOS/Windows 預設) 下也能正常運作。
        """
        original_track_step = model.track_optimize_step

        def _wrapped_track_step(pop=None, epoch=None, runtime=None):
            original_track_step(pop=pop, epoch=epoch, runtime=runtime)
            try:
                progress_queue.put_nowait((case_id, epoch))
            except Exception:
                # 進度回報是錦上添花，佇列滿了/manager 已關閉之類的問題絕對不該讓
                # 最佳化本身中斷或整個案例報廢。
                pass

        model.track_optimize_step = _wrapped_track_step

    def _optimize_burn_case(self, current_burns, scalar_params, vector_params, progress_queue=None,
                            parallel_case_slots=None, progress_case_id=None):
        """
        獨立的工作包：負責在單一核心上，執行特定推進次數的最佳化。

        注意：這個函式是透過 ProcessPoolExecutor 丟到「子行程」執行的，不是主行程。
        tqdm 的進度條物件活在主行程裡，子行程完全不知道它的存在/游標位置——如果在
        這裡直接 print()/tqdm.write()，好幾個子行程各自不同時間點寫同一個終端機，
        會跟主行程進度條的 `\r` 覆寫互相打架，實測會讓進度條每次重繪變成往下多印
        一行 (而不是原地覆蓋)，越跑越長。所以這裡只回傳資訊，所有會印出來的訊息都
        留給呼叫端 (run_study，在主行程) 統一印，讓 tqdm 全程只在單一行程裡運作。

        progress_queue (選填)：用來把「這個案例跑到第幾代」回報給主行程畫進度條，
        見 _attach_progress_reporting 的說明。run_study() 一定會傳；預設 None 只是
        給直接呼叫這個私有方法的情境 (例如測試) 一個安全的退路，不回報也不出錯，
        行為等同修這個問題之前的版本。
        """
        lb, ub = self._generate_bounds(current_burns)
        # 族群大小依「真正的決策變數維度」縮放 (n_dims * POPSIZE)，而不是舊版的
        # (15+3*燃燒次數)*POPSIZE —— 舊公式在低燃燒次數時嚴重超編：1 次燃燒只有 2 維
        # 決策變數，舊公式卻給 360 個個體 (180倍維度)，遠超過 DE 類演算法常見的
        # 10~20倍維度經驗值，多的族群規模只是浪費運算時間，不會讓解更好。
        n_dims = len(lb)
        pop_size = max(30, n_dims * self.popsize)

        # 種子初始化 (2026-08-14)：只對單棒有效 (見 _generate_seed_candidates 的說明)，
        # 種子只佔族群一小部分 (~5%，至少 1 個)，其餘照舊純隨機——刻意不用種子取代
        # 隨機初始化，種子猜錯/把族群帶偏的最壞情況也只是浪費掉粗掃那幾十秒，隨機
        # 探索這個安全網完全保留。找不到種子 (n_seeds<=0 或粗掃沒收斂出結果) 時
        # seed_candidates 是空列表，starting_solutions 自然變成 None，行為等同
        # 加這個功能之前的版本。
        n_seeds = max(1, round(pop_size * 0.05))
        # 可重現性 (2026-09-22)：初始族群的 random_part 用全域 np.random 抽，而下面 solve 前才
        # np.random.seed() 已經太晚——那批隨機初始個體是**沒 seed** 的。窄窗 (預設每棒上界=cap)
        # 被種子主導、看不出來；SPLIT_AWARE 放寬上界到 factor×cap 後就露餡 (同 SEED 跑兩次會翻
        # 2/3 棒)。這裡在生成種子 / 抽 random_part **之前**先 seed，讓整個初始族群可重現；
        # solve 前還會再 seed 一次，讓搜尋本身也可重現 (見下 self.seed 分支)。
        if self.seed is not None:
            np.random.seed(self.seed)
        # fast 已先精修插棒種子，短全域不再支付完整種子家族的粗掃/SLSQP 成本。
        primer_fast = getattr(self, "_primer_fast_research", False)
        seed_candidates = ([] if primer_fast else
                           self._generate_seed_candidates(current_burns, n_seeds))
        # C2：外部注入的插棒種子放在最前面，確保不被 n_seeds 上限擠掉；夾回界內
        # （coast_frac 反解可能微幅越界，clip 後仍是有效起點，DE 會再精修）。
        ext = self.external_seeds.get(current_burns, [])
        if ext:
            _lb, _ub = np.array(lb), np.array(ub)
            seed_candidates = [np.clip(np.asarray(s, dtype=np.float64), _lb, _ub)
                               for s in ext] + list(seed_candidates)
        oracle = getattr(self, "oracle_seeds", {}).get(current_burns, [])
        if oracle:
            # SPLIT_AWARE_SEARCH changes only magnitude bounds, not x layout.
            seed_candidates = [np.clip(np.asarray(s, dtype=np.float64), lb, ub)
                               for s in oracle] + list(seed_candidates)
            pop_size = max(pop_size, len(seed_candidates))
        if seed_candidates:
            lb_arr, ub_arr = np.array(lb), np.array(ub)
            n_random = pop_size - len(seed_candidates)
            random_part = [np.random.uniform(lb_arr, ub_arr) for _ in range(n_random)]
            starting_solutions = seed_candidates + random_part
        else:
            starting_solutions = None

        def fitness_wrapper(solution):
            return fast_fitness_evaluator(
                np.asarray(solution, dtype=np.float64), 
                current_burns, 
                scalar_params, 
                vector_params
            )

        deadline = getattr(self, "_primer_search_deadline", None)
        timed_fitness = None
        if deadline is not None:
            timed_fitness = _DeadlineFitness(fitness_wrapper, deadline)
            fitness_wrapper = timed_fitness

        # 只放寬一般 L-SHADE 搜尋；種子精修與 deadline incumbent 比較沿用精確包裝器。
        search_rtol = getattr(self, "SEARCH_COAST_RTOL", 1e-12)
        search_relaxed = search_rtol != 1e-12 and deadline is None
        search_fitness = fitness_wrapper
        if search_relaxed:
            search_scalars = scalar_params.copy()
            search_scalars[23] = search_rtol

            def search_fitness(solution):
                return fast_fitness_evaluator(
                    np.asarray(solution, dtype=np.float64), current_burns,
                    search_scalars, vector_params)

        problem = {
            "obj_func": search_fitness,
            "bounds": [FloatVar(lb=l, ub=u) for l, u in zip(lb, ub)],
            "minmax": "min",    
            "log_to": None
        }

        case_maxiter = self._maxiter_for(current_burns)
        # mealpy 會在 solve() 開始時以其 termination 參數覆蓋建構子的設定。
        termination = ({"max_early_stop": self.mes, "epsilon": self.tol}
                       if self.early_stop_enabled else None)
        if deadline is not None:
            # mealpy 原生支援 TB；其 max_time 合法範圍是 [0.1, 1e6]。
            # 更短/更長的期限由上面的逐次評估檢查精確涵蓋。
            termination = dict(termination or {})
            termination["max_time"] = max(0.1, min(1e6, deadline - time.monotonic()))
        model = L_SHADE(epoch=case_maxiter, pop_size=pop_size)
        if progress_queue is not None:
            self._attach_progress_reporting(
                model, progress_queue,
                current_burns if progress_case_id is None else progress_case_id)

        # 外層已經用 ProcessPoolExecutor 分配案例；集成時案例包含 (REVS, burn_count)。
        # 這裡再把剩餘核心切給 mealpy 的 'thread' 模式，讓每一代的族群評估也平行跑。
        # fast_fitness_evaluator 已標記 nogil=True，thread 真的能吃到多核而不是被 GIL 卡住。
        # NUM_THREADS 設為正整數可強制指定每個 process 用幾條 thread；<=0 (含預設 -1) 則自動
        # 用 (可用核心數 / 同時執行的案例數) 估一個合理值；共用池也會限制明確指定的配額。
        num_cases = max(1, parallel_case_slots or len(self.burns))
        thread_cap = max(2, (os.cpu_count() or 4) // num_cases)
        if isinstance(self.num_threads, int) and self.num_threads > 0:
            n_workers = max(2, self.num_threads)
            if parallel_case_slots is not None:
                n_workers = min(n_workers, thread_cap)
        else:
            n_workers = thread_cap
        # mealpy 的 seed= 只會種到它自己建立的 np.random.default_rng(seed) 那個 generator，
        # 但 L_SHADE.evolve() 算突變參數 F 用的是 scipy.stats.cauchy.rvs(...)，沒有帶
        # random_state，實際上是從 numpy 的「全域」隨機狀態拿亂數，完全不受 seed= 控制。
        # 這裡額外把全域狀態也種一樣的 seed，補上這個 mealpy 本身的漏洞。
        #
        # 但這樣還不夠：mode='thread' 時，好幾個執行緒會「同時」向同一個 RNG 要亂數，
        # numpy 的 Generator 不是 thread-safe 的，誰先誰後純粹看 OS 排程，即使種子固定，
        # 每次跑到的順序還是會不一樣 —— 這是實測驗證過的 (同 seed 關執行緒完全重現、
        # 開執行緒就對不上)。所以：有指定 seed 代表你要的是「可重現」，這裡就自動退回
        # 單執行緒換取重現性；沒設 seed (預設) 就照樣用多執行緒換速度，兩者只能選一個。
        try:
            if self.seed is not None:
                np.random.seed(self.seed)
                g_best = model.solve(problem, seed=self.seed, starting_solutions=starting_solutions,
                                     termination=termination)
            else:
                g_best = model.solve(problem, mode="thread", n_workers=n_workers, seed=self.seed,
                                      starting_solutions=starting_solutions, termination=termination)
        except _PrimerSearchTimeout:
            # 可能在初始族群或某代中途到期，model.g_best 未必已更新；回傳逐次評估
            # 留下的最佳解。若連第一顆都還沒評估，main 仍有原解與局部解可交。
            return (current_burns, timed_fitness.best_x, timed_fitness.best_fitness,
                    len(getattr(model.history, "list_epoch_time", [])), "，primer fast 牆鐘到期")

        current_best_x = g_best.solution
        raw_fitness = g_best.target.fitness
        if search_relaxed:
            raw_fitness = fitness_wrapper(current_best_x)
        current_best_score = float(raw_fitness) if raw_fitness is not None else float('inf')

        # 種子精修 (2026-08-14)：光把種子丟進初始族群不夠可靠——實測過，種子在整個
        # 族群裡通常只佔一小部分名額 (5% 是上限，不是保證，真正能用的種子數受限於
        # _generate_seed_candidates 找到幾個有效候選窗口，可能遠低於 5%)，族群演化
        # 過程中很容易被其他個體 (尤其是「立刻噴、不管合不合法」這種好找的區域)
        # 稀釋掉——SHADE 這類 current-to-pbest 變異策略會把整個族群往目前最好的
        # 方向拉，種子還沒精修完就先被拉走了 (親眼測過這個現象)。修法：不只依賴
        # L-SHADE 自己的演化去精修種子，額外對每個原始種子單獨做一次局部 NLP 精修
        # (不受族群其他個體干擾)，贏過 L-SHADE 自己找到的贏家就取代——跟
        # refine_trajectory() 對最終贏家做的事同一招，只是這裡對每個種子各做一次，
        # 而且要在這裡 (子行程) 做，不能留到外層 (run_study 只會對最終贏家精修一次，
        # 其他燃燒次數案例自己的種子沒有第二次機會)。
        for seed_x in (seed_candidates if self.SEED_LBFGS_POLISH and not primer_fast else []):
            # 2026-08-15：改用共用的 _narrow_tolerance_bounds (跟 refine_trajectory()
            # 同一套規則)，正確處理多棒種子的完整陣列結構 (原本這裡寫死只認識單棒
            # 的 5 元素陣列，多棒種子索引會對不上、精修會用錯容忍度)。
            seed_bounds = self._narrow_tolerance_bounds(seed_x, lb, ub)
            try:
                seed_nlp = minimize(
                    fun=fitness_wrapper, x0=seed_x, method='L-BFGS-B',
                    bounds=seed_bounds, options={'maxiter': 50}
                )
                if seed_nlp.fun < current_best_score:
                    current_best_x, current_best_score = seed_nlp.x, float(seed_nlp.fun)
            except Exception:
                # 種子精修失敗 (數值問題之類) 不該讓整個案例報廢，跳過這個種子繼續。
                continue

        # 實際跑了幾代 (用來判斷 MAX_EARLY_STOP 有沒有提早介入，MAXITER 設定合不合理)。
        # 只有「提早停止」跟「seed 已設定所以退回單執行緒」這兩種情況值得特別提醒
        # (前者代表 MAX_EARLY_STOP 提前介入、後者代表這次跑得比較慢是預期中的取捨)，
        # 平常每次都印的 thread 數對使用者判斷任務規劃結果沒什麼幫助，不印。
        epochs_run = len(model.history.list_epoch_time)
        note = ""
        if epochs_run < case_maxiter:
            note += "，提早停止"
        if self.seed is not None:
            note += "，單執行緒 (seed 已設定)"
        if seed_candidates:
            note += (f"，{len(seed_candidates)} 個種子已獨立精修" if self.SEED_LBFGS_POLISH and not primer_fast
                     else f"，{len(seed_candidates)} 個種子（未獨立精修）")

        # note 回傳給主行程印，不在這裡印 (見函式開頭的說明)
        return current_burns, current_best_x, current_best_score, epochs_run, note
    
    def preflight_report(self) -> None:
        """
        開跑前的免費健檢 (2026-08-15)：能量下限是封閉解、微秒等級，所以無條件算。

        MAX_BURNS 裡若有低於「直接合法所需棒數」的案例，它在搜尋輸出當下必然違規；但
        AUTO_SPLIT_LEGALIZE 開啟時，這可能正是 route-first 流程刻意要的候選：先用少數
        邏輯棒找到好路線，再由 legalize_violating_winner 動態拆成合法多棒解。因此這裡
        只做說明，絕不修改 self.burns，也不會在拆棒開啟時建議使用者刪除案例。

        只有 AUTO_SPLIT_LEGALIZE 關閉時，這些案例才沒有後續合法化路徑，可以明確建議移除。

        詳細的可行性分析 (合法解有多稀有、多棒構造存不存在) 在 feasibility.py，
        這裡只做這個零成本的必要條件檢查。
        """
        floor_mps = self.energy_floor_dv() * 1000.0
        if floor_mps <= 0.0:
            return
        cap_mps = self.MAX_DV * 1000.0
        min_burns = math.ceil(floor_mps / cap_mps)
        impossible = sorted(b for b in self.burns if b < min_burns)
        if not impossible:
            return
        prefix = (f"⚠️ 能量下限 {floor_mps:,.0f} m/s（每棒上限 {cap_mps:,.0f} m/s）→ "
                  f"至少需要 {min_burns} 棒才能直接合法；MAX_BURNS 裡的 {impossible} "
                  "在搜尋輸出當下必然違規。")
        if self.AUTO_SPLIT_LEGALIZE:
            log.warning(prefix +
                        " AUTO_SPLIT_LEGALIZE 已開啟：保留它們作為 route-first 候選，"
                        "贏家會再動態拆棒合法化；不要只因這個警告移除。")
        else:
            log.warning(prefix +
                        " AUTO_SPLIT_LEGALIZE 已關閉，沒有後續拆棒路徑；若只接受合法解，"
                        "建議移除這些棒數或先用 feasibility.py 確認。")

    def run_study(self):
        if getattr(self, "_primer_fast_research", False):
            # C2 fast 只有一個 (REVS, N+1) 案例，直接跑現有 DE，省去 spawn/Manager
            # 成本；局部階段已精修，收尾只重播，不在牆鐘到期後另開一輪 NLP。
            b = self.burns[0]
            vectors = self._vector_params()   # 含星曆快取列，跟 _scalar_params 的索引一致
            _, x, fitness, epochs, note = self._optimize_burn_case(
                b, self._scalar_params(), vectors)
            self.burn_case_results[b] = {
                "fitness": fitness, "epochs_run": epochs, "note": note, "best_x": x,
            }
            log.info(f"✅ 推進 {b} 次完成：目標值 {fitness:.4f}，"
                     f"跑了 {epochs}/{self._maxiter_for(b)} 代{note}")
            picked = self._pick_best_case()
            if picked is None:
                return None, None, (None, None)
            b, x, _ = picked
            return self._replay_mission(x, b)
        cases = sorted(self.burns, reverse=True)
        log.log(self._report_level,
                f"🚀 L-SHADE 軌道最佳化：推進次數 {sorted(self.burns)}，"
                f"各 {self._maxiter_for(cases[0])} 代上限，{len(self.burns)} 個案例平行跑")
        self.preflight_report()

        scalar_params = self._scalar_params()
        
        vector_params = self._vector_params()
        
        # 贏家是所有案例都跑完之後才挑的 (見 pbar.close() 之後那段)，這裡不再
        # 邊收邊比，所以也不需要預先放一個「目前最好」的暫存值。

        # 開啟多行程池，最大核心數設定為你要測試的推進情境總數 (例如 burns = [1, 2, 3] 就是開 3 個)
        num_cases = len(self.burns)

        # 提交所有任務：把不同的 current_burns 丟給不同的核心。「開始計算」訊息在這裡
        # 印 (主行程)，不是在 _optimize_burn_case 裡 (子行程) 印——子行程不知道下面的
        # tqdm 進度條長什麼樣，兩邊搶著寫同一個終端機會讓進度條沒辦法原地覆寫，越跑
        # 越長 (見 _optimize_burn_case 開頭的說明)。

        # 進度條的粒度：舊版用「完成的案例數」當總量 (total=num_cases)，代表整個案例
        # (可能要跑幾秒到幾分鐘，燃燒次數越多、決策變數維度越高、族群越大就越貴) 全部
        # 跑完才會跳一格，格與格之間間隔長短很不一致，容易讓人誤判卡住了。改成以「世代」
        # 為粒度：每個案例都以自己的世代預算為分母 (_maxiter_for，不管實際會不會提早
        # 停止，先假設跑好跑滿)，所有案例的世代數加總當總量，讓進度條在整個搜尋過程中
        # 平滑前進。self.maxiter 可能是單一整數 (所有案例共用) 或 {燃燒次數: 世代數}
        # 字典 (sweep_burns.py 粗掃階段依維度分配公平預算時用)，_maxiter_for 兩種都吃。
        #
        # 世代進度是子行程 (_optimize_burn_case 裡的 mealpy 模型) 透過
        # multiprocessing.Manager().Queue() 回報回來的 (見 _attach_progress_reporting)，
        # 用一個背景執行緒持續清空佇列、更新進度條；主行程本身的 as_completed 迴圈維持
        # 原本的職責 (印「案例完成」訊息、記錄結果、挑最佳解)，兩者用一個 lock 保護
        # 共用的 case_progress/pbar，避免兩邊同時 update() 互相打架。
        pbar = tqdm(total=sum(self._maxiter_for(b) for b in self.burns), desc="搜尋世代進度", unit="gen")
        case_progress: dict = {}
        progress_lock = threading.Lock()
        stop_draining = threading.Event()

        def _bump_progress(case_id, epoch):
            """把某個案例的進度推進到 epoch (不會後退)，回報實際往前推進的量。"""
            with progress_lock:
                epoch = min(epoch, self._maxiter_for(case_id))
                prev = case_progress.get(case_id, 0)
                if epoch > prev:
                    pbar.update(epoch - prev)
                    case_progress[case_id] = epoch

        def _drain_progress_queue(progress_queue):
            """背景執行緒：持續把子行程回報的 (case_id, epoch) 收進來更新進度條，
            直到 run_study() 收工 (stop_draining 被設定) 才結束。用短 timeout 輪詢，
            讓它能定期檢查 stop_draining，不會卡住整個程式收尾。"""
            while not stop_draining.is_set():
                try:
                    case_id, epoch = progress_queue.get(timeout=0.2)
                except queue.Empty:
                    continue
                except (EOFError, OSError, BrokenPipeError):
                    # manager 已經在收尾 (run_study 結束前的正常關閉時序)，直接結束。
                    break
                _bump_progress(case_id, epoch)

        # Manager().Queue() 而不是普通 multiprocessing.Queue()：ProcessPoolExecutor
        # 的 worker 是已經活著的行程，事後才把佇列傳進 submit() 的參數，一般 Queue
        # 只有在「行程建立當下」當參數傳入才能正確共享，這裡會直接丟 RuntimeError；
        # Manager 的 proxy 物件本來就設計成能在任何時間點被 pickle 送給已經在跑的
        # 行程，spawn (macOS/Windows 預設 start method) 下也驗證過能正常運作。
        with multiprocessing.Manager() as manager:
            progress_queue = manager.Queue()
            drain_thread = threading.Thread(
                target=_drain_progress_queue, args=(progress_queue,), daemon=True
            )
            drain_thread.start()

            with concurrent.futures.ProcessPoolExecutor(max_workers=num_cases) as executor:
                futures = {
                    executor.submit(self._optimize_burn_case, b, scalar_params, vector_params, progress_queue): b
                    for b in sorted(self.burns, reverse=True)
                }

                # 監聽完成狀態：哪個核心先算完就先驗收誰的結果。不逐次印「發現新最佳解」
                # (哪個燃燒次數先跑完純粹看排程，中途領先沒有意義)，只在全部跑完後報一次
                # 最終選了哪個方案。
                for future in concurrent.futures.as_completed(futures):
                    b = futures[future]
                    try:
                        # note 是子行程準備好、交回主行程印的狀態備註 (同樣是為了不讓子行程
                        # 直接寫終端機)，平常是空字串，只有「提早停止」/「單執行緒」才有內容。
                        b_count, best_x, best_score, epochs_run, note = future.result()
                        log.info(f"✅ 推進 {b_count} 次完成：目標值 {best_score:.4f}，"
                                 f"跑了 {epochs_run}/{self._maxiter_for(b_count)} 代{note}")
                        # best_x 也記下來 (2026-08-15 新增)：sweep_burns.py 要用它判斷
                        # 「這個燃燒次數的解，中間棒到底有沒有真的燒」。實測過好幾個
                        # 情境，多棒解的中間棒 Δv 會恰好是 0 (種子的空燒結構，L-SHADE
                        # 沒離開過那個起點)，等於退化成單棒——這種情況下的分數差異只是
                        # 雜訊，不是多棒優勢，光看 fitness 分不出來。見 STATUS.md
                        # 「2026-08-15 白天」那節。
                        self.burn_case_results[b_count] = {
                            "fitness": best_score, "epochs_run": epochs_run, "note": note,
                            "best_x": best_x,
                        }

                        # 這裡**不再**即時挑贏家。挑選整段移到迴圈外面，因為規則第 6 節
                        # 的平手判定需要 Δr_min/ΔV_team/T_team，那要重建任務才算得出來，
                        # 不能在 as_completed 的順序裡邊收邊比。見 pbar.close() 之後。

                    except Exception as exc:
                        log.error(f"❌ [核心錯誤] 推進 {b} 次案例崩潰: {exc}")
                    finally:
                        # 不管成功/失敗/提早停止，這個案例的份額都補滿到它自己的世代
                        # 預算——提早停止代表子行程回報的最後一則 epoch < 預算，崩潰的
                        # 案例可能完全沒回報過；兩種情況都要補滿，進度條才會在收工時
                        # 精準到 100%，不會卡在 99% 或某個案例的份額整段空白。
                        _bump_progress(b, self._maxiter_for(b))

            stop_draining.set()
            drain_thread.join(timeout=2.0)

        pbar.close()

        picked = self._pick_best_case()
        if picked is None:
            return None, None, (None, None)
        best_burns_count, best_overall_params, best_overall_score = picked
        return self.refine_trajectory(best_overall_params, best_burns_count, best_overall_score)

    def refine_trajectory(self, initial_guess_x, num_burns, initial_fitness=None):
        log.debug("🔬 啟動高精度 NLP 微調...")
        bounds = self._generate_bounds(num_burns)
        
        # 2026-08-15：容忍度規則抽到 _narrow_tolerance_bounds 共用 (原本這裡是
        # 唯一的實作，_optimize_burn_case 的種子精修現在也用同一套)。
        narrow_bounds = self._narrow_tolerance_bounds(initial_guess_x, bounds[0], bounds[1])

        scalar_params = self._scalar_params()
        
        vector_params = self._vector_params()

        def fitness_wrapper(solution):
            return fast_fitness_evaluator(
                np.asarray(solution, dtype=np.float64), 
                num_burns, 
                scalar_params, 
                vector_params
            )

        # L-SHADE 給的解本身的 fitness，作為「有沒有真的變好」的基準線。
        # run_study() 其實已經算過這個值了 (best_overall_score)，這裡直接沿用，
        # 不用再花一次 (現在因為順逆向各算一次 Lambert，變貴了的) evaluation 重算一遍。
        if initial_fitness is None:
            initial_fitness = float(fitness_wrapper(initial_guess_x))

        nlp_result = minimize(
            fun=fitness_wrapper, x0=initial_guess_x,
            method='L-BFGS-B', bounds=narrow_bounds,
            options={'disp': is_verbose(), 'maxiter': 50}   # scipy 自己的迭代碎念只在 -v 才放出來
        )

        # 安全回退：L-BFGS-B 的 success 只代表「收斂了」，不代表「比原本的解更好」。
        # 目標函式裡有好幾處硬跳躍 (撞地球直接 0 分、超過 Δv 就扣分)，數值梯度在這種
        # 不連續的地方不可靠，微調完分數反而變差是有可能發生的，所以要實際比一次 fitness，
        # 沒有變好 (更小，因為 mealpy 是找最小值) 就退回微調前的解。
        if nlp_result.success and nlp_result.fun <= initial_fitness:
            res = nlp_result.x
            # 真的動到解 = 事件，值一行 INFO。
            log.info(f"🔬 NLP 微調有改善: {initial_fitness:.4f} → {nlp_result.fun:.4f}")
        elif not nlp_result.success:
            # fun 可能其實有變小一點點，但 scipy 自己都不認為這是收斂的結果 (例如撞到
            # maxiter 上限)，保守起見不採用。沒採用 = no-op，降到 DEBUG。
            res = initial_guess_x
            log.debug(f"NLP 微調未收斂 (scipy success=False，{initial_fitness:.4f} → "
                      f"{nlp_result.fun:.4f})，保留微調前的解")
        else:
            res = initial_guess_x   # 收斂但沒更好 = no-op，降到 DEBUG。
            log.debug(f"NLP 微調沒有改善 (微調前 {initial_fitness:.4f} / 微調後 "
                      f"{nlp_result.fun:.4f})，保留微調前的解")

        res = self._tiebreak_polish(res, num_burns, fitness_wrapper, narrow_bounds)
        return self._replay_mission(res, num_burns)

    def _best_lambert(self, r0, v0, r_target, tof):
        """掃過所有 Lambert 分支，回傳需求 Δv 最小的那個 (v1, dv, used_retrograde)。

        分支政策**只在這裡跟 fast_fitness_evaluator 裡各寫一次**（後者是 njit，沒辦法
        共用 Python 函式）。2026-08-28 加多圈轉移時，只改了適應度函式跟重播，三個種子
        產生器都還停在 `M=0, lowpath=True`——結果是搜尋能「評估」多圈解，卻沒有任何
        種子能「提出」多圈解。這個函式就是為了不要再有第四個地方各寫一份。

        算不出來（所有分支都失敗）時回傳 (None, inf, False)。

        ⚠️ **目前沒有人呼叫它。** 2026-08-28 試著讓三個種子產生器改用它，實測反而變差
        （known_phasing、LAMBERT_MAX_REVS=4：最好的種子從 166.1 m/s 合法變成 3,940.7 m/s
        違規）。原因查明了：種子產生器裡的 Lambert 只是**挑窗口的啟發式排序**，種子真正的
        價值由 fast_fitness_evaluator 決定，而它本來就會掃所有分支——所以種子早就吃得到
        多圈的好處，把排序也換成多圈只會挑到不同、而且更差的窗口。已還原。

        留著這個函式是因為「分支政策散在多個地方各寫一份」本身是風險（今天就差點只改
        搜尋端沒改重播端）。之後若要統一，從這裡接，但記得排序啟發式跟評估目標**不必**
        是同一個東西。
        """
        best_v, best_dv, retro = None, float("inf"), False
        for m_rev in range(0, int(self.LAMBERT_MAX_REVS) + 1):
            for lowpath in (True, False):
                if m_rev == 0 and not lowpath:
                    continue                    # M=0 只有一組解
                for prograde in (True, False):
                    try:
                        v1, _ = lambert_izzo(self.MU, r0, r_target, float(tof), M=m_rev,
                                     prograde=prograde, lowpath=lowpath)
                    except Exception:
                        continue
                    d = fast_norm(v1 - v0)
                    if d < best_dv:
                        best_v, best_dv, retro = v1, d, (not prograde)
        return best_v, best_dv, retro

    def _scalar_params(self):
        """fast_fitness_evaluator 的 scalars 陣列。索引佈局要跟 evaluator 開頭逐格對齊：
        0-12 環境/計分常數、13 lambert_max_revs、14/15 SPLIT_AWARE_SEARCH、16-18 C4 終端棒
        拆後估計 (旗標、K、overhead)、19 總 Δv 上限 (km/s，0 = 沒有)、20 拆棒器能處理的單棒
        上限 (km/s，排位賽模式才用)、21 檢查點間距 (0=關)、22 檢查點數、23 滑行 rtol。
        SEARCH 與 SPLIT_LEADING 都開時另附 24 真實單棒上限、25 前導可拆上限。其餘維持 24 格 ABI。
        這裡的 rtol 永遠是精確值；只有 L-SHADE 搜尋另用搜尋容差。
        只准在這裡組——原本三處各抄一份，改一處忘兩處。"""
        params = np.array([
            self.MIN_COAST_TIME, self.T_max, self.MU, self.J2_VAL, self.J3_VAL, self.J4_VAL,
            self.RE_VAL, self.MIN_PERIAPSIS, self.MAX_DV_SOFT, self.k_t, self.C_t, self.k_v, self.C_v,
            float(self.LAMBERT_MAX_REVS),
            float(self.SPLIT_AWARE_SEARCH), self.SPLIT_AWARE_DV_OVERHEAD,
            float(self.SPLIT_AWARE_TERMINAL), self.SPLIT_AWARE_TERMINAL_MAX_FACTOR,
            self.SPLIT_AWARE_TERMINAL_DV_OVERHEAD,
            0.0 if self.MAX_TOTAL_DV_MPS is None else self.MAX_TOTAL_DV_MPS / 1000.0,
            self.SPLIT_LIMIT,
            0.0 if self.ephem is None else self.ephem[0],
            0.0 if self.ephem is None else self.ephem[1].shape[0] // 2,
            1e-12,
        ], dtype=np.float64)
        if self.SPLIT_AWARE_SEARCH and self.SPLIT_LEADING:
            params = np.append(params, [self.MAX_DV, self.LEADING_SPLIT_LIMIT])
        return params

    def _search_scalar_params(self):
        """搜尋用的獨立副本；不改變精修、重播及驗證使用的精確參數。"""
        scalars = self._scalar_params().copy()
        scalars[23] = self.SEARCH_COAST_RTOL
        return scalars

    def _fitness_wrapper(self, num_burns):
        """包一個給定燃燒次數的目標函式 (= -分數)，方便在最佳化流程外面單獨評估。"""
        scalar_params = self._scalar_params()
        vector_params = self._vector_params()

        def _f(solution):
            return fast_fitness_evaluator(np.asarray(solution, dtype=np.float64),
                                          num_burns, scalar_params, vector_params)
        return _f

    def _tiebreak_polish(self, x, num_burns, fitness_wrapper, bounds):
        """在**分數一分都不能少**的前提下，把 Δr_min 壓到最小。

        規則第 6 節的優先序 1 是相對距離小者排前面，而計分函式在 Δr ≤ 5km 之內完全
        平坦 (Δr_min 被 max(Δr, 5) 地板夾住)。也就是說：只要壓小 Δr 不用付出分數的
        代價，那就是白拿的名次優勢。決策向量的最後三格 (offset_r/theta/phi) 正是最後
        一棒 Lambert 瞄準點相對 A 真實位置的偏移，offset_r 就是這裡要壓的量。

        重點在「不用付代價」這個條件不是永遠成立的：瞄準點移動會改變 Lambert 需求，
        Δv 跟著變，燃料項不飽和時 1 m/s 就值 0.03 分左右，遠大於這裡的打平門檻——
        那種情況下搜尋已經做過最佳權衡了，這一步應該什麼都不做（而且會如實回報）。
        真正有賺頭的是燃料 sigmoid **飽和**的情境 (k_v 大或 Δv 離 C_v 很遠)，那時
        Δv 的微小變化對分數毫無影響，Δr 就成了免費的自由度。

        安全性：新解一定要通過「分數沒有變差」的實測才會被採用，沒通過就原封不動
        退回。分數永遠優先於平手判定 —— 拿分數換名次是方向錯的。
        """
        if not self.TIEBREAK_POLISH:
            return x
        x = np.asarray(x, dtype=np.float64).copy()
        baseline = float(fitness_wrapper(x))          # = -score，越小越好
        offset_idx = len(x) - 3
        if x[offset_idx] <= 1e-3:                     # 已經幾乎瞄準 A 本體，沒得壓
            return x

        # 目標：最小化 offset_r，但分數掉超過 TIEBREAK_SCORE_EPS 就用巨大罰項擋回去。
        # 罰項尺度 1e6 是相對於 offset_r (公里，最多 3.5) 取的——只要分數掉了一點點，
        # 罰項就會壓過任何可能的 offset_r 收益。
        def polish_objective(sol):
            f = float(fitness_wrapper(np.asarray(sol, dtype=np.float64)))
            over = max(0.0, f - (baseline + self.TIEBREAK_SCORE_EPS))
            return float(sol[offset_idx]) + 1e6 * over

        # 邊界：其他維度沿用 NLP 微調用的窄邊界 (不讓這一步把解帶跑掉)，但 offset_r
        # 這一維要放開到規則允許的完整範圍 [0, MISS_TOLERANCE_SOFT]。窄邊界是繞著
        # 微調前的解切出來的，如果連 offset_r 也照窄邊界切，這一步最多只能在原值附近
        # 挪一點點——實測 3,000 m 只降到 2,475 m 就卡住，等於白做。
        polish_bounds = list(bounds)
        polish_bounds[offset_idx] = (0.0, self.MISS_TOLERANCE_SOFT)

        try:
            out = minimize(fun=polish_objective, x0=x, method='L-BFGS-B',
                           bounds=polish_bounds, options={'disp': False, 'maxiter': 30})
        except Exception as exc:
            log.debug(f"平手判定微調跳過（{type(exc).__name__}）")
            return x

        cand = np.asarray(out.x, dtype=np.float64)
        cand_fit = float(fitness_wrapper(cand))
        gained = x[offset_idx] - cand[offset_idx]
        if cand_fit <= baseline + self.TIEBREAK_SCORE_EPS and gained > 1e-4:
            cost = cand_fit - baseline          # >0 代表分數真的掉了一點
            tag = ("（分數沒有變差）" if cost <= 1e-9 else
                   f"（分數掉了 {cost:.6f} 分，在設定的打平門檻 "
                   f"{self.TIEBREAK_SCORE_EPS:g} 以內——這是拿分數換名次，"
                   f"只有在官方比分數會四捨五入的前提下才划算）")
            # 真的壓下了 Δr = 事件，值一行 INFO（tag 的細節留給 DEBUG/log 檔就好）。
            log.info(f"⚖️ 平手微調(§6)：Δr {x[offset_idx]*1000:,.1f} → {cand[offset_idx]*1000:,.1f} m"
                     f"，分數 {-baseline:.4f} → {-cand_fit:.4f}")
            log.debug(f"   平手微調 tag：{tag}")
            return cand
        # 以下兩支都是 no-op（沒動到解）：不掉分壓不動、或壓了會掉分而放棄。降到 DEBUG，
        # 「為什麼壓不動」的原理（計分函式對瞄準點還有梯度、燃料項沒飽和）寫在本函式
        # docstring 裡，不再每次執行都印出來上課。
        if cand_fit > baseline + self.TIEBREAK_SCORE_EPS:
            log.debug(f"平手微調沒採用：壓小 Δr 會讓分數 {-baseline:.4f} → {-cand_fit:.4f}，分數優先，維持原解。")
        else:
            log.debug(f"平手微調沒空間：不掉分的前提下 Δr 壓不下去（維持 {x[offset_idx]*1000:,.1f} m）。")
        return x

    def _pick_best_case(self):
        """從 burn_case_results 裡照規則第 6 節挑出要送去精修的那個案例。

        回傳 (燃燒次數, 決策向量, fitness)，全軍覆沒時回傳 None。
        獨立成一個方法是為了可測試——這段的重點是「平手時選誰」，而那條路徑
        在真實搜尋裡不保證跑得到 (要剛好兩個案例分數一模一樣)，只能餵假資料驗。
        """
        # ── 挑贏家：照規則第 6 節的平手判定，不是照 fitness 誰小誰贏 ──────────
        # 舊版在 as_completed 迴圈裡用 `best_score < best_overall_score` 即時挑，兩個問題：
        #   (1) 嚴格小於代表平手時留下的是**先跑完**的那個，而完成順序由作業系統的行程
        #       排程決定 —— 同一份設定重跑兩次可能交出不同方案，這是不該有的隨機性。
        #   (2) 規則第 6 節根本沒有「誰先跑完」這條，分數相同時名次是看
        #       Δr_min → ΔV_team → T_team。
        # 而且分數打平在這個工具裡是常態不是特例：計分函式在 Δr ≤ 5km 內完全平坦、
        # 燃料/時間 sigmoid 飽和時也平坦、多棒解又常退化成跟少棒解同一個解 (見
        # effective_burns 的說明)，這三種情況都會產生浮點數等級一模一樣的分數。
        viable = {b: r for b, r in self.burn_case_results.items()
                  if r.get("best_x") is not None and r["fitness"] < 0.0}
        self.no_legal_route = None
        if not viable:
            self._log_no_legal_route()
            return None

        metrics = {}
        for b in sorted(viable):
            try:
                metrics[b] = self.mission_metrics(viable[b]["best_x"], b)
            except Exception as exc:
                # 連成績都重建不出來的候選直接淘汰——那種方案本來就交不出去
                log.warning(f"⚠️ 推進 {b} 次的解沒辦法重建成績（{type(exc).__name__}），不列入挑選")
        if not metrics:
            log.error("❌ 最佳化失敗：沒有任何一組解能重建出成績。")
            return None

        # 打平的候選先各自跑一次收尾微調再比。理由：微調專門在動 Δr (規則第 6 節的
        # 優先序 1)，動輒好幾公里，比較「微調前」的 Δr 等於拿還沒定案的數字排名次。
        # 實測過一次 playground：微調前 1 棒 3,499.9m / 2 棒 3,498.3m，用這 1.6 公尺
        # 的差距選了 2 棒 (而且那多出來的一棒很可能是 Δv≈0 的空燒)；微調後兩邊都會被
        # 壓到 0.1m 上下，那 1.6 公尺根本不存在。只在真的打平時才做，成本有上限。
        # C4：SPLIT_AWARE_TERMINAL 開時，分桶與排名的 Score 改用拆後估計 (score_split_est)
        # ——搜尋端已經用同一把尺，挑贏家不能又回到含 −10 的真實分數 (那會把拆後 98.32 的
        # 88.32 家族排在合法 89.25 家族後面)。旗標關時就是真實分數，逐位元同舊行為。
        def _sc(m):  # 跟 mission_rank_score 同規則：沒有拆後估計欄位就退回真實分數
            return mission_rank_score(m, split_est=self.SPLIT_AWARE_TERMINAL)
        pre_bucket = {b: round(_sc(metrics[b]) / self.TIEBREAK_SCORE_EPS) for b in metrics}
        if len(set(pre_bucket.values())) < len(pre_bucket) and self.TIEBREAK_POLISH:
            top = max(pre_bucket.values())
            tied_pre = [k for k in sorted(metrics) if pre_bucket[k] == top]
            # 內部前處理（打平候選先各自跑收尾微調再排名），不是使用者要盯的事件 → DEBUG。
            log.debug(f"⚖️ 推進 {tied_pre} 次分數打平，先各自跑 §6 收尾微調再比名次。")
            for b in tied_pre:
                try:
                    f = self._fitness_wrapper(b)
                    lb, ub = self._generate_bounds(b)
                    x0 = np.asarray(viable[b]["best_x"], dtype=np.float64)
                    polished = self._tiebreak_polish(
                        x0, b, f, self._narrow_tolerance_bounds(x0, lb, ub))
                    if polished is not x0:
                        viable[b]["best_x"] = polished
                        viable[b]["fitness"] = float(f(polished))
                        metrics[b] = self.mission_metrics(polished, b)
                except Exception as exc:
                    log.debug(f"（推進 {b} 次的收尾微調跳過：{type(exc).__name__}）")

        def _key(b, floor_miss):
            m = metrics[b]
            # 最後補上棒數：連平手判定的三項都相同時，選**實際用到**的棒數少的那個
            # (effective_burns，不是名目棒數——多棒解很常退化成中間棒 Δv=0 的空燒)。
            # 這一項不在規則裡，純粹是為了讓結果可重現，而且棒數少的 GMAT 腳本比較
            # 好收斂；只有在規則管不到的地方才會生效。
            return tiebreak_rank_key(_sc(m), m["miss_km"], m["dv_mps"],
                                     m["t_team"], floor_miss=floor_miss,
                                     eps=self.TIEBREAK_SCORE_EPS) + (
                                         effective_burns(b, viable[b]["best_x"]), b)

        best_burns_count = min(metrics, key=lambda b: _key(b, False))
        best_overall_params = viable[best_burns_count]["best_x"]
        best_overall_score = viable[best_burns_count]["fitness"]

        # 有沒有真的動用到平手判定？(不只一個候選落在同一個分數桶)
        bucket = {b: round(_sc(metrics[b]) / self.TIEBREAK_SCORE_EPS) for b in metrics}
        top_bucket = max(bucket.values())
        tied = sorted(b for b in metrics if bucket[b] == top_bucket)
        if len(tied) > 1:
            # 事件濃縮成一行（報告層級）：打平 → 採用哪個。逐項比對表是細節 → DEBUG/log 檔。
            log.log(self._report_level,
                    f"⚖️ 推進 {tied} 次打平(Score {_sc(metrics[tied[0]]):.4f}) → 依§6"
                    f"(Δr→ΔV→T)採用 {best_burns_count} 棒")
            log.debug(f"     {'棒數':<6}{'Δr_min (m)':>14}{'ΔV_team (m/s)':>16}{'T_team (s)':>14}")
            for b in tied:
                m = metrics[b]
                mark = "  ← 採用" if b == best_burns_count else ""
                log.debug(f"     {b:<6}{m['miss_km']*1000:>14,.1f}{m['dv_mps']:>16,.1f}"
                          f"{m['t_team']:>14,.1f}{mark}")

            # 規則第 6 節的歧義：優先序 1 的符號是 d_min,team，跟第 4 節計分用的
            # Δr_min = max(Δr, 5) 不是同一個符號，官方沒有定義 d_min,team。兩種讀法
            # 有時候會選出不同的方案——這會改變答案，屬於使用者該知道的警告，留 WARNING
            # 一行；「為什麼會歧義」的完整說明在上面這段註解裡，不再印到終端機上課。
            alt = min(metrics, key=lambda b: _key(b, True))
            if alt != best_burns_count:
                log.warning(f"⚠️ §6優先序1讀法會改變答案：原始最近距離→{best_burns_count}棒，"
                            f"Δr_min=max(Δr,5)地板→{alt}棒。工具用原始距離，數字自己看了定案。")

        # 代理值最好的案例不見得會被選上——挑贏家是用重播算出來的**真實分數**，
        # 而搜尋用的目標值只是代理 (最後一棒用純二體 Lambert 的 Δv，不含 J2/J3/J4
        # 修正)。飛行時間長的時候兩者可以差非常多：實測 hard_mode 診斷變體上，
        # 3 棒代理 -80.72 但真實只有 72.33，輸給 1 棒真實 74.75 的解 (官方範例題目
        # 那種 6.4 小時的尺度則幾乎完全一致，中位數只差 0.02 分)。
        # 不講白的話，日誌上會看到「目標值比較好的案例沒被選」而完全沒有理由。
        # 「目標值(代理)最好的案例沒被選」的診斷：代理 vs 真實分數的落差。原理長、而且常常
        # 是 +0.0000（代理跟真實一致），純診斷 → DEBUG。為什麼代理會偏（最後一棒純二體
        # Lambert、飛行時間越長偏越多）寫在上面這段註解裡，不印到終端機。
        fitness_best = min(viable, key=lambda b: viable[b]["fitness"])
        if fitness_best != best_burns_count and fitness_best in metrics:
            log.debug(f"📐 目標值最好的是 {fitness_best} 棒({viable[fitness_best]['fitness']:.4f})但沒採用"
                      f"（挑贏家看真實分數不看代理）："
                      f"{fitness_best}棒 代理{-viable[fitness_best]['fitness']:.4f}/真實{metrics[fitness_best]['score']:.4f}；"
                      f"{best_burns_count}棒 代理{-viable[best_burns_count]['fitness']:.4f}/真實{metrics[best_burns_count]['score']:.4f}")

        # C4 退路 (2.3)：記下真實分數最高的零違規、Earth-safe 候選 (未精修)。拆後估計只是
        # 估計——拆棒真的失敗時，main 拿它跟違規解比真實分數，交好的那個。
        self.legal_backup = None
        if self.SPLIT_AWARE_TERMINAL:
            legal = [b for b in metrics
                     if not is_disqualified(metrics[b]) and metrics[b]["earth_safe"]]
            if legal:
                bk = min(legal, key=lambda b: tiebreak_rank_key(
                    metrics[b]["score"], metrics[b]["miss_km"], metrics[b]["dv_mps"],
                    metrics[b]["t_team"], eps=self.TIEBREAK_SCORE_EPS) + (b,))
                self.legal_backup = {"opt": self, "burns": bk, "x": viable[bk]["best_x"],
                                     "fitness": viable[bk]["fitness"],
                                     "score": metrics[bk]["score"]}
            leading_count = metrics[best_burns_count].get("split_leading_count", 0)
            split_desc = ([f"前導棒 {leading_count} 發"] if leading_count else [])
            if metrics[best_burns_count]["split_terminal_count"]:
                split_desc.append("終端棒")
            if split_desc:
                log.log(self._report_level,
                        f"✂️ 採用的 {best_burns_count} 棒解{'、'.join(split_desc)}超標、可拆：真實 "
                        f"{metrics[best_burns_count]['score']:.4f} → 拆後估計 "
                        f"{metrics[best_burns_count]['score_split_est']:.4f}"
                        + (f"（合法備胎：{self.legal_backup['burns']} 棒 "
                           f"{self.legal_backup['score']:.4f}）" if self.legal_backup else
                           "（沒有零違規備胎）"))

        m = metrics[best_burns_count]
        log.log(self._report_level,
                f"✅ 最佳化完成！採用推進 {best_burns_count} 次的方案 "
                f"(目標值 {best_overall_score:.4f}，Δr_min {m['miss_km']*1000:,.1f} m，"
                f"ΔV_team {m['dv_mps']:,.1f} m/s，T_team {m['t_team']:,.1f} s)")
        return best_burns_count, best_overall_params, best_overall_score

    def _log_no_legal_route(self):
        """_pick_best_case 沒有任何合法層候選時的錯誤訊息。排位賽模式下最常見的原因是整場搜尋
        只找到失格層 (總 Δv 超標 / 單棒超出拆棒範圍) 的路線——明講，並印最好那個的數字，讓人
        知道差多少 (現場可以考慮放寬棒數、T_max 或接受沒有合法解)。"""
        dq = {b: r for b, r in self.burn_case_results.items()
              if r.get("best_x") is not None and r["fitness"] is not None
              and -SEARCH_FAIL_SCORE_RANKED > r["fitness"] > 0.0}
        if not (self.RANKING_RULES and dq):
            log.error("❌ 最佳化失敗：所有的嘗試都撞毀或違規了。")
            return
        b = min(dq, key=lambda k: dq[k]["fitness"])
        self.no_legal_route = {"burns": b, "x": np.asarray(dq[b]["best_x"], dtype=np.float64),
                               "fitness": float(dq[b]["fitness"])}
        detail = ""
        try:
            m = self.mission_metrics(dq[b]["best_x"], b)
            detail = (f"是 {b} 棒、總 Δv {m['dv_mps']:,.0f} m/s、T {m['t_team']:,.0f} s"
                      f"（{'；'.join(m['dq_reasons']) or '搜尋代理判失格、重播判合法'}；"
                      f"拆棒器單棒上限 {self.SPLIT_LIMIT * 1000.0:,.0f} m/s）")
        except Exception as exc:          # 診斷訊息，重建不出來也不擋
            detail = f"（重建成績失敗：{type(exc).__name__}）"
        log.error(f"❌ 找不到合法路線：所有棒數案例的最佳解都在失格層（總 Δv 超標或單棒超出拆棒範圍）。"
                  f"最接近合法的{detail}。排位賽規則下這種解會被判失格，不輸出。")
