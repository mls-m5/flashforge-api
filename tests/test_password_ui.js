"use strict";
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const source = fs.readFileSync("finderlab/webstatic/password.js", "utf8");
const flush = () => new Promise(resolve => setImmediate(resolve));

async function page(enabled = true) {
    const elements = new Map(), listeners = {}, requests = [];
    function el(id) {
        if (!elements.has(id)) elements.set(id, {value: "", hidden: true, disabled: false, textContent: "", handlers: {},
            addEventListener(name, callback) { this.handlers[name] = callback; }});
        return elements.get(id);
    }
    let respond = async () => ({ok: true, json: async () => ({password_changed: true, message: "Saved; log in again."})});
    const context = {document: {getElementById: el}, window: {addEventListener(name, callback) { listeners[name] = callback; }},
        fetch: async (url, options) => {
            requests.push({url, options});
            if (url === "/api/config") return {ok: true, json: async () => ({password_change_enabled: enabled, token: "session-token"})};
            return respond();
        }};
    vm.runInNewContext(source, context);
    await flush();
    return {el, requests, listeners, response(callback) { respond = callback; },
        submit() { return el("password-form").handlers.submit({preventDefault() {}}); }};
}

(async () => {
    const p = await page();
    assert.equal(p.el("password-settings").hidden, false);
    assert.equal(p.requests.length, 1, "opening page never changes password");
    function fill(next = "new private passphrase", repeat = next) {
        p.el("password-current").value = "old private passphrase";
        p.el("password-new").value = next;
        p.el("password-repeat").value = repeat;
    }
    fill("new private passphrase", "different"); await p.submit();
    assert.equal(p.requests.length, 1);
    fill("short"); await p.submit(); assert.equal(p.requests.length, 1);
    fill(); await p.submit();
    assert.equal(p.requests.length, 2);
    const request = p.requests[1];
    assert.equal(request.url, "/api/password");
    assert.equal(request.options.headers["X-Finder-Token"], "session-token");
    assert.deepEqual(JSON.parse(request.options.body), {confirm: true, current_password: "old private passphrase", new_password: "new private passphrase"});
    assert.equal(p.el("password-new").value, "");
    assert.equal(p.el("password-current").value, "");
    assert.equal(p.el("password-repeat").value, "");
    assert.equal(p.el("password-result").textContent, "Saved; log in again.");
    fill();
    p.response(async () => { throw new Error("lost response"); });
    await p.submit(); await flush();
    assert.equal(p.requests.length, 3, "lost response is not retried");
    assert.match(p.el("password-result").textContent, /No automatic retry/);
    assert.equal(p.el("password-new").value, "");
    fill(); p.listeners.pagehide(); assert.equal(p.el("password-current").value, "");
    let finish;
    p.response(() => new Promise(resolve => { finish = resolve; }));
    fill(); const pending = p.submit(); await flush();
    assert.equal(p.el("password-save").disabled, true);
    await p.submit(); assert.equal(p.requests.length, 4, "no duplicate submit while pending");
    finish({ok: true, json: async () => ({password_changed: true, message: "saved"})}); await pending;
    const local = await page(false);
    assert.equal(local.el("password-settings").hidden, true);
    await local.submit(); assert.equal(local.requests.length, 1);
    console.log("Password UI capability, explicit intent, confirmation fields, clearing, no retry/double-submit and no printer route checks passed.");
})().catch(error => { console.error(error); process.exitCode = 1; });
