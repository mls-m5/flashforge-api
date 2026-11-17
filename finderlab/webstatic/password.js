"use strict";
(() => {
    const el = id => document.getElementById(id);
    const section = el("password-settings");
    let config = null, pending = false;
    const fields = ["password-current", "password-new", "password-repeat"];
    function clear() { for (const id of fields) el(id).value = ""; }
    function controls(disabled) {
        for (const id of [...fields, "password-save"]) el(id).disabled = disabled;
    }
    el("password-form").addEventListener("submit", async event => {
        event.preventDefault();
        if (pending || !config || !config.password_change_enabled) return;
        const current = el("password-current").value;
        const next = el("password-new").value;
        if (next !== el("password-repeat").value) {
            el("password-result").textContent = "The new passwords do not match.";
            return;
        }
        if (Array.from(next).length < 12 || Array.from(next).length > 128) {
            el("password-result").textContent = "Use a password of12–128 characters.";
            return;
        }
        pending = true;
        controls(true);
        el("password-result").textContent = "Saving password…";
        try {
            const response = await fetch("/api/password", {
                method: "POST", cache: "no-store", headers: {
                    "Content-Type": "application/json", "X-Finder-Token": config.token
                },
                body: JSON.stringify({confirm: true, current_password: current, new_password: next})
            });
            const data = await response.json();
            if (!response.ok) throw new Error(data.error || "Password change was not accepted.");
            if (data.password_changed !== true) throw new Error("Password response unknown; do not automatically retry.");
            el("password-result").textContent = data.message;
        } catch (error) {
            el("password-result").textContent = error.message + " No automatic retry. A lost response may mean it was saved; try the new login or use offline reset.";
        } finally {
            clear();
            pending = false;
            controls(false);
        }
    });
    fetch("/api/config", {cache: "no-store"}).then(async response => {
        if (!response.ok) throw new Error("Configuration unavailable");
        config = await response.json();
        section.hidden = !config.password_change_enabled;
        controls(!config.password_change_enabled);
    }).catch(() => { section.hidden = true; controls(true); });
    window.addEventListener("pagehide", clear);
})();
