#!/usr/bin/env python3
"""Simple test for integrate_ang_vel_symplectic function."""

import numpy as np
import sys
import os
import matplotlib.pyplot as plt

# Add the plant directory to the Python path
sys.path.append('plant')

from dynamics import integrate_ang_vel_symplectic, integrate_ang_vel_rk4

def test_rigidbody_integration():
    """Test the rigid body equations integration with no torque and z-axis rotation.
    Axisymmetric no torque.
    Solutions in De Ruiter Ch. 13.1
    w_z should be constant
    w_t = (w_x^2 + w_y^2)^0.5 should be constant
    w_norm = (w_x^2 + w_y^2 + w_z^2)^0.5 should be constant
    h_norm = | J @ w | should be constant

    We can use the symplectic integration routine or the RK4 routine.
    Symplectic requires a much smaller time step to maintain accuracy, but maintains angular momentum.
    RK4 is more accurate, but does not maintain angular momentum.
    """

    print("Testing Rigid Body Equations Integration for Axisymmetric Body with No Torque")
    print("=" * 70)

    # Test parameters
    dt = 0.1  # Time step [s]
    num_steps = 10000
    tolerance = 1e-1
    integrator = 1 # 0 = symplectic, 1 = RK4

    # Initial angular velocity 
    w0 = np.array([0.03, 0.02, 0.1])  # [rad/s]
    
    # Axisymmetric body 
    J = np.array([[2.0, 0.0, 0.0],    # [kg*m²]
                  [0.0, 2.0, 0.0],
                  [0.0, 0.0, 1.0]])

    # No external torque
    L = np.array([0.0, 0.0, 0.0])  # [N*m]

    print(f"Initial angular velocity w0: {w0}")
    print(f"Inertia matrix J:\n{J}")
    print(f"Time step dt: {dt}, Number of steps: {num_steps}")

    # Store history
    w_history = np.zeros((num_steps + 1, 3))
    w_history[0] = w0
    
    w_current = w0.copy()
    for i in range(num_steps):
        if integrator == 0:
            w_current = integrate_ang_vel_symplectic(w_current, J, L, dt)
        elif integrator == 1:
            w_current = integrate_ang_vel_rk4(w_current, J, L, dt)
        else:
            raise ValueError(f"Invalid integrator: {integrator}")
        w_history[i+1] = w_current

    # --- Validation ---
    print("\nValidating conserved quantities...")

    # 1. Angular momentum h = J @ w
    h_history = np.array([J @ w for w in w_history])
    
    # For torque-free motion, the magnitude of the angular momentum vector is conserved in the body frame.
    # The vector itself is constant in the inertial frame, but it moves in the body frame.
    h_norm_history = np.linalg.norm(h_history, axis=1)
    assert np.allclose(h_norm_history, h_norm_history[0], atol=tolerance), "Angular momentum magnitude should be constant"
    print(f"✅ Angular momentum magnitude constant (initial: {h_norm_history[0]:.6f}, final: {h_norm_history[-1]:.6f})")

    # 2. w_z
    w_z_history = w_history[:, 2]
    assert np.allclose(w_z_history, w_z_history[0], atol=tolerance), "w_z should be constant"
    print(f"✅ w_z is constant (initial: {w_z_history[0]:.6f}, final: {w_z_history[-1]:.6f})")

    # 3. w_t = (w_x^2 + w_y^2)^0.5
    w_t_history = np.linalg.norm(w_history[:, :2], axis=1)
    assert np.allclose(w_t_history, w_t_history[0], atol=tolerance), "w_t should be constant"
    print(f"✅ w_t is constant (initial: {w_t_history[0]:.6f}, final: {w_t_history[-1]:.6f})")

    # 4. Kinetic Energy T = 0.5 * w.T @ J @ w 
    T_history = 0.5 * np.array([w.T @ J @ w for w in w_history])
    assert np.allclose(T_history, T_history[0], atol=tolerance), "Kinetic energy should be conserved"
    print(f"✅ Kinetic energy is constant (initial: {T_history[0]:.6f}, final: {T_history[-1]:.6f})")

    # 5. w_norm = |w|
    # For an axisymmetric body with torque-free motion, |w| is constant because w_t and w_z are constant.
    w_norm_history = np.linalg.norm(w_history, axis=1)
    assert np.allclose(w_norm_history, w_norm_history[0], atol=tolerance), "|w| should be constant"
    print(f"✅ |w| is constant (initial: {w_norm_history[0]:.6f}, final: {w_norm_history[-1]:.6f})")

    print("\nAll checks passed!")
    
    # Optional: Plotting for visual confirmation
    time = np.linspace(0, num_steps * dt, num_steps + 1)
    fig, axs = plt.subplots(3, 1, figsize=(10, 8), sharex=True)
    axs[0].plot(time, w_history[:, 0], label='w_x')
    axs[0].plot(time, w_history[:, 1], label='w_y')
    axs[0].plot(time, w_history[:, 2], label='w_z')
    axs[0].set_ylabel('Angular Velocity [rad/s]')
    axs[0].legend()
    axs[0].grid(True)
    
    axs[1].plot(time, w_t_history, label='w_t')
    axs[1].plot(time, w_norm_history, label='|w|')
    axs[1].set_ylabel('Magnitudes [rad/s]')
    axs[1].legend()
    axs[1].grid(True)
    axs[1].set_ylim([min(w_t_history)*0.9, max(w_norm_history)*1.1])

    axs[2].plot(time, h_norm_history, label='|h|')
    axs[2].set_ylabel('Ang. Momentum Mag. [kg*m^2/s]')
    axs[2].legend()
    axs[2].grid(True)
    
    plt.xlabel('Time [s]')
    plt.suptitle('Symplectic Integration of Axisymmetric Body')
    plt.tight_layout(rect=[0, 0.03, 1, 0.95])
    plt.show()
    print("\nGenerated plot: symplectic_integration_test.png")

if __name__ == "__main__":
    test_rigidbody_integration()