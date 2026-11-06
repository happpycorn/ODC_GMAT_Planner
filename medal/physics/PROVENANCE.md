# physics/ 的來源與改動（vendored from ODC_GMAT_Planner）

這個套件是把隔壁 `ODC_GMAT_Planner` **已與 GMAT 交叉驗證到公尺級**的純 numba 物理，
複製進本 repo 當 DRL env 的模擬器。訓練要跑幾百萬步，不可能每步呼叫 GMAT；GMAT 只
在最終驗證用（見 Linear HAP-56）。

## 來源
- 來源 repo：`ODC_GMAT_Planner`（兄弟目錄）
- 對應 commit：**`ae0032a`**（複製當下 2026-09-10）
- 對應 Linear 卡：**HAP-51**（接上 Planner 物理當模擬器）

## 為什麼用 vendor（複製）而不是直接 import 隔壁
1. Planner 需 Python 3.12 + poliastro 0.17 + **numpy 1.26**；本 repo 是 numpy 2.x
   （torch/sb3 需要），poliastro 0.17 與 numpy 2.x 不相容。
2. Planner 的 `src/` 沒有 `__init__.py` 且到處 `from src.xxx import`，當函式庫從外部
   import 很脆、且會跟本 repo 潛在的 `src` 命名衝突。
3. vendor 讓本 repo 能獨立跑、可逆（刪掉即可）、且不動到還在開發中的 Planner。

長期若要收斂成單一來源，這裡的結構（獨立 `physics/` 套件）可直接抽成可 pip 安裝的
共享套件。

## 各檔案的忠實度
| 檔案 | 狀態 |
|---|---|
| `core_math.py` | **逐字複製**，只把最上面 poliastro 的兩行 import 包成 try/except（見檔內 `VENDORED CHANGE` 註解）。poliastro 只被 Encke 傳播器用到；DRL 用的 `propagate_dop853` 不需要它。 |
| `scorer.py` | **逐字複製**，未改。 |
| `propagator.py` | **改寫**：`propagate()` 的包裝與常數與 Planner 對齊，但 `get_r0_v0()`（六根數→Cartesian）改用自帶純 numpy 實作，拿掉 poliastro/astropy 相依。另加 `orbital_period()`。 |

## 本 repo 原生（非 vendored）的物理模組
`lambert.py`、`intercept.py`、`coast.py`、`frames.py` 是本 repo 為決賽寫的，不在 Planner 裡。
`lambert.py` 用 `tools/compare_lambert_poliastro.py` 跟 Planner venv 的 poliastro izzo 比對過
（1000 案例，雙方可解/不可解判定完全一致，速度差最大 1.4e-14 km/s）。

## 同步注意
若 Planner 的 `core_math.py` / `scorer.py` 有實質更新，需手動同步這裡並更新上面的 commit。
`get_r0_v0` 因為是改寫版，不要直接覆蓋；只在數值定義（mu 等）變動時對齊。
