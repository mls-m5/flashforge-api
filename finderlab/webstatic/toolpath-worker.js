/* Offline linear-toolpath interpretation. Never firmware execution or safety validation. */
"use strict";
function parseToolpath(buffer, options = {}) {
    const bytes = new Uint8Array(buffer);
    const maxSegments = Math.min(options.maxSegments || 250000, 250000);
    if (!bytes.length || bytes.length > 8 * 1024 * 1024) throw new Error("Preview input must contain 1 byte to 8 MiB.");
    let offset = 0;
    const signature = new TextDecoder().decode(bytes.subarray(0, 10));
    if (signature === "xgcode 1.0") {
        if (bytes.length < 28) throw new Error("Truncated GX header.");
        offset = new DataView(buffer).getUint32(20, true);
        if (offset < 28 || offset >= bytes.length) throw new Error("Invalid GX G-code offset.");
    }
    const text = new TextDecoder("utf-8", {fatal: true}).decode(bytes.subarray(offset));
    if (text.includes("\0")) throw new Error("NUL in G-code body; unsupported binary format.");
    const positions = new Float32Array(maxSegments * 6), kinds = new Uint8Array(maxSegments);
    const heights = new Float32Array(maxSegments), layers = new Set(), warnings = [];
    const counts = {extrusion: 0, travel: 0, unknown: 0, unresolved: 0, unsupported: 0};
    let sawRetraction = false;
    let pos = [null, null, null], xyz = null, eMode = options.assumeAbsoluteE ? "absolute" : null;
    let e = null, units = 1, explicitUnits = false, debt = 0, count = 0, lineNo = 0, start = 0;
    const warn = message => { if (warnings.length < 30 && !warnings.includes(message)) warnings.push(message); };
    if (options.assumeAbsoluteE) warn("Absolute E ASSUMED by the viewer; not firmware evidence.");
    const invalidate = () => { pos = [null, null, null]; xyz = eMode = e = null; debt = 0; };
    while (start < text.length) {
        let end = text.indexOf("\n", start); if (end < 0) end = text.length;
        const raw = text.slice(start, end); start = end + 1;
        if (++lineNo > 500000 || raw.length > 4096) throw new Error("Preview line length/count limit exceeded.");
        const line = raw.split(";", 1)[0].trim().toUpperCase();
        if (!line) continue;
        const match = /^([GMT]\d+(?:\.\d+)?)(?=\s|[XYZEFST]|$)/.exec(line);
        if (!match || /[()*,]/.test(line)) {
            counts.unsupported++; warn("Unsupported syntax; affected paths omitted, state invalidated."); invalidate(); continue;
        }
        const command = match[1], tail = line.slice(match[0].length), values = {};
        let invalid = false;
        const rest = tail.replace(/([A-Z])([+-]?(?:\d+(?:\.\d*)?|\.\d+))/g, (_, key, value) => {
            if (key in values) invalid = true;
            const n = Number(value);
            if (!Number.isFinite(n) || Math.abs(n) > 1e7) throw new Error(`Numeric field out of bounds at line ${lineNo}.`);
            values[key] = n; return "";
        });
        if (["G0", "G1", "G92"].includes(command) && (invalid || rest.trim() || Object.keys(values).some(k => !(command === "G92" ? "XYZE" : "XYZEF").includes(k)))) {
            counts.unsupported++; warn("Ambiguous motion parameters; affected paths omitted."); invalidate(); continue;
        }
        if (command === "G20" || command === "G21") { units = command === "G20" ? 25.4 : 1; explicitUnits = true; }
        else if (command === "G90" || command === "G91") {
            xyz = command === "G91" ? "relative" : "absolute";
            if (eMode && eMode !== xyz) { eMode = null; warn("G90/G91 may change E mode; waiting for M82/M83."); }
            if (!eMode && options.assumeAbsoluteE && xyz === "absolute") eMode = "absolute";
        } else if (command === "M82" || command === "M83") eMode = command === "M82" ? "absolute" : "relative";
        else if (command === "G92") {
            if ("E" in values) { e = values.E * units; }
            if ("X" in values || "Y" in values || "Z" in values) {
                pos = [null, null, null];
                "XYZ".split("").forEach((a, i) => { if (a in values) pos[i] = values[a] * units; });
                warn("XYZ coordinate reset: physical frame is unmodeled; no connecting segment drawn.");
            }
        } else if (["G28", "G161", "G162", "M132"].includes(command)) {
            pos = [null, null, null]; e = null; debt = 0; counts.unresolved++;
            warn("Homing/offset paths are NOT rendered; subsequent origins may be unknown.");
        } else if (command === "G0" || command === "G1") {
            const before = pos.slice(); let delta = null;
            if (!explicitUnits) warn("Millimetres ASSUMED before explicit G20/G21.");
            "XYZ".split("").forEach((a, i) => {
                if (a in values) pos[i] = xyz === "absolute" ? values[a] * units :
                    xyz === "relative" && pos[i] !== null ? pos[i] + values[a] * units : null;
                if (pos[i] !== null && Math.abs(pos[i]) > 100000) throw new Error("Coordinate exceeds preview numeric limit.");
            });
            let material = 0;
            if ("E" in values) {
                const target = values.E * units;
                delta = eMode === "relative" ? target : eMode === "absolute" && e !== null ? target - e : null;
                e = eMode === "absolute" ? target : eMode === "relative" && e !== null ? e + target : null;
                if (delta !== null) {
                    if (delta < 0) { debt -= delta; sawRetraction = true; }
                    else { const restore = Math.min(debt, delta); debt -= restore; material = delta - restore; }
                } else warn("Unresolved extrusion mode/origin: magenta paths have unknown material classification.");
            }
            if (!Object.keys(values).some(a => "XYZ".includes(a))) continue;
            if ([...before, ...pos].some(v => v === null)) { counts.unresolved++; continue; }
            if (pos.every((v, i) => Math.abs(v - before[i]) < 1e-7)) continue;
            if (count >= maxSegments) throw new Error("Preview exceeds 250,000 segments; no silently truncated preview is shown.");
            const kind = "E" in values && delta === null ? 2 : material > 1e-7 ? 0 : 1;
            const height = Math.max(before[2], pos[2]);
            positions.set([...before, ...pos], count * 6); kinds[count] = kind; heights[count] = height;
            counts[["extrusion", "travel", "unknown"][kind]]++;
            if (kind === 0) {
                layers.add(Math.round(height * 10000) / 10000);
                if (layers.size > 4096) throw new Error("More than 4096 deposition heights; nonplanar/complex paths unsupported.");
            }
            count++;
        } else if ((command.startsWith("G") && command !== "G4") || command.startsWith("T") ||
                   ["M200", "M206", "M218", "M221", "M600"].includes(command)) {
            counts.unsupported++; warn(`${command} is not modeled; affected paths omitted, modal state invalidated.`); invalidate();
        } else if (!["G4", "M104", "M109", "M140", "M190", "M106", "M107", "M6", "M651", "M652", "M907", "M108", "M17", "M18", "M73", "M118", "M84", "M400"].includes(command)) {
            counts.unsupported++; warn("Unrecognized commands: rendered paths may be incomplete or firmware-dependent."); invalidate();
        }
    }
    if (sawRetraction) warn("Retract/unretract is a simplified E-debt model, not physical deposited volume.");
    if (!count) throw new Error("No resolvable linear segments. Check file/modes; preview cannot infer missing coordinates.");
    return {positions: positions.slice(0, count * 6), kinds: kinds.slice(0, count), heights: heights.slice(0, count),
        layers: [...layers].sort((a, b) => a - b), counts, warnings, gxOffset: offset, lines: lineNo,
        limitations: "Linear command-coordinate preview only. Not real motion, collision checking, print approval or time simulation."};
}
if (typeof module !== "undefined") module.exports = {parseToolpath};
if (typeof self !== "undefined" && typeof self.postMessage === "function") {
    self.onmessage = event => {
        try {
            const result = parseToolpath(event.data.buffer, event.data.options);
            self.postMessage({result}, [result.positions.buffer, result.kinds.buffer, result.heights.buffer]);
        } catch (error) { self.postMessage({error: error.message}); }
    };
}
