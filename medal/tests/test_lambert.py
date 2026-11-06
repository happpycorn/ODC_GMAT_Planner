"""Lambert 求解器驗證：解出的 v1 用純二體 DOP853 實際飛 tof 秒，必須抵達 r2。"""
import numpy as np
import pytest

from physics import EARTH_MU, get_r0_v0, orbital_period, propagate
from physics.lambert import izzo, lambert_min_dv


def _fly(r1, v1, tof):
    r, v = propagate(EARTH_MU, r1, v1, tof, 0)
    return r, v


def test_single_rev_hits_target_random():
    rng = np.random.default_rng(42)
    n_ok = 0
    for _ in range(300):
        o1 = dict(sma=rng.uniform(6700, 9000), ecc=rng.uniform(0, 0.1), inc=rng.uniform(0, 180),
                  raan=rng.uniform(0, 360), aop=rng.uniform(0, 360), ta=rng.uniform(0, 360))
        o2 = dict(sma=rng.uniform(6700, 9000), ecc=rng.uniform(0, 0.1), inc=rng.uniform(0, 180),
                  raan=rng.uniform(0, 360), aop=rng.uniform(0, 360), ta=rng.uniform(0, 360))
        r1, _ = get_r0_v0(**o1)
        r2, _ = get_r0_v0(**o2)
        tof = rng.uniform(300, 5000)
        for prograde in (True, False):
            ok, v1, v2 = izzo(EARTH_MU, r1, r2, tof, 0, prograde, True, 35, 1e-10)
            if not ok:
                continue
            rf, vf = _fly(r1, v1, tof)
            assert np.linalg.norm(rf - r2) < 1e-3, (o1, o2, tof, prograde)   # < 1 m
            assert np.linalg.norm(vf - v2) < 1e-6
            n_ok += 1
    assert n_ok > 550


@pytest.mark.parametrize("M", [1, 2, 3])
def test_multi_rev_hits_target(M):
    rng = np.random.default_rng(M)
    n_ok = 0
    for _ in range(100):
        r1, _ = get_r0_v0(7000.0, 0.0, 30.0, 0.0, 0.0, rng.uniform(0, 360))
        r2, _ = get_r0_v0(7300.0, 0.01, 31.0, 1.0, 0.0, rng.uniform(0, 360))
        T = orbital_period(7150.0)
        tof = rng.uniform((M + 0.2) * T, (M + 1.5) * T)
        for lowpath in (True, False):
            ok, v1, _ = izzo(EARTH_MU, r1, r2, tof, M, True, lowpath, 35, 1e-10)
            if not ok:
                continue
            rf, _ = _fly(r1, v1, tof)
            # 多圈時 T(x) 在最小值附近很平，x 的收斂容差被放大成 ~0.1 mm/s 級的速度誤差，
            # 飛 M+1 圈後變成數公尺——比捕獲半徑小三個數量級，實務無影響。
            assert np.linalg.norm(rf - r2) < 0.01 * M, (M, tof, lowpath)
            n_ok += 1
    assert n_ok > 100


def test_infeasible_multirev_reports_not_ok():
    r1, _ = get_r0_v0(7000.0, 0.0, 0.0, 0.0, 0.0, 0.0)
    r2, _ = get_r0_v0(7000.0, 0.0, 0.0, 0.0, 0.0, 90.0)
    ok, _, _ = izzo(EARTH_MU, r1, r2, 600.0, 3, True, True, 35, 1e-10)   # 10 分鐘不可能繞 3 圈
    assert not ok


def test_hohmann_like_dv():
    """同平面 7000 -> 7500 km 半圈轉移（避開 180° 共線，取 179°），Δv 應接近 Hohmann 第一棒。"""
    mu = EARTH_MU
    r1, v1c = get_r0_v0(7000.0, 0.0, 0.0, 0.0, 0.0, 0.0)
    r2, _ = get_r0_v0(7500.0, 0.0, 0.0, 0.0, 0.0, 179.0)
    a_t = (7000.0 + 7500.0) / 2
    tof = np.pi * np.sqrt(a_t ** 3 / mu) * 179.0 / 180.0
    dv, v1, _ = lambert_min_dv(mu, r1, v1c, r2, tof, 0)
    dv_hoh = np.sqrt(mu / 7000.0) * (np.sqrt(2 * 7500.0 / (7000.0 + 7500.0)) - 1.0)
    assert abs(dv - dv_hoh) < 0.02          # 20 m/s 內（179° 與精確 180° 的差）
