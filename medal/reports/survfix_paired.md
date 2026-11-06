# survfix：orbit_survives 末端半徑檢查，開關 關 vs 開（逐局配對）

同一批幾何（seed 1、24 局/配對）；關 = ODC_STRICT_SURVIVAL=0（舊行為）、開 = 1。符號檢定：雙尾精確，只看勝負翻轉的局。
「有變的局」= outcome、t_end、min_dist_km、used_* 任一不同。原始報表：reports/survfix_<組>_{off,on}.md；筆記：docs/notes/orbit_survives_fix.md。

### ranking_like

| 追者 | 躲者 | n | 追者勝率 關 → 開 | 撞地 P 關/開 | 撞地 E 關/開 | 有變的局 | 勝負翻轉 只關追者勝 / 只開追者勝 | 符號檢定 p |
|---|---|---|---|---|---|---|---|---|
| lambert_pursuer | dv_evader | 24 | 58% [39–76] → 58% [39–76] | 0 / 0 | 0 / 0 | 0 | 0 / 0 | 1 |
| lambert_pursuer | rollout_evader | 24 | 46% [28–65] → 46% [28–65] | 0 / 0 | 0 / 0 | 0 | 0 / 0 | 1 |
| lambert_pursuer | escape_evader | 24 | 67% [47–82] → 67% [47–82] | 0 / 0 | 0 / 0 | 0 | 0 / 0 | 1 |
| rollout_pursuer | dv_evader | 24 | 79% [60–91] → 79% [60–91] | 0 / 0 | 0 / 0 | 0 | 0 / 0 | 1 |
| rollout_pursuer | rollout_evader | 24 | 29% [15–49] → 29% [15–49] | 0 / 0 | 0 / 0 | 1 | 0 / 0 | 1 |
| rollout_pursuer | escape_evader | 24 | 100% [86–100] → 100% [86–100] | 0 / 0 | 0 / 0 | 1 | 0 / 0 | 1 |
| **合計** | | 144 | 63% [55–71] → 63% [55–71] | 0 / 0 | 0 / 0 | 2 | 0 / 0 | 1（合併，局間不獨立，僅供參考） |

### symmetric

| 追者 | 躲者 | n | 追者勝率 關 → 開 | 撞地 P 關/開 | 撞地 E 關/開 | 有變的局 | 勝負翻轉 只關追者勝 / 只開追者勝 | 符號檢定 p |
|---|---|---|---|---|---|---|---|---|
| lambert_pursuer | dv_evader | 24 | 12% [4–31] → 12% [4–31] | 0 / 0 | 0 / 0 | 0 | 0 / 0 | 1 |
| lambert_pursuer | rollout_evader | 24 | 0% [0–14] → 0% [0–14] | 0 / 0 | 0 / 0 | 2 | 0 / 0 | 1 |
| lambert_pursuer | escape_evader | 24 | 0% [0–14] → 0% [0–14] | 0 / 0 | 0 / 0 | 0 | 0 / 0 | 1 |
| rollout_pursuer | dv_evader | 24 | 33% [18–53] → 33% [18–53] | 0 / 0 | 0 / 0 | 0 | 0 / 0 | 1 |
| rollout_pursuer | rollout_evader | 24 | 58% [39–76] → 58% [39–76] | 0 / 0 | 0 / 0 | 0 | 0 / 0 | 1 |
| rollout_pursuer | escape_evader | 24 | 21% [9–40] → 21% [9–40] | 0 / 0 | 0 / 0 | 1 | 0 / 0 | 1 |
| **合計** | | 144 | 21% [15–28] → 21% [15–28] | 0 / 0 | 0 / 0 | 3 | 0 / 0 | 1（合併，局間不獨立，僅供參考） |

### flyby

