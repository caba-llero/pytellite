import asyncio
import json
import os
import time
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Response
from fastapi import Body
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from plant.sim import Plant
from plant.orbit import get_sid_time, earth_spin_rate_radps
from datetime import datetime, timezone
import math
from plant.quaternion_math import Quaternion
import yaml
import glob

# Ensure logs directory exists
os.makedirs("logs", exist_ok=True)

app = FastAPI()
STATIC_DIR = os.path.join(os.path.dirname(__file__), "webapp")
app.mount("/static", StaticFiles(directory=STATIC_DIR, html=True), name="static")
TEXTURES_DIR = os.path.join(os.path.dirname(__file__), "textures")
if os.path.isdir(TEXTURES_DIR):
    app.mount("/textures", StaticFiles(directory=TEXTURES_DIR, html=False), name="textures")

@app.get("/")
async def serve_config():
    return FileResponse(os.path.join(STATIC_DIR, "config.html"))

@app.get("/simulation")
async def serve_index():
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))

@app.get("/loading")
async def serve_loading():
    return FileResponse(os.path.join(STATIC_DIR, "loading.html"))

@app.head("/")
async def serve_index_head():
    return Response(status_code=200)

@app.get("/logo.png")
async def serve_logo():
    return FileResponse(os.path.join(os.path.dirname(__file__), "logo.png"))

# Favicons and manifest at root
@app.get("/apple-touch-icon.png")
async def serve_apple_touch():
    return FileResponse(os.path.join(os.path.dirname(__file__), "apple-touch-icon.png"))

@app.get("/favicon-32x32.png")
async def serve_favicon_32():
    return FileResponse(os.path.join(os.path.dirname(__file__), "favicon-32x32.png"))

@app.get("/favicon-16x16.png")
async def serve_favicon_16():
    return FileResponse(os.path.join(os.path.dirname(__file__), "favicon-16x16.png"))

@app.get("/site.webmanifest")
async def serve_manifest():
    return FileResponse(os.path.join(os.path.dirname(__file__), "site.webmanifest"))

@app.get("/healthz")
async def healthz():
    return {"status": "ok"}


def _load_defaults() -> dict:
    # Prefer root-level configs; fallback to legacy plant/config_default.yaml
    root_cfg = os.path.join(os.path.dirname(__file__), "configs", "config_default.yaml")
    legacy_cfg = os.path.join(os.path.dirname(__file__), "plant", "config_default.yaml")
    config_path = root_cfg if os.path.exists(root_cfg) else legacy_cfg
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


@app.get("/api/defaults")
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

@app.get("/api/presets")
async def api_presets():
    cfg_dir = os.path.join(os.path.dirname(__file__), "configs")
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

@app.get("/api/presets/{filename}")
async def api_preset_file(filename: str):
    # sanitize filename
    base = os.path.basename(filename)
    if not base.endswith('.yaml'):
        return {"error": "invalid preset filename"}
    cfg_dir = os.path.join(os.path.dirname(__file__), "configs")
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
            mapped = "zero_torque"
        elif ct in ("inertial_nonlinear", "nonlinear_tracking"):
            mapped = "nonlinear_tracking"
        elif ct in ("inertial", "inertial_linear", "tracking"):
            mapped = "tracking"
        else:
            mapped = "zero_torque"
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


@app.post("/api/compute")
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
        if control_type and qc_list:
            args["control_type"] = control_type
            args["kp"] = kp
            args["kd"] = kd
            args["qc"] = Quaternion(qc_list)

        t0 = time.perf_counter()
        t, y = plant.compute_states(**args)
        t_compute = time.perf_counter() - t0
        t_s, r_s, v_s, eul_s, w_s, q_s = plant.evaluate_gui(t, y, playback_speed=playback_speed, sample_rate=sample_rate)
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
        return {"error": str(e)}


@app.websocket("/ws")
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
            if control_type and qc_list:
                args["control_type"] = control_type
                args["kp"] = kp
                args["kd"] = kd
                args["qc"] = Quaternion(qc_list)

            t0 = time.perf_counter()
            t, y = plant.compute_states(**args)
            t_compute = time.perf_counter() - t0
            t_s, r_s, v_s, eul_s, w_s, q_s = plant.evaluate_gui(t, y, playback_speed=playback_speed, sample_rate=sample_rate)
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
            await websocket.send_text(json.dumps({"error": str(e)}))

        # Keep the connection alive to allow future reconfiguration if desired
        while True:
            await asyncio.sleep(1.0)

    try:
        await asyncio.gather(receiver(), sender())
    except WebSocketDisconnect:
        print("Client disconnected.")
    except Exception as e:
        print(f"An error occurred: {e}")


if __name__ == "__main__":
    import uvicorn
    # Bind to 0.0.0.0 and the provided PORT on Render; use localhost in dev
    port = int(os.getenv("PORT", "8000"))
    on_render = os.getenv("PORT") is not None
    host = "0.0.0.0" if on_render else "127.0.0.1"
    reload = False if on_render else True
    if on_render:
        print(f"Starting server for Render on {host}:{port}")
    else:
        print("Starting server in development mode...")
        print(f"Open your browser and navigate to http://{host}:{port}")
    uvicorn.run("app:app", host=host, port=port, reload=reload)
    