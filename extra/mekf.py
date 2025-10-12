import numpy as np
import matplotlib.pyplot as plt
import utils as u


class MEKF:
    """
    Class wrapper around MEKF implementation.
    """

    def __init__(self, inputs: dict | None = None) -> None:
        if inputs is None:
            inputs = {}

        # Constants
        self.I3 = np.eye(3)
        self.O3 = np.zeros((3, 3))
        self.pi = np.pi
        self.arcsec_to_rad = self.pi / (180 * 3600)
        self.degh_to_rads = self.pi / (180 * 3600)

        # Simulation and sensor parameters (defaults taken from ekf.py)
        self.t_max = inputs.get("t_max", 1000)
        self.dt = inputs.get("dt", 0.01)
        self.sigma_startracker = inputs.get("sigma_startracker", 6)
        self.sigma_v = inputs.get("sigma_v", (10 ** 0.5) * 1e-6)
        self.sigma_u = inputs.get("sigma_u", (10 ** 0.5) * 1e-9)
        self.freq_startracker = inputs.get("freq_startracker", 1)
        self.freq_gyro = inputs.get("freq_gyro", 20)
        self.init_inaccuracy = inputs.get("init_inaccuracy", 30)
        self.rng_seed = inputs.get("rng_seed", 1)

        # Algorithm switches
        self.Joseph = inputs.get("Joseph", True)
        self.simple_Phi = inputs.get("simple_Phi", False)

        # Initial estimate covariances and bias
        self.B_h_0 = np.asarray(inputs.get("B_h_0", np.array([0, 0, 0])), dtype=float)
        self.Pq = np.asarray(
            inputs.get(
                "Pq",
                (self.init_inaccuracy * self.arcsec_to_rad) ** 2 * self.I3,
            ),
            dtype=float,
        )
        self.Pb = np.asarray(
            inputs.get("Pb", (0.2 * self.degh_to_rads) ** 2 * self.I3), dtype=float
        )

        # Ground-truth initial conditions
        self.B_t_0 = np.asarray(
            inputs.get(
                "B_t_0", np.array([0.1, 0.1, 0.1]) * self.degh_to_rads
            ),
            dtype=float,
        )
        self.q_t_0 = np.asarray(
            inputs.get("q_t_0", np.array([1, 0, 0, 1]) / 2 ** 0.5), dtype=float
        )

        # Optional custom truth-rate function
        self.w_t_fun = inputs.get("w_t_fun", self._default_w_t_fun)

        # Results container (populated by calculate)
        self.results: dict | None = None

    # --- Defaults ---------------------------------------------------------
    def _default_w_t_fun(self, t: np.ndarray) -> np.ndarray:
        w1 = 0.1 * np.sin(0.01 * t) * self.pi / 180
        w2 = 0.1 * np.sin(0.0085 * t) * self.pi / 180
        w3 = 0.1 * np.cos(0.0085 * t) * self.pi / 180
        return np.vstack((w1, w2, w3))

    # --- Core computation --------------------------------------------------
    def calculate(self) -> dict:
        """
        Run the MEKF simulation and return a dictionary with logs and results.
        The same information is also stored on self.results.
        """
        I3 = self.I3
        O3 = self.O3
        arcsec_to_rad = self.arcsec_to_rad

        # Measurement model matrices
        H = np.hstack((I3, O3))
        R = I3 * (self.sigma_startracker * arcsec_to_rad) ** 2

        # Truth time grid and measurement indices
        times = np.arange(0, self.t_max, self.dt)
        idx_gyro = u.measurement_indices(self.t_max, self.dt, self.freq_gyro)
        idx_star = u.measurement_indices(self.t_max, self.dt, self.freq_startracker)
        idx_all = idx_gyro | idx_star
        timesteps = len(idx_all)

        n = 3
        w_t_l = self.w_t_fun(times)
        np.random.seed(self.rng_seed)

        # Initial attitude estimate from a noisy measurement
        Z_n = np.random.normal(
            0, self.sigma_startracker * arcsec_to_rad * self.init_inaccuracy, n
        ).reshape(-1, 1)
        q_m_0 = self.q_t_0.reshape(-1, 1) + 0.5 * u.Xi(self.q_t_0) @ Z_n
        q_m_0 = q_m_0.flatten() / np.linalg.norm(q_m_0)
        q_h_0 = q_m_0

        # Allocate logs
        s_l = np.empty((6, timesteps))
        q_h_l = np.empty((4, timesteps))
        B_h_l = np.empty((3, timesteps))
        q_t_l = np.empty((4, timesteps))
        Z_d_l = np.empty((3, timesteps))
        B_t_l = np.empty((3, timesteps))
        t_l = np.empty(timesteps)
        G_l = np.empty(timesteps)

        # Initial states
        q_t = self.q_t_0.copy()
        B_t = self.B_t_0.copy()
        B_h = self.B_h_0.copy()
        q_h = q_h_0.copy()
        q_d = u.quat_mul(q_t, u.quat_inv(q_h))
        Z_d = u.quat_to_rotvec(q_d)
        G = np.linalg.norm(Z_d)
        P = np.block([[self.Pq, O3], [O3, self.Pb]])

        # Optional initial log at t=0
        k = 0
        if 0 in idx_all and k < timesteps:
            s = np.sqrt(np.diag(P))
            s_l[:, k] = s
            t_l[k] = times[0]
            q_h_l[:, k] = q_h
            q_t_l[:, k] = q_t
            Z_d_l[:, k] = Z_d
            B_h_l[:, k] = B_h.flatten()
            B_t_l[:, k] = B_t
            k += 1

        last_gyro_i = 0
        for i in range(1, len(times)):
            # Propagate ground truth
            w_t = w_t_l[:, i - 1]
            q_t = u.quat_propagate(q_t, w_t, self.dt)
            B_t = B_t + np.random.normal(0, self.sigma_u * self.dt**0.5, n)

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
        return self.results

    # --- Plotting helpers --------------------------------------------------
    def _require_results(self) -> dict:
        if self.results is None:
            raise RuntimeError("No results found. Call calculate() first.")
        return self.results

    def plot_pointing_error(self) -> None:
        r = self._require_results()
        plt.figure(figsize=(10, 6))
        plt.plot(r["t"], r["G"]) 
        plt.title("Total pointing error")
        plt.ylabel("Error (rad)")
        plt.xlabel("Time (s)")
        plt.grid(True)

    def plot_bias(self) -> None:
        r = self._require_results()
        plt.figure(figsize=(10, 6))
        plt.plot(r["t"], r["B_t"][0, :])
        plt.plot(r["t"], r["B_h"][0, :])
        plt.title("Bias and Estimated Bias (X component)")
        plt.ylabel("Bias (rad/s)")
        plt.xlabel("Time (s)")
        plt.grid(True)

    def plot_attitude(self) -> None:
        r = self._require_results()
        fig, axs = plt.subplots(2, 2, figsize=(18, 10), sharex=True)
        axs[0, 0].plot(r["t"], r["q_t"][0, :])
        axs[0, 0].plot(r["t"], r["q_h"][0, :])
        axs[0, 1].plot(r["t"], r["q_t"][1, :])
        axs[0, 1].plot(r["t"], r["q_h"][1, :])
        axs[1, 0].plot(r["t"], r["q_t"][2, :])
        axs[1, 0].plot(r["t"], r["q_h"][2, :])
        axs[1, 1].plot(r["t"], r["q_t"][3, :])
        axs[1, 1].plot(r["t"], r["q_h"][3, :])
        axs[0, 0].set_title("X-component")
        axs[0, 1].set_title("Y-component")
        axs[1, 0].set_title("Z-component")
        axs[1, 1].set_title("W-component")
        for i in range(2):
            for j in range(2):
                axs[i, j].set_ylabel("Attitude (rad)")
                axs[i, j].legend(loc="upper right")
                axs[i, j].set_xlabel("Time (s)")
                axs[i, j].grid(True)
        plt.tight_layout()

    def plot_errors_with_bounds(self) -> None:
        r = self._require_results()
        fig, axs = plt.subplots(2, 3, figsize=(18, 10), sharex=True)
        fig.suptitle(
            "Attitude and gyro bias estimation errors with 3-sigma bounds",
            fontsize=16,
        )
        component = ["X", "Y", "Z"]
        for i in range(3):
            ax = axs[0, i]
            ax.plot(r["t"], r["Z_d"][i, :], "b", label=f"Error Axis {i+1}")
            ax.plot(r["t"], 3 * r["s"][i, :], "r--", label="3-sigma")
            ax.plot(r["t"], -3 * r["s"][i, :], "r--")
            ax.set_title(f"Attitude error - Component {component[i]}")
            ax.set_ylabel("Error (rad)")
            ax.grid(True)
            ax.legend()
        
        for i in range(3):
            ax = axs[1, i]
            ax.plot(r["t"], r["B_d"][i, :], "b", label=f"Error Axis {i+1}")
            ax.plot(r["t"], 3 * r["s"][i + 3, :], "r--", label="3-sigma")
            ax.plot(r["t"], -3 * r["s"][i + 3, :], "r--")
            ax.set_title(f"Gyro bias error - Component {component[i]}")
            ax.set_ylabel("Error (rad/s)")
            ax.grid(True)
            ax.legend()

        for ax in axs.flat:
            ax.set_xlabel("Time (s)")
        plt.tight_layout(rect=[0, 0.03, 1, 0.95])

    def plot_all(self) -> None:
        self.plot_pointing_error()
        self.plot_bias()
        self.plot_attitude()
        self.plot_errors_with_bounds()
        plt.show()

if __name__ == "__main__":
    mekf = MEKF()
    mekf.calculate()
    mekf.plot_all()
