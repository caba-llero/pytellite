from __future__ import annotations

import numpy as np
from plant.quaternion_math import Quaternion
from numpy.linalg import inv

MU_EARTH = 3.986004418e14  # [m^3/s^2]


def skew(v: np.ndarray) -> np.ndarray:
    """Return the 3x3 skew-symmetric matrix (v_x) of a 3-element vector v."""
    return np.array([
        [0, -v[2], v[1]],
        [v[2], 0, -v[0]],
        [-v[1], v[0], 0]
    ])

def two_body_acceleration(r_eci: np.ndarray, mu: float = MU_EARTH) -> np.ndarray:
    r_norm = np.linalg.norm(r_eci)
    if r_norm == 0:
        return np.zeros(3)
    return -mu * r_eci / (r_norm ** 3)


def rk4_step_orbit(r_eci: np.ndarray, v_eci: np.ndarray, dt: float, mu: float = MU_EARTH) -> tuple[np.ndarray, np.ndarray]:
    """
    Integrate orbital state using RK4.
    Inputs:
        r_eci: np.ndarray of shape (3,) - position in ECI frame
        v_eci: np.ndarray of shape (3,) - velocity in ECI frame
        dt: float - time step
        mu: float - gravitational parameter
    Output:
        tuple of (r_next, v_next) - next position and velocity
    """
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


def omega_to_quat_derivative(q: Quaternion, w: np.ndarray) -> Quaternion:
    """Convert angular velocity to quaternion derivative.
    Inputs:
        q: Quaternion
        w: np.ndarray of shape (3,)
    Output:
        dq/dt: Quaternion

    Source: Markley (Eq. 3.20, p.71)
    """
    dqdt = 0.5 * q ** w
    return dqdt

# To do: integrate with matrix exponential instead of RK4 (no normalization needed, more exact)
def integrate_attitude_rk4(q_bi: Quaternion, omega_b: np.ndarray, dt: float) -> Quaternion:
    """
    Integrate attitude using RK4.
    Inputs:
        q_bi: Quaternion - current body-to-inertial attitude
        omega_b: np.ndarray of shape (3,) - body angular velocity
        dt: float - time step
    Output:
        q_next: Quaternion - next attitude
    """
    def f(q_bi: Quaternion) -> Quaternion:
        return omega_to_quat_derivative(q_bi, omega_b)

    k1 = f(q_bi)
    k2 = f(q_bi + 0.5 * dt * k1)
    k3 = f(q_bi + 0.5 * dt * k2)
    k4 = f(q_bi + dt * k3)

    q_next = q_bi + (dt / 6.0) * (k1 + 2 * k2 + 2 * k3 + k4)
    return q_next.n

def eulers_equations(w: np.ndarray, J: np.ndarray, L: np.ndarray) -> np.ndarray:
    """
    Euler's equations for the rigid body dynamics. 
    Inputs:
        w: np.ndarray of shape (3,) - angular velocity
        J: np.ndarray of shape (3,3) - inertia matrix
        L: np.ndarray of shape (3,) - external torque
    Output:
        dw/dt: np.ndarray of shape (3,) - angular acceleration
    """
    return inv(J) @ (L - skew(w) @ J @ w)

# To do: integrate with sympletic 
def integrate_ang_vel_rk4(w: np.ndarray, J: np.ndarray, L: np.ndarray, dt: float) -> np.ndarray:
    """
    Integrate angular velocity using RK4.
    Inputs:
        w: np.ndarray of shape (3,) - current angular velocity 
        J: np.ndarray of shape (3,3) - inertia matrix 
        L: np.ndarray of shape (3,) - external torque vector
        dt: float - time step 

    Output:
        w_next: np.ndarray of shape (3,) - next angular velocity 
    """
    def f(w: np.ndarray) -> np.ndarray:
        return eulers_equations(w, J, L)

    k1 = f(w)
    k2 = f(w + 0.5 * dt * k1)
    k3 = f(w + 0.5 * dt * k2)
    k4 = f(w + dt * k3)
    
    w_next = w + (dt / 6.0) * (k1 + 2 * k2 + 2 * k3 + k4)
    return w_next