| 追者 | 躲者 | n | 追者勝率 關 → 開 | 撞地 P 關/開 | 撞地 E 關/開 | 有變的局 | 勝負翻轉 只關追者勝 / 只開追者勝 | 符號檢定 p |
|---|---|---|---|---|---|---|---|---|
| lambert_pursuer | coast | 24 | 92% [74–98] → 92% [74–98] | 1 / 0 | 0 / 0 | 1 | 0 / 0 | 1 |
| lambert_pursuer | dv_evader | 24 | 0% [0–14] → 0% [0–14] | 8 / 0 | 0 / 0 | 8 | 0 / 0 | 1 |
| lambert_pursuer | rollout_evader | 24 | 0% [0–14] → 0% [0–14] | 13 / 0 | 0 / 0 | 13 | 0 / 0 | 1 |
| lambert_pursuer | escape_evader | 24 | 0% [0–14] → 0% [0–14] | 5 / 0 | 0 / 0 | 5 | 0 / 0 | 1 |
| lambert_pursuer | sb3 躲者 | 24 | 0% [0–14] → 0% [0–14] | 4 / 0 | 0 / 0 | 4 | 0 / 0 | 1 |
| rollout_pursuer | coast | 24 | 92% [74–98] → 92% [74–98] | 0 / 0 | 0 / 0 | 0 | 0 / 0 | 1 |
| rollout_pursuer | dv_evader | 24 | 0% [0–14] → 0% [0–14] | 0 / 0 | 0 / 0 | 0 | 0 / 0 | 1 |
| rollout_pursuer | rollout_evader | 24 | 0% [0–14] → 0% [0–14] | 0 / 0 | 0 / 0 | 0 | 0 / 0 | 1 |
| rollout_pursuer | escape_evader | 24 | 0% [0–14] → 0% [0–14] | 0 / 0 | 0 / 0 | 0 | 0 / 0 | 1 |
| rollout_pursuer | sb3 躲者 | 24 | 0% [0–14] → 0% [0–14] | 0 / 0 | 0 / 0 | 0 | 0 / 0 | 1 |
| sb3 追者 | coast | 24 | 50% [31–69] → 50% [31–69] | 6 / 0 | 0 / 0 | 6 | 0 / 0 | 1 |
| sb3 追者 | dv_evader | 24 | 0% [0–14] → 0% [0–14] | 8 / 0 | 0 / 0 | 8 | 0 / 0 | 1 |
| sb3 追者 | rollout_evader | 24 | 0% [0–14] → 0% [0–14] | 9 / 0 | 0 / 0 | 9 | 0 / 0 | 1 |
| sb3 追者 | escape_evader | 24 | 0% [0–14] → 0% [0–14] | 5 / 0 | 0 / 0 | 6 | 0 / 0 | 1 |
| sb3 追者 | sb3 躲者 | 24 | 8% [2–26] → 8% [2–26] | 5 / 0 | 0 / 0 | 6 | 0 / 0 | 1 |
| **合計** | | 360 | 16% [13–20] → 16% [13–20] | 64 / 0 | 0 / 0 | 66 | 0 / 0 | 1（合併，局間不獨立，僅供參考） |

