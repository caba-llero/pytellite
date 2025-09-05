import asyncio
import json
import os
import time
import logging
import traceback
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Response, Body
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from src.simulation.simulation import Plant
from src.simulation.orbit import get_sid_time, earth_spin_rate_radps
from datetime import datetime, timezone
import math
import numpy as np
import yaml
import glob

router = APIRouter()

# Ensure logs directory exists
os.makedirs("logs", exist_ok=True)

STATIC_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "webapp")
TEXTURES_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "textures")

def_static_files = StaticFiles(directory=STATIC_DIR, html=True)
def_textures_files = StaticFiles(directory=TEXTURES_DIR, html=False)

@router.get("/")
async def serve_config():
    return FileResponse(os.path.join(STATIC_DIR, "config.html"))

@router.get("/simulation")
async def serve_index():
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))

@router.get("/loading")
async def serve_loading():
    return FileResponse(os.path.join(STATIC_DIR, "loading.html"))

@router.head("/")
async def serve_index_head():
    return Response(status_code=200)

@router.get("/logo.png")
async def serve_logo():
    return FileResponse(os.path.join(os.path.dirname(__file__), "..", "..", "logo.png"))

# Favicons and manifest at root
@router.get("/apple-touch-icon.png")
async def serve_apple_touch():
    return FileResponse(os.path.join(os.path.dirname(__file__), "..", "..", "apple-touch-icon.png"))

@router.get("/favicon-32x32.png")
async def serve_favicon_32():
    return FileResponse(os.path.join(os.path.dirname(__file__), "..", "..", "favicon-32x32.png"))

@router.get("/favicon-16x16.png")
async def serve_favicon_16():
    return FileResponse(os.path.join(os.path.dirname(__file__), "..", "..", "favicon-16x16.png"))

@router.get("/site.webmanifest")
async def serve_manifest():
    return FileResponse(os.path.join(os.path.dirname(__file__), "..", "..", "site.webmanifest"))

@router.get("/healthz")
async def healthz():
    return {"status": "ok"}


def _load_defaults() -> dict:
    # Prefer Markley preset as default; fall back to intermediate axis preset, then legacy
    cfg_dir = os.path.join(os.path.dirname(__file__), "..", "..", "configs")
    root_markley = os.path.join(cfg_dir, "config_markley_7_1.yaml")
    root_intermediate = os.path.join(cfg_dir, "config_intermediateaxis.yaml")
    
    if os.path.exists(root_markley):
        config_path = root_markley
    elif os.path.exists(root_intermediate):
        config_path = root_intermediate
    else:
        # As a last resort, look for any yaml file in the configs directory
        yaml_files = glob.glob(os.path.join(cfg_dir, "*.yaml"))
        if yaml_files:
            config_path = yaml_files[0]
        else:
            raise FileNotFoundError("No configuration file found in the 'configs' directory.")

    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


@router.get("/api/defaults")
async def api_defaults():
    cfg = _load_defaults()
    return {
        "spacecraft": {
            "inertia": cfg["spacecraft"]["inertia"],
            "shape": cfg["spacecraft"]["shape"],
        },
        "initial_conditions": {
            "q_bi": cfg["initial_conditions"]["q_bi"],
            "omega_bi_radps": cfg["initial_conditions"]["omega_bi_radps"],
            "orbit": cfg["initial_conditions"].get("orbit", {}),
        },
        "simulation": {
            "dt_sim": cfg["simulation"]["dt_sim"],
            "t_max": cfg["simulation"].get("t_max", 1000.0),
            "playback_speed": cfg["simulation"].get("playback_speed", 1.0),
            "sample_rate": cfg["simulation"].get("sample_rate", 30.0),
            "rtol": cfg["simulation"].get("rtol", 1.0e-12),
            "atol": cfg["simulation"].get("atol", 1.0e-12),
        },
        "control": {
            "control_type": cfg.get("control", {}).get("control_type", "none"),
            "kp": cfg.get("control", {}).get("kp", 0.0),
            "kd": cfg.get("control", {}).get("kd", 0.0),
            "qc": cfg.get("control", {}).get("qc", [0.0, 0.0, 0.0, 1.0]),
        },
    }

