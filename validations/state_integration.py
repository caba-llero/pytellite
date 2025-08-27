
from matplotlib import pyplot as plt
import numpy as np
import os
import sys
from scipy.integrate import solve_ivp

# Add the plant directory to the path (relative to this script's location)
script_dir = os.path.dirname(os.path.abspath(__file__))
plant_dir = os.path.join(script_dir, '..', 'plant')
sys.path.insert(0, plant_dir)

from dynamics import state_deriv
from quaternion_math import Quaternion

r0 = np.array([7000e3, 0, 0])
v0 = np.array([0, 7800, 0])
q0 = np.array([0.1494, 0.1494, 0.1494, 0.9659])
w0 = np.array([0.03, 0.02, 0.1])

y0 = np.hstack((r0, v0, q0, w0))
t_span = (0, 1000)

MU_EARTH = 3.986004418e14  # [m^3/s^2]

rtol = 1e-12

J = np.diag([2,2,1])
Ji = np.linalg.inv(J)

sol = solve_ivp(state_deriv, t_span, y0, args=(MU_EARTH, J, Ji, np.zeros(3)), rtol=rtol)

r_history = sol.y[0:3, :]
v_history = sol.y[3:6, :]
q_history = sol.y[6:10, :]
w_history = sol.y[10:13, :]
t_history = sol.t

delta_t = np.diff(t_history)

w_z_history = w_history[2, :]
w_t_history = np.linalg.norm(w_history[0:2, :], axis=0)
w_x_history = w_history[0, :]
w_y_history = w_history[1, :]
w_norm_history = np.linalg.norm(w_history, axis=0)
h_norm_history = np.linalg.norm(J @ w_history, axis=0)

plt.plot(t_history, w_z_history, label='w_z')
plt.plot(t_history, w_t_history, label='w_t')
plt.plot(t_history, w_x_history, label='w_x')
plt.plot(t_history, w_y_history, label='w_y')
plt.plot(t_history, w_norm_history, label='w_norm')
plt.plot(t_history, h_norm_history, label='h_norm')
plt.legend()
plt.show()







