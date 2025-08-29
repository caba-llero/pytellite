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

// Cuboid dimensions will be updated from server-provided defaults or config page via URL params
const urlParams = new URLSearchParams(window.location.search);
const sizeX = parseFloat(urlParams.get('sx') || '2');
const sizeY = parseFloat(urlParams.get('sy') || '1');
const sizeZ = parseFloat(urlParams.get('sz') || '0.5');
const cuboid = new THREE.Mesh(new THREE.BoxGeometry(sizeX, sizeY, sizeZ), new THREE.MeshNormalMaterial());
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
// Build dynamic WebSocket URL based on current page location
const wsScheme = window.location.protocol === 'https:' ? 'wss' : 'ws';
const wsHost = window.location.host; // includes hostname:port
const socket = new WebSocket(`${wsScheme}://${wsHost}/ws`);
let timeTick = 0;
let dataset = null;
let frameIndex = 0;
let playbackTimer = null;

pauseButton.addEventListener('click', () => {
    isPaused = !isPaused;
    pauseButton.innerText = isPaused ? 'Resume' : 'Pause';
    const command = { command: isPaused ? 'pause' : 'resume' };
    if (socket.readyState === WebSocket.OPEN) {
        socket.send(JSON.stringify(command));
    }
});

socket.onopen = () => {
    eulerDiv.innerHTML = "Connected";
    // If a precomputed dataset exists, use it directly and skip configure/start
    const pre = sessionStorage.getItem('precomputed_dataset');
    if (pre) {
        try {
            const data = JSON.parse(pre);
            dataset = data;
            sessionStorage.removeItem('precomputed_dataset');
            frameIndex = 0;
            // Kick off playback loop immediately using sample_rate
            if (playbackTimer) clearInterval(playbackTimer);
            const intervalMs = 1000.0 / (dataset.sample_rate || 30.0);
            playbackTimer = setInterval(() => {
                if (!dataset) return;
                if (isPaused) return;
                const n = dataset.t.length;
                if (n === 0) return;
                const i = Math.min(frameIndex, n - 1);
                latestAngles = { roll: dataset.roll[i], pitch: dataset.pitch[i], yaw: dataset.yaw[i] };
                const tx = dataset.t[i];
                const traceIndices = [0];
                Plotly.extendTraces('rollPlot',  { x: [[tx]], y: [[dataset.roll[i]]] }, traceIndices, MAX_DATA_POINTS);
                Plotly.extendTraces('pitchPlot', { x: [[tx]], y: [[dataset.pitch[i]]] }, traceIndices, MAX_DATA_POINTS);
                Plotly.extendTraces('yawPlot',   { x: [[tx]], y: [[dataset.yaw[i]]] }, traceIndices, MAX_DATA_POINTS);
                Plotly.extendTraces('pPlot',     { x: [[tx]], y: [[dataset.p[i]]] }, traceIndices, MAX_DATA_POINTS);
                Plotly.extendTraces('qPlot',     { x: [[tx]], y: [[dataset.q[i]]] }, traceIndices, MAX_DATA_POINTS);
                Plotly.extendTraces('rPlot',     { x: [[tx]], y: [[dataset.r[i]]] }, traceIndices, MAX_DATA_POINTS);
                frameIndex = (frameIndex + 1) % n;
            }, intervalMs);
            return; // Skip websocket configure; we already have data
        } catch {}
    }

    // Fallback to current behavior: configure and let server stream dataset
    const inertia = [urlParams.get('j1'), urlParams.get('j2'), urlParams.get('j3')].map(v => v !== null ? parseFloat(v) : null);
    const shape = [urlParams.get('sx'), urlParams.get('sy'), urlParams.get('sz')].map(v => v !== null ? parseFloat(v) : null);
    const q_bi = [urlParams.get('qx'), urlParams.get('qy'), urlParams.get('qz'), urlParams.get('qw')].map(v => v !== null ? parseFloat(v) : null);
    const omega = [urlParams.get('wx'), urlParams.get('wy'), urlParams.get('wz')].map(v => v !== null ? parseFloat(v) : null);
    const tmax = urlParams.get('tmax');
    const play = urlParams.get('play');
    const sr = urlParams.get('sr');
    const rtol = urlParams.get('rtol');
    const atol = urlParams.get('atol');

    const payload = {};
    if (inertia.every(v => typeof v === 'number' && !isNaN(v))) payload.inertia = inertia;
    if (shape.every(v => typeof v === 'number' && !isNaN(v))) payload.shape = shape;
    if (q_bi.every(v => typeof v === 'number' && !isNaN(v))) payload.q_bi = q_bi;
    if (omega.every(v => typeof v === 'number' && !isNaN(v))) payload.omega_bi_radps = omega;
    if (tmax !== null) payload.t_max = parseFloat(tmax);
    if (play !== null) payload.playback_speed = parseFloat(play);
    if (sr !== null) payload.sample_rate = parseFloat(sr);
    if (rtol !== null) payload.rtol = parseFloat(rtol);
    if (atol !== null) payload.atol = parseFloat(atol);

    if (Object.keys(payload).length > 0) {
        socket.send(JSON.stringify({ command: 'configure', payload }));
    } else {
        socket.send(JSON.stringify({ command: 'configure', payload: {} }));
    }
};
socket.onmessage = (event) => {
    const msg = JSON.parse(event.data);
    if (msg.dataset) {
        dataset = msg.dataset;
        frameIndex = 0;
        // Reset plots (clear existing trace data)
        Plotly.restyle('rollPlot', { x: [[]], y: [[]] }, [0]);
        Plotly.restyle('pitchPlot', { x: [[]], y: [[]] }, [0]);
        Plotly.restyle('yawPlot', { x: [[]], y: [[]] }, [0]);
        Plotly.restyle('pPlot', { x: [[]], y: [[]] }, [0]);
        Plotly.restyle('qPlot', { x: [[]], y: [[]] }, [0]);
        Plotly.restyle('rPlot', { x: [[]], y: [[]] }, [0]);

        // Start or restart playback timer based on sample_rate
        if (playbackTimer) {
            clearInterval(playbackTimer);
        }
        const intervalMs = 1000.0 / (dataset.sample_rate || 30.0);
        playbackTimer = setInterval(() => {
            if (!dataset) return;
            if (isPaused) return;
            const n = dataset.t.length;
            if (n === 0) return;
            const i = Math.min(frameIndex, n - 1);
            latestAngles = { roll: dataset.roll[i], pitch: dataset.pitch[i], yaw: dataset.yaw[i] };
            const tx = dataset.t[i];
            const traceIndices = [0];
            Plotly.extendTraces('rollPlot',  { x: [[tx]], y: [[dataset.roll[i]]] }, traceIndices, MAX_DATA_POINTS);
            Plotly.extendTraces('pitchPlot', { x: [[tx]], y: [[dataset.pitch[i]]] }, traceIndices, MAX_DATA_POINTS);
            Plotly.extendTraces('yawPlot',   { x: [[tx]], y: [[dataset.yaw[i]]] }, traceIndices, MAX_DATA_POINTS);
            Plotly.extendTraces('pPlot',     { x: [[tx]], y: [[dataset.p[i]]] }, traceIndices, MAX_DATA_POINTS);
            Plotly.extendTraces('qPlot',     { x: [[tx]], y: [[dataset.q[i]]] }, traceIndices, MAX_DATA_POINTS);
            Plotly.extendTraces('rPlot',     { x: [[tx]], y: [[dataset.r[i]]] }, traceIndices, MAX_DATA_POINTS);
            frameIndex = (frameIndex + 1) % n;
        }, intervalMs);
    }
};
socket.onclose = () => eulerDiv.innerHTML = "Connection Closed.";
socket.onerror = () => eulerDiv.innerHTML = "Connection Error!";

// --- Animation Loop ---
function animate() {
    requestAnimationFrame(animate);
    // positions and plots updated by playback timer
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
