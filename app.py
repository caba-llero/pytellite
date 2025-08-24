import asyncio
import json
import math
import time
import http.server
import socketserver
import threading
import websockets

# --- Configuration ---
HTTP_PORT = 8000
WEBSOCKET_PORT = 8765

# --- HTML and JavaScript Frontend ---
# UPDATED: Added Chart.js and a new layout for plots.
html_content = f"""
<!DOCTYPE html>
<html>
<head>
    <title>Python-Controlled Cuboid with Live Plots</title>
    <style>
        body {{ 
            margin: 0; 
            background-color: #111; 
            color: white; 
            font-family: monospace;
            overflow: hidden; /* Prevent scrollbars */
        }}
        #container {{
            display: flex;
            width: 100vw;
            height: 100vh;
        }}
        #main-vis {{
            flex: 3; /* 3/4 of the width */
            position: relative; /* Needed for the info box */
        }}
        #renderer-container {{
            width: 100%;
            height: 100%;
        }}
        #plots-container {{
            flex: 1; /* 1/4 of the width */
            display: flex;
            flex-direction: column;
            background-color: #1a1a1a;
            padding: 10px;
            box-sizing: border-box;
        }}
        .plot-wrapper {{
            flex: 1;
            min-height: 0; /* Important for flexbox to shrink children */
            margin-bottom: 10px;
        }}
        #info {{
            position: absolute;
            top: 10px;
            left: 10px;
            background-color: rgba(0,0,0,0.5);
            padding: 10px;
            border-radius: 5px;
            z-index: 10;
        }}
    </style>
</head>
<body>
    <div id="container">
        <div id="main-vis">
            <div id="info">
                <h2>Live Euler Angles</h2>
                <div id="euler-angles">Not Connected</div>
            </div>
            <div id="renderer-container"></div>
        </div>
        <div id="plots-container">
            <div class="plot-wrapper"><canvas id="rollChart"></canvas></div>
            <div class="plot-wrapper"><canvas id="pitchChart"></canvas></div>
            <div class="plot-wrapper"><canvas id="yawChart"></canvas></div>
        </div>
    </div>

    <script src="https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/three@0.128.0/examples/js/controls/OrbitControls.js"></script>
    <!-- ADDED SCRIPT FOR CHART.JS -->
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <script>
        // --- Basic Setup ---
        const eulerDiv = document.getElementById('euler-angles');
        const rendererContainer = document.getElementById('renderer-container');
        let latestAngles = {{ roll: 0, pitch: 0, yaw: 0 }};
        const MAX_DATA_POINTS = 100; // Number of points to show on the plot

        // --- 3D Scene Setup ---
        const scene = new THREE.Scene();
        const camera = new THREE.PerspectiveCamera(75, rendererContainer.clientWidth / rendererContainer.clientHeight, 0.1, 1000);
        const renderer = new THREE.WebGLRenderer({{ antialias: true }});
        renderer.setSize(rendererContainer.clientWidth, rendererContainer.clientHeight);
        rendererContainer.appendChild(renderer.domElement);

        const l_x = 2, l_y = 1, l_z = 0.5;
        const geometry = new THREE.BoxGeometry(l_x, l_y, l_z);
        const material = new THREE.MeshNormalMaterial();
        const cuboid = new THREE.Mesh(geometry, material);
        scene.add(cuboid);

        const worldAxes = new THREE.AxesHelper(5);
        scene.add(worldAxes);
        const bodyAxes = new THREE.AxesHelper(3);
        cuboid.add(bodyAxes);

        camera.position.set(3, 3, 3);
        const controls = new THREE.OrbitControls(camera, renderer.domElement);
        controls.enableDamping = true;

        // --- Charting Setup ---
        function createRealtimeChart(canvasId, label, color) {{
            const ctx = document.getElementById(canvasId).getContext('2d');
            return new Chart(ctx, {{
                type: 'line',
                data: {{ labels: [], datasets: [{{ 
                    label: label, 
                    data: [], 
                    borderColor: color, 
                    borderWidth: 2, 
                    pointRadius: 0,
                    tension: 0.1
                }}] }},
                options: {{
                    responsive: true,
                    maintainAspectRatio: false,
                    scales: {{
                        x: {{ ticks: {{ display: false }}, grid: {{ color: '#444' }} }},
                        y: {{ min: -2.5, max: 2.5, grid: {{ color: '#444' }} }}
                    }},
                    plugins: {{ legend: {{ labels: {{ color: 'white' }} }} }}
                }}
            }});
        }}

        const rollChart = createRealtimeChart('rollChart', 'Roll (X)', 'rgba(255, 99, 132, 1)');
        const pitchChart = createRealtimeChart('pitchChart', 'Pitch (Y)', 'rgba(54, 162, 235, 1)');
        const yawChart = createRealtimeChart('yawChart', 'Yaw (Z)', 'rgba(75, 192, 192, 1)');

        function updateChart(chart, label, value) {{
            chart.data.labels.push(label);
            chart.data.datasets[0].data.push(value);
            if (chart.data.labels.length > MAX_DATA_POINTS) {{
                chart.data.labels.shift();
                chart.data.datasets[0].data.shift();
            }}
            chart.update('none'); // Use 'none' for a smoother animation
        }}

        // --- WebSocket Client ---
        const socket = new WebSocket('ws://localhost:{WEBSOCKET_PORT}');
        let timeLabel = 0;

        socket.onopen = () => eulerDiv.innerHTML = "Connected";
        socket.onmessage = (event) => {{
            latestAngles = JSON.parse(event.data);
            timeLabel++;
            // Update all three charts with new data
            updateChart(rollChart, timeLabel, latestAngles.roll);
            updateChart(pitchChart, timeLabel, latestAngles.pitch);
            updateChart(yawChart, timeLabel, latestAngles.yaw);
        }};
        socket.onclose = () => eulerDiv.innerHTML = "Connection Closed.";
        socket.onerror = () => eulerDiv.innerHTML = "Connection Error!";

        // --- Animation Loop ---
        function animate() {{
            requestAnimationFrame(animate);
            cuboid.rotation.x = latestAngles.roll;
            cuboid.rotation.y = latestAngles.pitch;
            cuboid.rotation.z = latestAngles.yaw;
            controls.update();
            eulerDiv.innerHTML = `
                <p>Roll (X): ${{latestAngles.roll.toFixed(3)}}</p>
                <p>Pitch (Y): ${{latestAngles.pitch.toFixed(3)}}</p>
                <p>Yaw (Z): ${{latestAngles.yaw.toFixed(3)}}</p>
            `;
            renderer.render(scene, camera);
        }}
        animate();

        // Handle window resize
        window.addEventListener('resize', () => {{
            camera.aspect = rendererContainer.clientWidth / rendererContainer.clientHeight;
            camera.updateProjectionMatrix();
            renderer.setSize(rendererContainer.clientWidth, rendererContainer.clientHeight);
        }}, false);
    </script>
</body>
</html>
"""

