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
    console.log('yydoyFractionToDateString input:', yydoy, 'type:', typeof yydoy);
    if (yydoy === null || yydoy === undefined || yydoy === '') {
        console.log('yydoyFractionToDateString returning empty - null/undefined/empty');
        return '';
    }
    const val = parseFloat(yydoy);
    console.log('yydoyFractionToDateString parsed val:', val, 'isFinite:', isFinite(val));
    if (!isFinite(val)) {
        console.log('yydoyFractionToDateString returning empty - not finite');
        return '';
    }
    const intPart = Math.floor(val);
    const fracPart = val - intPart;
    const yy = Math.floor(intPart / 1000);
    const doy = intPart % 1000; // 1..366
    const year = 2000 + yy;
    const secondsInDay = Math.round(fracPart * 86400);
    const hours = Math.floor(secondsInDay / 3600);
    const minutes = Math.floor((secondsInDay % 3600) / 60);
    const seconds = secondsInDay % 60;
    console.log('yydoyFractionToDateString components:', {yy, doy, year, secondsInDay, hours, minutes, seconds});
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
    const result = `${y}-${m}-${d} ${hh}:${mm}:${ss}`;
    console.log('yydoyFractionToDateString result:', result);
    return result;
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
    const defaultsOrbit = defaults.initial_conditions?.orbit || {};
    const savedOrbit = saved.initial_conditions?.orbit || {};
    const orbit = { ...defaultsOrbit, ...savedOrbit }; // Merge defaults and saved
    console.log('Defaults orbit:', defaultsOrbit);
    console.log('Saved orbit:', savedOrbit);
    console.log('Merged orbit:', orbit);
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
    console.log('Orbit data:', orbit);
    console.log('Epoch value:', epoch, 'type:', typeof epoch);
    const dateStr = yydoyFractionToDateString(epoch);
    console.log('Converted date:', dateStr);
    setValue('DATEUTC', dateStr);
    setValue('SMA', sma);
    setValue('ECC', ecc);
    setValue('INC', inc);
    setValue('RAAN', raan);
    setValue('AOP', aop);
    setValue('TA', ta);
    setValue('TMAX', tmax);
    setValue('SR', sr);
    setValue('PLAYBACK_SPEED', play);
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

    // Estimation defaults - prioritize server defaults over localStorage for enable_estimation
    const mergedEstimation = {
        ...(defaults.estimation || {}),
        ...(saved.estimation || {})
    };
    // For enable_estimation specifically, always use the server default from config file
    // to ensure that config files load with their intended estimation state
    const enableEstimation = Boolean(defaults.estimation?.enable_estimation ?? false);
    const estimationCheckbox = document.getElementById('ENABLE_ESTIMATION');
    if (estimationCheckbox) {
        estimationCheckbox.checked = enableEstimation;
    }
    // Show/hide estimation settings and MEKF info based on checkbox state
    const estimationSettings = document.getElementById('estimation-settings');
    const mekfInfo = document.getElementById('mekf-info');
    if (estimationSettings) {
        estimationSettings.style.display = enableEstimation ? 'block' : 'none';
    }
    if (mekfInfo) {
        mekfInfo.style.display = enableEstimation ? 'block' : 'none';
    }
    // Set default values for estimation parameters from server defaults
    const estimationValues = mergedEstimation;
    setValue('CTRL_FREQ', estimationValues.ctrl_freq);
    setValue('GT_FREQ', estimationValues.gt_freq);
    setValue('RNG_SEED', estimationValues.rng_seed ?? 42);
    setValue('GYRO_MEAS_FREQ', estimationValues.gyro_meas_freq);
    setValue('GYRO_ARW', estimationValues.gyro_arw);
    setValue('GYRO_RRW', estimationValues.gyro_rrw);
    setValue('GYRO_TRUE_BIAS', estimationValues.gyro_true_bias);
    setValue('GYRO_EST_BIAS', estimationValues.gyro_est_bias);
    setValue('GYRO_INIT_COV', estimationValues.gyro_init_cov);
    setValue('STAR_MEAS_FREQ', estimationValues.star_meas_freq);
    setValue('STAR_ISO_ACC', estimationValues.star_iso_acc);
    setValue('STAR_INIT_ACC', estimationValues.star_init_acc);
    setValue('ATTITUDE_INIT_COV', estimationValues.attitude_init_cov);

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
        const enableEstimation = document.getElementById('ENABLE_ESTIMATION')?.checked || false;
        const params = {
            j1: readNumber('J1'), j2: readNumber('J2'), j3: readNumber('J3'),
            sx: readNumber('SX'), sy: readNumber('SY'), sz: readNumber('SZ'),
            wx: readNumber('WX'), wy: readNumber('WY'), wz: readNumber('WZ'),
            qx: readNumber('QX'), qy: readNumber('QY'), qz: readNumber('QZ'), qw: readNumber('QW'),
        tmax: readNumber('TMAX'), sr: readNumber('SR'), play: readNumber('PLAYBACK_SPEED'),
            rtol: readNumber('RTOL'), atol: readNumber('ATOL'),
            // control params in query string
            ctrl: document.getElementById('CTRL_TYPE')?.value || 'none',
            kp: readNumber('KP'), kd: readNumber('KD'),
            cq0: readNumber('CQ0'), cq1: readNumber('CQ1'), cq2: readNumber('CQ2'), cq3: readNumber('CQ3'),
            // epoch string, passed to loading page which forwards to backend
            epoch: (document.getElementById('DATEUTC')?.value || '').trim(),
            // estimation params (only include if enabled)
            ...(enableEstimation && {
                enable_estimation: true,
                ctrl_freq: readNumber('CTRL_FREQ'),
                gt_freq: readNumber('GT_FREQ'),
                rng_seed: readNumber('RNG_SEED'),
                gyro_meas_freq: readNumber('GYRO_MEAS_FREQ'),
                gyro_arw: readNumber('GYRO_ARW'),
                gyro_rrw: readNumber('GYRO_RRW'),
                gyro_true_bias: readNumber('GYRO_TRUE_BIAS'),
                gyro_est_bias: readNumber('GYRO_EST_BIAS'),
                gyro_init_cov: readNumber('GYRO_INIT_COV'),
                star_meas_freq: readNumber('STAR_MEAS_FREQ'),
                star_iso_acc: readNumber('STAR_ISO_ACC'),
                star_init_acc: readNumber('STAR_INIT_ACC'),
                attitude_init_cov: readNumber('ATTITUDE_INIT_COV')
            })
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
            },
            estimation: {
                enable_estimation: params.enable_estimation || false,
                ctrl_freq: params.ctrl_freq,
                gt_freq: params.gt_freq,
                rng_seed: params.rng_seed,
                gyro_meas_freq: params.gyro_meas_freq,
                gyro_arw: params.gyro_arw,
                gyro_rrw: params.gyro_rrw,
                gyro_true_bias: params.gyro_true_bias,
                gyro_est_bias: params.gyro_est_bias,
                gyro_init_cov: params.gyro_init_cov,
                star_meas_freq: params.star_meas_freq,
                star_iso_acc: params.star_iso_acc,
                star_init_acc: params.star_init_acc,
                attitude_init_cov: params.attitude_init_cov
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

    // Show/hide estimation settings on checkbox change
    const estimationCheckbox2 = document.getElementById('ENABLE_ESTIMATION');
    if (estimationCheckbox2) {
        estimationCheckbox2.addEventListener('change', () => {
            const estimationSettings = document.getElementById('estimation-settings');
            const mekfInfo = document.getElementById('mekf-info');
            if (estimationSettings) {
                estimationSettings.style.display = estimationCheckbox2.checked ? 'block' : 'none';
            }
            if (mekfInfo) {
                mekfInfo.style.display = estimationCheckbox2.checked ? 'block' : 'none';
            }
            
            // Update estimation errors radio button state in the main simulation page
            // Store the estimation state for the simulation page to read
            localStorage.setItem('estimation_enabled', estimationCheckbox2.checked.toString());
        });

        // Trigger initial state
        estimationCheckbox2.dispatchEvent(new Event('change'));
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
        let inertialPointingOption = null;
        for (const p of presets) {
            const opt = document.createElement('option');
            opt.value = p.file;
            // Use the name from YAML, or create a readable name from the filename
            const displayName = p.name || p.file.replace(/^config_/, '').replace(/\.yaml$/, '').replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase());
            opt.textContent = displayName;
            presetSelect.appendChild(opt);
            // Remember the inertial pointing preset option
            if (p.file === 'config_inertial_pointing.yaml') {
                inertialPointingOption = opt;
            }
        }
        // Select inertial pointing preset by default
        if (inertialPointingOption) {
            presetSelect.value = inertialPointingOption.value;
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
                if (sim.sample_rate !== undefined) setValue('SR', sim.sample_rate);
                if (sim.playback_speed !== undefined) setValue('PLAYBACK_SPEED', sim.playback_speed);
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
                
                // Handle estimation section
                const est = cfg.estimation || {};
                const enableEstimationCheckbox = document.getElementById('ENABLE_ESTIMATION');
                const estimationSettings = document.getElementById('estimation-settings');
                const mekfInfo = document.getElementById('mekf-info');
                
                if (enableEstimationCheckbox) {
                    const isEnabled = Boolean(est.enable_estimation);
                    enableEstimationCheckbox.checked = isEnabled;
                    
                    // Show/hide estimation settings and MEKF info
                    if (estimationSettings) {
                        estimationSettings.style.display = isEnabled ? 'block' : 'none';
                    }
                    if (mekfInfo) {
                        mekfInfo.style.display = isEnabled ? 'block' : 'none';
                    }
                    
                    // Trigger change event to ensure any other listeners are notified
                    enableEstimationCheckbox.dispatchEvent(new Event('change'));
                }
                
                // Set estimation parameter values
                if (est.ctrl_freq !== undefined) setValue('CTRL_FREQ', est.ctrl_freq);
                if (est.gt_freq !== undefined) setValue('GT_FREQ', est.gt_freq);
                setValue('RNG_SEED', est.rng_seed ?? 42);
                if (est.gyro_meas_freq !== undefined) setValue('GYRO_MEAS_FREQ', est.gyro_meas_freq);
                if (est.gyro_arw !== undefined) setValue('GYRO_ARW', est.gyro_arw);
                if (est.gyro_rrw !== undefined) setValue('GYRO_RRW', est.gyro_rrw);
                if (est.gyro_true_bias !== undefined) setValue('GYRO_TRUE_BIAS', est.gyro_true_bias);
                if (est.gyro_est_bias !== undefined) setValue('GYRO_EST_BIAS', est.gyro_est_bias);
                if (est.gyro_init_cov !== undefined) setValue('GYRO_INIT_COV', est.gyro_init_cov);
                if (est.star_meas_freq !== undefined) setValue('STAR_MEAS_FREQ', est.star_meas_freq);
                if (est.star_iso_acc !== undefined) setValue('STAR_ISO_ACC', est.star_iso_acc);
                if (est.star_init_acc !== undefined) setValue('STAR_INIT_ACC', est.star_init_acc);
                if (est.attitude_init_cov !== undefined) setValue('ATTITUDE_INIT_COV', est.attitude_init_cov);
                
            } catch (e) {
                console.warn('Failed to load preset', e);
            }
        };
        if (loadBtn) loadBtn.addEventListener('click', onLoadPreset);
    }

    
}

document.addEventListener('DOMContentLoaded', init);


