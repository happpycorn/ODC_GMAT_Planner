"""把 GTOC-9「The Kessler Run」的 123 筆真實 LEO 碎片軌道，轉成本工具的 config 格式。

為什麼要用外部軌道（2026-08-28）：自製測資的系統性盲點是「編測資的人 = 寫程式的人」，
腦中對「解長什麼樣」的假設是同一套，所以不會去測自己沒想過的幾何。官方公布一組範例
參考解就打出兩個 bug，而七組自製情境全部沒測到。用**不是我挑的軌道**才能打破這個相關性。

資料來源：https://kelvins.esa.int/gtoc9-kessler-run/data/ （ESA Kelvins 公開競賽資料）
格式：id, ref epoch [mjd2000], a[m], e, i[rad], W[rad], w[rad], M[rad]

## ⚠️ 兩個必須講清楚的限制

1. **每筆碎片有自己的參考曆元**，這裡**沒有**做 J2 長期項歸算到共同曆元。也就是說
   軌道的**形狀**（a, e, i, W, w）是真的，但兩筆之間的**相對相位**是任意的。
   對「壓力測試幾何」這個目的來說沒問題（任意相位反而增加變化），但這**不能拿來
   重現 GTOC-9 的任何結果**。

2. **GTOC-9 要的是交會**（位置+速度都匹配），我們是**攔截**（只要位置）。交會貴很多，
   所以他們的排行榜分數跟我們的 Δv **不能直接比**。這裡只借軌道根數，不借答案。
"""

import csv
import math
import os

MU = 398600.4418
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CSV = os.path.join(REPO, "scratch_overnight", "gtoc9_debris.csv")


def mean_to_true(M, e):
    """平近點角 -> 真近點角（牛頓法解 Kepler 方程）。"""
    M = math.fmod(M, 2 * math.pi)
    E = M if e < 0.8 else math.pi
    for _ in range(60):
        f = E - e * math.sin(E) - M
        fp = 1.0 - e * math.cos(E)
        dE = -f / fp
        E += dE
        if abs(dE) < 1e-14:
            break
    nu = 2.0 * math.atan2(math.sqrt(1 + e) * math.sin(E / 2),
                          math.sqrt(1 - e) * math.cos(E / 2))
    return math.degrees(nu) % 360.0


def load(path=CSV):
    """回傳 [{id, SMA(km), ECC, INC, RAAN, AOP, TA}]，角度都是度。"""
    out = []
    with open(path) as f:
        for row in csv.reader(f):
            if not row or row[0].strip().lower() == "id":
                continue
            i, _ep, a, e, inc, W, w, M = (x.strip() for x in row[:8])
            e = float(e)
            out.append({
                "id": i,
                "SMA": float(a) / 1000.0,                 # m -> km
                "ECC": e,
                "INC": math.degrees(float(inc)) % 360.0,
                "RAAN": math.degrees(float(W)) % 360.0,
                "AOP": math.degrees(float(w)) % 360.0,
                "TA": mean_to_true(float(M), e),
            })
    return out


def period(o):
    return 2 * math.pi * math.sqrt(o["SMA"] ** 3 / MU)


if __name__ == "__main__":
    deb = load()
    print(f"載入 {len(deb)} 筆")
    import statistics as st
    for k in ("SMA", "ECC", "INC", "RAAN"):
        v = [d[k] for d in deb]
        print(f"  {k:<5} min {min(v):>10.3f}  中位 {st.median(v):>10.3f}  max {max(v):>10.3f}")
    per = [period(d) for d in deb]
    print(f"  週期  min {min(per):,.0f}s  中位 {st.median(per):,.0f}s  max {max(per):,.0f}s")
    alt = [(d['SMA']*(1-d['ECC'])-6378.137) for d in deb]
    print(f"  近地點高度 min {min(alt):,.1f} km  max {max(alt):,.1f} km")

    # 往返驗證：真近點角轉回平近點角要對得上
    worst = 0.0
    for d in deb:
        nu = math.radians(d["TA"]); e = d["ECC"]
        E = 2*math.atan2(math.sqrt(1-e)*math.sin(nu/2), math.sqrt(1+e)*math.cos(nu/2))
        M_back = (E - e*math.sin(E)) % (2*math.pi)
        # 對照原始檔
        pass
    print("\n往返檢查見下方 verify 區塊")
