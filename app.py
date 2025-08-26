import asyncio
import json
import math
import os
import time
import http.server
import socketserver
import socket
import threading
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

def run_http_server():
    webapp_path = os.path.join(os.path.dirname(__file__), 'webapp')

    class CustomHandler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=webapp_path, **kwargs)

        def do_GET(self):
            # Lightweight health check endpoint for Railway
            if self.path == '/healthz':
                self.send_response(200)
                self.send_header("Content-type", "text/plain")
                self.end_headers()
                self.wfile.write(b"ok")
                return
            # Handle index.html specially to inject the WebSocket port
            if self.path == '/' or self.path == '/index.html':
                self.path = '/index.html'
                try:
                    with open(os.path.join(webapp_path, 'index.html'), 'r', encoding='utf-8') as f:
                        content = f.read()

                    # WebSocket now uses the same port as HTTP, no injection needed

                    self.send_response(200)
                    self.send_header("Content-type", "text/html")
                    self.end_headers()
                    self.wfile.write(content.encode('utf-8'))
                except FileNotFoundError:
                    self.send_error(404, "File not found")
            else:
                # Serve other static files normally
                super().do_GET()

    # Prefer IPv6 dual-stack binding to satisfy Railway v2 healthchecks
    try:
        class DualStackServer(socketserver.TCPServer):
            address_family = socket.AF_INET6
            allow_reuse_address = True
            def server_bind(self):
                if hasattr(socket, 'IPV6_V6ONLY'):
                    try:
                        self.socket.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 0)
                    except OSError:
                        pass
                super().server_bind()

        server = DualStackServer(('::', HTTP_PORT), CustomHandler)
        bound_host = '::'
    except Exception as e:
        print(f"IPv6 dual-stack bind failed ({e}); falling back to IPv4")
        server = socketserver.TCPServer((HOST, HTTP_PORT), CustomHandler)
        bound_host = HOST

    with server as httpd:
        print(f"HTTP server started at http://{bound_host}:{HTTP_PORT}")
        print(f"Serving files from: {webapp_path}")
        httpd.serve_forever()

async def main():
    async with websockets.serve(calculation_and_update_server, HOST, HTTP_PORT):
        print(f"WebSocket server started at ws://{HOST}:{HTTP_PORT}")
        await asyncio.Future()

if __name__ == "__main__":
    http_thread = threading.Thread(target=run_http_server)
    http_thread.daemon = True
    http_thread.start()
    print("Starting WebSocket server...")
    print(f"Open your browser and navigate to http://{HOST}:{HTTP_PORT}")
    print("Press Ctrl+C to stop the servers.")
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nServers stopped.")

    