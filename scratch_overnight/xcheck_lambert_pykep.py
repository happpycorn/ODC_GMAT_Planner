"""拿 ESA 的 pykep 交叉驗證我們的多圈 Lambert 分支選擇。

背景（2026-08-28）：這天把 `izzo()` 的呼叫從寫死 `M=0` 改成掃
`M x lowpath x 順/逆行`，官方範例題目上省 38% 燃料。但那個改動**完全沒有外部檢查**——
分支挑錯會直接汙染繳交的答案。

pykep 是 ESA Advanced Concepts Team 維護的獨立實作，`lambert_problem` 會一次回傳
所有解（理論上 2N+1 條，N 是實際塞得下的圈數）。這裡做集合比對：

  1. **我們的每一條解，在 pykep 的解集合裡找不找得到**（找不到 = 我們算出了假解）
  2. **pykep 有而我們沒有的解**（漏解 = 少賺，不是錯）
  3. 解的數量符不符合 2N+1

pykep 3.0.1 的 wheel 漏打包 `trajopt/gym/tops/*.json`，import 會炸；跑之前要先補四個
空 json 進去（見本檔開頭的 _patch_pykep()）。這是 uv 快取目錄，可重建。

跑法：uv run --with pykep python scratch_overnight/xcheck_lambert_pykep.py
"""

import glob
import math
import os
import sys

import numpy as np

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

import warnings
warnings.filterwarnings("ignore")
from poliastro.core.iod import izzo

MU = 398600.4418
TOL_KMS = 1e-6          # 兩邊算出的 v1 差多少算「同一條解」


def _patch_pykep():
    """補上 pykep 3.0.1 漏打包的資料檔，否則 import pykep 直接 FileNotFoundError。"""
    for d in glob.glob("/home/corn/.cache/uv/archive-v0/*/lib/python3.12/"
                       "site-packages/pykep/trajopt/gym"):
        tops = os.path.join(d, "tops")
        os.makedirs(tops, exist_ok=True)
        for name in ("_tops_cr3bp", "_tops_twobody", "_tops_ss", "_tops_mee"):
            p = os.path.join(tops, name + ".json")
            if not os.path.exists(p) or os.path.getsize(p) == 0:
                with open(p, "w") as f:
                    f.write("{}\n")


def our_branches(r0, r1, tof, prograde, max_revs):
    """我們的分支政策（跟 fast_fitness_evaluator / reconstruct_mission_logs 一致）。"""
    out = []
    for m in range(0, max_revs + 1):
        for lowpath in (True, False):
            if m == 0 and not lowpath:
                continue                      # M=0 只有一組解
            try:
                v1, _ = izzo(MU, r0, r1, tof, M=m, prograde=prograde,
                             lowpath=lowpath, numiter=35, rtol=1e-8)
            except Exception:
                continue
            v1 = np.asarray(v1, dtype=np.float64)
            if np.all(np.isfinite(v1)):
                out.append(((m, lowpath), v1))
    return out


def random_case(rng):
    """隨機幾何，涵蓋同平面/大傾角差、短/長 tof、LEO 到高軌。"""
    r_a = rng.uniform(6700.0, 30000.0)
    r_b = rng.uniform(6700.0, 30000.0)
    # 隨機兩個方向（不共線）
    def unit():
        v = rng.normal(size=3)
        return v / np.linalg.norm(v)
    u0 = unit()
    while True:
        u1 = unit()
        ang = math.degrees(math.acos(np.clip(np.dot(u0, u1), -1, 1)))
        if 5.0 < ang < 175.0:                 # 避開 0/180 度的退化幾何
            break
    r0 = (u0 * r_a).astype(np.float64)
    r1 = (u1 * r_b).astype(np.float64)
    # tof 從「短於最小能量轉移」到「夠繞好幾圈」
    a_mid = (r_a + r_b) / 2.0
    t_ref = 2 * math.pi * math.sqrt(a_mid ** 3 / MU)
    tof = float(rng.uniform(0.05, 4.0) * t_ref)
    return r0, r1, tof


