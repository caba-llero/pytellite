// --- Basic Setup ---
const eulerDiv = document.getElementById('euler-angles');
const rendererContainer = document.getElementById('renderer-container');
const pauseButton = document.getElementById('pauseButton');

let latestAngles = { roll: 0, pitch: 0, yaw: 0 };
let isPaused = false;
const MAX_DATA_POINTS = 150;

// --- 3D Scene Setup ---
const scene = new THREE.Scene();
const camera = new THREE.PerspectiveCamera(75, rendererContainer.clientWidth / rendererContainer.clientHeight, 0.1, 1000);
const renderer = new THREE.WebGLRenderer({ antialias: true });
renderer.setSize(rendererContainer.clientWidth, rendererContainer.clientHeight);
rendererContainer.appendChild(renderer.domElement);
const controls = new THREE.OrbitControls(camera, renderer.domElement);
controls.enableDamping = true;
camera.position.set(4, 4, 4);

const cuboid = new THREE.Mesh(new THREE.BoxGeometry(2, 1, 0.5), new THREE.MeshNormalMaterial());
scene.add(cuboid);

// --- NEW: Helper function to create text labels ---
function createTextSprite(text, { fontsize = 32, fontface = 'Arial', textColor = { r: 255, g: 255, b: 255, a: 1.0 } }) {
    const canvas = document.createElement('canvas');
    const context = canvas.getContext('2d');
    context.font = `Bold ${fontsize}px ${fontface}`;

    // Set background color
    context.fillStyle = "rgba(0, 0, 0, 0.0)"; // Transparent background
    context.fillRect(0, 0, canvas.width, canvas.height);

    // Set text color
    context.fillStyle = `rgba(${textColor.r}, ${textColor.g}, ${textColor.b}, ${textColor.a})`;
    context.fillText(text, 0, fontsize);

    const texture = new THREE.Texture(canvas);
    texture.needsUpdate = true;

    const spriteMaterial = new THREE.SpriteMaterial({ map: texture });
    const sprite = new THREE.Sprite(spriteMaterial);
    sprite.scale.set(2, 1, 1.0); // Adjust scale as needed
    return sprite;
}

// --- NEW: Helper function to create a complete labeled axis ---
function createLabeledAxis(parent, direction, color, length, labelText) {
    const dir = new THREE.Vector3(...direction);
    const origin = new THREE.Vector3(0, 0, 0);
    const hex = color;

    // Create arrow
    const arrowHelper = new THREE.ArrowHelper(dir.normalize(), origin, length, hex, 0.2, 0.1);
    parent.add(arrowHelper);

    // Create label
    const label = createTextSprite(labelText, { fontsize: 24 });
    label.position.copy(dir.multiplyScalar(length * 1.1)); // Position label at the end of the arrow
    parent.add(label);
}

// --- NEW: Create Inertial Frame Axes ---
createLabeledAxis(scene, [1, 0, 0], 0xff0000, 5, 'X Inertial');
createLabeledAxis(scene, [0, 1, 0], 0x00ff00, 5, 'Y Inertial');
createLabeledAxis(scene, [0, 0, 1], 0x0000ff, 5, 'Z Inertial');

// --- NEW: Create Body-Fixed Frame Axes ---
// We add these to the cuboid object itself, so they rotate with it.
createLabeledAxis(cuboid, [1, 0, 0], 0xff0000, 3, 'x body');
createLabeledAxis(cuboid, [0, 1, 0], 0x00ff00, 3, 'y body');
createLabeledAxis(cuboid, [0, 0, 1], 0x0000ff, 3, 'z body');


// --- Plotly Charting Setup ---
function createPlotlyChart(divId, title, color, y_range) {
    const data = [{ x: [], y: [], type: 'scatter', mode: 'lines', line: { color: color, width: 2 } }];
    const layout = {
        title: { text: title, font: { color: 'white', size: 14 } },
        paper_bgcolor: '#1a1a1a', plot_bgcolor: '#1a1a1a',
        margin: { l: 40, r: 20, b: 30, t: 40, pad: 4 },
        xaxis: { color: 'white', gridcolor: '#444' },
        yaxis: { color: 'white', gridcolor: '#444', range: y_range }
    };
    Plotly.newPlot(divId, data, layout, { responsive: true });
}

