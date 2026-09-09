"""適應度函式（搜尋用的代理）跟重播（真實成績）差多少，跟飛行時間有沒有關係。

背景：hard_mode 的 3 棒種子精修後 fitness -80.7，但重播出來的真實 Score 只有 72.3；
有一個更誇張，fitness -78.3 對上真實 Score 1.1（ΔV 13,661 m/s）。

猜測的機制：fast_fitness_evaluator 的最後一棒直接用 izzo 的**純二體** Lambert 解算 Δv，
而重播會用 refine_lambert_burn 把它修正成「含 J2/J3/J4 之後仍然命中」的 Δv。飛行時間
越長，二體解偏離得越多，要補的修正量就越大——hard_mode 的最後一段長達 7 天。

如果成立，那對初賽（LEO、T_max 只有 6.4 小時）影響應該很小，但這件事必須量出來，
不能用猜的。
"""
import sys, json, numpy as np
sys.path.insert(0,"/home/corn/ODC_GMAT_Planner")
import warnings; warnings.filterwarnings("ignore")
from scipy.optimize import minimize
from src.optimizer import MissionOptimizer

SP="/tmp/claude-1000/-home-corn-ODC-GMAT-Planner/a52dbbe3-5991-419b-8818-0d22c7a0e531/scratchpad"

def survey(label, cfg, nb, seeds):
    opt=MissionOptimizer(cfg); f=opt._fitness_wrapper(nb)
    lb,ub=opt._generate_bounds(nb)
    print(f"\n=== {label}（{nb} 棒，T_max {opt.T_max:,.0f}s）===", flush=True)
    print(f"  {'代理分數':>10}{'真實分數':>10}{'落差':>9}"
          f"{'最後一段(s)':>14}{'真實ΔV(m/s)':>13}{'違規':>5}", flush=True)
    rows=[]
    for sd in seeds:
        x=np.asarray(sd,dtype=np.float64)
        try:
            r=minimize(fun=f, x0=x, method='L-BFGS-B',
                       bounds=opt._narrow_tolerance_bounds(x,lb,ub),
                       options={'maxiter':50})
            xr=np.asarray(r.x,dtype=np.float64)
        except Exception:
            continue
        proxy=-float(f(xr))
        try: m=opt.mission_metrics(xr, nb)
        except Exception: continue
        # 最後一段飛行時間：重播的 T_team 減掉最後一棒的時刻，用 x 反推比較麻煩，
        # 這裡直接用 T_team 當長度的代表（hard_mode 的最後一段占絕大部分）
        rows.append((proxy, m['score'], m['t_team'], m['dv_mps'], m['penalty_count']))
        print(f"  {proxy:>10.3f}{m['score']:>10.3f}{proxy-m['score']:>9.2f}"
              f"{m['t_team']:>14,.0f}{m['dv_mps']:>13,.1f}{m['penalty_count']:>5d}", flush=True)
    if rows:
        gaps=[abs(r[0]-r[1]) for r in rows]
        print(f"  -> 落差 最大 {max(gaps):.2f} 分、中位數 {sorted(gaps)[len(gaps)//2]:.2f} 分", flush=True)

# A. hard_mode 診斷變體（最後一段長達數天）
cfg=json.load(open(SP+"/hard_mode_flat.json")); cfg.pop("local",None)
opt=MissionOptimizer(cfg)
survey("hard_mode 變體", cfg, 3, opt._generate_ladder_seed_candidates(3, 30))

# B. 官方範例題目（LEO，T_max 只有 6.4 小時）——初賽真正要面對的尺度
cfg2=json.load(open("/home/corn/ODC_GMAT_Planner/configs/official_sample.json")); cfg2.pop("local",None)
opt2=MissionOptimizer(cfg2)
for nb in (1,2):
    survey("官方範例題目", cfg2, nb, opt2._generate_seed_candidates(nb, 20))
print("\nPROXY DONE", flush=True)
