async function fetchDefaults() {
    const res = await fetch('/api/defaults');
    return res.json();
}

async function fetchPresets() {
    const res = await fetch('/api/presets');
    return res.json();
}

// Convert YYDDD.DDDD (UTC fractional day-of-year) <-> 'YYYY-MM-DD HH:MM:SS' (UTC)
function yydoyFractionToDateString(yydoy) {
    if (yydoy === null || yydoy === undefined || yydoy === '') return '';
    const val = parseFloat(yydoy);
    if (!isFinite(val)) return '';
    const intPart = Math.floor(val);
    const fracPart = val - intPart;
    const yy = Math.floor(intPart / 1000);
    const doy = intPart % 1000; // 1..366
    const year = 2000 + yy;
    const secondsInDay = Math.round(fracPart * 86400);
    const hours = Math.floor(secondsInDay / 3600);
    const minutes = Math.floor((secondsInDay % 3600) / 60);
    const seconds = secondsInDay % 60;
    // Start of year UTC + (doy-1) days
    const jan1 = new Date(Date.UTC(year, 0, 1, 0, 0, 0));
    const date = new Date(jan1.getTime() + (doy - 1) * 86400000);
    // Apply time of day
    date.setUTCHours(hours, minutes, seconds, 0);
    const y = date.getUTCFullYear();
    const m = String(date.getUTCMonth() + 1).padStart(2, '0');
    const d = String(date.getUTCDate()).padStart(2, '0');
    const hh = String(date.getUTCHours()).padStart(2, '0');
    const mm = String(date.getUTCMinutes()).padStart(2, '0');
    const ss = String(date.getUTCSeconds()).padStart(2, '0');
    return `${y}-${m}-${d} ${hh}:${mm}:${ss}`;
}

