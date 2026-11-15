// Virtual panel only: mocked DOM/HTTP, not a rendered browser or firmware test.
const assert = require('node:assert/strict');
const fs = require('node:fs'), vm = require('node:vm'), path = require('node:path');
const flush = () => new Promise(resolve => setImmediate(resolve));
function setup(enabled = true) {
    const elements = new Map(), requests = [], timers = new Map();
    let next = 0, fail = false, readFail = false, release = null;
    let report = {enabled, virtual_only: true, busy: false, job_active: false, blocked: false,
        message: enabled ? 'Virtual rehearsal only' : 'Physical manual controls are locked',
        state: enabled ? {revision: 0, rgb: [0, 0, 0], offsets_mm: {X: 0, Y: 0, Z: 0}, extruded_mm: 0, warm_nozzle_simulated: false} : null};
    function el(id) {
        if (!elements.has(id)) elements.set(id, {value: {'manual-colour': '#888a85', 'manual-xy-step': '.1',
            'manual-z-step': '.1', 'manual-e-step': '1'}[id] || '', checked: false, disabled: false, handlers: {},
            addEventListener(name, fn) {this.handlers[name] = fn;}});
        return elements.get(id);
    }
    const context = {
        document: {getElementById: el}, confirm: () => {throw new Error('No confirmation popup allowed');},
        setTimeout(fn) {timers.set(++next, fn); return next;}, clearTimeout(id) {timers.delete(id);},
        async fetch(url, options = {}) {
            requests.push({url, options});
            if (url === '/api/config') return {ok: true, json: async () => ({manual_virtual_enabled: enabled, token: 'test'})};
            if (url === '/api/manual') {
                assert.equal(options.method, 'POST');
                assert.equal(options.headers['X-Finder-Token'], 'test');
                if (release) await new Promise(resolve => {release.resolve = resolve;});
                if (fail) throw new Error('synthetic lost response');
                const data = JSON.parse(options.body);
                assert.equal(data.confirm, true); assert.equal(data.revision, report.state.revision);
                const s = {...report.state, offsets_mm: {...report.state.offsets_mm}, revision: report.state.revision + 1};
                if (data.action === 'jog') s.offsets_mm[data.axis] += data.distance;
                if (data.action === 'light') s.rgb = data.rgb;
                if (data.action === 'extrude') s.extruded_mm += data.distance;
                if (data.action === 'warm') s.warm_nozzle_simulated = data.enabled;
                report = {...report, state: s};
            } else {
                assert.equal(url, '/api/manual-state');
                if (readFail) throw new Error('synthetic failed read');
            }
            return {ok: true, json: async () => report};
        }
    };
    vm.runInNewContext(fs.readFileSync(path.join(__dirname, '../finderlab/webstatic/manual.js'), 'utf8'), context);
    return {el, requests, timers,
        set fail(value) {fail = value;}, set readFail(value) {readFail = value;},
        set release(value) {release = value;}, get report() {return report;},
        set report(value) {report = value;}};
}
async function main() {
    const h = setup(); await flush();
    const count = () => h.requests.filter(r => r.options.method === 'POST').length;
    assert.equal(count(), 0, 'startup is cached reads only');
    assert.equal(h.el('manual-controls').disabled, false);
    assert.equal(h.el('manual-feed').disabled, true);
    h.el('manual-feed').handlers.click(); await flush(); assert.equal(count(), 0, 'cold extruder locked');
    h.el('manual-light').handlers.click(); await flush();
    assert.deepEqual(h.report.state.rgb, [136, 138, 133]);
    assert.match(h.el('manual-values').textContent, /NOT printer feedback/);
    const release = {}; h.release = release;
    h.el('manual-x-plus').handlers.click(); await flush();
    const during = count();
    h.el('manual-x-plus').handlers.click(); await flush(); assert.equal(count(), during, 'double click cannot queue another step');
    release.resolve(); h.release = null; await flush();
    assert.equal(h.report.state.offsets_mm.X, .1);
    h.el('manual-z-step').value = '5';
    h.el('manual-z-plus').handlers.click(); await flush(); assert.equal(count(), during, 'no 5 mm Z step');
    h.el('manual-z-step').value = '.1';
    h.el('manual-warm').checked = true;
    h.el('manual-warm').handlers.change({target: h.el('manual-warm')}); await flush();
    assert.equal(h.el('manual-feed').disabled, false);
    h.el('manual-retract').handlers.click(); await flush(); assert.equal(h.report.state.extruded_mm, -1);
    h.fail = true;
    h.el('manual-y-plus').handlers.click(); await flush();
    assert.match(h.el('manual-result').textContent, /UNKNOWN/);
    assert.equal(h.el('manual-controls').disabled, true);
    const lost = count(); h.fail = false;
    const timer = [...h.timers.values()][0]; await timer(); await flush();
    assert.equal(count(), lost, 'automatic refresh never retries a step');
    assert.equal(h.el('manual-controls').disabled, true, 'only explicit refresh clears uncertainty');
    h.el('manual-refresh').handlers.click(); await flush();
    assert.equal(h.el('manual-controls').disabled, false);
    let prevented = false;
    h.el('manual-controls').handlers.keydown({repeat: true, preventDefault() {prevented = true;}});
    assert.equal(prevented, true);
    h.report = {...h.report, job_active: true};
    h.el('manual-refresh').handlers.click(); await flush();
    assert.equal(h.el('manual-controls').disabled, true, 'active virtual job locks controls');
    h.readFail = true; h.el('manual-refresh').handlers.click(); await flush();
    assert.match(h.el('manual-values').textContent, /No known/);
    assert.equal(h.el('manual-controls').disabled, true);
    assert(h.requests.every(r => ['/api/config', '/api/manual-state', '/api/manual'].includes(r.url)));
    const locked = setup(false); await flush();
    locked.el('manual-x-plus').handlers.click(); await flush();
    assert.equal(locked.el('manual-controls').disabled, true);
    assert.equal(locked.requests.filter(r => r.options.method === 'POST').length, 0);
    assert.equal(locked.timers.size, 0, 'configured targets do not gain a manual polling loop');
    console.log('Virtual manual UI gates, confirmation, no-repeat and uncertainty tests passed.');
}
main().catch(error => {console.error(error); process.exitCode = 1;});
