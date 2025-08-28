
from matplotlib import pyplot as plt
import numpy as np
import os
import sys

from pathlib import Path
from scipy.integrate import solve_ivp

# Add the project root directory to the path (relative to this script's location)
script_dir = Path(__file__).parent
project_root = script_dir.parent
sys.path.insert(0, str(project_root))

from plant.dynamics import state_deriv
from plant.quaternion_math import Quaternion
from plant.sim import Plant

r0 = np.array([7000e3, 0, 0])
v0 = np.array([0, 7800, 0])
q0 = np.array([0.1494, 0.1494, 0.1494, 0.9659])
w0 = np.array([0.03, 0.02, 0.1])

y0 = np.hstack((r0, v0, w0, q0))
t_max = 1000

MU_EARTH = 3.986004418e14  # [m^3/s^2]

rtol = 1e-9
atol = 1e-12

J = np.diag([2,2,1])
Ji = np.linalg.inv(J)

sol = solve_ivp(state_deriv, (0, t_max), y0, args=(MU_EARTH, J, Ji, np.zeros(3)), rtol=rtol, atol=atol)

r_history = sol.y[0:3, :]
v_history = sol.y[3:6, :]
w_history = sol.y[6:9, :]
q_history = sol.y[9:13, :]
t_history = sol.t

delta_t = np.diff(t_history)

w_z_history = w_history[2, :]
w_t_history = np.linalg.norm(w_history[0:2, :], axis=0)
w_x_history = w_history[0, :]
w_y_history = w_history[1, :]
w_norm_history = np.linalg.norm(w_history, axis=0)
h_norm_history = np.linalg.norm(J @ w_history, axis=0)

plt.scatter(t_history, w_z_history, label='w_z')
plt.scatter(t_history, w_t_history, label='w_t')
plt.scatter(t_history, w_x_history, label='w_x')
plt.scatter(t_history, w_y_history, label='w_y')
plt.scatter(t_history, w_norm_history, label='w_norm')
plt.plot(t_history, h_norm_history, label='h_norm')
plt.legend()
plt.show()

##### With plant
plant = Plant()
t, y = plant.compute_states(t_max, rtol=rtol, atol=atol)
t_sampled, r_sampled, v_sampled, euler_sampled, w_sampled = plant.evaluate_gui(t, y, playback_speed=1, sample_rate=30)

w_z_history_plant = w_sampled[2, :]
w_t_history_plant = np.linalg.norm(w_sampled[0:2, :], axis=0)
w_x_history_plant = w_sampled[0, :] # x is the spin axis
w_y_history_plant = w_sampled[1, :] # y is the transverse axis
w_norm_history_plant = np.linalg.norm(w_sampled, axis=0)
h_norm_history_plant = np.linalg.norm(J @ w_sampled, axis=0)
euler_history_plant = euler_sampled

plt.scatter(t_sampled, w_z_history_plant, label='w_z')
plt.scatter(t_sampled, w_t_history_plant, label='w_t')
plt.scatter(t_sampled, w_x_history_plant, label='w_x')
plt.scatter(t_sampled, w_y_history_plant, label='w_y')
plt.scatter(t_sampled, w_norm_history_plant, label='w_norm')
plt.scatter(t_sampled, h_norm_history_plant, label='h_norm')
plt.title('Plant')
plt.legend()
plt.show()








