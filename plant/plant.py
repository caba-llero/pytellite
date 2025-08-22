from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np
import yaml

from .dynamics import rk4_step_orbit, integrate_attitude_rk4
from .sensors import GPSSensorConfig, GyroSensorConfig, DeterministicRNG, GPSSynthesizer, GyroSynthesizer
from .utils import NDJSONUDPSocket, load_protocol_schemas, SchemaRegistry


def load_config(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def run(config_path: str):
    cfg = load_config(config_path)

    dt_sim = float(cfg["simulation"]["dt_sim"])  # [s]
    time_scale = float(cfg["simulation"]["time_scale"])  # sim seconds per real second
    rng_seed = int(cfg["simulation"]["rng_seed"])

    udp_send_port = int(cfg["comms"]["udp"]["plant_to_flight_port"])  # 10001
    udp_recv_port = int(cfg["comms"]["udp"]["flight_to_plant_port"])  # 10002

    replay_file = cfg["logging"]["replay_file"]
    Path(Path(replay_file).parent).mkdir(parents=True, exist_ok=True)

    schemas = load_protocol_schemas("docs/protocol_schema.json")
    schema_registry = SchemaRegistry(schemas)

    udp = NDJSONUDPSocket("127.0.0.1", udp_send_port, udp_recv_port, recv_timeout=0.0)

    rng = DeterministicRNG(rng_seed)

    gps_cfg = GPSSensorConfig(
        rate_hz=float(cfg["sensors"]["gps"]["rate_hz"]),
        sigma_pos_m=float(cfg["sensors"]["gps"]["sigma_pos_m"]),
        sigma_vel_mps=float(cfg["sensors"]["gps"]["sigma_vel_mps"]),
    )
    gyro_cfg = GyroSensorConfig(
        rate_hz=float(cfg["sensors"]["gyro"]["rate_hz"]),
        sigma_radps=float(cfg["sensors"]["gyro"]["sigma_radps"]),
        bias_rw_sigma=float(cfg["sensors"]["gyro"].get("bias_rw_sigma", 0.0)) or None,
    )

    gps = GPSSynthesizer(gps_cfg, rng)
    gyro = GyroSynthesizer(gyro_cfg, rng)

    # Initial conditions: simple circular LEO if not provided
    r0 = np.array(cfg["initial_conditions"]["r_eci_m"], dtype=float)
    v0 = np.array(cfg["initial_conditions"]["v_eci_mps"], dtype=float)
    q_bi = np.array(cfg["initial_conditions"].get("q_bi", [0, 0, 0, 1]), dtype=float)
    omega_b = np.array(cfg["initial_conditions"].get("omega_b_radps", [0, 0, 0]), dtype=float)

    r_eci = r0.copy()
    v_eci = v0.copy()

    t_sim = 0.0
    sim_epoch_wall = time.perf_counter()
    last_wall = sim_epoch_wall

    with open(replay_file, "w", encoding="utf-8") as replay_f:
        while t_sim <= float(cfg["simulation"].get("t_final", 60.0)):
            # Integrate orbit and attitude
            r_eci, v_eci = rk4_step_orbit(r_eci, v_eci, dt_sim)
            q_bi = integrate_attitude_rk4(q_bi, omega_b, dt_sim)

            # Sensors
            gps_msg = gps.maybe_emit(t_sim, r_eci, v_eci)
            if gps_msg is not None:
                schema_registry.validate_sensor(gps_msg)
                udp.send_json(gps_msg)
                replay_f.write(json.dumps({"direction": "out", "frame": gps_msg}) + "\n")

            gyro_msg = gyro.maybe_emit(t_sim, omega_b)
            if gyro_msg is not None:
                schema_registry.validate_sensor(gyro_msg)
                udp.send_json(gyro_msg)
                replay_f.write(json.dumps({"direction": "out", "frame": gyro_msg}) + "\n")

            # Receive actuator if any
            incoming = udp.try_recv_json()
            if incoming is not None:
                replay_f.write(json.dumps({"direction": "in", "frame": incoming, "t_sim": t_sim}) + "\n")

            # Advance time
            t_sim += dt_sim

            # Real-time pacing
            target_wall = sim_epoch_wall + t_sim / max(time_scale, 1e-9)
            now = time.perf_counter()
            sleep_time = target_wall - now
            if sleep_time > 0:
                time.sleep(min(sleep_time, 0.1))


def main():
    parser = argparse.ArgumentParser(description="Satellite Plant Simulator (MVP)")
    parser.add_argument("--config", type=str, default="plant/config_default.yaml", help="Path to YAML config")
    args = parser.parse_args()
    run(args.config)


if __name__ == "__main__":
    main()