@router.get("/api/presets")
async def api_presets():
    cfg_dir = os.path.join(os.path.dirname(__file__), "..", "..", "configs")
    presets = []
    for path in sorted(glob.glob(os.path.join(cfg_dir, "*.yaml"))):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            name = data.get("name") or os.path.basename(path)
            presets.append({
                "name": name,
                "file": os.path.basename(path)
            })
        except Exception:
            continue
    return {"presets": presets}

@router.get("/api/presets/{filename}")
async def api_preset_file(filename: str):
    # sanitize filename
    base = os.path.basename(filename)
    if not base.endswith('.yaml'):
        return {"error": "invalid preset filename"}
    cfg_dir = os.path.join(os.path.dirname(__file__), "..", "..", "configs")
    path = os.path.join(cfg_dir, base)
    if not os.path.exists(path):
        return {"error": "preset not found"}
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data


def merge_with_defaults(payload: dict) -> dict:
    cfg = _load_defaults()
    inertia = payload.get("inertia")
    shape = payload.get("shape")
    q_bi = payload.get("q_bi")
    omega_bi_radps = payload.get("omega_bi_radps")
    dt_sim = payload.get("dt_sim")
    t_max = payload.get("t_max")
    playback_speed = payload.get("playback_speed")
    sample_rate = payload.get("sample_rate")
    rtol = payload.get("rtol")
    atol = payload.get("atol")
    if inertia is not None:
        cfg["spacecraft"]["inertia"] = inertia
    if shape is not None:
        cfg["spacecraft"]["shape"] = shape
    if q_bi is not None:
        cfg["initial_conditions"]["frame"] = "inertial"
        cfg["initial_conditions"]["q_bi"] = q_bi
    if omega_bi_radps is not None:
        cfg["initial_conditions"]["omega_bi_radps"] = omega_bi_radps
    if dt_sim is not None:
        cfg["simulation"]["dt_sim"] = dt_sim
    if t_max is not None:
        cfg["simulation"]["t_max"] = t_max
    if playback_speed is not None:
        cfg["simulation"]["playback_speed"] = playback_speed
    if sample_rate is not None:
        cfg["simulation"]["sample_rate"] = sample_rate
    if rtol is not None:
        cfg["simulation"]["rtol"] = rtol
    if atol is not None:
        cfg["simulation"]["atol"] = atol

    # Control parameters (flat or nested)
    ctrl_payload = payload.get("control", {}) if isinstance(payload.get("control"), dict) else payload
    
    control_type = ctrl_payload.get("control_type") or ctrl_payload.get("ctrl")
    kp = ctrl_payload.get("kp")
    kd = ctrl_payload.get("kd")
    qc = ctrl_payload.get("qc")

    # Normalize control_type to internal identifiers used by dynamics
    if control_type is not None:
        # Accept values: none | zero_torque | inertial | tracking | inertial_linear | inertial_nonlinear | nonlinear_tracking
        ct = str(control_type).lower().strip()
        if ct in ("none", "zero_torque"):
            mapped = 0
        elif ct in ("inertial_nonlinear", "nonlinear_tracking"):
            mapped = 2
        elif ct in ("inertial", "inertial_linear", "tracking"):
            mapped = 1
        else:
            mapped = 0
        cfg["control"] = cfg.get("control", {})
        cfg["control"]["control_type"] = mapped
    if kp is not None:
        cfg.setdefault("control", {})["kp"] = float(kp)
    if kd is not None:
        cfg.setdefault("control", {})["kd"] = float(kd)
    if qc is not None:
        cfg.setdefault("control", {})["qc"] = qc
    return cfg


def _bytes_human(n: int) -> str:
    try:
        kb = 1024.0
        mb = kb * 1024.0
        if n >= mb:
            return f"{n/mb:.2f} MB"
        if n >= kb:
            return f"{n/kb:.2f} KB"
        return f"{n} B"
    except Exception:
        return str(n)


