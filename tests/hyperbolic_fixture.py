"""雙曲線 smoke / e2e 共用的內建測試設定。"""

def _hyper_config(maxiter, popsize, revs_ensemble=False):
    """SCENARIOS.md hyperbolic_test：單/雙棒都超標的雙曲線飛越，逼 DE 交違規解測拆棒接手。
    近地點 10,000km（安全），TA=-100° 在漸近線內（arccos(-1/1.5)≈131.8°）。"""
    return {
        "orbit_A": {"SMA": -20000.0, "ECC": 1.5, "INC": 28.0, "RAAN": 50.0, "AOP": 30.0, "TA": -100.0},
        "orbit_B": {"SMA": 6800.0, "ECC": 0.0, "INC": 28.0, "RAAN": 50.0, "AOP": 0.0, "TA": 0.0},
        "rules": {
            "MAX_DV_MPS": 1500.0, "MIN_MANEUVER_INTERVAL_SEC": 100.0, "T_MAX_SEC": 8000.0,
            "k_t": 0.003982, "C_t": 6505.65, "k_v": 0.0011862, "C_v": 9064.3,
        },
        "strategy": {"GRAVITY_DEGREE": 0, "MISS_TOLERANCE_KM": 5.0, "REVS_ENSEMBLE": revs_ensemble},
        "optimization": {
            "MAX_BURNS": [2, 3], "MAXITER": maxiter, "POPSIZE": popsize, "NUM_THREADS": 1,
            "MAX_EARLY_STOP": 40, "TOL": 0.01, "SEED": 42,
        },
    }
