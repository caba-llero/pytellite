import asyncio
import json
import os
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from plant.plant import Plant

app = FastAPI()
STATIC_DIR = os.path.join(os.path.dirname(__file__), "web")
app.mount("/static", StaticFiles(directory=STATIC_DIR, html=True), name="static")

@app.get("/")
async def serve_index():
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    print("Client connected.")
    is_paused = False

    async def receiver():
        nonlocal is_paused
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
            except json.JSONDecodeError:
                print(f"Received non-JSON message: {message}")

    async def sender():
        plant = Plant('plant/config_default.yaml')
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
    print("Open your browser and navigate to http://localhost:8000")
    uvicorn.run("app:app", host="127.0.0.1", port=8000, reload=True)
    