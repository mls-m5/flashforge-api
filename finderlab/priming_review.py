"""Bounded offline XY centreline diagnostics for tagged, linear Orca first layers.

Not collision/firmware/material validation. Never rewrites files or calls printers.
"""
import math
import hashlib
from pathlib import Path
import re

LIMIT = 8 * 1024 * 1024
MAX_PAIRS = 2000000
WORD = re.compile(r"([XYZEF])([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)")


def _fields(words):
    result = {}
    for word in words:
        match = WORD.fullmatch(word)
        if not match or match[1] in result: raise ValueError("Unsupported/duplicate linear field")
        n = float(match[2])
        if not math.isfinite(n) or abs(n) > 1000000: raise ValueError("Unbounded/nonfinite linear field")
        result[match[1]] = n
    return result


def _read(path):
    with Path(path).open('rb') as source: raw = source.read(LIMIT+1)
    if not 0 < len(raw) <= LIMIT or b'\0' in raw: raise ValueError('Expected bounded plain G-code, at most 8 MiB')
    return raw


def segments(path):
    return _segments(_read(path))


def _segments(raw):
    text = raw.decode('utf-8'); groups = {k:[] for k in ('startup','skirt','brim','object')}
    position = dict.fromkeys('XYZ'); absolute = emode = None; e = None; debt = 0.
    layer = 0; feature = None; first = None; prefix_mm = False; units = None; frame_break = False
    import io
    for i,line in enumerate(io.StringIO(text),1):
        if len(line.rstrip('\n')) > 4096 or i > 500000: raise ValueError('G-code line limit exceeded')
        stripped = line.strip()
        if stripped == ';LAYER_CHANGE':
            layer += 1
            if layer > 1: break
            feature = None
        if stripped.startswith(';TYPE:'): feature = stripped[6:].strip().lower()
        code = line.partition(';')[0].strip().split()
        if not code: continue
        command = code[0].upper()
        if command in ('G90','G91'): absolute = command == 'G90'
        elif command in ('M82','M83'): emode = command == 'M82'
        elif command == 'G21': units = 'mm'
        elif command == 'G20': raise ValueError('Inch-mode priming review is unsupported')
        elif command in ('G28','G161','G162','M132'):
            if any(groups.values()): frame_break = True
            position = dict.fromkeys('XYZ')  # Unknown physical homing/offset effects, never interpolate them.
        elif command == 'G92':
            fields = _fields(code[1:])
            if any(a in fields for a in 'XYZ'): raise ValueError('XYZ coordinate resets unsupported in priming review')
            if 'E' in fields: e = fields['E']  # Retract debt survives coordinate reset.
        elif command in ('G0','G1'):
            fields = _fields(code[1:]); before = position.copy()
            if absolute is None: raise ValueError('Unknown XYZ mode')
            if units is None and any(a in fields for a in 'XYZE'): prefix_mm = True
            for a in 'XYZ':
                if a in fields: position[a] = fields[a] if absolute else (None if before[a] is None else before[a]+fields[a])
            deposition = 0.
            if 'E' in fields:
                if emode is None or (emode and e is None): raise ValueError('Unknown E origin/mode')
                delta = fields['E']-e if emode else fields['E'];e = fields['E'] if emode else (None if e is None else e+delta)
                if delta < 0: debt -= delta
                else:
                    restored = min(debt,delta);debt -= restored;deposition = delta-restored
            if deposition > 1e-8 and any(a in fields for a in 'XY'):
                if frame_break: raise ValueError('Cannot compare deposition across unmodeled homing/offset frames')
                if any(before[a] is None or position[a] is None for a in 'XYZ'): raise ValueError('Unknown extrusion endpoint')
                if abs(before['Z']-position['Z']) > 1e-5: raise ValueError('Mixed-Z deposition unsupported')
                a = (before['X'],before['Y']);b = (position['X'],position['Y'])
                if a == b: continue
                if sum(map(abs,a+b)) > 400000: raise ValueError('Resolved coordinate bound exceeded')
                if layer and not feature: raise ValueError('Missing first-layer TYPE tag')
                group = 'startup' if not layer or feature == 'custom' else feature if feature in ('skirt','brim') else 'object'
                if layer and first is None: first = feature
                groups[group].append((a,b))
                if sum(map(len,groups.values())) > 100000: raise ValueError('Priming segment limit exceeded')
        elif command.startswith('G') and command not in ('G4',):
            raise ValueError('Unsupported motion/frame command: '+command)
    if not layer or not groups['object']: raise ValueError('No tagged first-layer object paths')
    return groups,first,prefix_mm


