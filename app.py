import asyncio
import json
import math
import os
import time
import http.server
import socket
import websockets
from plant.plant import Plant

# --- Configuration ---
HTTP_PORT = int(os.getenv('PORT', 8000))
HOST = os.getenv('HOST', '0.0.0.0')  # Use 0.0.0.0 for production

# --- Frontend files are now served from the webapp directory ---

# --- Python Backend ---


# CORRECTED: The WebSocket handler now correctly manages the connection state.
async def calculation_and_update_server(websocket):
    print("Client connected.")
    is_paused = False
    
    async def receiver():
        nonlocal is_paused
        async for message in websocket:
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
        # CORRECTED LINE: Changed `while websocket.open` to `while True`
        while True:
            if not is_paused:
                euler_angles, angular_velocity = plant.update()
                data = {
                    "roll": euler_angles[0], "pitch": euler_angles[1], "yaw": euler_angles[2],
                    "p": angular_velocity[0], "q": angular_velocity[1], "r": angular_velocity[2]
                }
                # This will raise ConnectionClosed when the client disconnects
                await websocket.send(json.dumps(data))
            
            await asyncio.sleep(plant.dt_sim)

    try:
        await asyncio.gather(receiver(), sender())
    except websockets.exceptions.ConnectionClosed:
        print("Client disconnected.")
    except Exception as e:
        print(f"An error occurred: {e}")

def _guess_mime_type(path: str) -> str:
    if path.endswith('.html'):
        return 'text/html; charset=utf-8'
    if path.endswith('.js'):
        return 'application/javascript; charset=utf-8'
    if path.endswith('.css'):
        return 'text/css; charset=utf-8'
    if path.endswith('.json'):
        return 'application/json; charset=utf-8'
    if path.endswith('.png'):
        return 'image/png'
    if path.endswith('.jpg') or path.endswith('.jpeg'):
        return 'image/jpeg'
    if path.endswith('.svg'):
        return 'image/svg+xml'
    return 'application/octet-stream'


def _serve_static_request(path: str):
    webapp_path = os.path.join(os.path.dirname(__file__), 'webapp')

    # Health check
    if path == '/healthz':
        body = b"ok"
        return (
            http.HTTPStatus.OK,
            [("Content-Type", "text/plain"), ("Content-Length", str(len(body)))],
            body,
        )

    if path == '/':
        path = '/index.html'

    # Prevent directory traversal
    requested = os.path.normpath(path.lstrip('/'))
    full_path = os.path.join(webapp_path, requested)
    full_path = os.path.normpath(full_path)
    if not full_path.startswith(os.path.normpath(webapp_path)):
        body = b"Forbidden"
        return (
            http.HTTPStatus.FORBIDDEN,
            [("Content-Type", "text/plain"), ("Content-Length", str(len(body)))],
            body,
        )

    try:
        with open(full_path, 'rb') as f:
            body = f.read()
        headers = [
            ("Content-Type", _guess_mime_type(full_path)),
            ("Content-Length", str(len(body))),
        ]
        return (http.HTTPStatus.OK, headers, body)
    except FileNotFoundError:
        body = b"Not Found"
        return (
            http.HTTPStatus.NOT_FOUND,
            [("Content-Type", "text/plain"), ("Content-Length", str(len(body)))],
            body,
        )

async def main():
    # Serve both HTTP (static files + /healthz) and WebSocket on the SAME port
    async def process_request(path, request):
        # If this is a normal HTTP request (not a WS upgrade), serve static
        upgrade_hdr = request.headers.get('Upgrade', '')
        if upgrade_hdr.lower() != 'websocket':
            return _serve_static_request(path)
        # Otherwise, proceed with WebSocket handshake (return None)
        return None

    print(f"Starting unified HTTP+WebSocket server on {HOST}:{HTTP_PORT}")
    async with websockets.serve(
        calculation_and_update_server,
        HOST,
        HTTP_PORT,
        process_request=process_request,
    ):
        await asyncio.Future()

if __name__ == "__main__":
    print(f"Open your browser and navigate to http://{HOST}:{HTTP_PORT}")
    print("Press Ctrl+C to stop the server.")
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nServer stopped.")

    