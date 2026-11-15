import hashlib
import math
from pathlib import Path
import struct
import unittest
from finderlab.model_transform import normalize_transform,read_stl,layout,write_transformed
from helpers import workspace_tempdir

ASCII=b'solid t\nfacet normal 0 0 1\nouter loop\nvertex 10 20 30\nvertex 14 20 30\nvertex 10 22 33\nendloop\nendfacet\nendsolid t\n'
MACHINE={'printable_area':['-70x-70','70x-70','70x70','-70x70'],'printable_height':'140'}

class ModelTransformTests(unittest.TestCase):
    def test_typed_limits(self):
        self.assertIsNone(normalize_transform(None));self.assertEqual(normalize_transform({})['scale'],1.)
        for value in (True,[],1,'x',{'z':1},{'scale':True},{'x':'1'},{'rotate_z':361},{'x':71},{'scale':0},{'scale':11},{'scale':10**1000},{'x':float('nan')},{'x':float('inf')}):
            with self.subTest(value=type(value)):
                with self.assertRaises(ValueError):normalize_transform(value)

    def test_bake_rotation_scale_position_and_original_immutable(self):
        with workspace_tempdir() as directory:
            source=Path(directory)/'input.stl';output=Path(directory)/'placed.stl';source.write_bytes(ASCII)
            t={'scale':2,'rotate_x':90,'x':30,'y':-15}
            report=write_transformed(source,output,t,MACHINE)
            vertices=read_stl(output)
            expected=[(26,-12,0),(34,-12,0),(26,-18,4)]
            for v,e in zip(vertices,expected):
                for actual,wanted in zip(v,e):self.assertAlmostEqual(actual,wanted,places=5)
            self.assertEqual(source.read_bytes(),ASCII)
            self.assertEqual(report['sha256'],hashlib.sha256(output.read_bytes()).hexdigest())
            self.assertEqual(report['arrange'],0)
            with self.assertRaises(FileExistsError):write_transformed(source,output,t,MACHINE)

    def test_combined_rotation_order_against_sequential_operations(self):
        vertices=[(10.,20.,30.),(14.,20.,30.),(10.,22.,33.)]
        t={'scale':.7,'rotate_x':17,'rotate_y':-28,'rotate_z':63,'x':-21,'y':24}
        got,_=layout(vertices,t)
        expected=[]
        for p in vertices:
            x,y,z=[(p[i]-[12,21,31.5][i])*.7 for i in range(3)]
            a,b,c=[math.radians(t[k]) for k in ('rotate_x','rotate_y','rotate_z')]
            y,z=y*math.cos(a)-z*math.sin(a),y*math.sin(a)+z*math.cos(a)
            x,z=x*math.cos(b)+z*math.sin(b),-x*math.sin(b)+z*math.cos(b)
            x,y=x*math.cos(c)-y*math.sin(c),x*math.sin(c)+y*math.cos(c)
            expected.append([x,y,z])
        offsets=[-21-(min(v[0] for v in expected)+max(v[0] for v in expected))/2,24-(min(v[1] for v in expected)+max(v[1] for v in expected))/2,-min(v[2] for v in expected)]
        for v,e in zip(got,expected):
            for i in range(3):self.assertAlmostEqual(v[i],e[i]+offsets[i],places=10)

    def test_bounds_invalid_geometry_and_profile_fail_before_output(self):
        with workspace_tempdir() as directory:
            source=Path(directory)/'input.stl';output=Path(directory)/'placed.stl';source.write_bytes(ASCII)
            for machine,t in [(MACHINE,{'x':70}),({'printable_area':['0x0'],'printable_height':'140'},{}),(MACHINE,{'scale':10,'y':70}),(MACHINE|{'printable_area':['-70x-70','70x70','70x-70','-70x70']},{})]:
                with self.assertRaises(ValueError):write_transformed(source,output,t,machine)
                self.assertFalse(output.exists())
            for raw in (b'not STL',ASCII.replace(b'vertex 14',b'vertex NaN'),ASCII.replace(b'vertex 14',b'vertex 100001'),ASCII.replace(b'endfacet',b'wrong')):
                source.write_bytes(raw)
                with self.assertRaises(ValueError):read_stl(source)
            source.write_bytes(b'\0'*80+struct.pack('<I',1)+struct.pack('<12fH',0,0,1,float('nan'),0,0,1,0,0,0,1,0,0))
            with self.assertRaises(ValueError):read_stl(source)
