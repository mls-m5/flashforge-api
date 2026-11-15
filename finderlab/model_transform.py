"""Typed one-model transforms. Geometry only; no native/printer transport."""
import hashlib
import math
import re
import struct
from pathlib import Path

MAX_BYTES = 32 * 1024 * 1024
MAX_TRIANGLES = 200000
DEFAULT = dict(scale=1., rotate_x=0., rotate_y=0., rotate_z=0., x=0., y=0.)


def normalize_transform(value):
    if value is None:
        return None
    if not isinstance(value, dict) or set(value) - DEFAULT.keys():
        raise ValueError("Transform accepts only scale, rotate_x/y/z and x/y")
    result = DEFAULT | value
    for key, number in result.items():
        low, high = (.01, 10) if key == "scale" else (-70, 70) if key in ("x", "y") else (-360, 360)
        if type(number) not in (int, float) or not low <= number <= high or not math.isfinite(number):
            raise ValueError(f"Transform {key} must be finite in [{low}, {high}]")
        result[key] = float(number)
    return result


def read_stl(path):
    with Path(path).open("rb") as stream:
        raw = stream.read(MAX_BYTES + 1)
    if not 0 < len(raw) <= MAX_BYTES:
        raise ValueError("Manual transform STL limit is 32 MiB")
    count = struct.unpack_from("<I", raw, 80)[0] if len(raw) >= 84 else -1
    if count >= 0 and 84 + count * 50 == len(raw):
        if not 0 < count <= MAX_TRIANGLES:
            raise ValueError("Manual transform requires 1–200000 triangles")
        vertices = [struct.unpack_from("<3f", raw, 84+i*50+12+j*12) for i in range(count) for j in range(3)]
    else:
        text = raw.decode("utf-8-sig")
        if not re.match(r"\s*solid(?:\s|$)", text, re.I) or "\0" in text:
            raise ValueError("Expected binary or ASCII STL")
        number = r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?"
        vertex = re.compile(rf"vertex\s+({number})\s+({number})\s+({number})\s*", re.I)
        vertices = []; active = False; n = 0; count = 0
        # Avoid allocating a list for all lines; input/line counts remain bounded.
        import io
        for line_number, raw_line in enumerate(io.StringIO(text), 1):
            line = raw_line.rstrip("\n")
            if len(line) > 4096 or line_number > 2000000:
                raise ValueError("STL line limit exceeded")
            line = line.strip()
            if not line: continue
            if re.match(r"facet\s+normal\s+", line, re.I):
                if active: raise ValueError("Nested STL facet")
                active = True; n = 0
            elif re.match(r"vertex\s", line, re.I):
                match = vertex.fullmatch(line)
                if not active or not match or n >= 3: raise ValueError("Malformed STL vertex/facet")
                vertices.append(tuple(float(x) for x in match.groups())); n += 1
                if len(vertices) > MAX_TRIANGLES * 3: raise ValueError("Too many STL triangles")
            elif line.lower() == "endfacet":
                if not active or n != 3: raise ValueError("Incomplete STL triangle")
                active = False; count += 1
            elif not re.fullmatch(r"solid(?:\s.*)?|endsolid(?:\s.*)?|outer\s+loop|endloop", line, re.I):
                raise ValueError("Unsupported ASCII STL syntax")
        if active or not count or len(vertices) != count * 3:
            raise ValueError("Incomplete/empty STL")
    for vertex in vertices:
        if any(not math.isfinite(n) or abs(n) > 100000 for n in vertex):
            raise ValueError("STL coordinate exceeds transform bounds")
    # Match browser Float32 source geometry, including for ASCII input.
    return [struct.unpack("<3f", struct.pack("<3f", *v)) for v in vertices]


