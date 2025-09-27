from __future__ import annotations

import argparse
import os
from typing import Any, Dict, Optional

import numpy as np
import yaml
from scipy.integrate import solve_ivp

from ..math import quaternion as qm
from ..math.integration import rk45_step_autonomous as int_step
from ..math.quaternion import slerp_quat_array
from . import kalman as k
from .control import control_laws
from .dynamics import state_deriv, state_deriv_kalman


MU_EARTH = 3.986004418e14  # [m^3/s^2]
ARCSEC_TO_RAD = np.deg2rad(1.0 / 3600.0)
DEFAULT_QC = np.array([0.0, 0.0, 0.0, 1.0], dtype=float)


def _map_control_type(control_type: object) -> int:
    """Normalize control type selector to internal integer identifier."""
    if isinstance(control_type, (int, np.integer)):
        return int(control_type)
    if isinstance(control_type, str):
        s = control_type.lower().strip()
        if s in {"none", "zero_torque", "off"}:
            return 0
        if s in {"inertial", "inertial_linear", "tracking"}:
            return 1
        if s in {"inertial_nonlinear", "nonlinear_tracking"}:
            return 2
    return 0


class Plant:
    """Bundle truth dynamics and optional attitude estimation."""

    def __init__(self, config_path: Optional[str] = None, config: Optional[Dict[str, Any]] = None) -> None:
        if config is not None:
            cfg = config
        else:
            if config_path is None:
                module_dir = os.path.dirname(os.path.abspath(__file__))
                config_path = os.path.join(module_dir, "config_default.yaml")
            with open(config_path, "r", encoding="utf-8") as f:
                cfg = yaml.safe_load(f)

        self._load_simulation_core(cfg)
        self._configure_estimation(cfg.get("estimation", {}))
    
    def _load_simulation_core(self, cfg: Dict[str, Any]) -> None:
        """Load core dynamics configuration."""
        # Simulation timing
        sim_section = cfg.get("simulation", {})
        self.dt_sim = float(sim_section.get("dt_sim", 0.1))
        self.t_sim = 0.0

        # Initial orbital state
        ic_section = cfg.get("initial_conditions", {})
        self.r0 = np.array(ic_section.get("r_eci_m", [0.0, 0.0, 0.0]), dtype=float)
        self.v0 = np.array(ic_section.get("v_eci_mps", [0.0, 0.0, 0.0]), dtype=float)

        # Spacecraft properties
        inertia = cfg.get("spacecraft", {}).get("inertia", [1.0, 1.0, 1.0])
        self.J = np.diag(np.array(inertia, dtype=float))
        self.Ji = np.linalg.inv(self.J)

        # Initial attitude state
        frame = ic_section.get("frame", "inertial")
        if frame == "orbit":
            raise NotImplementedError("Orbit frame initialization is not yet refactored.")
        if frame != "inertial":
            raise ValueError(f"Invalid initial condition frame: {frame}")

        self.q_bi = np.array(ic_section.get("q_bi", [0.0, 0.0, 0.0, 1.0]), dtype=float)
        self.w_bi = np.array(ic_section.get("omega_bi_radps", [0.0, 0.0, 0.0]), dtype=float)

        # Initial reaction wheel angular momentum (aligned with principal axes)
        self.h0 = np.zeros(3, dtype=float)

    def _configure_estimation(self, cfg: Dict[str, Any]) -> None:
        """Load estimation-related parameters (defaults when disabled)."""

        def _to_float(value: Any, default: float = 0.0) -> float:
            try:
                if value is None:
                    return default
                return float(value)
            except (TypeError, ValueError):
                return default

        self.estimation_enabled = bool(cfg.get("enable_estimation", False))

        # Sampling intervals (fallbacks ensure estimator still runs when disabled)
        freq_truth = _to_float(cfg.get("gt_freq"), 0.0)
        freq_gyro = _to_float(cfg.get("gyro_meas_freq"), 0.0)
        freq_star = _to_float(cfg.get("star_meas_freq"), 0.0)
        freq_ctrl = _to_float(cfg.get("ctrl_freq"), 0.0)

        self.dt_truth = 1.0 / freq_truth if freq_truth > 0 else 0.01
        self.dt_gyro = 1.0 / freq_gyro if freq_gyro > 0 else self.dt_truth
        self.dt_star = 1.0 / freq_star if freq_star > 0 else self.dt_truth
        self.dt_ctrl = 1.0 / freq_ctrl if freq_ctrl > 0 else self.dt_truth

        self.freq_truth = 1.0 / self.dt_truth
        self.freq_gyro = 1.0 / self.dt_gyro if self.dt_gyro > 0 else 0.0
        self.freq_startracker = 1.0 / self.dt_star if self.dt_star > 0 else 0.0
        self.freq_control = 1.0 / self.dt_ctrl if self.dt_ctrl > 0 else 0.0

        self.rng_seed = int(_to_float(cfg.get("rng_seed"), 0.0))
        self.sigma_startracker = _to_float(cfg.get("star_iso_acc"), 0.0)
        self.init_inaccuracy = _to_float(cfg.get("star_init_acc"), 0.0)
        self.sigma_v = _to_float(cfg.get("gyro_arw"), 0.0)
        self.sigma_u = _to_float(cfg.get("gyro_rrw"), 0.0)

        bias_true = _to_float(cfg.get("gyro_true_bias"), 0.0)
        bias_est = _to_float(cfg.get("gyro_est_bias"), 0.0)
        bias_init_cov = max(_to_float(cfg.get("gyro_init_cov"), 0.0), 0.0)
        attitude_init_cov = max(_to_float(cfg.get("attitude_init_cov"), bias_init_cov), 0.0)

        self.B_t_0 = np.full(3, bias_true, dtype=float)
        self.B_h_0 = np.full(3, bias_est, dtype=float)
        self.Pq = np.eye(3) * attitude_init_cov
        self.Pb = np.eye(3) * bias_init_cov

        self.simple_Phi = bool(cfg.get("simple_phi", False))
        self.Joseph = bool(cfg.get("joseph_covariance", True))

        # Initial truth/estimate seeds (MEKF uses these as starting point)
        self.q_t_0 = self.q_bi.copy()
        self.w_t_0 = self.w_bi.copy()

    def compute_states(
        self,
        t_max: float,
        rtol: float = 1e-12,
        atol: float = 1e-12,
        control_type: Optional[object] = None,
        kp: Optional[float] = None,
        kd: Optional[float] = None,
        qc: Optional[np.ndarray] = None,
    ) -> tuple[np.ndarray, np.ndarray]:
        """Integrate plant dynamics without estimation."""

        t_span = (0.0, t_max)
        y0 = np.hstack((self.r0, self.v0, self.w_bi, self.q_bi, self.h0))

        ct_int = _map_control_type(control_type)
        kp_val = float(kp) if kp is not None else 0.0
        kd_val = float(kd) if kd is not None else 0.0
        qc_arr = np.array(qc, dtype=float) if qc is not None else DEFAULT_QC

        args = (self.J, self.Ji, ct_int, kp_val, kd_val, qc_arr)
        sol = solve_ivp(state_deriv, t_span, y0, args=args, rtol=rtol, atol=atol)
        return sol.t, sol.y

    def compute_states_kalman(
        self,
        t_max: float,
        rtol: float = 1e-12,
        atol: float = 1e-12,
        control_type: Optional[object] = None,
        kp: Optional[float] = None,
        kd: Optional[float] = None,
        qc: Optional[np.ndarray] = None,
    ) -> dict[str, np.ndarray]:

        """Run MEKF-based simulation and log truth/estimate (estimation tab)."""

        if not self.estimation_enabled:
            raise RuntimeError("Estimation is disabled; enable it in the configuration to call this method.")

        qc_arr = np.array(qc, dtype=float) if qc is not None else DEFAULT_QC
        ct_int = _map_control_type(control_type)
        kp_val = float(kp) if kp is not None else 0.0
        kd_val = float(kd) if kd is not None else 0.0

        I3 = np.eye(3)
        O3 = np.zeros((3, 3))
        H = np.hstack((I3, O3))
        R = I3 * (self.sigma_startracker * ARCSEC_TO_RAD) ** 2

        times = np.arange(0.0, t_max, self.dt_truth)
        idx_gyro = k.measurement_indices(t_max, self.dt_truth, self.freq_gyro)
        idx_star = k.measurement_indices(t_max, self.dt_truth, self.freq_startracker)
        idx_ctrl = k.measurement_indices(t_max, self.dt_truth, self.freq_control)
        idx_all = sorted(idx_gyro | idx_star | idx_ctrl)
        timesteps = len(idx_all)

        n = 3
        np.random.seed(self.rng_seed)

        Z_n = np.random.normal(0, self.sigma_startracker * ARCSEC_TO_RAD * self.init_inaccuracy, n).reshape(-1, 1)
        q_m_0 = self.q_t_0.reshape(-1, 1) + 0.5 * k.Xi(self.q_t_0) @ Z_n
        q_m_0 = q_m_0.flatten() / np.linalg.norm(q_m_0)
        q_h_0 = q_m_0

        q_h_l = np.empty((4, timesteps))
        w_h_l = np.empty((3, timesteps))
        B_h_l = np.empty((3, timesteps))
        B_t_l = np.empty((3, timesteps))
        w_t_l = np.empty((3, timesteps))
        q_t_l = np.empty((4, timesteps))
        h_l = np.empty((3, timesteps))
        L_l = np.empty((3, timesteps))
        t_l = np.empty(timesteps)
        G_l = np.empty(timesteps)
        Z_d_l = np.empty((3, timesteps))
        s_l = np.empty((6, timesteps))

        q_t = self.q_t_0.copy()
        B_t = self.B_t_0.copy()
        B_h = self.B_h_0.copy()
        w_t = self.w_t_0.copy()
        w_h = w_t - B_h  # Initialize w_h consistent with the initial estimate
        q_h = q_h_0.copy()
        q_d = k.quat_mul(q_t, qm.quat_inv(q_h))
        Z_d = k.quat_to_rotvec(q_d)
        L = np.zeros(3)
        h = np.zeros(3)
        G = np.linalg.norm(Z_d)
        P = np.block([[self.Pq, O3], [O3, self.Pb]])

        log_index = 0
        if idx_all and idx_all[0] == 0:
            s_l[:, log_index] = np.sqrt(np.diag(P))
            t_l[log_index] = 0.0
            q_h_l[:, log_index] = q_h
            q_t_l[:, log_index] = q_t
            Z_d_l[:, log_index] = Z_d
            B_h_l[:, log_index] = B_h.flatten()
            B_t_l[:, log_index] = B_t
            w_h_l[:, log_index] = w_t
            w_t_l[:, log_index] = w_t
            h_l[:, log_index] = h
            L_l[:, log_index] = L
            G_l[log_index] = G
            log_index += 1

        for i in range(1, len(times)):
            y = np.hstack((w_t, h))
            y_next, _, _ = int_step(state_deriv_kalman, y, self.dt_truth, self.J, self.Ji, L)
            w_t = y_next[:3]
            h = y_next[3:]
            q_t = k.quat_propagate(q_t, w_t, self.dt_truth)
            B_t = B_t + np.random.normal(0.0, self.sigma_u * self.dt_truth ** 0.5, n)

            if i in idx_gyro:
                w_m = w_t + B_t + np.random.standard_normal(n) * (self.sigma_v / np.sqrt(self.dt_gyro))
                w_h = w_m - B_h
                Phi = k.Phi(self.dt_gyro, w_h, I3, self.simple_Phi)
                Qk = k.Q(self.sigma_v, self.sigma_u, self.dt_gyro, I3)
                P = k.P_prop(P, Phi, Qk)
                q_h = k.quat_propagate(q_h, w_h, self.dt_gyro)

            if i in idx_star:
                dZ_m = k.startracker_meas(q_t, q_h, self.sigma_startracker * ARCSEC_TO_RAD, n)
                K, K_Z, K_B = k.K(P, H, R)
                P = k.P_meas(K, H, P, R, self.Joseph)
                dB_h = K_B @ dZ_m
                dZ_h = K_Z @ dZ_m
                B_h = B_h + dB_h
                w_h = w_h - dB_h  # Correct w_h with the bias update

                theta = np.linalg.norm(dZ_h)
                if theta > 0:
                    axis = dZ_h / theta
                    dq_err = np.hstack((axis * np.sin(0.5 * theta), np.cos(0.5 * theta)))
                else:
                    dq_err = np.array([0.0, 0.0, 0.0, 1.0])
                q_h = k.quat_mul(dq_err, q_h)
                q_h = q_h / np.linalg.norm(q_h)

                q_d = k.quat_mul(q_t, k.quat_inv(q_h))
                Z_d = k.quat_to_rotvec(q_d)
                G = np.linalg.norm(Z_d)

            if i in idx_ctrl:
                L = control_laws(w_h, q_h, qc_arr, ct_int, kp_val, kd_val)

            if i in idx_all:
                if not i in idx_gyro:
                    w_h = w_t + B_t - B_h # If no gyro measurement, estimate w_h from truth
                if log_index >= timesteps:
                    continue
                s_l[:, log_index] = np.sqrt(np.diag(P))
                t_l[log_index] = times[i]
                G_l[log_index] = G
                q_h_l[:, log_index] = q_h
                q_t_l[:, log_index] = q_t
                Z_d_l[:, log_index] = Z_d
                B_h_l[:, log_index] = B_h.flatten()
                B_t_l[:, log_index] = B_t
                w_h_l[:, log_index] = w_h
                w_t_l[:, log_index] = w_t
                h_l[:, log_index] = h
                L_l[:, log_index] = L
                log_index += 1

        return {
            "t": t_l[:log_index],
            "G": G_l[:log_index],
            "q_h": q_h_l[:, :log_index],
            "q_t": q_t_l[:, :log_index],
            "Z_d": Z_d_l[:, :log_index],
            "B_h": B_h_l[:, :log_index],
            "B_t": B_t_l[:, :log_index],
            "B_d": (B_t_l - B_h_l)[:, :log_index],
            "s": s_l[:, :log_index],
            "w_h": w_h_l[:, :log_index],
            "w_t": w_t_l[:, :log_index],
            "h": h_l[:, :log_index],
            "L": L_l[:, :log_index],
        }

    # endregion




        

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



