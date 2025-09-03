// --- Basic Setup ---
const eulerDiv = document.getElementById('euler-angles');
const rendererContainer = document.getElementById('renderer-container');
const playPauseBtn = document.getElementById('playPauseBtn');
const timelineSlider = document.getElementById('timelineSlider');
const timeLabel = document.getElementById('timeLabel');

let latestAngles = { roll: 0, pitch: 0, yaw: 0 };
let isPaused = false;

function fmtTime(seconds) {
    const s = Math.max(0, Math.floor(seconds));
    const m = Math.floor(s / 60);
    const r = s % 60;
    return `${String(m).padStart(2,'0')}:${String(r).padStart(2,'0')}`;
}

// --- 3D Scene Setup ---
const scene = new THREE.Scene();
const camera = new THREE.PerspectiveCamera(75, rendererContainer.clientWidth / rendererContainer.clientHeight, 0.1, 1000);
const renderer = new THREE.WebGLRenderer({ antialias: true });
renderer.setSize(rendererContainer.clientWidth, rendererContainer.clientHeight);
rendererContainer.appendChild(renderer.domElement);
const controls = new THREE.OrbitControls(camera, renderer.domElement);
controls.enableDamping = true;
camera.position.set(4, 4, 4);

// Cuboid dimensions
const urlParams = new URLSearchParams(window.location.search);
const sizeX = parseFloat(urlParams.get('sx') || '2');
const sizeY = parseFloat(urlParams.get('sy') || '1');
const sizeZ = parseFloat(urlParams.get('sz') || '0.5');
const cuboid = new THREE.Mesh(new THREE.BoxGeometry(sizeX, sizeY, sizeZ), new THREE.MeshNormalMaterial());
scene.add(cuboid);

