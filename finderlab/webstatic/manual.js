"use strict";
(() => {
    const el = id => document.getElementById(id);
    const buttons = ["manual-light", "manual-dark", "manual-x-minus", "manual-x-plus", "manual-y-minus",
        "manual-y-plus", "manual-z-minus", "manual-z-plus", "manual-feed", "manual-retract"];
    let config, report, pending = false, reading = false, uncertain = false, timer;
    function text(id, value) { el(id).textContent = value; }
    function render() {
        const blocked = !config || !config.manual_virtual_enabled || !report || !report.enabled ||
            !report.state || report.busy || report.job_active || report.blocked || pending || reading || uncertain;
        el("manual-controls").disabled = Boolean(blocked);
        for (const id of buttons) el(id).disabled = Boolean(blocked);
        el("manual-warm").checked = Boolean(report && report.state && report.state.warm_nozzle_simulated);
        for (const id of ["manual-feed", "manual-retract"]) {
            el(id).disabled = Boolean(blocked || !el("manual-warm").checked);
        }
        text("manual-policy", report ? report.message : "Physical controls locked. Manual-state read is pending/unavailable.");
        const s = report && report.state;
        text("manual-values", s ? `VIRTUAL relative counters: X ${s.offsets_mm.X}, Y ${s.offsets_mm.Y}, Z ${s.offsets_mm.Z}, E ${s.extruded_mm} mm · RGB ${s.rgb.join("/")} · revision ${s.revision}. NOT printer feedback.` : "No known virtual control state.");
        text("manual-result", uncertain ? "Control result UNKNOWN. Refresh control state explicitly before a new confirmation; no automatic retry." :
            report && report.job_active ? "Virtual print active: manual rehearsal is locked." :
            report && report.busy ? "Local operation active: manual rehearsal is locked." :
            report && report.blocked ? "Unknown local printer result: inspect existing job diagnostics first." :
            report && report.capture ? `Last virtual intent recorded in ${report.capture}. No wire commands sent.` : "No manual action requested.");
        el("manual-refresh").disabled = pending || reading || !config;
    }
    async function request(url, options) {
        const response = await fetch(url, {cache: "no-store", ...options});
        const result = await response.json();
        if (!response.ok) throw new Error(result.error || `HTTP ${response.status}`);
        return result;
    }
    function schedule() {
        clearTimeout(timer);
        if (config && config.manual_virtual_enabled) timer = setTimeout(() => refresh(false), 1000);
    }
    async function refresh(explicit = false) {
        clearTimeout(timer);
        if (!config || pending || reading) { schedule(); return; }
        reading = true; render();
        try {
            report = await request("/api/manual-state");
            if (explicit) { uncertain = false; text("manual-error", ""); }
        } catch (error) {
            report = null; uncertain = true;
            text("manual-error", "Cannot read control state: " + error.message);
        } finally { reading = false; render(); schedule(); }
    }
    async function action(intent) {
        if (pending || reading || uncertain || el("manual-controls").disabled) return;
        const summary = intent.action === "jog" ? `${intent.axis} ${intent.distance} mm` :
            intent.action === "extrude" ? `extruder ${intent.distance} mm` :
            intent.action === "warm" ? `simulated warm nozzle ${intent.enabled ? "on" : "off"}` : `light RGB ${intent.rgb.join("/")}`;
        if (!confirm(`Rehearse ${summary} in the owned dummy? This changes only virtual counters/light state. No motion, heat or printer command is sent.`)) { render(); return; }
        const body = {...intent, revision: report.state.revision, confirm: true};
        pending = true; clearTimeout(timer); render(); text("manual-error", "");
        try {
            report = await request("/api/manual", {method: "POST", headers: {
                "Content-Type": "application/json", "X-Finder-Token": config.token
            }, body: JSON.stringify(body)});
        } catch (error) {
            uncertain = true;
            text("manual-error", error.message + " Refresh control state; do not repeat automatically.");
        } finally { pending = false; render(); schedule(); }
    }
    el("manual-light").addEventListener("click", () => {
        const colour = el("manual-colour").value;
        if (!/^#[0-9a-f]{6}$/i.test(colour)) { text("manual-error", "Choose a valid RGB colour."); return; }
        action({action: "light", rgb: [1, 3, 5].map(i => parseInt(colour.slice(i, i+2), 16))});
    });
    el("manual-dark").addEventListener("click", () => action({action: "light", rgb: [0, 0, 0]}));
    for (const axis of ["X", "Y", "Z"]) {
        for (const [sign, multiplier] of [["minus", -1], ["plus", 1]]) {
            el(`manual-${axis.toLowerCase()}-${sign}`).addEventListener("click", () => {
                const distance = multiplier * Number(el(axis === "Z" ? "manual-z-step" : "manual-xy-step").value);
                const allowed = axis === "Z" ? [0.1, 1] : [0.1, 1, 5];
                if (!allowed.includes(Math.abs(distance))) { text("manual-error", "Choose an allowed finite step."); return; }
                action({action: "jog", axis, distance});
            });
        }
    }
    el("manual-warm").addEventListener("change", event => action({action: "warm", enabled: event.target.checked}));
    for (const [id, sign] of [["manual-feed", 1], ["manual-retract", -1]]) {
        el(id).addEventListener("click", () => {
            if (el(id).disabled) return;
            const distance = sign * Number(el("manual-e-step").value);
            if (![1, 5].includes(Math.abs(distance))) { text("manual-error", "Choose a 1 or 5 mm extruder rehearsal step."); return; }
            action({action: "extrude", distance});
        });
    }
    el("manual-controls").addEventListener("keydown", event => {
        if (event.repeat) event.preventDefault(); // No keyboard auto-repeat/continuous jog.
    });
    el("manual-refresh").addEventListener("click", () => refresh(true));
    request("/api/config").then(value => { config = value; refresh(false); }).catch(error => {
        uncertain = true; text("manual-error", "Cannot load control capability: " + error.message + ". Reload the page."); render();
    });
    render();
})();
