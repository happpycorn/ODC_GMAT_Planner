# 拆棒 STM Jacobian 驗證（2026-10-28）

從 `outputs/stm_validation/report.md` 收進版控（原檔與跑檔封存在 `~/Documents/Program/ODC_archive_pre1109/`）。
當時 `SPLIT_JACOBIAN="stm"` 是選用；之後 commit `1277cf0` 改成預設，排位賽當天跑的就是這條路徑。

hyper_far、180 s 預算、3 workers：fd 拆棒 179 s、stm 24 s（7.3 倍），兩者 8 棒、分數差 6.5e-7。

---

已完成可選的 `strategy.SPLIT_JACOBIAN="stm"`，預設仍為 `"fd"`，未 commit。

原本的 propagate_dop853、容差、物理模型、scorer 與 GMAT 腳本均未修改。新增傳播器沿用原六維單步與誤差控制；接受步之後，以相同 RK stages 積分 36 個 STM 分量。這是 42 維方程的分塊積分，STM 的大小不會影響狀態步長。600、6,000、40,000 秒的 B 初始軌道傳播，r/v 均與原傳播器逐位元相同。

變分方程為 dPhi/dt = [[0,I],[G,0]] Phi。二體的 G = mu/r³ (3 rrᵀ/r²-I) 使用解析式；J2–J4 對原 perturbation_accel 作三個方向的中央差分，每個 stage 六次攝動加速度評估，h=cbrt(eps)|r|。各攝動項分開及合開皆已對獨立中央差分驗證。

令 S=d(r,v)/dx。各部分的處理如下：

- t0：先用原 fixed_orbit_state 取得等待末狀態，S 的 t0 欄設成燃燒前 f(y_wait)。這包含完整 J2–J4 加速度，並適用 ephemeris 檢查點之間的局部分支。
- dv_i：在第 i 次燃燒前的 S 加上對應三欄的 [0;I]，再經後續各弧的 Phi 傳下去。
- coast_i：先算 S_end=Phi_i S_start，再對該段 coast 欄加 f(y_end)。這個 f 是下一棒之前的動力學，後續脈衝的狀態跳躍 Jacobian 為 I。
- T_team=t0+sum(coasts)：t0 與所有 coast 欄為 1，其餘為 0。末端相對位置的導數是 S_final[:3]-v_A outer dT；miss 再乘上單位相對位置向量。
- 每棒 norm 的梯度為 dv/|dv|，total_dv 將它們相加。計分對 T、總 dv 與 miss 的偏導依原 scorer 的分支與指數截斷組合；m/s 的 1000 倍亦包含在內。
- arc_minr：沿用原 reaches_perigee 與端點 min 的分支。端點分支用 r/|r| 乘上對應 S；近地點分支用解析式 rp=|r×v|²/[mu(1+e)] 的梯度再乘 S。此式與原束縛軌道的 a(1-e) 代數等價，但不更動原函數值。非束縛向外分支為 |r|。
- 等待弧：選中等待末端時，導數為 r_hat dot v；初始半徑、密切近地點與已完成的 ephemeris prefix 都是該分支內的常數，導數為 0。所有 min/分支相等點取一個分支，零 dv、零 miss 與正圓的 norm 使用零次梯度。

梯度檢查使用獨立九點中央差分，計分 stencil 留在 miss=5 km 的同一側。兩個實際存檔 route 的暖啟各抽五點，另檢查五個含 ephemeris 的 ranking_round 點。隨機擾動為時間 0.05–0.2 秒、dv 各分量標準差 2 m/s。fixture 已收進 tests/fixtures，測試不依賴 outputs 存檔存在。

| 檢查 | 最大誤差 |
|---|---:|
| Phi 各欄相對範數 | 4.882e-8 |
| Phi 逐元素混合相對誤差 | 6.429e-7 |
| hyper_far 完整 NLP Jacobian | 2.041e-6 |
| ranking_round 完整 NLP Jacobian | 1.510e-6 |
| ranking_round + ephemeris | 1.722e-6 |

