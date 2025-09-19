from ..math import quaternion as qm
import numpy as np
from .dynamics import state_deriv_kalman as f
from ..math.integration import rk45_step
'''
Notation

x: state vector
z: measurement vector
u: control vector
P: covariance matrix
Q: process noise covariance matrix
R: measurement noise covariance matrix

eps: vector part of quaternion
eta: scalar part of quaternion
w: angular velocity
x = [w, eps, eta]' (dimension 7)



Subscripts:
0: initial
1: predicted
2: updated with measurement
new: new value after step (k subscript in math notation). If not specified, it is the current value (k-1 subscript)


'''




'''
Helper functions
'''



'''
Initialization
'''
# Integration
dt = 0.1

# Inertia matrix
J = np.diag([10_000, 9_000, 12_000])
Ji = np.linalg.inv(J)

# Initial state

# We should allow the user to specify the initial state
# 1. Deviation from true initial attitude at a certain pointing error (perhaps coarse initial attitude)
# 2. A certain inputted initial attitude
# 3. Identity quaternion attitude
w0 = np.array([0.0, 0.0, 0.0])
eps0 = np.array([0.0, 0.0, 0.0])
eta0 = 1.0
x0 = np.hstack((w0, eps0, eta0))
P0 = np.eye(7)



''' 
Prediction
'''
