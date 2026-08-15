"""
feasibility.py —— 開跑之前先問「這個情境到底有沒有合法解、有多難找」。

為什麼需要這支工具 (2026-08-15)：那天連續設計了四組極限測資，每一組都遇到同一個
問題——**搜尋跑完沒找到合法解時，分不清是「工具不夠力」還是「這題本來就無解」**。
沒有這個答案，測試結果完全無法解讀。當時是每組情境各寫一支拋棄式腳本去掃，這裡把
那套流程收斂成一支吃 config 的通用工具。

三層檢查，由便宜到貴：

  1. 能量下限（瞬間，而且是**證明**不是統計）
     B 的軌道半徑範圍如果跟 A 的完全不重疊，B 就必須先改變軌道能量才可能碰到 A。
     這個 Δv 有封閉解 (在 B 的近地點切向燒最省)，是真正的下限——任何解都不可能
     比它便宜。除以每棒上限就得到「至少需要幾棒」，不受網格解析度影響。

  2. 單棒 Lambert 網格（數十秒～數分鐘）
     掃 (起燒時機 x 飛行時間 x 順/逆行)，看合法單棒解存不存在、佔搜尋空間多少
     比例。這個比例就是難度：weird_test 是 0.0086% (L-SHADE 跑 2000 代都撞不到)，
     antialigned_highecc 是 16.53% (隨便找都有)。

  3. 多棒可行性（數分鐘～數十分鐘，--burns 才會跑）
     用「近地點連續推進 + 最後一棒 Lambert 收尾」這個構造去試 N 棒。這不是窮舉
     所有多棒策略，只是找一個存在性證明——找到就代表「至少有解」，找不到則不能
     斷定無解 (構造有侷限)，工具會照實講。

⚠️ 這支工具用的初始狀態直接來自 MissionOptimizer，跟真正的搜尋是同一份 A/B 位置、
   同一個 T_max、同一組規則數字。刻意不自己用 poliastro 重建一份——不然兩邊算的
   其實是不同的題目，結論就沒有意義。

用法：
    uv run feasibility.py --config configs/x.json              # 前兩層 (快)
    uv run feasibility.py --config configs/x.json --burns 3    # 加做 3 棒可行性
    uv run feasibility.py --config configs/x.json --grid 160   # 加密單棒網格
"""
import os
import sys
import math
import argparse
import warnings

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.optimizer import MissionOptimizer
from src.core_math import propagate_dop853, fast_norm
from main import load_or_create_config  # noqa: E402

warnings.filterwarnings("ignore")
from poliastro.core.iod import izzo  # noqa: E402


def floor_reason(rp_b, ra_b, rp_a, ra_a):
    """把能量下限為什麼>0 講成人話 (數值本身由 MissionOptimizer.energy_floor_dv 算)。"""
    if ra_b >= rp_a and rp_b <= ra_a:
        return "軌道半徑範圍已經重疊，能量上沒有硬門檻"
    if ra_b < rp_a:
        return f"B 的遠地點 {ra_b:,.0f} km 構不到 A 的近地點 {rp_a:,.0f} km"
    return f"B 的近地點 {rp_b:,.0f} km 還在 A 的遠地點 {ra_a:,.0f} km 外面"


def lambert_min_dv(mu, r0, v0, r_target, tof):
    best = float("inf")
    for prograde in (True, False):
        try:
            v1, _ = izzo(mu, r0, r_target, float(tof), M=0, prograde=prograde,
                          lowpath=True, numiter=35, rtol=1e-8)
        except Exception:
            continue
        best = min(best, fast_norm(v1 - v0))
    return best * 1000.0


def single_burn_sweep(opt, n_grid):
    """掃單棒 Lambert，回傳 (最小Δv, 合法數, 總數, 最佳位置)。"""
    mu, dt = opt.MU, 60.0
    j2, j3, j4, re = opt.J2_VAL, opt.J3_VAL, opt.J4_VAL, opt.RE_VAL
    cap = opt.MAX_DV * 1000.0
    T = opt.T_max
    best, best_at, legal, total = float("inf"), None, 0, 0
    for tb in np.linspace(0.0, T * 0.85, n_grid):
        r_b, v_b = propagate_dop853(opt.B_r0, opt.B_v0, float(tb), dt, mu, j2, j3, j4, re)
        max_ft = T - tb
        if max_ft < 600:
            continue
        for ft in np.linspace(600.0, max_ft, n_grid):
            r_a, _ = propagate_dop853(opt.A_r0, opt.A_v0, float(tb + ft), dt, mu, j2, j3, j4, re)
            dv = lambert_min_dv(mu, r_b, v_b, r_a, ft)
            if not math.isfinite(dv):
                continue
            total += 1
            if dv <= cap:
                legal += 1
            if dv < best:
                best, best_at = dv, (tb, ft)
    return best, legal, total, best_at