if __name__ == "__main__":
    _patch_pykep()
    from pykep import lambert_problem

    rng = np.random.default_rng(20260828)
    N_CASES = int(os.environ.get("XCHECK_CASES", "200"))
    MAX_REVS = 3

    n_cmp = 0
    worst = 0.0
    worst_case = None
    ghosts = []          # 我們有、pykep 沒有 -> 假解（嚴重）
    missing = []         # pykep 有、我們沒有 -> 漏解（少賺）
    count_mismatch = []
    errs = []

    print("=" * 92)
    print("多圈 Lambert 交叉驗證：我們（poliastro izzo）vs ESA pykep")
    print("=" * 92)
    print(f"{N_CASES} 組隨機幾何 x 順行/逆行，max_revs={MAX_REVS}，"
          f"判定同解門檻 {TOL_KMS:g} km/s\n", flush=True)

    for i in range(N_CASES):
        r0, r1, tof = random_case(rng)
        for prograde in (True, False):
            cw = not prograde
            try:
                lp = lambert_problem(r0=list(r0), r1=list(r1), tof=tof,
                                     mu=MU, cw=cw, multi_revs=MAX_REVS)
                pk_v = [np.asarray(v, dtype=np.float64) for v in lp.v0]
            except Exception as e:
                errs.append((i, prograde, type(e).__name__, str(e)[:70]))
                continue

            ours = our_branches(r0, r1, tof, prograde, MAX_REVS)

            # 1) 我們的每條解，pykep 找不找得到
            for tag, v in ours:
                d = min((float(np.linalg.norm(v - w)) for w in pk_v), default=float("inf"))
                n_cmp += 1
                if d > worst:
                    worst, worst_case = d, (i, prograde, tag, tof)
                if d > TOL_KMS:
                    ghosts.append((i, prograde, tag, d, tof))

            # 2) pykep 有而我們沒有
            for w in pk_v:
                d = min((float(np.linalg.norm(w - v)) for _, v in ours), default=float("inf"))
                if d > TOL_KMS:
                    missing.append((i, prograde, d, tof))

            # 3) 數量：pykep 回 2*Nmax+1
            nmax = lp.Nmax
            if len(pk_v) != 2 * nmax + 1:
                count_mismatch.append((i, prograde, len(pk_v), nmax))

        if (i + 1) % 50 == 0:
            print(f"  ...{i+1}/{N_CASES} 組，比對 {n_cmp:,} 條解，"
                  f"目前最大偏差 {worst:.3e} km/s", flush=True)

    print("\n" + "-" * 92)
    print(f"比對解數：{n_cmp:,}")
    print(f"最大偏差：{worst:.3e} km/s"
          + (f"（case {worst_case[0]}, {'順行' if worst_case[1] else '逆行'}, "
             f"M={worst_case[2][0]} lowpath={worst_case[2][1]}, tof={worst_case[3]:,.0f}s）"
             if worst_case else ""))
    print(f"🔴 假解（我們有、pykep 沒有）：{len(ghosts)}")
    print(f"⚠️  漏解（pykep 有、我們沒有）：{len(missing)}")
    print(f"   pykep 自身數量不符 2N+1：{len(count_mismatch)}")
    print(f"   pykep 例外：{len(errs)}")

    for lbl, lst in (("假解", ghosts[:5]), ("漏解", missing[:5])):
        for it in lst:
            print(f"     [{lbl}] case {it[0]} {'順行' if it[1] else '逆行'} "
                  f"偏差 {it[-2]:.3e} tof={it[-1]:,.0f}s")

    print()
    if not ghosts and worst <= TOL_KMS:
        print("✅ 通過：我們算出的每一條分支，pykep 都確認是真解。")
    else:
        print("🔴 未通過：有分支 pykep 對不上——多圈結果不可信。")
    if missing:
        print(f"   註：漏解 {len(missing)} 條代表少賺（沒找到某些合法轉移），不是算錯。")
    print("XCHECK DONE")
