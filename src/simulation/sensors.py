from __future__ import annotations

import time
import json
from dataclasses import dataclass
from typing import Optional, Tuple

import numpy as np


@dataclass
class GPSSensorConfig:
    rate_hz: float
    sigma_pos_m: float
    sigma_vel_mps: float


@dataclass
class GyroSensorConfig:
    rate_hz: float
    sigma_radps: float
    bias_rw_sigma: Optional[float] = None


class DeterministicRNG:
    def __init__(self, seed: int):
        self.rng = np.random.default_rng(seed)

    def normal(self, mean: float, sigma: float, size: Tuple[int, ...] | int) -> np.ndarray:
        return self.rng.normal(loc=mean, scale=sigma, size=size)


class GPSSynthesizer:
    def __init__(self, cfg: GPSSensorConfig, rng: DeterministicRNG):
        self.cfg = cfg
        self.rng = rng
        self._next_emit = 0.0
        self.seq = 0

    def maybe_emit(self, t_sim: float, r_eci: np.ndarray, v_eci: np.ndarray) -> Optional[dict]:
        if t_sim + 1e-9 < self._next_emit:
            return None
        self._next_emit = t_sim + 1.0 / self.cfg.rate_hz
        self.seq += 1

        r_noisy = r_eci + self.rng.normal(0.0, self.cfg.sigma_pos_m, 3)
        v_noisy = v_eci + self.rng.normal(0.0, self.cfg.sigma_vel_mps, 3)
        msg = {
            "type": "sensor",
            "protocol_version": "1.0",
            "schema_version": "gps-v1",
            "sensor": "gps",
            "t_sim": float(t_sim),
            # For determinism in logs, omit wall-clock timestamp in MVP
            "t_sent": None,
            "seq": self.seq,
            "payload": {
                "r_eci": [float(x) for x in r_noisy],
                "v_eci": [float(x) for x in v_noisy],
            },
        }
        return msg


class GyroSynthesizer:
    def __init__(self, cfg: GyroSensorConfig, rng: DeterministicRNG):
        self.cfg = cfg
        self.rng = rng
        self._next_emit = 0.0
        self.seq = 0
        self.bias = np.zeros(3)

    def step_bias(self):
        if self.cfg.bias_rw_sigma is not None and self.cfg.bias_rw_sigma > 0:
            self.bias += self.rng.normal(0.0, self.cfg.bias_rw_sigma, 3)

    def maybe_emit(self, t_sim: float, omega_body_true: np.ndarray) -> Optional[dict]:
        if t_sim + 1e-9 < self._next_emit:
            return None
        self._next_emit = t_sim + 1.0 / self.cfg.rate_hz
        self.seq += 1
        self.step_bias()

        noise = self.rng.normal(0.0, self.cfg.sigma_radps, 3)
        omega_meas = omega_body_true + self.bias + noise
        msg = {
            "type": "sensor",
            "protocol_version": "1.0",
            "schema_version": "gyro-v1",
            "sensor": "gyro",
            "t_sim": float(t_sim),
            "t_sent": None,
            "seq": self.seq,
            "payload": {
                "omega_body": [float(x) for x in omega_meas],
            },
        }
        return msg


