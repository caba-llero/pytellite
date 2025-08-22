import json
from pathlib import Path

import numpy as np

from plant.sensors import DeterministicRNG, GPSSensorConfig, GyroSensorConfig, GPSSynthesizer, GyroSynthesizer
from plant.utils import load_protocol_schemas, SchemaRegistry


def test_deterministic_rng_repeatability():
    seed = 42
    rng1 = DeterministicRNG(seed)
    rng2 = DeterministicRNG(seed)
    a = rng1.normal(0.0, 1.0, 5)
    b = rng2.normal(0.0, 1.0, 5)
    assert np.allclose(a, b)


def test_message_schema_validation(tmp_path):
    schemas = load_protocol_schemas("docs/protocol_schema.json")
    reg = SchemaRegistry(schemas)

    rng = DeterministicRNG(1)
    gps = GPSSynthesizer(GPSSensorConfig(rate_hz=1.0, sigma_pos_m=1.0, sigma_vel_mps=0.1), rng)
    gyro = GyroSynthesizer(GyroSensorConfig(rate_hz=100.0, sigma_radps=0.001, bias_rw_sigma=0.0), rng)

    r = np.zeros(3)
    v = np.zeros(3)
    w = np.zeros(3)

    gps_msg = gps.maybe_emit(0.0, r, v)
    gyro_msg = gyro.maybe_emit(0.0, w)

    reg.validate_sensor(gps_msg)
    reg.validate_sensor(gyro_msg)




