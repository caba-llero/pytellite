import numpy as np
from numba import njit

# Dormand-Prince (RK45) Butcher tableau
# Coefficients for the stages
C = np.array([0.0, 1/5, 3/10, 4/5, 8/9, 1.0, 1.0])
A = np.array([
    [0.0],
    [1/5],
    [3/40, 9/40],
    [44/45, -56/15, 32/9],
    [19372/6561, -25360/2187, 64448/6561, -212/729],
    [9017/3168, -355/33, 46732/5247, 49/176, -5103/18656],
    [35/384, 0.0, 500/1113, 125/192, -2187/6784, 11/84]
], dtype=np.float64)

# 5th order solution weights (b)
B5 = np.array([35/384, 0.0, 500/1113, 125/192,
               -2187/6784, 11/84, 0.0], dtype=np.float64)

# 4th order solution weights (b_hat)
B4 = np.array([5179/57600, 0.0, 7571/16695, 393/640,
               -92097/339200, 187/2100, 1/40], dtype=np.float64)


@njit
def rk45_step(fun, t, y, dt):
    """
    Perform a single Dormand-Prince RK45 step.
    
    Parameters
    ----------
    fun : callable(t, y) -> ndarray
        Dynamics function dy/dt = f(t, y).
    t : float
        Current time.
    y : ndarray
        Current state.
    dt : float
        Step size.
    
    Returns
    -------
    y5 : ndarray
        5th order solution at t + dt.
    y4 : ndarray
        4th order solution at t + dt.
    err : ndarray
        Difference y5 - y4, error estimate.
    """
    k = []
    k1 = fun(t, y)
    k.append(k1)

    k2 = fun(t + C[1]*dt, y + dt*(A[1][0]*k1))
    k.append(k2)

    k3 = fun(t + C[2]*dt, y + dt*(A[2][0]*k1 + A[2][1]*k2))
    k.append(k3)

    k4 = fun(t + C[3]*dt, y + dt*(A[3][0]*k1 + A[3][1]*k2 + A[3][2]*k3))
    k.append(k4)

    k5 = fun(t + C[4]*dt, y + dt*(A[4][0]*k1 + A[4][1]*k2 + A[4][2]*k3 + A[4][3]*k4))
    k.append(k5)

    k6 = fun(t + C[5]*dt, y + dt*(A[5][0]*k1 + A[5][1]*k2 + A[5][2]*k3 + A[5][3]*k4 + A[5][4]*k5))
    k.append(k6)

    k7 = fun(t + C[6]*dt, y + dt*(A[6][0]*k1 + A[6][2]*k3 + A[6][3]*k4 + A[6][4]*k5 + A[6][5]*k6))
    k.append(k7)

    # 5th order solution
    y5 = y + dt*(B5[0]*k1 + B5[2]*k3 + B5[3]*k4 + B5[4]*k5 + B5[5]*k6)

    # 4th order solution
    y4 = y + dt*(B4[0]*k1 + B4[2]*k3 + B4[3]*k4 + B4[4]*k5 + B4[5]*k6 + B4[6]*k7)

    # Error estimate
    err = y5 - y4

    return y5, y4, err