# --- Python Backend (No changes needed) ---
from plant.plant import Plant

async def calculation_and_update_server(websocket):
    print("Client connected.")
    plant = Plant('plant/config_default.yaml')
    try:
        while True:
            euler_angles, angular_velocity = plant.update()
            
            angles = {"roll": euler_angles[0], "pitch": euler_angles[1], "yaw": euler_angles[2]}
            await websocket.send(json.dumps(angles))
            await asyncio.sleep(plant.dt_sim)
    except websockets.exceptions.ConnectionClosed:
        print("Client disconnected.")
    except Exception as e:
        print(f"An error occurred: {e}")

def run_http_server():
    Handler = http.server.SimpleHTTPRequestHandler
    class CustomHandler(Handler):
        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-type", "text/html")
            self.end_headers()
            self.wfile.write(html_content.encode('utf-8'))
    with socketserver.TCPServer(("", HTTP_PORT), CustomHandler) as httpd:
        print(f"HTTP server started at http://localhost:{HTTP_PORT}")
        httpd.serve_forever()

async def main():
    async with websockets.serve(calculation_and_update_server, "localhost", WEBSOCKET_PORT):
        print(f"WebSocket server started at ws://localhost:{WEBSOCKET_PORT}")
        await asyncio.Future()

if __name__ == "__main__":
    http_thread = threading.Thread(target=run_http_server)
    http_thread.daemon = True
    http_thread.start()
    print("Starting WebSocket server...")
    print("Open your browser and navigate to http://localhost:8000")
    print("Press Ctrl+C to stop the servers.")
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nServers stopped.")