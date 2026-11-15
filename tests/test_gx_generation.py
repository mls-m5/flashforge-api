"""Generated geometry/headers only. No proprietary fixtures or hardware."""
import asyncio
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import struct
import unittest
from unittest.mock import patch

from finderlab.capture import Capture
from finderlab.gx import CODE_OFFSET,envelope,render_bmp,metadata_from_orca,build_files,normalize_metadata
from finderlab.gx_export import GXLimits,export_gx
from finderlab.model_transform import read_stl,layout
from tools.extract_gx_preview import decode_preview
from helpers import workspace_tempdir
from test_model_transform import ASCII

META=dict(print_seconds=125,filament_mm=124,layer_microns=180,shells=2,speed_mm_s=60,bed_c=0,nozzle_c=220)
CODE=b'M140 S0 T0\nM104 S220 T0\n;LAYER_CHANGE\nG90\n; ~M29 ok\n; filament used [mm] = 123.4\n; estimated printing time (normal mode) = 2m 5s\n'
PROCESS=dict(layer_height='0.18',wall_loops='2',sparse_infill_speed='60')
FILAMENT=dict(nozzle_temperature_initial_layer=['220'])

class GXGenerationTests(unittest.TestCase):
    def setUp(self):
        self.temp=workspace_tempdir();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        self.model=self.root/'model.stl';self.model.write_bytes(ASCII)
        self.vertices=read_stl(self.model)

    def test_header_offsets_values_and_body_are_exact(self):
        bmp=render_bmp(self.vertices);gx=envelope(CODE,bmp,META)
        self.assertEqual(len(gx),14512+len(CODE))
        self.assertEqual(struct.unpack('<12s7I9H',gx[:58]),
            (b'xgcode 1.0\n\0',0,58,14512,14512,125,124,0,11,180,0,2,60,0,220,0,1))
        self.assertEqual(gx[14512:],CODE)
        info,got,ppm=decode_preview(gx)
        self.assertEqual(got,bmp);self.assertEqual((info['width'],info['height']),(80,60))
        rgb=ppm.split(b'\n',3)[3];self.assertTrue(any(rgb));self.assertTrue(any(v==0 for v in rgb))
        for i in range(0,len(rgb),3):self.assertEqual(rgb[i:i+1]*3,rgb[i:i+3])

    def test_renderer_is_deterministic_translation_invariant_rotation_changes_image(self):
        bmp=render_bmp(self.vertices)
        self.assertEqual(bmp,render_bmp(self.vertices))
        self.assertEqual(bmp,render_bmp([tuple(n+100 for n in p) for p in self.vertices]))
        rotated,_=layout(self.vertices,{'rotate_x':90,'scale':1})
        self.assertNotEqual(bmp,render_bmp(rotated))
        # Z-buffer output cannot depend on triangle submission order.
        mesh=self.vertices+[(x+1,y-2,z+3) for x,y,z in self.vertices]
        self.assertEqual(render_bmp(mesh),render_bmp(mesh[3:]+mesh[:3]))

    def test_invalid_metadata_geometry_and_size_fail(self):
        for m in (META|{'print_seconds':True},META|{'filament_mm':0},META|{'unknown':0},META|{'nozzle_c':351}):
            with self.assertRaises(ValueError):normalize_metadata(m)
        for v in ([],[(0,0,0)]*3,[(float('nan'),1,1)]*3):
            with self.assertRaises(ValueError):render_bmp(v)
        with patch('finderlab.gx.MAX_RASTER_WORK',1),self.assertRaisesRegex(ValueError,'work limit'):
            render_bmp(self.vertices)
        bmp=render_bmp(self.vertices)
        for code in (b'',b'bad\0code',b'xgcode old',b'a'*(8*1024*1024)):
            with self.assertRaises(ValueError):envelope(code,bmp,META)

    def test_exact_output_estimates_effective_metadata_no_generic_defaults(self):
        self.assertEqual(metadata_from_orca(CODE,PROCESS,FILAMENT),META)
        for data in (CODE.replace(b'2m 5s',b'2m invalid'),CODE+ b'; filament used [mm] = 4\n',CODE.replace(b'123.4',b'1,2'),CODE.replace(b'M104 S220',b'M104 S230')):
            with self.assertRaises(ValueError):metadata_from_orca(data,PROCESS,FILAMENT)
        with self.assertRaises((ValueError,TypeError)):metadata_from_orca(CODE,PROCESS|{'wall_loops':'1.5'},FILAMENT)

    def test_build_preserves_source_and_never_overwrites(self):
        source=self.root/'source.gcode';source.write_bytes(CODE);output=self.root/'new.gx';report=self.root/'report.json'
        result=build_files(source,self.model,{},META,output,report)
        self.assertEqual(output.read_bytes()[CODE_OFFSET:],CODE);self.assertEqual(self.model.read_bytes(),ASCII)
        self.assertEqual(result['sha256'],hashlib.sha256(output.read_bytes()).hexdigest())
        self.assertFalse(result['firmware_validated'])
        with self.assertRaises(FileExistsError):build_files(source,self.model,{},META,output,report)

class GXExportTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp=workspace_tempdir();self.root=Path(self.temp.name)
        self.source=self.root/'source.gcode';self.source.write_bytes(CODE)
        self.model=self.root/'model.stl';self.model.write_bytes(ASCII)
        self.output=self.root/'new.gx';self.capture=Capture(self.root/'captures','gx',max_bytes=1024*1024)

    async def asyncTearDown(self):self.capture.close();self.temp.cleanup()

    async def test_bounded_worker_roundtrip_and_finalized_evidence(self):
        result=await export_gx(self.source,self.model,self.output,GXLimits(),capture=self.capture,metadata=META,transform={'rotate_z':30})
        self.assertEqual(self.output.read_bytes()[14512:],CODE)
        self.assertEqual(result['gcode_sha256'],hashlib.sha256(CODE).hexdigest())
        self.assertTrue(self.capture.closed);self.assertTrue(self.capture.manifest['complete'])
        self.assertEqual(self.capture.manifest['sessions'],[])
        command=self.capture.manifest['metadata']['gx_inputs']
        self.assertEqual(command['model']['sha256'],hashlib.sha256(ASCII).hexdigest())

    async def test_recording_or_identity_failure_never_publishes(self):
        with self.assertRaisesRegex(ValueError,'G-code changed'):
            await export_gx(self.source,self.model,self.output,GXLimits(),capture=self.capture,metadata=META,expected_gcode_sha256='old')
        with self.assertRaisesRegex(ValueError,'Model changed'):
            await export_gx(self.source,self.model,self.output,GXLimits(),capture=self.capture,metadata=META,expected_model_sha256='old')
        self.assertFalse(self.output.exists())
        original=self.capture.close
        def fail():original();raise OSError('finalization failed')
        with patch.object(self.capture,'close',fail),self.assertRaises(OSError):
            await export_gx(self.source,self.model,self.output,GXLimits(),capture=self.capture,metadata=META)
        self.assertFalse(self.output.exists())

    async def test_worker_error_or_timeout_cleans_scratch_no_output(self):
        self.model.write_bytes(b'not STL')
        with self.assertRaises(ValueError):
            await export_gx(self.source,self.model,self.output,GXLimits(),capture=self.capture,metadata=META)
        self.assertFalse(self.output.exists())
        self.model.write_bytes(ASCII)
        with self.assertRaises(ValueError):
            await export_gx(self.source,self.model,self.output,GXLimits(timeout=.001),capture=self.capture,metadata=META)
        self.assertFalse(self.output.exists())
