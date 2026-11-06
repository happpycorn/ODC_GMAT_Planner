"""窗口內連續事件偵測（physics/coast.py）與座標系轉換（physics/frames.py）。"""
import numpy as np

from physics import EARTH_MU, RE_VAL, get_r0_v0, propagate
from physics.coast import EV_CAPTURE, EV_CRASH_P, EV_NONE, closest_approach, coast_pair
from physics.frames import rsw_basis, rv2coe, vnb_basis
from physics.core_math import to_vnb_frame


def _dense_min_dist(rp, vp, re, ve, dt, step=1.0):
    best = np.linalg.norm(rp - re)
    t = 0.0
    while t < dt - 1e-9:
        h = min(step, dt - t)
        rp, vp = propagate(EARTH_MU, rp, vp, h, 2)
        re, ve = propagate(EARTH_MU, re, ve, h, 2)
        best = min(best, np.linalg.norm(rp - re))
        t += h
    return best


def test_mid_window_flyby_is_captured():
    """兩船在窗口中間（~150 s）以 1 km/s 相對速度穿過彼此，端點距離都遠大於 5 km。"""
    rp, vp = get_r0_v0(7000.0, 0.0, 0.0, 0.0, 0.0, 0.0)
    re = rp + np.array([0.0, 0.0, 150.0])        # 軌道面上方 150 km
    ve = vp + np.array([0.0, 0.0, -1.0])         # 以 1 km/s 往下掃過軌道面
    d_end0 = np.linalg.norm(rp - re)
    out = coast_pair(rp, vp, re, ve, 300.0, 60.0, EARTH_MU, 2, 5.0, RE_VAL)
    rp1, vp1, re1, ve1, t_ev, ev, dmin, tmin = out
    assert d_end0 > 100.0
    dense = _dense_min_dist(rp, vp, re, ve, 300.0)
    assert dense < 5.0, "測試構造錯誤：密集取樣也沒進捕獲球"
    assert ev == EV_CAPTURE
    assert 0.0 < t_ev < 300.0
    assert np.linalg.norm(rp1 - re1) <= 5.0 + 1e-3


def test_high_speed_head_on_pass_is_captured():
    """逆行交會（相對速度 ~15 km/s）：一個取樣間隔就飛過數十公里，捕獲球可能落在兩個取樣點之間。

    2026-09-15 對打評測抓到：wild 家族有「最近距離 0.0 km 卻判超時」的局——舊版只在取樣點
    檢查是否 <= 半徑，最小值精修後找到的真正最近點沒回頭補判捕獲。
    """
    rp, vp = get_r0_v0(7000.0, 0.0, 0.0, 0.0, 0.0, 0.0)
    re_, ve_ = get_r0_v0(7000.0, 0.0, 180.0, 0.0, 0.0, 0.0)   # 同軌道面逆行，同位置
    # 把 evader 往回推 150 秒（沿自己的逆行軌道）：從 pursuer 正前方迎面而來
    re0, ve0 = get_r0_v0(7000.0, 0.0, 180.0, 0.0, 0.0, -150.0 / 5828.5 * 360.0)
    rp0, vp0 = get_r0_v0(7000.0, 0.0, 0.0, 0.0, 0.0, -150.0 / 5828.5 * 360.0)
    re0 = re0 + np.array([0.0, 0.0, 1.0])                         # 1 km 平面外偏移
    dense = _dense_min_dist(rp0, vp0, re0, ve0, 300.0, step=0.05)
    assert dense < 5.0
    *_, t_ev, ev, dmin, _ = coast_pair(rp0, vp0, re0, ve0, 300.0, 60.0, EARTH_MU, 0, 5.0, RE_VAL)
    assert ev == EV_CAPTURE, (dense, dmin)
    assert 100.0 < t_ev < 200.0


