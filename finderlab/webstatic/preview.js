import {ToolpathView} from './toolpath-view.js';

// No mutation/printer endpoints: only cached state and the current server artifact.
const el = id => document.getElementById(id);
let view, worker, abort, deadline, timer, revision = 0, stateRevision = 0;
let identity = '', attempted = '', layers = [], enabled = true;
let polling = false, refreshRequested = false, closed = false;
const text = (id, value) => { el(id).textContent = value; };
function cancel() {
    revision++; if (worker) worker.terminate(); worker = null;
    if (abort) abort.abort(); abort = null; clearTimeout(deadline);
}
function clear(message) {
    cancel(); if (view) view.clear(); layers = [];
    el('preview-layer').disabled = true; text('preview-height', 'No current preview');
    text('preview-warnings', ''); text('preview-message', message);
}
function filter() {
    const index = Number(el('preview-layer').value);
    const height = index >= layers.length ? Infinity : layers[index];
    text('preview-height', Number.isFinite(height) ? `Through deposition height ${height.toFixed(3)} mm (${index+1}/${layers.length})` : 'All heights (including startup/end travel if enabled)');
    if (view) view.filter(height, el('preview-travel').checked);
}
async function load(state) {
    const ticket = revision, key = identity;
    attempted = key;
    try {
        if (!view) view = new ToolpathView(el('preview-canvas'));
        abort = new AbortController();
        deadline = setTimeout(() => {
            if (ticket === revision) clear('Preview deadline exceeded. Use Reload preview to retry; no printer action was sent.');
        }, 30000);
        text('preview-message', `Loading ${state.name} from this server…`);
        const response = await fetch('/api/artifact', {cache: 'no-store', signal: abort.signal,
            headers: {'If-Match': '"' + state.sha256 + '"'}});
        if (!response.ok) throw new Error(`Artifact unavailable/changed (HTTP ${response.status}).`);
        if (response.headers.get('ETag') !== '"' + state.sha256 + '"') throw new Error('Artifact identity mismatch.');
        const size = Number(response.headers.get('Content-Length'));
        if (!Number.isInteger(size) || size < 1 || size > 8*1024*1024) throw new Error('Invalid artifact size.');
        const buffer = await response.arrayBuffer();
        if (ticket !== revision || identity !== key) return;
        if (buffer.byteLength !== size) throw new Error('Incomplete artifact response.');
        text('preview-message', 'Interpreting linear toolpaths in a worker…');
        worker = new Worker('/toolpath-worker.js');
        worker.onerror = () => fail('Preview worker failed.', ticket);
        worker.onmessage = event => {
            if (ticket !== revision || identity !== key) return;
            if (event.data.error) { fail(event.data.error, ticket); return; }
            try {
                const data = event.data.result;
                view.setToolpath(data); layers = data.layers;
                el('preview-layer').max = String(layers.length);
                el('preview-layer').value = String(layers.length); el('preview-layer').disabled = false;
                text('preview-message', `${state.name} · ${state.sha256.slice(0,12)} · ${data.counts.extrusion} extrusion / ${data.counts.travel} travel / ${data.counts.unknown} unknown segments. ${data.counts.unresolved} unresolved moves omitted. ${data.counts.unsupported} unsupported commands/lines.`);
                text('preview-warnings', data.limitations + '\n' + data.warnings.join('\n'));
                filter();
                worker.terminate(); worker = null; clearTimeout(deadline); abort = null;
            } catch (error) { fail(error.message, ticket); }
        };
        worker.postMessage({buffer, options: {assumeAbsoluteE: el('preview-assume-e').checked}}, [buffer]);
    } catch (error) { if (ticket === revision) fail(error.message, ticket); }
}
function fail(message, ticket) {
    if (ticket !== revision) return;
    clear('Preview unavailable: ' + message + ' Upload/slicing controls remain independent.');
}
function accept(state) {
    const key = state.artifact && !state.busy && /^[0-9a-f]{64}$/.test(state.sha256 || '') ? state.sha256 + ':' + state.name : '';
    if (key !== identity) {
        identity = key; attempted = '';
        clear(key ? 'New artifact available.' : 'Choose a print file or finish Slice. No complete idle artifact is selected.');
    }
    if (enabled && key && attempted !== key) load(state);
}
async function poll() {
    clearTimeout(timer);
    if (closed) return;
    if (polling) { refreshRequested = true; return; }
    polling = true; const start = stateRevision;
    try {
        const response = await fetch('/api/state', {cache: 'no-store'});
        if (!response.ok) throw new Error('Cannot read artifact state.');
        const state = await response.json();
        if (!closed && !refreshRequested && start === stateRevision) accept(state);
    } catch (error) {
        if (!closed && !refreshRequested && start === stateRevision) { identity = ''; attempted = ''; clear(error.message); }
    } finally {
        polling = false;
        if (!closed) { timer = setTimeout(poll, refreshRequested ? 0 : 2000); refreshRequested = false; }
    }
}
document.addEventListener('finder-artifact-state', event => { stateRevision++; accept(event.detail); });
el('preview-layer').addEventListener('input', filter);
el('preview-travel').addEventListener('change', filter);
el('preview-fit').addEventListener('click', () => { if (view) view.reset(); });
el('preview-reload').addEventListener('click', () => { attempted = ''; identity = ''; clear('Reloading current artifact…'); poll(); });
el('preview-assume-e').addEventListener('change', () => { attempted = ''; identity = ''; clear('Reinterpreting with the selected E assumption…'); poll(); });
el('preview-enabled').addEventListener('change', event => {
    enabled = event.target.checked; attempted = '';
    clear(enabled ? 'Loading current artifact…' : 'Preview paused; no geometry retained.');
    if (enabled) poll();
});
el('preview-canvas').addEventListener('preview-context-lost', () => {
    enabled = false; el('preview-enabled').checked = false;
    clear('WebGL context lost. Reload the page to recreate the viewer. File/job controls are independent.');
});
window.addEventListener('pagehide', () => { closed = true; enabled = false; refreshRequested = false; cancel(); clearTimeout(timer); });
window.addEventListener('pageshow', event => {
    if (event.persisted) { closed = false; enabled = el('preview-enabled').checked; identity = ''; attempted = ''; poll(); }
});
poll();
