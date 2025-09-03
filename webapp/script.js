// --- Basic Setup ---
const metricsDiv = document.getElementById('metrics');
const simInfoDiv = document.getElementById('sim-info');
const configBtn = document.getElementById('config-btn');
// Simple tabs behavior for left panel
document.querySelectorAll('#left-panel .tab').forEach(tab => {
    tab.addEventListener('click', () => {
        const group = tab.closest('#left-panel');
        const target = tab.getAttribute('data-tab');
        group.querySelectorAll('.tab').forEach(t => { t.classList.remove('active'); t.setAttribute('aria-selected', 'false'); });
        group.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));
        tab.classList.add('active');
        tab.setAttribute('aria-selected', 'true');
        const panel = group.querySelector(`.tab-panel[data-tab="${target}"]`);
        if (panel) panel.classList.add('active');
    });
});
const rendererContainer = document.getElementById('renderer-container');
const mainVis = document.getElementById('main-vis');
const playPauseBtn = document.getElementById('playPauseBtn');
const timelineSlider = document.getElementById('timelineSlider');
const timeLabel = document.getElementById('timeLabel');

let latestQuat = { x: 0, y: 0, z: 0, w: 1 };
let isPaused = false;

function fmtTime(seconds) {
    const s = Math.max(0, Math.floor(seconds));
    const m = Math.floor(s / 60);
    const r = s % 60;
    return `${String(m).padStart(2,'0')}:${String(r).padStart(2,'0')}`;
}

// --- 3D Scene Setup ---
const scene = new THREE.Scene();
const camera = new THREE.PerspectiveCamera(75, window.innerWidth / window.innerHeight, 0.1, 1000);
const renderer = new THREE.WebGLRenderer({ antialias: true });
renderer.setPixelRatio(window.devicePixelRatio || 1);
renderer.setSize(window.innerWidth, window.innerHeight);
rendererContainer.appendChild(renderer.domElement);
const controls = new THREE.OrbitControls(camera, mainVis);
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

// Keep the 3D view visually centered on the center panel while allowing spill under the left panel
function repositionRenderer() {
    try {
        const container = document.getElementById('container');
        const leftPanel = document.getElementById('left-panel');
        const plots = document.getElementById('plots-container');
        if (!container || !leftPanel || !plots) return;
        const W = container.clientWidth;
        const leftW = leftPanel.offsetWidth;
        const rightW = plots.offsetWidth;
        const dx = (leftW - rightW) / 2; // shift so scene center aligns with center panel center
        rendererContainer.style.transform = `translateX(${dx}px)`;
    } catch (_) {
        // no-op
    }
}
repositionRenderer();

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
createPlotlyChart('qxPlot', 'q_x', '#ff6384', [-1, 1]);
createPlotlyChart('qyPlot', 'q_y', '#36a2eb', [-1, 1]);
createPlotlyChart('qzPlot', 'q_z', '#4bc0c0', [-1, 1]);
createPlotlyChart('qwPlot', 'q_w (scalar)', '#e6e600', [-1, 1]);
createPlotlyChart('pPlot', 'Roll Rate', '#ff9f40', [-5, 5]);
createPlotlyChart('qPlot', 'Pitch Rate', '#9966ff', [-5, 5]);
createPlotlyChart('rPlot', 'Yaw Rate', '#c9cbcf', [-5, 5]);

// WebSocket & Controls
const wsScheme = window.location.protocol === 'https:' ? 'wss' : 'ws';
const wsHost = window.location.host;
const socket = new WebSocket(`${wsScheme}://${wsHost}/ws`);
let dataset = null;
let metrics = null;
let frameIndex = 0;
let playbackTimer = null;
let precomputedDataLoaded = false;

function updateTimeLabel(i) {
    if (!dataset) return;
    const t = dataset.t[i] || 0;
    const tmax = dataset.t[dataset.t.length - 1] || 0;
    timeLabel.textContent = `${fmtTime(t)} / ${fmtTime(tmax)}`;
}

