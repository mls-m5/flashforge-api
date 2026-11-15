"""Bounded geometry-only 3MF mesh import. No archive extraction or preset loading.

Narrow core subset: mesh objects, build items, affine transforms and units.
Components, external model references and required extensions fail explicitly.
"""

import hashlib
import math
from pathlib import PurePosixPath
import struct
import xml.etree.ElementTree as ET
from zipfile import ZipFile, BadZipFile, ZIP_STORED, ZIP_DEFLATED

CORE = "{http://schemas.microsoft.com/3dmanufacturing/core/2015/02}"
REL = "{http://schemas.openxmlformats.org/package/2006/relationships}"
MAX_XML = 16 * 1024 * 1024
MAX_TRIANGLES = 200000


def xml(data):
    if b"\0" in data or b"<!DOCTYPE" in data.upper() or b"<!ENTITY" in data.upper():
        raise ValueError("3MF XML must be UTF-8 without DTD/entities")
    return ET.fromstring(data.decode("utf-8-sig"))


def safe_name(name):
    parts = PurePosixPath(name).parts
    if not name or "\\" in name or name.startswith("/") or any(p in ("..", ".") for p in parts) or ":" in name:
        raise ValueError("Unsafe/unsupported 3MF archive path")
    return name


def number(value):
    result = float(value)
    if not math.isfinite(result) or abs(result) > 1000000:
        raise ValueError("3MF numeric value outside import limits")
    return result


def geometry_to_stl(source, destination, *, max_output=64 * 1024 * 1024):
    """Convert an already bounded input snapshot, never passing the 3MF to Orca."""
    try:
        return _convert(source, destination, max_output)
    except (BadZipFile, ET.ParseError, KeyError, TypeError, OverflowError, UnicodeError, struct.error) as exc:
        raise ValueError("Invalid/unsupported geometry-only 3MF: " + str(exc)) from exc


