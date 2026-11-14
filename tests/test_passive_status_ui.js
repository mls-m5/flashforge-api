// Passive status view: mocked HTTP/DOM only, no printer or browser.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const path = require("node:path");
const elements = new Map(), requests = [], timers = new Map();
let timerId = 0, fail = false, release = null;
function el(id) {
    if (!elements.has(id)) elements.set(id, {value: "", disabled: false, handlers: {},
        addEventListener(name, fn) { this.handlers[name] = fn; }, classList: {add() {}, remove() {}}});
    return elements.get(id);
}
let report = {source: "synthetic-capture", upstream: "192.0.2.10:8899", session: "s0001", stale: false,
    message: "Observed proxy replies only", capture_finalized: false,
    samples: {
        M105: {values: {nozzle: 220, nozzle_target: 220, bed: 0, bed_target: 0}, stale: false, observed_utc: "example", age_seconds: 1},
        M119: {values: {machine: "BUILDING_FROM_SD", move: "MOVING"}, stale: false, observed_utc: "example", age_seconds: 1},
        M27: {values: {done: 101, total: 100, percent: 100, over_total: true}, stale: false, observed_utc: "example", age_seconds: 1}
    }};
const context = {
    document: {getElementById: el},
    setTimeout(fn) { timers.set(++timerId, fn); return timerId; },
    clearTimeout(id) { timers.delete(id); },
    async fetch(url, options = {}) {
        requests.push({url, options});
        assert.notEqual(options.method, "POST", "status view cannot initiate printer actions");
        if (url === "/api/config") return {ok: true, json: async () => ({passive_status_enabled: true})};
        if (url === "/api/state") return {ok: true, json: async () => ({phase: "empty", busy: false})};
        assert.equal(url, "/api/printer-status");
        if (release) await new Promise(resolve => { release.resolve = resolve; });
        if (fail) throw new Error("synthetic offline HTTP");
        return {ok: true, json: async () => report};
    }
};
const flush = () => new Promise(resolve => setImmediate(resolve));
async function main() {
    vm.runInNewContext(fs.readFileSync(path.join(__dirname, "../finderlab/webstatic/app.js"), "utf8"), context);
    await flush();
    assert.match(el("printer-temperature").textContent, /220 \/ 220/);
    assert.match(el("printer-machine").textContent, /BUILDING_FROM_SD/);
    assert.equal(el("printer-progress").value, 100);
    assert.match(el("printer-progress-text").textContent, /more than total/);
    assert.equal(timers.size, 1);
    report = {...report, stale: true, samples: {M105: {...report.samples.M105, stale: true, age_seconds: 20}}};
    el("printer-refresh").handlers.click(); await flush();
    assert.match(el("printer-temperature").textContent, /stale/);
    assert.equal(el("printer-machine").textContent, "unknown");
    assert.match(el("printer-status-message").textContent, /STALE/);
    release = {};
    el("printer-refresh").handlers.click(); await flush();
    const count = requests.length;
    el("printer-refresh").handlers.click(); await flush();
    assert.equal(requests.length, count, "manual refresh cannot create overlapping polls");
    fail = true; release.resolve(); await flush();
    assert.equal(el("printer-temperature").textContent, "unknown", "failed reads cannot retain fresh-looking values");
    assert.equal(el("printer-progress").value, 0);
    assert.match(el("printer-status-message").textContent, /Cannot read/);
    assert.equal(timers.size, 1);
    console.log("Passive status UI freshness, error and polling tests passed.");
}
main().catch(error => {console.error(error); process.exitCode = 1;});