def _distance(a,b,c,d):
    def cross(p,q,r): return (q[0]-p[0])*(r[1]-p[1])-(q[1]-p[1])*(r[0]-p[0])
    def point(p,q,r):
        dx,dy=r[0]-q[0],r[1]-q[1];den=dx*dx+dy*dy
        t=max(0.,min(1.,((p[0]-q[0])*dx+(p[1]-q[1])*dy)/den)) if den else 0.
        return (p[0]-q[0]-t*dx)**2+(p[1]-q[1]-t*dy)**2
    bbox = all(max(min(a[i],b[i]),min(c[i],d[i])) <= min(max(a[i],b[i]),max(c[i],d[i]))+1e-9 for i in (0,1))
    if bbox and cross(a,b,c)*cross(a,b,d) <= 0 and cross(c,d,a)*cross(c,d,b) <= 0: return 0.
    return math.sqrt(min(point(a,c,d),point(b,c,d),point(c,a,b),point(d,a,b)))


def review_priming(path, *, max_pairs=MAX_PAIRS):
    raw = _read(path)
    groups,first,prefix_mm = _segments(raw);pairs = 0
    def compare(left,right):
        nonlocal pairs
        count = 0;distance = math.inf
        if pairs+len(groups[left])*len(groups[right]) > max_pairs: raise ValueError('Priming pair-comparison limit exceeded; no complete report')
        for a,b in groups[left]:
            for c,d in groups[right]:
                pairs += 1;gap = _distance(a,b,c,d);distance = min(distance,gap)
                if gap <= 1e-8: count += 1
        return {'xy_intersections':count,'min_centerline_gap_mm':None if math.isinf(distance) else round(distance,6)}
    bounds = {kind:None if not lines else [[min(p[a] for line in lines for p in line),max(p[a] for line in lines for p in line)] for a in (0,1)] for kind,lines in groups.items()}
    return {'sha256':hashlib.sha256(raw).hexdigest(),'first_layer_first_feature':first,'deposition_xy_bounds_mm':bounds,'segments':{k:len(v) for k,v in groups.items()},
            'startup_vs_object':compare('startup','object'),'startup_vs_brim':compare('startup','brim'),
            'skirt_vs_object':compare('skirt','object'),'skirt_vs_brim':compare('skirt','brim'),
            'brim_vs_object':compare('brim','object'),
            'comparisons':pairs,'prefix_mm_assumption':prefix_mm,
            'safety_validated':False,'note':'Nominal XY centrelines only, even across different Z. No bead width/thermal/homing/clearance validation.'}


def candidate_issues(report):
    """Conservative offline candidate guard, NOT a general print safety validator."""
    issues = []
    if report['first_layer_first_feature'] != 'skirt' or not report['segments']['skirt']:
        issues.append('Native skirt must be the first tagged deposition feature')
    if report['segments']['startup']:
        issues.append('Custom startup XY extrusion remains')
    for key in ('skirt_vs_object','skirt_vs_brim'):
        item = report[key];gap = item['min_centerline_gap_mm']
        if item['xy_intersections'] or (gap is not None and gap < 1.): issues.append(key+': nominal paths cross or are too close')
    if report['brim_vs_object']['xy_intersections']:
        issues.append('brim_vs_object: nominal centrelines cross (bead contact is not modeled)')
    for kind,bounds in report['deposition_xy_bounds_mm'].items():
        if bounds and any(lo < -69-1e-5 or hi > 69+1e-5 for lo,hi in bounds):
            issues.append(kind+': first-layer extrusion exceeds nominal +/-69 mm review margin')
    return issues


if __name__ == '__main__':
    # Internal bounded slicer helper; reports diagnostics even when guard rejects.
    import json
    import sys
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
    from finderlab.model_transform import require_finder_profile
    try:
        source, machine, destination = map(Path,sys.argv[1:])
        require_finder_profile(json.loads(machine.read_bytes()))
        report = review_priming(source)
        report['candidate_issues'] = candidate_issues(report)
        destination.write_text(json.dumps(report))
    except Exception as exc:
        print((str(exc) or type(exc).__name__)[:2000],file=sys.stderr);sys.exit(1)