結局有變的局：

  - lambert_pursuer vs coast 第 16 局：crash_pursuer @ 7005 s → timeout @ 7442 s（最近 59.4 → 59.4 km）
  - lambert_pursuer vs dv_evader 第 1 局：crash_pursuer @ 7182 s → timeout @ 8045 s（最近 232.0 → 232.0 km）
  - lambert_pursuer vs dv_evader 第 4 局：crash_pursuer @ 8862 s → timeout @ 8912 s（最近 361.1 → 361.1 km）
  - lambert_pursuer vs dv_evader 第 8 局：crash_pursuer @ 7218 s → timeout @ 8389 s（最近 636.8 → 636.8 km）
  - lambert_pursuer vs dv_evader 第 9 局：crash_pursuer @ 8649 s → timeout @ 9614 s（最近 698.9 → 698.9 km）
  - lambert_pursuer vs dv_evader 第 10 局：crash_pursuer @ 8901 s → timeout @ 9788 s（最近 446.5 → 446.5 km）
  - lambert_pursuer vs dv_evader 第 11 局：crash_pursuer @ 9928 s → timeout @ 10129 s（最近 1358.7 → 1358.7 km）
  - lambert_pursuer vs dv_evader 第 16 局：crash_pursuer @ 6844 s → timeout @ 7442 s（最近 227.3 → 227.3 km）
  - lambert_pursuer vs dv_evader 第 21 局：crash_pursuer @ 8554 s → timeout @ 9381 s（最近 641.9 → 641.9 km）
  - lambert_pursuer vs escape_evader 第 1 局：crash_pursuer @ 7897 s → timeout @ 8045 s（最近 145.2 → 145.2 km）
  - lambert_pursuer vs escape_evader 第 2 局：crash_pursuer @ 8533 s → timeout @ 8969 s（最近 103.3 → 103.3 km）
  - lambert_pursuer vs escape_evader 第 5 局：crash_pursuer @ 8114 s → timeout @ 8255 s（最近 189.8 → 189.8 km）
  - lambert_pursuer vs escape_evader 第 9 局：crash_pursuer @ 8964 s → timeout @ 9614 s（最近 65.0 → 65.0 km）
  - lambert_pursuer vs escape_evader 第 16 局：crash_pursuer @ 6679 s → timeout @ 7442 s（最近 158.8 → 158.8 km）
  - lambert_pursuer vs rollout_evader 第 1 局：crash_pursuer @ 7141 s → timeout @ 8045 s（最近 8.9 → 8.9 km）
  - lambert_pursuer vs rollout_evader 第 4 局：crash_pursuer @ 7890 s → timeout @ 8912 s（最近 83.7 → 83.7 km）
  - lambert_pursuer vs rollout_evader 第 5 局：crash_pursuer @ 7170 s → timeout @ 8255 s（最近 83.1 → 83.1 km）
  - lambert_pursuer vs rollout_evader 第 6 局：crash_pursuer @ 9425 s → timeout @ 10527 s（最近 81.3 → 81.3 km）
  - lambert_pursuer vs rollout_evader 第 8 局：crash_pursuer @ 7279 s → timeout @ 8389 s（最近 77.7 → 77.7 km）
  - lambert_pursuer vs rollout_evader 第 9 局：crash_pursuer @ 8903 s → timeout @ 9614 s（最近 33.0 → 33.0 km）
  - lambert_pursuer vs rollout_evader 第 10 局：crash_pursuer @ 9342 s → timeout @ 9788 s（最近 63.6 → 63.6 km）
  - lambert_pursuer vs rollout_evader 第 12 局：crash_pursuer @ 8891 s → timeout @ 8938 s（最近 74.7 → 74.7 km）
  - lambert_pursuer vs rollout_evader 第 14 局：crash_pursuer @ 9841 s → timeout @ 10797 s（最近 11.6 → 11.6 km）
  - lambert_pursuer vs rollout_evader 第 16 局：crash_pursuer @ 7005 s → timeout @ 7442 s（最近 59.4 → 59.4 km）
  - lambert_pursuer vs rollout_evader 第 20 局：crash_pursuer @ 11148 s → timeout @ 12028 s（最近 13.5 → 13.5 km）
  - lambert_pursuer vs rollout_evader 第 21 局：crash_pursuer @ 8677 s → timeout @ 9381 s（最近 10.9 → 10.9 km）
  - lambert_pursuer vs rollout_evader 第 22 局：crash_pursuer @ 9169 s → timeout @ 9856 s（最近 59.7 → 59.7 km）
  - lambert_pursuer vs sb3 躲者 第 7 局：crash_pursuer @ 8298 s → timeout @ 8754 s（最近 149.8 → 149.8 km）
  - lambert_pursuer vs sb3 躲者 第 9 局：crash_pursuer @ 8600 s → timeout @ 9614 s（最近 130.7 → 130.7 km）
  - lambert_pursuer vs sb3 躲者 第 16 局：crash_pursuer @ 6939 s → timeout @ 7442 s（最近 146.4 → 146.4 km）
  - lambert_pursuer vs sb3 躲者 第 21 局：crash_pursuer @ 8603 s → timeout @ 9381 s（最近 191.2 → 191.2 km）
  - sb3 追者 vs coast 第 0 局：crash_pursuer @ 10415 s → timeout @ 11407 s（最近 304.7 → 304.7 km）
  - sb3 追者 vs coast 第 1 局：crash_pursuer @ 7638 s → timeout @ 8045 s（最近 32.0 → 32.0 km）
  - sb3 追者 vs coast 第 2 局：crash_pursuer @ 8450 s → timeout @ 8969 s（最近 428.1 → 428.1 km）
  - sb3 追者 vs coast 第 4 局：crash_pursuer @ 7924 s → timeout @ 8912 s（最近 68.4 → 68.4 km）
  - sb3 追者 vs coast 第 6 局：crash_pursuer @ 9613 s → timeout @ 10527 s（最近 202.9 → 202.9 km）
  - sb3 追者 vs coast 第 16 局：crash_pursuer @ 6805 s → timeout @ 7442 s（最近 59.4 → 59.4 km）
  - sb3 追者 vs dv_evader 第 1 局：crash_pursuer @ 7322 s → timeout @ 8045 s（最近 232.6 → 232.6 km）
  - sb3 追者 vs dv_evader 第 4 局：crash_pursuer @ 8408 s → timeout @ 8912 s（最近 862.4 → 862.4 km）
  - sb3 追者 vs dv_evader 第 5 局：crash_pursuer @ 7547 s → timeout @ 8255 s（最近 925.6 → 925.6 km）
  - sb3 追者 vs dv_evader 第 6 局：crash_pursuer @ 10091 s → timeout @ 10527 s（最近 3658.3 → 3658.3 km）
  - sb3 追者 vs dv_evader 第 7 局：crash_pursuer @ 7912 s → timeout @ 8754 s（最近 585.6 → 585.6 km）
  - sb3 追者 vs dv_evader 第 9 局：crash_pursuer @ 8700 s → timeout @ 9614 s（最近 675.6 → 675.6 km）
  - sb3 追者 vs dv_evader 第 10 局：crash_pursuer @ 8989 s → timeout @ 9788 s（最近 428.1 → 428.1 km）
  - sb3 追者 vs dv_evader 第 16 局：crash_pursuer @ 6698 s → timeout @ 7442 s（最近 227.3 → 227.3 km）
  - sb3 追者 vs escape_evader 第 1 局：crash_pursuer @ 7799 s → timeout @ 8045 s（最近 145.3 → 145.3 km）
  - sb3 追者 vs escape_evader 第 4 局：crash_pursuer @ 8388 s → timeout @ 8912 s（最近 479.7 → 479.7 km）
  - sb3 追者 vs escape_evader 第 7 局：crash_pursuer @ 8163 s → timeout @ 8754 s（最近 219.0 → 219.0 km）
  - sb3 追者 vs escape_evader 第 9 局：crash_pursuer @ 9110 s → timeout @ 9614 s（最近 672.1 → 672.1 km）
  - sb3 追者 vs escape_evader 第 16 局：crash_pursuer @ 6550 s → timeout @ 7442 s（最近 158.8 → 158.8 km）
  - sb3 追者 vs rollout_evader 第 0 局：crash_pursuer @ 10415 s → timeout @ 11407 s（最近 304.7 → 304.7 km）
  - sb3 追者 vs rollout_evader 第 1 局：crash_pursuer @ 7638 s → timeout @ 8045 s（最近 32.0 → 32.0 km）
  - sb3 追者 vs rollout_evader 第 2 局：crash_pursuer @ 8450 s → timeout @ 8969 s（最近 428.1 → 428.1 km）
  - sb3 追者 vs rollout_evader 第 4 局：crash_pursuer @ 7924 s → timeout @ 8912 s（最近 68.4 → 68.4 km）
  - sb3 追者 vs rollout_evader 第 5 局：crash_pursuer @ 7180 s → timeout @ 8255 s（最近 79.6 → 79.6 km）
  - sb3 追者 vs rollout_evader 第 6 局：crash_pursuer @ 9613 s → timeout @ 10527 s（最近 202.9 → 202.9 km）
  - sb3 追者 vs rollout_evader 第 9 局：crash_pursuer @ 9217 s → timeout @ 9614 s（最近 86.2 → 86.2 km）
  - sb3 追者 vs rollout_evader 第 10 局：crash_pursuer @ 9046 s → timeout @ 9788 s（最近 72.7 → 72.7 km）
  - sb3 追者 vs rollout_evader 第 16 局：crash_pursuer @ 6805 s → timeout @ 7442 s（最近 59.4 → 59.4 km）
  - sb3 追者 vs sb3 躲者 第 1 局：crash_pursuer @ 7943 s → timeout @ 8045 s（最近 163.5 → 163.5 km）
  - sb3 追者 vs sb3 躲者 第 3 局：crash_pursuer @ 11197 s → timeout @ 12073 s（最近 1635.3 → 1635.3 km）
  - sb3 追者 vs sb3 躲者 第 4 局：crash_pursuer @ 8151 s → timeout @ 8912 s（最近 165.9 → 165.9 km）
  - sb3 追者 vs sb3 躲者 第 7 局：crash_pursuer @ 8094 s → timeout @ 8754 s（最近 288.6 → 288.6 km）
  - sb3 追者 vs sb3 躲者 第 16 局：crash_pursuer @ 6772 s → timeout @ 7442 s（最近 146.2 → 146.2 km）