@router.post("/api/compute")
async def api_compute(config: dict = Body(default={})):  # type: ignore[assignment]
    try:
        sim_config = merge_with_defaults(config or {})
        plant = Plant(config=sim_config)
        sim = sim_config.get("simulation", {})
        t_max = float(sim.get("t_max", 1000.0))
        rtol = float(sim.get("rtol", 1.0e-12))
        atol = float(sim.get("atol", 1.0e-12))
        playback_speed = float(sim.get("playback_speed", 1.0))
        sample_rate = float(sim.get("sample_rate", 30.0))
        
        # Control
        ctrl = sim_config.get("control", {})
        control_type = ctrl.get("control_type")
        kp = float(ctrl.get("kp", 0.0))
        kd = float(ctrl.get("kd", 0.0))
        qc_list = ctrl.get("qc")

        # Prepare arguments for compute_states
        args = {"t_max": t_max, "rtol": rtol, "atol": atol}
        if control_type is not None and qc_list:
            args["control_type"] = control_type
            args["kp"] = kp
            args["kd"] = kd
            args["qc"] = np.array(qc_list, dtype=float)

        t0 = time.perf_counter()
        t, y = plant.compute_states(**args)
        t_compute = time.perf_counter() - t0
        t_s, r_s, v_s, eul_s, w_s, q_s, h_s = plant.evaluate_gui(t, y, playback_speed=playback_speed, sample_rate=sample_rate)
        # Quaternion components (scalar last): qx, qy, qz, qw
        qx_arr = q_s[0, :].tolist()
        qy_arr = q_s[1, :].tolist()
        qz_arr = q_s[2, :].tolist()
        qw_arr = q_s[3, :].tolist()
        # Earth rotation parameters for orbit visualization
        try:
            input_time_str = None
            if isinstance(config, dict):
                input_time_str = config.get("epoch_utc")
            if not input_time_str:
                input_time_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
            theta0_deg = float(get_sid_time(input_time_str))
            theta0_rad = math.radians(theta0_deg)
            spin_rate = float(earth_spin_rate_radps(input_time_str))
        except Exception:
            theta0_rad = 0.0
            spin_rate = 7.2921151e-5

        dataset = {
            "t": t_s.tolist(),
            "qx": qx_arr,
            "qy": qy_arr,
            "qz": qz_arr,
            "qw": qw_arr,
            "p": w_s[0, :].tolist(),
            "q": w_s[1, :].tolist(),
            "r": w_s[2, :].tolist(),
            "hx": h_s[0, :].tolist(),
            "hy": h_s[1, :].tolist(),
            "hz": h_s[2, :].tolist(),
            "sample_rate": sample_rate,
            # Earth rotation parameters
            "earth_initial_sidereal_angle_rad": theta0_rad,
            "earth_spin_rate_radps": spin_rate,
        }
        # Metrics
        num_steps = int(t.shape[0])
        # Low-overhead memory proxy: raw solver arrays size (pre-JSON)
        solver_bytes = int(getattr(t, 'nbytes', 0) + getattr(y, 'nbytes', 0))
        time_per_step = (t_compute / num_steps) if num_steps > 0 else 0.0
        metrics = {
            "compute_time_s": t_compute,
            "num_integration_points": num_steps,
            "time_per_integration_point_s": time_per_step,
            "solver_state_size_bytes": solver_bytes,
            "solver_state_size_readable": _bytes_human(solver_bytes),
        }
        return {"dataset": dataset, "metrics": metrics}
    except Exception as e:
        logging.error(traceback.format_exc())
        return {"error": str(e)}


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    print("Client connected.")
    is_paused = False

    # Synchronization for receiving configuration before starting the simulation
    config_event = asyncio.Event()
    sim_config = {"_received": False}

    async def receiver():
        nonlocal is_paused, sim_config
        while True:
            try:
                message = await websocket.receive_text()
            except WebSocketDisconnect:
                raise
            try:
                command = json.loads(message)
                if command.get("command") == "pause":
                    print("Simulation paused.")
                    is_paused = True
                elif command.get("command") == "resume":
                    print("Simulation resumed.")
                    is_paused = False
                elif command.get("command") == "configure":
                    print("Received simulation configuration.")
                    payload = command.get("payload", {})
                    sim_config = merge_with_defaults(payload)
                    # Stash epoch_utc (string) for visualization parameters
                    try:
                        sim_config["_epoch_utc"] = payload.get("epoch_utc") if isinstance(payload, dict) else None
                    except Exception:
                        sim_config["_epoch_utc"] = None
                    sim_config["_received"] = True
                    config_event.set()
            except json.JSONDecodeError:
                print(f"Received non-JSON message: {message}")

    async def sender():
        # Wait for configuration from the client
        await config_event.wait()
        plant = Plant(config=sim_config)
        # Precompute full trajectory and provide sampled dataset for GUI playback
        sim = sim_config.get("simulation", {})
        t_max = float(sim.get("t_max", 1000.0))
        rtol = float(sim.get("rtol", 1.0e-12))
        atol = float(sim.get("atol", 1.0e-12))
        playback_speed = float(sim.get("playback_speed", 1.0))
        sample_rate = float(sim.get("sample_rate", 30.0))

        try:
            # Control
            ctrl = sim_config.get("control", {})
            control_type = ctrl.get("control_type")
            kp = float(ctrl.get("kp", 0.0))
            kd = float(ctrl.get("kd", 0.0))
            qc_list = ctrl.get("qc")
            
            # Prepare arguments for compute_states
            args = {"t_max": t_max, "rtol": rtol, "atol": atol}
            if control_type is not None and qc_list:
                args["control_type"] = control_type
                args["kp"] = kp
                args["kd"] = kd
                args["qc"] = np.array(qc_list, dtype=float)

            t0 = time.perf_counter()
            t, y = plant.compute_states(**args)
            t_compute = time.perf_counter() - t0
            t_s, r_s, v_s, eul_s, w_s, q_s, h_s = plant.evaluate_gui(t, y, playback_speed=playback_speed, sample_rate=sample_rate)
            # Quaternion components (scalar last): qx, qy, qz, qw
            qx_arr = q_s[0, :].tolist()
            qy_arr = q_s[1, :].tolist()
            qz_arr = q_s[2, :].tolist()
            qw_arr = q_s[3, :].tolist()
            # Earth rotation parameters for orbit visualization (use provided epoch_utc if available)
            try:
                input_time_str = sim_config.get("_epoch_utc")
                if not input_time_str:
                    input_time_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
                theta0_deg = float(get_sid_time(input_time_str))
                theta0_rad = math.radians(theta0_deg)
                spin_rate = float(earth_spin_rate_radps(input_time_str))
            except Exception:
                theta0_rad = 0.0
                spin_rate = 7.2921151e-5

            dataset = {
                "t": t_s.tolist(),
                "qx": qx_arr,
                "qy": qy_arr,
                "qz": qz_arr,
                "qw": qw_arr,
                "p": w_s[0, :].tolist(),
                "q": w_s[1, :].tolist(),
                "r": w_s[2, :].tolist(),
                "hx": h_s[0, :].tolist(),
                "hy": h_s[1, :].tolist(),
                "hz": h_s[2, :].tolist(),
                "sample_rate": sample_rate,
                # Earth rotation parameters
                "earth_initial_sidereal_angle_rad": theta0_rad,
                "earth_spin_rate_radps": spin_rate,
            }
            # Metrics
            num_steps = int(t.shape[0])
            solver_bytes = int(getattr(t, 'nbytes', 0) + getattr(y, 'nbytes', 0))
            time_per_step = (t_compute / num_steps) if num_steps > 0 else 0.0
            metrics = {
                "compute_time_s": t_compute,
                "num_integration_points": num_steps,
                "time_per_integration_point_s": time_per_step,
                "solver_state_size_bytes": solver_bytes,
                "solver_state_size_readable": _bytes_human(solver_bytes),
            }
            await websocket.send_text(json.dumps({"dataset": dataset, "metrics": metrics}))
        except Exception as e:
            logging.error(traceback.format_exc())
            await websocket.send_text(json.dumps({"error": str(e)}))

        # Keep the connection alive to allow future reconfiguration if desired
        while True:
            await asyncio.sleep(1.0)

    try:
        await asyncio.gather(receiver(), sender())
    except WebSocketDisconnect:
        print("Client disconnected.")
    except Exception as e:
        logging.error(traceback.format_exc())
        print(f"An error occurred: {e}")
