"use strict";
(() => {
    const el = id => document.getElementById(id);
    let config, state = {busy: false, phase: "empty"}, pending = false, uncertain = false;
    let timer = null, polling = false, modelPreparing = false, modelDraft = null;
    function adoptState(next) {
        if (next.source_id !== state.source_id || next.suggested_name !== state.suggested_name) el('remote').value = next.suggested_name || '';
        state = next;
    }
    if (document.addEventListener) document.addEventListener('finder-state-observed', event => {
        if (!config || pending || polling || uncertain || modelPreparing) { event.preventDefault(); return; }
        adoptState(event.detail); render(); // cached GET only; never reconcile an uncertain job automatically
    });
    if (document.addEventListener) document.addEventListener('finder-model-transform', event => {
        modelDraft = event.detail;
        // No native action here. Defer to avoid renderer/controller event reentrancy.
        Promise.resolve().then(render);
    });
    if (document.addEventListener) document.addEventListener('finder-model-preparing', event => {
        // Defer rendering to avoid reentering a viewer's source/abort cleanup.
        Promise.resolve().then(() => {
            modelPreparing = Boolean(event.detail);
            render();
            if (!modelPreparing && !uncertain) refresh(); // after abort the bounded worker may still be finishing
        });
    });
    let printerTimer = null, printerPolling = false, monitorPending = false, printerReport = {};
    function renderMonitor() {
        el("monitor-start").disabled = Boolean(!config || !config.active_monitor_enabled || monitorPending || printerPolling ||
            pending || polling || modelPreparing || state.busy || uncertain || printerReport.monitor_running || printerReport.monitor_stopping);
        // Stopping observation is independent of file/job actions; never POST /api/stop.
        el("monitor-stop").disabled = Boolean(!config || !config.active_monitor_enabled || monitorPending || !printerReport.monitor_running);
    }
    function renderPrinter(report) {
        printerReport = report;
        text("printer-status-mode", report.passive === false ? "· active status polling" : "· passive proxy observation");
        renderMonitor();
        const samples = report.samples || {};
        const temperature = samples.M105, machine = samples.M119, progress = samples.M27;
        const temp = temperature && temperature.values;
        const status = machine && machine.values;
        const file = progress && progress.values;
        text("printer-status-message", (report.stale ? "STALE / incomplete observation. " : (report.passive === false ? "Recent status batch. " : "Recent proxy observation. ")) + report.message);
        text("printer-status-source", report.source ? `${report.source} / ${report.session || "no session"} · ${report.passive === false ? "configured endpoint" : "captured upstream"} ${report.upstream} · ${report.capture_finalized ? "recording finalized" : "recording not finalized (may be running or interrupted)"}` : "No matching proxy recording");
        const suffix = sample => sample && sample.stale ? " (stale)" : "";
        text("printer-temperature", temp ? `${temp.nozzle} / ${temp.nozzle_target} °C${suffix(temperature)}` : "unknown");
        text("printer-bed", temp ? `${temp.bed} / ${temp.bed_target} °C${suffix(temperature)}` : "unknown");
        text("printer-machine", status ? `${status.machine} / ${status.move}${suffix(machine)}` : "unknown");
        el("printer-progress").value = file && file.percent !== null ? file.percent : 0;
        text("printer-progress-text", file && file.total !== null ? `${file.done} / ${file.total} bytes · ${file.percent === null ? "unknown" : file.percent.toFixed(1) + "%"}${suffix(progress)}` +
            (file.over_total ? " · printer reports more than total; display capped at 100%." : "") : "No known file-progress observation.");
        text("printer-observed", Object.entries(samples).map(([code, sample]) => `${code}: ${sample.observed_utc} (${sample.age_seconds}s old)`).join(" · ") || "No timestamped sample yet.");
    }
    async function refreshPrinter() {
        clearTimeout(printerTimer); printerTimer = null;
        if (!config || (!config.passive_status_enabled && !config.active_monitor_enabled) || printerPolling) return;
        printerPolling = true; renderMonitor();
        el("printer-refresh").disabled = true;
        try {
            renderPrinter(await request("/api/printer-status"));
        } catch (error) {
            // Do not keep old values looking current after an HTTP/read failure.
            renderPrinter({stale: true, samples: {}, message: "Cannot read observations: " + error.message});
        } finally {
            printerPolling = false; renderMonitor();
            el("printer-refresh").disabled = false;
            printerTimer = setTimeout(refreshPrinter, 2000);
        }
    }
    function text(id, value) { el(id).textContent = value || ""; }
    function render() {
        // Notify the independent viewer immediately on local slot/job transitions.
        if (document.dispatchEvent && typeof CustomEvent !== "undefined") {
            document.dispatchEvent(new CustomEvent("finder-artifact-state", {detail: {...state, busy: state.busy || pending || modelPreparing || uncertain}}));
        }
        renderMonitor();
        const busy = pending || polling || modelPreparing || state.busy || uncertain || monitorPending;
        el("file").disabled = busy || !(state.phase === 'empty' || (state.phase === 'model_ready' && state.models?.length && state.models.every(m=>/\.stl$/i.test(m.name)) && state.slice_settings == null && state.models.length<8));
        el("discard").disabled = busy || state.phase === "empty";
        el("slice").disabled = busy || !config || !config.slicing_enabled || state.phase !== "model_ready" || Boolean(state.models?.length>1 && !modelDraft?.plate) || Boolean(modelDraft && (modelDraft.source_sha256 !== state.source_sha256 || modelDraft.source_id !== state.source_id || modelDraft.error || modelDraft.locked));
        el("quality-settings").disabled = el("slice").disabled;
        el("brim-width").disabled = el("slice").disabled || el("brim-mode").value !== "outer";
        el("hole-compensation").disabled = el("slice").disabled;
        el("contour-compensation").disabled = el("slice").disabled;
        const applied = state.effective_quality;
        text("applied-quality", applied ? `Applied to this file: layer ${applied.layer_height} mm · first layer ${applied.initial_layer_print_height} mm · brim ${applied.brim_type || "profile default"} · width ${applied.brim_width || "0"} mm · gap ${applied.brim_object_gap || "profile default"} mm · XY hole compensation ${applied.xy_hole_compensation ?? "profile default"} mm per edge · outer contour ${applied.xy_contour_compensation ?? "profile default"} mm per edge.` :
            state.slice_settings ? "Slicing options submitted; effective values appear after successful slicing." : "No quality overrides applied yet. Layer/brim profile choices preserve defaults; hole/outer-contour compensation starts at 0 mm (clear for profile).");
        el("save").disabled = Boolean(busy || !config || !config.upload_enabled || !state.artifact || state.saved ||
            state.phase === "unknown" || (state.sliced && !config.sliced_upload_enabled));
        el("start").disabled = Boolean(busy || !config || !config.job_controls_enabled || !state.saved ||
            !state.save_id || state.start_attempted || state.phase === "unknown");
        el("stop").disabled = Boolean(busy || !config || !config.job_controls_enabled);
        el('start-after-upload').disabled = Boolean(busy || !config || !config.job_controls_enabled || !config.upload_enabled || state.saved);
        if (config && !config.job_controls_enabled) el('start-after-upload').checked = false;
        el("start").textContent = state.saved_name ? `Start ${state.saved_name} · may heat/move` : "Start saved file · may heat/move";
        el("remote").disabled = busy;
        const startAfter = Boolean(config && config.job_controls_enabled && el('start-after-upload').checked);
        const endpoint = config && config.owned_dummy ? 'dummy' : 'Finder';
        el('save').textContent = startAfter ? `Save + start ${el('remote').value || 'selected file'} on ${endpoint} · may heat/move` : `Save to ${endpoint} · no start`;
        if (state.phase === "empty") el("incoming").value = 0;
        el("download").hidden = !state.artifact || busy;
        el('create-gx').disabled = Boolean(busy || !state.sliced || !state.artifact || state.saved || state.gx_generated || !state.gx_metadata || state.phase === 'unknown');
        el('gx-thumbnail').hidden = !state.gx_generated || busy;
        const thumbnail = state.gx_generated && !busy ? '/api/gx-thumbnail?v='+state.sha256 : '';
        if (el('gx-thumbnail').getAttribute) {
            if (thumbnail && el('gx-thumbnail').getAttribute('src') !== thumbnail) el('gx-thumbnail').src = thumbnail;
            if (!thumbnail) el('gx-thumbnail').removeAttribute('src');
        }
        text('gx-status',state.gx_generated ? 'GX ready: shaded source-mesh thumbnail, unchanged G-code body. Experimental printer-display compatibility; not print-safety validation.' :
            state.busy && state.phase === 'gx_export' ? 'Rendering the 3D thumbnail and packaging GX locally…' :
            state.gx_metadata ? 'Optional GX export available. Separate click; no upload or start.' : (state.gx_unavailable || 'Slice a model first; standalone print files are not repackaged here.'));
        text("selection", state.name || "One file at a time. Choosing a file only stores it locally.");
        text("phase", uncertain ? "HTTP response unknown — refresh before continuing" : state.phase);
        text("hash", state.sha256);
        text("capture", state.capture);
        text("warning", state.warning);
        text("slice-status", state.busy && state.phase === "slicing" ?
            (state.slicer_stage === 'priming_review' ? 'Checking first-layer priming and nominal margin…' : state.slicer_stage === "geometry_transform" ? "Applying model transforms…" : state.slicer_stage === "slice" ? "Slicing model…" : "Checking the Orca CLI…") :
            state.sliced && state.artifact ? `Slice completed: ${state.size} bytes. Download below for offline review; this is not print approval.` :
            state.phase === "failed" && state.slicer_stage ? "Slice failed. See the diagnostic excerpt below." :
            state.artifact ? "Existing print file ready; no slicing needed." : "Choose an STL/3MF, then click Slice. No slicing starts automatically.");
        const excerpt = state.slicer_log || (state.sliced && state.artifact ?
            "Orca finished successfully without additional slice output. Download and review the generated file." : "No Orca output recorded yet.");
        if (config && config.priming_review_enabled) text('priming-notice','Experimental native-skirt candidate: first-layer overlap/nominal margin checks enabled before artifact publication. Changed startup is not physically validated; homing, head/clip clearance and bead behavior remain unmodeled.');
        text("slicer-log", (state.error ? "Operation error: " + state.error + "\n\n" : "") + excerpt);
        text("bytes", `${state.acknowledged || 0} / ${state.size || 0} bytes acknowledged`);
        el("outgoing").value = state.size ? 100 * (state.acknowledged || 0) / state.size : 0;
        text("result", state.saved ? (state.start_after_upload ? 'Final save confirmed. Start was also requested; see the separate job outcome below.' : 'Final save confirmed. Saving does not start or stop a print.') :
            state.phase === "unknown" ? "Remote result UNKNOWN. Inspect logs and physical state before retrying." :
            "Acknowledged bytes are not final save confirmation.");
        text("job-result", state.job_result === 'start_not_sent' ? 'Start after upload requested, but no start sent by this operation. Inspect save/release/recording errors; no automatic retry.' :
            state.job_result === 'start_pending' ? 'Save confirmed; fresh connection/READY check before the one requested start attempt.' : state.job_result === "start_acknowledged" ? "Start acknowledged. The printer may heat/move; supervise it. No live job progress is inferred." :
            state.job_result === "cancel_acknowledged" ? "Cancel command acknowledged. This does NOT prove READY, motion stopped or cooled heaters. Check the printer physically." :
            /_unknown$/.test(state.job_result || "") ? "Job result UNKNOWN. Check physical state; no automatic retry was performed." :
            "No job-control result in this slot. Cached acknowledgements are not live printer status.");
        if (config && config.owned_dummy) {
            text("job-result", state.job_result === "start_acknowledged" ? "Virtual job started in the owned dummy. No G-code, motion or heating is executed." :
                state.job_result === "cancel_acknowledged" ? "Virtual cancel acknowledged by the owned dummy." :
                /_unknown$/.test(state.job_result || "") ? "Virtual job result unknown; inspect local diagnostics." :
                state.job_result === 'start_not_sent' ? 'Virtual start requested but not sent; inspect save diagnostics.' :
                state.job_result === 'start_pending' ? 'Virtual save confirmed; start pending fresh READY.' : 'No virtual job requested yet.');
        }
        text("job-gating", config && config.owned_dummy ? "Confirmed virtual Start/Cancel available. This endpoint is the owned dummy, not hardware." : config && config.job_controls_enabled ? "Explicit job controls ENABLED. Start uses only this slot's confirmed saved filename." :
            "Job controls disabled. Restart with --enable-job-controls only for a deliberate supervised trial.");
        if (state.error) text("error", state.error);
        if (el('action-error')) text('action-error', el('error').textContent);
        text("gating", !config || !config.upload_enabled ? "Printer uploads disabled: start the server with --enable-upload for an explicitly chosen endpoint." :
            state.sliced && !config.sliced_upload_enabled ? "Generated-output saving is blocked pending profile review and server --allow-sliced-upload." :
            (config.active_monitor_enabled ? "Status polling can open a connection; Save/Start/Cancel still require separate explicit actions." :
             "Only explicit Save/Start/Cancel actions open printer connections."));
    }
    async function request(url, options) {
        const response = await fetch(url, {cache: "no-store", ...options});
        const data = await response.json();
        if (!response.ok) {
            const error = new Error(data.error || `HTTP ${response.status}`);
            // These server replies reject requests before launching a task.
            // Lost/malformed responses, 408 and 5xx I/O errors remain uncertain.
            error.notAccepted = [400,403,404,409,413,415,422,507].includes(response.status);
            throw error;
        }
        return data;
    }
    async function refresh() {
        clearTimeout(timer); timer = null;
        if (polling || pending || !config) return;
        polling = true; render();
        try {
            adoptState(await request("/api/state"));
            uncertain = false;
            if (!state.error) text("error", "");
            if (state.busy) timer = setTimeout(refresh, 1000);
        } catch (error) {
            text("error", error.message + " Job may still be running; refresh, do not resubmit.");
        } finally { polling = false; render(); }
    }
    async function action(operation, body) {
        if (pending || polling || modelPreparing || monitorPending || state.busy || uncertain) return;
        pending = true; clearTimeout(timer); text("error", ""); render();
        let accepted = false;
        try {
            adoptState(await request("/api/" + operation, {method: "POST", headers: {
                "Content-Type": "application/json", "X-Finder-Token": config.token
            }, body: JSON.stringify(body)}));
            accepted = true;
        } catch (error) {
            uncertain = !error.notAccepted;
            text("error", error.notAccepted ? 'Request rejected: '+error.message : error.message + ' Response unknown; refresh the result before another operation.');
        } finally { pending = false; render(); }
        // GET only reads cached state, never printer status.
        if (accepted) await refresh();
    }
    function receive(file, done=()=>{}) {
        if (!config || pending || polling || modelPreparing || monitorPending || state.busy || uncertain || !['empty','model_ready'].includes(state.phase) || !file) {done(false);return;}
        const stl = /\.(stl|3mf)$/i.test(file.name);
        if (!/\.(stl|3mf|gx|gcode|g)$/i.test(file.name) || !file.size || file.size > (stl ? config.model_limit : config.print_limit)) {
            text("error", "Choose a nonempty STL/3MF (up to 64 MiB) or GX/G-code/G (up to 8 MiB)."); done(false);return;
        }
        pending = true; clearTimeout(timer); text("error", ""); el("incoming").value = 0; render();
        const xhr = new XMLHttpRequest();
        xhr.open("POST", "/api/file?name=" + encodeURIComponent(file.name));
        xhr.setRequestHeader("Content-Type", "application/octet-stream");
        xhr.setRequestHeader("X-Finder-Token", config.token);
        xhr.timeout = 70000;
        xhr.upload.onprogress = event => { if (event.lengthComputable) el("incoming").value = 100 * event.loaded / event.total; };
        function failed(message) {
            uncertain = true; pending = false; text("error", message + " Refresh the result before selecting again; already received models remain."); render();done(false);
        }
        xhr.onerror = xhr.ontimeout = () => failed("Browser upload response lost.");
        xhr.onload = () => {
            try {
                const data = JSON.parse(xhr.responseText);
                if (xhr.status !== 200) throw new Error(data.error || "File was not accepted");
                state = data; pending = false;
                el("remote").value = state.suggested_name || "";
                el('file').value = ''; // Permit deliberately adding the same STL as another copy.
                render();done(true);
            } catch (error) { failed(error.message); }
        };
        xhr.send(file);
    }
    function receiveFiles(files){
        const chosen=Array.from(files||[]);if(!chosen.length)return;
        if(chosen.length>1 && (!chosen.every(f=>/\.stl$/i.test(f.name)) || chosen.length+(state.models?.length||0)>8)){
            text('error','Choose up to8 STL models together; 3MF/print files remain standalone.');render();return;
        }
        let index=0;
        function next(ok=true){if(ok&&index<chosen.length)receive(chosen[index++],next);}
        next();
    }
    el("file").addEventListener("change", event => receiveFiles(event.target.files));
    el("drop").addEventListener("dragover", event => { event.preventDefault(); el("drop").classList.add("over"); });
    el("drop").addEventListener("dragleave", () => el("drop").classList.remove("over"));
    el("drop").addEventListener("drop", event => {
        event.preventDefault(); el("drop").classList.remove("over");
        receiveFiles(event.dataTransfer.files);
    });
    el("refresh").addEventListener("click", refresh);
    el("printer-refresh").addEventListener("click", refreshPrinter);
    async function toggleMonitor(enabled) {
        if (monitorPending || !config || !config.active_monitor_enabled ||
                (enabled && el("monitor-start").disabled)) return;
        monitorPending = true; render(); text("monitor-error", "");
        try {
            renderPrinter(await request("/api/monitor", {method: "POST", headers: {
                "Content-Type": "application/json", "X-Finder-Token": config.token
            }, body: JSON.stringify({enabled, confirm: true})}));
        } catch (error) {
            text("monitor-error", error.message + " Polling result unknown; refresh status, do not automatically retry.");
        } finally { monitorPending = false; render(); await refreshPrinter(); }
    }
    el("monitor-start").addEventListener("click", () => toggleMonitor(true));
    el("monitor-stop").addEventListener("click", () => toggleMonitor(false));
    el("discard").addEventListener("click", () => {
        action("discard", {confirm: true}); el("file").value = "";
    });
    el("brim-mode").addEventListener("change", render);
    el("slice").addEventListener("click", () => {
        const layer = el("layer-height").value;
        const width = Number(el("brim-width").value);
        const holeInput = el("hole-compensation");
        const hole = holeInput.value.trim() === "" ? null : Number(holeInput.value);
        const contourInput = el("contour-compensation");
        const contour = contourInput.value.trim() === "" ? null : Number(contourInput.value);
        const settings = {layer_height: layer === "" ? null : Number(layer), brim: el("brim-mode").value,
            brim_width: width, xy_hole_compensation: hole, xy_contour_compensation: contour};
        if (!Number.isFinite(width) || width < 1 || width > 10 || (settings.layer_height !== null &&
                (!Number.isFinite(settings.layer_height) || settings.layer_height < 0.08 || settings.layer_height > 0.28)) || (hole !== null && (!Number.isFinite(hole) || hole < -0.5 || hole > 0.5)) ||
                (holeInput.validity && holeInput.validity.badInput) ||
                (contour !== null && (!Number.isFinite(contour) || contour < -0.5 || contour > 0.5)) ||
                (contourInput.validity && contourInput.validity.badInput)) {
            text("error", "Use layer height 0.08–0.28 mm, brim width 1–10 mm and XY hole/contour compensation −0.5 to +0.5 mm per edge."); return;
        }
        const body = {confirm: true, settings};
        if (modelDraft) {
            if (modelDraft.source_sha256 !== state.source_sha256 || modelDraft.source_id !== state.source_id || modelDraft.error || modelDraft.locked) {
                text('error', modelDraft.error || 'Source model changed or was already sliced; refresh result.'); return;
            }
            if(modelDraft.plate)body.plate=modelDraft.plate;
            else body.transform = modelDraft.transform;
            body.source_sha256 = modelDraft.source_sha256; body.source_id = modelDraft.source_id;
        }
        action("slice", body);
    });
    if(document.addEventListener)document.addEventListener('finder-remove-model',event=>{
        action('model-remove',{confirm:true,source_id:event.detail.source_id,model_id:event.detail.model_id});
    });
    el('create-gx').addEventListener('click',()=>action('gx',{confirm:true,artifact_sha256:state.sha256,source_id:state.source_id}));
    el('start-after-upload').addEventListener('change', render);
    el('remote').addEventListener('input', render);
    el("save").addEventListener("click", () => {
        action("save", {confirm: true, remote_name: el("remote").value,
            start_after_upload: Boolean(config && config.job_controls_enabled && el('start-after-upload').checked),
            artifact_sha256: state.sha256, source_id: state.source_id});
    });
    el("start").addEventListener("click", () => {
        action("start", {confirm: true, save_id: state.save_id});
    });
    el("stop").addEventListener("click", () => {
        action("stop", {confirm: true});
    });
    request("/api/config").then(data => {
        config = data;
        text("access-policy", data.lan_mode ? "LAN sharing: everyone with the password shares this printer and current file. HTTP is not encrypted. Review the exact saved filename before Start; coordinate with the other operator." : "Local-only web access.");
        text("target", data.owned_dummy ? `${data.target} · FRESH OWNED DUMMY · virtual Save/Start/Cancel, no G-code execution` :
            `${data.target} · printer uploads ${data.upload_enabled ? "ENABLED" : "disabled"}`);
        text("orca", data.slicing_enabled ? "Trusted server-side Orca/profiles configured. Slice offline, then download and review before a separate Save." :
            "Orca not configured. Supply --orca and trusted self-contained --machine / --process / --filament JSON on the server. Existing FlashPrint GX files work independently.");
        text("printer-status-policy", data.active_monitor_enabled ?
            "Active polling sends M119/M105/M27 batches about one second apart, pauses for local operations and stops on errors. Close FlashPrint/other clients. Stop status polling does not cancel printing. Percent is not remaining time or proof of completion." :
            "Passive mode reads existing proxy logs only; FlashPrint must already be polling through the proxy. No printer commands are sent. Percent is not remaining time or proof of completion.");
        if (data.passive_status_enabled || data.active_monitor_enabled) refreshPrinter();
        else {
            text("printer-status-message", "Passive status not configured. Use the proxy web launcher or tools/watch_printer.sh. No printer polling is performed.");
            el("printer-refresh").disabled = true;
        }
        refresh();
    }).catch(error => text("error", error.message + " Reload the page using the exact server URL."));
    render();
})();