def multi_burn_probe(opt, n_burns):
    """
    用「近地點連續切向推進 + 最後一棒 Lambert」構造找 n_burns 棒的存在性證明。
    找到 -> 確定有解；找不到 -> 只能說這個構造沒找到，不等於無解。
    """
    mu, dt = opt.MU, 60.0
    j2, j3, j4, re = opt.J2_VAL, opt.J3_VAL, opt.J4_VAL, opt.RE_VAL
    cap = opt.MAX_DV * 1000.0
    T = opt.T_max
    rp_b, ra_b = opt._orbit_radius_range(opt.B_r0, opt.B_v0)
    a_b = (rp_b + ra_b) / 2.0 if math.isfinite(ra_b) else None
    b_per = 2 * math.pi * math.sqrt(a_b ** 3 / mu) if a_b else T / 8.0

    best = None
    n_legal = 0
    kick_levels = np.arange(600.0, cap + 1.0, 150.0)

    for t_wait in np.arange(0.0, min(b_per * 3, T * 0.3), b_per / 5):
        r_c, v_c = propagate_dop853(opt.B_r0, opt.B_v0, float(t_wait), dt, mu, j2, j3, j4, re)
        t_now = float(t_wait)
        # 逐棒往上疊：每一棒沿速度方向燒，然後滑行 (半圈/整圈) 再燒下一棒
        stack = [(r_c, v_c, t_now, [], 0.0)]
        for _ in range(n_burns - 1):
            nxt = []
            for (r_i, v_i, t_i, hist, acc) in stack:
                v_hat = v_i / fast_norm(v_i)
                for dv in kick_levels:
                    v_new = v_i + v_hat * (dv / 1000.0)
                    sp = fast_norm(v_new) ** 2 / 2.0 - mu / fast_norm(r_i)
                    if sp >= 0:
                        continue  # 逃逸了，對攔截沒意義
                    a_new = -mu / (2.0 * sp)
                    per = 2 * math.pi * math.sqrt(a_new ** 3 / mu)
                    for frac in (0.5, 1.0):
                        coast = per * frac
                        if t_i + coast >= T - 600:
                            continue
                        r_n, v_n = propagate_dop853(r_i, v_new, coast, dt, mu, j2, j3, j4, re)
                        nxt.append((r_n, v_n, t_i + coast, hist + [dv], acc + dv))
            # 控制爆炸：只留累計 Δv 最小的一批繼續往下疊
            nxt.sort(key=lambda s: s[4])
            stack = nxt[:60]
        for (r_f, v_f, t_f, hist, acc) in stack:
            max_ft = T - t_f
            if max_ft < 600:
                continue
            for ft in np.linspace(600.0, min(max_ft, T * 0.7), 26):
                r_a, _ = propagate_dop853(opt.A_r0, opt.A_v0, float(t_f + ft), dt, mu, j2, j3, j4, re)
                dv_final = lambert_min_dv(mu, r_f, v_f, r_a, ft)
                if not math.isfinite(dv_final) or dv_final > cap:
                    continue
                n_legal += 1
                total = acc + dv_final
                if best is None or total < best[0]:
                    best = (total, hist + [dv_final], t_f + ft)
    return best, n_legal


