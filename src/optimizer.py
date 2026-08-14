import os
import math
import numpy as np
from numba import njit
from poliastro.core.iod import izzo
import concurrent.futures
import multiprocessing
import queue
import threading

from typing import Tuple
from scipy.optimize import minimize
from mealpy import FloatVar
from mealpy.evolutionary_based.SHADE import L_SHADE

from src.propagator import get_r0_v0
from src.scorer import calculate_score
from src.core_math import propagate_dop853, check_constraints, fast_norm, to_vnb_frame
import numba as nb
from tqdm import tqdm

# 這裡把所有不變的環境常數傳進來，避免 Numba 抓取外部全域變數
# nogil=True: 純數值運算 (內部呼叫的 propagate_dop853/izzo/calculate_score 也都是 njit)，
# 沒有碰任何 Python 物件，執行時可以釋放 GIL，讓 mealpy 的 'thread' 平行模式真的吃到多核。
@njit(nb.float64(nb.float64[:], nb.int64, nb.float64[:], nb.float64[:, :]), fastmath=True, cache=True, nogil=True)
def fast_fitness_evaluator(
    x: np.ndarray, num_burns: int, 
    scalars: np.ndarray, vectors: np.ndarray
) -> float:
    """
    100% 純 JIT 的適應度函數。沒有任何 Python 物件，直接吃 Mealpy 的一維陣列。
    """

    min_coast_time = scalars[0]
    T_max = scalars[1]
    mu = scalars[2]
    j2_val = scalars[3]
    j3_val = scalars[4]
    j4_val = scalars[5]
    re_val = scalars[6]
    min_periapsis = scalars[7]
    max_dv = scalars[8]
    k_t = scalars[9]
    C_t = scalars[10]
    k_v = scalars[11]
    C_v = scalars[12]

    A_r0 = vectors[0]
    A_v0 = vectors[1]
    B_r0 = vectors[2]
    B_v0 = vectors[3]

    total_dv = 0.0
    penalty_count = 0
    dt = 60.0  # DOP853 初始步長猜測 (自適應積分器會自己調整實際步長)

    # 1. 初始等待時間 (t_wait)
    current_time = float(x[0])
    
    # 傳播太空船 B 到第一次點火點
    r_curr, v_curr = propagate_dop853(B_r0, B_v0, current_time, dt, mu, j2_val, j3_val, j4_val, re_val)

    idx = 1
    # 2. 執行前 N-1 次機動 (如果 num_burns > 1)
    for _ in range(1, num_burns):
        # 球座標參數化 (r, theta, phi)：r 本身就是 Δv 大小，bounds 已經把 r 夾在
        # [0, MAX_DV_SOFT]，天生保證合規，不會再有「合成起來超標」的無效角落。
        dv_r = x[idx]
        dv_theta = x[idx+1]
        dv_phi = x[idx+2]
        coast_frac = x[idx+3]
        idx += 4

        sin_theta = math.sin(dv_theta)
        dv_vec = np.array([
            dv_r * sin_theta * math.cos(dv_phi),
            dv_r * sin_theta * math.sin(dv_phi),
            dv_r * math.cos(dv_theta)
        ], dtype=np.float64)

        dv_mag = dv_r  # 球座標半徑本身就是 Δv 大小，不用再算一次 norm
        total_dv += dv_mag
        if dv_mag > max_dv:  # 理論上不會發生了，留著當防呆
            penalty_count += 1

        v_curr_new = v_curr + dv_vec

        # 安檢：點火後會不會撞地球？
        if not check_constraints(r_curr, v_curr_new, mu, min_periapsis):
            return 0.0 # 直接判定 0 分 (極度差的適應度)

        # 計算這次的海岸滑行時間 (Coast Time)
        max_coast = T_max - current_time - min_coast_time
        t_coast = min_coast_time
        if max_coast > min_coast_time:
            t_coast += coast_frac * (max_coast - min_coast_time)
            
        # 傳播太空船 B 經過 Coast Time
        r_curr, v_curr = propagate_dop853(r_curr, v_curr_new, t_coast, dt, mu, j2_val, j3_val, j4_val, re_val)
        current_time += t_coast

    # 3. 最後一次機動 (Lambert 攔截)
    # 決定最後一段飛行時間
    final_leg_frac = x[-4]
    max_final = T_max - current_time
    t_final_leg = min_coast_time
    if max_final > min_coast_time:
        t_final_leg += final_leg_frac * (max_final - min_coast_time)

    intercept_time = current_time + t_final_leg

    # 傳播太空船 A (目標) 到攔截時間點
    r_A_target, _ = propagate_dop853(A_r0, A_v0, intercept_time, dt, mu, j2_val, j3_val, j4_val, re_val)

    # 規則只要求 Δr <= 門檻 (預設 5km)，Δr_min 超過命中點的部分不會多加分，所以不用
    # 死盯著 A 的精確位置打：球座標 (offset_r, offset_theta, offset_phi) 讓 Lambert
    # 改瞄準 A 附近容許球內、最省油的一點。offset_r 本身就是最終會落在的實際 Δr。
    offset_r = x[-3]
    offset_theta = x[-2]
    offset_phi = x[-1]
    sin_ot = math.sin(offset_theta)
    offset_vec = np.array([
        offset_r * sin_ot * math.cos(offset_phi),
        offset_r * sin_ot * math.sin(offset_phi),
        offset_r * math.cos(offset_theta)
    ], dtype=np.float64)
    r_aim = r_A_target + offset_vec

    # 呼叫 Poliastro 內建的純 Numba Lambert 求解器 (izzo)
    # izzo 回傳的是 (v1_req, v2_req)。順向/逆向兩種轉移都算一次，取 Δv 較小的那個 —
    # A/B 兩軌道傾角差大時，逆向解常常明顯省油，只算順向會漏掉更好的解。
    #
    # izzo 內部的 Householder/Halley 疊代對某些幾何 (轉移角接近 0°/180°、極端的
    # SMA 落差之類) 會直接丟 RuntimeError("Failed to converge")，不是回傳一個
    # 很爛的解——沒接住的話，L-SHADE 族群裡剛好抽到一個這種候選解，會讓整個
    # model.solve() 當掉，白白浪費掉那個燃燒次數案例已經算好的所有結果 (實測
    # 抓到過：測極端大 SMA 的情境時 3 個案例裡有 2 個因為這樣整組報廢)。跟
    # check_constraints 撞地球的處理方式一致：算不出來就當作這組候選解爛掉，
    # 回傳 0 分讓 L-SHADE 自然淘汰它，不要讓一個候選解拖垮整次搜尋。
    pro_ok = True
    v1_req_pro = np.zeros(3, dtype=np.float64)
    try:
        v1_req_pro, _ = izzo(
            mu, r_curr, r_aim, t_final_leg,
            M=0, prograde=True, lowpath=True, numiter=35, rtol=1e-8
        )
    except Exception:
        pro_ok = False

    retro_ok = True
    v1_req_retro = np.zeros(3, dtype=np.float64)
    try:
        v1_req_retro, _ = izzo(
            mu, r_curr, r_aim, t_final_leg,
            M=0, prograde=False, lowpath=True, numiter=35, rtol=1e-8
        )
    except Exception:
        retro_ok = False

    if not pro_ok and not retro_ok:
        return 0.0
    elif not retro_ok:
        v1_req = v1_req_pro
    elif not pro_ok:
        v1_req = v1_req_retro
    elif fast_norm(v1_req_retro - v_curr) < fast_norm(v1_req_pro - v_curr):
        v1_req = v1_req_retro
    else:
        v1_req = v1_req_pro

    # 計算需要的最後一次推力
    dv_final_vec = v1_req - v_curr
    dv_final_mag = fast_norm(dv_final_vec)
    total_dv += dv_final_mag

    if dv_final_mag > max_dv:
        penalty_count += 1

    # 最終安檢
    if not check_constraints(r_curr, v1_req, mu, min_periapsis):
        return 0.0

    # 4. 結算最終分數 (利用我們剛改好的 scorer)
    # min_distance_km 理論上就是 offset_r：Lambert 打的是瞄準點，瞄準點跟 A 的真實
    # 位置差 offset_r，只要 offset_r <= miss_tol (由 bounds 保證)，Δr_min 一律地板在
    # 5 (真正的規則門檻)，不會因為瞄準點刻意偏移而被扣分。
    score = calculate_score(
        min_distance_km=offset_r,
        total_time_sec=intercept_time,
        total_dv_mps=total_dv * 1000.0,
        penalty_count=penalty_count,
        k_t=k_t, C_t=C_t, k_v=k_v, C_v=C_v
    )

    # Mealpy 預設是找「最小值」，所以我們把分數加負號回傳
    return -score

