# --- DIAGNOSTICS ---
import websockets
print(f"--- DIAGNOSTIC: websockets version installed is {websockets.__version__} ---")

# --- IMPORTS ---
import asyncio
import http
import json
import os
import signal
from plant.plant import Plant

# This is the main server function from the websockets library
from websockets.asyncio.server import serve

# --- CONFIGURATION ---
HTTP_PORT = int(os.getenv('PORT', 8080))
HOST = os.getenv('HOST', '0.0.0.0')

# --- WEBSOCKET HANDLER ---
# This is your application logic for when a WebSocket connection is established.
# It does not need to change.
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

# --- HTTP REQUEST PROCESSOR (NEW AND CORRECTED) ---
# This function uses the pattern from the documentation you provided.
# It receives the connection and request objects.
def process_request(connection, request):
    # Check if the request is for a WebSocket upgrade.
    # If so, return None to let the websockets library handle it.
    if "Upgrade" in request.headers and request.headers["Upgrade"].lower() == "websocket":
        return None

    # This is a regular HTTP request. We will serve a file or a health check.
    path = request.path
    
    # Handle health check endpoint
    if path == '/healthz':
        # Use connection.respond() as shown in the documentation
        return connection.respond(http.HTTPStatus.OK, "OK\n")

    # Serve static files from the 'webapp' directory
    webapp_path = os.path.join(os.path.dirname(__file__), 'webapp')
    if path == '/':
        path = '/index.html'
    
    requested_path = os.path.normpath(path.lstrip('/'))
    full_path = os.path.join(webapp_path, requested_path)

    # Security check: prevent directory traversal attacks
    if not os.path.normpath(full_path).startswith(os.path.normpath(webapp_path)):
        return connection.respond(http.HTTPStatus.FORBIDDEN, "Forbidden")

    try:
        with open(full_path, 'rb') as f:
            body = f.read()

        # websockets 15.x respond(status, body) — headers aren’t supported positionally
        # Serving without explicit headers is acceptable for our static assets
        return connection.respond(http.HTTPStatus.OK, body)
    except (FileNotFoundError, IsADirectoryError):
        # Use connection.respond() for 404 errors
        return connection.respond(http.HTTPStatus.NOT_FOUND, "Not Found")

# --- MAIN SERVER STARTUP ---
async def main():
    print(f"Starting unified HTTP+WebSocket server on {HOST}:{HTTP_PORT}")
    # Pass the corrected process_request function to the server
    async with serve(
        calculation_and_update_server,
        HOST,
        HTTP_PORT,
        process_request=process_request,
    ) as server:
        # Close the server when receiving SIGTERM (graceful shutdown for PaaS)
        loop = asyncio.get_running_loop()
        loop.add_signal_handler(signal.SIGTERM, server.close)
        await server.wait_closed()

if __name__ == "__main__":
    print(f"Open your browser and navigate to http://{HOST}:{HTTP_PORT}")
    print("Press Ctrl+C to stop the server.")
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nServer stopped.")