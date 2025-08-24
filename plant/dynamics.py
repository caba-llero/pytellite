from __future__ import annotations

import numpy as np
try:
    from plant.quaternion_math import Quaternion
except ImportError:
    # Fallback for direct import (when not used as part of plant package)
    from quaternion_math import Quaternion
from numpy.linalg import inv, solve

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
        a_eci: np.ndarray of shape (3,) - acceleration in ECI frame
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
    a_next = two_body_acceleration(r_next, mu)
    return r_next, v_next, a_next


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

def integrate_attitude_quat_mult(q_bi: Quaternion, omega_b: np.ndarray, dt: float) -> Quaternion:
    """
    Integrate attitude using quaternion multiplication.
    Inputs:
        q_bi: Quaternion - current body-to-inertial attitude
        omega_b: np.ndarray of shape (3,) - body angular velocity
        dt: float - time step

    Output:
        q_next: Quaternion - next attitude
    """

    theta = np.linalg.norm(omega_b) * dt
    if theta == 0:
        return q_bi
    
    axis = omega_b / np.linalg.norm(omega_b)
    s2 = np.sin(theta / 2)
    c2 = np.cos(theta / 2)
    dq = Quaternion(axis[0] * s2, axis[1] * s2, axis[2] * s2, c2)
    q_next = q_bi * dq
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

def integrate_ang_vel_symplectic(w: np.ndarray, J: np.ndarray, L: np.ndarray, dt: float) -> np.ndarray:
    """
    Integrate angular velocity using Strang splitting.
    Separates the angular velocity update into three parts:
    - Update the angular velocity using the external torque (half kick)
    - Update the angular velocity using the inertia matrix (drift)
    - Update the angular velocity using the external torque (half kick)

    The advantage of this method is that it preserves the angular momentum if the torque is zero.
    Check my notes for more details: "Integration - Symplectic vs RK4. Caley transform"

    Inputs:
        w: np.ndarray of shape (3,) - current angular velocity 
        J: np.ndarray of shape (3,3) - inertia matrix 
        L: np.ndarray of shape (3,) - external torque vector
        dt: float - time step 
    Output:
        w_next: np.ndarray of shape (3,) - next angular velocity 
    """

    w_0 = w.copy()
    h_0 = J @ w_0
    
    A = dt / 2 * skew(inv(J) @ h_0)
    Q = solve(np.eye(3) - A, np.eye(3) + A)

    h_1 = h_0 + 0.5 * dt * L # First half kick
    h_2 = Q @ h_1 # Drift (Cayley rotation)
    h_3 = h_2 + 0.5 * dt * L # Second half kick

    w_out = solve(J, h_3)
    return w_out


def orbit_to_inertial(r_i: np.ndarray, v_i: np.ndarray, a_i: np.ndarray) -> np.ndarray:
    """
    Compute the rotation matrix from inertial frame F_i to orbit frame F_o and the angular velocity of the orbit frame F_o with respect to the inertial frame F_i, in F_o frame.
    Inputs:
        r_i: np.ndarray of shape (3,) - position in inertial frame F_i
        v_i: np.ndarray of shape (3,) - velocity in inertial frame F_i
        a_i: np.ndarray of shape (3,) - acceleration in inertial frame F_i
    Output:
        R_io: np.ndarray of shape (3,3) - rotation matrix from inertial frame F_i to orbit frame F_o
        w_oi: np.ndarray of shape (3,) - angular velocity of the orbit frame F_o with respect to the inertial frame F_i, in F_o frame
    """
    rxv = np.cross(r_i, v_i)
    rxv_n = np.linalg.norm(rxv)
    r_n = np.linalg.norm(r_i)

    z_o = -r_i / r_n
    y_o = - rxv / rxv_n
    x_o = np.cross(y_o, z_o)

    w_x = 0
    w_y = - rxv_n / r_n**2
    w_z = r_n * np.dot(rxv, a_i) / rxv_n**2

    R_io = np.array([x_o, y_o, z_o])
    w_oi = np.array([w_x, w_y, w_z])

    return R_io, w_oi

def omega_orbit_to_inertial(r_i: np.ndarray, v_i: np.ndarray) -> np.ndarray:
    """
    Compute the angular velocity of the orbit frame F_o with respect to the inertial frame F_i, in F_o frame.
    """
    

    