function updateAllVisuals(index, isScrubbing = false) {
    if (!dataset || index < 0 || index >= dataset.t.length) return;
    const i = Math.min(index, dataset.t.length - 1);
    latestQuat = { x: dataset.qx[i], y: dataset.qy[i], z: dataset.qz[i], w: dataset.qw[i] };
    timelineSlider.value = i;
    updateTimeLabel(i);

    const allPlots = ['qxPlot', 'qyPlot', 'qzPlot', 'qwPlot', 'pPlot', 'qPlot', 'rPlot'];
    const dataKeys = ['qx', 'qy', 'qz', 'qw', 'p', 'q', 'r'];

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
            Plotly.extendTraces('qxPlot',  { x: [[tx]], y: [[dataset.qx[i]]] }, traceIndices);
            Plotly.extendTraces('qyPlot', { x: [[tx]], y: [[dataset.qy[i]]] }, traceIndices);
            Plotly.extendTraces('qzPlot',   { x: [[tx]], y: [[dataset.qz[i]]] }, traceIndices);
            Plotly.extendTraces('qwPlot',   { x: [[tx]], y: [[dataset.qw[i]]] }, traceIndices);
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

function renderMetrics(m) {
    if (!metricsDiv || !m) return;
    const rows = [
        ['Compute time', `${(m.compute_time_s || 0).toFixed(3)} s`],
        ['Integration points (N)', `${m.num_integration_points ?? '—'}`],
        ['Time per step', `${(m.time_per_integration_point_s || 0).toExponential(2)} s/step`],
        ['Solver state size', `${m.solver_state_size_readable || '—'} (${m.solver_state_size_bytes || 0} B)`]
    ];
    const html = rows.map(([k,v]) => `<div><span style="color:#8fa1b3">${k}:</span> <span style="color:#e6eefc">${v}</span></div>`).join('');
    metricsDiv.innerHTML = html;
}

function renderSimInfo(m) {
    if (!simInfoDiv) return;
    const totalTime = (dataset && dataset.t && dataset.t.length > 0) ? dataset.t[dataset.t.length - 1] : (m && m.simulation_time_s) || 0;
    const numSamples = (dataset && dataset.t && dataset.t.length) || (m && m.num_integration_points) || 0;
    const sr = (dataset && dataset.sample_rate) || (m && m.sample_rate) || '—';
    const pbs = (m && m.playback_speed) || 1;
    const tmax = (m && m.t_max) || (typeof totalTime === 'number' ? totalTime : '—');
    const rows = [
        ['Sim time', `${(Number(totalTime) || 0).toFixed(2)} s`],
        ['Samples (N)', `${numSamples}`],
        ['Sample rate', `${sr} Hz`],
        ['Playback speed', `${pbs}x`],
        ['t_max', `${tmax} s`]
    ];
    const html = rows.map(([k,v]) => `<div><span style="color:#8fa1b3">${k}:</span> <span style="color:#e6eefc">${v}</span></div>`).join('');
    simInfoDiv.innerHTML = html;
}

function startPlaybackFromDataset(data, m=null) {
    dataset = data;
    metrics = m;
    if (metrics) {
        renderMetrics(metrics);
        renderSimInfo(metrics);
    }
    frameIndex = 0;
    if (typeof Plotly !== 'undefined') {
        try {
            Plotly.restyle('qxPlot', { x: [[]], y: [[]] }, [0]);
            Plotly.restyle('qyPlot', { x: [[]], y: [[]] }, [0]);
            Plotly.restyle('qzPlot', { x: [[]], y: [[]] }, [0]);
            Plotly.restyle('qwPlot', { x: [[]], y: [[]] }, [0]);
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
            // Also try to read metrics if present (future-proof)
            const preMetrics = sessionStorage.getItem('precomputed_metrics');
            const m = preMetrics ? JSON.parse(preMetrics) : null;
            startPlaybackFromDataset(data, m);
            sessionStorage.removeItem('precomputed_dataset');
            if (preMetrics) sessionStorage.removeItem('precomputed_metrics');
            precomputedDataLoaded = true;
        } catch (e) {
            console.warn('Failed to parse precomputed dataset.', e);
        }
    }
})();

socket.onopen = () => {
    if (precomputedDataLoaded) {
        return;
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
        startPlaybackFromDataset(msg.dataset, msg.metrics || null);
    }
};

socket.onclose = () => {};
socket.onerror = () => {};

// Animation loop
function animate() {
    requestAnimationFrame(animate);
    cuboid.quaternion.set(latestQuat.x, latestQuat.y, latestQuat.z, latestQuat.w);
    controls.update();
    renderer.render(scene, camera);
}
animate();

window.addEventListener('resize', () => {
    camera.aspect = window.innerWidth / window.innerHeight;
    camera.updateProjectionMatrix();
    renderer.setSize(window.innerWidth, window.innerHeight);
    repositionRenderer();
}, false);

// Prevent player controls from affecting OrbitControls interactions
const playerControlsEl = document.getElementById('playerControls');
if (playerControlsEl) {
    ['pointerdown', 'mousedown', 'touchstart', 'wheel'].forEach(evt => {
        playerControlsEl.addEventListener(evt, e => e.stopPropagation());
    });
}

// Change configuration button behavior
if (configBtn) {
    configBtn.addEventListener('click', () => {
        window.location.href = '/';
    });
}
