from astropy.time import Time

# Under construction

def get_sid_time(input_time: str) -> float:
    t = Time(input_time, scale="utc")
    theta = t.sidereal_time('mean', 'greenwich')
    return theta.deg

def earth_spin_rate_radps(input_time: str) -> float:
    theta_dot = 7.2921151e-5
    return theta_dot
