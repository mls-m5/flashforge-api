// Minimal DOM/API model. No browser, HTTP listener, slicer or printer is started.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const path = require("node:path");
const elements = new Map(), posts = [], xhrs = [], documentHandlers = {};
let failNextPost = false;
const config = {token: "test-token", target: "127.0.0.1:9000", upload_enabled: true,
    slicing_enabled: true, sliced_upload_enabled: false, job_controls_enabled: true, model_limit: 64 * 1024 ** 2, print_limit: 8 * 1024 ** 2};
let state = {phase: "empty", busy: false};
function element(id) {
    if (!elements.has(id)) elements.set(id, {value: id === "brim-width" ? "5" : id === "brim-mode" ? "profile" : ["hole-compensation", "contour-compensation"].includes(id) ? "0" : "", textContent: "", disabled: false, hidden: false,
        handlers: {}, classList: {add() {}, remove() {}},
        addEventListener(name, fn) { this.handlers[name] = fn; }});
    return elements.get(id);
}
const fakeWindowTimers = new Map();
let timerId = 0;
class XHR {
    constructor() { this.upload = {}; this.headers = {}; xhrs.push(this); }
    open(method, url) { this.method = method; this.url = url; }
    setRequestHeader(key, value) { this.headers[key] = value; }
    send(file) { this.file = file; }
    finish(next) { state = next; this.status = 200; this.responseText = JSON.stringify(next); this.onload(); }
}
const context = {
    document: {getElementById: element, addEventListener(name, fn) {documentHandlers[name]=fn;} },
    XMLHttpRequest: XHR,
    confirm: () => { throw new Error("No browser confirmation dialogs allowed"); },
    clearTimeout: id => fakeWindowTimers.delete(id),
    setTimeout: fn => { fakeWindowTimers.set(++timerId, fn); return timerId; },
    async fetch(url, options = {}) {
        if (options.method === "POST") {
            assert.equal(options.headers["X-Finder-Token"], config.token);
            const data = JSON.parse(options.body);
            posts.push({url, data});
            if (failNextPost) { failNextPost = false; throw new Error("synthetic lost POST response"); }
            if (url === "/api/save") state = {...state, saved: true, phase: "saved", busy: false, saved_name: data.remote_name, save_id: "saved-identity", start_attempted: false};
            if (url === "/api/start") state = {...state, start_attempted: true, job_result: "start_acknowledged"};
            if (url === "/api/stop") state = {...state, job_result: "cancel_acknowledged"};
            if (url === "/api/discard") state = {busy: false, phase: "empty"};
            if (url === "/api/slice") state = {...state, busy: false, phase: "review", sliced: true, artifact: true,
                slice_settings: data.settings, effective_quality: {layer_height: data.settings.layer_height || "0.18",
                    initial_layer_print_height: "0.27", brim_type: "outer_only", brim_width: "5", brim_object_gap: "0.1",
                    xy_hole_compensation: String(data.settings.xy_hole_compensation ?? 0), xy_contour_compensation: String(data.settings.xy_contour_compensation ?? 0)}};
        }
        return {ok: true, json: async () => url === "/api/config" ? config : {...state}};
    }
};
const flush = () => new Promise(resolve => setImmediate(resolve));
function click(id) { if (!element(id).disabled) element(id).handlers.click(); }
function choose(name, size) { element("file").handlers.change({target: {files: [{name, size}]}}); }
async function main() {
    vm.runInNewContext(fs.readFileSync(path.join(__dirname, "../finderlab/webstatic/app.js"), "utf8"), context);
    await flush();
    assert.equal(posts.length, 0, "initial configuration/state reads must not save or slice");
    assert.equal(element("hole-compensation").value, "0", "new UI default disables hole compensation");
    choose("bad.obj", 10); assert.equal(xhrs.length, 0);
    choose("sample.gx", 5129);
    assert.equal(xhrs.length, 1);
    assert.equal(posts.length, 0, "file selection only posts file bytes");
    assert.equal(xhrs[0].headers["X-Finder-Token"], config.token);
    xhrs[0].finish({phase: "file_ready", busy: false, name: "sample.gx", suggested_name: "sample.gx", artifact: true, size: 5129});
    assert.equal(element("remote").value, "sample.gx");
    click("save"); click("save");
    await flush();
    assert.equal(posts.length, 1, "double click submits once");
    assert.equal(posts[0].url, "/api/save");
    assert.equal(posts[0].data.confirm, true);
    assert.match(element("result").textContent, /Final save confirmed/);
    assert.equal(element("save").disabled, true);
    assert.equal(posts.filter(p => p.url === "/api/start").length, 0, "save never starts automatically");
    element("remote").value = "different.gx";
    click("start"); click("start"); await flush();
    assert.equal(posts.filter(p => p.url === "/api/start").length, 1);
    assert.equal(posts.at(-1).data.save_id, "saved-identity");
    assert.equal(posts.at(-1).data.remote_name, undefined, "Start does not use the editable remote input");
    assert.equal(element("start").disabled, true);
    assert.match(element("job-result").textContent, /may heat\/move/);
    click("stop"); await flush();
    assert.equal(posts.at(-1).url, "/api/stop");
    assert.match(element("job-result").textContent, /does NOT prove READY/);
    click("discard"); await flush();
    choose("model.stl", 100);
    xhrs[1].finish({phase: "model_ready", busy: false, name: "model.stl", suggested_name: "model.gcode", artifact: false, size: 100, source_sha256:'b'.repeat(64)});
    assert.equal(element("save").disabled, true);
    assert.equal(element("remote").value, "model.gcode");
    assert.equal(element("quality-settings").disabled, false);
    documentHandlers['finder-model-preparing']({detail:true});await flush();
    assert.equal(element('slice').disabled,true,'preparing geometry blocks overlapping jobs immediately');
    const beforePreview=posts.length;click('slice');await flush();assert.equal(posts.length,beforePreview);
    documentHandlers['finder-model-preparing']({detail:false});await flush();
    assert.equal(element('slice').disabled,false,'cached state is reconciled after preparation/abort');
    assert.equal(element("brim-width").disabled, true);
    element("brim-mode").value = "outer";
    element("brim-mode").handlers.change();
    assert.equal(element("brim-width").disabled, false);
    element("brim-width").value = "99";
    const beforeSlice = posts.length;
    click("slice"); await flush();
    assert.equal(posts.length, beforeSlice, "invalid width must not submit");
    element("brim-width").value = "5";
    element("layer-height").value = "0.12";
    for (const value of ["0.51", "-0.51", "NaN", "Infinity"]) {
        element("hole-compensation").value = value;
        click("slice"); await flush();
        assert.equal(posts.length, beforeSlice, "invalid hole compensation must not submit");
    }
    element("hole-compensation").value = "";
    element("hole-compensation").validity = {badInput: true};
    click("slice"); await flush();
    assert.equal(posts.length, beforeSlice, "bad numeric input must not silently select profile");
    element("hole-compensation").validity = {badInput: false};
    element("hole-compensation").value = "0.2";
    for (const value of ["0.51", "-0.51", "NaN", "Infinity"]) {
        element("contour-compensation").value = value;
        click("slice"); await flush();
        assert.equal(posts.length, beforeSlice, "invalid contour compensation must not submit");
    }
    element("contour-compensation").value = "";
    element("contour-compensation").validity = {badInput: true};
    click("slice"); await flush();
    assert.equal(posts.length, beforeSlice);
    element("contour-compensation").validity = {badInput: false};
    element("contour-compensation").value = "-0.2";
    assert.equal(posts.length, beforeSlice, "quality choice alone does not slice");
    const draft={source_sha256:'b'.repeat(64),transform:{scale:2,x:3,y:4,rotate_z:90},error:'',locked:false};
    documentHandlers['finder-model-transform']({detail:{...draft,source_sha256:'old'}});await flush();
    assert.equal(element('slice').disabled,true,'stale model edits cannot slice another source');
    documentHandlers['finder-model-transform']({detail:{...draft,error:'invalid mesh layout'}});await flush();
    assert.equal(element('slice').disabled,true);
    documentHandlers['finder-model-transform']({detail:{...draft,locked:true}});await flush();
    assert.equal(element('slice').disabled,true,'another tab already sliced this source');
    documentHandlers['finder-model-transform']({detail:draft});await flush();
    assert.equal(element('slice').disabled,false);assert.equal(posts.length,beforeSlice,'geometry edits never auto-slice');
    click("slice"); await flush();
    assert.equal(posts.at(-1).url, "/api/slice");
    assert.deepEqual(posts.at(-1).data.transform,draft.transform);assert.equal(posts.at(-1).data.source_sha256,draft.source_sha256);
    documentHandlers['finder-model-transform']({detail:null});await flush();
    assert.deepEqual(posts.at(-1).data.settings, {layer_height: 0.12, brim: "outer", brim_width: 5, xy_hole_compensation: 0.2, xy_contour_compensation: -0.2});
    assert.equal(element("quality-settings").disabled, true);
    assert.match(element("applied-quality").textContent, /layer 0.12 mm/);
    assert.match(element("applied-quality").textContent, /first layer 0.27 mm/);
    assert.match(element("applied-quality").textContent, /hole compensation 0.2 mm per edge/);
    assert.equal(element("hole-compensation").disabled, true);
    assert.equal(element("contour-compensation").disabled, true);
    assert.match(element("applied-quality").textContent, /outer contour -0.2 mm per edge/);
    element("hole-compensation").value = "0.4";
    const immutable = posts.length; click("slice");
    assert.equal(posts.length, immutable, "an existing slice cannot silently change");
    assert.match(element("applied-quality").textContent, /hole compensation 0.2 mm per edge/);
    assert.equal(posts.filter(p => p.url === "/api/save").length, 1, "slice does not automatically save");
    assert.equal(element("download").hidden, false);
    assert.match(element("slice-status").textContent, /Slice completed/);
    assert.match(element("slicer-log").textContent, /finished successfully/);
    assert.equal(element("save").disabled, true, "unreviewed generated output stays blocked");
    click("discard"); await flush();
    choose("again.gx", 20);
    xhrs[2].onerror();
    assert.equal(element("file").disabled, true, "lost file response requires a state refresh");
    assert.equal(element("save").disabled, true);
    click("refresh"); await flush();
    assert.equal(element("file").disabled, false);
    assert.equal(fakeWindowTimers.size, 0);
    choose("uncertain.gx", 20);
    xhrs[3].finish({phase: "file_ready", busy: false, name: "uncertain.gx", artifact: true, size: 20});
    failNextPost = true;
    click("save"); await flush();
    assert.equal(element("save").disabled, true);
    assert.match(element("error").textContent, /lost POST response/);
    assert.match(element("phase").textContent, /HTTP response unknown/);
    const count = posts.length;
    click("save"); assert.equal(posts.length, count, "lost submission is not retried");
    click("refresh"); await flush();
    assert.equal(element("save").disabled, false);
    config.job_controls_enabled = false;
    click("refresh"); await flush();
    assert.equal(element("start").disabled, true);
    assert.equal(element("stop").disabled, true);
    const before = posts.length;
    click("start"); click("stop");
    assert.equal(posts.length, before);
    state = {busy: false, phase: "failed", error: "Transport endpoint is not connected", slicer_log: ""};
    click("refresh"); await flush();
    assert.match(element("slicer-log").textContent, /Transport endpoint is not connected/);
    config.owned_dummy = true;
    config.job_controls_enabled = true;
    state = {busy: false, phase: "start_acknowledged", job_result: "start_acknowledged", saved: true, start_attempted: true};
    click("refresh"); await flush();
    assert.match(element("job-result").textContent, /No G-code, motion or heating/);
    assert.match(element("job-gating").textContent, /owned dummy, not hardware/);
    assert.equal(element("stop").disabled, false);
    click("stop"); await flush();
    assert.match(element("job-result").textContent, /Virtual cancel acknowledged/);
    click("discard"); await flush();
    choose("profile-hole.3mf", 100);
    xhrs.at(-1).finish({phase: "model_ready", busy: false, name: "profile-hole.stl", suggested_name: "profile-hole.gcode", artifact: false});
    element("hole-compensation").value = "";
    element("contour-compensation").value = "";
    click("slice"); await flush();
    assert.equal(posts.at(-1).data.settings.xy_hole_compensation, null, "blank explicitly preserves server profile");
    assert.equal(posts.at(-1).data.settings.xy_contour_compensation, null);
    console.log("Standalone page quality/hole compensation, confirmations, slice/save separation and uncertainty tests passed.");
}
main().catch(error => { console.error(error); process.exitCode = 1; });
