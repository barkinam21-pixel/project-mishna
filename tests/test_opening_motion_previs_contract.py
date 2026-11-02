"""Portable code/source checks that do not need OpenCV, sound media or API credentials."""
import ast, json, pathlib, unittest
ROOT=pathlib.Path(__file__).resolve().parents[1]
RENDERER=ROOT/'tools'/'build_opening_motion_previs.py'
QA=ROOT/'tools'/'verify_opening_motion_previs.py'
MANIFEST=ROOT/'episodes'/'berakhot-01-01'/'opening-45s-director-pack-v1.json'

class OpeningMotionContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source=RENDERER.read_text(encoding='utf-8')
        cls.data=json.loads(MANIFEST.read_text(encoding='utf-8'))
    def test_render_code_compiles(self):
        compile(self.source,str(RENDERER),'exec')
        compile(QA.read_text(encoding='utf8'),str(QA),'exec')
    def test_renderer_no_provider_access(self):
        tree=ast.parse(self.source)
        imports=[n.module for n in ast.walk(tree) if isinstance(n,ast.ImportFrom)]
        imports += [x.name for n in ast.walk(tree) if isinstance(n,ast.Import) for x in n.names]
        self.assertFalse(any(x and x.startswith(('fal','requests','httpx','openai','google.genai','boto3')) for x in imports))
        self.assertNotIn('tinyfish',self.source.lower())
        self.assertNotIn('image_gen',self.source)
    def test_output_rejects_unapproved_spend(self):
        self.assertIn("new_external_spend_authorized",self.source)
        self.assertIn("raise ValueError('Strict zero-spend/no-imagegen gate required')",self.source)
    def test_opening_not_sons(self):
        self.assertEqual([x['id'] for x in self.data['shots']],[f'OPN{i:02d}' for i in range(1,8)])
        self.assertTrue(self.data['sons_return_scene_is_later'])
        self.assertEqual(self.data['next_paid_shot_candidate'],'OPN01')
    def test_moving_human_blocking_not_static_zoom_only(self):
        self.assertIn('draw_figure',self.source)
        self.assertIn('phase=t*6.2',self.source)
        self.assertIn("sid=='OPN06'",self.source)
        self.assertIn("older_hand_end",self.source)
        self.assertIn("younger_hand_end",self.source)
    def test_actual_color_primaries_and_transfer_required(self):
        self.assertIn('colorprim=bt709:transfer=bt709:colormatrix=bt709',self.source)
        qa=QA.read_text(encoding='utf8')
        self.assertIn("'color_primaries':'bt709'",qa)
        self.assertIn("'color_transfer':'bt709'",qa)
    def test_source_quote_is_labeled_dramatization(self):
        s=self.data['source_contract']
        self.assertEqual(s['source_layer'],'dramatization_only_until_next_sequence')
        self.assertIn('המחזה',s['mandatory_first_caption_he'])
        for shot in self.data['shots']:
            self.assertEqual(shot['asset_status'],'not_generated')
            for d in shot.get('dialogue_he',[]):
                self.assertEqual(d['type'],'invented_dramatization_not_a_quote')

if __name__=='__main__':unittest.main()