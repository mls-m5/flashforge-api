from pathlib import Path
import unittest
from finderlab.priming_review import review_priming, candidate_issues, _distance
from helpers import workspace_tempdir

PREFIX='G90\nM82\nG92 E0\nG1 X-10 Y0 Z.2\n'
BODY=';TYPE:Outer wall\nG1 X2 E1\nG1 Y2 E2\nG1 X-2 E3\nG1 Y-2 E4\n'
FIXED=PREFIX+'G1 X10 E1\nG92 E0\n;LAYER_CHANGE\nG1 Z.27\nG1 X-2 Y-2\n'+BODY+';LAYER_CHANGE\n'
SKIRT=PREFIX+''';LAYER_CHANGE
G1 E-1.3
G92 E0
G1 X-5 Y-5 Z.27
G1 E1.3
;TYPE:Skirt
G1 X5 E2.3
G1 Y5 E3.3
G1 X-5 E4.3
G1 Y-5 E5.3
G92 E0
G1 X-3 Y-3
;TYPE:Brim
G1 X3 E1
G1 Y3 E2
G1 X-3 E3
G1 Y-3 E4
G92 E0
G1 X-2 Y-2
'''+BODY+';LAYER_CHANGE\n'

class PrimingReviewTests(unittest.TestCase):
    def report(self,text,**kwargs):
        with workspace_tempdir() as directory:
            path=Path(directory)/'input.gcode';raw=text.encode();path.write_bytes(raw)
            result=review_priming(path,**kwargs);self.assertEqual(path.read_bytes(),raw)
            return result

    def test_fixed_startup_nominal_xy_overlap_even_at_different_z(self):
        r=self.report(FIXED)
        self.assertEqual(r['startup_vs_object']['xy_intersections'],2)
        self.assertEqual(r['first_layer_first_feature'],'outer wall')
        self.assertFalse(r['safety_validated']);self.assertTrue(r['prefix_mm_assumption'])

    def test_skirt_brim_gaps_and_retract_debt(self):
        r=self.report(SKIRT)
        self.assertEqual(r['first_layer_first_feature'],'skirt');self.assertEqual(r['segments']['startup'],0)
        self.assertEqual(r['skirt_vs_object'],{'xy_intersections':0,'min_centerline_gap_mm':3.})
        self.assertEqual(r['skirt_vs_brim'],{'xy_intersections':0,'min_centerline_gap_mm':2.})
        self.assertEqual(r['segments']['skirt'],4)
        self.assertEqual(candidate_issues(r),[])
        self.assertEqual(r['deposition_xy_bounds_mm']['skirt'],[[-5.,5.],[-5.,5.]])
        r['deposition_xy_bounds_mm']['skirt'][0][1]=72.105
        self.assertTrue(any('margin' in issue for issue in candidate_issues(r)))

    def test_unsupported_ambiguous_and_resource_limits_fail_without_partial_report(self):
        for text in ('G20\n'+FIXED,FIXED.replace('G90\n',''),FIXED.replace('G1 X10 E1','G2 X10 E1'),FIXED.replace('X10 E1','X10 X11 E1'),FIXED.replace('X10 E1','X1e999 E1'),FIXED.replace('G92 E0\n;LAYER','G92 X0 E0\n;LAYER'),FIXED.replace('G92 E0\n;LAYER','G28\nG92 E0\n;LAYER'),'\0'+FIXED,';'+('x'*4096)+'\n'+FIXED,FIXED.replace(';LAYER_CHANGE',';unknown')):
            with self.subTest(prefix=text[:12]):
                with self.assertRaises(ValueError):self.report(text)
        with self.assertRaises(ValueError):self.report(SKIRT,max_pairs=1)

    def test_segment_distance_crossing_touch_parallel_and_collinear(self):
        self.assertEqual(_distance((0,0),(2,0),(1,-1),(1,1)),0)
        self.assertEqual(_distance((0,0),(2,0),(2,0),(3,0)),0)
        self.assertEqual(_distance((0,0),(2,0),(3,0),(4,0)),1)
        self.assertEqual(_distance((0,0),(2,0),(0,3),(2,3)),3)
