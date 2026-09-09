# 情境 C（Claude 壞掉）── 改用 Gemini 手動完成

> 什麼時候切到這張：Claude / Claude Code 連不上、當機、或帳號/額度出問題。
> **先深呼吸——這不是災難。** 你比賽時真正要跑的工具是**純 Python，一個字都不依賴 Claude。**
> Claude 平常只是幫你「下指令的介面 + 判斷 + debug」。這三件事，Gemini 都接得住（規則明文允許 Gemini）。

## 第一件事：認清「工具不需要 Claude」

- 找 burn、驗證、產繳交檔，全靠 `uv run python ...` 這些指令，**在終端機直接敲就會跑**。
- Claude 掛掉 = 你少了一個「幫你想、幫你讀報錯」的助手，**不等於工具停擺**。
- 所以策略很簡單：**指令照這張卡逐行敲；需要判斷或 debug 時，把資訊貼給 Gemini 問。**

---

## 一、照抄就能跑的指令序列（在遠端機或 Mac，哪台活著用哪台）

```bash
cd <專案路徑>            # 遠端機是 ~/ODC_GMAT_Planner
# 1. 抄題後，把 A/B 六根數 + k_t/C_t/k_v/C_v 填進 configs/contest.json（範本見 CONTEST_DAY.md §5.1）
#    ⚠️ 單位：k_v = 官方 kv ÷ 1000、C_v = 官方 Cv × 1000；k_t/C_t 照抄

# 2. 體檢（數字不對就是抄錯，回頭核對）
uv run python check_problem.py --config configs/contest.json

# 3. 可行性
uv run python feasibility.py --config configs/contest.json

# 4. 省油/預設分支（有 GMAT 就拿掉 --no-gmat）
uv run python main.py --config configs/contest.json --no-gmat

# 5. 快解分支：把 contest.json 複製成 fast.json，加一行 "T_MAX_SEC": <秒數> 到 rules 區塊，再跑
uv run python main.py --config configs/fast.json --no-gmat

# 6. 選分數高的那條，換 SEED 再跑 1–2 次取最好，產出 outputs/output_submit.txt
```

**GMAT 驗證**（有 GMAT 的機器）：把上面 `--no-gmat` 拿掉即可，或指定路徑
`--gmat-console <GmatConsole 路徑>`。沒 GMAT 就 `--no-gmat`，驗證留到主辦機（見情境 B）。

---

## 二、怎麼讀工具的輸出（沒有 Claude 幫你唸，自己看這幾行）

跑完 `main.py` 找這幾個東西：

| 要找的 | 意思 | 判準 |
|---|---|---|
| **違規次數** | 有沒有超過 ΔV/間隔限制 | 必須 **= 0** |
| **Score** | 總分 | 兩條分支比這個，高的贏 |
| **Δr_min** | 最近相對距離 | 必須 **< 5,000 m** |
| **ΔV_team / T_team** | 總燃料 / 完成時間 | 記下來（§6 同分判定用）|
| **GMAT 區塊**（有跑驗證時）| 命中 / Targeter / 最後一棒 | 三個都要 ✅ |
| 檔案 | 繳交用 | **`outputs/output_submit.txt`**（不是 output.txt）|

---

## 三、Gemini 怎麼用（有界、可對答案的任務——別讓它「操作」，讓它「檢查/建議」）

Gemini 不能跑你的工具，但能幫你想清楚。**把它當計算器和第二意見，不當真理。** 常用四招：

### 1) 手算/複核分數（驗證單位換算、或比較兩條分支）
貼給 Gemini：
> 規則計分公式：`Score = 50*exp(-(Δr_min-5)/100) + 25/(1+e^{k_t*(t-C_t)}) + 25/(1+e^{k_v*(ΔV-C_v)}) - ΣP`。
> 參數 k_t=__, C_t=__, k_v=__, C_v=__（注意 ΔV 單位是 m/s）。我的解 Δr_min=5、t=__ s、ΔV=__ m/s、無違規。
> 幫我把三項分別算出來、加總。

**校準檢查**：拿官方參考解（範例題是 ΔV 2241.427 m/s、t 3211.737 s）算，應得 **50 + 22.5 + 17.5 = 90.00**。
算出來離譜 → `k_v/C_v` 的 ÷1000/×1000 換錯了（見 CONTEST_DAY.md §四）。

### 2) 算「該追快解還是省油解」
> A 軌道週期 T_A=__ s，所以 T_max=4*T_A=__。C_t=__。幫我算 C_t/T_max，並判斷時間項卡得緊不緊。

（比值很小＝時間很貴、主攻快解；很大＝省油解也有戲。不確定就兩條都跑、比 Score。）

### 3) debug Python 報錯
> 我跑 `uv run python main.py --config configs/contest.json` 出現這個 traceback：<貼完整錯誤>。
> 這是什麼原因、怎麼修？

常見坑：config JSON 格式錯（少逗號/引號）、六根數打成字串、路徑不對。多半是 config 手打的問題。

### 4) 幫忙讀/填 GMAT script 的 burn（提交那步）
> 這是我工具產出的 burn table：<貼 output_submit.txt 裡的機動段>。
> 幫我核對每棒 |dV| 有沒有 ≤ 1500 m/s、時間間隔有沒有 ≥ 100 s。

⚠️ **Gemini 產的任何 GMAT script 片段，貼進主辦機前先確認全是 ASCII（沒有中文/全形字元）**，
否則 GMAT 解析會直接失敗（歷史踩過三次）。

---

## 四、判斷哪些事「不需要 AI」——直接照規則做就好

- **快 vs 省油**：不用糾結，**兩條都跑，Score 高的贏**。這是規則層級的客觀比較，不需要判斷。
- **要不要多棒**：`feasibility.py` 說單棒不可行才往上加 `MAX_BURNS`。照它說的。
- **同分**：比 `Δr_min` → `ΔV_team` → `T_team`（§6），工具會印，記下來即可。
- **繳哪個檔**：永遠是 `outputs/output_submit.txt`。

---

## 五、最壞情況的底線

就算 Claude、遠端機**同時**掛：Mac 上 `uv run python main.py --config configs/contest.json --no-gmat`
還是會給你一個解，`output_submit.txt` 照樣產出，帶去主辦機驗證 + 提交。**只要 config 抄對，就交得出東西。**
所以賽前把力氣花在：① 隊友 A 的抄題核對 ② Mac 離線自足驗過 ③ 提交流程彩排過。這三件比任何工具都保險。
