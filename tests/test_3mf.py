"""Generated core-mesh packages only; no private models or hardware."""
import io
from pathlib import Path
import struct
import unittest
from zipfile import ZipFile, ZIP_DEFLATED

from finderlab.model_3mf import geometry_to_stl
from helpers import workspace_tempdir

MODEL = '''<model xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02" unit="millimeter">
<resources><object id="1" type="model"><mesh><vertices>
<vertex x="0" y="0" z="0"/><vertex x="1" y="0" z="0"/><vertex x="0" y="1" z="0"/>
</vertices><triangles><triangle v1="0" v2="1" v3="2"/></triangles></mesh></object></resources>
<build><item objectid="1" transform="1 0 0 0 1 0 0 0 1 10 20 30"/></build></model>'''
RELS = '''<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="r1" Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel" Target="/3D/3dmodel.model"/></Relationships>'''


def package(model=MODEL, rels=RELS, extra=None):
    stream = io.BytesIO()
    with ZipFile(stream, 'w', ZIP_DEFLATED) as z:
        z.writestr('_rels/.rels', rels)
        z.writestr('3D/3dmodel.model', model)
        for name, data in (extra or {}).items(): z.writestr(name, data)
    return stream.getvalue()


class ThreeMFTests(unittest.TestCase):
    def setUp(self):
        self.temp = workspace_tempdir(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name); self.source = self.root/'model.3mf'; self.output=self.root/'model.stl'

    def convert(self, model=MODEL, rels=RELS, extra=None, **options):
        self.source.write_bytes(package(model, rels, extra))
        self.output.unlink(missing_ok=True)
        return geometry_to_stl(self.source, self.output, **options)

    def test_geometry_units_transform_only_and_embedded_config_never_loaded(self):
        report=self.convert(extra={'Metadata/Slic3r_PE.config':'layer_height=99\nstart_gcode=M112\nfilament_diameter=8'})
        self.assertFalse(report['embedded_settings_loaded'])
        self.assertEqual(report['triangles'],1)
        self.assertEqual(report['bounds_mm'],{'X':[10,11],'Y':[20,21],'Z':[30,30]})
        raw=self.output.read_bytes(); self.assertEqual(len(raw),134)
        self.assertEqual(struct.unpack_from('<I',raw,80)[0],1)
        self.assertNotIn(b'M112',raw)
        report=self.convert(MODEL.replace('millimeter','inch'))
        self.assertAlmostEqual(report['bounds_mm']['X'][1],279.4)

    def test_rotation_and_reflection_preserve_surface_orientation(self):
        rotated=MODEL.replace('1 0 0 0 1 0 0 0 1 10 20 30','0 1 0 -1 0 0 0 0 1 0 0 0')
        report=self.convert(rotated)
        self.assertEqual(report['bounds_mm']['X'],[-1,0])
        self.assertEqual(report['bounds_mm']['Y'],[0,1])
        mirrored=MODEL.replace('1 0 0 0 1 0 0 0 1 10 20 30','-1 0 0 0 1 0 0 0 1 0 0 0')
        self.convert(mirrored)
        self.assertGreater(struct.unpack_from('<3f', self.output.read_bytes(),84)[2],0)

    def test_reject_external_components_indices_xml_paths_and_limits(self):
        bad=[MODEL.replace('v3="2"','v3="99"'),MODEL.replace('x="1"','x="nan"'),
             MODEL.replace('unit="millimeter"','unit="unknown"'),MODEL.replace('<mesh>','<components/><mesh>'),
             MODEL.replace('<model ','<model requiredextensions="p" '),
             MODEL.replace('1 0 0 0 1 0 0 0 1 10 20 30','0 0 0 0 0 0 0 0 0 0 0 0'),
             '<!DOCTYPE model [<!ENTITY x "a">]>'+MODEL,
             MODEL.replace('printable="1"','printable="0"').replace('<item objectid','<item printable="0" objectid')]
        for model in bad:
            with self.subTest(model=model[:60]),self.assertRaises(ValueError):self.convert(model)
        with self.assertRaises(ValueError):self.convert(rels=RELS.replace('Id="r1"','Id="r1" TargetMode="External"'))
        with self.assertRaises(ValueError):self.convert(extra={'../escape':'no'})
        with self.assertRaises(ValueError):self.convert(max_output=100)
        with self.assertRaises(ValueError):self.convert(extra={str(i):'' for i in range(257)})

    def test_zero_area_facets_are_reported_but_no_surface_repair_is_guessed(self):
        model=MODEL.replace('</triangles>','<triangle v1="0" v2="0" v3="1"/></triangles>')
        report=self.convert(model)
        self.assertEqual(report['zero_area_facets_skipped'],1)
        self.assertEqual(report['triangles'],1)
