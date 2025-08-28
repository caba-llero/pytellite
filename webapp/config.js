async function fetchDefaults() {
    const res = await fetch('/api/defaults');
    return res.json();
}

function setValue(id, value) {
    const el = document.getElementById(id);
    if (el) el.value = value;
}

function readNumber(id) {
    const el = document.getElementById(id);
    if (!el) return null;
    const v = parseFloat(el.value);
    return isNaN(v) ? null : v;
}

function navigateToSimulation(params) {
    const filtered = Object.fromEntries(Object.entries(params).filter(([_, v]) => v !== null && v !== undefined && v !== ''));
    const query = new URLSearchParams(filtered).toString();
    window.location.href = '/simulation?' + query;
}

async function init() {
    const defaults = await fetchDefaults();
    const [j1, j2, j3] = defaults.spacecraft.inertia;
    const [sx, sy, sz] = defaults.spacecraft.shape;
    const [wx, wy, wz] = defaults.initial_conditions.omega_bi_radps;
    const [qx, qy, qz, qw] = defaults.initial_conditions.q_bi;
    const sim = defaults.simulation || {};
    const tmax = sim.t_max ?? 1000.0;
    const play = sim.playback_speed ?? 1.0;
    const sr = sim.sample_rate ?? 30.0;
    const rtol = sim.rtol ?? 1e-12;
    const atol = sim.atol ?? 1e-12;

    setValue('J1', j1);
    setValue('J2', j2);
    setValue('J3', j3);
    setValue('SX', sx);
    setValue('SY', sy);
    setValue('SZ', sz);
    setValue('WX', wx);
    setValue('WY', wy);
    setValue('WZ', wz);
    setValue('QX', qx);
    setValue('QY', qy);
    setValue('QZ', qz);
    setValue('QW', qw);
    setValue('TMAX', tmax);
    setValue('PLAY', play);
    setValue('SR', sr);
    setValue('RTOL', rtol);
    setValue('ATOL', atol);

    // Tabs behavior
    const tabs = document.querySelectorAll('.tab');
    const panels = document.querySelectorAll('.tab-panel');
    tabs.forEach(tab => {
        tab.addEventListener('click', () => {
            const target = tab.getAttribute('data-tab');
            tabs.forEach(t => { t.classList.remove('active'); t.setAttribute('aria-selected', 'false'); });
            panels.forEach(p => { p.classList.remove('active'); });
            tab.classList.add('active');
            tab.setAttribute('aria-selected', 'true');
            const panel = document.querySelector(`.tab-panel[data-tab="${target}"]`);
            if (panel) panel.classList.add('active');
        });
    });

    document.getElementById('startBtn').addEventListener('click', () => {
        const params = {
            j1: readNumber('J1'), j2: readNumber('J2'), j3: readNumber('J3'),
            sx: readNumber('SX'), sy: readNumber('SY'), sz: readNumber('SZ'),
            wx: readNumber('WX'), wy: readNumber('WY'), wz: readNumber('WZ'),
            qx: readNumber('QX'), qy: readNumber('QY'), qz: readNumber('QZ'), qw: readNumber('QW'),
            tmax: readNumber('TMAX'), play: readNumber('PLAY'), sr: readNumber('SR'),
            rtol: readNumber('RTOL'), atol: readNumber('ATOL'),
        };
        navigateToSimulation(params);
    });
}

document.addEventListener('DOMContentLoaded', init);


