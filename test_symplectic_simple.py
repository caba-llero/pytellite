#!/usr/bin/env python3
"""Simple test for integrate_ang_vel_symplectic function."""

import numpy as np
import sys
import os

# Add the plant directory to the Python path
sys.path.append('plant')

from dynamics import integrate_ang_vel_symplectic

def test_symplectic_simple():
    """Simple test with no torque and z-axis rotation."""

    print("Symplectic Integration Test")
    print("=" * 40)

    # Test case: pure z-axis rotation with no torque
    w = np.array([0.0, 0.0, 1.0])  # Only z-component [rad/s]
    J = np.array([[2.0, 0.0, 0.0],
                  [0.0, 2.0, 0.0],
                  [0.0, 0.0, 1.0]])  # Diagonal inertia matrix
    L = np.array([0.0, 0.0, 0.0])    # No torque
    dt = 0.01                       # Time step

    print(f"Initial w: {w} (magnitude: {np.linalg.norm(w):.6f})")

    # Run one integration step
    w_next = integrate_ang_vel_symplectic(w, J, L, dt)

    print(f"After dt={dt}s: {w_next} (magnitude: {np.linalg.norm(w_next):.6f})")

    # Check angular momentum conservation
    h_initial = J @ w
    h_final = J @ w_next
    h_diff = np.linalg.norm(h_final - h_initial)

    print(f"Angular momentum conserved: {h_diff < 1e-12}")

    # Run multiple steps
    print("\nRunning 5 steps:")
    w_current = w.copy()
    for i in range(5):
        w_current = integrate_ang_vel_symplectic(w_current, J, L, dt)
        magnitude = np.linalg.norm(w_current)
        print(f"Step {i+1}: w = {w_current}, |w| = {magnitude:.6f}")

if __name__ == "__main__":
    test_symplectic_simple()