def test_min_distance_matches_dense_sampling():
    rng = np.random.default_rng(3)
    for _ in range(10):
        rp, vp = get_r0_v0(7000.0, 0.001, 20.0, 10.0, 0.0, rng.uniform(0, 360))
        re = rp + rng.normal(size=3) * 30.0
        ve = vp + rng.normal(size=3) * 0.05
        *_, ev, dmin, _ = coast_pair(rp, vp, re, ve, 600.0, 60.0, EARTH_MU, 2, -1.0, -1.0)
        assert ev == EV_NONE
        dense = _dense_min_dist(rp, vp, re, ve, 600.0, step=1.0)
        assert dmin <= dense + 1e-3            # 連續最小值不會比 1 秒取樣大
        assert dense - dmin < 0.05             # 且相差 < 50 m（1 秒取樣本身的離散誤差）


def test_mid_window_reentry_detected():
    """近地點掉到 60 km 高度的橢圓：端點都在 300 km 以上，但途中穿過 100 km 再入線。"""
    rp_alt, ra_alt = 60.0, 900.0
    a = RE_VAL + (rp_alt + ra_alt) / 2
    e = (ra_alt - rp_alt) / (2 * a)
    r, v = get_r0_v0(a, e, 0.0, 0.0, 0.0, -40.0)          # 近地點前 40°
    re, ve = get_r0_v0(8000.0, 0.0, 0.0, 0.0, 0.0, 90.0)
    assert np.linalg.norm(r) - RE_VAL > 90.0
    *_, t_ev, ev, _, _ = coast_pair(r, v, re, ve, 1500.0, 60.0, EARTH_MU, 2, 5.0, RE_VAL + 100.0)
    assert ev == EV_CRASH_P
    assert 0.0 < t_ev < 1500.0


def test_closest_approach_coast():
    rp, vp = get_r0_v0(7000.0, 0.0, 0.0, 0.0, 0.0, 0.0)
    re, ve = get_r0_v0(7000.0, 0.0, 0.0, 0.0, 0.0, 1.0)
    d, t, rel = closest_approach(rp, vp, re, ve, 3000.0, 120.0, EARTH_MU, 0)
    # 同圓軌道相位差固定 → 距離恆定，最近距離 = 初始距離
    assert abs(d - np.linalg.norm(rp - re)) < 1e-3
    assert abs(np.linalg.norm(rel) - d) < 1e-6


def test_frames_orthonormal_and_vnb_consistent():
    rng = np.random.default_rng(0)
    for _ in range(20):
        r, v = get_r0_v0(rng.uniform(6800, 9000), rng.uniform(0, 0.3), rng.uniform(0, 180),
                         rng.uniform(0, 360), rng.uniform(0, 360), rng.uniform(0, 360))
        for B in (rsw_basis(r, v), vnb_basis(r, v)):
            assert np.allclose(B @ B.T, np.eye(3), atol=1e-12)
            assert abs(np.linalg.det(B) - 1.0) < 1e-12
        dv = rng.normal(size=3)
        assert np.allclose(vnb_basis(r, v) @ dv, to_vnb_frame(r, v, dv), atol=1e-12)
        R = rsw_basis(r, v)
        assert R[0] @ r > 0 and R[1] @ v > 0          # R 朝外、S 與速度同向


def test_rv2coe_roundtrip():
    rng = np.random.default_rng(1)
    for _ in range(50):
        o = dict(sma=rng.uniform(6800, 20000), ecc=rng.uniform(0.001, 0.5), inc=rng.uniform(1, 179),
                 raan=rng.uniform(0, 360), aop=rng.uniform(0, 360), ta=rng.uniform(0, 360))
        if o["sma"] * (1 - o["ecc"]) < 6600:
            continue
        r, v = get_r0_v0(**o)
        c = rv2coe(r, v)
        r2, v2 = get_r0_v0(**c)
        assert np.allclose(r, r2, atol=1e-6) and np.allclose(v, v2, atol=1e-9)
    # 退化：圓 + 赤道
    r, v = get_r0_v0(7000.0, 0.0, 0.0, 0.0, 0.0, 33.0)
    r2, v2 = get_r0_v0(**rv2coe(r, v))
    assert np.allclose(r, r2, atol=1e-6) and np.allclose(v, v2, atol=1e-9)
