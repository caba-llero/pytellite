"""
Satellite Plant Simulator

This module simulates the physical behavior of a satellite in orbit, including:
- Orbital dynamics (position and velocity in Earth-Centered Inertial frame)
- Attitude dynamics (orientation using quaternions)
- Sensor modeling (GPS and gyro with realistic noise)
- Real-time simulation with configurable time scaling
- UDP communication with flight software
- Data logging for replay and analysis

The simulator runs in a Software-in-the-Loop (SIL) configuration where it provides
realistic sensor data to flight software and receives actuator commands.
"""

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
    """Load simulation configuration from YAML file.

    Args:
        path: Path to the YAML configuration file

    Returns:
        Dictionary containing all simulation parameters
    """
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def run(config_path: str):
    """Main simulation function that runs the satellite plant simulator.

    This function:
    1. Loads and parses configuration
    2. Initializes simulation components (dynamics, sensors, comms)
    3. Runs the main simulation loop with real-time pacing
    4. Handles sensor data generation and communication
    5. Logs all data for replay analysis

    Args:
        config_path: Path to YAML configuration file
    """
    cfg = load_config(config_path)

    # =============================================================================
    # SIMULATION SETUP
    # =============================================================================

    # Extract simulation timing parameters
    dt_sim = float(cfg["simulation"]["dt_sim"])  # [s] - simulation time step
    time_scale = float(cfg["simulation"]["time_scale"])  # sim seconds per real second
    rng_seed = int(cfg["simulation"]["rng_seed"])

    # =============================================================================
    # COMMUNICATION SETUP
    # =============================================================================

    # UDP ports for Software-in-the-Loop (SIL) communication with flight software
    udp_send_port = int(cfg["comms"]["udp"]["plant_to_flight_port"])  # 10001 - sensor data to flight
    udp_recv_port = int(cfg["comms"]["udp"]["flight_to_plant_port"])  # 10002 - actuator commands from flight

    # =============================================================================
    # LOGGING SETUP
    # =============================================================================

    # Create replay log directory and initialize logging
    replay_file = cfg["logging"]["replay_file"]  # Get full path to log file from config
    Path(Path(replay_file).parent).mkdir(parents=True, exist_ok=True) # create the directory for the log file

    # Load and validate message schemas for communication protocol
    schemas = load_protocol_schemas("docs/protocol_schema.json")
    schema_registry = SchemaRegistry(schemas)

    # Initialize UDP communication socket (non-blocking for real-time operation)
    udp = NDJSONUDPSocket("127.0.0.1", udp_send_port, udp_recv_port, recv_timeout=0.0)

    # Initialize deterministic random number generator for reproducible results
    rng = DeterministicRNG(rng_seed)

    # =============================================================================
    # SENSOR CONFIGURATION
    # =============================================================================

    # Configure GPS sensor with realistic noise characteristics
    gps_cfg = GPSSensorConfig(
        rate_hz=float(cfg["sensors"]["gps"]["rate_hz"]),              # GPS measurement rate [Hz]
        sigma_pos_m=float(cfg["sensors"]["gps"]["sigma_pos_m"]),      # Position noise standard deviation [m]
        sigma_vel_mps=float(cfg["sensors"]["gps"]["sigma_vel_mps"]),  # Velocity noise standard deviation [m/s]
    )

    # Configure gyro sensor with realistic noise and bias characteristics
    gyro_cfg = GyroSensorConfig(
        rate_hz=float(cfg["sensors"]["gyro"]["rate_hz"]),             # Gyro measurement rate [Hz]
        sigma_radps=float(cfg["sensors"]["gyro"]["sigma_radps"]),    # Angular rate noise [rad/s]
        bias_rw_sigma=float(cfg["sensors"]["gyro"].get("bias_rw_sigma", 0.0)) or None,  # Bias random walk [rad/s/√Hz]
    )

    # Create sensor synthesizer objects that generate realistic sensor measurements
    gps = GPSSynthesizer(gps_cfg, rng)    # GPS position and velocity measurements
    gyro = GyroSynthesizer(gyro_cfg, rng) # Gyro angular rate measurements

    # =============================================================================
    # INITIAL CONDITIONS SETUP
    # =============================================================================

    # Load initial orbital state (Earth-Centered Inertial frame)
    r0 = np.array(cfg["initial_conditions"]["r_eci_m"], dtype=float)       # Initial position [m]
    v0 = np.array(cfg["initial_conditions"]["v_eci_mps"], dtype=float)     # Initial velocity [m/s]

    # Load initial attitude state (body-to-inertial quaternion)
    q_bi = np.array(cfg["initial_conditions"].get("q_bi", [0, 0, 0, 1]), dtype=float)  # Body-to-inertial quaternion
    omega_b = np.array(cfg["initial_conditions"].get("omega_b_radps", [0, 0, 0]), dtype=float)  # Body angular velocity [rad/s]

    # Create working copies of state vectors (these will be updated during simulation; keep original values for reference)
    r_eci = r0.copy()    # Current position in ECI frame [m]
    v_eci = v0.copy()    # Current velocity in ECI frame [m/s]

    # =============================================================================
    # SIMULATION TIME INITIALIZATION
    # =============================================================================

    t_sim = 0.0                          # Current simulation time [s]
    sim_epoch_wall = time.perf_counter() # Wall clock time when simulation started
    last_wall = sim_epoch_wall          # Previous wall clock time (for time management)

    # =============================================================================
    # MAIN SIMULATION LOOP
    # =============================================================================

    # Open replay log file for recording all simulation data
    with open(replay_file, "w", encoding="utf-8") as replay_f:
        # Run simulation until final time is reached
        while t_sim <= float(cfg["simulation"].get("t_final", 60.0)):

            # =====================================================================
            # DYNAMICS INTEGRATION
            # =====================================================================

            # Update orbital state using 4th-order Runge-Kutta integration
            # This simulates two-body orbital mechanics (Earth's gravity only)
            r_eci, v_eci = rk4_step_orbit(r_eci, v_eci, dt_sim)

            # Update attitude state using 4th-order Runge-Kutta integration
            # This simulates rigid body rotational dynamics
            q_bi = integrate_attitude_rk4(q_bi, omega_b, dt_sim)

            # =====================================================================
            # SENSOR DATA GENERATION AND TRANSMISSION
            # =====================================================================

            # Generate GPS measurements (position and velocity) with realistic noise
            # GPS has lower update rate but provides absolute position reference
            gps_msg = gps.maybe_emit(t_sim, r_eci, v_eci)
            if gps_msg is not None:
                # Validate message against protocol schema before transmission
                schema_registry.validate_sensor(gps_msg)
                # Send GPS data to flight software via UDP
                udp.send_json(gps_msg)
                # Log outgoing GPS message for replay analysis
                replay_f.write(json.dumps({"direction": "out", "frame": gps_msg}) + "\n")

            # Generate gyro measurements (angular rates) with realistic noise and bias
            # Gyro has higher update rate but provides relative angular measurements
            gyro_msg = gyro.maybe_emit(t_sim, omega_b)
            if gyro_msg is not None:
                # Validate message against protocol schema before transmission
                schema_registry.validate_sensor(gyro_msg)
                # Send gyro data to flight software via UDP
                udp.send_json(gyro_msg)
                # Log outgoing gyro message for replay analysis
                replay_f.write(json.dumps({"direction": "out", "frame": gyro_msg}) + "\n")

            # =====================================================================
            # ACTUATOR COMMAND RECEPTION
            # =====================================================================

            # Check for incoming actuator commands from flight software (non-blocking)
            # In a full implementation, these would affect satellite attitude via omega_b
            incoming = udp.try_recv_json()
            if incoming is not None:
                # Log incoming actuator command for replay analysis
                # Note: Actuator commands are not yet implemented in this MVP
                replay_f.write(json.dumps({"direction": "in", "frame": incoming, "t_sim": t_sim}) + "\n")

            # =====================================================================
            # TIME MANAGEMENT
            # =====================================================================

            # Advance simulation time by one time step
            t_sim += dt_sim

            # =====================================================================
            # REAL-TIME PACING
            # =====================================================================

            # Maintain real-time pacing by sleeping to match simulation time scale
            # This ensures the simulation runs at the desired speed relative to wall clock time
            target_wall = sim_epoch_wall + t_sim / max(time_scale, 1e-9)  # Target wall time for current sim time
            now = time.perf_counter()                                    # Current wall time
            sleep_time = target_wall - now                              # Time to sleep
            if sleep_time > 0:
                # Sleep but cap at 0.1s to maintain responsiveness
                time.sleep(min(sleep_time, 0.1))


# =============================================================================
# COMMAND-LINE INTERFACE
# =============================================================================

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

    # Start the simulation with the provided configuration
    run(args.config)


# =============================================================================
# SCRIPT EXECUTION
# =============================================================================

if __name__ == "__main__":
    main()



