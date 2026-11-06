"""DRL env 用的物理引擎，vendored 自 ODC_GMAT_Planner（見 PROVENANCE.md）。

公開 API：
    get_r0_v0, propagate, orbital_period, EARTH_MU, J2/J3/J4_VAL, RE_VAL  ← propagator
    calculate_score                                                       ← scorer
    to_vnb_frame, compute_dv_mag, check_constraints, reaches_perigee      ← core_math
"""
from physics.propagator import (
    get_r0_v0,
    propagate,
    orbital_period,
    EARTH_MU,
    J2_VAL,
    J3_VAL,
    J4_VAL,
    RE_VAL,
)
from physics.scorer import calculate_score
from physics.core_math import (
    to_vnb_frame,
    compute_dv_mag,
    check_constraints,
    reaches_perigee,
)

__all__ = [
    "get_r0_v0",
    "propagate",
    "orbital_period",
    "EARTH_MU",
    "J2_VAL",
    "J3_VAL",
    "J4_VAL",
    "RE_VAL",
    "calculate_score",
    "to_vnb_frame",
    "compute_dv_mag",
    "check_constraints",
    "reaches_perigee",
]