def decision_variable_dims(num_burns: int) -> int:
    """
    _generate_bounds() 產生的決策變數維度：1 (t_wait) + 4*(num_burns-1) (中間燃燒的
    r/theta/phi/coast_frac) + 1 (final_leg_frac) + 3 (瞄準點偏移
    offset_r/theta/phi) = 4*num_burns + 1。

    抽成獨立函式 (不只是 _generate_bounds 內部算好就算了) 是因為 sweep_burns.py 的
    粗掃階段需要靠這個維度數去幫不同燃燒次數案例分配「公平」的世代預算——維度公式
    只准在這裡改一處，兩邊才不會兜不起來 (_generate_bounds 底部有一個 assert 會在
    公式不同步時立刻炸出來，不會安靜地算錯)。
    """
    return 4 * num_burns + 1


class MissionOptimizer:
    def __init__(self, config):
        self.config = config
        # run_study() 跑完後，這裡會存每個 MAX_BURNS 案例的 (raw_fitness, epochs_run, note)，
        # 不只是最終贏家——sweep_burns.py 用這個畫「燃燒次數 vs 分數」的趨勢表。
        # main.py 的正常流程不需要這個，只是額外多存一份，不影響 run_study() 原本的回傳值。
        self.burn_case_results: dict = {}
        # config 分兩塊環境設定：rules (主辦方規定/公告，我們不能改) 跟 strategy
        # (我們自己的任務設計選項，不是規則要求)。詳見 main.py 的 DEFAULT_CONFIG 註解。
        rules = config["rules"]
        strategy = config.get("strategy", {})

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
        # 搜尋/微調階段用的「內部目標」比規則的真實上限更嚴一點 (留 10 m/s 安全邊界)，
        # 避免 NLP 微調的數值梯度在邊界上把解推過真正的 ΔV_lim 那一側才被扣分。
        # 最終回報/合規判定 (_replay_mission) 仍然用 self.MAX_DV 這個真實規則上限去算。
        self.MAX_DV_SOFT = self.MAX_DV - 0.01
        self.MIN_COAST_TIME = float(rules.get("MIN_MANEUVER_INTERVAL_SEC", 100.0))

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
        # 固定隨機種子讓同一組設定可以重現一樣的結果，方便比較「改了東西到底有沒有用」。
        # 不設 (null/None) 就維持每次隨機，想探索不同解可以拿掉這個欄位。
        self.seed = config["optimization"].get("SEED")


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
        lb = [0.0]
        ub = [self.T_max]
        for _ in range(1, num_burns):
            lb.extend([0.0, 0.0, 0.0, 0.0])
            ub.extend([self.MAX_DV_SOFT, math.pi, 2.0 * math.pi, 1.0])
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

    def _optimize_burn_case(self, current_burns, scalar_params, vector_params, progress_queue=None):
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

        def fitness_wrapper(solution):
            return fast_fitness_evaluator(
                np.asarray(solution, dtype=np.float64), 
                current_burns, 
                scalar_params, 
                vector_params
            )

        problem = {
            "obj_func": fitness_wrapper,
            "bounds": [FloatVar(lb=l, ub=u) for l, u in zip(lb, ub)],
            "minmax": "min",    
            "log_to": None
        }

        case_maxiter = self._maxiter_for(current_burns)
        term_dict = {"max_early_stop": self.mes, "epsilon": self.tol}
        model = L_SHADE(epoch=case_maxiter, pop_size=pop_size, termination=term_dict)
        if progress_queue is not None:
            self._attach_progress_reporting(model, progress_queue, current_burns)

        # 外層已經用 ProcessPoolExecutor 依燃燒次數分配了核心 (num_cases 個 process)，
        # 這裡再把剩餘核心切給 mealpy 的 'thread' 模式，讓每一代的族群評估也平行跑。
        # fast_fitness_evaluator 已標記 nogil=True，thread 真的能吃到多核而不是被 GIL 卡住。
        # NUM_THREADS 設為正整數可強制指定每個 process 用幾條 thread；<=0 (含預設 -1) 則自動
        # 用 (可用核心數 / 燃燒次數情境數) 估一個合理值。
        num_cases = max(1, len(self.burns))
        if isinstance(self.num_threads, int) and self.num_threads > 0:
            n_workers = max(2, self.num_threads)
        else:
            n_workers = max(2, (os.cpu_count() or 4) // num_cases)
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
        if self.seed is not None:
            np.random.seed(self.seed)
            g_best = model.solve(problem, seed=self.seed)
        else:
            g_best = model.solve(problem, mode="thread", n_workers=n_workers, seed=self.seed)

        current_best_x = g_best.solution
        raw_fitness = g_best.target.fitness
        current_best_score = float(raw_fitness) if raw_fitness is not None else float('inf')

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

        # note 回傳給主行程印，不在這裡印 (見函式開頭的說明)
        return current_burns, current_best_x, current_best_score, epochs_run, note
    
    def run_study(self):
        print(f"🚀 啟動 JIT 極速版 L-SHADE 軌道最佳化 (多核心巨觀平行化)...")

        scalar_params = np.array([
            self.MIN_COAST_TIME, self.T_max, self.MU, self.J2_VAL, self.J3_VAL, self.J4_VAL,
            self.RE_VAL, self.MIN_PERIAPSIS, self.MAX_DV_SOFT, self.k_t, self.C_t, self.k_v, self.C_v
        ], dtype=np.float64)
        
        vector_params = np.vstack([
            self.A_r0, self.A_v0, self.B_r0, self.B_v0
        ])  
        
        best_overall_score = float('inf')  
        best_overall_params = None
        best_burns_count = 1

        # 開啟多行程池，最大核心數設定為你要測試的推進情境總數 (例如 burns = [1, 2, 3] 就是開 3 個)
        num_cases = len(self.burns)

        # 提交所有任務：把不同的 current_burns 丟給不同的核心。「開始計算」訊息在這裡
        # 印 (主行程)，不是在 _optimize_burn_case 裡 (子行程) 印——子行程不知道下面的
        # tqdm 進度條長什麼樣，兩邊搶著寫同一個終端機會讓進度條沒辦法原地覆寫，越跑
        # 越長 (見 _optimize_burn_case 開頭的說明)。
        print(f"⏳ 開始計算推進次數 {sorted(self.burns, reverse=True)} ...")

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
                        tqdm.write(f"✅ 推進 {b_count} 次完成：目標值 {best_score:.4f}，"
                                   f"跑了 {epochs_run}/{self._maxiter_for(b_count)} 代{note}")
                        self.burn_case_results[b_count] = {
                            "fitness": best_score, "epochs_run": epochs_run, "note": note,
                        }

                        if best_score < best_overall_score:
                            best_overall_score = best_score
                            best_overall_params = best_x
                            best_burns_count = b_count

                    except Exception as exc:
                        tqdm.write(f"❌ [核心錯誤] 推進 {b} 次案例崩潰: {exc}")
                    finally:
                        # 不管成功/失敗/提早停止，這個案例的份額都補滿到它自己的世代
                        # 預算——提早停止代表子行程回報的最後一則 epoch < 預算，崩潰的
                        # 案例可能完全沒回報過；兩種情況都要補滿，進度條才會在收工時
                        # 精準到 100%，不會卡在 99% 或某個案例的份額整段空白。
                        _bump_progress(b, self._maxiter_for(b))

            stop_draining.set()
            drain_thread.join(timeout=2.0)

        pbar.close()

        if best_overall_score >= 0.0 or best_overall_params is None:
            print("\n❌ 最佳化失敗：所有的嘗試都撞毀或違規了。")
            return None, None, (None, None)

        print(f"\n✅ 最佳化完成！採用推進 {best_burns_count} 次的方案 (目標值 {best_overall_score:.4f})")
        return self.refine_trajectory(best_overall_params, best_burns_count, best_overall_score)

    def refine_trajectory(self, initial_guess_x, num_burns, initial_fitness=None):
        print("\n🔬 啟動高精度 NLP 微調...")
        bounds = self._generate_bounds(num_burns)
        
        narrow_bounds = []
        n = len(initial_guess_x)
        for i, (lb, ub) in enumerate(zip(*bounds)):
            x_val = initial_guess_x[i]
            span = ub - lb
            # 陣列結構: [0]=t_wait，中間每 4 個一組 [r, theta, phi, coast_frac]，
            # 接著 [n-4]=final_leg_frac，最後三個 [n-3,n-2,n-1]=瞄準點偏移
            # (offset_r, offset_theta, offset_phi)。r/theta/phi 類 (燃燒的大小方向、
            # 瞄準點偏移方向) 給寬容度；時間類變數 (t_wait/coast_frac/final_leg_frac)
            # 給嚴格限制，避免微調打亂已經算好的攔截時序。
            is_offset_param = i >= n - 3
            is_final_leg = (i == n - 4)
            is_t_wait = (i == 0)
            if is_offset_param:
                tolerance = span * 0.15
            elif is_t_wait or is_final_leg:
                tolerance = span * 0.02
            else:
                tolerance = span * 0.15 if ((i - 1) % 4) < 3 else span * 0.02
            narrow_bounds.append((max(lb, x_val - tolerance), min(ub, x_val + tolerance)))
        
        scalar_params = np.array([
            self.MIN_COAST_TIME, self.T_max, self.MU, self.J2_VAL, self.J3_VAL, self.J4_VAL,
            self.RE_VAL, self.MIN_PERIAPSIS, self.MAX_DV_SOFT, self.k_t, self.C_t, self.k_v, self.C_v
        ], dtype=np.float64)
        
        vector_params = np.vstack([
            self.A_r0, self.A_v0, self.B_r0, self.B_v0
        ]) 

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
            options={'disp': True, 'maxiter': 50}
        )

        # 安全回退：L-BFGS-B 的 success 只代表「收斂了」，不代表「比原本的解更好」。
        # 目標函式裡有好幾處硬跳躍 (撞地球直接 0 分、超過 Δv 就扣分)，數值梯度在這種
        # 不連續的地方不可靠，微調完分數反而變差是有可能發生的，所以要實際比一次 fitness，
        # 沒有變好 (更小，因為 mealpy 是找最小值) 就退回微調前的解。
        if nlp_result.success and nlp_result.fun <= initial_fitness:
            res = nlp_result.x
            print(f"   ↳ NLP 微調有改善: {initial_fitness:.4f} -> {nlp_result.fun:.4f}，採用微調後的解")
        elif not nlp_result.success:
            # fun 可能其實有變小一點點，但 scipy 自己都不認為這是收斂的結果 (例如撞到
            # maxiter 上限)，保守起見不採用，訊息如實反映「未收斂」而不是「沒有改善」。
            res = initial_guess_x
            print(f"   ↳ NLP 微調未收斂 (scipy success=False，fitness {initial_fitness:.4f} -> "
                  f"{nlp_result.fun:.4f})，保守起見保留微調前的解")
        else:
            res = initial_guess_x
            print(f"   ↳ NLP 微調沒有改善 (微調前 {initial_fitness:.4f} / 微調後 {nlp_result.fun:.4f})，"
                  f"保留微調前的解")

        return self._replay_mission(res, num_burns)

    def _replay_mission(self, x, num_burns):
        """純 Python 的日誌重建器，只在最後跑一次，並用含 J2 的高精度模型算出真實成績"""
        print("\n📝 --- 任務執行清單 (Mission Plan) ---")
        burn_logs, times, miss_km, dc_converged, r_aim, used_retrograde = reconstruct_mission_logs(
            x, num_burns, self.MIN_COAST_TIME, self.T_max,
            self.A_r0, self.A_v0, self.B_r0, self.B_v0,
            self.MU, self.J2_VAL, self.J3_VAL, self.J4_VAL, self.RE_VAL
        )

        print(f"任務開始後等待: {x[0]:.1f} 秒")
        print(f"  最後一棒 Lambert 轉移方向: {'🔄 逆向 (retrograde)' if used_retrograde else '➡️ 順向 (prograde)'}")
        total_dv = 0.0
        penalty_count = 0
        for log in burn_logs:
            over_limit = log['dv_mag'] > self.MAX_DV
            total_dv += log['dv_mag']
            if over_limit:
                penalty_count += 1
            flag = "  ⚠️ 超過 1500 m/s 限制！" if over_limit else ""
            print(f"  [{log['type']}] 時間: {log['time']:.1f}s | 推力: {np.round(log['dv_vnb'], 3)} km/s | 大小: {log['dv_mag']*1000:.1f} m/s{flag}")

        intercept_time = times[-1]
        final_score = calculate_score(
            min_distance_km=miss_km,
            total_time_sec=intercept_time,
            total_dv_mps=total_dv * 1000.0,
            penalty_count=penalty_count,
            k_t=self.k_t, C_t=self.C_t, k_v=self.k_v, C_v=self.C_v
        )

        print("\n--- ⭐ 高精度 (含 J2) 收斂結果，不需開 GMAT 也能預覽 ---")
        print(f"  最終燃燒 DC 收斂狀態: {'✅ 已收斂' if dc_converged else '❌ 未收斂 (建議檢查此解或加大 refine_lambert_burn 的 max_iter)'}")
        print(f"  最小相對距離 Δr_min: {miss_km * 1000:.1f} m  (規則門檻 5000 m)")
        print(f"  總速度增量 ΔV_team: {total_dv * 1000:.1f} m/s")
        print(f"  任務完成時間 T_team: {intercept_time:.1f} s")
        print(f"  違規次數: {penalty_count}")
        print(f"  預估 Score: {final_score:.2f} / 100")

        burns = [log['dv_vnb'] for log in burn_logs]
        times_diff = np.diff(times).tolist()
        # 回傳給最外層的 script_generator 使用，並附上完整的成績資訊供程式化存取
        mission_info = {
            "x": x, "num_burns": num_burns,
            "score": final_score, "miss_km": miss_km,
            "total_dv_mps": total_dv * 1000.0, "T_team": intercept_time,
            "penalty_count": penalty_count, "dc_converged": dc_converged,
            # GMAT script 的打靶目標要瞄準這個點 (EarthMJ2000Eq, km)，不是 ShipA 的
            # 真實位置，不然 GMAT 自己的 DC 會把刻意換來的省油設計修正掉。
            "aim_point": (float(r_aim[0]), float(r_aim[1]), float(r_aim[2])),
            # 最後一棒 (GMAT 會自己再修正的那把火) Python 端自己的預測值，方便跟
            # GMAT 實際收斂後的真實大小做對照。
            "final_burn_dv_mps": burn_logs[-1]["dv_mag"] * 1000.0,
        }
        return burns, times_diff, mission_info