function dateStringToYyDoyFraction(str) {
    if (!str || typeof str !== 'string') return '';
    const s = str.trim().replace('T', ' ');
    const parts = s.split(' ');
    if (parts.length < 2) return '';
    const [datePart, timePart] = parts;
    const dBits = datePart.split('-').map(x => parseInt(x, 10));
    const tBits = timePart.split(':').map(x => parseInt(x, 10));
    if (dBits.length !== 3 || tBits.length < 2) return '';
    const [Y, M, D] = dBits;
    const [H, Min, SRaw] = [tBits[0], tBits[1], tBits[2] ?? 0];
    if ([Y, M, D, H, Min].some(v => !isFinite(v))) return '';
    const S = isFinite(SRaw) ? SRaw : 0;
    const dtMs = Date.UTC(Y, (M - 1), D, H, Min, S, 0);
    if (!isFinite(dtMs)) return '';
    const startMs = Date.UTC(Y, 0, 1, 0, 0, 0, 0);
    const diffSec = Math.max(0, Math.round((dtMs - startMs) / 1000));
    const doy = Math.floor(diffSec / 86400) + 1; // 1-based
    const secOfDay = diffSec - (doy - 1) * 86400;
    const frac = secOfDay / 86400;
    const yy = Y % 100;
    const prefix = yy * 1000 + doy; // YYDDD
    const val = prefix + frac;
    // Match defaults precision (4 decimals)
    return val.toFixed(4);
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
    const [defaults, presetsPayload] = await Promise.all([fetchDefaults(), fetchPresets()]);
    // Load persisted values if present
    const saved = JSON.parse(localStorage.getItem('sim_config') || '{}');
    const [j1, j2, j3] = (saved.spacecraft?.inertia) || defaults.spacecraft.inertia;
    const [sx, sy, sz] = (saved.spacecraft?.shape) || defaults.spacecraft.shape;
    const [wx, wy, wz] = (saved.initial_conditions?.omega_bi_radps) || defaults.initial_conditions.omega_bi_radps;
    const [qx, qy, qz, qw] = (saved.initial_conditions?.q_bi) || defaults.initial_conditions.q_bi;
    const orbit = (saved.initial_conditions?.orbit) || defaults.initial_conditions.orbit || {};
    const epoch = orbit.epoch_utc_fractional_yydoy ?? '';
    const kep = orbit.keplerian || {};
    const sma = kep.semi_major_axis_km ?? '';
    const ecc = kep.eccentricity ?? '';
    const inc = kep.inclination_deg ?? '';
    const raan = kep.raan_deg ?? '';
    const aop = kep.argument_of_the_perigee_deg ?? '';
    const ta = kep.true_anomaly_deg ?? '';
    const sim = saved.simulation || defaults.simulation || {};
    const tmax = sim.t_max ?? 1000.0;
    const play = sim.playback_speed ?? 1.0;
    const sr = sim.sample_rate ?? 30.0;
    const rtol = sim.rtol ?? 1e-12;
    const atol = sim.atol ?? 1e-12;
    const control = saved.control || defaults.control || { control_type: 'none', kp: 0.0, kd: 0.0, qc: [0,0,0,1] };
    
    let ctrlType = control.control_type || 'none';
    if (ctrlType === 'tracking') ctrlType = 'inertial_linear';
    if (ctrlType === 'nonlinear_tracking') ctrlType = 'inertial_nonlinear';
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
    setValue('DATEUTC', yydoyFractionToDateString(epoch));
    setValue('SMA', sma);
    setValue('ECC', ecc);
    setValue('INC', inc);
    setValue('RAAN', raan);
    setValue('AOP', aop);
    setValue('TA', ta);
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
        const show = (ctrlType === 'inertial_linear' || ctrlType === 'inertial_nonlinear');
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
            cq0: readNumber('CQ0'), cq1: readNumber('CQ1'), cq2: readNumber('CQ2'), cq3: readNumber('CQ3'),
            // epoch string, passed to loading page which forwards to backend
            epoch: (document.getElementById('DATEUTC')?.value || '').trim()
        };
        // persist selections
        const persisted = {
            spacecraft: { inertia: [params.j1, params.j2, params.j3], shape: [params.sx, params.sy, params.sz] },
            initial_conditions: {
                q_bi: [params.qx, params.qy, params.qz, params.qw],
                omega_bi_radps: [params.wx, params.wy, params.wz],
                orbit: {
                    epoch_utc_fractional_yydoy: dateStringToYyDoyFraction(document.getElementById('DATEUTC')?.value || ''),
                    keplerian: {
                        semi_major_axis_km: readNumber('SMA'),
                        eccentricity: readNumber('ECC'),
                        inclination_deg: readNumber('INC'),
                        raan_deg: readNumber('RAAN'),
                        argument_of_the_perigee_deg: readNumber('AOP'),
                        true_anomaly_deg: readNumber('TA')
                    }
                }
            },
            simulation: { t_max: params.tmax, playback_speed: params.play, sample_rate: params.sr, rtol: params.rtol, atol: params.atol },
            control: {
                control_type: (params.ctrl === 'inertial_linear' ? 'tracking' : (params.ctrl === 'inertial_nonlinear' ? 'nonlinear_tracking' : 'zero_torque')),
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
            const v = ctrlSelect2.value;
            const show = (v === 'inertial_linear' || v === 'inertial_nonlinear');
            const paramsDiv = document.getElementById('CTRL_PARAMS');
            if (paramsDiv) paramsDiv.style.display = show ? '' : 'none';
        });
    }

    // Populate presets dropdown
    const presetSelect = document.getElementById('PRESET_SELECT');
    const presets = (presetsPayload && presetsPayload.presets) || [];
    if (presetSelect) {
        presetSelect.innerHTML = '';
        // Placeholder option
        const ph = document.createElement('option');
        ph.value = '';
        ph.textContent = 'Select a preset…';
        presetSelect.appendChild(ph);
        for (const p of presets) {
            const opt = document.createElement('option');
            opt.value = p.file;
            opt.textContent = p.name || p.file;
            presetSelect.appendChild(opt);
        }
        const loadBtn = document.getElementById('PRESET_LOAD_BTN');
        const onLoadPreset = async () => {
            const file = presetSelect.value;
            if (!file) return;
            try {
                const res = await fetch('/api/presets/' + file);
                const cfg = await res.json();
                if (!cfg || typeof cfg !== 'object') return;
                const sc = cfg.spacecraft || {};
                const ic = cfg.initial_conditions || {};
                const sim = cfg.simulation || {};
                const ctrl = cfg.control || {};
                const [pj1, pj2, pj3] = sc.inertia || [];
                const [psx, psy, psz] = sc.shape || [];
                const [pwx, pwy, pwz] = ic.omega_bi_radps || [];
                const [pqx, pqy, pqz, pqw] = ic.q_bi || [];
                if (pj1 !== undefined) setValue('J1', pj1);
                if (pj2 !== undefined) setValue('J2', pj2);
                if (pj3 !== undefined) setValue('J3', pj3);
                if (psx !== undefined) setValue('SX', psx);
                if (psy !== undefined) setValue('SY', psy);
                if (psz !== undefined) setValue('SZ', psz);
                if (pwx !== undefined) setValue('WX', pwx);
                if (pwy !== undefined) setValue('WY', pwy);
                if (pwz !== undefined) setValue('WZ', pwz);
                if (pqx !== undefined) setValue('QX', pqx);
                if (pqy !== undefined) setValue('QY', pqy);
                if (pqz !== undefined) setValue('QZ', pqz);
                if (pqw !== undefined) setValue('QW', pqw);
                // Orbit preset values
                const porbit = ic.orbit || {};
                const pkep = porbit.keplerian || {};
                if (porbit.epoch_utc_fractional_yydoy !== undefined) setValue('DATEUTC', yydoyFractionToDateString(porbit.epoch_utc_fractional_yydoy));
                if (pkep.semi_major_axis_km !== undefined) setValue('SMA', pkep.semi_major_axis_km);
                if (pkep.eccentricity !== undefined) setValue('ECC', pkep.eccentricity);
                if (pkep.inclination_deg !== undefined) setValue('INC', pkep.inclination_deg);
                if (pkep.raan_deg !== undefined) setValue('RAAN', pkep.raan_deg);
                if (pkep.argument_of_the_perigee_deg !== undefined) setValue('AOP', pkep.argument_of_the_perigee_deg);
                if (pkep.true_anomaly_deg !== undefined) setValue('TA', pkep.true_anomaly_deg);
                if (sim.t_max !== undefined) setValue('TMAX', sim.t_max);
                if (sim.playback_speed !== undefined) setValue('PLAY', sim.playback_speed);
                if (sim.sample_rate !== undefined) setValue('SR', sim.sample_rate);
                if (sim.rtol !== undefined) setValue('RTOL', sim.rtol);
                if (sim.atol !== undefined) setValue('ATOL', sim.atol);
                const ctrlSelect3 = document.getElementById('CTRL_TYPE');
                if (ctrlSelect3) {
                    let tRaw = (ctrl.control_type || 'none').toString().toLowerCase().trim();
                    let t;
                    if (tRaw.includes('nonlinear')) {
                        t = 'inertial_nonlinear';
                    } else if (tRaw.includes('tracking') || tRaw.includes('inertial')) {
                        t = 'inertial_linear';
                    } else {
                        t = 'none';
                    }
                    ctrlSelect3.value = t;
                    const show = (t === 'inertial_linear' || t === 'inertial_nonlinear');
                    const paramsDiv = document.getElementById('CTRL_PARAMS');
                    if (paramsDiv) paramsDiv.style.display = show ? '' : 'none';
                    // Ensure any listeners update dependent UI
                    ctrlSelect3.dispatchEvent(new Event('change'));
                }
                if (ctrl.kp !== undefined) setValue('KP', ctrl.kp);
                if (ctrl.kd !== undefined) setValue('KD', ctrl.kd);
                const qc = ctrl.qc || [];
                if (qc[0] !== undefined) setValue('CQ0', qc[0]);
                if (qc[1] !== undefined) setValue('CQ1', qc[1]);
                if (qc[2] !== undefined) setValue('CQ2', qc[2]);
                if (qc[3] !== undefined) setValue('CQ3', qc[3]);
            } catch (e) {
                console.warn('Failed to load preset', e);
            }
        };
        if (loadBtn) loadBtn.addEventListener('click', onLoadPreset);
    }

    
}

document.addEventListener('DOMContentLoaded', init);


