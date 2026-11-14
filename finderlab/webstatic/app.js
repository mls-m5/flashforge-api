"use strict";
(() => {
    const el = id => document.getElementById(id);
    let config, state = {busy: false, phase: "empty"}, pending = false, uncertain = false;
    let timer = null, polling = false;
    function text(id, value) { el(id).textContent = value || ""; }
    function render() {
        const busy = pending || polling || state.busy || uncertain;
        el("file").disabled = busy || state.phase !== "empty";
        el("discard").disabled = busy || state.phase === "empty";
        el("slice").disabled = busy || !config || !config.slicing_enabled || state.phase !== "model_ready";
        el("save").disabled = Boolean(busy || !config || !config.upload_enabled || !state.artifact || state.saved ||
            state.phase === "unknown" || (state.sliced && !config.sliced_upload_enabled));
        el("start").disabled = Boolean(busy || !config || !config.job_controls_enabled || !state.saved ||
            !state.save_id || state.start_attempted || state.phase === "unknown");
        el("stop").disabled = Boolean(busy || !config || !config.job_controls_enabled);
        el("remote").disabled = busy;
        el("save").textContent = config && config.owned_dummy ? "Save to dummy · no start" : "Save to Finder · no start";
        if (state.phase === "empty") el("incoming").value = 0;
        el("download").hidden = !state.artifact || busy;
        text("selection", state.name || "One file at a time. Choosing a file only stores it locally.");
        text("phase", uncertain ? "HTTP response unknown — refresh before continuing" : state.phase);
        text("hash", state.sha256);
        text("capture", state.capture);
        text("warning", state.warning);
        text("slice-status", state.busy && state.phase === "slicing" ?
            (state.slicer_stage === "slice" ? "Slicing STL…" : "Checking the Orca CLI…") :
            state.sliced && state.artifact ? `Slice completed: ${state.size} bytes. Download below for offline review; this is not print approval.` :
            state.phase === "failed" && state.slicer_stage ? "Slice failed. See the diagnostic excerpt below." :
            state.artifact ? "Existing print file ready; no slicing needed." : "Choose an STL, then click Slice. No slicing starts automatically.");
        const excerpt = state.slicer_log || (state.sliced && state.artifact ?
            "Orca finished successfully without additional slice output. Download and review the generated file." : "No Orca output recorded yet.");
        text("slicer-log", (state.error ? "Operation error: " + state.error + "\n\n" : "") + excerpt);
        text("bytes", `${state.acknowledged || 0} / ${state.size || 0} bytes acknowledged`);
        el("outgoing").value = state.size ? 100 * (state.acknowledged || 0) / state.size : 0;
        text("result", state.saved ? "Final save confirmed. Saving does not start or stop a print." :
            state.phase === "unknown" ? "Remote result UNKNOWN. Inspect logs and physical state before retrying." :
            "Acknowledged bytes are not final save confirmation.");
        text("job-result", state.job_result === "start_acknowledged" ? "Start acknowledged. The printer may heat/move; supervise it. No live job progress is inferred." :
            state.job_result === "cancel_acknowledged" ? "Cancel command acknowledged. This does NOT prove READY, motion stopped or cooled heaters. Check the printer physically." :
            /_unknown$/.test(state.job_result || "") ? "Job result UNKNOWN. Check physical state; no automatic retry was performed." :
            "No job-control result in this slot. Cached acknowledgements are not live printer status.");
        if (config && config.owned_dummy) {
            text("job-result", state.job_result === "start_acknowledged" ? "Virtual job started in the owned dummy. No G-code, motion or heating is executed." :
                state.job_result === "cancel_acknowledged" ? "Virtual cancel acknowledged by the owned dummy." :
                /_unknown$/.test(state.job_result || "") ? "Virtual job result unknown; inspect local diagnostics." : "No virtual job requested yet.");
        }
        text("job-gating", config && config.owned_dummy ? "Confirmed virtual Start/Cancel available. This endpoint is the owned dummy, not hardware." : config && config.job_controls_enabled ? "Explicit job controls ENABLED. Start uses only this slot's confirmed saved filename." :
            "Job controls disabled. Restart with --enable-job-controls only for a deliberate supervised trial.");
        if (state.error) text("error", state.error);
        text("gating", !config || !config.upload_enabled ? "Printer uploads disabled: start the server with --enable-upload for an explicitly chosen endpoint." :
            state.sliced && !config.sliced_upload_enabled ? "Generated-output saving is blocked pending profile review and server --allow-sliced-upload." :
            "Only explicit Save/Start/Cancel actions open printer connections.");
    }
    async function request(url, options) {
        const response = await fetch(url, {cache: "no-store", ...options});
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || `HTTP ${response.status}`);
        return data;
    }
    async function refresh() {
        clearTimeout(timer); timer = null;
        if (polling || pending || !config) return;
        polling = true; render();
        try {
            state = await request("/api/state");
            uncertain = false;
            if (!state.error) text("error", "");
            if (state.busy) timer = setTimeout(refresh, 1000);
        } catch (error) {
            text("error", error.message + " Job may still be running; refresh, do not resubmit.");
        } finally { polling = false; render(); }
    }
    async function action(operation, body) {
        if (pending || polling || state.busy || uncertain) return;
        pending = true; clearTimeout(timer); text("error", ""); render();
        let accepted = false;
        try {
            state = await request("/api/" + operation, {method: "POST", headers: {
                "Content-Type": "application/json", "X-Finder-Token": config.token
            }, body: JSON.stringify(body)});
            accepted = true;
        } catch (error) {
            uncertain = true;
            text("error", error.message + " Refresh the result before another operation.");
        } finally { pending = false; render(); }
        // GET only reads cached state, never printer status.
        if (accepted) await refresh();
    }
    function receive(file) {
        if (!config || pending || polling || state.busy || uncertain || state.phase !== "empty" || !file) return;
        const stl = /\.stl$/i.test(file.name);
        if (!/\.(stl|gx|gcode|g)$/i.test(file.name) || !file.size || file.size > (stl ? config.model_limit : config.print_limit)) {
            text("error", "Choose a nonempty STL (up to 64 MiB) or GX/G-code/G (up to 8 MiB)."); return;
        }
        pending = true; clearTimeout(timer); text("error", ""); el("incoming").value = 0; render();
        const xhr = new XMLHttpRequest();
        xhr.open("POST", "/api/file?name=" + encodeURIComponent(file.name));
        xhr.setRequestHeader("Content-Type", "application/octet-stream");
        xhr.setRequestHeader("X-Finder-Token", config.token);
        xhr.timeout = 70000;
        xhr.upload.onprogress = event => { if (event.lengthComputable) el("incoming").value = 100 * event.loaded / event.total; };
        function failed(message) {
            uncertain = true; pending = false; text("error", message + " Refresh the result before selecting again."); render();
        }
        xhr.onerror = xhr.ontimeout = () => failed("Browser upload response lost.");
        xhr.onload = () => {
            try {
                const data = JSON.parse(xhr.responseText);
                if (xhr.status !== 200) throw new Error(data.error || "File was not accepted");
                state = data; pending = false;
                el("remote").value = state.suggested_name || "";
                render();
            } catch (error) { failed(error.message); }
        };
        xhr.send(file);
    }
    el("file").addEventListener("change", event => receive(event.target.files[0]));
    el("drop").addEventListener("dragover", event => { event.preventDefault(); el("drop").classList.add("over"); });
    el("drop").addEventListener("dragleave", () => el("drop").classList.remove("over"));
    el("drop").addEventListener("drop", event => {
        event.preventDefault(); el("drop").classList.remove("over");
        if (event.dataTransfer.files.length !== 1) { text("error", "Drop one file at a time."); return; }
        receive(event.dataTransfer.files[0]);
    });
    el("refresh").addEventListener("click", refresh);
    el("discard").addEventListener("click", () => {
        if (confirm("Remove current input/generated files? Private captures remain. This does not undo a printer save or cancel a print.")) {
            action("discard", {confirm: true}); el("file").value = "";
        }
    });
    el("slice").addEventListener("click", () => {
        if (confirm("Run trusted server-configured Orca and profiles offline? Output is NOT print-safety validated. No printer connection will be made.")) action("slice", {confirm: true});
    });
    el("save").addEventListener("click", () => {
        const message = config.owned_dummy ? `Save to the newly owned dummy at ${config.target}? Files are virtual/RAM-only and no G-code is executed. No start or stop is sent.` :
            `Save to ${config.target}? A proxy may reach real hardware and an existing remote file may be overwritten. Review the toolpaths first. No print start or stop will be sent.`;
        if (confirm(message)) {
            action("save", {confirm: true, remote_name: el("remote").value});
        }
    });
    el("start").addEventListener("click", () => {
        const message = config.owned_dummy ? `Start a virtual job for ${state.saved_name} in the owned dummy? No G-code will be executed.` :
            `Start saved file ${state.saved_name} on ${config.target}? This may HEAT AND MOVE the printer. Remote file contents were not read back; close other printer clients and supervise physically.`;
        if (confirm(message)) {
            action("start", {confirm: true, save_id: state.save_id});
        }
    });
    el("stop").addEventListener("click", () => {
        const message = config.owned_dummy ? "Cancel the virtual job in the owned dummy? No hardware is contacted." :
            `Request cancellation of the current job on ${config.target}? This can cancel a job started elsewhere. It is NOT an emergency stop or a guarantee of stopped motion or cooled heaters. Check the physical printer.`;
        if (confirm(message)) {
            action("stop", {confirm: true});
        }
    });
    request("/api/config").then(data => {
        config = data;
        text("target", data.owned_dummy ? `${data.target} · FRESH OWNED DUMMY · virtual Save/Start/Cancel, no G-code execution` :
            `${data.target} · printer uploads ${data.upload_enabled ? "ENABLED" : "disabled"}`);
        text("orca", data.slicing_enabled ? "Trusted server-side Orca/profiles configured. Slice offline, then download and review before a separate Save." :
            "Orca not configured. Supply --orca and trusted self-contained --machine / --process / --filament JSON on the server. Existing FlashPrint GX files work independently.");
        refresh();
    }).catch(error => text("error", error.message + " Reload the page using the exact server URL."));
    render();
})();
