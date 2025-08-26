# --- DIAGNOSTICS ---
import websockets
print(f"--- DIAGNOSTIC: websockets version installed is {websockets.__version__} ---")

# --- IMPORTS ---
import asyncio
import json
import http
import os
from plant.plant import Plant
# NO MORE 'Response' or 'Headers' imports are needed.

# --- CONFIGURATION ---
HTTP_PORT = int(os.getenv('PORT', 8080))
HOST = os.getenv('HOST', '0.0.0.0')

# --- WEBSOCKET HANDLER ---
# (This part of your code is fine and does not need changes)
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
        while websocket.open:
            if not is_paused:
                euler_angles, angular_velocity = plant.update()
                data = {
                    "roll": euler_angles[0], "pitch": euler_angles[1], "yaw": euler_angles[2],
                    "p": angular_velocity[0], "q": angular_velocity[1], "r": angular_velocity[2]
                }
                await websocket.send(json.dumps(data))
            
            await asyncio.sleep(plant.dt_sim)

    try:
        await asyncio.gather(receiver(), sender())
    except websockets.exceptions.ConnectionClosed:
        print("Client disconnected.")
    except Exception as e:
        print(f"An error occurred: {e}")

# --- HELPER FOR STATIC FILES ---
def _guess_mime_type(path: str) -> str:
    if path.endswith('.html'): return 'text/html; charset=utf-8'
    if path.endswith('.js'): return 'application/javascript; charset=utf-8'
    if path.endswith('.css'): return 'text/css; charset=utf-8'
    if path.endswith('.json'): return 'application/json; charset=utf-8'
    if path.endswith('.png'): return 'image/png'
    if path.endswith('.jpg') or path.endswith('.jpeg'): return 'image/jpeg'
    if path.endswith('.svg'): return 'image/svg+xml'
    return 'application/octet-stream'

# --- MAIN SERVER LOGIC ---
# This version returns tuples: (status_code, headers, body)
# This is the stable, long-term supported API for websockets.
async def process_request(path: str, request_headers):
    # Health check endpoint
    if path == '/healthz':
        headers = [("Content-Type", "text/plain")]
        return http.HTTPStatus.OK, headers, b"ok"

    # This is a regular HTTP request, so we serve a static file.
    if "Upgrade" not in request_headers or request_headers["Upgrade"].lower() != "websocket":
        webapp_path = os.path.join(os.path.dirname(__file__), 'webapp')
        if path == '/':
            path = '/index.html'
        
        requested_path = os.path.normpath(path.lstrip('/'))
        full_path = os.path.join(webapp_path, requested_path)

        if not os.path.normpath(full_path).startswith(os.path.normpath(webapp_path)):
            return http.HTTPStatus.FORBIDDEN, [], b"Forbidden"

        try:
            with open(full_path, 'rb') as f:
                body = f.read()
            headers = [
                ("Content-Type", _guess_mime_type(full_path)),
                ("Content-Length", str(len(body))),
            ]
            return http.HTTPStatus.OK, headers, body
        except (FileNotFoundError, IsADirectoryError):
            headers = [("Content-Type", "text/plain")]
            return http.HTTPStatus.NOT_FOUND, headers, b"Not Found"

    # If we get here, it's a WebSocket upgrade request.
    # Returning None lets the WebSocket handshake proceed.
    return None

async def main():
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