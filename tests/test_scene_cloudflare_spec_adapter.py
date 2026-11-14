"""No-network tests for scene-wide Cloudflare shape bridge."""
import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from tools.scene_factory import SceneBlocked, digest
from tools.scene_production_packet import build_packet
from tools.scene_cloudflare_spec_adapter import compile_previews, summarize

ROOT=Path(__file__).resolve().parents[1]


def template(reference):
    return {
        "schema_version":1,
        "model":{"id":"black-forest-labs/FLUX.2-klein-4B","revision":"UNVERIFIED"},
        "size":[1024,576],
        "style":"Legacy sunset old style MUST NOT be imported into dawn",
        "references":[reference],
        "available_backends":{"cloudflare":{"type":"cloudflare",
            "model":"@cf/black-forest-labs/flux-2-klein-4b",
            "safety":{"free_hard_cap_verified":False}}},
    }


class CloudflareSceneAdapterTests(unittest.TestCase):
    def setUp(self):
        scene=json.loads((ROOT/'episodes/berakhot-01-01/scene-prologue-v02.json').read_text())
        bible=json.loads((ROOT/scene['bible']['path']).read_text())
        self.packet=build_packet(scene,bible,ROOT)
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        p=self.root/'private-media'/'synthetic-reference.png'
        p.parent.mkdir(parents=True)
        p.write_bytes(b"FAKE_NONTIMAGE_NO_PROVIDER")
        sha=hashlib.sha256(p.read_bytes()).hexdigest()
        self.reference={"path":"private-media/synthetic-reference.png",
            "sha256":sha,"expected_sha256":sha,
            "synthesis_rights_confirmed":True,
            "rights_basis":"TEST_FIXTURE_ONLY_NOT_PRODUCTION"}
        self.legacy=template(self.reference)

    def test_real_15_shot_packet_compiles_to_provider_shape_no_dispatch(self):
        out=compile_previews(self.packet,self.legacy,self.root)
        self.assertEqual(out["job_count"],15)
        self.assertEqual(out["provider_calls"],0)
        self.assertFalse(out["provider_dispatch_authorized"])
        self.assertFalse(out["native_legacy_engine_compatible"])
        self.assertEqual(out["reference_status"],["PRIVATE_BYTES_HASH_VERIFIED_ONLY"])
        self.assertEqual([j["shot_id"] for j in out["jobs"]],
                         [f"EP-P{i:02d}" for i in range(1,16)])
        self.assertTrue(all(j["provider_calls"]==0 and j["blockers"] for j in out["jobs"]))
        self.assertEqual(summarize(out)["blocked_jobs"],15)

    def test_old_sunset_style_never_replaces_new_dawn(self):
        out=compile_previews(self.packet,self.legacy,self.root)
        for job in out["jobs"]:
            spec=job["engine_spec_preview"]
            self.assertIn("dawn",spec["prompt"])
            self.assertNotIn("sunset",spec["prompt"].lower())
            self.assertNotIn("sunset",spec["style"].lower())
            self.assertEqual(spec["size"],[1024,576])
            self.assertEqual(spec["backend"]["type"],"cloudflare")
            self.assertEqual(spec["characters"],{}) # must lock visibility first

    def test_same_legacy_candidate_is_never_two_approved_originals(self):
        out=compile_previews(self.packet,self.legacy,self.root)
        ids=[(j["shot_id"],j["legacy_candidate_id"]) for j in out["jobs"]
             if j["legacy_candidate_id"]]
        self.assertEqual(ids,[("EP-P07","OPN02"),("EP-P09","OPN03"),
                              ("EP-P14","OPN02")])
        for j in out["jobs"]:
            if j["shot_id"] in ("EP-P07","EP-P14"):
                self.assertIn("DUPLICATE_CANDIDATE_COVERAGE",j["blockers"])
            self.assertIn("SCENE_NATIVE_DIRECTOR_CONTROLS_UNMAPPED",j["blockers"])
            self.assertIn("HOSTED_M3_AND_GENERATION_POLICY_CLOSED",j["blockers"])

    def test_stable_asset_keys_and_seeds_when_caption_changes(self):
        changed=copy.deepcopy(self.packet)
        changed["jobs"][0]["sound_spotting"][0]["kind"]="draft tweak"
        changed["packet_sha256"]=digest({k:v for k,v in changed.items() if k!="packet_sha256"})
        old=compile_previews(self.packet,self.legacy,self.root)
        newer=compile_previews(changed,self.legacy,self.root)
        a=old["jobs"][0]["engine_spec_preview"];b=newer["jobs"][0]["engine_spec_preview"]
        self.assertEqual(a["seed"],b["seed"])
        self.assertEqual(a["prompt"],b["prompt"])
        self.assertNotEqual(old["preview_sha256"],newer["preview_sha256"])

    def test_untrusted_tampering_rejected_not_sent(self):
        tampered=copy.deepcopy(self.packet)
        tampered["jobs"][0]["ready_for_model_submission"]=True
        with self.assertRaisesRegex(SceneBlocked,"CLOUD_PACKET_CHANGED"):
            compile_previews(tampered,self.legacy,self.root)
        tampered["packet_sha256"]=digest({k:v for k,v in tampered.items() if k!="packet_sha256"})
        with self.assertRaisesRegex(SceneBlocked,"CLOUD_JOB_NOT_CLOSED"):
            compile_previews(tampered,self.legacy,self.root)

    def test_missing_changed_or_unlicensed_reference_is_explicit_blocker(self):
        p=self.root/'private-media/synthetic-reference.png'
        p.unlink()
        out=compile_previews(self.packet,self.legacy,self.root)
        self.assertIn("PRIVATE_REFERENCE_NOT_RESTORED",out["reference_status"])
        p.write_bytes(b"BAD_CHANGING_BYTES")
        out=compile_previews(self.packet,self.legacy,self.root)
        self.assertIn("PRIVATE_REFERENCE_HASH_CHANGED",out["reference_status"])
        p.write_bytes(b"FAKE_NONTIMAGE_NO_PROVIDER")
        self.legacy["references"][0]["synthesis_rights_confirmed"]=False
        out=compile_previews(self.packet,self.legacy,self.root)
        self.assertIn("REFERENCE_RIGHTS_NOT_ATTESTED",out["reference_status"])

    def test_legacy_provider_model_does_not_mutate_or_enable_billing(self):
        before=copy.deepcopy(self.legacy)
        out=compile_previews(self.packet,self.legacy,self.root)
        self.assertEqual(self.legacy,before)
        self.assertFalse(out["provider_dispatch_authorized"])
        self.assertEqual(self.legacy["available_backends"]["cloudflare"]["safety"]["free_hard_cap_verified"],False)
        changed=copy.deepcopy(self.legacy);changed["model"]["id"]="unknown"
        with self.assertRaisesRegex(SceneBlocked,"CLOUD_MODEL_CHANGED"):
            compile_previews(self.packet,changed,self.root)

    def test_engine_shot_alias_not_silently_substituted(self):
        out=compile_previews(self.packet,self.legacy,self.root)
        self.assertTrue(all(j["shot_id"].startswith("EP-P") for j in out["jobs"]))
        self.assertTrue(all("LEGACY_ENGINE_EP_SHOT_IDS_UNSUPPORTED" in j["blockers"]
                            for j in out["jobs"]))
        self.assertEqual(len({j["engine_spec_preview"]["seed"] for j in out["jobs"]}),15)


if __name__=="__main__":unittest.main()
