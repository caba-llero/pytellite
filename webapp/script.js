// --- Basic Setup ---
const metricsDiv = document.getElementById('metrics');
const simInfoDiv = document.getElementById('sim-info');
const configBtn = document.getElementById('config-btn');
const legendOverlay = document.getElementById('legend-content');
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
const plotModeInputs = document.querySelectorAll('input[name="plotMode"]');
const groundTruthSection = document.getElementById('groundTruthPlots');
const errorSection = document.getElementById('errorPlots');
const errorPlotsUnavailable = document.getElementById('errorPlotsUnavailable');
const angleUnitSelect = document.getElementById('angleUnitSelect');
const orbitStatusBanner = document.getElementById('orbit-status');

let currentPlotMode = 'ground_truth';
let requestedPlotMode = 'ground_truth';
let latestQuat = { x: 0, y: 0, z: 0, w: 1 };
let isPaused = false;

function fmtTime(seconds) {
    const s = Math.max(0, Math.floor(seconds));
    const m = Math.floor(s / 60);
    const r = s % 60;
    return `${String(m).padStart(2,'0')}:${String(r).padStart(2,'0')}`;
}

// --- 3D Scene Setup ---
const attitudeScene = new THREE.Scene();
const orbitScene = new THREE.Scene();
let currentView = 'attitude'; // 'attitude' | 'orbit'
const camera = new THREE.PerspectiveCamera(75, window.innerWidth / window.innerHeight, 0.1, 1000);
// Use Z-up visualization (does not affect simulation frames)
camera.up.set(0, 0, 1);
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
attitudeScene.add(cuboid);

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
createAxis(attitudeScene, [1, 0, 0], 0xff0000, 5, false);
createAxis(attitudeScene, [0, 1, 0], 0x00ff00, 5, false);
createAxis(attitudeScene, [0, 0, 1], 0x0000ff, 5, false);
createAxis(cuboid, [1, 0, 0], 0xff0000, 3, true);
createAxis(cuboid, [0, 1, 0], 0x00ff00, 3, true);
createAxis(cuboid, [0, 0, 1], 0x0000ff, 3, true);

// Orbit scene: Earth sphere at origin and ECI axes
const earthRadius = 1.0;
const earthGeometry = new THREE.SphereGeometry(earthRadius, 32, 32);
const earthTextureLoader = new THREE.TextureLoader();
const earthTexture = earthTextureLoader.load('/textures/earth_daymap.jpg');
earthTexture.colorSpace = THREE.SRGBColorSpace || THREE.sRGBEncoding; // compatibility across versions
const earthMaterial = new THREE.MeshPhongMaterial({ map: earthTexture });
const earth = new THREE.Mesh(earthGeometry, earthMaterial);
// Align Earth's rotation axis with +Z (north up)
earth.rotation.x = Math.PI / 2;
// Add a simple light for Phong material
const orbitAmbient = new THREE.AmbientLight(0x404040, 0.8);
const orbitDirectional = new THREE.DirectionalLight(0xffffff, 1.0);
orbitDirectional.position.set(5, 5, 5);
orbitScene.add(orbitAmbient);
orbitScene.add(orbitDirectional);
// Group for Earth + ECEF axes so we can rotate relative to fixed ECI
const ecefGroup = new THREE.Group();
ecefGroup.add(earth);
orbitScene.add(ecefGroup);
// ECI axes (fixed)
createAxis(orbitScene, [1, 0, 0], 0xff0000, 5, false);
createAxis(orbitScene, [0, 1, 0], 0x00ff00, 5, false);
createAxis(orbitScene, [0, 0, 1], 0x0000ff, 5, false);
// ECEF axes (rotate with Earth)
createAxis(ecefGroup, [1, 0, 0], 0xaa4444, 4, true);
createAxis(ecefGroup, [0, 1, 0], 0x44aa44, 4, true);
createAxis(ecefGroup, [0, 0, 1], 0x4444aa, 4, true);

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