def _convert(source, destination, max_output):
    # Bound central-directory allocation before ZipFile constructs its entry objects.
    with source.open("rb") as reader:
        reader.seek(0, 2); size = reader.tell(); reader.seek(max(0, size - 65557))
        tail = reader.read(65557)
    end = tail.rfind(b"PK\x05\x06")
    if end < 0 or len(tail) - end < 22:
        raise ValueError("Missing 3MF ZIP directory")
    _, disk, directory_disk, disk_entries, total_entries, directory_size, directory_offset, comment_size = struct.unpack_from("<4s4H2IH", tail, end)
    if (disk or directory_disk or disk_entries != total_entries or total_entries > 256 or
            directory_size > 1024 * 1024 or directory_offset + directory_size > size or
            end + 22 + comment_size != len(tail)):
        raise ValueError("3MF ZIP directory limits exceeded; split/ZIP64 packages unsupported")
    with ZipFile(source) as archive:
        infos = archive.infolist()
        if len(infos) > 256 or sum(i.file_size for i in infos) > 64 * 1024 * 1024:
            raise ValueError("3MF archive exceeds entry/uncompressed size limits")
        names = set()
        for info in infos:
            safe_name(info.filename)
            if (info.filename in names or info.flag_bits & 1 or
                    info.compress_type not in (ZIP_STORED, ZIP_DEFLATED) or
                    (info.external_attr >> 16) & 0o170000 == 0o120000):
                raise ValueError("Duplicate/encrypted/symlink 3MF entries unsupported")
            names.add(info.filename)
        def read(name):
            info = archive.getinfo(name)
            if info.file_size > MAX_XML:
                raise ValueError("3MF XML part exceeds 16 MiB")
            with archive.open(info) as stream:
                data = stream.read(MAX_XML + 1)
            if len(data) > MAX_XML or len(data) != info.file_size:
                raise ValueError("3MF XML size mismatch/limit")
            return data
        relations = xml(read("_rels/.rels"))
        if relations.tag != REL + "Relationships":
            raise ValueError("Unsupported 3MF package relationships")
        models = [r for r in relations if r.get("Type", "").endswith("/3dmodel")]
        if len(models) != 1 or models[0].get("TargetMode", "Internal") != "Internal":
            raise ValueError("3MF needs one internal root model")
        model_name = safe_name(models[0].get("Target", "").lstrip("/"))
        model_bytes = read(model_name)
        root = xml(model_bytes)
    if root.tag != CORE + "model" or root.get("requiredextensions", "").strip():
        raise ValueError("3MF required extensions/unknown model namespace unsupported")
    scale = {"micron": .001, "millimeter": 1, "centimeter": 10, "inch": 25.4, "foot": 304.8, "meter": 1000}.get(root.get("unit", "millimeter"))
    if scale is None:
        raise ValueError("Unknown 3MF unit")
    resources = root.find(CORE + "resources"); build = root.find(CORE + "build")
    if resources is None or build is None:
        raise ValueError("3MF resources/build missing")
    objects = {}
    vertex_count = triangle_count = 0
    for obj in resources:
        if obj.tag != CORE + "object":
            # Materials can be present, but only mesh geometry is imported.
            continue
        ident = obj.get("id")
        if not ident or ident in objects or obj.get("type", "model") != "model":
            raise ValueError("Duplicate/unsupported 3MF object")
        mesh = obj.find(CORE + "mesh")
        if mesh is None or obj.find(CORE + "components") is not None:
            raise ValueError("3MF components/external objects unsupported; export mesh-only 3MF or STL")
        if any(child.tag not in (CORE + "vertices", CORE + "triangles") for child in mesh):
            raise ValueError("Extended 3MF mesh geometry unsupported")
        vertices = mesh.find(CORE + "vertices"); triangles = mesh.find(CORE + "triangles")
        if vertices is None or triangles is None or not len(vertices) or not len(triangles):
            raise ValueError("Empty/missing 3MF mesh")
        vertex_count += len(vertices); triangle_count += len(triangles)
        if vertex_count > 300000 or triangle_count > MAX_TRIANGLES:
            raise ValueError("3MF mesh exceeds vertex/triangle limits")
        points = []
        for v in vertices:
            if v.tag != CORE + "vertex": raise ValueError("Unsupported 3MF vertex")
            points.append(tuple(number(v.attrib[a]) for a in "xyz"))
        faces = []
        for face in triangles:
            if face.tag != CORE + "triangle": raise ValueError("Unsupported 3MF triangle")
            indices = tuple(int(face.attrib[a]) for a in ("v1", "v2", "v3"))
            if min(indices) < 0 or max(indices) >= len(points):
                raise ValueError("Invalid 3MF triangle indices")
            faces.append(indices)
        objects[ident] = (points, faces)
    if len(build) > 256: raise ValueError("3MF build item limit exceeded")
    expanded = 0
    for item in build:
        if item.get("printable", "1") != "0" and item.get("objectid") in objects:
            expanded += len(objects[item.get("objectid")][1])
    if expanded > MAX_TRIANGLES:
        raise ValueError("Instanced 3MF exceeds expanded triangle limit")
    count = skipped = 0; bounds = [[math.inf, -math.inf] for _ in range(3)]
    digest = hashlib.sha256()
    # Local scratch only. A failed conversion is never published or passed to Orca.
    with destination.open("xb") as writer:
        writer.write(b"Finderlab geometry-only 3MF derivative".ljust(80, b"\0") + struct.pack("<I", 0))
        for item in build:
            if item.tag != CORE + "item" or any(k.startswith("{") for k in item.attrib):
                raise ValueError("Unsupported 3MF build item/external reference")
            if item.get("printable", "1") not in ("0", "1"):
                raise ValueError("Invalid 3MF printable flag")
            if item.get("printable") == "0": continue
            if item.get("objectid") not in objects: raise ValueError("Missing 3MF build object")
            matrix = [number(x) for x in item.get("transform", "1 0 0 0 1 0 0 0 1 0 0 0").split()]
            if len(matrix) != 12: raise ValueError("3MF transform must have 12 numbers")
            m = matrix
            determinant = m[0]*(m[4]*m[8]-m[5]*m[7])-m[3]*(m[1]*m[8]-m[2]*m[7])+m[6]*(m[1]*m[5]-m[2]*m[4])
            if abs(determinant) < 1e-12: raise ValueError("Singular 3MF build transform")
            points, faces = objects[item.get("objectid")]
            transformed = []
            for x,y,z in points:
                p = tuple((x*m[a]+y*m[3+a]+z*m[6+a]+m[9+a])*scale for a in range(3))
                if any(not math.isfinite(v) or abs(v) > 100000 for v in p):
                    raise ValueError("Transformed 3MF coordinates exceed limits")
                transformed.append(p)
            for indices in faces:
                a,b,c = (transformed[i] for i in indices)
                if determinant < 0: b,c = c,b
                ab = [b[i]-a[i] for i in range(3)]; ac = [c[i]-a[i] for i in range(3)]
                n = (ab[1]*ac[2]-ab[2]*ac[1],ab[2]*ac[0]-ab[0]*ac[2],ab[0]*ac[1]-ab[1]*ac[0])
                length = math.sqrt(sum(v*v for v in n))
                if length == 0:
                    skipped += 1
                    continue  # Zero-area facets carry no printable surface; report explicitly.
                count += 1
                if count > MAX_TRIANGLES or 84 + count*50 > max_output:
                    raise ValueError("Flattened 3MF exceeds triangle/output limit")
                writer.write(struct.pack("<12fH", *(v/length for v in n), *a,*b,*c,0))
                for p in (a,b,c):
                    for i,v in enumerate(p): bounds[i] = [min(bounds[i][0],v),max(bounds[i][1],v)]
        if count == 0: raise ValueError("3MF has no printable mesh triangles")
        writer.seek(80); writer.write(struct.pack("<I",count))
    with destination.open("rb") as reader:
        while data := reader.read(65536): digest.update(data)
    return {"source_model_part": model_name, "triangles": count, "zero_area_facets_skipped": skipped, "bounds_mm": dict(zip("XYZ",bounds)),
            "size": 84+count*50, "sha256": digest.hexdigest(), "embedded_settings_loaded": False,
            "note": "Geometry-only flattened STL; project presets/modifiers/material assignments are not imported. Orca arranges/ensures on bed as before."}
