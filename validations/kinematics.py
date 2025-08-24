import numpy as np
import sys
import os

# Add the plant directory to the path (relative to this script's location)
script_dir = os.path.dirname(os.path.abspath(__file__))
plant_dir = os.path.join(script_dir, '..', 'plant')
sys.path.insert(0, plant_dir)

from quaternion_math import Quaternion
from dynamics import integrate_attitude_quat_mult

# Test parameters
omega_b = np.array([0.0, 0.0, 1.0])  # rad/s, spin about z-axis
dt = 0.1                             # s
steps = 100                          # total integration steps
T = steps * dt                       # total time

# Initial attitude (identity quaternion)
q = Quaternion(0, 0, 0, 1)

# Store results
q_history = [q]

for _ in range(steps):
    q = integrate_attitude_quat_mult(q, omega_b, dt)
    q_history.append(q)

# Analytic solution: rotation about z-axis by angle = omega * T
theta_true = np.linalg.norm(omega_b) * T
q_true = Quaternion(
    0.0,
    0.0,
    np.sin(theta_true / 2),
    np.cos(theta_true / 2)
)

print("Final integrated quaternion:", q_history[-1])
print("Analytic quaternion:", q_true)
print("Angle error (rad):", 2 * np.arccos(np.clip(np.abs(q_history[-1].q[3,0]*q_true.q[3,0] +
                                                          np.dot(q_history[-1].q[:3,0], q_true.q[:3,0])), -1.0, 1.0)))