// Legend switching
function renderLegend(view) {
    if (!legendOverlay) return;
    if (view === 'orbit') {
        legendOverlay.innerHTML = `
            <div class="legend-section"><span class="legend-line dashed"></span><span class="legend-text">Spacecraft body axes</span></div>
            <div class="legend-section"><span class="legend-line solid"></span><span class="legend-text">Earth Centered Inertial</span></div>
            <div class="legend-section"><span class="legend-line dashdot"></span><span class="legend-text">Earth Centered Earth Fixed</span></div>
            <div class="legend-section legend-colors">
                <span class="legend-color x"></span><span class="legend-axis-label">X</span>
                <span class="legend-color y"></span><span class="legend-axis-label">Y</span>
                <span class="legend-color z"></span><span class="legend-axis-label">Z</span>
            </div>
            <div class="legend-note">Vernal equinox: X on the ECI frame</div>
        `;
    } else {
        legendOverlay.innerHTML = `
            <div class="legend-section"><span class="legend-line solid"></span><span class="legend-text">Inertial axes</span></div>
            <div class="legend-section"><span class="legend-line dashed"></span><span class="legend-text">Body axes</span></div>
            <div class="legend-section legend-colors">
                <span class="legend-color x"></span><span class="legend-axis-label">X</span>
                <span class="legend-color y"></span><span class="legend-axis-label">Y</span>
                <span class="legend-color z"></span><span class="legend-axis-label">Z</span>
            </div>
        `;
    }
}
renderLegend('attitude');

// Plotly charts
const timeUnitSelect = document.getElementById('timeUnitSelect');
const omegaUnitSelect = document.getElementById('omegaUnitSelect');
let estimationEnabled = false;
let errorData = null;
let groundTruthPlotsInitialised = false;

function hasErrorData() {
    return !!(estimationEnabled && errorData && Array.isArray(errorData.Zdx) && Array.isArray(errorData.sigma));
}

function syncPlotModeRadios(mode) {
    plotModeInputs.forEach(input => {
        const isActive = input.value === mode;
        input.checked = isActive;
        input.setAttribute('aria-checked', isActive ? 'true' : 'false');
    });
}

function setPlotMode(mode, { syncRadios = true, refresh = true, persistRequest = true, force = false } = {}) {
    const normalized = mode === 'estimate_errors' ? 'estimate_errors' : 'ground_truth';
    if (persistRequest || force) {
        requestedPlotMode = normalized;
    }
    currentPlotMode = normalized;
    if (syncRadios && plotModeInputs.length) {
        syncPlotModeRadios(normalized);
    }
    if (groundTruthSection) groundTruthSection.classList.toggle('hidden', normalized !== 'ground_truth');
    if (errorSection) errorSection.classList.toggle('hidden', normalized !== 'estimate_errors');

    if (!refresh || !dataset) return;

    if (normalized === 'estimate_errors') {
        const dataAvailable = hasErrorData();
        if (errorSection) errorSection.classList.toggle('no-data', !dataAvailable);
        if (errorPlotsUnavailable) {
            if (dataAvailable) {
                errorPlotsUnavailable.classList.add('hidden');
                errorPlotsUnavailable.setAttribute('aria-hidden', 'true');
            } else {
                errorPlotsUnavailable.classList.remove('hidden');
                errorPlotsUnavailable.removeAttribute('aria-hidden');
            }
        }
        if (dataAvailable) {
            redrawErrorPlots(frameIndex);
        }
    } else {
        if (errorSection) errorSection.classList.remove('no-data');
        if (errorPlotsUnavailable) {
            errorPlotsUnavailable.classList.add('hidden');
            errorPlotsUnavailable.setAttribute('aria-hidden', 'true');
        }
        rebuildSeriesUpTo(frameIndex);
    }
}

plotModeInputs.forEach(input => {
    input.addEventListener('change', (e) => {
        if (!e.target.checked) return;
        setPlotMode(e.target.value);
    });
});

setPlotMode(currentPlotMode, { syncRadios: true, refresh: false });

function getTimeFactor() {
    const unit = (timeUnitSelect && timeUnitSelect.value) || 's';
    if (unit === 'm') return 1/60;
    if (unit === 'h') return 1/3600;
    return 1;
}

function getTimeUnitLabel() {
    const unit = (timeUnitSelect && timeUnitSelect.value) || 's';
    if (unit === 'm') return 'min';
    if (unit === 'h') return 'h';
    return 's';
}

function getOmegaFactor() {
    const unit = (omegaUnitSelect && omegaUnitSelect.value) || 'rad';
    return unit === 'deg' ? (180/Math.PI) : 1;
}

