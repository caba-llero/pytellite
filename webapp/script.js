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

// --- Axes helper: create arrow (solid or dashed) with arrow tip, no text labels ---
function createAxis(parent, direction, color, length, dashed = false) {
    const dir = new THREE.Vector3(...direction).normalize();
    const start = new THREE.Vector3(0, 0, 0);
    const end = dir.clone().multiplyScalar(length);

    // Shaft
    const shaftGeometry = new THREE.BufferGeometry().setFromPoints([start, end]);
    let shaftMaterial;
    if (dashed) {
        shaftMaterial = new THREE.LineDashedMaterial({ color: color, dashSize: 0.2, gapSize: 0.1 });
    } else {
        shaftMaterial = new THREE.LineBasicMaterial({ color: color });
    }
    const shaft = new THREE.Line(shaftGeometry, shaftMaterial);
    if (dashed) {
        shaft.computeLineDistances();
    }
    parent.add(shaft);

    // Arrow tip
    const headLength = 0.2;
    const headRadius = 0.08;
    const coneGeometry = new THREE.ConeGeometry(headRadius, headLength, 16);
    coneGeometry.translate(0, headLength / 2, 0);
    const coneMaterial = new THREE.MeshBasicMaterial({ color: color });
    const cone = new THREE.Mesh(coneGeometry, coneMaterial);
    const up = new THREE.Vector3(0, 1, 0);
    cone.quaternion.setFromUnitVectors(up, dir);
    cone.position.copy(end.clone().sub(dir.clone().multiplyScalar(headLength)));
    parent.add(cone);
}

// --- NEW: Create Inertial Frame Axes (solid) ---
createAxis(scene, [1, 0, 0], 0xff0000, 5, false);
createAxis(scene, [0, 1, 0], 0x00ff00, 5, false);
createAxis(scene, [0, 0, 1], 0x0000ff, 5, false);

// --- NEW: Create Body-Fixed Frame Axes (dashed) ---
// We add these to the cuboid object itself, so they rotate with it.
createAxis(cuboid, [1, 0, 0], 0xff0000, 3, true);
createAxis(cuboid, [0, 1, 0], 0x00ff00, 3, true);
createAxis(cuboid, [0, 0, 1], 0x0000ff, 3, true);


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
// Connect to the same host that served this page, using the same port as HTTP
const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
const socket = new WebSocket(`${protocol}//${window.location.host}`);
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
