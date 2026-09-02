"""比賽當天的體檢工具：把 config 回顯成人一眼能核對的衍生量。

為什麼 (2026-09-02)：90 分鐘裡最脆弱的一步是手抄題目的 A/B 六根數 —— 12 個數字
打錯一個，答案就錯，而且分數照樣算得出來、未必看得出來。config_validator 只擋
「近地點低於地表」這種硬錯，抓不到「INC 打成 54 而不是 45」這種還算合理、但其實抄錯
的數字。

這支工具不重算一套邏輯，直接用 MissionOptimizer 初始化（等於回顯**工具真正會用**的
數值），把打錯就會變離譜的衍生量印出來：
  * A/B 的週期、遠近地點高度      -> SMA/ECC 打錯 -> 週期或高度荒謬
  * A、B 兩軌道平面的夾角          -> INC/RAAN 打錯 -> 夾角荒謬
  * T_max、C_t/T_max 比值          -> 判斷該押快解還是省油解、長飛行時間家族活不活
  * 時間 vs 燃料的邊際交換率        -> 早 1 秒值多少 m/s
  * 若像範例題目：參考解該得幾分    -> 驗算計分參數的單位有沒有換錯

用法：
    uv run python check_problem.py --config configs/official_sample.json
"""
import argparse
import math
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import warnings
warnings.filterwarnings("ignore")
from src.optimizer import MissionOptimizer


def _angle_between(u, v):
    c = float(np.dot(u, v)) / (np.linalg.norm(u) * np.linalg.norm(v))
    return math.degrees(math.acos(min(1.0, max(-1.0, c))))


def _orbit_facts(m, r0, v0, label):
    """回傳一段人可讀的軌道摘要 + 給夾角用的角動量向量。"""
    mu = m.MU
    r = float(np.linalg.norm(r0))
    v = float(np.linalg.norm(v0))
    energy = v * v / 2.0 - mu / r
    h_vec = np.cross(r0, v0)
    rp, ra = m._orbit_radius_range(r0, v0)
    lines = [f"  {label}:"]
    if energy < 0.0:
        a = -mu / (2.0 * energy)
        period = 2.0 * math.pi * math.sqrt(a ** 3 / mu)
        lines.append(f"    半長軸 SMA   {a:10.2f} km")
        lines.append(f"    週期         {period:10.1f} s  ({period/60.0:.2f} 分)")
    else:
        lines.append(f"    半長軸 SMA   {'(逃逸/雙曲線)':>10}  能量 {energy:+.4f} km^2/s^2")
        period = None
    lines.append(f"    近地點半徑   {rp:10.2f} km  (高度 {rp - m.RE_VAL:8.2f} km)")
    lines.append(f"    遠地點半徑   {ra:10.2f} km  (高度 {ra - m.RE_VAL:8.2f} km)")
    lines.append(f"    初始位置 |r| {r:10.2f} km  速度 |v| {v:8.4f} km/s")
    # 撞地球的紅旗：近地點在地表以下
    if rp < m.RE_VAL:
        lines.append(f"    ** 警告：近地點半徑 {rp:.1f} < 地球半徑 {m.RE_VAL:.1f}，這條軌道會撞地球 **")
    elif rp < m.MIN_PERIAPSIS:
        lines.append(f"    ** 注意：近地點高度 {rp - m.RE_VAL:.1f} km < 100 km 安全底線 **")
    return "\n".join(lines), h_vec, period