def main():
    ap = argparse.ArgumentParser(description="開跑前先確認這個情境有沒有合法解、有多難找")
    ap.add_argument("--config", default=os.path.join("configs", "config.json"))
    ap.add_argument("--grid", type=int, default=120, help="單棒網格解析度 (每軸點數，預設 120)")
    ap.add_argument("--burns", type=int, default=0,
                    help="額外檢查 N 棒可行性 (預設 0 = 不做，這步比較慢)")
    args = ap.parse_args()

    config = load_or_create_config(args.config)
    cfg = dict(config)
    cfg["optimization"] = dict(config["optimization"])
    cfg["optimization"]["MAX_BURNS"] = [1]
    opt = MissionOptimizer(cfg)
    mu = opt.MU
    cap = opt.MAX_DV * 1000.0

    # 半徑範圍跟能量下限都直接用 MissionOptimizer 的實作，不要在這裡重刻一份
    # ——兩邊各算各的，遲早會 drift 成不同的答案。
    rp_b, ra_b = opt._orbit_radius_range(opt.B_r0, opt.B_v0)
    rp_a, ra_a = opt._orbit_radius_range(opt.A_r0, opt.A_v0)

    print("=" * 70)
    print(f"可行性檢查：{args.config}")
    print("=" * 70)
    print(f"  A 半徑範圍 {rp_a:>12,.0f} ~ {ra_a:>12,.0f} km")
    print(f"  B 半徑範圍 {rp_b:>12,.0f} ~ {ra_b:>12,.0f} km")
    print(f"  T_max = {opt.T_max:,.0f}s ({opt.T_max/86400:.2f} 天)，每棒上限 {cap:,.0f} m/s")

    # --- 第 1 層：能量下限 (證明) ---
    print("\n" + "-" * 70)
    print("1. 能量下限（封閉解，是證明不是統計）")
    print("-" * 70)
    floor = opt.energy_floor_dv() * 1000.0
    print(f"  {floor_reason(rp_b, ra_b, rp_a, ra_a)}")
    if floor <= 0:
        print("  -> 能量上沒有硬門檻，單棒在能量層面是可能的（能不能命中要看下一層）")
        min_burns_energy = 1
    else:
        # 不要對爬升棒數再 +1 給「命中那一棒」——最後一棒的爬升跟命中是同一個動作
        # (Lambert 那一棒本來就會把剩下的能量差補完)。實測佐證：perigee_kick_test 的
        # 能量下限是 1.59 棒份，實際跑出來就是 2 棒解 (1283 + 1151，第二棒同時完成
        # 爬升與命中)，不是 3 棒。
        min_burns_energy = math.ceil(floor / cap)
        print(f"  -> 最小 Δv = {floor:,.1f} m/s（{floor/cap:.2f} 棒份）")
        print(f"  -> **至少** {min_burns_energy} 棒。單棒" +
              ("在數學上不可能合法。" if floor > cap else "可能吃緊。"))
        print(f"     這是下限不是答案：能量下限沒有把平面差、相位、命中精度算進去，")
        print(f"     實際需要的棒數只會 >= 這個值。(實測：hard_mode 的下限算出 2 棒，")
        print(f"     但 2 棒實際上 0 解、要 3 棒才有；perigee_kick 的下限 2 棒則剛好等於實際。)")

    # --- 第 2 層：單棒網格 ---
    print("\n" + "-" * 70)
    print(f"2. 單棒 Lambert 網格實掃（{args.grid}x{args.grid}x2）")
    print("-" * 70)
    best, legal, total, best_at = single_burn_sweep(opt, args.grid)
    rarity = 100.0 * legal / max(total, 1)
    print(f"  解出 {total:,} 組，最小單棒 Δv = {best:,.1f} m/s"
          f"（t_burn={best_at[0]:,.0f}s, flight={best_at[1]:,.0f}s）")
    print(f"  合法組合 = {legal:,}（{rarity:.4f}%）")
    if legal == 0:
        print("  🔴 這個解析度下找不到合法單棒解")
        if floor > cap:
            print("     （跟上面的能量下限一致，互相印證——單棒真的不可能）")
        else:
            print("     ⚠️ 但能量下限沒有排除單棒，可能是窄窗被網格跳過了"
                  "（weird_test 的合法窗只有 200 秒寬，600 秒步長就會整個錯過）。"
                  "\n        建議加大 --grid 再確認一次。")
    elif rarity < 0.05:
        print("  🔴 合法解極稀有——這是窄窗地形，隨機搜尋幾乎撞不到，"
              "要靠種子機制的網格粗掃")
    elif rarity < 1.0:
        print("  🟠 合法解稀有，搜尋需要種子機制幫忙")
    else:
        print("  🟢 合法解不罕見，單棒就能解，多半不需要多棒")

    # --- 第 3 層：多棒存在性 ---
    if args.burns >= 2:
        print("\n" + "-" * 70)
        print(f"3. {args.burns} 棒可行性（近地點連續推進 + Lambert 收尾）")
        print("-" * 70)
        res, n_legal = multi_burn_probe(opt, args.burns)
        if res:
            total_dv, hist, t_hit = res
            print(f"  ✅ 找到合法 {args.burns} 棒解（{n_legal:,} 組），最省的一組："
                  f"總 Δv = {total_dv:,.1f} m/s")
            print("     " + " + ".join(f"{d:,.0f}" for d in hist) + " m/s")
            print(f"     攔截於 t={t_hit:,.0f}s（{t_hit/86400:.2f} 天）")
            print(f"  -> 這個情境有解，搜尋失敗的話是工具的問題，不是題目無解")
        else:
            print(f"  🔴 這個構造沒找到合法 {args.burns} 棒解")
            print("     注意：這**不等於無解**——這裡只試了「切向近地點推進 + Lambert 收尾」，")
            print("     沒有窮舉所有多棒策略。可以試更多棒 (--burns) 或加大 --grid。")

    # --- 建議 ---
    print("\n" + "=" * 70)
    print("建議")
    print("=" * 70)
    if floor > cap:
        print(f"  MAX_BURNS 不要放小於 {min_burns_energy} 的值——那些在物理上不可能合法，")
        print(f"  放進去只是浪費搜尋時間（會找到違規解，每次違規扣 10 分）。")
        print(f"  但也不要只放 {min_burns_energy}：下限沒算平面差跟相位，實際可能還要更多，")
        print(f"  建議從 {min_burns_energy} 掃到 {min_burns_energy + 2} 左右。")
    elif legal == 0:
        print("  能量上單棒可行但網格找不到，先加大 --grid 確認是不是窄窗；")
        print("  如果加密後仍然是 0，再考慮多棒。")
    else:
        print(f"  單棒可行且合法解佔 {rarity:.2f}%，MAX_BURNS 從 [1] 開始測就好。")
        print("  多棒在這種情境通常只會退化成單棒（中間棒 Δv=0），用 sweep_burns.py 確認。")
    print("\n  找出「需要幾棒最好」用 sweep_burns.py；這支工具只回答「有沒有解」。")


if __name__ == "__main__":
    main()
