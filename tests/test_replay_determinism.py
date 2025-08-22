import json
import os
import shutil
import subprocess
import sys
from pathlib import Path


def run_plant_and_capture(tmp_dir: Path):
    cfg_path = tmp_dir / "config.yaml"
    logs_dir = tmp_dir / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    replay_path = logs_dir / "replay.ndjson"

    cfg = {
        "simulation": {
            "dt_sim": 0.01,
            "time_scale": 1e9,  # essentially no sleep in tests
            "mode": "SIL",
            "rng_seed": 123,
            "t_final": 0.2,
        },
        "spacecraft": {"mass": 10.0, "inertia": [0.1, 0.1, 0.1], "shape": [0.1, 0.1, 0.3]},
        "sensors": {
            "gps": {"rate_hz": 10.0, "sigma_pos_m": 0.0, "sigma_vel_mps": 0.0},
            "gyro": {"rate_hz": 200.0, "sigma_radps": 0.0, "bias_rw_sigma": 0.0},
        },
        "actuators": {"reaction_wheels": {"max_torque": 0.01, "max_speed_rpm": 6000, "inertia": 0.001}},
        "perturbations": {"two_body": True, "j2": False, "sun_moon": False, "srp": False, "drag": False},
        "comms": {"protocol": "udp", "udp": {"plant_to_flight_port": 11001, "flight_to_plant_port": 11002}},
        "watchdog": {"timeout_sec": 1.0},
        "logging": {"replay_file": str(replay_path)},
        "initial_conditions": {
            "r_eci_m": [6871000.0, 0.0, 0.0],
            "v_eci_mps": [0.0, 7610.0, 0.0],
            "q_bi": [0.0, 0.0, 0.0, 1.0],
            "omega_b_radps": [0.0, 0.0, 0.0],
        },
    }

    cfg_path.write_text(json.dumps(cfg), encoding="utf-8")

    # Run as module to ensure local import works
    subprocess.check_call([sys.executable, "-m", "plant.plant", "--config", str(cfg_path)])
    return replay_path.read_text(encoding="utf-8")


def test_replay_identical_runs(tmp_path):
    run1 = run_plant_and_capture(tmp_path / "run1")
    run2 = run_plant_and_capture(tmp_path / "run2")
    assert run1 == run2




