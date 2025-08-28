import asyncio
import json
import os
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Response
from fastapi import Body
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from plant.sim import Plant
import yaml

# Ensure logs directory exists
os.makedirs("logs", exist_ok=True)

app = FastAPI()
STATIC_DIR = os.path.join(os.path.dirname(__file__), "webapp")
app.mount("/static", StaticFiles(directory=STATIC_DIR, html=True), name="static")

@app.get("/")
async def serve_config():
    return FileResponse(os.path.join(STATIC_DIR, "config.html"))

@app.get("/simulation")
async def serve_index():
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))

@app.head("/")
async def serve_index_head():
    return Response(status_code=200)

@app.get("/logo.png")
async def serve_logo():
    return FileResponse(os.path.join(os.path.dirname(__file__), "logo.png"))

@app.get("/healthz")
async def healthz():
    return {"status": "ok"}


def _load_defaults() -> dict:
    config_path = os.path.join(os.path.dirname(__file__), "plant", "config_default.yaml")
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
        },
        "simulation": {
            "dt_sim": cfg["simulation"]["dt_sim"],
            "t_max": cfg["simulation"].get("t_max", 1000.0),
            "playback_speed": cfg["simulation"].get("playback_speed", 1.0),
            "sample_rate": cfg["simulation"].get("sample_rate", 30.0),
            "rtol": cfg["simulation"].get("rtol", 1.0e-12),
            "atol": cfg["simulation"].get("atol", 1.0e-12),
        },
    }


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    print("Client connected.")
    is_paused = False

    # Synchronization for receiving configuration before starting the simulation
    config_event = asyncio.Event()
    sim_config = {"_received": False}

    def _merge_with_defaults(payload: dict) -> dict:
        cfg = _load_defaults()
        # Apply overrides
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
        return cfg

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
                    sim_config = _merge_with_defaults(payload)
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
            t, y = plant.compute_states(t_max=t_max, rtol=rtol, atol=atol)
            t_s, r_s, v_s, eul_s, w_s = plant.evaluate_gui(t, y, playback_speed=playback_speed, sample_rate=sample_rate)
            # eul_s is (3, N) in ZYX order -> yaw, pitch, roll. Reorder to roll, pitch, yaw
            yaw_arr = eul_s[0, :].tolist()
            pitch_arr = eul_s[1, :].tolist()
            roll_arr = eul_s[2, :].tolist()
            dataset = {
                "t": t_s.tolist(),
                "roll": roll_arr,
                "pitch": pitch_arr,
                "yaw": yaw_arr,
                "p": w_s[0, :].tolist(),
                "q": w_s[1, :].tolist(),
                "r": w_s[2, :].tolist(),
                "sample_rate": sample_rate,
            }
            await websocket.send_text(json.dumps({"dataset": dataset}))
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
    