import numpy as np

from plant.dynamics import rk4_step_orbit, MU_EARTH, quaternion_normalize, quaternion_multiply, integrate_attitude_rk4


def specific_orbital_energy(r, v, mu=MU_EARTH):
    rnorm = np.linalg.norm(r)
    return 0.5 * np.dot(v, v) - mu / rnorm


def test_two_body_energy_conservation_short_run():
    r = np.array([6871e3, 0.0, 0.0])
    v = np.array([0.0, 7610.0, 0.0])
    e0 = specific_orbital_energy(r, v)
    dt = 0.5
    for _ in range(200):
        r, v = rk4_step_orbit(r, v, dt)
    e1 = specific_orbital_energy(r, v)
    rel_err = abs((e1 - e0) / e0)
    assert rel_err < 1e-6


def test_attitude_integration_constant_rate():
    q = np.array([0.0, 0.0, 0.0, 1.0])
    w = np.array([0.01, 0.0, 0.0])
    dt = 0.1
    for _ in range(100):
        q = integrate_attitude_rk4(q, w, dt)
        print(q)
    assert np.isclose(np.linalg.norm(q), 1.0)