def main():
    ap = argparse.ArgumentParser(description="比賽當天的 config 體檢/回顯")
    ap.add_argument("--config", required=True, help="要體檢的 config JSON 路徑")
    args = ap.parse_args()

    import json
    with open(args.config, encoding="utf-8") as f:
        cfg = json.load(f)

    print("=" * 66)
    print(f"config 體檢：{args.config}")
    print("（用 MissionOptimizer 初始化，回顯的是工具真正會用的數值）")
    print("=" * 66)

    m = MissionOptimizer(cfg)
    mu = m.MU

    # --- 原始六根數回顯（照抄 config，讓人跟題目逐字核對）---
    print("\n【原始六根數（跟題目逐字核對）】")
    for key in ("orbit_A", "orbit_B"):
        o = cfg.get(key, {})
        print(f"  {key}: SMA={o.get('SMA')}  ECC={o.get('ECC')}  INC={o.get('INC')}  "
              f"RAAN={o.get('RAAN')}  AOP={o.get('AOP')}  TA={o.get('TA')}")

    # --- 衍生量：打錯就會變離譜 ---
    print("\n【衍生量（打錯就會變離譜）】")
    a_txt, hA, Ta = _orbit_facts(m, m.A_r0, m.A_v0, "A（目標，被動）")
    b_txt, hB, Tb = _orbit_facts(m, m.B_r0, m.B_v0, "B（我方，機動）")
    print(a_txt)
    print(b_txt)

    plane_angle = _angle_between(hA, hB)
    print(f"\n  A、B 兩軌道平面夾角  {plane_angle:8.3f} 度")
    print("    （INC/RAAN 抄錯這個數會跟著錯；範例題目是 93.84 度）")

    # --- 時間預算 ---
    print("\n【時間預算】")
    print(f"  T_max            {m.T_max:10.1f} s  ({m.T_max/60.0:.1f} 分)")
    if m.Ta_sec:
        print(f"  A 的週期 Ta      {m.Ta_sec:10.1f} s   -> T_max = {m.T_max/m.Ta_sec:.2f} × Ta")

    # --- 計分參數 + 策略提示 ---
    print("\n【計分參數與策略提示】")
    print(f"  每棒 ΔV 上限     {m.MAX_DV*1000.0:10.1f} m/s   （安全邊際後軟上限 {m.MAX_DV_SOFT*1000.0:.1f}）")
    print(f"  機動間隔下限     {m.MIN_COAST_TIME:10.1f} s")
    print(f"  k_t={m.k_t:.6g}  C_t={m.C_t:.6g} s   k_v={m.k_v:.6g}  C_v={m.C_v:.6g} m/s")

    ratio = m.C_t / m.T_max if m.T_max else float("nan")
    print(f"\n  C_t / T_max      {ratio:8.3f}")
    if ratio < 0.30:
        print("    -> 時間窗很緊：主攻快解。長飛行時間家族（雙橢圓、長滑行多圈）大多已死。")
    elif ratio > 0.70:
        print("    -> 時間窗寬鬆：長飛行時間的省油解可能有戲。注意 coast_frac 弱點（HAP-18）。")
    else:
        print("    -> 中間地帶：快解跟省油解都要各跑一次再比。")

    # 時間 vs 燃料的邊際交換率。sigmoid 在拐點斜率最大，所以 k_t/k_v 是「早 1 秒值多少
    # m/s」的**上界**（兩個項都在各自拐點時才取到）。真正的工作點通常偏離拐點，實際值
    # 更低——範例題目在 T=3158/V=2242 精算是 1.21，而這裡的上界是 3.36。有了真正的解
    # 之後要用那個解的 T/V 重算，別直接拿這個上界當停止門檻。
    if m.k_v > 0:
        print(f"\n  時間 vs 燃料：早到 1 秒最多值得多花 {m.k_t/m.k_v:.2f} m/s（拐點上界，實際更低）")
        print("    （拿到解之後用該解的 T/V 重算真正的交換率，見 CONTEST_DAY 第五節）")

    # --- 若參考解已知：驗算單位 ---
    REF_DV, REF_T, REF_SCORE = 2241.427, 3211.737, 90.00
    def score(V_mps, T_s):
        s_dist = 50.0
        s_time = 25.0 / (1.0 + math.exp(min(m.k_t * (T_s - m.C_t), 700.0)))
        s_dv = 25.0 / (1.0 + math.exp(min(m.k_v * (V_mps - m.C_v), 700.0)))
        return s_dist + s_time + s_dv
    ref = score(REF_DV, REF_T)
    print("\n【單位換算檢查（僅對範例題目有意義）】")
    print(f"  官方參考解 {REF_DV} m/s @ {REF_T} s 用這組參數算 = {ref:.3f} 分")
    if abs(ref - REF_SCORE) < 0.05:
        print(f"    ✅ 剛好 {REF_SCORE}，計分參數的單位換算正確（k_v/C_v 有從 km/s 換成 m/s）")
    else:
        print(f"    ⚠️  不是 {REF_SCORE} —— 若這就是範例題目，很可能 k_v/C_v 單位沒換算。"
              " 官方 k_v 是 (km/s)^-1、C_v 是 km/s，本工具要 m/s：k_v/1000、C_v×1000。")
        print("    （若這是別的題目，這行沒意義，忽略即可）")

    print("\n" + "=" * 66)
    print("體檢完成。逐項確認上面的數字都合理，再開始跑 main.py。")
    print("=" * 66)


if __name__ == "__main__":
    main()