createPlotlyChart('rollPlot', 'Roll (X)', '#ff6384', [-Math.PI, Math.PI]);
createPlotlyChart('pitchPlot', 'Pitch (Y)', '#36a2eb', [-Math.PI, Math.PI]);
createPlotlyChart('yawPlot', 'Yaw (Z)', '#4bc0c0', [-Math.PI, Math.PI]);
createPlotlyChart('pPlot', 'Roll Rate', '#ff9f40', [-5, 5]);
createPlotlyChart('qPlot', 'Pitch Rate', '#9966ff', [-5, 5]);
createPlotlyChart('rPlot', 'Yaw Rate', '#c9cbcf', [-5, 5]);

// --- WebSocket & Controls ---
// Get the WebSocket port from the global variable set by the server
const WEBSOCKET_PORT = window.WEBSOCKET_PORT || 8765;
const socket = new WebSocket(`ws://localhost:${WEBSOCKET_PORT}`);
let timeTick = 0;

pauseButton.addEventListener('click', () => {
    isPaused = !isPaused;
    pauseButton.innerText = isPaused ? 'Resume' : 'Pause';
    const command = { command: isPaused ? 'pause' : 'resume' };
    if (socket.readyState === WebSocket.OPEN) {
        socket.send(JSON.stringify(command));
    }
});

socket.onopen = () => eulerDiv.innerHTML = "Connected";
socket.onmessage = (event) => {
    const data = JSON.parse(event.data);
    latestAngles = { roll: data.roll, pitch: data.pitch, yaw: data.yaw };

    const update = {
        x: [[timeTick], [timeTick], [timeTick], [timeTick], [timeTick], [timeTick]],
        y: [[data.roll], [data.pitch], [data.yaw], [data.p], [data.q], [data.r]]
    };

    const traceIndices = [0];
    Plotly.extendTraces('rollPlot',  { x: [update.x[0]], y: [update.y[0]] }, traceIndices, MAX_DATA_POINTS);
    Plotly.extendTraces('pitchPlot', { x: [update.x[1]], y: [update.y[1]] }, traceIndices, MAX_DATA_POINTS);
    Plotly.extendTraces('yawPlot',   { x: [update.x[2]], y: [update.y[2]] }, traceIndices, MAX_DATA_POINTS);
    Plotly.extendTraces('pPlot',     { x: [update.x[3]], y: [update.y[3]] }, traceIndices, MAX_DATA_POINTS);
    Plotly.extendTraces('qPlot',     { x: [update.x[4]], y: [update.y[4]] }, traceIndices, MAX_DATA_POINTS);
    Plotly.extendTraces('rPlot',     { x: [update.x[5]], y: [update.y[5]] }, traceIndices, MAX_DATA_POINTS);

    timeTick++;
};
socket.onclose = () => eulerDiv.innerHTML = "Connection Closed.";
socket.onerror = () => eulerDiv.innerHTML = "Connection Error!";

// --- Animation Loop ---
function animate() {
    requestAnimationFrame(animate);
    cuboid.rotation.x = latestAngles.roll;
    cuboid.rotation.y = latestAngles.pitch;
    cuboid.rotation.z = latestAngles.yaw;
    controls.update();
    eulerDiv.innerHTML = `
        Roll: ${latestAngles.roll.toFixed(2)}<br>
        Pitch: ${latestAngles.pitch.toFixed(2)}<br>
        Yaw: ${latestAngles.yaw.toFixed(2)}
    `;
    renderer.render(scene, camera);
}
animate();

window.addEventListener('resize', () => {
    camera.aspect = rendererContainer.clientWidth / rendererContainer.clientHeight;
    camera.updateProjectionMatrix();
    renderer.setSize(rendererContainer.clientWidth, rendererContainer.clientHeight);
}, false);
