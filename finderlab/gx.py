"""Experimental observed Finder GX envelope and deterministic CPU mesh thumbnail.

No network or G-code rewriting. Unknown constants are scoped to two local
ffslicer1.30.0 Finder samples, not a universal firmware specification.
"""
import hashlib
import json
import math
from pathlib import Path
import re
import struct

CODE_OFFSET = 14512
MAX_GX = 8 * 1024 * 1024
MAX_RASTER_WORK = 12000000
FIELDS = ('print_seconds','filament_mm','layer_microns','shells','speed_mm_s','bed_c','nozzle_c')


def normalize_metadata(value):
    if not isinstance(value,dict) or set(value) != set(FIELDS):
        raise ValueError('GX requires explicit print_seconds, filament_mm, layer_microns, shells, speed_mm_s, bed_c, nozzle_c')
    limits = dict(print_seconds=(1,0xffffffff),filament_mm=(1,0xffffffff),layer_microns=(1,1000),
                  shells=(1,100),speed_mm_s=(1,1000),bed_c=(0,150),nozzle_c=(1,350))
    for k,n in value.items():
        lo,hi=limits[k]
        if type(n) is not int or not lo <= n <= hi: raise ValueError('Invalid GX metadata: '+k)
    return dict(value)


def _scalar(profile,key):
    v=profile.get(key)
    if isinstance(v,list):
        if len(v)!=1: raise ValueError('GX metadata supports one filament/extruder only: '+key)
        v=v[0]
    if isinstance(v,bool): raise ValueError('Invalid profile numeric metadata')
    n=float(v)
    if not math.isfinite(n): raise ValueError('Nonfinite profile metadata')
    return n


def metadata_from_orca(data,process,filament):
    """Use exact output estimates and effective private profile snapshots only."""
    if len(data)>MAX_GX or b'\0' in data: raise ValueError('Expected bounded plain Orca output')
    lines=data.decode('utf-8').splitlines()
    times=[];lengths=[]
    for line in lines:
        if len(line)>4096: raise ValueError('GX metadata line limit exceeded')
        m=re.fullmatch(r'; estimated printing time \(normal mode\) = (.+)',line)
        if m:
            text=m[1];tokens=re.findall(r'(\d+)\s*([dhms])',text)
            if not tokens or re.sub(r'(\d+)\s*([dhms])','',text).strip(): raise ValueError('Unknown Orca time estimate syntax')
            units=[u for _,u in tokens]
            if len(set(units))!=len(units): raise ValueError('Duplicate Orca estimate units')
            times.append(sum(int(n)*{'d':86400,'h':3600,'m':60,'s':1}[u] for n,u in tokens))
        m=re.fullmatch(r'; (?:total filament length|filament used) \[mm\] = ([0-9]+(?:\.[0-9]+)?)',line)
        if m: lengths.append(float(m[1]))
    if len(times)!=1 or len(lengths)!=1: raise ValueError('GX needs one unambiguous Orca time and total filament length estimate; re-slice with a supported build')
    layer=_scalar(process,'layer_height')*1000
    shells=_scalar(process,'wall_loops')
    if abs(layer-round(layer))>1e-6 or abs(shells-round(shells))>1e-6: raise ValueError('GX header cannot exactly express layer height/shell count')
    bed=[];nozzle=[]
    for line in lines:
        if line.strip()==';LAYER_CHANGE':break
        command=line.partition(';')[0].strip()
        m=re.fullmatch(r'M140 S(\d+)(?: T0)?',command)
        if m:bed.append(int(m[1]))
        m=re.fullmatch(r'M104 S(\d+) T0',command)
        if m:nozzle.append(int(m[1]))
    if len(bed)!=1 or len(nozzle)!=1 or nozzle[0]!=round(_scalar(filament,'nozzle_temperature_initial_layer')):
        raise ValueError('GX needs unambiguous initial T0/bed targets matching the filament snapshot')
    return normalize_metadata(dict(print_seconds=times[0],filament_mm=math.ceil(lengths[0]),layer_microns=round(layer),shells=round(shells),
                                   speed_mm_s=round(_scalar(process,'sparse_infill_speed')),
                                   bed_c=bed[0],
                                   nozzle_c=round(_scalar(filament,'nozzle_temperature_initial_layer'))))


