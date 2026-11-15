"""Bounded one-plate mesh assembly, never sequential object printing or transport."""
import hashlib
import json
from pathlib import Path
import struct
import sys
if __name__=='__main__':sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

from finderlab.model_transform import read_stl, layout, normalize_transform, require_finder_profile

MAX_MODELS = 8
MAX_TRIANGLES = 200000


def normalize_plate(value, ids):
    if not isinstance(value,list) or not 2 <= len(value) <= MAX_MODELS or len(value)!=len(ids):
        raise ValueError('Plate needs 2–8 models, each exactly once')
    result=[];seen=set()
    for item in value:
        if not isinstance(item,dict) or set(item)!={'id','transform'} or not isinstance(item['id'],str):
            raise ValueError('Plate entries require only id and transform')
        if item['id'] not in ids or item['id'] in seen:raise ValueError('Unknown/duplicate plate model')
        t=normalize_transform(item['transform'])
        if t is None:raise ValueError('Each plate model needs an explicit transform')
        seen.add(item['id']);result.append(dict(id=item['id'],transform=t))
    return result


def separated(bounds, gap=1.):
    # Deliberately conservative full-height XY AABBs; not a collision solver.
    return all(any(a[k][1]+gap <= b[k][0]+1e-6 or b[k][1]+gap <= a[k][0]+1e-6 for k in (0,1))
               for i,a in enumerate(bounds) for b in bounds[i+1:])


def assemble(entries, machine, output):
    require_finder_profile(machine)
    meshes=[];reports=[];count=0
    for entry in entries:
        source=Path(entry['path'])
        if source.stat().st_size>32*1024*1024:raise ValueError('Plate STL exceeds32MiB per model')
        raw_hash=hashlib.sha256(source.read_bytes()).hexdigest()
        if raw_hash!=entry['sha256']:raise ValueError('Plate source hash changed')
        vertices,bounds=layout(read_stl(source),entry['transform'])
        count+=len(vertices)//3
        if count>MAX_TRIANGLES:raise ValueError('Combined plate exceeds 200000 triangles')
        meshes.append(vertices);reports.append(dict(id=entry['id'],sha256=raw_hash,transform=entry['transform'],bounds_mm=bounds))
    if not separated([r['bounds_mm'] for r in reports]):raise ValueError('Models overlap or have less than 1 mm XY bounding-box gap; move them apart')
    # Normals are recalculated by Orca/thumbnail renderer. Positive uniform scale
    # and proper rotations preserve winding. No topology repair or union is claimed.
    digest=hashlib.sha256()
    with Path(output).open('xb') as stream:
        head=b'finderlab combined plate; not a safety approval'.ljust(80,b'\0')+struct.pack('<I',count)
        stream.write(head);digest.update(head)
        for vertices in meshes:
            for i in range(0,len(vertices),3):
                data=struct.pack('<12fH',0,0,0,*vertices[i],*vertices[i+1],*vertices[i+2],0)
                stream.write(data);digest.update(data)
    return dict(models=reports,triangles=count,size=84+count*50,sha256=digest.hexdigest(),arrange=0,orient=0,
                sequential_printing=False,safety_validated=False)


if __name__=='__main__':
    import sys
    try:
        config,machine,output,report=map(Path,sys.argv[1:])
        value=json.loads(config.read_bytes())
        normalize_plate([dict(id=e['id'],transform=e['transform']) for e in value],[e['id'] for e in value])
        info=assemble(value,json.loads(machine.read_bytes()),output)
        report.write_text(json.dumps(info))
    except Exception as exc:
        print((str(exc) or type(exc).__name__)[:2000],file=sys.stderr);sys.exit(1)