function createMultiTraceChart(divId, yAxisTitle, traces) {
    try {
    if (typeof Plotly === 'undefined') return;
        const data = traces.map(t => ({ x: [], y: [], type: 'scatter', mode: 'lines', line: { color: t.color, width: 2 }, name: t.name }));
        const layout = {
            paper_bgcolor: 'rgba(0,0,0,0)', plot_bgcolor: 'rgba(0,0,0,0)',
            margin: { l: 40, r: 20, b: 30, t: 10, pad: 4 },
            xaxis: { color: 'white', gridcolor: '#222' },
            yaxis: {
                color: 'white',
                gridcolor: '#222',
                automargin: true,
                title: { text: yAxisTitle, font: { color: 'white', size: 12 }, standoff: 12 }
            },
            showlegend: false
        };
        Plotly.newPlot(divId, data, layout, { responsive: true });
    } catch (e) {
        console.warn('Plotly unavailable, skipping charts.', e);
    }
}

// Colors aligned with 3D axes: x red, y green, z blue; quaternion scalar white

function rebuildSeriesUpTo(index) {
    if (!dataset || typeof Plotly === 'undefined') return;
    const i = Math.min(index, dataset.t.length - 1);
    const tf = getTimeFactor();
    const of = getOmegaFactor();
    const xArr = dataset.t.slice(0, i + 1).map(t => t * tf);
    const restyleMulti = (id, yArrays) => {
        const xs = yArrays.map(() => xArr);
        Plotly.restyle(id, { x: xs, y: yArrays }, [0,1,2,3].slice(0, yArrays.length));
    };
    restyleMulti('quatPlot', [
        dataset.qx.slice(0, i + 1),
        dataset.qy.slice(0, i + 1),
        dataset.qz.slice(0, i + 1),
        dataset.qw.slice(0, i + 1)
    ]);
    restyleMulti('omegaPlot', [
        dataset.p.slice(0, i + 1).map(v => v * of),
        dataset.q.slice(0, i + 1).map(v => v * of),
        dataset.r.slice(0, i + 1).map(v => v * of)
    ]);
    restyleMulti('hPlot', [
        dataset.hx.slice(0, i + 1),
        dataset.hy.slice(0, i + 1),
        dataset.hz.slice(0, i + 1)
    ]);
}

function redrawErrorPlots(index) {
    if (!hasErrorData() || typeof Plotly === 'undefined') {
        return;
    }
    const estimatorTimes = Array.isArray(errorData.time) ? errorData.time : dataset.t;
    const maxLen = Math.min(dataset.t.length, estimatorTimes.length);
    if (maxLen === 0) return;
    const i = Math.min(index, maxLen - 1);
    const tf = getTimeFactor();
    const rawTimes = estimatorTimes.slice(0, i + 1).map(t => Number(t ?? 0));
    const timeSlice = rawTimes.map(t => t * tf);
    const plotError = (plotId, components, sigmaIndices, yAxisTitle, valueTransform = (x) => x) => {
        const traces = [];
        components.forEach((comp) => {
            const series = errorData[comp.key];
            if (!Array.isArray(series)) return;
            const len = Math.min(series.length, timeSlice.length);
            if (len === 0) return;
            traces.push({
                x: timeSlice.slice(0, len),
                y: series.slice(0, len).map(v => valueTransform(Number(v ?? 0))),
                type: 'scatter',
                mode: 'lines',
                line: { color: comp.color, width: 2 },
                name: comp.label
            });
        });
        if (sigmaIndices) {
            sigmaIndices.forEach((sigmaIndex) => {
                const sigmaRow = errorData.sigma?.[sigmaIndex];
                if (!Array.isArray(sigmaRow)) return;
                const len = Math.min(sigmaRow.length, timeSlice.length);
                if (len === 0) return;
                const sigmaSeries = sigmaRow.slice(0, len).map(v => valueTransform(3 * Math.abs(Number(v ?? 0))));
                const xs = timeSlice.slice(0, len);
                traces.push({
                    x: xs,
                    y: sigmaSeries,
                    type: 'scatter',
                    mode: 'lines',
                    line: { color: '#cccccc', width: 1, dash: 'dot' },
                    hoverinfo: 'skip',
                    showlegend: false
                });
                traces.push({
                    x: xs,
                    y: sigmaSeries.map(v => -v),
                    type: 'scatter',
                    mode: 'lines',
                    line: { color: '#cccccc', width: 1, dash: 'dot' },
                    hoverinfo: 'skip',
                    showlegend: false
                });
            });
        }
        if (!traces.length) {
            Plotly.react(plotId, [], { paper_bgcolor: 'rgba(0,0,0,0)', plot_bgcolor: 'rgba(0,0,0,0)' });
            return;
        }
        const layout = {
            paper_bgcolor: 'rgba(0,0,0,0)',
            plot_bgcolor: 'rgba(0,0,0,0)',
            margin: { l: 40, r: 20, b: 30, t: 10, pad: 4 },
            xaxis: { color: 'white', gridcolor: '#222' },
            yaxis: { color: 'white', gridcolor: '#222', automargin: true, title: { text: yAxisTitle, font: { color: 'white', size: 12 } } },
            showlegend: false
        };
        Plotly.react(plotId, traces, layout, { responsive: true });
    };

    plotError('rotErrPlot', [
        { key: 'Zdx', color: '#ff0000', label: 'Z_d,x' },
        { key: 'Zdy', color: '#00ff00', label: 'Z_d,y' },
        { key: 'Zdz', color: '#0000ff', label: 'Z_d,z' }
    ], [0, 1, 2], 'Error rotation vector');

    plotError('biasErrPlot', [
        { key: 'Bdx', color: '#ff0000', label: 'B_d,x' },
        { key: 'Bdy', color: '#00ff00', label: 'B_d,y' },
        { key: 'Bdz', color: '#0000ff', label: 'B_d,z' }
    ], [3, 4, 5], 'Gyro bias error', (v) => v * getOmegaFactor());

    plotError('wErrPlot', [
        { key: 'wErrX', color: '#ff0000', label: 'ω error x' },
        { key: 'wErrY', color: '#00ff00', label: 'ω error y' },
        { key: 'wErrZ', color: '#0000ff', label: 'ω error z' }
    ], null, 'Angular velocity error', (v) => v * getOmegaFactor());
}

