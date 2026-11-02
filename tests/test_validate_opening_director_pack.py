import copy
import importlib.util
import json
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]
S=importlib.util.spec_from_file_location("validate_opening_director_pack",ROOT/"tools"/"validate_opening_director_pack.py")
MODULE=importlib.util.module_from_spec(S)
S.loader.exec_module(MODULE)
PACK=json.loads((ROOT/"episodes"/"berakhot-01-01"/"opening-45s-director-pack-v1.json").read_text(encoding="utf-8"))

class OpeningDirectorPackValidation(unittest.TestCase):
    def copy(self): return copy.deepcopy(PACK)
    def valid(self,x): return MODULE.validate(x)["status"]=="PASS_DRY_RUN_ONLY"
    def test_original_pack_passes(self): self.assertTrue(self.valid(self.copy()))
    def test_opn01_ambiguous_two_traveler_frame_rejected(self):
        d=self.copy()
        d["shots"][0]["prompt_subject_en"]="TWO ANONYMOUS travelers in a close shot" * 10
        self.assertFalse(self.valid(d))
    def test_opn01_extra_leg_contract_rejected(self):
        d=self.copy()
        d["shots"][0]["anatomy_contract"]["visible_legs"]=3
        self.assertFalse(self.valid(d))
    def test_prior_spend_cannot_be_erased(self):
        d=self.copy()
        d["production_history"]["previous_opn01_paid_attempts"]=0
        self.assertFalse(self.valid(d))
    def test_no_new_paid_approval_may_be_claimed(self):
        d=self.copy()
        d["production_history"]["new_opn01_paid_authorization"]=True
        self.assertFalse(self.valid(d))
    def test_schema_rejects_paid_authorization(self):
        d=self.copy();d["privacy"]["fal_paid_approval_granted"]=True;self.assertFalse(self.valid(d))
    def test_schema_rejects_any_image_generation(self):
        d=self.copy();d["privacy"]["images_generated_for_this_pack"]=1;self.assertFalse(self.valid(d))
    def test_schema_rejects_images_in_chatgpt(self):
        d=self.copy();d["privacy"]["generation_in_chatgpt_forbidden"]=False;self.assertFalse(self.valid(d))
    def test_duplicate_shot_rejected(self):
        d=self.copy();d["shots"][1]["id"]="OPN01";self.assertFalse(self.valid(d))
    def test_non_contiguous_frames_rejected(self):
        d=self.copy();d["shots"][2]["start_frame"]+=1;self.assertFalse(self.valid(d))
    def test_camera_speed_115_must_be_kept(self):
        d=self.copy();d["shots"][1]["camera"]["motion_speed_factor"]=1.0;self.assertFalse(self.valid(d))
    def test_no_shake_or_pseudo_camera_jitter(self):
        d=self.copy();d["shots"][3]["camera"]["shake_px"]=1;self.assertFalse(self.valid(d))
    def test_no_sons_scene_as_opening(self):
        d=self.copy();d["next_paid_shot_candidate"]="SH09";self.assertFalse(self.valid(d))
    def test_no_fake_source_quotes(self):
        d=self.copy();d["shots"][2]["dialogue_he"][0]["type"]="direct_historical_quote";self.assertFalse(self.valid(d))
    def test_no_source_label_skipping(self):
        d=self.copy();d["shots"][5]["source_label"]="היסטוריה מתועדת";self.assertFalse(self.valid(d))
    def test_later_edit_does_not_autolock_sources(self):
        d=self.copy();d["source_contract"]["approved_for_public_release"]=True;self.assertFalse(self.valid(d))
    def test_no_copyrighted_music_use(self):
        d=self.copy();d["theme_motif_music"]["original_music_only"]=False;self.assertFalse(self.valid(d))
    def test_spotting_sheet_covers_all_frames(self):
        d=self.copy();d["audio_spotting_frames"][2]["end_frame"]-=20;self.assertFalse(self.valid(d))
    def test_no_repeating_crop_as_separate_original(self):
        d=self.copy();d["shots"][4]["original_illustration_required"]=False;self.assertFalse(self.valid(d))

if __name__=="__main__":unittest.main()