# --- 放在同一個檔案或 mission_evaluator.py 中的輔助函式 ---
def refine_lambert_burn(
    r_curr: np.ndarray, v1_guess: np.ndarray, r_target: np.ndarray, t_flight: float,
    mu: float, j2_val: float, j3_val: float, j4_val: float, re_val: float,
    dt: float = 10.0, tol_km: float = 0.05, max_iter: int = 8, fd_eps: float = 1e-4
):
    """
    Lambert (izzo) 給的 v1_guess 是「無擾動二體」下的理論解。
    這裡用含 J2(+J3+J4，視 GRAVITY_DEGREE 而定) 的高精度傳播器 (propagate_dop853)
    當作真實模型，對 v1_guess 做牛頓法微分修正 (有限差分算 3x3 Jacobian) ——
    邏輯上等同 GMAT 的 Target/Vary/Achieve (DC1) 在做的事，只是搬進 Python，
    讓我們不用真的打開 GMAT 也能拿到「加入重力擾動後仍收斂」的最終 Δv 與誤差。
    回傳: (v1_corrected, converged, final_miss_km, iterations)
    """
    v1 = v1_guess.copy()

    for it in range(max_iter):
        r_pred, _ = propagate_dop853(r_curr, v1, t_flight, dt, mu, j2_val, j3_val, j4_val, re_val)
        residual = r_target - r_pred
        miss = fast_norm(residual)
        if miss <= tol_km:
            return v1, True, miss, it

        # 有限差分 Jacobian：d(r_pred)/d(v1)，跟 GMAT Perturbation=0.0001 同量級
        jac = np.empty((3, 3), dtype=np.float64)
        for k in range(3):
            dv = np.zeros(3, dtype=np.float64)
            dv[k] = fd_eps
            r_pert, _ = propagate_dop853(r_curr, v1 + dv, t_flight, dt, mu, j2_val, j3_val, j4_val, re_val)
            jac[:, k] = (r_pert - r_pred) / fd_eps

        try:
            delta_v = np.linalg.solve(jac, residual)
        except np.linalg.LinAlgError:
            break
        v1 = v1 + delta_v

    r_pred, _ = propagate_dop853(r_curr, v1, t_flight, dt, mu, j2_val, j3_val, j4_val, re_val)
    miss = fast_norm(r_target - r_pred)
    return v1, miss <= tol_km, miss, max_iter