// WebSocket & Controls
const wsScheme = window.location.protocol === 'https:' ? 'wss' : 'ws';
const wsHost = window.location.host;
const socket = new WebSocket(`${wsScheme}://${wsHost}/ws`);
let dataset = null;
let metrics = null;
let frameIndex = 0;
let playbackTimer = null;
let precomputedDataLoaded = false;
let earthInitialSiderealAngleRad = 0.0;
let earthSpinRateRadps = 0.0;

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

  if (typeof Plotly === 'undefined') return;

    if (currentPlotMode === 'estimate_errors') {
        redrawErrorPlots(i);
        return;
    }

    if (isScrubbing) {
        rebuildSeriesUpTo(i);
        return;
    }

    const tf = getTimeFactor();
    const of = getOmegaFactor();
    const tx = dataset.t[i] * tf;
    Plotly.extendTraces('quatPlot',  { x: [[tx],[tx],[tx],[tx]], y: [[dataset.qx[i]],[dataset.qy[i]],[dataset.qz[i]],[dataset.qw[i]]] }, [0,1,2,3]);
    Plotly.extendTraces('omegaPlot', { x: [[tx],[tx],[tx]], y: [[dataset.p[i] * of],[dataset.q[i] * of],[dataset.r[i] * of]] }, [0,1,2]);
    Plotly.extendTraces('hPlot',     { x: [[tx],[tx],[tx]], y: [[dataset.hx[i]],[dataset.hy[i]],[dataset.hz[i]]] }, [0,1,2]);
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
    // Read Earth rotation parameters from dataset
    earthInitialSiderealAngleRad = Number(data.earth_initial_sidereal_angle_rad || 0.0) || 0.0;
    earthSpinRateRadps = Number(data.earth_spin_rate_radps || 0.0) || 0.0;
    if (metrics) {
        renderMetrics(metrics);
        renderSimInfo(metrics);
    }
    frameIndex = 0;
    if (typeof Plotly !== 'undefined' && !groundTruthPlotsInitialised) {
        createMultiTraceChart('quatPlot', 'Attitude quaternion', [
            { name: 'q<sub>x</sub>', color: '#ff0000' },
            { name: 'q<sub>y</sub>', color: '#00ff00' },
            { name: 'q<sub>z</sub>', color: '#0000ff' },
            { name: 'q<sub>w</sub>', color: '#ffffff' }
        ]);
        createMultiTraceChart('omegaPlot', 'Angular velocity', [
            { name: 'ω<sub>x</sub>', color: '#ff0000' },
            { name: 'ω<sub>y</sub>', color: '#00ff00' },
            { name: 'ω<sub>z</sub>', color: '#0000ff' }
        ]);
        createMultiTraceChart('hPlot', 'Wheel angular momentum', [
            { name: 'h<sub>x</sub>', color: '#ff0000' },
            { name: 'h<sub>y</sub>', color: '#00ff00' },
            { name: 'h<sub>z</sub>', color: '#0000ff' }
        ]);
        groundTruthPlotsInitialised = true;
    }

    timelineSlider.max = dataset.t.length - 1;
    updateAllVisuals(0, true);
    if (!hasErrorData()) {
        if (requestedPlotMode === 'estimate_errors') {
            setPlotMode('estimate_errors', { syncRadios: true, refresh: true, persistRequest: false });
        } else {
            setPlotMode('ground_truth', { syncRadios: true, refresh: true, persistRequest: false });
        }
    } else if (requestedPlotMode === 'estimate_errors') {
        setPlotMode('estimate_errors', { syncRadios: true, refresh: true });
    } else {
        setPlotMode('ground_truth', { syncRadios: true, refresh: true, persistRequest: false });
    }
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
    const preErrors = sessionStorage.getItem('precomputed_errors');
    if (pre) {
        try {
            const data = JSON.parse(pre);
            // Also try to read metrics if present (future-proof)
            const preMetrics = sessionStorage.getItem('precomputed_metrics');
            const m = preMetrics ? JSON.parse(preMetrics) : null;
            if (preErrors) {
                try {
                    errorData = JSON.parse(preErrors);
                    estimationEnabled = true;
                } catch (_) {
                    errorData = null;
                    estimationEnabled = false;
                }
            }
            startPlaybackFromDataset(data, m);
            sessionStorage.removeItem('precomputed_dataset');
            if (preMetrics) sessionStorage.removeItem('precomputed_metrics');
            if (preErrors) sessionStorage.removeItem('precomputed_errors');
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
    const epoch = urlParams.get('epoch');
    const enableEstimation = urlParams.get('enable_estimation') === 'true';

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
    if (ctrl === 'inertial_linear') payload.control_type = 'tracking';
    else if (ctrl === 'inertial_nonlinear') payload.control_type = 'nonlinear_tracking';
    else if (ctrl) payload.control_type = ctrl;
    if (kp !== null) payload.kp = parseFloat(kp);
    if (kd !== null) payload.kd = parseFloat(kd);
    const qc = [cq0, cq1, cq2, cq3].map(v => v !== null ? parseFloat(v) : null);
    if (qc.every(v => typeof v === 'number' && !isNaN(v))) payload.qc = qc;
    if (epoch) payload.epoch_utc = epoch;

    if (enableEstimation) {
        payload.estimation = {
            enable_estimation: true,
            ctrl_freq: urlParams.get('ctrl_freq') ? parseFloat(urlParams.get('ctrl_freq')) : null,
            gt_freq: urlParams.get('gt_freq') ? parseFloat(urlParams.get('gt_freq')) : null,
            rng_seed: urlParams.get('rng_seed') ? parseFloat(urlParams.get('rng_seed')) : null,
            gyro_meas_freq: urlParams.get('gyro_meas_freq') ? parseFloat(urlParams.get('gyro_meas_freq')) : null,
            gyro_arw: urlParams.get('gyro_arw') ? parseFloat(urlParams.get('gyro_arw')) : null,
            gyro_rrw: urlParams.get('gyro_rrw') ? parseFloat(urlParams.get('gyro_rrw')) : null,
            gyro_true_bias: urlParams.get('gyro_true_bias') ? parseFloat(urlParams.get('gyro_true_bias')) : null,
            gyro_est_bias: urlParams.get('gyro_est_bias') ? parseFloat(urlParams.get('gyro_est_bias')) : null,
            gyro_init_cov: urlParams.get('gyro_init_cov') ? parseFloat(urlParams.get('gyro_init_cov')) : null,
            star_meas_freq: urlParams.get('star_meas_freq') ? parseFloat(urlParams.get('star_meas_freq')) : null,
            star_iso_acc: urlParams.get('star_iso_acc') ? parseFloat(urlParams.get('star_iso_acc')) : null,
            star_init_acc: urlParams.get('star_init_acc') ? parseFloat(urlParams.get('star_init_acc')) : null,
            attitude_init_cov: urlParams.get('attitude_init_cov') ? parseFloat(urlParams.get('attitude_init_cov')) : null
        };
    }

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
        if (msg.errors) {
            errorData = msg.errors;
            estimationEnabled = true;
            try {
                const preview = (arr, n = 5) => Array.isArray(arr) ? arr.slice(0, n) : arr;
                const diagPreview = Array.isArray(msg.errors.sigma)
                    ? msg.errors.sigma.slice(0, Math.min(6, msg.errors.sigma.length)).map(row => preview(row))
                    : msg.errors.sigma;
                console.log('Estimator snapshot', {
                    time: preview(msg.errors.time),
                    rotationError: {
                        Zdx: preview(msg.errors.Zdx),
                        Zdy: preview(msg.errors.Zdy),
                        Zdz: preview(msg.errors.Zdz),
                    },
                    biasError: {
                        Bdx: preview(msg.errors.Bdx),
                        Bdy: preview(msg.errors.Bdy),
                        Bdz: preview(msg.errors.Bdz),
                    },
                    angularVelError: {
                        wErrX: preview(msg.errors.wErrX),
                        wErrY: preview(msg.errors.wErrY),
                        wErrZ: preview(msg.errors.wErrZ),
                    },
                    sigmaDiag: diagPreview,
                });
            } catch (snapshotErr) {
                console.warn('Failed to log estimator snapshot', snapshotErr);
            }
            setPlotMode(requestedPlotMode, { syncRadios: true, refresh: true, persistRequest: false });
            sessionStorage.removeItem('precomputed_errors');
        } else {
            estimationEnabled = false;
            errorData = null;
            if (currentPlotMode === 'estimate_errors') {
                setPlotMode('ground_truth');
            }
        }
    }
};

