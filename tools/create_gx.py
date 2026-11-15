#!/usr/bin/env python3
"""Experimental offline GX + CPU 3D thumbnail. Never uploads or starts prints."""
import argparse
import asyncio
import json
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from finderlab.capture import Capture
from finderlab.gx_export import GXLimits,export_gx


def bounded_json(path):
    with path.open('rb') as source:raw=source.read(65537)
    if len(raw)>65536:raise ValueError('JSON options exceed64KiB')
    return json.loads(raw)


async def run(args):
    capture=Capture(args.capture_dir,'gx',max_bytes=1024*1024,metadata={'operation':'gx','interface':'offline-tool','start_requested':False})
    print('Capture: '+str(capture.path),flush=True)
    try:
        result=await export_gx(args.gcode,args.model,args.output,GXLimits(),capture=capture,
                               metadata=bounded_json(args.metadata),transform=bounded_json(args.transform) if args.transform else None)
        print(json.dumps(result,indent=2))
    except BaseException as exc:
        if not capture.closed and not capture.failed:capture.event('error',phase='gx',message=str(exc))
        raise
    finally:capture.close()


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('gcode',type=Path)
    parser.add_argument('--model',type=Path,required=True,help='STL or supported geometry-only3MF used for thumbnail')
    parser.add_argument('--metadata',type=Path,required=True,help='explicit typed header metadata JSON; see docs/GX_GENERATION.md')
    parser.add_argument('--transform',type=Path,help='optional typed manual model transform JSON')
    parser.add_argument('--output',type=Path,required=True,help='new .gx path, never overwritten')
    parser.add_argument('--capture-dir',type=Path,default=Path('captures/gx'))
    args=parser.parse_args()
    try:asyncio.run(run(args))
    except (ValueError,OSError,TimeoutError) as exc:parser.exit(1,'GX export failed: '+str(exc)+'\n')
