import numpy as np
from numba import njit


# Dormand–Prince (RK45) Butcher tableau
C = np.array([0.0, 1/5, 3/10, 4/5, 8/9, 1.0, 1.0])

A = np.array([
    [0.0],
    [1/5],
    [3/40,       9/40],
    [44/45,     -56/15,     32/9],
    [19372/6561, -25360/2187, 64448/6561,  -212/729],
    [9017/3168,  -355/33,    46732/5247,    49/176,   -5103/18656],
    [35/384,     0.0,        500/1113,      125/192,  -2187/6784, 11/84]
], dtype=np.float64)

# 5th-order weights (for main solution)
B5 = np.array([35/384, 0.0, 500/1113, 125/192,
               -2187/6784, 11/84, 0.0], dtype=np.float64)

# 4th-order weights (for error estimate)
B4 = np.array([5179/57600, 0.0, 7571/16695, 393/640,
               -92097/339200, 187/2100, 1/40], dtype=np.float64)


@njit
def rk45_step(fun, t, y, dt):
    """
    Perform one Dormand–Prince RK45 step.
    
    Parameters
    ----------
    fun : callable(t, y) -> ndarray
        ODE function dy/dt = f(t, y).
    t : float
        Current time.
    y : ndarray
        Current state.
    dt : float
        Step size.
    
    Returns
    -------
    y5 : ndarray
        5th-order solution at t + dt.
    y4 : ndarray
        4th-order solution at t + dt.
    err : ndarray
        Difference (y5 - y4), error estimate.
    """
    k = [None] * 7  # allocate storage for stages

    # Stage 1
    k[0] = fun(t, y)

    # Stage 2
    k[1] = fun(t + C[1]*dt,
               y + dt * (A[1][0] * k[0]))

    # Stage 3
    k[2] = fun(t + C[2]*dt,
               y + dt * (A[2][0] * k[0] + A[2][1] * k[1]))

    # Stage 4
    k[3] = fun(t + C[3]*dt,
               y + dt * (A[3][0] * k[0] + A[3][1] * k[1] + A[3][2] * k[2]))

    # Stage 5
    k[4] = fun(t + C[4]*dt,
               y + dt * (A[4][0] * k[0] + A[4][1] * k[1] + A[4][2] * k[2] + A[4][3] * k[3]))

    # Stage 6
    k[5] = fun(t + C[5]*dt,
               y + dt * (A[5][0] * k[0] + A[5][1] * k[1] + A[5][2] * k[2] +
                         A[5][3] * k[3] + A[5][4] * k[4]))

    # Stage 7 
    k[6] = fun(t + C[6]*dt,
               y + dt * (A[6][0] * k[0] + A[6][1] * k[1] + A[6][2] * k[2] +
                         A[6][3] * k[3] + A[6][4] * k[4] + A[6][5] * k[5]))

    # 5th-order solution (main value we return)
    y5 = y + dt * (B5[0]*k[0] + B5[1]*k[1] + B5[2]*k[2] +
                   B5[3]*k[3] + B5[4]*k[4] + B5[5]*k[5])

    # 4th-order solution (for error estimation)
    y4 = y + dt * (B4[0]*k[0] + B4[1]*k[1] + B4[2]*k[2] +
                   B4[3]*k[3] + B4[4]*k[4] + B4[5]*k[5] + B4[6]*k[6])

    # Error estimate
    err = y5 - y4

    return y5, y4, err


@njit
def rk45_step_autonomous(fun, y, dt, *args):
    """
    Dormand–Prince RK45 step for autonomous systems with extra arguments.

    Parameters
    ----------
    fun : callable(y, *args) -> ndarray
        Dynamics function dy/dt = f(y, *args).
    y : ndarray
        Current state.
    dt : float
        Step size.
    *args : tuple
        Extra arguments passed to fun.

    Returns
    -------
    y5 : ndarray
        5th-order solution at t + dt.
    y4 : ndarray
        4th-order solution at t + dt.
    err : ndarray
        Difference (y5 - y4), error estimate.
    """
    k = [None] * 7

    k[0] = fun(y, *args)
    k[1] = fun(y + dt*(A[1][0]*k[0]), *args)
    k[2] = fun(y + dt*(A[2][0]*k[0] + A[2][1]*k[1]), *args)
    k[3] = fun(y + dt*(A[3][0]*k[0] + A[3][1]*k[1] + A[3][2]*k[2]), *args)
    k[4] = fun(y + dt*(A[4][0]*k[0] + A[4][1]*k[1] + A[4][2]*k[2] + A[4][3]*k[3]), *args)
    k[5] = fun(y + dt*(A[5][0]*k[0] + A[5][1]*k[1] + A[5][2]*k[2] +
                       A[5][3]*k[3] + A[5][4]*k[4]), *args)
    k[6] = fun(y + dt*(A[6][0]*k[0] + A[6][1]*k[1] + A[6][2]*k[2] +
                       A[6][3]*k[3] + A[6][4]*k[4] + A[6][5]*k[5]), *args)

    y5 = y + dt*(B5[0]*k[0] + B5[1]*k[1] + B5[2]*k[2] +
                 B5[3]*k[3] + B5[4]*k[4] + B5[5]*k[5])

    y4 = y + dt*(B4[0]*k[0] + B4[1]*k[1] + B4[2]*k[2] +
                 B4[3]*k[3] + B4[4]*k[4] + B4[5]*k[5] + B4[6]*k[6])

    err = y5 - y4
    return y5, y4, err