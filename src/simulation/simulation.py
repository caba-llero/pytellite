

from __future__ import annotations
from scipy.integrate import solve_ivp
import argparse
import numpy as np
import os
import yaml
from typing import Optional, Dict, Any

from ..math import quaternion as qm
from .dynamics import state_deriv, state_deriv_kalman
from ..math.quaternion import slerp_quat_array
from ..math.integration import rk45_step_autonomous as int_step
import kalman as k


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
        self.J = np.diag(cfg["spacecraft"]["inertia"]).astype(float)
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
            self.q_bi = np.array(ic["q_bi"], dtype=float)
            self.w_bi = np.array(ic["omega_bi_radps"], dtype=float)
        else:
            raise ValueError(f"Invalid initial condition frame: {frame}")

        # Initial reaction wheel angular momentum (aligned with principal axes)
        self.h0 = np.zeros(3, dtype=float)

    def compute_states(self, t_max: float, rtol: float = 1e-12, atol: float = 1e-12, 
        control_type: Optional[object] = None, kp: Optional[float] = None, 
        kd: Optional[float] = None, qc: Optional[np.ndarray] = None) -> np.ndarray:
        """
        Compute the states of the plant over a given time range.
        """
        t_span = (0, t_max)
        y0 = np.hstack((self.r0, self.v0, self.w_bi, self.q_bi, self.h0))
        
        # Map control_type to integer expected by JITed dynamics
        def _map_control_type(ct: object) -> int:
            if isinstance(ct, (int, np.integer)):
                return int(ct)
            if isinstance(ct, str):
                s = ct.lower().strip()
                if s in ("none", "zero_torque"):
                    return 0
                if s in ("inertial", "inertial_linear", "tracking"):
                    return 1
                if s in ("inertial_nonlinear", "nonlinear_tracking"):
                    return 2
            return 0

        ct_int = _map_control_type(control_type)
        kp_val = float(kp) if kp is not None else 0.0
        kd_val = float(kd) if kd is not None else 0.0
        qc_arr = np.array(qc, dtype=float) if qc is not None else np.array([0.0, 0.0, 0.0, 1.0], dtype=float)

        # Prepare args for state_deriv
        args = (self.J, self.Ji, ct_int, kp_val, kd_val, qc_arr)
            
        sol = solve_ivp(state_deriv, t_span, y0, args=args, rtol=rtol, atol=atol)
        return sol.t, sol.y

    def compute_states_kalman(self, t_max: float, dt_t: float, dt_m: float, dt_g: float, dt_c: float,
        rtol: float = 1e-12, atol: float = 1e-12, 
        control_type: Optional[object] = None, kp: Optional[float] = None, 
        kd: Optional[float] = None, qc: Optional[np.ndarray] = None) -> np.ndarray:
        """
        Compute the states of the plant over a given time range using the MEKF (estimation option on)
        """

        I3 = np.eye(3)
        O3 = np.zeros((3,3))
        arcsec_to_rad = self.arcsec_to_rad

        # Measurement model matrices
        H = np.hstack((I3, O3))
        R = I3 * (self.sigma_startracker * arcsec_to_rad) ** 2

        # Truth time grid and measurement & control update indices
        times = np.arange(0, self.t_max, self.dt)
        idx_gyro = k.measurement_indices(self.t_max, self.dt, self.freq_gyro)
        idx_star = k.measurement_indices(self.t_max, self.dt, self.freq_startracker)
        idx_ctrl = k.measurement_indices(self.t_max, self.dt, self.freq_control)
        idx_all = idx_gyro | idx_star | idx_ctrl
        timesteps = len(idx_all)

        n = 3 
        np.random.seed(self.rng_seed) # set RNG seed

        # Initial attitude estimate from a noisy measurement
        Z_n = np.random.normal(
            0, self.sigma_startracker * arcsec_to_rad * self.init_inaccuracy, n
        ).reshape(-1, 1) 
        q_m_0 = self.q_t_0.reshape(-1, 1) + 0.5 * k.Xi(self.q_t_0) @ Z_n
        q_m_0 = q_m_0.flatten() / np.linalg.norm(q_m_0)
        q_h_0 = q_m_0

        ## Allocate logs ____________________________________________________________________________________
        # Estimates
        q_h_l = np.empty((4, timesteps)) # attitude
        w_h_l = np.empty((3, timesteps)) # angular velocity
        B_h_l = np.empty((3, timesteps)) # gyro bias
        
        # Ground truth
        B_t_l = np.empty((3, timesteps))
        w_t_l = np.empty((3, timesteps))
        q_t_l = np.empty((4, timesteps))

        # Control & other
        h_l = np.empty((3, timesteps)) # angular velocity of wheels
        L_l = np.empty((3, timesteps)) # control torque
        t_l = np.empty(timesteps) # time
        G_l = np.empty(timesteps) # scalar pointing error
        Z_d_l = np.empty((3, timesteps)) # pointing error vector components
        s_l = np.empty((6, timesteps)) # standard deviation of attitude error vector and bias error, both 3 components each

        ## Copy initial states to current value ____________________________________________________________________________________
        q_t = self.q_t_0.copy()
        B_t = self.B_t_0.copy()
        B_h = self.B_h_0.copy()
        w_t = self.w_t_0.copy()
        q_h = q_h_0.copy()
        q_d = k.quat_mul(q_t, u.quat_inv(q_h))
        Z_d = k.quat_to_rotvec(q_d)
        L = np.zeros(3) # zero initial control torque
        h = np.zeros(3) # zero initial wheel angular momentum
        G = np.linalg.norm(Z_d)
        P = np.block([[self.Pq, O3], [O3, self.Pb]])

        # Initial log at t=0
        if 0 in idx_all and k < timesteps:
            s = np.sqrt(np.diag(P))
            s_l[:, 0] = s
            t_l[0] = times[0]
            q_h_l[:, 0] = q_h
            q_t_l[:, 0] = q_t
            Z_d_l[:, 0] = Z_d
            B_h_l[:, 0] = B_h.flatten()
            B_t_l[:, 0] = B_t
            h_l[:,0] = h
            G_l[:,0] = G
            L_l[:,0] = L

        # Calculate for the rest of the timesteps
        k = 1 # k=0 is the initial "measurement" time, which was assigned above
        for i in range(1, len(times)):
            # Propagate ground truth
            y = np.concatenate(w_t, h)
            w_t = int_step(state_deriv_kalman, y, dt_t, J, Ji, control_type, kp, kd, qc, q_t)
            q_t = k.quat_propagate(q_t, w_t, self.dt_t)
            B_t = B_t + np.random.normal(0, self.sigma_u * self.dt_t**0.5, n)

            # Prediction on gyro event
            if i in idx_gyro:
                dt_g = times[i] - times[last_gyro_i]
                if dt_g <= 0:
                    dt_g = self.dt
                w_t_meas = w_t_l[:, i] if i < w_t_l.shape[1] else w_t_l[:, -1]
                w_m = w_t_meas + B_t + np.random.standard_normal(n) * (
                    self.sigma_v / np.sqrt(dt_g)
                )
                w_h = w_m - B_h
                Phi = u.Phi(dt_g, w_h, I3, self.simple_Phi)
                Qk = u.Q(self.sigma_v, self.sigma_u, dt_g, I3)
                P = u.P_prop(P, Phi, Qk)
                q_h = u.quat_propagate(q_h, w_h, dt_g)
                last_gyro_i = i

            # Update on star tracker event
            if i in idx_star:
                dZ_m = u.startracker_meas(
                    q_t, q_h, self.sigma_startracker * arcsec_to_rad, n
                )
                K, K_Z, K_B = u.K(P, H, R)
                P = u.P_meas(K, H, P, R, self.Joseph)
                dB_h = K_B @ dZ_m
                dZ_h = K_Z @ dZ_m
                B_h = B_h + dB_h

                theta = np.linalg.norm(dZ_h)
                if theta > 0:
                    axis = dZ_h / theta
                    dq_err = np.hstack((axis * np.sin(0.5 * theta), np.cos(0.5 * theta)))
                else:
                    dq_err = np.array([0.0, 0.0, 0.0, 1.0])
                q_h = u.quat_mul(dq_err, q_h)
                q_h = q_h / np.linalg.norm(q_h)
                q_d = u.quat_mul(q_t, u.quat_inv(q_h))
                Z_d = u.quat_to_rotvec(q_d)
                G = np.linalg.norm(Z_d)

            # Update control law
            if i in idx_ctrl:
                pass


            # Log at measurement events
            if i in idx_all and k < timesteps:
                s = np.sqrt(np.diag(P))
                s_l[:, k] = s
                t_l[k] = times[i]
                G_l[k] = G
                q_h_l[:, k] = q_h
                q_t_l[:, k] = q_t
                Z_d_l[:, k] = Z_d
                B_h_l[:, k] = B_h.flatten()
                B_t_l[:, k] = B_t
                k += 1

        B_d = B_t_l - B_h_l

        self.results = {
            "t": t_l,
            "G": G_l,
            "q_h": q_h_l,
            "q_t": q_t_l,
            "Z_d": Z_d_l,
            "B_h": B_h_l,
            "B_t": B_t_l,
            "B_d": B_d,
            "s": s_l,
        }




        

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
        # Interpolate reaction wheel angular momentum components
        h_sampled = np.array([np.interp(t_sampled, t, component) for component in y[13:16]])
        # Keep Euler for legacy uses if needed
        euler_sampled = qm.quat_to_euler(q_sampled)
        return t_sampled, r_sampled, v_sampled, euler_sampled, w_sampled, q_sampled, h_sampled



### DEPRECATED ___________________________________________________________________________________________________________________

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



