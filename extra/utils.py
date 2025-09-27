import numpy as np
from numba import njit

I3 = np.eye(3)

@njit(cache=True, fastmath=True)
def Phi(dt, w_h, I3, simple=False, min_e=1e-7): # returns state transition matrix (discrete-time), i.e. Phi = Exp(F dt)
    e = np.linalg.norm(w_h)
    if e < min_e: # to avoid numerical instabilities as we divide by e
        simple=True

    p = e * dt
    a = skew(w_h)
    sp = np.sin(p)
    cp = np.cos(p)

    if simple:
        Phi11 = I3 - a*dt
        Phi12 = -I3 * dt
    else:
        Phi11 = I3 - a/e * sp + a@a / e**2 * (1-cp)
        Phi12 = -I3 * dt - a@a / e**3 * (p - sp) + a/e**2 * (1 - cp)

    Phi21 = np.zeros((3,3))
    Phi22 = np.eye(3)

    phi = np.empty((6, 6))
    phi[:3, :3] = Phi11
    phi[:3, 3:] = Phi12
    phi[3:, :3] = Phi21
    phi[3:, 3:] = Phi22
    
    return phi

@njit(cache=True, fastmath=True)
def skew(a): # returns skew-symmetric matrix of column vector x
    a = a.flatten()
    a_x = np.array([[0, -a[2], a[1]],
                    [a[2], 0, -a[0]],
                    [-a[1], a[0], 0] ])
    return a_x

@njit(cache=True, fastmath=True)
def Q(sigma_v, sigma_u, dt, I3): # Discrete time noise covariance matrix (Eq. 6.93)
    Q11 = (sigma_v**2 * dt + sigma_u**2 * dt**3 / 3) * I3
    Q12 = - sigma_u**2 * dt**2 * I3 / 2
    Q22 = sigma_u**2 * dt * I3
    
    q = np.empty((6, 6))
    q[:3, :3] = Q11
    q[:3, 3:] = Q12
    q[3:, :3] = Q12
    q[3:, 3:] = Q22
    return q

@njit(cache=True, fastmath=True)
def K(P, H, R): # Kalman gain
    S = H @ P @ H.T + R
    K = P @ H.T @ np.linalg.inv(S)
    K_Z = K[:3, :] # Z part of the gain
    K_B = K[3:, :] # B part of the gain
    return K, K_Z, K_B

@njit(cache=True, fastmath=True)
def P_meas(K, H, P, R, Joseph = True): # returns the update covariance matrix, after measurement
    KH = K @ H
    IKH = np.eye(6) - KH

    if Joseph: 
        return IKH @ P @ IKH.T + K @ R @ K.T
    else:
        return IKH @ P

@njit(cache=True, fastmath=True)
def P_prop(P, Phi, Q): # returns the update of the covariance matrix, after propagation
    return Phi @ P @ Phi.T + Q


def measurement_indices(t_max, dt, measurement_freq): # returns the indices of t at which we trigger a measurement event
    n_steps = int(t_max / dt)
    expected_times = np.arange(0, t_max, 1/measurement_freq)
    indices = np.ceil(expected_times / dt).astype(int)  # Convert expected times to indices (round up to ensure >= condition)
    indices = indices[indices < n_steps]  # Filter out indices beyond array bounds
    return set(indices)  

@njit(cache=True, fastmath=True)
def quat_mul(q1, q2):     # Quaternion product q1 ⊗ q2
    x1,y1,z1,w1 = q1
    x2,y2,z2,w2 = q2
    x = w1*x2 + x1*w2 + y1*z2 - z1*y2
    y = w1*y2 - x1*z2 + y1*w2 + z1*x2
    z = w1*z2 + x1*y2 - y1*x2 + z1*w2
    w = w1*w2 - x1*x2 - y1*y2 - z1*z2
    return np.array([x,y,z,w])

@njit(cache=True, fastmath=True)
def quat_propagate(q, w, dt, p_min = 1e-7): 
    # propagates initial quaternion q thru angular vel w and delta time dt
    # done with q <-- dq ⊗ q
    dz = w*dt
    p = np.linalg.norm(dz)
    if p < p_min: # return the same quaternion to avoid numerical instabilities
        return q
    else:
        e = dz / p
        
        # Create dq array manually
        dq = np.empty(4)
        dq[:3] = e * np.sin(p / 2)
        dq[3] = np.cos(p / 2)
        
        q = quat_mul(dq, q)
        return q


@njit(cache=True, fastmath=True)
def Xi(q):
    return np.array([ [q[3], -q[2], q[1]],
                      [q[2], q[3], -q[0]],
                      [-q[1], q[0], q[3]],
                      [-q[0], -q[1], -q[2]]  
                         ])


@njit(cache=True, fastmath=True)
def startracker_meas(q_t, q_h, sigma, n):
    Z_n = np.random.standard_normal(n).reshape(-1,1) * sigma
    q_m = q_t.reshape(-1,1) + 0.5 * Xi(q_t) @ Z_n # small angle approximation of q_m = q_n ⊗ q_t
    q_m = q_m.flatten()
    dq_m = quat_mul(q_m / np.linalg.norm(q_m), quat_inv(q_h))
    dZ_m = quat_to_rotvec(dq_m)
    return dZ_m

@njit(cache=True, fastmath=True)
def quat_inv(q):
    return np.array([-q[0], -q[1], -q[2], q[3]])

@njit(cache=True, fastmath=True)
def quat_to_rotvec(q, eps=1e-12):
    # Map unit quaternion to rotation vector using exact formula
    q = q / np.linalg.norm(q)
    v = q[:3]
    w = q[3]
    v_norm = np.linalg.norm(v)
    if v_norm < eps:
        return np.zeros(3)
    angle = 2.0 * np.arctan2(v_norm, w)
    return v * (angle / v_norm)