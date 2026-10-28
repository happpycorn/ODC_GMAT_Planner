# AIAA Capture the Satellite Challenge 考古（2026-10-28）

目的：TASA 0510 簡報點名這個比賽，金／銅牌賽（一追一躲、角色當天抽籤、公用電腦下指令投大螢幕）很可能參考它的形式。
這份整理**已驗證**的資料，並標出對我們有用的地方。未驗證的說法放在最後一節。

## 比賽本體（已驗證）

- 由 MIT Lincoln Laboratory 主辦，在 AIAA SciTech 現場決賽：2024 年第一屆，2025 年第二屆，2026 年第三屆（1/15，Orlando）。
  平台是開源的 [mit-ll/spacegym-kspdg](https://github.com/mit-ll/spacegym-kspdg)（Kerbal Space Program＋kRPC，Gymnasium／PettingZoo 介面）。
  平台論文：SpaceGym（[IEEE Aerospace 2023](https://ieeexplore.ieee.org/document/10115590/)）。
- 賽制（[ERAU 新聞](https://news.erau.edu/headlines/embry-riddle-student-team-earns-first-place-in-capture-the-satellite-competition)、kspdg README）：
  8 月開賽，期間每月開會，12 月準決賽，1 月 SciTech 現場決賽。參賽隊伍在自己電腦上評估 agent，再把結果上傳排行榜。
  **決賽給 3 天，而且題目放了一個之前沒見過的新元素**（2026 年是突然多一顆保鑣衛星）。
  主辦人 Ross Allen 的說法是想看隊伍做的東西夠不夠穩健，不會一碰到新狀況就壞掉。
- 歷年題型（kspdg [CHANGELOG](https://github.com/mit-ll/spacegym-kspdg/blob/main/CHANGELOG.md)）：
  - 2024：追逃 `pe1`，以及 Lady-Bandit-Guard `lbg1`。v0.5.1 是「SciTech 2024 Finals Codebase」，還加了「給觀眾看的即時分數」。
  - 2025：`LBG1_LG3`～`LG5`，原始碼經過混淆，內建進階 bot。
  - 2026：`LBG1_LG6`。參賽者控制 bandit，要捕獲故障衛星 lady，同時躲開保鑣 guard。
- 得獎隊伍：
  - 2026：Embry-Riddle XDLab 第一（52 隊），CU Boulder AVS Lab 第二，UPM–MIT 第三。
    ERAU 的方法是**古典軌道力學與 AI 的混合**。理由是「只用 AI／ML 有風險，很難解釋 AI 叫你做什麼」（[ERAU 新聞](https://news.erau.edu/headlines/embry-riddle-student-team-earns-first-place-in-capture-the-satellite-competition)）。
  - 2025：陽明交大 ARRC 第三（34 隊），用 **NMPC（非線性模型預測控制）**（[陽明交大新聞](https://sdgs.nycu.edu.tw/nycu-arrc-team-wins-third-place-at-aiaa-scitech-capture-the-satellite-challenge/?lang=en)）。
  - UPM–MIT 團隊論文：[Language Models are Spacecraft Operators（arXiv:2404.00413）](https://arxiv.org/abs/2404.00413)，用 LLM 當操控員。

## 追逃題 `pe1` 的規格（直接讀原始碼 `src/kspdg/pe1/`）

- 1 對 1，參賽者控制追方，逃方由程式控制。兩艘船的參數相同；逃方初始軌道固定，追方初始軌道有 4 種：
  i1 橢圓／圓切向交會、i2 相對傾斜、i3 同軌約 3 km、i4 傾斜加相位不同步。
- **尺度跟我們完全不同**：回合上限 240 s，捕獲距離 5 m，用的是 RCS 連續推力（每噴嘴 1000 N、Isp 240 s）。
  屬於近接操作，跟 TASA 的遠距脈衝機動（GMAT）不同。簡報也說了本賽著重遠距靠近，AIAA 著重近接。
- **計分**（分數越低越好）：`(0.1·d)^2 + (0.5·v)^1.5 + (0.1·f)^1.25 + (0.01·t)^1`。
  d 是最近距離（m），v 是最近時的相對速度，f 是追方燃料（kg），t 是到最近點的時間。
  設計意圖：**先比最近距離，再比相對速度，然後是燃料，最後才是時間**。
- **逃方 bot 的四種策略**：
  - e1：完全不機動。
  - e2：追方進入 2.2 km 控制範圍後，隨機選姿態、推力和時長。
  - e3：追方進入 **200 m 時全推力往軌道法向（normal）噴**，離開範圍就關掉。
  - e4：不管追方在哪，持續小推力順著速度方向（prograde）抬升軌道。

## 對金／銅牌賽的啟示（推論，需規則公布後確認）

1. **TASA 的形式很像 `pe1`，但勝負是二元的**：追方在時間與燃料內靠近就贏，否則躲方贏。
   AIAA 用連續分數，而且最近距離排第一優先，方向一致。
2. **規則很可能晚公布，或比賽當下才加新元素**（AIAA 決賽前 3 天才放新元素）。
   所以要準備的是**快速重規劃**的能力，而不是針對單一情境調到最好。
   `~/ODC_GMAT_DRL` 的 rollout 規劃器＋copilot 要能在幾分鐘內，對任何初始狀態給出合法指令。
3. **兩種角色都要準備**：抽到躲方的機率是 50%。kspdg 的逃方啟發式（e3 法向噴、e4 持續抬升）可以當躲方基準策略，
   也可以拿來當練追方的對手。在脈衝、遠距的尺度下哪個有效，要在 DRL repo 裡實測，不能直接照搬。
4. **方法選擇**：冠軍用古典＋AI 混合、季軍用 NMPC。在只有 90 分鐘、現場又有新狀況的條件下，
   以可解釋的古典方法（Lambert／primer／rollout）當主力最穩。

## 未驗證（Gemini 的說法，找不到原文）

- KAIST licspace（Han-Lim Choi）「連續兩屆冠軍」。
- CU Boulder 用 Basilisk 加深度強化學習，練出打帶跑戰術。
- 逃方 e4 的描述跟原始碼一致（已驗證），但 Gemini 對 e3 的描述「法向或反向」不精確，原始碼是只往法向。
- Gemini 第一次給的 arXiv 編號 2303.01633 是錯的，對應到一篇無關的 6G 綜述。
