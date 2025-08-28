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
        while True:
            if not is_paused:
                euler_angles, angular_velocity = plant.update()
                data = {
                    "roll": euler_angles[0],
                    "pitch": euler_angles[1],
                    "yaw": euler_angles[2],
                    "p": angular_velocity[0],
                    "q": angular_velocity[1],
                    "r": angular_velocity[2],
                }
                await websocket.send_text(json.dumps(data))
            await asyncio.sleep(plant.dt_sim)

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
    