socket.onclose = () => {};
socket.onerror = () => {};

// Unit controls handlers
if (timeUnitSelect) {
    timeUnitSelect.addEventListener('change', () => {
        if (currentPlotMode === 'ground_truth') {
            rebuildSeriesUpTo(frameIndex);
        } else if (currentPlotMode === 'estimate_errors') {
            redrawErrorPlots(frameIndex);
        }
    });
}
if (omegaUnitSelect) {
    omegaUnitSelect.addEventListener('change', () => {
        if (currentPlotMode === 'ground_truth') {
            rebuildSeriesUpTo(frameIndex);
        } else if (currentPlotMode === 'estimate_errors') {
            redrawErrorPlots(frameIndex);
        }
    });
}

// Animation loop
function animate() {
    requestAnimationFrame(animate);
    cuboid.quaternion.set(latestQuat.x, latestQuat.y, latestQuat.z, latestQuat.w);
    controls.update();
    // Update ECEF rotation: theta(t) = theta0 + omega * t
    try {
        if (dataset) {
            const tNow = (frameIndex >= 0 && frameIndex < dataset.t.length) ? dataset.t[frameIndex] : 0;
            const theta = earthInitialSiderealAngleRad + earthSpinRateRadps * tNow;
            ecefGroup.rotation.set(0, 0, theta);
        }
    } catch (_) {}
    const activeScene = currentView === 'orbit' ? orbitScene : attitudeScene;
    renderer.render(activeScene, camera);
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

// View toggle behavior (Attitude | Orbit)
(function initViewToggle() {
    const viewToggle = document.getElementById('view-toggle');
    if (!viewToggle) return;
    const buttons = viewToggle.querySelectorAll('.toggle-segment');
    if (orbitStatusBanner) {
        orbitStatusBanner.setAttribute('hidden', 'true');
    }
    buttons.forEach(btn => {
        btn.addEventListener('click', () => {
            buttons.forEach(b => { b.classList.remove('active'); b.setAttribute('aria-pressed', 'false'); });
            btn.classList.add('active');
            btn.setAttribute('aria-pressed', 'true');
            const view = btn.getAttribute('data-view');
            if (view === 'orbit' || view === 'attitude') {
                currentView = view;
                if (orbitStatusBanner) {
                    if (view === 'orbit') {
                        orbitStatusBanner.removeAttribute('hidden');
                    } else {
                        orbitStatusBanner.setAttribute('hidden', 'true');
                    }
                }
                camera.position.set(4, 4, 4);
                controls.target.set(0, 0, 0);
                controls.update();
                renderLegend(currentView);
            }
        });
    });
})();
