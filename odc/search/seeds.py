"""保存任務搜尋的各種候選種子建構方法
主要入口為 SeedCandidatesMixin._generate_seed_candidates。
"""
import math
import numpy as np
from typing import Tuple
from scipy.optimize import minimize
from odc.scoring.scorer import (calculate_score, ranked_search_score, assess_legality,
                        SEARCH_FAIL_SCORE_RANKED, DV_LIMIT_TOL_MPS)
from odc.physics.core_math import (propagate_dop853, check_constraints, fast_norm,
                           to_vnb_frame, reaches_perigee, lambert_izzo,
                           izzo_max_revs, ephem_state, build_ephem_table, fixed_orbit_state,
                           build_wait_prefix, cached_wait_min_radius, arc_radius_from_end,
                           initial_wait_min_radius)
from odc.search.fitness import decision_variable_dims


class SeedCandidatesMixin:

    def _generate_seed_candidates(self, num_burns: int, n_seeds: int) -> list:
        """
        幫初始族群準備幾個「有物理根據的猜測」當種子，其餘照舊隨機生成——不是取代
        隨機初始化，是額外加進去 (見 _optimize_burn_case 呼叫端怎麼混合)。

        動機 (2026-08-14「weird_test.json 深度診斷」那節)：某些極端幾何 (例如目標 A
        跟 B 的軌道傾角差很大) 下，唯一合法的單棒解可能藏在一個只佔 T_max 千分之幾
        的窄時間窗口裡，實測過純隨機初始化跑到 2000 代都撞不到；反過來，一個便宜的
        低維度粗掃 (只掃 t_wait/flight_time，不用管其他維度) 幾秒到幾十秒內就能找到。

        多棒 (num_burns>1) 種子 (2026-08-15 補上，見 STATUS.md「多棒分段接力種子」節)：
        不是重新對高維度決策空間做網格搜尋 (維度詛咒，25點網格在9維會爆炸到 25^9)，
        而是「分段貪婪接力」——先遞迴呼叫這個方法本身 (num_burns=1) 拿到單棒候選，
        每個候選本質上是一組「(t_wait_final, final_leg_frac) 這樣接力就能命中」的
        時機答案；把它原封不動當成「最後一棒」的時機，前面 (num_burns-1) 棒全部
        設成 Δv=0 的空燒 (方向不重要，大小是0，球座標參數化下天生合法)，滑行時間
        全部卡在 MIN_COAST_TIME (最短間隔)，讓 current_time 精確疊加到跟單棒種子
        一樣的 t_wait_final。這樣構造出來的種子，重播出來的軌跡跟「直接單棒解」
        完全等價 (前面幾棒等於沒發生過)，是個合法但保守的起點——L-SHADE 自己會在
        這個起點附近去試「前面幾棒到底該不該真的燒」，不用種子自己猜方向。
        測過 (2026-08-15 多棒基準測試)：weird_test.json 的 2 棒案例在同樣的世代
        預算下，沒種子的話比有種子的單棒還差 (-64.33 vs -76.98)，純隨機在9維
        空間內明顯吃虧。

        候選窗口有「兩種」來源 (2026-08-15 補上第二種，見 STATUS.md「傾角窄窗」節)：
        1. A 離地球最近的時間——對應「離心率把時間壓縮在近地點附近」這種窄窗，是
           原本就有的邏輯。
        2. A 最靠近 B 軌道平面的時間 (節線附近)——對應「傾角差大」這種窄窗。實測
           過 (2026-08-15 傾角掃描)：傾角差在 90° 附近時，合法窗口可以窄到只佔
           220 秒；而且兩種候選來源可能完全對不上——AOP 讓近地點落在離節線很遠的
           地方時，只用第 1 種來源找到的種子，Δv 比真正的全域最佳差了 7500 m/s
           以上 (見 inc_aop_adversarial.py 的實測)。所以這裡兩種來源都掃，不能只
           選一種。

        兩種掃法都刻意做得便宜 (相對於後面真正的 L-SHADE 搜尋而言)，而且共用同一次
        粗掃迴圈算出來的 A 軌道位置，不用多傳播一次：
        - 不管 A 是週期性軌道 (每圈一次) 還是排位賽的雙曲線 (最多一次飛掠)，這兩種
          掃法對兩種軌道形狀都適用，不用特別判斷是哪一種。
        - B 的軌道平面法向量用 t=0 時的 (B_r0, B_v0) 算 (h_B = r×v 方向)，只當一個
          便宜的近似候選來源——J2 攝動會讓真實平面慢慢進動，但候選窗口只是要告訴
          後面的 Lambert 精修「大概去哪裡找」，不要求算得多準，真正精確的收斂交給
          下面的中解析度/細網格 Lambert 掃描 (跟第 1 種來源的近地點候選是同一個
          精修管線，來源不同、後續處理完全一樣)。

        接下來對每個候選時間點附近，用 Lambert 做一次粗略的局部收斂 (t_wait 在候選點
        附近晃動、flight_time 抓幾個常見量級)，找出還不錯的 (t_wait, flight_time)
        組合轉成種子。不追求全域最佳 (那是 L-SHADE 接手後的工作)，只求種子落在
        對的鄰域，讓後續的突變/交叉有機會慢慢逼近真正的最佳值。
        """
        if n_seeds <= 0:
            return []

        if num_burns > 1:
            # 兩個家族混合 (2026-08-15)：
            #  - 分段貪婪接力：把單棒的好答案接成多棒格式 (前面幾棒空燒)。單棒夠用的
            #    情境靠這個，實測會正確退化回單棒。
            #  - 近地點連續推進階梯：真的有燒的中間棒，補上前者的結構性盲區。只有在
            #    energy_floor_dv() 超過每棒上限 (= 單棒在能量上不可能) 時才會產生東西，
            #    一般情境直接回空清單，不花成本。
            # 兩邊都給就好，不用互斥——族群裡多一種起點只會多一個探索方向。
            relay = self._generate_multiburn_seed_candidates(num_burns, n_seeds)
            ladder = self._generate_ladder_seed_candidates(num_burns, n_seeds)
            # 抬高+換面+平均拆收尾 (2026-09-05)：大傾角差 + 撞地球約束下 relay/ladder 都
            # 到不了的家族 (初賽最佳合法解正是這一類)，只有平面夾角>30° 才會產東西。
            pcsplit = self._generate_planechange_split_seed_candidates(num_burns, n_seeds)
            # 不要在這裡截斷！第一版寫成 (relay+ladder)[:max(n_seeds, len(relay))]，
            # 而 relay 本來就會回傳到 n_seeds 個，所以那個切片把階梯種子整批丟掉，
            # 實測「加了種子但種子數完全沒變 (13 -> 13)」才抓到。三個家族各自已經
            # 在內部限制數量了，這裡直接相加即可；種子總數相對族群 (n_dims*POPSIZE，
            # 5 棒是 420) 仍然只佔一成上下，不會淹掉隨機探索。
            #
            # joint NLP 精修 (HAP-47，2026-09-10)：對上面三家族已經產出的種子再做一次
            # 帶顯式不等式約束的 SLSQP 局部聯合優化，見 _generate_nlp_refined_seed_candidates
            # docstring。輸入是三家族的合併結果，只有「贏過自己的 warm start」才會被收進來，
            # 不會讓整體變差。
            nlp_refined = self._generate_nlp_refined_seed_candidates(
                num_burns, n_seeds, relay + ladder + pcsplit)
            return relay + ladder + pcsplit + nlp_refined

        dt = 60.0
        mu, j2, j3, j4, re = self.MU, self.J2_VAL, self.J3_VAL, self.J4_VAL, self.RE_VAL

        # B 軌道平面法向量 (t=0 時刻的近似，見上面docstring說明)，用來偵測 A 幾時
        # 靠近這個平面 (節線附近)。萬一 B_r0/B_v0 剛好共線 (理論上不該發生的退化
        # 軌道) h_B 會是零向量，正規化前先擋一下避免除以零。
        h_B = np.cross(self.B_r0, self.B_v0)
        h_B_norm = fast_norm(h_B)
        h_B_hat = h_B / h_B_norm if h_B_norm > 1e-9 else np.array([0.0, 0.0, 1.0])

        # 第一步：粗掃 A 的距地距離 (窄窗來源1) 跟 A 到 B 軌道平面的垂直距離 (窄窗
        # 來源2)，找各自的局部極小值當候選窗口。共用同一次傳播迴圈算兩個指標。
        n_coarse = 400
        coarse_ts = np.linspace(0.0, self.T_max, n_coarse)
        dists = np.empty(n_coarse)
        plane_dists = np.empty(n_coarse)
        for i, t in enumerate(coarse_ts):
            r, _ = self.state_A(t)
            dists[i] = fast_norm(r)
            plane_dists[i] = abs(np.dot(r, h_B_hat))

        def _local_minima_idxs(values):
            idxs = []
            for i in range(n_coarse):
                left_ok = (i == 0) or (values[i] <= values[i - 1])
                right_ok = (i == n_coarse - 1) or (values[i] <= values[i + 1])
                if left_ok and right_ok:
                    idxs.append(i)
            return idxs

        # 兩種來源各自排序取前幾名，再合併去重——各自的候選數上限砍半，讓合併後
        # 的候選總數維持在原本 max(n_seeds*2, 5) 差不多的量級，不會因為多了一種
        # 來源就讓後面的中解析度掃描 (第二步) 的成本翻倍。
        per_source_cap = max(n_seeds, 3)
        earth_idxs = sorted(_local_minima_idxs(dists), key=lambda i: dists[i])[:per_source_cap]
        plane_idxs = sorted(_local_minima_idxs(plane_dists), key=lambda i: plane_dists[i])[:per_source_cap]
        candidate_idxs = list(dict.fromkeys(earth_idxs + plane_idxs))  # 保序去重

        lb, ub = self._generate_bounds(1)
        lb_arr, ub_arr = np.array(lb), np.array(ub)
        step_coarse = self.T_max / (n_coarse - 1)
        flight_times = np.array([600.0, 1800.0, 3600.0, 7200.0, 14400.0, 43200.0, 86400.0])

        # 第二步 (中解析度)：對每個候選窗口找一個粗略還不錯的 (tw, ft)。這一步刻意
        # 便宜 (~290 秒間隔)，只用來從一堆候選窗口裡篩出「真的有搞頭」的那幾個，
        # 不追求精準——真正要靠這個解析度直接找到最佳解不夠細，見下一步。
        rough_hits = []  # [(best_dv, idx, best_tw, best_ft), ...]
        for idx in candidate_idxs:
            center_t = coarse_ts[idx]
            best_dv, best_tw, best_ft = np.inf, None, None
            # 要對準的是「B 抵達的時間」(tw+ft) 接近 center_t (A 靠近地球的那個
            # 時間點)，不是「B 出發的時間」(tw) 本身——出發時間沒有直接的物理意義，
            # flight_time 拉長時這兩者可以差到快一整天，如果誤把 tw 對準 center_t，
            # flight_time 一大就會搜到 A 早就已經飛遠的地方去。所以 flight_time 放
            # 外層，每個 flight_time 各自反推出對應的 tw 搜尋中心 (center_t - ft)。
            for ft in flight_times:
                tw_center = center_t - ft
                local_tws = np.linspace(
                    max(0.0, tw_center - step_coarse), min(self.T_max, tw_center + step_coarse), 21
                )
                for tw in local_tws:
                    if ft < self.MIN_COAST_TIME or tw < 0.0 or tw + ft > self.T_max:
                        continue
                    r_b, v_b = self.state_B(tw)
                    r_a, _ = self.state_A(tw + ft)
                    for prograde in (True, False):
                        try:
                            v1, _ = lambert_izzo(mu, r_b, r_a, ft, M=0, prograde=prograde,
                                         lowpath=True)
                            dv = fast_norm(v1 - v_b)
                        except Exception:
                            continue
                        # 種子的安檢要跟真正的評估函式**用同一套**，不然挑出來的種子
                        # 有很高機率一開局就是 0 分。2026-08-28 起評估函式改成只在
                        # 這段弧真的會經過近地點時才比近地點半徑，這裡跟著改。
                        # ⚠️ 這裡**故意**只用 M=0，不是漏改。
                        # 這段的職責是「挑哪個 (t_wait, flight_time) 窗口當種子」，是個
                        # **啟發式排序**；種子真正的價值由 fast_fitness_evaluator 決定，
                        # 而它會掃過所有 Lambert 分支 (含多圈)。所以種子早就享受得到多圈
                        # 的好處。2026-08-28 試著把這個排序也換成含多圈的 _best_lambert，
                        # 實測反而變差 (known_phasing、LAMBERT_MAX_REVS=4：最好的種子從
                        # 166.1 m/s 合法變成 3,940.7 m/s 違規)——含多圈的 dv 排序會挑到
                        # 不同的窗口，而那些窗口在完整評估下比較差。已還原。
                        if reaches_perigee(r_b, v1, mu, ft) and \
                                not check_constraints(r_b, v1, mu, self.MIN_PERIAPSIS):
                            continue
                        if dv < best_dv:
                            best_dv, best_tw, best_ft = dv, tw, ft
            if best_tw is not None:
                rough_hits.append((best_dv, idx, best_tw, best_ft))

        # 第三步 (細解析度精修)：只對第二步真正成功、而且 Δv 排名前面的候選做——
        # 不是對 candidate_idxs 全部都做，避免 n_seeds 開很大 (例如族群大時 5% 換算
        # 出幾十個) 但真正存在的候選窗口沒那麼多時，浪費時間細修一堆本來就要被
        # 丟棄的候選。這一步刻意不用梯度類方法 (L-BFGS-B 之類)——實測過 (2026-08-14)
        # Δv 超標的懲罰是離散跳躍不是平滑漸變，梯度法在這種斷點附近會瞎眼，明明
        # 只差幾百秒就跨進合法範圍，梯度法完全不會移動過去。網格搜尋雖然單次評估
        # 比較笨，但保證不會跳過比步長還寬的窗口，這正是這裡需要的特性 (跟
        # STATUS.md「weird_test.json 深度診斷」那節手動驗證過的方法一致)。
        rough_hits.sort(key=lambda h: h[0])
        seeds = []
        for _, idx, rough_tw, rough_ft in rough_hits[:n_seeds]:
            best_dv, best_tw, best_ft = np.inf, rough_tw, rough_ft
            fine_tw_span = step_coarse / 10.0
            fine_ft_span = max(600.0, rough_ft * 0.3)
            fine_tws = np.linspace(
                max(0.0, rough_tw - fine_tw_span), min(self.T_max, rough_tw + fine_tw_span), 25
            )
            fine_fts = np.linspace(max(self.MIN_COAST_TIME, rough_ft - fine_ft_span), rough_ft + fine_ft_span, 11)
            for tw in fine_tws:
                r_b, v_b = self.state_B(tw)
                for ft in fine_fts:
                    if ft < self.MIN_COAST_TIME or tw + ft > self.T_max:
                        continue
                    r_a, _ = self.state_A(tw + ft)
                    for prograde in (True, False):
                        try:
                            v1, _ = lambert_izzo(mu, r_b, r_a, ft, M=0, prograde=prograde,
                                         lowpath=True)
                            dv = fast_norm(v1 - v_b)
                        except Exception:
                            continue
                        if reaches_perigee(r_b, v1, mu, ft) and \
                                not check_constraints(r_b, v1, mu, self.MIN_PERIAPSIS):
                            continue
                        if dv < best_dv:
                            best_dv, best_tw, best_ft = dv, tw, ft

            max_final = self.T_max - best_tw
            if max_final > self.MIN_COAST_TIME:
                final_leg_frac = float(np.clip(
                    (best_ft - self.MIN_COAST_TIME) / (max_final - self.MIN_COAST_TIME), 0.0, 1.0
                ))
            else:
                final_leg_frac = 0.0
            # 瞄準點偏移全部給 0 (精準瞄準 A 的真實位置)——省油的偏移瞄準留給 L-SHADE
            # 自己在種子附近去探索，種子本身只負責把 t_wait/flight_time 帶對地方。
            x = np.array([best_tw, final_leg_frac, 0.0, 0.0, 0.0], dtype=np.float64)
            seeds.append(np.clip(x, lb_arr, ub_arr))

        return seeds

    @staticmethod
    def _narrow_tolerance_bounds(x, lb, ub):
        """
        給一個決策向量 x 算出一組「收緊過的邊界」，給局部 NLP 精修用——時間類變數
        (t_wait/coast_frac/final_leg_frac) 收緊到 2%，避免微調打亂已經算好的攔截
        時序；方向/瞄準類變數 (燃燒方向 r/theta/phi、瞄準點偏移) 放寬到 15%，這幾維
        本來就比較平滑，可以讓 NLP 多探索一點。

        原本這條規則只在 refine_trajectory() (跑完整個 run_study 後，對最終贏家做
        一次性的精修) 用；2026-08-15 抽出來變成共用方法，讓 _optimize_burn_case
        裡「每個種子單獨精修」那段也能用同一套規則，而不是原本寫死只認識單棒
        5 元素陣列的版本 (多棒的話索引對不上，精修會用錯容忍度)。

        陣列結構: [0]=t_wait，中間每 4 個一組 [r, theta, phi, coast_frac]，
        接著 [n-4]=final_leg_frac，最後三個 [n-3,n-2,n-1]=瞄準點偏移
        (offset_r, offset_theta, offset_phi)。num_burns==1 時中間沒有任何一組
        (n=5)，規則一樣適用 (i-1 迴圈範圍是空的，直接落到 offset/final_leg 判斷)。
        """
        n = len(x)
        bounds = []
        for i, (l, u) in enumerate(zip(lb, ub)):
            span = u - l
            is_offset_param = i >= n - 3
            is_final_leg = (i == n - 4)
            is_t_wait = (i == 0)
            if is_offset_param:
                tolerance = span * 0.15
            elif is_t_wait or is_final_leg:
                tolerance = span * 0.02
            else:
                tolerance = span * 0.15 if ((i - 1) % 4) < 3 else span * 0.02
            bounds.append((max(l, x[i] - tolerance), min(u, x[i] + tolerance)))
        return bounds

    def _generate_multiburn_seed_candidates(self, num_burns: int, n_seeds: int) -> list:
        """
        分段貪婪接力：把 num_burns==1 的種子候選，接到 num_burns 棒的決策向量格式，
        前面 (num_burns-1) 棒全部塞「Δv=0 的空燒、最短間隔滑行」，最後一棒沿用單棒
        種子找到的 (t_wait_final, final_leg_frac)。詳細動機見 _generate_seed_candidates
        的 docstring。

        這裡刻意不遞迴呼叫 self._generate_seed_candidates(1, n_seeds) (雖然邏輯上
        等價)，是因為要避免未來如果 _generate_seed_candidates 的 num_burns==1
        分支簽章改變時，這裡跟著遞迴呼叫容易搞錯是呼叫「哪一層」——直接呼叫同一個
        私有方法本身沒問題 (Python 遞迴呼叫 self 的方法就是正常的多型分派)，這裡
        寫成獨立方法只是讓「單棒種子生成」跟「多棒接力組裝」的職責分開，方便之後
        個別測試/替換其中一半 (例如以後想換掉接力策略，不用動單棒那段已經驗證過
        的邏輯)。
        """
        base_seeds = self._generate_seed_candidates(1, n_seeds)
        if not base_seeds:
            return []

        lb, ub = self._generate_bounds(num_burns)
        lb_arr, ub_arr = np.array(lb), np.array(ub)
        n_prefix_burns = num_burns - 1  # 前面要塞幾棒空燒

        seeds = []
        for base_x in base_seeds:
            t_wait_final, final_leg_frac = float(base_x[0]), float(base_x[1])
            # 前面 n_prefix_burns 棒都卡最短間隔，讓 current_time 從 t_wait 精確疊加
            # 到 t_wait_final；t_wait 本身往前推正好 n_prefix_burns 個 MIN_COAST_TIME。
            t_wait = t_wait_final - n_prefix_burns * self.MIN_COAST_TIME
            if t_wait < 0.0:
                # 單棒種子的時機太早，前面塞不下這麼多空燒——這個候選在這個棒數
                # 下沒有乾淨的接力方式，跳過 (仍有其他候選可用，不強求每個都成功)。
                continue

            x = [t_wait]
            for _ in range(n_prefix_burns):
                # 球座標 (r, theta, phi, coast_frac)：r=0 天生合法 (Δv 大小為0)，
                # theta/phi 在 r=0 時無意義，填 0 即可；coast_frac=0 對應最短滑行。
                x.extend([0.0, 0.0, 0.0, 0.0])
            x.extend([final_leg_frac, 0.0, 0.0, 0.0])  # 最後一棒 + 瞄準偏移全部置中
            x = np.clip(np.array(x, dtype=np.float64), lb_arr, ub_arr)
            seeds.append(x)

        return seeds

    def _orbit_radius_range(self, r0, v0) -> Tuple[float, float]:
        """從狀態向量算這條軌道的 (近地點半徑, 遠地點半徑)。雙曲線遠地點回傳 inf。"""
        r = fast_norm(r0)
        v = fast_norm(v0)
        energy = v * v / 2.0 - self.MU / r
        h = fast_norm(np.cross(r0, v0))
        if abs(energy) < 1e-14:
            return r, float("inf")
        a = -self.MU / (2.0 * energy)
        ecc = math.sqrt(max(0.0, 1.0 + 2.0 * energy * h * h / (self.MU * self.MU)))
        rp = a * (1.0 - ecc)
        ra = a * (1.0 + ecc) if a > 0 else float("inf")
        return rp, ra

    def energy_floor_dv(self) -> float:
        """
        B 要讓自己的軌道半徑範圍碰到 A 的半徑範圍，最少要花多少 Δv (km/s)。

        封閉解、微秒等級，所以可以無條件算，不會拖慢任何情境。這是**下限不是可達值**：
        只算「把軌道撐大/縮小到範圍重疊」的能量成本，沒算平面差、相位、命中精度，
        真正需要的 Δv 一定 >= 這個值。用途是判斷「單棒在能量上是不是根本不可能」——
        如果連這個下限都超過每棒上限，那再怎麼調時機也不可能有合法單棒解。
        """
        rp_b, ra_b = self._orbit_radius_range(self.B_r0, self.B_v0)
        rp_a, ra_a = self._orbit_radius_range(self.A_r0, self.A_v0)
        if ra_b >= rp_a and rp_b <= ra_a:
            return 0.0  # 半徑範圍已經重疊，能量上沒有硬門檻
        mu = self.MU
        if ra_b < rp_a:
            # B 整條軌道都在 A 內側：在 B 的近地點沿速度方向燒，把遠地點抬到 A 的近地點
            a_b = (rp_b + ra_b) / 2.0
            v_now = math.sqrt(mu * (2.0 / rp_b - 1.0 / a_b))
            v_need = math.sqrt(mu * (2.0 / rp_b - 2.0 / (rp_b + rp_a)))
            return max(0.0, v_need - v_now)
        # B 整條軌道都在 A 外側：在 B 的遠地點減速，把近地點壓到 A 的遠地點
        a_b = (rp_b + ra_b) / 2.0
        v_now = math.sqrt(mu * (2.0 / ra_b - 1.0 / a_b))
        v_need = math.sqrt(mu * (2.0 / ra_b - 2.0 / (ra_b + ra_a)))
        return abs(v_now - v_need)

    def _split_aware_dv_ub(self) -> float:
        """SPLIT_AWARE_SEARCH 開時，中間棒 Δv 大小的上界 (km/s)——B1（2026-09-22）。

        取代舊的「永遠 SPLIT_AWARE_MAX_FACTOR × MAX_DV」：那個 factor 是猜的，設低漏解、
        設高稀釋 DE 解析度。改由情境**實際能量差** energy_floor_dv() 算出「夠用」的上界：
            dv_ub = clamp( ⌈floor/cap⌉·cap + margin ,  MAX_DV_SOFT ,  MAX_FACTOR·MAX_DV )
        低能量差（軌道半徑範圍已重疊，floor≈0）自動收窄到 ~1×cap（不放寬、不稀釋搜尋）；
        高能量差（雙曲線飛掠很可能，floor 遠超 cap）自動放寬到夠用、但仍夾在 MAX_FACTOR·MAX_DV
        這個硬天花板內。energy_floor_dv() 是封閉解、微秒級，無條件算不拖慢。

        物理：SPLIT_AWARE 的中間棒代表「一個之後會被拆成多發合法燒的大節點」，它要能承載的
        最大衝量，量級就是把 B/A 軌道能量差一次交割所需的 Δv（≥floor），⌈floor/cap⌉·cap 是
        「用整數發 cap 蓋過那個能量差」的量，margin 給 DE 一點超出下限的迴旋。"""
        hard_cap = float(self.SPLIT_AWARE_MAX_FACTOR) * self.MAX_DV
        cap = self.MAX_DV
        if cap <= 0.0:
            return hard_cap
        floor = self.energy_floor_dv()          # km/s，封閉解
        needed = math.ceil(floor / cap) * cap + cap   # margin = 一發 cap
        # 只放寬、不收到比預設 MAX_DV_SOFT 還緊；也不超過 MAX_FACTOR·MAX_DV 硬天花板
        return max(self.MAX_DV_SOFT, min(hard_cap, needed))

    @staticmethod
    def _direction_to_spherical(u) -> Tuple[float, float]:
        """把單位方向向量轉成決策向量用的 (theta, phi)，跟 _replay_mission 的
        dv_vec = r*[sin(t)cos(p), sin(t)sin(p), cos(t)] 這組公式互為反函數。"""
        uz = float(np.clip(u[2], -1.0, 1.0))
        theta = math.acos(uz)
        phi = math.atan2(float(u[1]), float(u[0]))
        if phi < 0.0:
            phi += 2.0 * math.pi
        return theta, phi

    def _generate_ladder_seed_candidates(self, num_burns: int, n_seeds: int) -> list:
        """
        「近地點連續推進」種子 (2026-08-15 新增)：專門補上分段貪婪接力種子的結構性盲區。

        為什麼需要：_generate_multiburn_seed_candidates 產生的多棒種子，前面每一棒都是
        Δv=0 的空燒——它本質上是「偽裝成多棒的單棒解」，從來不會猜測「中間棒該燒多少」。
        單棒夠用的情境下這完全正確 (實測過四組情境都會正確退化回單棒)，但遇到「單棒在
        能量上根本不可能」的情境就整批落在錯誤的區域：實測 hard_mode_test.json (B 在
        6800km 圓軌道、A 的近地點在 50000km 外) 時，已經證明存在合法 3 棒解
        (1100+600+1485 m/s、0 違規)，但三個燃燒次數案例全部退化成同一個違規單棒解
        (2924.8 m/s)，中間棒依然是 0。

        這裡改成用物理構造直接生成「真的有燒」的種子：在 B 的近地點附近沿速度方向連續
        推進 (Oberth 效率最高)，每次之間滑行整數個週期回到同一個近地點，最後一棒用
        Lambert 收尾。這個構造在 hard_mode 的離線驗證裡找到 382 組合法解，證明它涵蓋
        得到正確答案所在的區域。

        成本控制：只有 energy_floor_dv() 超過每棒上限時才會跑 (封閉解判斷，微秒等級)，
        所以單棒就搆得到的一般情境完全不受影響。真的要跑時也不做暴力掃描——燃燒大小
        直接從能量下限反推 (只試幾種分配策略)，滑行時間只試整數倍週期，真正需要掃的
        只有最後一段 Lambert 飛行時間。
        """
        if num_burns < 2 or n_seeds <= 0:
            return []
        floor = self.energy_floor_dv()
        if floor <= self.MAX_DV_SOFT:
            return []  # 單棒在能量上就搆得到，不需要階梯種子

        mu, dt = self.MU, 60.0
        j2, j3, j4, re = self.J2_VAL, self.J3_VAL, self.J4_VAL, self.RE_VAL
        cap = self.MAX_DV_SOFT
        n_climb = num_burns - 1  # 中間棒全部拿來爬升，最後一棒留給 Lambert
        lb, ub = self._generate_bounds(num_burns)
        lb_arr, ub_arr = np.array(lb), np.array(ub)

        rp_b, ra_b = self._orbit_radius_range(self.B_r0, self.B_v0)
        a_b = (rp_b + ra_b) / 2.0
        b_period = 2.0 * math.pi * math.sqrt(a_b ** 3 / mu)

        # 燃燒大小策略：不暴力掃，只試幾種「怎麼把 floor 分配給爬升棒」的分法。
        # 種子不需要最優，只要落在正確的區域，後面的 L-SHADE + NLP 會把它磨細。
        #
        # 2026-08-15 修：第一版只試「平均分配」跟「每棒燒滿」，n_climb==1 時兩者
        # 退化成同一個方案 (都是 cap)，等於只試了一種爬升高度。實測 A 的近地點在
        # 42,000km 那組情境時整批種子產不出來——爬升高度沒得選，最後一棒的 Lambert
        # 需求就固定了，剛好超標就全軍覆沒。改成沿著「爬多高」這個維度掃幾個比例。
        mag_plans = []
        for frac in (1.0, 0.85, 0.7, 0.55):
            per_burn = min(cap, floor * frac / n_climb)
            if per_burn > 0.05:                     # 太小的爬升沒意義
                mag_plans.append([per_burn] * n_climb)
        mag_plans.append([cap] * n_climb)           # 每棒燒滿 (爬最快)
        if n_climb >= 2:
            mag_plans.append([cap] + [max(0.2, floor - cap) / (n_climb - 1)] * (n_climb - 1))
        # 去掉重複的方案 (n_climb==1 且 floor>=cap 時上面幾種會撞在一起)
        seen = set()
        uniq = []
        for p in mag_plans:
            key = tuple(round(m, 6) for m in p)
            if key not in seen:
                seen.add(key)
                uniq.append(p)
        mag_plans = uniq

        seeds = []
        # 起燒時機：掃 B 前一個週期內的幾個點 (圓軌道沒有特定近地點，掃幾個就夠；
        # 橢圓軌道則會掃到近地點附近，Oberth 效率最高的位置自然勝出)
        for t_wait in np.linspace(0.0, b_period, 5, endpoint=False):
            for mags in mag_plans:
                r_cur, v_cur = self.state_B(float(t_wait))
                cur_t = float(t_wait)
                legs = []      # 每棒的 (r, theta, phi, coast_frac)
                ok = True
                for k, mag in enumerate(mags):
                    v_hat = v_cur / fast_norm(v_cur)
                    theta, phi = self._direction_to_spherical(v_hat)
                    v_new = v_cur + v_hat * mag
                    if not check_constraints(r_cur, v_new, mu, self.MIN_PERIAPSIS):
                        ok = False
                        break
                    sp = fast_norm(v_new) ** 2 / 2.0 - mu / fast_norm(r_cur)
                    if sp >= 0.0:
                        ok = False   # 逃逸了，對攔截沒意義
                        break
                    a_new = -mu / (2.0 * sp)
                    # 滑行整整一圈回到同一個近地點，下一棒才吃得到一樣的 Oberth 效率
                    t_coast = 2.0 * math.pi * math.sqrt(a_new ** 3 / mu)
                    max_coast = self.T_max - cur_t - self.MIN_COAST_TIME
                    if max_coast <= self.MIN_COAST_TIME or t_coast >= max_coast:
                        ok = False
                        break
                    coast_frac = (t_coast - self.MIN_COAST_TIME) / (max_coast - self.MIN_COAST_TIME)
                    legs.append((mag, theta, phi, float(np.clip(coast_frac, 0.0, 1.0))))
                    r_cur, v_cur = propagate_dop853(r_cur, v_new, t_coast, dt, mu, j2, j3, j4, re)
                    cur_t += t_coast
                if not ok or len(legs) != n_climb:
                    continue

                # 最後一棒：掃飛行時間，找 Lambert 需求最小且合法的那個
                max_final = self.T_max - cur_t
                if max_final <= self.MIN_COAST_TIME:
                    continue
                # 最後一段飛行時間的取樣密度：這是整個構造裡唯一真的需要掃的維度，
                # 太粗就會整批漏掉。2026-08-15 修：第一版固定 40 點，但 max_final
                # 可以長達好幾天 (例如 724,000s -> 每格 18,500s)，而 A 的週期只有
                # 184,000s，等於每圈只取樣 10 個點，能命中的窗口比這細得多，實測
                # 整批種子產不出來。改成依「這段時間裡 A 會繞幾圈」決定點數，每圈
                # 至少取樣 60 個點，並夾在 [60, 600] 之間控制成本。
                a_period = getattr(self, "Ta_sec", 0.0) or (max_final / 4.0)
                revs = max(1.0, max_final / a_period)
                n_ft = int(min(600, max(60, 60 * revs)))
                best = None
                for ft in np.linspace(self.MIN_COAST_TIME, max_final, n_ft):
                    r_a, _ = self.state_A(cur_t + float(ft))
                    for prograde in (True, False):
                        try:
                            v1, _ = lambert_izzo(mu, r_cur, r_a, float(ft), M=0, prograde=prograde,
                                          lowpath=True)
                        except Exception:
                            continue
                        dv = fast_norm(v1 - v_cur)
                        if dv <= cap and (best is None or dv < best[0]):
                            best = (dv, float(ft))
                if best is None:
                    continue
                final_leg_frac = (best[1] - self.MIN_COAST_TIME) / (max_final - self.MIN_COAST_TIME)

                x = [float(t_wait)]
                for (mag, theta, phi, cf) in legs:
                    x.extend([mag, theta, phi, cf])
                x.extend([float(np.clip(final_leg_frac, 0.0, 1.0)), 0.0, 0.0, 0.0])
                seeds.append((best[0], np.clip(np.array(x, dtype=np.float64), lb_arr, ub_arr)))

        # 最後一棒需求最小的優先 (代表這個階梯把 B 送到最有利的位置)
        seeds.sort(key=lambda s: s[0])
        return [x for _, x in seeds[:n_seeds]]

    def _generate_planechange_split_seed_candidates(self, num_burns: int, n_seeds: int) -> list:
        """
        「抬高+換面 → 平均拆收尾」種子 (2026-09-05 新增)。

        補上 relay / ladder 兩種種子的盲區：大傾角差 + 撞地球約束下，最佳合法解的結構是
        「第一棒抬高並換面 (往上飛、避開地球)，滑行到遠地點附近，再把昂貴的換面/攔截機動
        **平均拆成數段合法燒**」。relay 是空燒單棒、ladder 沿速度方向爬升 (不換面)，兩者
        都到不了這個家族。初賽情境 (A/B 軌道平面夾角 80°、快速直飛會鑽到地表下) 的最佳
        合法解正是這一類——純隨機 / relay / ladder 都找不到，靠這個構造當種子才進得去
        (見 outputs/best_98.31_split5_rebalanced/SUMMARY.md、STATUS.md 2026-09-05)。

        只有 A/B 軌道平面夾角夠大 (>30°) 才跑；一般情境回空清單，不動既有行為。整段構造
        用跟 fast_fitness_evaluator 完全相同的碰撞判定 (reaches_perigee + check_constraints)，
        所以產出的種子保證是 Earth-safe 的合法起點，不是撞地球的假解。
        """
        if num_burns < 2 or n_seeds <= 0:
            return []
        mu, dt = self.MU, 60.0
        j2, j3, j4, re = self.J2_VAL, self.J3_VAL, self.J4_VAL, self.RE_VAL
        h_B = np.cross(self.B_r0, self.B_v0)
        h_A = np.cross(self.A_r0, self.A_v0)
        nB, nA = fast_norm(h_B), fast_norm(h_A)
        if nB < 1e-9 or nA < 1e-9:
            return []
        plane_angle = math.degrees(math.acos(
            max(-1.0, min(1.0, float(np.dot(h_B, h_A) / (nB * nA))))))
        if plane_angle < 30.0:
            return []  # 換面不大，這種種子沒有存在意義，省成本

        cap = self.MAX_DV_SOFT
        n_final = num_burns - 1  # 第一棒抬高，其餘 (num_burns-1) 段拿來平均拆收尾機動
        lb, ub = self._generate_bounds(num_burns)
        lb_arr, ub_arr = np.array(lb), np.array(ub)

        def prop(r, v, tof):
            return propagate_dop853(r, v, float(tof), dt, mu, j2, j3, j4, re)

        def arc_safe(r, v, dtt):
            if reaches_perigee(r, v, mu, dtt):
                return check_constraints(r, v, mu, self.MIN_PERIAPSIS)
            r_end, _ = prop(r, v, dtt)
            return (fast_norm(r) >= self.MIN_PERIAPSIS
                    and fast_norm(r_end) >= self.MIN_PERIAPSIS)

        def lam_best(r0, r1, tof, vref):
            best, bv = 1e18, None
            for m in range(self.LAMBERT_MAX_REVS + 1):
                for lp in range(2):
                    if m == 0 and lp == 1:
                        continue
                    for pg in range(2):
                        try:
                            vt, _ = lambert_izzo(mu, r0, r1, float(tof), M=m,
                                         prograde=(pg == 0), lowpath=(lp == 0))
                        except Exception:
                            continue
                        d = fast_norm(vt - vref)
                        if d < best:
                            best, bv = d, vt
            return bv, best

        def split_even(r0, v0, t0, target, T, nseg):
            """從 (r0,v0,t0) 用 nseg 段等量 (間隔 MIN_COAST) 打到 target 於 T。
            回傳 (kicks, coasts) 或 None。每段都過 arc_safe，末段需 <= cap。"""
            r, v, t = r0.copy(), v0.copy(), t0
            kicks, coasts = [], []
            for s in range(nseg - 1):
                vd, _ = lam_best(r, target, T - t, v)
                if vd is None:
                    return None
                need = vd - v
                nn = fast_norm(need)
                if nn < 1e-12:
                    return None
                step = min(cap, nn / (nseg - s))  # 把剩餘需求平均分給剩下的段
                kk = need / nn * step
                if not arc_safe(r, v + kk, self.MIN_COAST_TIME):
                    return None
                kicks.append(kk)
                coasts.append(self.MIN_COAST_TIME)
                r, v = prop(r, v + kk, self.MIN_COAST_TIME)
                t += self.MIN_COAST_TIME
                if fast_norm(r) < self.MIN_PERIAPSIS:
                    return None
            vd, dvm = lam_best(r, target, T - t, v)
            if vd is None or dvm > cap or not arc_safe(r, vd, T - t):
                return None
            kicks.append(vd - v)
            return kicks, coasts

        a_period = getattr(self, "Ta_sec", 0.0) or (self.T_max / 4.0)
        candidates = []  # (neg_score, x) —— 依分數排序，優先高分 (T 早 + 總 Δv 低) 的基底

        for t_wait in (0.0, a_period * 0.05):
            rb, vb = self.state_B(t_wait)
            Vhat = vb / fast_norm(vb)
            Nhat = np.cross(rb, vb)
            Nhat = Nhat / fast_norm(Nhat)
            Bhat = np.cross(Vhat, Nhat)
            for cv in (0.5, 1.0):                    # V 分量 (抬高)
                for cn in (-1.0, -0.5, 0.5, 1.0):    # N 分量 (換面)
                    for cb in (-1.0, 0.0, 1.0):      # B 分量 (換面)
                        k = (cv * Vhat + cn * Nhat + cb * Bhat) * cap
                        km = fast_norm(k)
                        if km > cap:
                            k = k / km * cap
                        vb1 = vb + k
                        sp = fast_norm(vb1) ** 2 / 2.0 - mu / fast_norm(rb)
                        if sp >= 0.0:
                            continue  # 逃逸軌道，對攔截沒意義
                        a_new = -mu / (2.0 * sp)
                        new_period = 2.0 * math.pi * math.sqrt(a_new ** 3 / mu)
                        for coast_mult in (0.5, 0.75):   # 滑行到遠地點附近再連打
                            tc = coast_mult * new_period
                            if tc < self.MIN_COAST_TIME:
                                continue
                            if not arc_safe(rb, vb1, tc):
                                continue
                            rm, vm = prop(rb, vb1, tc)
                            if fast_norm(rm) < self.MIN_PERIAPSIS:
                                continue
                            t_mid = t_wait + tc
                            hi = min(t_mid + a_period * 1.2, self.T_max)
                            lo = t_mid + a_period * 0.3
                            if hi <= lo:
                                continue
                            for Tarr in np.linspace(lo, hi, 8):
                                r_a, _ = self.state_A(float(Tarr))
                                out = split_even(rm, vm, t_mid, r_a, float(Tarr), n_final)
                                if out is None:
                                    continue
                                fkicks, fcoasts = out
                                mags = [fast_norm(kk) * 1000.0 for kk in ([k] + fkicks)]
                                mid_kicks = [k] + fkicks[:-1]     # 中途棒 = burn1 + 收尾前段
                                mid_coasts = [tc] + fcoasts
                                x = [float(t_wait)]
                                cur = float(t_wait)
                                okx = True
                                for kk, cc in zip(mid_kicks, mid_coasts):
                                    kmag = fast_norm(kk)
                                    theta, phi = self._direction_to_spherical(
                                        kk / kmag if kmag > 1e-12 else np.array([0.0, 0.0, 1.0]))
                                    maxc = self.T_max - cur - self.MIN_COAST_TIME
                                    if maxc <= self.MIN_COAST_TIME:
                                        okx = False
                                        break
                                    cf = (cc - self.MIN_COAST_TIME) / (maxc - self.MIN_COAST_TIME)
                                    x.extend([kmag, theta, phi, float(np.clip(cf, 0.0, 1.0))])
                                    cur += cc
                                if not okx:
                                    continue
                                maxf = self.T_max - cur
                                if maxf <= self.MIN_COAST_TIME:
                                    continue
                                flf = (Tarr - cur - self.MIN_COAST_TIME) / (maxf - self.MIN_COAST_TIME)
                                x.extend([float(np.clip(flf, 0.0, 1.0)), 0.0, 0.0, 0.0])
                                if len(x) != decision_variable_dims(num_burns):
                                    continue
                                # 依真實分數排序：這個家族的重點是把 L-SHADE 種到「T 早
                                # (時間分高) + 總 Δv 不太離譜」那個高分基底，而不是挑總 Δv
                                # 最小 (那是 T 很晚、時間分幾乎歸零的慢解)。用跟正式計分
                                # 完全一樣的 calculate_score，瞄準點誤差取 0 (種子瞄 A 精確
                                # 位置，命中容許範圍的省油留給 L-SHADE/NLP 去挖)。
                                seed_score = calculate_score(
                                    min_distance_km=0.0, total_time_sec=float(Tarr),
                                    total_dv_mps=float(sum(mags)), penalty_count=0,
                                    k_t=self.k_t, C_t=self.C_t, k_v=self.k_v, C_v=self.C_v)
                                candidates.append(
                                    (-seed_score, np.clip(np.array(x, dtype=np.float64), lb_arr, ub_arr)))

        candidates.sort(key=lambda c: c[0])  # 分數高的優先 (neg_score 小)
        return [x for _, x in candidates[:n_seeds]]

    def _generate_nlp_refined_seed_candidates(self, num_burns: int, n_seeds: int,
                                               base_candidates: list) -> list:
        """對 relay/ladder/pcsplit 已經產出的種子，用帶顯式不等式約束的 SLSQP 再做一次
        局部聯合優化 (HAP-47，2026-09-10；研究過程見 HAP47_SPLIT_ALGORITHM_RESEARCH.md)。

        動機：`_optimize_burn_case` 本來就會對每個種子跑一次 L-BFGS-B 局部精修，但那一步
        只有 box bounds——近地點違規是靠 fitness/`calculate_score` 裡的懲罰擋，是個階梯
        函數 (不連續)，L-BFGS-B 拿不到「還差多少才會撞地球」這種連續梯度，只能在懲罰懸崖
        前面卡住，貼不了邊界。這裡改用 SLSQP + 顯式不等式約束 (近地點餘裕、命中容許、
        Lambert 差分修正器有沒有收斂)，才挖得到「幾棒貼滿 Δv 上限、其餘棒省下來」這種
        貼邊解——這正是 PoC 在既有 98.31 案例上找到、GMAT 驗證過的那個改善的來源
        (HAP47_SPLIT_ALGORITHM_RESEARCH.md §7.1)。

        跟 PoC (`scripts/research/hap47_poc_nlp_split.py`) 的差異：PoC 用的是「每棒 ECI
        Δv 直接當自由變數」的 Cartesian 表示法，但正式系統的最後一棒不是自由變數——是
        `reconstruct_mission_logs` 用 Lambert 解出來瞄準 `offset` 點的。這裡直接對現有的
        標準決策向量 (球座標 + coast_frac + final_leg_frac + offset) 做 SLSQP，完整重用
        `mission_metrics`/`reconstruct_mission_logs` 内建的 Lambert 掃描/`refine_lambert_burn`
        牛頓修正/近地點判定，不在第二個地方重寫一份物理邏輯。

        只挑 `base_candidates` 裡分數最高的少數幾個當 warm start (效能考量：每次
        `mission_metrics` 呼叫都要掃 Lambert + 牛頓迭代，比單純傳播貴很多，SLSQP 在
        4*num_burns+1 維上抓有限差分梯度又要再乘上好幾倍)，而且每個 SLSQP 結果都要贏過
        自己的 warm start 才會被收進來——精修絕對不會讓種子池變差，找不到更好的解時就
        大方回傳空/较短的列表。
        """
        if not self.ENABLE_NLP_SPLIT_REFINE:
            return []
        if num_burns < 2 or n_seeds <= 0 or not base_candidates:
            return []

        lb, ub = self._generate_bounds(num_burns)
        lb_arr, ub_arr = np.array(lb), np.array(ub)
        bounds = list(zip(lb, ub))

        # C4：旗標開時精修目標跟搜尋同一把尺 (拆後估計)。
        sc = "score_split_est" if self.SPLIT_AWARE_TERMINAL else "score"
        infeasible = {
            "score": -1e6, "score_split_est": -1e6, "miss_km": 1e6, "dc_converged": False,
            "earth_safe": False, "min_arc_radius_km": -1e6,
        }

        def safe_metrics(x):
            try:
                return self.mission_metrics(x, num_burns)
            except Exception:
                # reconstruct_mission_logs 對徹底無解的 Lambert 組合會丟 RuntimeError
                # (見該函式 docstring)——SLSQP 有限差分探路時可能踩到，不能讓它炸穿整個
                # 精修流程，回傳一組明確不可行的假資料讓 SLSQP 自己繞開即可。
                return infeasible

        def cached_metrics(x, _cache={}):
            key = np.asarray(x, dtype=np.float64).tobytes()
            if key not in _cache:
                _cache.clear()  # 只留最新一筆：SLSQP 同一輪迭代裡 objective/constraint
                                 # 對同一個 x 各呼叫一次，避免重算一整套 Lambert/牛頓迭代
                _cache[key] = safe_metrics(x)
            return _cache[key]

        def objective(x):
            return -cached_metrics(x)[sc]

        def constraint_fn(x):
            m = cached_metrics(x)
            dc_flag = 1.0 if m["dc_converged"] else -1.0
            return np.array([
                m["min_arc_radius_km"] - self.MIN_PERIAPSIS,
                self.MISS_TOLERANCE_SOFT - m["miss_km"],
                dc_flag,
            ])

        # 只挑分數最高的少數幾個 warm start，把總成本壓在「這個 num_burns 案例多花數十秒
        # 到一兩分鐘」的量級 (見上面 docstring 的效能小節)。
        scored = [(safe_metrics(x)[sc], x) for x in base_candidates]
        scored.sort(key=lambda t: t[0], reverse=True)
        warm_starts = scored[:min(len(scored), 3)]

        refined = []
        for score0, x0 in warm_starts:
            result = minimize(
                objective, np.asarray(x0, dtype=np.float64), method="SLSQP",
                bounds=bounds,
                constraints=[{"type": "ineq", "fun": constraint_fn}],
                options={"maxiter": 60, "ftol": 1e-10},
            )
            x1 = np.clip(result.x, lb_arr, ub_arr)
            m1 = safe_metrics(x1)
            if m1["earth_safe"] and m1["dc_converged"] and m1[sc] >= score0:
                refined.append(x1)

        return refined[:n_seeds]
