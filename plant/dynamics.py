from __future__ import annotations

import numpy as np
from .quaternion_math import quaternion_multiply, quaternion_normalize

MU_EARTH = 3.986004418e14  # [m^3/s^2]


def two_body_acceleration(r_eci: np.ndarray, mu: float = MU_EARTH) -> np.ndarray:
    r_norm = np.linalg.norm(r_eci)
    if r_norm == 0:
        return np.zeros(3)
    return -mu * r_eci / (r_norm ** 3)


def rk4_step_orbit(r_eci: np.ndarray, v_eci: np.ndarray, dt: float, mu: float = MU_EARTH) -> tuple[np.ndarray, np.ndarray]:
    def f(state: np.ndarray) -> np.ndarray:
        r = state[:3]
        v = state[3:]
        a = two_body_acceleration(r, mu)
        return np.hstack((v, a))

    state = np.hstack((r_eci, v_eci))

    k1 = f(state)
    k2 = f(state + 0.5 * dt * k1)
    k3 = f(state + 0.5 * dt * k2)
    k4 = f(state + dt * k3)

    next_state = state + (dt / 6.0) * (k1 + 2 * k2 + 2 * k3 + k4)
    r_next, v_next = next_state[:3], next_state[3:]
    return r_next, v_next


def omega_to_quat_derivative(q: np.ndarray, w: np.ndarray) -> np.ndarray:
    """Convert angular velocity to quaternion derivative.
    Inputs:
        q: np.ndarray of shape (4,1)
        w: np.ndarray of shape (3,1)
    Output:
        dq: np.ndarray of shape (4,1)
    """
    wx, wy, wz = w
    omega_quat = np.array([wx, wy, wz, 0.0])
    dq = 0.5 * quaternion_multiply(q, omega_quat)
    return dq

def integrate_attitude_rk4(q_bi: np.ndarray, omega_b: np.ndarray, dt: float) -> np.ndarray:
    k1 = omega_to_quat_derivative(q_bi, omega_b)
    k2 = omega_to_quat_derivative(q_bi + 0.5 * dt * k1, omega_b)
    k3 = omega_to_quat_derivative(q_bi + 0.5 * dt * k2, omega_b)
    k4 = omega_to_quat_derivative(q_bi + dt * k3, omega_b)
    q_next = q_bi + (dt / 6.0) * (k1 + 2 * k2 + 2 * k3 + k4)
    return quaternion_normalize(q_next)