// Axes helpers
function createAxis(parent, direction, color, length, dashed = false) {
    const dir = new THREE.Vector3(...direction).normalize();
    const start = new THREE.Vector3(0, 0, 0);
    const end = dir.clone().multiplyScalar(length);
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
createAxis(scene, [1, 0, 0], 0xff0000, 5, false);
createAxis(scene, [0, 1, 0], 0x00ff00, 5, false);
createAxis(scene, [0, 0, 1], 0x0000ff, 5, false);
createAxis(cuboid, [1, 0, 0], 0xff0000, 3, true);
createAxis(cuboid, [0, 1, 0], 0x00ff00, 3, true);
createAxis(cuboid, [0, 0, 1], 0x0000ff, 3, true);

// Plotly charts
function createPlotlyChart(divId, title, color, y_range) {
    try {
        if (typeof Plotly === 'undefined') return;
        const data = [{ x: [], y: [], type: 'scatter', mode: 'lines', line: { color: color, width: 2 } }];
        const layout = {
            title: { text: title, font: { color: 'white', size: 14 } },
            paper_bgcolor: '#1a1a1a', plot_bgcolor: '#1a1a1a',
            margin: { l: 40, r: 20, b: 30, t: 40, pad: 4 },
            xaxis: { color: 'white', gridcolor: '#444' },
            yaxis: { color: 'white', gridcolor: '#444', range: y_range }
        };
        Plotly.newPlot(divId, data, layout, { responsive: true });
    } catch (e) {
        // If Plotly fails to load, skip charts gracefully
        console.warn('Plotly unavailable, skipping charts.', e);
    }
}
createPlotlyChart('rollPlot', 'Roll (X)', '#ff6384', [-Math.PI, Math.PI]);
createPlotlyChart('pitchPlot', 'Pitch (Y)', '#36a2eb', [-Math.PI, Math.PI]);
createPlotlyChart('yawPlot', 'Yaw (Z)', '#4bc0c0', [-Math.PI, Math.PI]);
createPlotlyChart('pPlot', 'Roll Rate', '#ff9f40', [-5, 5]);
createPlotlyChart('qPlot', 'Pitch Rate', '#9966ff', [-5, 5]);
createPlotlyChart('rPlot', 'Yaw Rate', '#c9cbcf', [-5, 5]);

// WebSocket & Controls
const wsScheme = window.location.protocol === 'https:' ? 'wss' : 'ws';
const wsHost = window.location.host;
const socket = new WebSocket(`${wsScheme}://${wsHost}/ws`);
let dataset = null;
let frameIndex = 0;
let playbackTimer = null;

function updateTimeLabel(i) {
    if (!dataset) return;
    const t = dataset.t[i] || 0;
    const tmax = dataset.t[dataset.t.length - 1] || 0;
    timeLabel.textContent = `${fmtTime(t)} / ${fmtTime(tmax)}`;
}

function updateAllVisuals(index, isScrubbing = false) {
    if (!dataset || index < 0 || index >= dataset.t.length) return;
    const i = Math.min(index, dataset.t.length - 1);
    latestAngles = { roll: dataset.roll[i], pitch: dataset.pitch[i], yaw: dataset.yaw[i] };
    timelineSlider.value = i;
    updateTimeLabel(i);

    const allPlots = ['rollPlot', 'pitchPlot', 'yawPlot', 'pPlot', 'qPlot', 'rPlot'];
    const dataKeys = ['roll', 'pitch', 'yaw', 'p', 'q', 'r'];

    if (isScrubbing) {
        if (typeof Plotly !== 'undefined') {
            for (let j = 0; j < allPlots.length; j++) {
                const trace = {
                    x: [dataset.t.slice(0, i + 1)],
                    y: [dataset[dataKeys[j]].slice(0, i + 1)]
                };
                Plotly.restyle(allPlots[j], trace, [0]);
            }
        }
    } else {
        if (typeof Plotly !== 'undefined') {
            const tx = dataset.t[i];
            const traceIndices = [0];
            Plotly.extendTraces('rollPlot',  { x: [[tx]], y: [[dataset.roll[i]]] }, traceIndices);
            Plotly.extendTraces('pitchPlot', { x: [[tx]], y: [[dataset.pitch[i]]] }, traceIndices);
            Plotly.extendTraces('yawPlot',   { x: [[tx]], y: [[dataset.yaw[i]]] }, traceIndices);
            Plotly.extendTraces('pPlot',     { x: [[tx]], y: [[dataset.p[i]]] }, traceIndices);
            Plotly.extendTraces('qPlot',     { x: [[tx]], y: [[dataset.q[i]]] }, traceIndices);
            Plotly.extendTraces('rPlot',     { x: [[tx]], y: [[dataset.r[i]]] }, traceIndices);
        }
    }
}

function setPlayingState(playing) {
    if (playing) {
        playPauseBtn.classList.add('playing');
        isPaused = false;
    } else {
        playPauseBtn.classList.remove('playing');
        isPaused = true;
    }
}

playPauseBtn.addEventListener('click', () => {
    setPlayingState(isPaused); // toggle state
});

timelineSlider.addEventListener('input', () => {
    setPlayingState(false);
    const newIndex = parseInt(timelineSlider.value, 10);
    if (newIndex !== frameIndex) {
        frameIndex = newIndex;
        updateAllVisuals(frameIndex, true);
    }
});

function startPlaybackFromDataset(data) {
    dataset = data;
    frameIndex = 0;
    if (typeof Plotly !== 'undefined') {
        try {
            Plotly.restyle('rollPlot', { x: [[]], y: [[]] }, [0]);
            Plotly.restyle('pitchPlot', { x: [[]], y: [[]] }, [0]);
            Plotly.restyle('yawPlot', { x: [[]], y: [[]] }, [0]);
            Plotly.restyle('pPlot', { x: [[]], y: [[]] }, [0]);
            Plotly.restyle('qPlot', { x: [[]], y: [[]] }, [0]);
            Plotly.restyle('rPlot', { x: [[]], y: [[]] }, [0]);
        } catch (e) {
            console.warn('Plotly restyle failed, continuing.', e);
        }
    }
    timelineSlider.max = dataset.t.length - 1;
    updateAllVisuals(0, true);
    setPlayingState(true);
    if (playbackTimer) clearInterval(playbackTimer);
    const intervalMs = 1000.0 / (dataset.sample_rate || 30.0);
    playbackTimer = setInterval(() => {
        if (!dataset || isPaused) return;
        const n = dataset.t.length;
        if (n === 0 || frameIndex >= n - 1) return;
        frameIndex++;
        updateAllVisuals(frameIndex);
    }, intervalMs);
}

// Attempt to start from precomputed dataset immediately (without waiting for WS)
(function tryPrecomputedPlayback() {
    const pre = sessionStorage.getItem('precomputed_dataset');
    if (pre) {
        try {
            const data = JSON.parse(pre);
            startPlaybackFromDataset(data);
            sessionStorage.removeItem('precomputed_dataset');
        } catch (e) {
            console.warn('Failed to parse precomputed dataset.', e);
        }
    }
})();

socket.onopen = () => {
    eulerDiv.innerHTML = "Connected";
    const pre = sessionStorage.getItem('precomputed_dataset');
    if (pre) {
        try {
            const data = JSON.parse(pre);
            startPlaybackFromDataset(data);
            sessionStorage.removeItem('precomputed_dataset');
            return;
        } catch {}
    }

    // configure via websocket
    const inertia = [urlParams.get('j1'), urlParams.get('j2'), urlParams.get('j3')].map(v => v !== null ? parseFloat(v) : null);
    const shape = [urlParams.get('sx'), urlParams.get('sy'), urlParams.get('sz')].map(v => v !== null ? parseFloat(v) : null);
    const q_bi = [urlParams.get('qx'), urlParams.get('qy'), urlParams.get('qz'), urlParams.get('qw')].map(v => v !== null ? parseFloat(v) : null);
    const omega = [urlParams.get('wx'), urlParams.get('wy'), urlParams.get('wz')].map(v => v !== null ? parseFloat(v) : null);
    const tmax = urlParams.get('tmax');
    const play = urlParams.get('play');
    const sr = urlParams.get('sr');
    const rtol = urlParams.get('rtol');
    const atol = urlParams.get('atol');
    const ctrl = urlParams.get('ctrl');
    const kp = urlParams.get('kp');
    const kd = urlParams.get('kd');
    const cq0 = urlParams.get('cq0');
    const cq1 = urlParams.get('cq1');
    const cq2 = urlParams.get('cq2');
    const cq3 = urlParams.get('cq3');

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
    if (ctrl) payload.control_type = ctrl;
    if (kp !== null) payload.kp = parseFloat(kp);
    if (kd !== null) payload.kd = parseFloat(kd);
    const qc = [cq0, cq1, cq2, cq3].map(v => v !== null ? parseFloat(v) : null);
    if (qc.every(v => typeof v === 'number' && !isNaN(v))) payload.qc = qc;

    if (Object.keys(payload).length > 0) {
        socket.send(JSON.stringify({ command: 'configure', payload }));
    } else {
        socket.send(JSON.stringify({ command: 'configure', payload: {} }));
    }
};

socket.onmessage = (event) => {
    const msg = JSON.parse(event.data);
    if (msg.dataset) {
        startPlaybackFromDataset(msg.dataset);
    }
};

socket.onclose = () => eulerDiv.innerHTML = "Connection Closed.";
socket.onerror = () => eulerDiv.innerHTML = "Connection Error!";

// Animation loop
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
