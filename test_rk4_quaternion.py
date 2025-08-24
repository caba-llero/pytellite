import numpy as np

def omega_matrix(w):
    # Build quaternion Omega matrix for angular velocity w = [wx, wy, wz]
    wx, wy, wz = w
    return np.array([
        [0, -wx, -wy, -wz],
        [wx, 0, wz, -wy],
        [wy, -wz, 0, wx],
        [wz, wy, -wx, 0]
    ])

def dqdt(q, w):
    return 0.5 * omega_matrix(w) @ q

def rk4_step(q, w, dt):
    k1 = dqdt(q, w)
    k2 = dqdt(q + 0.5*dt*k1, w)
    k3 = dqdt(q + 0.5*dt*k2, w)
    k4 = dqdt(q + dt*k3, w)
    return q + dt/6 * (k1 + 2*k2 + 2*k3 + k4)

# Initial unit quaternion (identity rotation)
q = np.array([1.0, 0.0, 0.0, 0.0])
w = np.array([0.0, 0.0, 1.0])  # constant rotation about z-axis
dt = 0.1

for step in range(100):
    q = rk4_step(q, w, dt)
    norm = np.linalg.norm(q)
    print(step, norm)