def render_bmp(vertices):
    """Orthographic isometric flat-shaded z-buffer, 2x supersampling, grayscale."""
    if not vertices or len(vertices)%3 or len(vertices)>600000: raise ValueError('Thumbnail needs 1–200000 triangles')
    if any(not math.isfinite(n) or abs(n)>100000 for v in vertices for n in v): raise ValueError('Invalid thumbnail coordinate')
    width,height=160,120
    # Orthonormal camera looking from +X,-Y,+Z. Depth increases toward camera.
    right=(2**-.5,2**-.5,0.);up=(-1/math.sqrt(6),1/math.sqrt(6),2/math.sqrt(6));eye=(1/math.sqrt(3),-1/math.sqrt(3),1/math.sqrt(3))
    def dot(a,b):return sum(x*y for x,y in zip(a,b))
    projected=[(dot(v,right),dot(v,up),dot(v,eye)) for v in vertices]
    lo=[min(v[a] for v in projected) for a in range(2)];hi=[max(v[a] for v in projected) for a in range(2)]
    extent=[hi[a]-lo[a] for a in range(2)]
    if max(extent)<1e-8:raise ValueError('No visible model extent')
    scale=min((width-16)/max(extent[0],1e-8),(height-16)/max(extent[1],1e-8))
    mid=[(lo[a]+hi[a])/2 for a in range(2)]
    points=[((v[0]-mid[0])*scale+width/2,height/2-(v[1]-mid[1])*scale,v[2]) for v in projected]
    pixels=bytearray(width*height);depth=[-math.inf]*(width*height);work=0;drawn=0
    for i in range(0,len(points),3):
        a,b,c=points[i:i+3]
        area=(b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])
        if abs(area)<1e-10:continue
        p,q,r=vertices[i:i+3];u=[q[j]-p[j] for j in range(3)];v=[r[j]-p[j] for j in range(3)]
        normal=(u[1]*v[2]-u[2]*v[1],u[2]*v[0]-u[0]*v[2],u[0]*v[1]-u[1]*v[0]);norm=math.hypot(*normal)
        if norm<1e-20:continue
        # Two-sided shading avoids pretending malformed winding is repaired.
        shade=round(65+175*abs(dot(normal,(-.25,-.45,.857)))/norm);shade=min(240,shade)
        xmin=max(0,math.floor(min(a[0],b[0],c[0])));xmax=min(width-1,math.ceil(max(a[0],b[0],c[0])))
        ymin=max(0,math.floor(min(a[1],b[1],c[1])));ymax=min(height-1,math.ceil(max(a[1],b[1],c[1])))
        work+=(xmax-xmin+1)*(ymax-ymin+1)
        if work>MAX_RASTER_WORK:raise ValueError('Thumbnail raster work limit exceeded; simplify mesh')
        for y in range(ymin,ymax+1):
            for x in range(xmin,xmax+1):
                px,py=x+.5,y+.5
                wb=((px-a[0])*(c[1]-a[1])-(py-a[1])*(c[0]-a[0]))/area
                wc=((b[0]-a[0])*(py-a[1])-(b[1]-a[1])*(px-a[0]))/area;wa=1-wb-wc
                if min(wa,wb,wc)<-1e-9:continue
                z=wa*a[2]+wb*b[2]+wc*c[2];index=y*width+x
                if z>depth[index]:depth[index]=z;pixels[index]=shade;drawn+=1
    if not drawn:raise ValueError('No visible nonzero-area triangles')
    # Observed BMP: 80x60, bottom-up24bit BGR, stride240, no color variance.
    image=bytearray()
    for y in range(59,-1,-1):
        for x in range(80):
            value=round(sum(pixels[(2*y+dy)*width+2*x+dx] for dy in (0,1) for dx in (0,1))/4)
            image.extend((value,value,value))
    return struct.pack('<2sIHHI',b'BM',14454,0,0,54)+struct.pack('<IiiHHIIiiII',40,80,60,1,24,0,14400,3780,3780,0,0)+image


def envelope(gcode,bmp,metadata):
    m=normalize_metadata(metadata)
    if not gcode or len(gcode)+CODE_OFFSET>MAX_GX or b'\0' in gcode or gcode.startswith((b'xgcode',b'GCDE')):
        raise ValueError('GX requires nonempty plain G-code and total size at most8MiB')
    gcode.decode('utf-8')
    if len(bmp)!=14454 or bmp[:2]!=b'BM':raise ValueError('Expected generated80x60 BMP')
    header=struct.pack('<12s7I9H',b'xgcode 1.0\n\0',0,58,CODE_OFFSET,CODE_OFFSET,
                       m['print_seconds'],m['filament_mm'],0,11,m['layer_microns'],0,m['shells'],m['speed_mm_s'],m['bed_c'],m['nozzle_c'],0,1)
    return header+bmp+gcode


def build_files(gcode,model,options,metadata,output,report):
    from finderlab.model_transform import read_stl,layout
    from finderlab.model_3mf import geometry_to_stl
    source=Path(model)
    if source.suffix.lower()=='.3mf':
        derived=Path(output).with_suffix('.mesh.stl');geometry_to_stl(source,derived);source=derived
    vertices=read_stl(source)
    t=options or dict(scale=1,rotate_x=0,rotate_y=0,rotate_z=0,x=0,y=0)
    # Bounds/fit check uses the same editor contract; renderer recentres its camera.
    vertices,bounds=layout(vertices,t)
    with Path(gcode).open('rb') as stream:code=stream.read(MAX_GX+1)
    bmp=render_bmp(vertices);data=envelope(code,bmp,metadata)
    info=dict(format='finder-ffslicer1.30-observed-experimental',size=len(data),sha256=hashlib.sha256(data).hexdigest(),
              gcode_sha256=hashlib.sha256(code).hexdigest(),bmp_sha256=hashlib.sha256(bmp).hexdigest(),
              code_offset=CODE_OFFSET,metadata=metadata,triangles=len(vertices)//3,thumbnail='CPU orthographic shaded source mesh,80x60 grayscale',
              bounds_mm=bounds,automatic_arrangement_not_reproduced=options is None,firmware_validated=False)
    with Path(output).open('xb') as stream:stream.write(data)
    Path(report).write_text(json.dumps(info))
    return info


if __name__=='__main__':
    import sys
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
    try:
        # Called as module by bounded wrapper; all paths are server-owned snapshots.
        code,model,params,destination,report=map(Path,sys.argv[1:])
        config=json.loads(params.read_bytes())
        build_files(code,model,config['transform'],config['metadata'],destination,report)
    except Exception as exc:
        print((str(exc) or type(exc).__name__)[:2000],file=sys.stderr);sys.exit(1)
