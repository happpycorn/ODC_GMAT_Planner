# GMAT/Yukon 獨立求解器對照

**問題**：官方範例題目（2026-08-28 注意事項第八節）。
**目的**：拿 GMAT 自己的 `Yukon` 非線性最佳化器當**獨立實作**，檢查我們的答案是不是局部最佳。
跟我們的程式零共用，只共用 GMAT 的傳播器（那本來就是我們的驗證基準）。

## 設定

抵達時間釘在我們的 3,158.3 s、第一棒在 t=0，Yukon 變兩棒的 VNB 分量，最小化總 Δv，
約束 `missDist <= 5 km`。初始猜測**就是我們的答案** —— 所以這回答的是「我們的解是不是
局部最佳」，不是「Yukon 能不能從零找到它」。

## 結果

| | 總 ΔV | Δr | dv1 | dv2 |
|---|---|---|---|---|
| 我們的工具 | 2,242.0 m/s | 2,359 m | 1,498.0 | 743.9 |
| GMAT Yukon | **2,240.5 m/s** | 4,627 m | 1,497.0 | 743.5 |

**差 1.5 m/s（0.07%）。** 我們的解實質上就是局部最佳。那 1.5 m/s 對應的是平手微調把
Δr 從 4.6 km 壓到 2.36 km 的代價（約 0.009 分），跟 `TIEBREAK_SCORE_EPS=0.005` 的預算一致。

## 🔴 踩到的三個坑（下次要用 GMAT 當求解器時直接看這裡）

1. **腳本路徑要絕對路徑。** GmatConsole 會把工作目錄切到自己的 `bin/`，相對路徑一律
   `does not exist`。

2. **Yukon 吃不下多個不等式約束。** 6 變數 + 3 個 `NonlinearConstraint` →
   `ArrayTemplate error : dimension error`（跑了 6 次迭代才炸，是資料相關的）。
   1 個約束就正常收斂。分離測試：
   - `yukon_noopt.script`（拆掉 Optimize）→ 正常，重現我們的答案
   - `yukon_varA.script`（6 燃燒變數 + 3 約束）→ ArrayTemplate
   - `yukon_varB.script`（1 變數 + 3 約束）→ `Rmatrix is singular`（預期，欠定）
   - `yukon_A1.script`（0 約束）→ 正常，Δv 掉到 0.04（無約束最小值當然是不燒）
   - `yukon_A2.script`（1 約束）→ 收斂，但**在不可行點終止**（見下）
   - `yukon_A3.script`（1 約束 + 修好步長與尺度）→ **正常收斂到可行解**

3. **`MaxStep` 必須配合約束的靈敏度，不然會在不可行點終止。**
   A2 用 `MaxStep = 0.05 km/s`，但最後一段飛 2,124 秒，那個步長會造成 **~106 km** 的
   位置變化，而約束只有 5 km——步長比約束大 20 倍，QP 走不穩，Yukon 就靠放棄約束來
   降成本（終止時 missDist = 785 km）。
   算法：`MaxStep < 約束容許 / 飛行時間` = 5 / 2124 ≈ 0.0024 km/s。實際用 0.0005。
   同時把 `missDist` 縮放成 `/100`（原本量級到數百 km，Δv 只有 1 上下，QP 病態）。

4. **非 ASCII 一樣會炸**（這個坑第四次踩到）：用 `sed` 產生變體腳本時插了中文註解，
   GMAT 直接 `contains characters outside of the ASCII character set`。

## 檔案

- `yukon_intercept.script` — 原始版（3 約束，會炸，保留當證據）
- `yukon_A3.script` — **可用的版本**
- 其餘 `yukon_*.script` 是分離測試用的變體
