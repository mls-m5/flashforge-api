// Active UI wiring only: no real browser/printer, no automatic mutating requests.
const assert = require('node:assert/strict');
const fs = require('node:fs'), vm = require('node:vm'), path = require('node:path');
const elements = new Map(), calls = [], timers = new Map();
let next = 0, confirmation = false, fail = false;
let report = {passive: false, monitor_running: true, monitor_stopping: false, stale: false,
    source: 'dummy-monitor', session: 's0001', upstream: '127.0.0.1:12345', message: 'Active status polling',
    samples: {M105: {values: {nozzle: 20, nozzle_target: 0, bed: 0, bed_target: 0}, observed_utc: 'example', age_seconds: 0}}};
function el(id) {
    if (!elements.has(id)) elements.set(id, {value: '', disabled: false, handlers: {},
        addEventListener(name, fn) {this.handlers[name] = fn;}, classList: {add() {}, remove() {}}});
    return elements.get(id);
}
const context = {
    document: {getElementById: el}, confirm: () => confirmation,
    setTimeout(fn) {timers.set(++next, fn); return next;}, clearTimeout(id) {timers.delete(id);},
    async fetch(url, options = {}) {
        calls.push({url, options});
        if (url === '/api/config') return {ok: true, json: async () => ({active_monitor_enabled: true, token: 'test-token', target: 'owned dummy'})};
        if (url === '/api/state') return {ok: true, json: async () => ({busy: false, phase: 'empty'})};
        if (url === '/api/monitor') {
            if (fail) throw new Error('synthetic lost response');
            assert.equal(options.method, 'POST');
            assert.equal(options.headers['X-Finder-Token'], 'test-token');
            const body = JSON.parse(options.body);
            assert.equal(body.confirm, true);
            report = {...report, monitor_running: body.enabled, stale: !body.enabled};
        } else assert.equal(url, '/api/printer-status');
        return {ok: true, json: async () => report};
    }
};
const flush = () => new Promise(resolve => setImmediate(resolve));
async function main() {
    vm.runInNewContext(fs.readFileSync(path.join(__dirname, '../finderlab/webstatic/app.js'), 'utf8'), context);
    await flush();
    assert.equal(calls.filter(c => c.options.method === 'POST').length, 0, 'startup/browser refresh must not start a monitor or print');
    assert.match(el('printer-status-mode').textContent, /active/);
    assert.equal(el('monitor-start').disabled, true);
    assert.equal(el('monitor-stop').disabled, false);
    await el('monitor-stop').handlers.click(); await flush();
    assert.equal(calls.filter(c => c.url === '/api/monitor').length, 1);
    assert.equal(el('monitor-start').disabled, false);
    await el('monitor-start').handlers.click(); await flush();
    assert.equal(calls.filter(c => c.url === '/api/monitor').length, 1, 'restart needs confirmation');
    confirmation = true;
    await el('monitor-start').handlers.click(); await flush();
    assert.equal(el('monitor-stop').disabled, false);
    fail = true;
    await el('monitor-stop').handlers.click(); await flush();
    assert.match(el('monitor-error').textContent, /unknown/);
    const count = calls.filter(c => c.url === '/api/monitor').length;
    await el('printer-refresh').handlers.click(); await flush();
    assert.equal(calls.filter(c => c.url === '/api/monitor').length, count, 'GET refresh never retries a lost monitor mutation');
    assert.equal(calls.filter(c => c.url === '/api/stop' || c.url === '/api/start' || c.url === '/api/save').length, 0);
    assert.equal(timers.size, 1);
    console.log('Active status UI controls, startup and no-job-action tests passed.');
}
main().catch(error => {console.error(error); process.exitCode = 1;});
