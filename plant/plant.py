"""
Satellite Plant Simulator

This module simulates the physical behavior of a satellite in orbit, including:
- Orbital dynamics (position and velocity in Earth-Centered Inertial frame)
- Attitude dynamics (orientation using quaternions)
- Sensor modeling (GPS and gyro with realistic noise)
- Real-time simulation with configurable time scaling
- UDP communication with flight software
- Data logging for replay and analysis

The simulator runs in a Software-in-the-Loop (SIL) configuration where it provides
realistic sensor data to flight software and receives actuator commands.
"""

from __future__ import annotations
from scipy.integrate import solve_ivp
import argparse
import numpy as np
import yaml

try:
    # Try relative imports (when run as module)
    from .dynamics import rk4_step_orbit, integrate_attitude_quat_mult, integrate_ang_vel_rk4, orbit_to_inertial
    from .quaternion_math import rotmatrix_to_quaternion, quat_to_euler, Quaternion, quat_to_rotmatrix
except ImportError:
    # Fall back to absolute imports (when imported by other scripts)
    from dynamics import state_deriv, rk4_step_orbit, integrate_attitude_quat_mult, integrate_ang_vel_rk4, orbit_to_inertial
    from quaternion_math import rotmatrix_to_quaternion, quat_to_euler, Quaternion, quat_to_rotmatrix


MU_EARTH = 3.986004418e14  # [m^3/s^2]

class Plant:
    def __init__(self, config_path: str = "plant/config_default.yaml"):
        with open(config_path, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f)


        # Initial orbital state
        self.r0 = np.array(cfg["initial_conditions"]["r_eci_m"], dtype=float)
        self.v0 = np.array(cfg["initial_conditions"]["v_eci_mps"], dtype=float)


        # Spacecraft properties
        self.J = np.diag(cfg["spacecraft"]["inertia"])
        self.Ji = np.linalg.inv(self.J)
        self.L = np.zeros(3) # No torque

        # Initial attitude state
        ic = cfg["initial_conditions"]
        frame = ic.get("frame", "inertial")

        if frame == 'orbit':
            q_bo_init = Quaternion(ic["q_ob"])
            w_bo_init = np.array(ic["omega_bo_radps"], dtype=float)

            # Compute initial orbit frame
            _, _, a0 = rk4_step_orbit(r0, v0, 0) # Get initial acceleration
            R_io, w_oi = orbit_to_inertial(r0, v0, a0)
            q_io = rotmatrix_to_quaternion(R_io)

            # Initialize body state wrt inertial frame
            self.q_bi = q_io * q_bo_init
            
            R_bo = quat_to_rotmatrix(q_bo_init)
            self.w_bi = w_bo_init + R_bo.T @ w_oi
        elif frame == 'inertial':
            self.q_bi = Quaternion(ic["q_bi"])
            self.w_bi = np.array(ic["omega_bi_radps"], dtype=float)
        else:
            raise ValueError(f"Invalid initial condition frame: {frame}")

    def compute_states(self, t_range: tuple[float, float], rtol: float = 1e-12) -> np.ndarray:
        """
        Compute the states of the plant over a given time range.
        """
        t_span = (t_range[0], t_range[1])
        y0 = np.hstack((self.r0, self.v0, self.q_bi.q, self.w_bi))
        sol = solve_ivp(state_deriv, t_span, y0, args=(MU_EARTH, self.J, self.Ji, self.L), rtol=rtol)
        return sol.t, sol.y



    def update(self) -> np.ndarray:
        """
        DEPRECATED
        Update the plant state by one time step.
        Returns the euler angles (roll, pitch, yaw) of the body wrt inertial frame.
        """
        # For this task, we can ignore orbital motion update in the loop,
        # as it does not affect unforced attitude dynamics.
        # self.r_i, self.v_i, _ = rk4_step_orbit(self.r_i, self.v_i, self.dt_sim)

        self.w_bi = integrate_ang_vel_rk4(self.w_bi, self.J, self.L, self.dt_sim)
        self.q_bi = integrate_attitude_quat_mult(self.q_bi, self.w_bi, self.dt_sim)

        self.t_sim += self.dt_sim

        euler_angles = quat_to_euler(self.q_bi)
        angular_velocity = self.w_bi
        
        return euler_angles, angular_velocity


def main():
    """Main entry point for the satellite plant simulator.

    Parses command line arguments and starts the simulation with the specified
    configuration file. This allows the simulator to be run as a standalone
    program from the command line.
    """
    # Set up command line argument parser
    parser = argparse.ArgumentParser(description="Satellite Plant Simulator (MVP)")
    parser.add_argument("--config", type=str, default="plant/config_default.yaml",
                       help="Path to YAML configuration file")
    args = parser.parse_args()

    # Example of how to use the Plant class
    plant = Plant(args.config)
    print(plant.q_bi)
    print(plant.w_bi)
    for _ in range(10000):
        euler_angles = plant.update()
        #print(f"t={plant.t_sim:.2f}, roll={euler_angles[0]:.2f}, pitch={euler_angles[1]:.2f}, yaw={euler_angles[2]:.2f}")


if __name__ == "__main__":
    main()



