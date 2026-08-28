"""已知答案測資：拿有閉合解的經典軌道問題，檢查工具找不找得到。

為什麼要這個（2026-08-28）：自製測資有系統性盲點——編測資時「腦中的解長什麼樣」
跟寫程式時的假設是同一套，所以不會去測「最佳解的中間軌道近地點在地表以下」或
「最佳解要繞地球四圈」這種情況。官方公布範例參考解一天就打出兩個 bug，
而那兩個 bug 自製的七組情境全部沒測到。

閉合解是**外部標準**：不是我編的，也不受我的假設影響。

## ⚠️ 兩類要分清楚，標籤不能混

**真下限**（能量論證，不可能更便宜）：工具低於它 = **工具有 bug**。
**構造**（某個家族裡的最好）：工具贏它 = 正常且是好事；工具**遠輸**它才是問題。

今天已經在「構造當最佳解」上栽過兩次（見 SCENARIOS.md 教訓二），所以這裡標死。

## ⚠️ 已知答案測資的設計要點

**要測哪一項，就得把其他項壓平。** 第一版把 `C_t` 設在霍曼的抵達時刻，工具理性地
拿燃料換時間，交出 612.7 m/s（比下限多 26 m/s）——那是**對的行為**，是測資設計錯了。
把 `k_t` 壓到 1e-12 之後才量得到「找不找得到最小 Δv」。

同理 `GRAVITY_DEGREE` 要設 0：閉合解是純二體的，開 J2 就不是公平比較。

跑法：uv run python scratch_overnight/known_answer_suite.py
（只算閉合解與建 config，不跑最佳化——最佳化各跑一次要好幾分鐘，手動跑
 `uv run python main.py --config configs/known_*.json --no-gmat` 再對照下面印出來的數字。）
"""

import json
import math
import os

MU = 398600.4418
RE = 6378.137
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def base_cfg(A, B, k_v, C_v, burns, comment):
    """共用骨架：時間項壓平、純二體、只留燃料項有梯度。"""
    return {
        "_comment": comment,
        "orbit_A": A, "orbit_B": B,
        "rules": {"MAX_DV_MPS": 1500.0, "MIN_MANEUVER_INTERVAL_SEC": 100.0,
                  "T_MAX_PERIOD_MULTIPLE": 4.0,
                  "k_t": 1e-12, "C_t": 1.0, "k_v": k_v, "C_v": round(C_v, 3)},
        "strategy": {"GRAVITY_DEGREE": 0, "MISS_TOLERANCE_KM": 5.0},
        "optimization": {"MAX_BURNS": burns, "MAXITER": 800, "POPSIZE": 20,
                         "NUM_THREADS": 12, "MAX_EARLY_STOP": 80, "TOL": 0.01,
                         "SEED": None},
        "local": {"gmat_console_path":
                  "/home/corn/software/GMAT/GMAT/R2026a/bin/GmatConsole"},
    }


def hohmann_first_impulse():
    """真下限：從 r1 圓軌道抵達半徑 r2 的最小單棒 = 把遠地點抬到 r2 的切向燒。

    能量論證：任何能碰到 r2 的軌道，遠地點至少要 r2；從圓軌道出發，達成這件事最便宜
    的方式就是切向加速。所以這是**不可能更便宜**的下限。

    A 的相位刻意對準：讓 A 在 B 走完轉移橢圓半圈時剛好在那個遠地點。
    """
    r1, r2 = 6878.0, 9500.0
    dv = math.sqrt(MU / r1) * (math.sqrt(2 * r2 / (r1 + r2)) - 1) * 1000.0
    t_tr = math.pi * math.sqrt(((r1 + r2) / 2) ** 3 / MU)
    ta_A = math.degrees(math.pi - math.sqrt(MU / r2 ** 3) * t_tr) % 360.0
    # 工具可以瞄準 A 內側 MISS_TOLERANCE_SOFT(=3.5km)，所以合理答案略低於上面那個值
    dv_aim = math.sqrt(MU / r1) * (math.sqrt(2 * (r2 - 3.5) / (r1 + r2 - 3.5)) - 1) * 1000.0
    cfg = base_cfg(
        {"SMA": r2, "ECC": 0.0, "INC": 0.0, "RAAN": 0.0, "AOP": 0.0, "TA": round(ta_A, 6)},
        {"SMA": r1, "ECC": 0.0, "INC": 0.0, "RAAN": 0.0, "AOP": 0.0, "TA": 0.0},
        0.005, dv, [1, 2],
        "已知答案測資：霍曼第一棒（真下限）。時間項壓平、純二體，只測「找不找得到最小 Δv」。")
    return ("known_hohmann", cfg, "真下限", dv, dv_aim,
            f"抵達 {t_tr:,.1f}s；瞄準內側 3.5km 的下限 {dv_aim:.3f} m/s")


