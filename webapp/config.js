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
    // Redirect to loading page first
    window.location.href = '/loading?' + query;
}

async function init() {
    const defaults = await fetchDefaults();
    // Load persisted values if present
    const saved = JSON.parse(localStorage.getItem('sim_config') || '{}');
    const [j1, j2, j3] = (saved.spacecraft?.inertia) || defaults.spacecraft.inertia;
    const [sx, sy, sz] = (saved.spacecraft?.shape) || defaults.spacecraft.shape;
    const [wx, wy, wz] = (saved.initial_conditions?.omega_bi_radps) || defaults.initial_conditions.omega_bi_radps;
    const [qx, qy, qz, qw] = (saved.initial_conditions?.q_bi) || defaults.initial_conditions.q_bi;
    const sim = saved.simulation || defaults.simulation || {};
    const tmax = sim.t_max ?? 1000.0;
    const play = sim.playback_speed ?? 1.0;
    const sr = sim.sample_rate ?? 30.0;
    const rtol = sim.rtol ?? 1e-12;
    const atol = sim.atol ?? 1e-12;
    const control = saved.control || defaults.control || { control_type: 'none', kp: 0.0, kd: 0.0, qc: [0,0,0,1] };
    
    let ctrlType = control.control_type || 'none';
    if (ctrlType === 'tracking') ctrlType = 'inertial';
    if (ctrlType === 'zero_torque') ctrlType = 'none';

    const kp = control.kp ?? 0.0;
    const kd = control.kd ?? 0.0;
    const [cq0, cq1, cq2, cq3] = control.qc || [0,0,0,1];

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
    // Control fields
    const ctrlSelect = document.getElementById('CTRL_TYPE');
    const ctrlParams = document.getElementById('CTRL_PARAMS');
    if (ctrlSelect) {
        ctrlSelect.value = ctrlType;
        const show = ctrlType === 'inertial';
        ctrlParams.style.display = show ? '' : 'none';
    }
    setValue('KP', kp);
    setValue('KD', kd);
    setValue('CQ0', cq0);
    setValue('CQ1', cq1);
    setValue('CQ2', cq2);
    setValue('CQ3', cq3);

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
            // control params in query string
            ctrl: document.getElementById('CTRL_TYPE')?.value || 'none',
            kp: readNumber('KP'), kd: readNumber('KD'),
            cq0: readNumber('CQ0'), cq1: readNumber('CQ1'), cq2: readNumber('CQ2'), cq3: readNumber('CQ3')
        };
        // persist selections
        const persisted = {
            spacecraft: { inertia: [params.j1, params.j2, params.j3], shape: [params.sx, params.sy, params.sz] },
            initial_conditions: { q_bi: [params.qx, params.qy, params.qz, params.qw], omega_bi_radps: [params.wx, params.wy, params.wz] },
            simulation: { t_max: params.tmax, playback_speed: params.play, sample_rate: params.sr, rtol: params.rtol, atol: params.atol },
            control: {
                control_type: (params.ctrl === 'inertial' ? 'tracking' : 'zero_torque'),
                kp: params.kp, kd: params.kd,
                qc: [params.cq0, params.cq1, params.cq2, params.cq3]
            }
        };
        localStorage.setItem('sim_config', JSON.stringify(persisted));
        navigateToSimulation(params);
    });

    // Show/hide control params on change
    const ctrlSelect2 = document.getElementById('CTRL_TYPE');
    if (ctrlSelect2) {
        ctrlSelect2.addEventListener('change', () => {
            const show = ctrlSelect2.value === 'inertial';
            const paramsDiv = document.getElementById('CTRL_PARAMS');
            if (paramsDiv) paramsDiv.style.display = show ? '' : 'none';
        });
    }
}

document.addEventListener('DOMContentLoaded', init);