def layout(vertices, transform):
    t = normalize_transform(transform)
    if t is None: raise ValueError("Explicit manual transform required")
    bounds = [[min(v[a] for v in vertices), max(v[a] for v in vertices)] for a in range(3)]
    center = [(a+b)/2 for a,b in bounds]
    x,y,z = [math.radians(t[k]) for k in ("rotate_x", "rotate_y", "rotate_z")]
    cx,sx,cy,sy,cz,sz = math.cos(x),math.sin(x),math.cos(y),math.sin(y),math.cos(z),math.sin(z)
    # Column vector, extrinsic X then Y then Z: Rz * Ry * Rx, uniform scale.
    r = [[cz*cy, cz*sy*sx-sz*cx, cz*sy*cx+sz*sx],
         [sz*cy, sz*sy*sx+cz*cx, sz*sy*cx-cz*sx], [-sy,cy*sx,cy*cx]]
    rotated = [tuple(sum(r[a][b]*(v[b]-center[b])*t["scale"] for b in range(3)) for a in range(3)) for v in vertices]
    box = [[min(v[a] for v in rotated),max(v[a] for v in rotated)] for a in range(3)]
    offset = [t["x"]-sum(box[0])/2,t["y"]-sum(box[1])/2,-box[2][0]]
    placed = [tuple(v[a]+offset[a] for a in range(3)) for v in rotated]
    result_bounds = [[box[a][0]+offset[a],box[a][1]+offset[a]] for a in range(3)]
    if any(result_bounds[a][0] < -70-1e-5 or result_bounds[a][1] > 70+1e-5 for a in (0,1)) or result_bounds[2][1] > 140+1e-5:
        raise ValueError("Transformed mesh exceeds nominal centered 140 mm plate/height; reduce scale or move inward")
    return placed, result_bounds


def require_finder_profile(machine):
    """Nominal profile match only, not a physical clearance assertion."""
    points = machine.get("printable_area", [])
    try:
        polygon = [tuple(float(x) for x in p.split("x")) for p in points]
        if len(polygon) == 5 and polygon[0] == polygon[-1]: polygon.pop()
        area = set(polygon)
        compatible = len(polygon) == 4 and area == {(-70.,-70.),(70.,-70.),(70.,70.),(-70.,70.)}
        if compatible:
            twice_area = sum(polygon[i][0]*polygon[(i+1)%4][1]-polygon[(i+1)%4][0]*polygon[i][1] for i in range(4))
            compatible = abs(twice_area) == 39200 and float(machine["printable_height"]) == 140
    except (AttributeError, TypeError, ValueError, KeyError): compatible = False
    if not compatible: raise ValueError("This operation requires a nominal centered 140×140×140 machine profile")


def write_transformed(source, destination, transform, machine):
    require_finder_profile(machine)
    vertices, bounds = layout(read_stl(source), transform)
    digest = hashlib.sha256()
    with Path(destination).open("xb") as output:
        header = b"finderlab manual geometry; no print safety approval".ljust(80,b"\0") + struct.pack("<I",len(vertices)//3)
        output.write(header);digest.update(header)
        for i in range(0,len(vertices),3):
            a,b,c = vertices[i:i+3];u=[b[j]-a[j] for j in range(3)];v=[c[j]-a[j] for j in range(3)]
            normal = [u[1]*v[2]-u[2]*v[1],u[2]*v[0]-u[0]*v[2],u[0]*v[1]-u[1]*v[0]]
            length = math.hypot(*normal);normal = [n/length for n in normal] if length else [0.,0.,0.]
            block = struct.pack("<12fH",*normal,*a,*b,*c,0);output.write(block);digest.update(block)
    return {"transform":normalize_transform(transform),"bounds_mm":bounds,"sha256":digest.hexdigest(),
            "size":84+len(vertices)//3*50,"triangles":len(vertices)//3,"arrange":0,"orient":0,
            "note":"Nominal mesh bounds only; start/purge/brim/compensation/head clearance are not validated."}


if __name__ == "__main__":
    import json
    import sys
    try:
        source, destination, options, machine, report = map(Path, sys.argv[1:])
        result = write_transformed(source, destination, json.loads(options.read_bytes()), json.loads(machine.read_bytes()))
        report.write_text(json.dumps(result))
    except Exception as exc:
        print((str(exc) or type(exc).__name__)[:2000], file=sys.stderr)
        sys.exit(1)
