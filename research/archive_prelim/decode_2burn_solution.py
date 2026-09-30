import sys, json, math
sys.path.insert(0, "/Users/corn/Documents/Program/ODC_Program")
import numpy as np
from src.optimizer import MissionOptimizer
from src.core_math import propagate_dop853, fast_norm, check_constraints
from poliastro.core.iod import izzo

config = json.load(open("/Users/corn/Documents/Program/ODC_Program/configs/weird_test.json"))
cfg = dict(config); cfg["optimization"] = dict(config["optimization"])
cfg["optimization"]["MAX_BURNS"] = [2]
opt = MissionOptimizer(cfg)
mu, dt = opt.MU, 60.0
j2, j3, j4, re = opt.J2_VAL, opt.J3_VAL, opt.J4_VAL, opt.RE_VAL

x = np.array([1.71462112e+06, 6.34010657e-01, 6.65026423e-01, 9.52937930e-01,
              0.00000000e+00, 1.11538971e-02, 3.50000000e+00, 1.76314491e+00, 8.15067487e-01])

t_wait = x[0]
dv_r, dv_theta, dv_phi, coast_frac = x[1], x[2], x[3], x[4]
final_leg_frac = x[5]

r_cur, v_cur = propagate_dop853(opt.B_r0, opt.B_v0, t_wait, dt, mu, j2, j3, j4, re)
v_before_burn1 = fast_norm(v_cur)
print(f"燃燒1發生於 t_wait={t_wait:.0f}s ({t_wait/86400:.2f}天)，此時 B 速度={v_before_burn1:.3f}km/s，"
      f"半徑={fast_norm(r_cur):.1f}km")

sin_theta = math.sin(dv_theta)
dv_vec1 = np.array([dv_r*sin_theta*math.cos(dv_phi), dv_r*sin_theta*math.sin(dv_phi), dv_r*math.cos(dv_theta)])
v_after_burn1 = v_cur + dv_vec1
print(f"燃燒1 大小={fast_norm(dv_vec1)*1000:.1f}m/s")

# 角度變化 (燒之前 vs 燒之後的方向夾角，粗略代表這棒改了多少軌道平面/方向)
cos_angle = np.dot(v_cur, v_after_burn1) / (fast_norm(v_cur)*fast_norm(v_after_burn1))
angle_deg = math.degrees(math.acos(np.clip(cos_angle, -1, 1)))
print(f"燃燒1 前後速度方向夾角: {angle_deg:.1f}度")

max_coast = opt.T_max - t_wait - opt.MIN_COAST_TIME
t_coast = opt.MIN_COAST_TIME + coast_frac*(max_coast - opt.MIN_COAST_TIME)
r_cur2, v_cur2 = propagate_dop853(r_cur, v_after_burn1, t_coast, dt, mu, j2, j3, j4, re)
current_time = t_wait + t_coast
print(f"滑行 {t_coast:.0f}s 到 t={current_time:.0f}s ({current_time/86400:.2f}天)，此時速度={fast_norm(v_cur2):.3f}km/s")

max_final = opt.T_max - current_time
t_final_leg = opt.MIN_COAST_TIME + final_leg_frac*(max_final - opt.MIN_COAST_TIME)
intercept_time = current_time + t_final_leg
r_a_target, _ = propagate_dop853(opt.A_r0, opt.A_v0, intercept_time, dt, mu, j2, j3, j4, re)
offset_r, offset_theta, offset_phi = x[6], x[7], x[8]
sin_ot = math.sin(offset_theta)
offset_vec = np.array([offset_r*sin_ot*math.cos(offset_phi), offset_r*sin_ot*math.sin(offset_phi), offset_r*math.cos(offset_theta)])
r_aim = r_a_target + offset_vec

best_dv2, v2 = np.inf, None
for prograde in (True, False):
    try:
        v1_req, _ = izzo(mu, r_cur2, r_aim, t_final_leg, M=0, prograde=prograde, lowpath=True, numiter=35, rtol=1e-8)
        d = fast_norm(v1_req - v_cur2)
        if d < best_dv2: best_dv2, v2 = d, v1_req
    except Exception: pass
print(f"燃燒2 (攔截) 發生於 t={current_time:.0f}s, 目標抵達時間={intercept_time:.0f}s ({intercept_time/86400:.2f}天)")
print(f"燃燒2 大小={best_dv2*1000:.1f}m/s")

cos_angle2 = np.dot(v_cur2, v2) / (fast_norm(v_cur2)*fast_norm(v2))
angle_deg2 = math.degrees(math.acos(np.clip(cos_angle2, -1, 1)))
print(f"燃燒2 前後速度方向夾角: {angle_deg2:.1f}度")

total = fast_norm(dv_vec1)*1000 + best_dv2*1000
print(f"\n總 Dv = {total:.1f}m/s")

# 對照：純單棒(直接在 t_wait 那個時間點做一次攔截 Lambert)要花多少
r_b0, v_b0 = propagate_dop853(opt.B_r0, opt.B_v0, t_wait, dt, mu, j2, j3, j4, re)
best_single = np.inf
for prograde in (True, False):
    try:
        v1s, _ = izzo(mu, r_b0, r_aim, t_coast+t_final_leg, M=0, prograde=prograde, lowpath=True, numiter=35, rtol=1e-8)
        d = fast_norm(v1s - v_b0)
        if d < best_single: best_single = d
    except Exception: pass
print(f"對照：如果同一個時間點/同一個瞄準點只用單棒直接打，需要 {best_single*1000:.1f}m/s")
