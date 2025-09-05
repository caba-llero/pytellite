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
import os
import yaml
from typing import Optional, Dict, Any

from ..math import quaternion as qm
from .dynamics import state_deriv
from ..math.quaternion import slerp_quat_array


MU_EARTH = 3.986004418e14  # [m^3/s^2]

class Plant:
    def __init__(self, config_path: Optional[str] = None, config: Optional[Dict[str, Any]] = None):
        if config is not None:
            cfg = config
        else:
            if config_path is None:
                # Use default config relative to this module's location
                module_dir = os.path.dirname(os.path.abspath(__file__))
                config_path = os.path.join(module_dir, "config_default.yaml")
            with open(config_path, "r", encoding="utf-8") as f:
                cfg = yaml.safe_load(f)


        # Simulation timing
        sim_section = cfg.get("simulation", {})
        self.dt_sim = float(sim_section.get("dt_sim", 0.1))
        self.t_sim = 0.0

        # Initial orbital state
        self.r0 = np.array(cfg["initial_conditions"]["r_eci_m"], dtype=float)
        self.v0 = np.array(cfg["initial_conditions"]["v_eci_mps"], dtype=float)


        # Spacecraft properties
        self.J = np.diag(cfg["spacecraft"]["inertia"])
        self.Ji = np.linalg.inv(self.J)

        # Initial attitude state
        ic = cfg["initial_conditions"]
        frame = ic.get("frame", "inertial")

        if frame == 'orbit':
            raise NotImplementedError("Orbit frame initialization is not yet refactored.")
            # The following code needs to be updated to use numpy arrays for quaternions
            # q_bo_init = Quaternion(ic["q_ob"])
            # w_bo_init = np.array(ic["omega_bo_radps"], dtype=float)

            # # Compute initial orbit frame
            # _, _, a0 = rk4_step_orbit(self.r0, self.v0, 0) # Get initial acceleration
            # R_io, w_oi = orbit_to_inertial(self.r0, self.v0, a0)
            # q_io = rotmatrix_to_quaternion(R_io)

            # # Initialize body state wrt inertial frame
            # self.q_bi = q_io * q_bo_init
            
            # R_bo = quat_to_rotmatrix(q_bo_init)
            # self.w_bi = w_bo_init + R_bo.T @ w_oi
        elif frame == 'inertial':
            self.q_bi = np.array(ic["q_bi"])
            self.w_bi = np.array(ic["omega_bi_radps"], dtype=float)
        else:
            raise ValueError(f"Invalid initial condition frame: {frame}")

    def compute_states(self, t_max: float, rtol: float = 1e-12, atol: float = 1e-12, 
        control_type: Optional[str] = None, kp: Optional[float] = None, 
        kd: Optional[float] = None, qc: Optional[np.ndarray] = None) -> np.ndarray:
        """
        Compute the states of the plant over a given time range.
        """
        t_span = (0, t_max)
        y0 = np.hstack((self.r0, self.v0, self.w_bi, self.q_bi))
        
        # Determine args for state_deriv based on provided control parameters
        if control_type is not None and kp is not None and kd is not None and qc is not None:
            args = (self.J, self.Ji, control_type, kp, kd, qc)
        else:
            # Fallback to zero_torque if control params are missing
            args = (self.J, self.Ji, "zero_torque", 0.0, 0.0, np.array([0,0,0,1.0]))
            
        sol = solve_ivp(state_deriv, t_span, y0, args=args, rtol=rtol, atol=atol)
        return sol.t, sol.y

    def evaluate_gui(self, t, y, playback_speed: float = 1.0, sample_rate: float = 30) -> np.ndarray:
        """
        Takes the computed states and returns the states at the sample rate.
        playback_speed is the factor by which the simulation time is scaled (e.g. 1.0 for real time, 0.1 for 10x slow-motion)
        sample_rate is the number of samples per second.
        """
        t_sampled = np.arange(0, t[-1], playback_speed/sample_rate)
        y_sampled = np.array([np.interp(t_sampled, t, component) for component in y[:9]])
        r_sampled = y_sampled[0:3]  
        v_sampled = y_sampled[3:6]
        w_sampled = y_sampled[6:9]
        # Interpolate attitude quaternions (scalar-last [x, y, z, w])
        q_sampled = slerp_quat_array(t_sampled, t, y[9:13])
        # Keep Euler for legacy uses if needed
        euler_sampled = qm.quat_to_euler(q_sampled)
        return t_sampled, r_sampled, v_sampled, euler_sampled, w_sampled, q_sampled


### DEPRECATED

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

        euler_angles = qm.quat_to_euler(self.q_bi)
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
        euler_angles, angular_velocity = plant.update()
        #print(f"t={plant.t_sim:.2f}, roll={euler_angles[0]:.2f}, pitch={euler_angles[1]:.2f}, yaw={euler_angles[2]:.2f}")


if __name__ == "__main__":
    main()