def reconstruct_mission_logs(x, num_burns, min_coast_time, T_max, A_r0, A_v0, B_r0, B_v0,
                              mu, j2_val, j3_val, j4_val, re_val):
    """
    一步一步重播最佳解，並把 VNB 轉換和時間記錄下來。
    因為不用 JIT，可以盡情使用 list 和 dict。
    """
    burn_logs = []
    times = [0.0]
    dt = 60.0  # DOP853 初始步長猜測 (自適應積分器會自己調整實際步長)
    
    current_time = float(x[0])
    times.append(current_time)
    r_curr, v_curr = propagate_dop853(B_r0, B_v0, current_time, dt, mu, j2_val, j3_val, j4_val, re_val)

    idx = 1
    for i in range(1, num_burns):
        # 跟 fast_fitness_evaluator 一致的球座標 (r, theta, phi) -> 直角座標轉換
        dv_r, dv_theta, dv_phi = x[idx], x[idx+1], x[idx+2]
        coast_frac = x[idx+3]
        idx += 4

        sin_theta = math.sin(dv_theta)
        dv_vec = np.array([
            dv_r * sin_theta * math.cos(dv_phi),
            dv_r * sin_theta * math.sin(dv_phi),
            dv_r * math.cos(dv_theta)
        ])

        dv_mag = dv_r
        dv_vnb = to_vnb_frame(r_curr, v_curr, dv_vec)
        
        burn_logs.append({"time": current_time, "dv_vec": dv_vec, "dv_vnb": dv_vnb, "dv_mag": dv_mag, "type": f"Burn {i}"})
        v_curr_new = v_curr + dv_vec
        
        max_coast = T_max - current_time - min_coast_time
        t_coast = min_coast_time + coast_frac * (max_coast - min_coast_time) if max_coast > min_coast_time else min_coast_time
        
        r_curr, v_curr = propagate_dop853(r_curr, v_curr_new, t_coast, dt, mu, j2_val, j3_val, j4_val, re_val)
        current_time += t_coast
        times.append(current_time)
        
    final_leg_frac = x[-4]
    max_final = T_max - current_time
    t_final_leg = min_coast_time + final_leg_frac * (max_final - min_coast_time) if max_final > min_coast_time else min_coast_time
    intercept_time = current_time + t_final_leg

    r_A_target, _ = propagate_dop853(A_r0, A_v0, intercept_time, dt, mu, j2_val, j3_val, j4_val, re_val)

    # 跟 fast_fitness_evaluator 一致：Lambert 瞄準的是 A 附近容許球內的偏移點
    # (offset_r/theta/phi)，不是 A 的精確位置，藉此換取更省油的轉移。
    offset_r, offset_theta, offset_phi = x[-3], x[-2], x[-1]
    sin_ot = math.sin(offset_theta)
    offset_vec = np.array([
        offset_r * sin_ot * math.cos(offset_phi),
        offset_r * sin_ot * math.sin(offset_phi),
        offset_r * math.cos(offset_theta)
    ])
    r_aim = r_A_target + offset_vec

    # 順向/逆向都算一次，取 Δv 較小的那個當初始猜測 (跟 fast_fitness_evaluator 邏輯一致)。
    # 這裡理論上不太會撞到 izzo 的 Failed to converge (fast_fitness_evaluator 已經把
    # 會崩潰的候選解擋在搜尋階段淘汰掉了，能走到重播這一步的解本來就是搜尋階段判定
    # 「算得出來」的那個)，但還是接住例外，萬一真的撞到給一句看得懂的錯誤，不要噴
    # poliastro 內部的 raw traceback。
    pro_ok, retro_ok = True, True
    try:
        v1_guess_pro, _ = izzo(mu, r_curr, r_aim, t_final_leg, M=0, prograde=True, lowpath=True, numiter=35, rtol=1e-8)
    except Exception:
        pro_ok = False
        v1_guess_pro = np.zeros(3)
    try:
        v1_guess_retro, _ = izzo(mu, r_curr, r_aim, t_final_leg, M=0, prograde=False, lowpath=True, numiter=35, rtol=1e-8)
    except Exception:
        retro_ok = False
        v1_guess_retro = np.zeros(3)

    if not pro_ok and not retro_ok:
        raise RuntimeError(
            "重播最佳解時，izzo Lambert 求解器兩個方向都沒收斂 (Failed to converge)——"
            "理論上不該發生 (搜尋階段已經會淘汰這種候選解)，如果真的看到這個訊息，"
            "代表這組解的幾何非常邊緣，回報這個狀況並檢查是不是要換一組軌道參數重跑。"
        )
    used_retrograde = retro_ok and (not pro_ok or fast_norm(v1_guess_retro - v_curr) < fast_norm(v1_guess_pro - v_curr))
    if used_retrograde:
        v1_guess = v1_guess_retro
    else:
        v1_guess = v1_guess_pro

    # 用含 J2 的高精度模型微分修正 Lambert 的理想化猜測值 (等同 GMAT DC1 在做的事)。
    # 注意：這裡修正的目標是瞄準點 r_aim，不是 A 的真實位置，回傳的 miss_km 只代表
    # 「有沒有準確命中瞄準點」，不是最終真正跟 A 差多遠 —— 後者要另外算 (見下)。
    v1_req, dc_converged, _miss_from_aim_km, _dc_iters = refine_lambert_burn(
        r_curr, v1_guess, r_aim, t_final_leg, mu, j2_val, j3_val, j4_val, re_val
    )

    dv_final_vec = v1_req - v_curr
    dv_final_mag = fast_norm(dv_final_vec)
    dv_final_vnb = to_vnb_frame(r_curr, v_curr, dv_final_vec)

    # 真正跟 A 的距離：用修正後的 v1_req 實際傳播一次，量測最終位置跟 A 真實位置
    # (不是瞄準點) 的距離 —— 這才是規則真正在乎、也是計分公式要用的 Δr。
    r_final_actual, _ = propagate_dop853(r_curr, v1_req, t_final_leg, 10.0, mu, j2_val, j3_val, j4_val, re_val)
    miss_km = fast_norm(r_final_actual - r_A_target)

    burn_logs.append({"time": current_time, "dv_vec": dv_final_vec, "dv_vnb": dv_final_vnb, "dv_mag": dv_final_mag, "type": "Final Burn"})
    times.append(intercept_time)

    # r_aim 一併回傳：GMAT script 的打靶目標要瞄準這個點，不能只瞄準 A 的真實位置，
    # 不然 GMAT 自己的 DC 會把我們刻意換來的省油設計修正掉 (詳見 script_generator)。
    return burn_logs, times, miss_km, dc_converged, r_aim, used_retrograde