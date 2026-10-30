"""保存任務重播、指標、計分與合法性評估方法
主要入口為 MissionEvalMixin.mission_metrics。
"""
import numpy as np
from odc.scoring.scorer import (calculate_score, ranked_search_score, assess_legality,
                        SEARCH_FAIL_SCORE_RANKED, DV_LIMIT_TOL_MPS)
from odc.runlog import log, is_verbose
from odc.search.fitness import effective_burns
from odc.search.replay import reconstruct_mission_logs


class MissionEvalMixin:

    def split_est_score(self, burn_logs, miss_km, t_team, earth_safe) -> tuple:
        """拆後估計：(score_split_est, 可拆終端棒數, 可拆前導棒數)。

        終端棒超標、但 ≤ SPLIT_AWARE_TERMINAL_MAX_FACTOR × cap、且全程 Earth-safe (撞地球
        的解本來就不拆，見 HAP-48 閘門) 時，把那 −10 分加回來、改扣預付的拆棒燃料——跟
        fast_fitness_evaluator 旗標開時的算法一致。SPLIT_LEADING 開時，超標但
        ≤ LEADING_SPLIT_LIMIT 的前導棒也加回 −10、用 SPLIT_AWARE_DV_OVERHEAD 預付燃料
        (拆棒階段會先等分它，見 burn_splitter.presplit_leading)。不看 SPLIT_AWARE_TERMINAL，
        永遠算得出來；用不用由呼叫端依旗標決定。跟 score 一樣是搜尋/挑候選用的分數
        (含軟懲罰)，不是交件分數。"""
        leg = self.assess_burn_logs(burn_logs)
        n_soft, v_single = self._search_score_terms(leg, [bl['dv_mag'] for bl in burn_logs])
        total_dv = sum(bl['dv_mag'] for bl in burn_logs)
        term = burn_logs[-1]['dv_mag']
        lim = self.SPLIT_AWARE_TERMINAL_MAX_FACTOR * self.MAX_DV_SOFT
        if self.RANKING_RULES:
            lim = min(lim, self.SPLIT_LIMIT)   # 超出拆棒範圍的已經算進失格層，不能再加回 10 分
        n_split = int(bool(earth_safe) and (len(burn_logs) - 1) in leg["over_dv_legs"]
                      and term <= lim)
        if n_split:
            total_dv += term * (self.SPLIT_AWARE_TERMINAL_DV_OVERHEAD - 1.0)
        n_leading = 0
        if self.SPLIT_LEADING and earth_safe:
            for i in leg["over_dv_legs"]:
                d = burn_logs[i]['dv_mag']
                if i < len(burn_logs) - 1 and d <= self.LEADING_SPLIT_LIMIT:
                    n_leading += 1
                    total_dv += d * (self.SPLIT_AWARE_DV_OVERHEAD - 1.0)
        est = self.ranking_score(miss_km, t_team, total_dv * 1000.0,
                                 n_soft - n_split - n_leading, v_single)
        return est, n_split, n_leading

    def _search_score_terms(self, leg, dvs_kms) -> tuple:
        """最終判定 (assess_legality) → 搜尋用分數的兩個量：(n_soft, single_violation_mps)。
        n_soft = 每次 −10 的軟懲罰 (機動間隔違規 + 還拆得掉的單棒超標)；single_violation_mps =
        拆不掉的單棒超標量 (失格層用，見 scorer.ranked_search_score)。dvs_kms：每棒 Δv (km/s)。
        初賽模式：單棒超標一律 −10、沒有失格層，逐位元同舊行為。排位賽模式：只有終端棒、且
        ≤ SPLIT_LIMIT 才拆得掉；SPLIT_LEADING 開時，前導棒 ≤ LEADING_SPLIT_LIMIT 也可拆。
        其餘超標量算進失格層。SEARCH 開時搜尋端也使用相同的前導棒分類。"""
        if not self.RANKING_RULES:
            return leg["penalty_count"] + leg["over_dv_count"], 0.0
        n_soft, v = leg["penalty_count"], 0.0
        last = len(dvs_kms) - 1
        for i in leg["over_dv_legs"]:
            d = float(dvs_kms[i])
            if i == last and d <= self.SPLIT_LIMIT:
                n_soft += 1
            elif i != last and self.SPLIT_LEADING:
                if d <= self.LEADING_SPLIT_LIMIT:
                    n_soft += 1
                else:
                    v += (d - self.LEADING_SPLIT_LIMIT) * 1000.0
            else:
                v += (d - (self.SPLIT_LIMIT if i == last else self.MAX_DV_SOFT)) * 1000.0
        return n_soft, v

    def search_score(self, leg, dvs_kms, miss_km, t_team, total_dv_mps) -> float:
        """搜尋/挑候選用分數，直接吃最終判定 (assess_legality) 的結果。mission_metrics、
        _replay_mission、main 的拆棒結果都走這裡，跟 fast_fitness_evaluator 同一套分層。"""
        n_soft, v = self._search_score_terms(leg, dvs_kms)
        return self.ranking_score(miss_km, t_team, total_dv_mps, n_soft, v)

    def assess_burn_logs(self, burn_logs) -> dict:
        """最終交件判定 (odc.scoring.scorer.assess_legality) 套上這個 optimizer 的規則數字。"""
        return assess_legality([bl['dv_mag'] * 1000.0 for bl in burn_logs],
                               [bl['time'] for bl in burn_logs],
                               self.MAX_DV * 1000.0, self.MIN_COAST_TIME, self.MAX_TOTAL_DV_MPS)

    def ranking_score(self, miss_km, t_team, total_dv_mps, n_soft, single_violation_mps=0.0) -> float:
        """搜尋/挑候選用的分數：n_soft 次 −10 (機動間隔違規 + 還拆得掉的單棒超標)。排位賽模式下
        總 Δv 超標、或 single_violation_mps > 0 (拆不掉的單棒超標量) 時改回失格層 [−20, −10)，
        任何合法層候選 (≥ 0) 都排在它前面 (scorer.ranked_search_score)。跟 fast_fitness_evaluator
        同一套算法。合法解 (沒失格) 時等於官方分數；失格解的這個數字只拿來排「哪條路線值得
        拆棒」，不能當交件分數。"""
        sc = calculate_score(
            min_distance_km=miss_km, total_time_sec=t_team,
            total_dv_mps=total_dv_mps, penalty_count=n_soft,
            k_t=self.k_t, C_t=self.C_t, k_v=self.k_v, C_v=self.C_v)
        if self.RANKING_RULES:
            sc = ranked_search_score(sc, total_dv_mps, self.MAX_TOTAL_DV_MPS, single_violation_mps)
        return float(sc)

    def legality_fields(self, leg, miss_km, t_team) -> dict:
        """mission_info / metrics 共用的判定欄位。penalty_count 只算機動間隔違規 (官方扣分)；
        單棒/總 Δv 超標是失格 (disqualified)，失格解 official_score = None。"""
        official = None if leg["disqualified"] else float(calculate_score(
            min_distance_km=miss_km, total_time_sec=t_team,
            total_dv_mps=leg["total_dv_mps"], penalty_count=leg["penalty_count"],
            k_t=self.k_t, C_t=self.C_t, k_v=self.k_v, C_v=self.C_v))
        return {
            "penalty_count": int(leg["penalty_count"]),
            "over_dv_count": int(leg["over_dv_count"]),
            "total_dv_over": bool(leg["total_dv_over"]),
            "disqualified": bool(leg["disqualified"]),
            "dq_reasons": list(leg["dq_reasons"]),
            "official_score": official,
        }

    def mission_metrics(self, x, num_burns) -> dict:
        """安靜地把一組決策向量換算成官方成績的三個數字 + 分數，一個字都不印。

        跟 _replay_mission 走的是同一套重建流程 (reconstruct_mission_logs，含設定的
        重力階數)，差別只在不輸出。run_study() 挑贏家時要對每個燃燒次數的候選各算
        一次來做規則第 6 節的平手判定，不能用會印一整頁任務規劃的那個版本。

        注意：這裡的 total_dv / 判定 / 分數算法必須跟 _replay_mission 裡那段保持一致
        (兩邊都走 assess_burn_logs + ranking_score + legality_fields)。
        """
        burn_logs, times, miss_km, dc_converged, _r_aim, _retro, earth_safe, min_arc_radius_km = \
            reconstruct_mission_logs(
                x, num_burns, self.MIN_COAST_TIME, self.T_max,
                self.A_r0, self.A_v0, self.B_r0, self.B_v0,
                self.MU, self.J2_VAL, self.J3_VAL, self.J4_VAL, self.RE_VAL,
                self.LAMBERT_MAX_REVS, self.MIN_PERIAPSIS, ephem=self.ephem
            )
        total_dv = sum(log['dv_mag'] for log in burn_logs)
        t_team = float(times[-1])
        leg = self.assess_burn_logs(burn_logs)
        score = self.search_score(leg, [bl['dv_mag'] for bl in burn_logs], miss_km, t_team,
                                  total_dv * 1000.0)
        score_split_est, n_split, n_leading = self.split_est_score(burn_logs, miss_km, t_team, earth_safe)
        return {
            "score": float(score),
            "score_split_est": score_split_est,
            "split_terminal_count": n_split, "split_leading_count": n_leading,
            "miss_km": float(miss_km),
            "dv_mps": float(total_dv * 1000.0),
            "t_team": t_team,
            **self.legality_fields(leg, miss_km, t_team),
            "dc_converged": bool(dc_converged),
            "earth_safe": bool(earth_safe),
            "min_arc_radius_km": float(min_arc_radius_km),
        }

    def _replay_mission(self, x, num_burns):
        """純 Python 的日誌重建器，只在最後跑一次，並用含 J2 的高精度模型算出真實成績"""
        burn_logs, times, miss_km, dc_converged, r_aim, used_retrograde, earth_safe, min_arc_radius_km = \
            reconstruct_mission_logs(
                x, num_burns, self.MIN_COAST_TIME, self.T_max,
                self.A_r0, self.A_v0, self.B_r0, self.B_v0,
                self.MU, self.J2_VAL, self.J3_VAL, self.J4_VAL, self.RE_VAL,
                self.LAMBERT_MAX_REVS, self.MIN_PERIAPSIS, ephem=self.ephem
            )

        # 整份任務報告收進 lines、最後一次 log 出去（存進 mission_info["report_text"]，
        # 讓 REVS 集成能把勝出那趟的報告以 INFO 重印一次，不必重算）。層級 = self._report_level：
        # 單跑 INFO 直接顯示；集成時每趟被壓成 DEBUG，只重印勝出趟。
        lines = [f"\n── 任務規劃 {'─' * 46}",
                 f"  等待 {x[0]:,.1f}s 後開始，最後一棒 Lambert 走"
                 f"{'逆向 (retrograde)' if used_retrograde else '順向 (prograde)'}"]
        total_dv = sum(bl['dv_mag'] for bl in burn_logs)
        leg = self.assess_burn_logs(burn_logs)
        vnb_lines = []   # 每棒的 VNB 向量：診斷細節，走 DEBUG（-v console 顯示、log 檔永遠有、
                         # 預設 console 不印）——見準則：VNB 丟 -v 就好。
        for i, bl in enumerate(burn_logs):
            over_limit = i in leg["over_dv_legs"]
            flag = f"  🔴 超過 {self.MAX_DV*1000:.0f} m/s 上限（失格）" if over_limit else ""
            lines.append(f"  [{bl['type']:<10}] t={bl['time']:>12,.1f}s   "
                         f"Δv={bl['dv_mag']*1000:>8.1f} m/s{flag}")
            vnb_lines.append(f"  [{bl['type']:<10}] VNB={np.round(bl['dv_vnb'], 3)}")
        # 實際用到幾棒 (2026-08-15)：多棒解常常退化成「中間棒 Δv=0 的空燒」，光看棒數
        # 會以為用了多棒策略，其實跟更少棒的方案是同一個解。這裡直接講白，免得誤讀。
        eff = effective_burns(num_burns, x)
        if eff < num_burns:
            lines.append(f"  ⚠️ 這是 {num_burns} 棒的方案，但實際只用到 {eff} 棒"
                         f"（其餘是 Δv≈0 的空燒）——等價於 {eff} 棒解。")

        intercept_time = times[-1]
        penalty_count = leg["penalty_count"]
        # final_score = 搜尋/挑候選用分數 (拆得掉的單棒超標各 −10；排位賽模式下總 Δv 超標或拆不掉
        # 的超標進失格層)；沒失格時就是官方分數。
        final_score = self.search_score(leg, [bl['dv_mag'] for bl in burn_logs], miss_km,
                                        intercept_time, total_dv * 1000.0)
        legality = self.legality_fields(leg, miss_km, intercept_time)

        # 標題照實反映實際開的重力階數 (GRAVITY_DEGREE)，不要再寫死「含 J2」——
        # 2026-08-14 起這是可設定的 (0=點質量 / 2=J2 / 3=+J3 / 4=+J4)，寫死會誤導。
        grav = {0: "點質量", 2: "J2", 3: "J2+J3", 4: "J2+J3+J4"}.get(self.GRAVITY_DEGREE,
                                                                       f"degree={self.GRAVITY_DEGREE}")
        lines += [f"\n── Python 預測 ({grav}，不用開 GMAT) {'─' * 25}",
                  f"  Δr_min     {miss_km * 1000:>12,.1f} m   (門檻 5,000 m)",
                  f"  ΔV_team    {total_dv * 1000:>12,.1f} m/s"
                  + (f"   (上限 {self.MAX_TOTAL_DV_MPS:,.0f} m/s)" if self.MAX_TOTAL_DV_MPS is not None else ""),
                  f"  T_team     {intercept_time:>12,.1f} s",
                  f"  間隔違規   {penalty_count:>12d}"
                  + (f"   ⚠️ 機動間隔 < {self.MIN_COAST_TIME:.0f} s，每次扣 10 分" if penalty_count else "")]
        if legality["disqualified"]:
            lines += [f"  Score      {'🔴 失格':>10}   ——" + "；".join(legality["dq_reasons"]),
                      f"             (搜尋用分數 {final_score:.2f}，只代表路線值得拆棒，不是交件分數)"]
        else:
            lines.append(f"  Score      {final_score:>12.2f} / 100")
        score_split_est, n_split, n_leading = self.split_est_score(burn_logs, miss_km, intercept_time, earth_safe)
        if n_split or n_leading:
            split_desc = "、".join(([f"前導棒 {n_leading} 發"] if n_leading else [])
                                   + (["終端棒"] if n_split else []))
            lines.append(f"  拆後估計   {score_split_est:>12.2f} / 100   ({split_desc}可拆，"
                         f"{'搜尋/挑贏家用這個' if self.SPLIT_AWARE_TERMINAL else 'SPLIT_AWARE_TERMINAL 關，僅供參考'})")

        # Earth-safe 判定 (2026-09-09, HAP-48)：跟 fast_fitness_evaluator 一致的碰撞
        # 判定。初賽證實「軌跡穿過地表」是官方失格線,所以這條一定要印清楚、撞到就大聲擋。
        alt_km = min_arc_radius_km - self.RE_VAL
        safe_alt_km = self.MIN_PERIAPSIS - self.RE_VAL
        if earth_safe:
            lines.append(f"  Earth-safe    ✅   (全程最低高度 {alt_km:>10,.0f} km,門檻 {safe_alt_km:,.0f} km)")
        else:
            lines += [f"  Earth-safe    🔴 撞地球 (最低高度 {alt_km:,.0f} km < 門檻 {safe_alt_km:,.0f} km)"
                      f"——官方會判失格,絕對不可繳交（改找 Earth-safe 合法解 / 加大 T_max/棒數）。"]

        # 「荒謬超標」警告 (2026-08-15；排位賽起單棒超標已是失格，這行留著說明「多離譜」)：
        # 初賽時違規懲罰固定每次 -10 分、跟超標幅度無關，而最後一棒是
        # Lambert 反算、沒有上界。所以在根本沒有合法解的情境裡「花 10 分買完美命中」永遠划算，
        # 分數看起來很體面（實測 ECC=5 交出 611,787 m/s 卻回報 62.76）。分數忠於規則不改，但
        # 這種方案實務上交不出去（GMAT DC 的 Vary 邊界搆不到那個量級，一般版本必不收斂）——
        # 濃縮成一行警告；完整的「為什麼」寫在本段註解裡，不印到終端機上課。
        worst_ratio = max((bl['dv_mag'] / self.MAX_DV for bl in burn_logs), default=0.0)
        if worst_ratio > 3.0:
            lines.append(f"  🔴 最大單棒超標 {worst_ratio:.0f} 倍上限"
                         f"（{max(bl['dv_mag'] for bl in burn_logs)*1000:,.0f} vs 上限 "
                         f"{self.MAX_DV*1000:,.0f} m/s）——實務上交不出去(DC 收斂不到)，"
                         f"通常代表 T_max 內無合法解，見 feasibility.py。")
        if not dc_converged:
            lines.append("  ⚠️ 最後一棒差分修正未收斂——命中距離可能不可靠，"
                         "建議加大 refine_lambert_burn 的 max_iter。")

        report_text = "\n".join(lines)
        log.log(self._report_level, report_text)
        log.debug("── 各棒 VNB 分量 " + "─" * 40 + "\n" + "\n".join(vnb_lines))

        burns = [log['dv_vnb'] for log in burn_logs]
        times_diff = np.diff(times).tolist()
        # 回傳給最外層的 script_generator 使用，並附上完整的成績資訊供程式化存取
        mission_info = {
            "x": x, "num_burns": num_burns,
            "score": final_score, "miss_km": miss_km,
            "total_dv_mps": total_dv * 1000.0, "T_team": intercept_time,
            # C4 拆後估計 (見 split_est_score)。SPLIT_AWARE_TERMINAL 開時 REVS 集成 / C2 比這個。
            "score_split_est": score_split_est, "split_terminal_count": n_split, "split_leading_count": n_leading,
            **legality, "dc_converged": dc_converged,
            # GMAT script 的打靶目標要瞄準這個點 (EarthMJ2000Eq, km)，不是 ShipA 的
            # 真實位置，不然 GMAT 自己的 DC 會把刻意換來的省油設計修正掉。
            "aim_point": (float(r_aim[0]), float(r_aim[1]), float(r_aim[2])),
            # 最後一棒 (GMAT 會自己再修正的那把火) Python 端自己的預測值，方便跟
            # GMAT 實際收斂後的真實大小做對照。
            "final_burn_dv_mps": burn_logs[-1]["dv_mag"] * 1000.0,
            # Earth-safe 硬性閘門 (HAP-48)：main.py 用這個擋掉撞地球的解，不讓它產生
            # 繳交腳本。min_arc_radius_km 是全程實際到達過的最低軌道半徑 (km)。
            "earth_safe": bool(earth_safe),
            "min_arc_radius_km": float(min_arc_radius_km),
            # 這趟任務規劃 + Python 預測的完整報告文字，讓 REVS 集成能把勝出趟以 INFO
            # 重印一次（見 run_study_over_revs），不必重跑重播。
            "report_text": report_text,
        }
        return burns, times_diff, mission_info
