import numpy as np
from typing import Tuple
from astropy import units as u
from poliastro.bodies import Earth
from poliastro.twobody import Orbit
from src.core_math import propagate_dop853

from numba import njit

# J2/J3/J4 zonal harmonic 係數：直接從 GMAT 用的同一份 JGM2.cof 重力場檔案反算
# (RECOEF 2/3/4 0 那三個正規化係數乘上 sqrt(2n+1) 去正規化，再取負號)，確保
# Python 端跟 GMAT 端用同一組數字。J3/J4 是 2026-08-14 新增，公式推導/交叉驗證
# 過程見 core_math.fast_dynamics 的說明。
J2_VAL = 1.08262668e-3
J3_VAL = -2.5323078e-6
J4_VAL = -1.62042999e-6
RE_VAL = 6378.137

def get_r0_v0(sma: float, ecc: float, inc: float, raan: float, aop: float, ta: float):
    initial_orbit = Orbit.from_classical(
        attractor=Earth,
        a=u.Quantity(float(sma), u.km),
        ecc=u.Quantity(float(ecc), u.one),
        inc=u.Quantity(float(inc), u.deg),
        raan=u.Quantity(float(raan), u.deg),
        argp=u.Quantity(float(aop), u.deg),
        nu=u.Quantity(float(ta), u.deg)
    )
    
    r0 = initial_orbit.r.to_value(u.km).astype(np.float64)
    v0 = initial_orbit.v.to_value(u.km / u.s).astype(np.float64)

    return r0, v0   

@njit(fastmath=True)
def propagate(
    k: float, r0: np.ndarray, v0: np.ndarray, tof: float, gravity_degree: int = 2
) -> Tuple[np.ndarray, np.ndarray]:
    """
    改用純 Numba DOP853 (8 階 Dormand-Prince) 自適應步長引擎的軌道傳播器
    (2026-08-14 從固定 60 秒的古典 RK4 先換成 RK45 自適應、再換成這個更高階的
    版本——同樣的自適應步長概念，換一組更高階、對這種平滑軌道問題更有效率的
    係數表，見 core_math.propagate_dop853 的說明)。
    gravity_degree: 0=純點質量, 2=J2, 3=J2+J3, 4=J2+J3+J4。
    """
    active_j2 = J2_VAL if gravity_degree >= 2 else 0.0
    active_j3 = J3_VAL if gravity_degree >= 3 else 0.0
    active_j4 = J4_VAL if gravity_degree >= 4 else 0.0

    # 初始步長猜測 (自適應積分器會自己調整，這個值只影響最開頭幾步要花多少次
    # 嘗試才會收斂到合適的步長)。
    dt0 = 60.0

    # 直接呼叫 core_math 裡面的純數學迴圈
    r_final, v_final = propagate_dop853(r0, v0, tof, dt0, k, active_j2, active_j3, active_j4, RE_VAL)

    return r_final, v_final

# ==========================================
# 測試區塊 
# ==========================================
if __name__ == "__main__":
    import time

    mu = Earth.k.to_value((u.km ** 3) / (u.s ** 2)) # type: ignore
    
    params = {
        "sma": 7000.0, "ecc": 0.0, "inc": 30.0, 
        "raan": 45.0, "aop": 0.0, "ta": 120.0
    }
    
    print("=== 初始化高階軌道模型 ===")
    r0, v0 = get_r0_v0(**params)
    tof = 3600.0
    
    print("\n=== 啟動傳播器測試 (JIT + SciPy DOP853) ===")
    
    # 暖機 (讓 Numba 先編譯一次)
    propagate(mu, r0, v0, tof, gravity_degree=4)

    start_time = time.perf_counter()
    for _ in range(100):
        r_new, v_new = propagate(mu, r0, v0, tof, gravity_degree=4)
    end_time = time.perf_counter()

    print(f"[t={tof}s] 未來位置 (km): {np.round(r_new, 2)}")
    print(f"[t={tof}s] 未來速度 (km/s): {np.round(v_new, 2)}")
    print(f"✅ 100 次含 J2+J3+J4 運算耗時: {(end_time - start_time) * 1000:.2f} 毫秒")