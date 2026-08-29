# DifferentialCorrector 的替代演算法（備援用）

**日期**：2026-08-29　**腳本**：`dc_algorithms.py`（第一版，比不出東西）、`dc_stress.py`（有效版）

## 為什麼

`src/script_generator.py:70` 產生的是 `Create DifferentialCorrector DC_Targeter;` ——
全部吃 GMAT 預設值，也就是 `NewtonRaphson` + `ForwardDifference`。
文件（`docs/help/html/DifferentialCorrector.html`）寫還有：

* `Algorithm` = `NewtonRaphson` / `Broyden` / `ModifiedBroyden`
* `DerivativeMethod` = `ForwardDifference` / `BackwardDifference` / `CentralDifference`
  （只在 `NewtonRaphson` 下生效）

比賽當天最怕 Targeter 不收斂。多知道一組備援設定就是保險。

## 第一次測失敗，但失敗本身是個結果

直接拿官方範例題目的 `outputs/output.txt` 跑五種演算法 → **五份輸出位元相同**，
全部 1 次迭代、0.2 秒。原因看 GMAT 的 stdout 就懂了：

```
DC_Targeter Iteration 1; Nominal Pass
   ShipB.EarthMJ2000Eq.X  Desired: -6683.677012  Achieved: -6683.67927654  Variance: 0.00226
   ShipB.EarthMJ2000Eq.Y  Desired: -1376.3660598 Achieved: -1376.36767644  Variance: 0.00162
   ShipB.EarthMJ2000Eq.Z  Desired: -1399.6841401 Achieved: -1399.68368371  Variance: -0.00046
*** Targeting Completed in 1 iterations.
```

**Python 給的初始猜測誤差只有 2.3 / 1.6 / 0.5 公尺**，已經落在 Achieve 容許（0.01 km = 10 m）
之內，DC 在 nominal pass 就收斂，根本沒有機會展現演算法差異。

這件事本身值得記：我們交出去的腳本，GMAT 的 targeter 實際上沒在「解」什麼，只是確認了一遍。

## 有效的測法：把初始猜測打歪

那才是比賽當天真正的失效模式（Python 端算歪，要靠 GMAT 救）。
三個 `Vary` 的初始值按元素號輪流 ±（避免三個同向剛好變成純量縮放）。

| 猜測誤差 | 全部五種是否收斂 | 迭代數 | 各演算法最終 Δr 差異 |
|---|---|---|---|
| 0 %  | ✅ | 1 | 0 |
| 2 %  | ✅ | 3 | 0.02 m |
| 10 % | ✅ | 4 | 0.6 m |
| 35 % | ✅ | 7 | **3.1 m** |
| 10 %（容許收到 0.1 m）| ✅ | NR 4 / Broyden 5 | 0 |

**五種演算法在每一個設定下都收斂**，最終 Δr 差異最大 3.1 公尺，遠在 10 公尺容許之內。

## 真正的差別在成本，不在收斂性

同一組（猜測歪 35%、7 次迭代），數 GMAT stdout 裡的擾動傳播次數：

| 演算法 | 擾動傳播次數 | 說明 |
|---|---|---|
| `NewtonRaphson` + `ForwardDifference` | 18 | 3 變數 × 6 次重建 Jacobian |
| `NewtonRaphson` + `CentralDifference` | **36** | 正好 2 倍 —— 確認這個欄位真的有生效 |
| `NewtonRaphson` + `BackwardDifference` | 18 | |
| `Broyden` | **3** | Jacobian 只建一次，之後用秩一更新 |
| `ModifiedBroyden` | **3** | |

`CentralDifference` 那 36 次是重要的旁證：三種差分法給出**位元相同**的最終答案，
一度讓我懷疑 GMAT 根本沒理這個設定。數擾動 pass 才確認有生效 ——
是這個問題本身夠線性，Jacobian 怎麼算都收斂到同一點。

## 結論

**不改預設。** 繳交腳本一次跑 0.2 秒，18 次還是 3 次擾動傳播完全沒差，
而 `NewtonRaphson` 是 GMAT 預設、最多人驗證過的路徑。

**但當天如果 Targeter 卡住，備援順序是：**

1. 先看 stdout 的 `Variance` —— 如果 nominal pass 就已經在容許內，問題不在 targeter。
2. `GMAT DC_Targeter.Algorithm = 'Broyden';` —— 擾動傳播少 6 倍，長傳播情境下差別會放大。
3. `GMAT DC_Targeter.DerivativeMethod = 'CentralDifference';` —— 成本 2 倍，
   但如果是 Jacobian 品質的問題（步長跟靈敏度不匹配），這個最有機會救。
4. 這兩行直接插在 `Create DifferentialCorrector DC_Targeter;` 後面即可，其餘不動。
