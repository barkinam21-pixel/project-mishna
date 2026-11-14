"""Real 15-shot scene-native direction tests; no network or private media."""
import copy
import json
import unittest
from pathlib import Path

from tools.scene_factory import SceneBlocked, keys
from tools.scene_native_direction import compile_native_direction
from tools.scene_production_packet import build_packet

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "episodes/berakhot-01-01/scene-prologue-v02.json"


class NativeSceneDirectionTests(unittest.TestCase):
    def setUp(self):
        self.scene=json.loads(MANIFEST.read_text(encoding="utf-8"))
        self.bible=json.loads((ROOT/self.scene["bible"]["path"]).read_text(encoding="utf-8"))

    def compile(self, i):
        s=self.scene["shots"][i]
        return compile_native_direction(s,self.bible["states"][s["pre_state"]])

    def test_all_fifteen_scene_native_shots_have_draft_cast_and_axis(self):
        packet=build_packet(self.scene,self.bible,ROOT)
        self.assertEqual(len(packet["jobs"]),15)
        self.assertEqual(packet["inference_requests"],0)
        self.assertFalse(packet["provider_dispatch_authorized"])
        self.assertEqual(packet["duration_frames"],2184)
        for i in range(15):
            d=self.compile(i)
            self.assertEqual(d["review_status"],"DRAFT_REQUIRES_REVIEW")
            self.assertEqual(d["scene_shot_id"],f"EP-P{i+1:02d}")
            self.assertEqual(d["axis"],"south side of travel line")
            self.assertEqual(d["camera_side"],"south")
            self.assertEqual(d["time_of_day"],"dawn")
            self.assertEqual(d["sun_direction"],"screen-left")
            self.assertEqual(list(d["characters"]),d["cast_visible"])
            self.assertTrue(packet["jobs"][i]["visual_spec"]["scene_native_direction"])

    def test_empty_landscape_cannot_inherit_entire_scene_cast(self):
        self.assertEqual(self.compile(0)["cast_visible"],[])
        self.assertEqual(self.compile(1)["characters"],{})
        self.assertEqual(self.compile(14)["cast_visible"],[])
        for i in (2,4,5):
            d=self.compile(i)
            self.assertEqual(d["cast_visible"],[])
            self.assertTrue(d["human_detail_unattributed"])
        for i in (6,7,10,11,13):
            self.assertEqual(set(self.compile(i)["cast_visible"]),{"elder","younger"})

    def test_two_shot_draft_left_right_and_waterskin_transfer(self):
        front=self.compile(6)
        transfer=self.compile(11)
        self.assertEqual(front["positions"],{"elder":"screen-left","younger":"screen-right"})
        self.assertEqual(transfer["positions"],front["positions"])
        self.assertEqual(self.compile(12)["cast_visible"],["younger"])
        self.assertIn("indigo robe",front["characters"]["elder"]["description"])
        self.assertIn("brown wrap",front["characters"]["younger"]["description"])
        self.assertTrue(all(x["references"]==[] for x in front["characters"].values()))
        self.assertEqual(front["source_anchor"],"docs/epic-intro-prologue-shotmap-v02.md#P07")

    def test_wrong_sun_time_axis_and_side_fail_closed(self):
        for field,value in (("time_of_day","sunset"),("sun_direction","screen-right"),
                            ("axis","north side of travel line"),("camera_side","north"),
                            ("screen_direction","left-to-right")):
            changed=copy.deepcopy(self.scene["shots"][6])
            changed["blocking"][field]=value
            with self.subTest(field=field), self.assertRaisesRegex(
                SceneBlocked,"NATIVE_AXIS_OR_DAYLIGHT_CONFLICT|NATIVE_CAMERA_SIDE_CROSSES_AXIS"
            ):
                compile_native_direction(changed,self.bible["states"]["DAWN_BEFORE"])

    def test_forged_or_missing_cast_and_position_fail_closed(self):
        for change,reason in (
            ({"cast_visible":["invented"],"positions":{"invented":"center"}},"NATIVE_CAST_NOT_IN_BIBLE"),
            ({"cast_visible":["elder"],"positions":{"younger":"screen-left"}},"NATIVE_CAST_POSITION_INVALID"),
            ({"positions":{"elder":"top-right","younger":"screen-right"}},"NATIVE_CAST_POSITION_INVALID"),
            ({"cast_visible":["elder","elder"]},"NATIVE_CAST_VISIBILITY_INVALID"),
            ({"human_detail_unattributed":True},"NATIVE_UNATTRIBUTED_DETAIL_INVALID"),
        ):
            shot=copy.deepcopy(self.scene["shots"][6])
            shot["blocking"].update(change)
            with self.subTest(change=change),self.assertRaisesRegex(SceneBlocked,reason):
                compile_native_direction(shot,self.bible["states"]["DAWN_BEFORE"])

    def test_unreviewed_direction_cannot_be_automatically_approved(self):
        shot=copy.deepcopy(self.scene["shots"][6])
        shot["blocking"]["review_status"]="APPROVED"
        with self.assertRaisesRegex(SceneBlocked,"NATIVE_BLOCKING_SCOPE_OR_APPROVAL_INVALID"):
            compile_native_direction(shot,self.bible["states"]["DAWN_BEFORE"])
        shot=copy.deepcopy(self.scene["shots"][6])
        shot["blocking"]["source_anchor"]="historical manuscript verified"
        with self.assertRaisesRegex(SceneBlocked,"NATIVE_SHOT_SOURCE_ANCHOR_INVALID"):
            compile_native_direction(shot,self.bible["states"]["DAWN_BEFORE"])
        shot=copy.deepcopy(self.scene["shots"][6])
        del shot["blocking"]["cast_visible"]
        with self.assertRaisesRegex(SceneBlocked,"NATIVE_BLOCKING_SCHEMA_INVALID"):
            compile_native_direction(shot,self.bible["states"]["DAWN_BEFORE"])

    def test_one_camera_blocking_edit_invalidates_only_its_visual_asset_key(self):
        first=keys(self.scene,self.bible)["asset_keys"]
        changed=copy.deepcopy(self.scene)
        changed["shots"][6]["blocking"]["composition"] += " revised creative framing"
        second=keys(changed,self.bible)["asset_keys"]
        self.assertEqual({k for k in first if first[k]!=second[k]},{"EP-P07"})
        changed=copy.deepcopy(self.scene)
        changed["shots"][6]["captions"]=[{"text":"טיוטה","start_frame":0,"end_frame":20}]
        self.assertEqual(keys(changed,self.bible)["asset_keys"],first)

    def test_legacy_opn_shot_id_cannot_masquerade_as_episode_shot(self):
        shot=copy.deepcopy(self.scene["shots"][6])
        shot["id"]="OPN02"
        shot["blocking"]["shot_id"]="OPN02"
        with self.assertRaisesRegex(SceneBlocked,"NATIVE_EP_SHOT_ID_INVALID"):
            compile_native_direction(shot,self.bible["states"]["DAWN_BEFORE"])


if __name__=="__main__":
    unittest.main()