完整 Jacobian 逐元素使用 abs(error)/max(abs(reference),2) < 1e-5，即小元素的絕對門檻 2e-5；Phi 的混合誤差分母下限為 1，另獨立限制每欄相對範數 <1e-6。r_final、T_team、total_dv 與各項約束的內部指標導數亦逐一檢查。計分平坦區、指數截斷及三種近地點分支另有獨立純函數檢查。

相對於改動前 HEAD，joint_nlp_split 與 legalize_route 在原始 FD、疊合 FD 路徑各比對一次（10 次迭代），所有回傳欄位均逐位元相同。相關紀錄在 validation/fd_baseline.log。

實測由指定 hyper_far winner 存檔複製，僅加入 Jacobian 模式並將兩者牆鐘預算同設 180 秒；其餘設定保留，包括 workers=3、multistart=[0,0.75,1]、prune=1 m/s。兩種模式依序執行，量測時未並行其他重測試。計時以 legalize_route 入口包裝，不包含載入 optimizer 的時間。

| 模式 | 拆棒秒數 | 最終分數 | 棒數 | 撞到 180 s 預算 |
|---|---:|---:|---:|---|
| fd | 179.189097 | 82.43267897088518 | 8 | 否 |
| stm | 24.460606 | 82.43267962551909 | 8 | 否 |

STM 快 7.3256 倍，分數增加 6.546339e-7。兩份 mission 皆 Earth-safe、未失格且 miss <5 km。多行程與多起點在這次正式重播中均實際使用；STM 不使用 FDPool 分攤擾動點。STM 的新函數 JIT 編譯時間包含在拆棒計時內。

重跑指令（沙盒中的 uv 需離線並使用可寫快取）：

```sh
MPLCONFIGDIR=/tmp/odc-mpl UV_CACHE_DIR=/tmp/odc-uv-cache uv run --offline --no-sync python tests/test_split_stm.py
MPLCONFIGDIR=/tmp/odc-mpl UV_CACHE_DIR=/tmp/odc-uv-cache uv run --offline --no-sync python run_regression.py
MPLCONFIGDIR=/tmp/odc-mpl UV_CACHE_DIR=/tmp/odc-uv-cache uv run --offline --no-sync python outputs/stm_validation/benchmark.py --from-winner outputs/stm_validation/winner_fd.json --stop-after solve --run-dir outputs/stm_validation/fd-rerun
MPLCONFIGDIR=/tmp/odc-mpl UV_CACHE_DIR=/tmp/odc-uv-cache uv run --offline --no-sync python outputs/stm_validation/benchmark.py --from-winner outputs/stm_validation/winner_stm.json --stop-after solve --run-dir outputs/stm_validation/stm-rerun
```

未完成驗證的範圍是沙盒外的 Manager socket 與 GMAT 寫入相關端到端測試；600 秒原始預算未另跑，這次統一比較 180 秒。不可微邊界的梯度採上述分支/次梯度約定，不宣稱在這些點存在唯一 Jacobian。

最終完整回歸為 20/24 通過，299.9 秒；test_split_stm.py 通過（37.2 秒）。其餘四支均屬指定排除範圍：

- test_hyperbolic_e2e.py：multiprocessing.Manager 的 socket bind 被沙盒拒絕。
- test_no_legal_route_e2e.py：同一個 Manager socket 限制。
- test_retarget_gmat_e2e.py：GMAT 無法寫入 ../output/GmatLog.txt 與執行檔目錄的替代 log。
- test_revs_schedule.py：使用者指定排除；multiprocessing spawn 階段失敗。

完整逐支輸出在 validation/regression.log。禁止修改的檔案均未改動；propagate_dop853 的原始文字與 HEAD 完全相同。二體加速度、J2–J4 加速度、DOP853 單步與誤差估計函數的 AST 亦確認未改。
