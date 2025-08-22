# Conventions

## Frames and Orientation
- Body frame: spacecraft-fixed, principle inertia axes. 
- Inertial frame: ECI (J2000). X-axis: vernal equinox; Z-axis: Earth's rotation axis at J2000; Y-axis: completes right hand system
- Attitude quaternion: `q_bi = [q1, q2, q3, q4]` (scalar-last, like Markley), represents rotation from body to inertial
- Angular velocity `omega_b`: expressed in the body frame.

## Units
- SI throughout: meters, kilograms, seconds, Newtons, Newton-meters, radians, rad/s.

## Timestamps
- Canonical simulation time `t_sim` is seconds since simulation epoch (defined by the Plant). In SIL, Plant is authoritative (flight controller and UI follow this clock).
- (For later): We will include additonal timestamps to compute the latency (might be useful for the control law?).Packets may include `t_sent` and receivers may add `t_recv`.

## Quaternions
- Normalize after integration steps.
- Composition uses Markley convention: q_a (x) q_b corresponds to rotating thru q_a first and then q_b

## Message Protocol
- Newline-delimited JSON (NDJSON) over UDP for SIL.
- Every message includes `protocol_version` (communication rules) and `schema_version` (data structure type that is sent).
- Schemas are validated using JSON Schema in the Plant and later in Flight software.


