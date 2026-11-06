"""把本 repo 的 numba Izzo 跟 poliastro 的 izzo 逐案比對（離線驗證，非 CI）。

poliastro 裝不進本 repo 的 venv，所以分兩段跑：
    # 1) 本 repo：產生隨機案例 + 我們的解
    uv run python tools/compare_lambert_poliastro.py gen /tmp/lam_cases.npz
    # 2) Planner 的 venv（有 poliastro 0.17）：讀案例、用 poliastro 解、比對
    cd ~/ODC_GMAT_Planner && uv run python ~/ODC_GMAT_DRL/tools/compare_lambert_poliastro.py cmp /tmp/lam_cases.npz
"""
import sys

import numpy as np

MU = 398600.4418


def _rand_r(rng):
    rmag = rng.uniform(6700, 9000)
    d = rng.normal(size=3)
    return rmag * d / np.linalg.norm(d)


def gen(path, n=1000):
    sys.path.insert(0, __file__.rsplit("/tools/", 1)[0])
    from physics.lambert import izzo

    rng = np.random.default_rng(7)
    rows = []
    for _ in range(n):
        r1, r2 = _rand_r(rng), _rand_r(rng)
        M = int(rng.integers(0, 3))
        tof = rng.uniform(600, 4000) + M * 6000.0
        prograde = bool(rng.integers(0, 2))
        lowpath = bool(rng.integers(0, 2))
        ok, v1, v2 = izzo(MU, r1, r2, tof, M, prograde, lowpath, 35, 1e-10)
        rows.append((r1, r2, tof, M, prograde, lowpath, ok, v1, v2))
    np.savez(path,
             r1=np.array([r[0] for r in rows]), r2=np.array([r[1] for r in rows]),
             tof=np.array([r[2] for r in rows]), M=np.array([r[3] for r in rows]),
             prograde=np.array([r[4] for r in rows]), lowpath=np.array([r[5] for r in rows]),
             ok=np.array([r[6] for r in rows]), v1=np.array([r[7] for r in rows]),
             v2=np.array([r[8] for r in rows]))
    print(f"wrote {n} cases to {path}")


def cmp(path):
    from poliastro.core.iod import izzo as pizzo

    d = np.load(path)
    n = len(d["tof"])
    both = only_ours = only_theirs = neither = 0
    max_err = 0.0
    worst = None
    for i in range(n):
        try:
            v1, v2 = pizzo(MU, d["r1"][i], d["r2"][i], float(d["tof"][i]), int(d["M"][i]),
                           bool(d["prograde"][i]), bool(d["lowpath"][i]), 35, 1e-10)
            theirs = True
        except Exception:
            theirs = False
        ours = bool(d["ok"][i])
        if ours and theirs:
            both += 1
            err = max(np.linalg.norm(v1 - d["v1"][i]), np.linalg.norm(v2 - d["v2"][i]))
            if err > max_err:
                max_err, worst = err, i
        elif ours:
            only_ours += 1
        elif theirs:
            only_theirs += 1
        else:
            neither += 1
    print(f"cases={n} both_ok={both} only_ours={only_ours} only_poliastro={only_theirs} neither={neither}")
    print(f"max |dv| difference where both solved: {max_err:.3e} km/s (case {worst})")


if __name__ == "__main__":
    {"gen": gen, "cmp": cmp}[sys.argv[1]](sys.argv[2])
