import asyncio
import json
import os
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import PlainTextResponse
from starlette.staticfiles import StaticFiles
from plant.plant import Plant


# FastAPI application
app = FastAPI()


@app.get("/healthz", response_class=PlainTextResponse)
async def healthz() -> str:
    return "OK\n"


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    print("Client connected.")
    is_paused = False
    plant = Plant('plant/config_default.yaml')

    async def receiver() -> None:
        nonlocal is_paused
        try:
            while True:
                message = await websocket.receive_text()
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
        except WebSocketDisconnect:
            pass

    async def sender() -> None:
        try:
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
                    await websocket.send_json(data)
                await asyncio.sleep(plant.dt_sim)
        except WebSocketDisconnect:
            pass

    try:
        await asyncio.gather(receiver(), sender())
    finally:
        print("Client disconnected.")


# Serve static files (index.html, js, css) from /webapp at the root path
app.mount("/", StaticFiles(directory="webapp", html=True), name="static")
