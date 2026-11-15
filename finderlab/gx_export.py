"""Bounded offline GX packaging orchestration. Never imports printer transport."""
from dataclasses import dataclass, replace
import hashlib
import json
from pathlib import Path
import sys
import tempfile

from .gx import MAX_GX, normalize_metadata
from .slicer import ROOT, _copy_bounded, _run, SliceError


@dataclass(frozen=True)
class GXLimits:
    timeout: float = 30
    memory_mib: int = 512
    max_model_size: int = 64 * 1024 * 1024
    max_work_bytes: int = 128 * 1024 * 1024
    max_log_bytes: int = 64 * 1024


async def export_gx(code,model,output,config,*,capture,metadata,transform=None,expected_gcode_sha256=None,expected_model_sha256=None):
    from .model_transform import normalize_transform
    metadata=normalize_metadata(metadata);transform=normalize_transform(transform)
    code,model,output=map(Path,(code,model,output))
    if code.suffix.lower() not in ('.gcode','.g') or model.suffix.lower() not in ('.stl','.3mf'):
        raise ValueError('GX export needs plain G-code and an explicit STL/geometry-only3MF model')
    if output.suffix.lower()!='.gx' or output.exists() or output.is_symlink():raise ValueError('GX output must be a new .gx file')
    scratch=ROOT/'.tmp';scratch.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(dir=scratch,prefix='gx-') as directory:
        work=Path(directory)
        for name in ('tmp','data','cache','config'): (work/name).mkdir()
        src=work/('source'+model.suffix.lower());gcode=work/'source.gcode'
        inputs={'model':_copy_bounded(model,src,config.max_model_size),'gcode':_copy_bounded(code,gcode,MAX_GX-14512)}
        if expected_model_sha256 is not None and inputs['model']['sha256'] != expected_model_sha256:
            raise ValueError('Model changed before thumbnail rendering; GX not published')
        if expected_gcode_sha256 is not None and inputs['gcode']['sha256'] != expected_gcode_sha256:
            raise ValueError('G-code changed before packaging; GX not published')
        capture.manifest['metadata'].update(gx_inputs=inputs,gx_requested_metadata=metadata,gx_transform=transform)
        params=work/'params.json';params.write_text(json.dumps(dict(metadata=metadata,transform=transform)))
        await _run(sys.executable,[Path(__file__).with_name('gx.py'),gcode,src,params,work/'result.gx',work/'result.json'],
                   work,replace(config,memory_mib=min(512,config.memory_mib)),capture,stage='gx_export',timeout=min(30,config.timeout))
        report=work/'result.json';result=work/'result.gx'
        if not report.is_file() or not 0<report.stat().st_size<=65536:raise SliceError('Missing/oversized GX report')
        info=json.loads(report.read_bytes())
        with result.open('rb') as source:data=source.read(MAX_GX+1)
        if len(data)>MAX_GX or info['sha256']!=hashlib.sha256(data).hexdigest() or data[14512:]!=gcode.read_bytes():
            raise SliceError('GX export identity/body mismatch')
        capture.event('gx_result',**info)
        capture.manifest['metadata']['gx_result']=info
        # Finalize before publication: caller's lifecycle can close idempotently.
        # If recording fails there is no new selected/output file.
        capture.close()
        if capture.failed:raise SliceError('GX recording incomplete; output not published')
        stream=output.open('xb')
        try:
            with stream:stream.write(data)
        except BaseException:
            output.unlink(missing_ok=True);raise
        return info
