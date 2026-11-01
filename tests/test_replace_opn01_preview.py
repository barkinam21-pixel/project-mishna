"""Fast no-network contracts for exact 45s opening shot replacement."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
SPEC=importlib.util.spec_from_file_location('replace_opn01_preview',ROOT/'tools/replace_opn01_preview.py')
MOD=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(MOD)
DATA=json.loads((ROOT/'episodes/berakhot-01-01/opening-45s-director-pack-v1.json').read_text())

class ShotReplacement(unittest.TestCase):
    def test_expected_story_order(self):
        self.assertEqual(DATA['shots'][0]['id'],'OPN01')
        self.assertEqual(DATA['shots'][0]['frames'],MOD.FIRST)
        self.assertEqual(DATA['shots'][-1]['end_frame'],MOD.TOTAL)
    def test_ass_source_label_is_explicit(self):
        with tempfile.TemporaryDirectory() as td:
            f=Path(td)/'stamp.ass';MOD.ass_stamp(f)
            s=f.read_text()
            self.assertIn('המחזה סמלית',s)
            self.assertIn('טרם אושר',s)
            self.assertIn('Noto Sans Hebrew',s)
    def test_stamp_not_fabricated_historical_quote(self):
        with tempfile.TemporaryDirectory() as td:
            f=Path(td)/'stamp.ass';MOD.ass_stamp(f)
            s=f.read_text();self.assertNotIn('חייבין',s)
            self.assertNotIn('מותרין',s)
    def test_exact_sha_needed(self):
        with tempfile.TemporaryDirectory() as td:
            img=Path(td)/'img.png';img.write_bytes(b'PNG')
            master=Path(td)/'master.mp4';master.write_bytes(b'video')
            with self.assertRaises(MOD.UnsafeMedia):
                MOD.preflight(DATA,img,'bad-hash',master)
    def test_missing_media_never_autosubstitutes(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)
            with self.assertRaises(MOD.UnsafeMedia):
                MOD.preflight(DATA,p/'wrong.png','0'*64,p/'wrong.mp4')
    def test_render_rejects_missing_human_review_before_ffmpeg(self):
        with tempfile.TemporaryDirectory() as td:
            d=Path(td)
            with patch.object(MOD,'preflight',return_value={'status':'OFFLINE_EDITORIAL_PLAN_READY'}), \
                 patch.object(MOD.visual_gate_opn01,'verify_visual_gate') as gate, \
                 patch.object(MOD.subprocess,'run') as command:
                gate.side_effect=MOD.visual_gate_opn01.VisualGateError('No review')
                with self.assertRaises(MOD.visual_gate_opn01.VisualGateError):
                    MOD.render(d/'image.png','a'*64,d/'blockout.mp4',d/'manifest.json',d/'result.mp4',dry_run=False)
                gate.assert_called_once_with(None,'a'*64)
                command.assert_not_called()
                self.assertFalse((d/'result.mp4').exists())
    def test_renderer_cli_requires_separate_review_file(self):
        s=(ROOT/'tools/replace_opn01_preview.py').read_text()
        self.assertIn("--visual-review-json",s)
        self.assertIn("verify_visual_gate(visual_review, expected_sha)",s)
        self.assertIn("visual_review=a.visual_review_json",s)
        f=(ROOT/'tools/finish_opn01_private.py').read_text()
        self.assertIn("dry_run=False,visual_review=visual_review",f)

    def test_remux_prevents_last_frame_timestamp_shortfall(self):
        s=(ROOT/'tools/replace_opn01_preview.py').read_text()
        # A container duration of 45s alone is insufficient: the original
        # video stream ended at 44.958333s despite 1080 frames.
        self.assertIn("'-video_track_timescale','12288'",s)
        self.assertIn("'-c','copy'",s)
        self.assertIn("v.get('avg_frame_rate')!='24/1'",s)
        self.assertIn("abs(float(v.get('duration','0'))-45.0)>.001",s)
        self.assertIn('retimed.replace(output_path)',s)

    def test_output_keeps_hebrew_tags_and_phone_friendly_codec(self):
        s=(ROOT/'tools/replace_opn01_preview.py').read_text()
        self.assertIn("'language=heb'",s)
        self.assertIn("'colorprim=bt709:transfer=bt709:colormatrix=bt709'",s)
        self.assertIn("'-movflags','+faststart'",s)
        self.assertIn('end_frame={FIRST}',s)
        self.assertIn('start_frame={FIRST}:end_frame={TOTAL}',s)

if __name__=='__main__':unittest.main()