def pure_phasing():
    """構造：A/B 同軌道、A 超前 theta，B 切向改週期，繞 k 圈後在燒點會合。

    不是下限——B 其實不必在燒點會合，也可以用別的漂移方式在別的點碰到 A。

    這組還順便測出一個結構限制：最佳解是「燒一棒然後漂」，而我們的編碼裡最後一棒
    永遠是 Lambert 棒，這條轉移繞了約 4 圈，M=0 的 Lambert 表達不出來。
    實測 MAX_BURNS=[1] 時：LAMBERT_MAX_REVS=0 -> 1,490.0 m/s；=4 -> 70.6 m/s（省 21 倍）。
    """
    r, theta = 7200.0, 40.0
    T = 2 * math.pi * math.sqrt(r ** 3 / MU)
    v_c = math.sqrt(MU / r)
    best = None
    for m in range(1, 6):
        t = T * (m - math.radians(theta) / (2 * math.pi))
        if t > 4 * T:
            continue
        for k in range(1, 8):
            a = (MU * ((t / k) / (2 * math.pi)) ** 2) ** (1 / 3)
            if 2 * a - r <= RE + 100:
                continue
            dv = abs(math.sqrt(MU * (2 / r - 1 / a)) - v_c) * 1000.0
            if dv > 1500:
                continue
            if best is None or dv < best[0]:
                best = (dv, m, k, t, a)
    dv, m, k, t, a = best
    cfg = base_cfg(
        {"SMA": r, "ECC": 0.0, "INC": 0.0, "RAAN": 0.0, "AOP": 0.0, "TA": theta},
        {"SMA": r, "ECC": 0.0, "INC": 0.0, "RAAN": 0.0, "AOP": 0.0, "TA": 0.0},
        0.02, dv, [1, 2],
        "已知答案測資：純相位追趕（構造，不是下限）。工具找到更便宜的解是正常的。")
    return ("known_phasing", cfg, "構造", dv, None,
            f"B 繞 {k} 圈 / A 走 {m} 圈，於燒點會合，抵達 {t:,.1f}s")


if __name__ == "__main__":
    print("=" * 88)
    print("已知答案測資：閉合解 vs 工具")
    print("=" * 88)
    for name, cfg, kind, dv, dv_aim, note in (hohmann_first_impulse(), pure_phasing()):
        path = os.path.join(REPO, "configs", f"{name}.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=4, ensure_ascii=False)
        tag = "🔴 工具低於它 = bug" if kind == "真下限" else "工具贏它 = 正常"
        print(f"\n[{kind}] {name}")
        print(f"  閉合解 = {dv:,.3f} m/s   ({tag})")
        print(f"  {note}")
        print(f"  📄 configs/{name}.json")
    print("\n" + "-" * 88)
    print("實測結果（2026-08-28）：")
    print("  known_hohmann  工具 586.1 m/s  vs 瞄準修正後的下限 586.121 m/s  -> 差 -0.004% ✅")
    print("  known_phasing  工具  70.7 m/s  vs 構造 70.87 m/s               -> 略優 ✅")
    print("  known_phasing 附帶發現：MAX_BURNS=[1] 時 M=0 只能交出 1,490.0 m/s，")
    print("                          LAMBERT_MAX_REVS=4 才找得到 70.6 m/s（省 21 倍）。")