### flyby_pursuer

| 追者 | 躲者 | n | 追者勝率 關 → 開 | 撞地 P 關/開 | 撞地 E 關/開 | 有變的局 | 勝負翻轉 只關追者勝 / 只開追者勝 | 符號檢定 p |
|---|---|---|---|---|---|---|---|---|
| lambert_pursuer | coast | 24 | 92% [74–98] → 92% [74–98] | 0 / 0 | 0 / 0 | 0 | 0 / 0 | 1 |
| lambert_pursuer | dv_evader | 24 | 0% [0–14] → 0% [0–14] | 0 / 0 | 0 / 0 | 4 | 0 / 0 | 1 |
| lambert_pursuer | rollout_evader | 24 | 0% [0–14] → 0% [0–14] | 0 / 0 | 0 / 0 | 7 | 0 / 0 | 1 |
| lambert_pursuer | escape_evader | 24 | 8% [2–26] → 0% [0–14] | 0 / 0 | 2 / 0 | 2 | 2 / 0 | 0.5 |
| lambert_pursuer | sb3 躲者 | 24 | 29% [15–49] → 0% [0–14] | 0 / 0 | 7 / 0 | 7 | 7 / 0 | 0.0156 |
| rollout_pursuer | coast | 24 | 88% [69–96] → 88% [69–96] | 0 / 0 | 0 / 0 | 2 | 0 / 0 | 1 |
| rollout_pursuer | dv_evader | 24 | 0% [0–14] → 0% [0–14] | 0 / 0 | 0 / 0 | 2 | 0 / 0 | 1 |
| rollout_pursuer | rollout_evader | 24 | 0% [0–14] → 0% [0–14] | 0 / 0 | 0 / 0 | 6 | 0 / 0 | 1 |
| rollout_pursuer | escape_evader | 24 | 0% [0–14] → 0% [0–14] | 0 / 0 | 0 / 0 | 1 | 0 / 0 | 1 |
| rollout_pursuer | sb3 躲者 | 24 | 42% [24–61] → 0% [0–14] | 0 / 0 | 10 / 0 | 11 | 10 / 0 | 0.00195 |
| sb3 追者 | coast | 24 | 92% [74–98] → 92% [74–98] | 0 / 0 | 0 / 0 | 0 | 0 / 0 | 1 |
| sb3 追者 | dv_evader | 24 | 0% [0–14] → 0% [0–14] | 0 / 0 | 0 / 0 | 6 | 0 / 0 | 1 |
| sb3 追者 | rollout_evader | 24 | 0% [0–14] → 0% [0–14] | 0 / 0 | 0 / 0 | 6 | 0 / 0 | 1 |
| sb3 追者 | escape_evader | 24 | 4% [1–20] → 0% [0–14] | 0 / 0 | 1 / 0 | 8 | 1 / 0 | 1 |
| sb3 追者 | sb3 躲者 | 24 | 46% [28–65] → 4% [1–20] | 0 / 0 | 10 / 0 | 12 | 10 / 0 | 0.00195 |
| **合計** | | 360 | 27% [22–31] → 18% [15–23] | 0 / 0 | 30 / 0 | 74 | 30 / 0 | 1.86e-09（合併，局間不獨立，僅供參考） |

