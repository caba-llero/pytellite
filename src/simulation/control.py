import numpy as np
from numba import njit
from ..math import quaternion as qm
import os
from ..math import quaternion as qm

# Use the same conditional Numba import pattern as other modules so that
# setting DISABLE_NUMBA=1 (used locally to speed up dev) disables JIT here too.
def _identity_decorator(func=None, **kwargs):
    if func is None:
        return lambda f: f
    return func
if os.getenv("DISABLE_NUMBA", "0") == "1":
    njit = _identity_decorator  # type: ignore[assignment]
else:
    try:
        from numba import njit  # type: ignore
    except Exception:
        njit = _identity_decorator  # type: ignore[assignment]


@njit
def control_laws(w: np.ndarray, q: np.ndarray, qc: np.ndarray, control_type: int, kp: float, kd: float):
    if control_type == 0:
        return np.zeros(3)
    elif control_type == 1:
        return control_law_tracking(w, q, qc, kp, kd)
    elif control_type == 2:
        return control_law_nonlinear_tracking(w, q, qc, kp, kd)
    # Fallback to safe default if control_type is unknown
    return np.zeros(3)

@njit
def control_law_tracking(w: np.ndarray, q: np.ndarray, qc: np.ndarray, kp: float, kd: float):
    dq = qm.quat_multiply_cross(q, qm.quat_inv(qc))
    dq = qm.quat_normalize(dq)
    L = - kp * np.sign(dq[3]) * dq[0:3] - kd * w
    return L

@njit
def control_law_nonlinear_tracking(w: np.ndarray, q: np.ndarray, qc: np.ndarray, kp: float, kd: float):
    dq = qm.quat_multiply_cross(q, qm.quat_inv(qc))
    dq = qm.quat_normalize(dq)
    dq_vec = dq[0:3]
    L = - kp * np.sign(dq[3]) * dq_vec - kd * (1 + np.dot(dq_vec, dq_vec)) * w
    return L

