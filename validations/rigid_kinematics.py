import numpy as np
import sys
import os
from matplotlib import pyplot as plt


"""
Seems to work well!
with these initial conditions:
q_bi: [0.0, 0, 0.0, 1]
omega_bi_radps: [0.05, 0.04, 0.1]

We expect then on a steady state that w_z is constant, w_t is constant, w_norm is constant, and h_norm is constant.
At the beginning, none of those are constant because the body is not in a steady state (its attitude is not in a stable equilibrium).
h_norm is constant throughout which is good.

"""

# Add the parent directory to the path (so 'plant' is recognized as a package)
script_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(script_dir)  # This is the project root
sys.path.insert(0, parent_dir)

from plant.plant import Plant

plant = Plant('plant/config_default.yaml')

w_z_history = []
w_t_history = []
w_norm_history = []
h_norm_history = []

for _ in range(1000):
    euler_angles, angular_velocity = plant.update()
    
    w_z_history.append(angular_velocity[2])
    w_t_history.append(np.linalg.norm(angular_velocity[:2]))
    w_norm_history.append(np.linalg.norm(angular_velocity))
    h_norm_history.append(np.linalg.norm(plant.J @ angular_velocity))


fig, ax = plt.subplots()
ax.plot(w_z_history)
ax.plot(w_t_history)
ax.plot(w_norm_history)
ax.legend(['w_z', 'w_t', 'w_norm'])

fig, ax = plt.subplots()
ax.plot(h_norm_history)
ax.legend(['h_norm'])

plt.show()