結局有變的局：

  - lambert_pursuer vs escape_evader 第 5 局：crash_evader @ 7453 s → timeout @ 8255 s（最近 1179.7 → 1179.7 km）
  - lambert_pursuer vs escape_evader 第 22 局：crash_evader @ 9213 s → timeout @ 9856 s（最近 1824.4 → 1824.4 km）
  - lambert_pursuer vs sb3 躲者 第 1 局：crash_evader @ 7521 s → timeout @ 8045 s（最近 122.8 → 122.8 km）
  - lambert_pursuer vs sb3 躲者 第 5 局：crash_evader @ 7201 s → timeout @ 8255 s（最近 250.3 → 250.3 km）
  - lambert_pursuer vs sb3 躲者 第 6 局：crash_evader @ 9651 s → timeout @ 10527 s（最近 1401.5 → 1401.5 km）
  - lambert_pursuer vs sb3 躲者 第 8 局：crash_evader @ 7503 s → timeout @ 8389 s（最近 672.9 → 672.9 km）
  - lambert_pursuer vs sb3 躲者 第 11 局：crash_evader @ 9495 s → timeout @ 10129 s（最近 90.1 → 90.1 km）
  - lambert_pursuer vs sb3 躲者 第 14 局：crash_evader @ 9898 s → timeout @ 10797 s（最近 135.4 → 135.4 km）
  - lambert_pursuer vs sb3 躲者 第 21 局：crash_evader @ 9219 s → timeout @ 9381 s（最近 88.4 → 88.4 km）
  - rollout_pursuer vs sb3 躲者 第 1 局：crash_evader @ 7412 s → timeout @ 8045 s（最近 143.8 → 143.8 km）
  - rollout_pursuer vs sb3 躲者 第 2 局：crash_evader @ 8824 s → timeout @ 8969 s（最近 496.5 → 496.5 km）
  - rollout_pursuer vs sb3 躲者 第 5 局：crash_evader @ 7342 s → timeout @ 8255 s（最近 250.3 → 250.3 km）
  - rollout_pursuer vs sb3 躲者 第 6 局：crash_evader @ 9661 s → timeout @ 10527 s（最近 1215.0 → 1215.0 km）
  - rollout_pursuer vs sb3 躲者 第 7 局：crash_evader @ 8706 s → timeout @ 8754 s（最近 340.5 → 340.5 km）
  - rollout_pursuer vs sb3 躲者 第 8 局：crash_evader @ 7519 s → timeout @ 8389 s（最近 672.9 → 672.9 km）
  - rollout_pursuer vs sb3 躲者 第 14 局：crash_evader @ 9929 s → timeout @ 10797 s（最近 155.7 → 155.7 km）
  - rollout_pursuer vs sb3 躲者 第 18 局：crash_evader @ 10259 s → timeout @ 10558 s（最近 77.8 → 77.8 km）
  - rollout_pursuer vs sb3 躲者 第 22 局：crash_evader @ 9648 s → timeout @ 9856 s（最近 71.9 → 71.9 km）
  - rollout_pursuer vs sb3 躲者 第 23 局：crash_evader @ 7005 s → timeout @ 7291 s（最近 110.9 → 110.9 km）
  - sb3 追者 vs escape_evader 第 5 局：crash_evader @ 7399 s → timeout @ 8255 s（最近 1383.5 → 1383.5 km）
  - sb3 追者 vs sb3 躲者 第 0 局：crash_evader @ 10478 s → timeout @ 11407 s（最近 2884.7 → 2884.7 km）
  - sb3 追者 vs sb3 躲者 第 1 局：crash_evader @ 7413 s → timeout @ 8045 s（最近 124.6 → 124.6 km）
  - sb3 追者 vs sb3 躲者 第 5 局：crash_evader @ 7319 s → timeout @ 8255 s（最近 171.3 → 171.3 km）
  - sb3 追者 vs sb3 躲者 第 6 局：crash_evader @ 9885 s → timeout @ 10527 s（最近 3455.4 → 3455.4 km）
  - sb3 追者 vs sb3 躲者 第 8 局：crash_evader @ 7993 s → timeout @ 8389 s（最近 967.9 → 967.9 km）
  - sb3 追者 vs sb3 躲者 第 14 局：crash_evader @ 9884 s → timeout @ 10797 s（最近 2134.9 → 2134.9 km）
  - sb3 追者 vs sb3 躲者 第 20 局：crash_evader @ 11397 s → timeout @ 12028 s（最近 3484.6 → 3484.6 km）
  - sb3 追者 vs sb3 躲者 第 21 局：crash_evader @ 8818 s → timeout @ 9381 s（最近 153.9 → 153.9 km）
  - sb3 追者 vs sb3 躲者 第 22 局：crash_evader @ 8980 s → timeout @ 9856 s（最近 453.1 → 453.1 km）
  - sb3 追者 vs sb3 躲者 第 23 局：crash_evader @ 6415 s → timeout @ 7291 s（最近 117.2 → 117.2 km）
