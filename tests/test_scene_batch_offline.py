"""Adversarial zero-network 15-shot rehearsal using existing M3 mock journal."""
import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from tools.scene_factory import SceneBlocked, digest
from tools.scene_production_packet import build_packet
from tools.scene_cloudflare_spec_adapter import compile_previews
from tools.scene_batch_offline import (
    OfflineFakeCloudflare, OfflineFakeDrive, rehearse_once,
)
from tools.scene_m3_remote import AtomicMemoryJournal, OfflineRemoteCoordinator

ROOT=Path(__file__).resolve().parents[1]


class SceneBatchOfflineTests(unittest.TestCase):
    def setUp(self):
        m=json.loads((ROOT/"episodes/berakhot-01-01/scene-prologue-v02.json").read_text())
        b=json.loads((ROOT/m["bible"]["path"]).read_text())
        self.packet=build_packet(m,b,ROOT)
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root=Path(self.temp.name)
        p=root/"private-media"/"fake.png"
        p.parent.mkdir(parents=True)
        self.refbytes=b"SYNTHETIC_REFERENCE_ONLY_NO_PHOTO_NO_IMAGE"
        p.write_bytes(self.refbytes)
        sha=hashlib.sha256(self.refbytes).hexdigest()
        self.ref={"path":"private-media/fake.png","sha256":sha,"expected_sha256":sha,
                  "role":"SYNTHETIC_TEST","synthesis_rights_confirmed":True}
        legacy={"schema_version":1,
                "model":{"id":"black-forest-labs/FLUX.2-klein-4B","revision":"UNVERIFIED"},
                "size":[1024,576],"references":[self.ref],
                "available_backends":{"cloudflare":{
                    "type":"cloudflare","model":"@cf/black-forest-labs/flux-2-klein-4b"}}}
        self.previews=compile_previews(self.packet,legacy,root)
        self.baseline={"entries":{}, "attempts":[
            {"key":"OFFLINE_LEGACY_"+str(i), "status":"SYNTHETIC", "accepted":False}
            for i in range(6)]}
        self.journal=AtomicMemoryJournal(copy.deepcopy(self.baseline))
        self.drive=OfflineFakeDrive({self.ref["path"]:self.refbytes})
        self.provider=OfflineFakeCloudflare()
        self.request_id="d"*32

    def run_batch(self, **kwargs):
        return rehearse_once(self.packet,self.previews,
            drive=self.drive, provider=self.provider, journal=self.journal,
            baseline=self.baseline, request_id=self.request_id,
            max_attempts=kwargs.pop("max_attempts",2),**kwargs)

    def add_cache(self,index,accepted=True,rights=True,raw=b"TEST_APPROVED_SYNTHETIC_PIXELS"):
        job=self.packet["jobs"][index]
        self.drive.cache[job["asset_key"]]={
            "accepted":accepted,"rights_verified":rights,"shot_id":job["shot_id"],
            "origin":"OFFLINE_SYNTHETIC_FIXTURE","bytes":raw,
            "sha256":hashlib.sha256(raw).hexdigest(),
        }
        return job

    def test_two_full_fake_preparations_with_immutable_six_attempt_prefix(self):
        out=self.run_batch()
        self.assertEqual(out["status"],"OFFLINE_FAKE_BATCH_DONE_NOT_ART")
        self.assertEqual(out["recorded_fake_receipts"],2)
        self.assertEqual(self.provider.prepares,["EP-P01","EP-P02"])
        self.assertEqual(self.provider.submit_calls,0)
        self.assertEqual(out["external_inference_requests"],0)
        self.assertFalse(out["generation_authorized"])
        version,journal=self.journal.read()
        self.assertEqual(journal["attempts"][:6],self.baseline["attempts"])
        self.assertEqual(len(journal["attempts"]),8)
        status=OfflineRemoteCoordinator(self.journal).status(self.request_id)
        self.assertEqual(status["status"],"SIMULATED_NOT_ART")
        self.assertTrue(all(x["kind"]=="OFFLINE_FAKE_NOT_IMAGE"
                            and x["accepted"] is False
                            for x in status["receipts"].values()))

    def test_only_sha_verified_explicit_synthetic_accepted_cache_is_skipped(self):
        self.add_cache(0)
        out=self.run_batch()
        self.assertEqual(out["cached_synthetic"],["EP-P01"])
        self.assertEqual(self.provider.prepares,["EP-P02","EP-P03"])
        self.assertEqual(len(self.journal.read()[1]["attempts"]),8)
        self.assertEqual(self.journal.read()[1]["attempts"][:6],self.baseline["attempts"])

    def test_unapproved_opn_candidates_or_cache_without_rights_are_not_hits(self):
        self.add_cache(6,accepted=False)
        self.add_cache(13,accepted=False)
        self.add_cache(0,accepted=True,rights=False)
        self.assertFalse(self.drive.accepted_synthetic_cache_hit(self.packet["jobs"][6]))
        self.assertFalse(self.drive.accepted_synthetic_cache_hit(self.packet["jobs"][13]))
        out=self.run_batch()
        self.assertEqual(out["cached_synthetic"],[])
        self.assertEqual(self.provider.prepares,["EP-P01","EP-P02"])
        self.assertEqual(out["external_inference_requests"],0)

    def test_accepted_fixture_bad_bytes_are_blocked_before_reservation(self):
        j=self.add_cache(0)
        self.drive.cache[j["asset_key"]]["bytes"]=b"CHANGED_AFTER_CACHE"
        with self.assertRaisesRegex(SceneBlocked,"BATCH_FAKE_ACCEPTED_CACHE_HASH_CHANGED"):
            self.run_batch()
        self.assertEqual(self.journal.writes,0)
        self.assertEqual(self.provider.prepares,[])

    def test_recover_and_continue_after_completed_receipt_without_repreparing(self):
        first=self.run_batch(step_limit=1)
        self.assertEqual(first["status"],"OFFLINE_FAKE_PARTIAL_RESUMABLE")
        self.assertEqual(self.provider.prepares,["EP-P01"])
        self.provider=OfflineFakeCloudflare() # Simulated process restart
        second=self.run_batch()
        self.assertEqual(second["status"],"OFFLINE_FAKE_BATCH_DONE_NOT_ART")
        self.assertEqual(self.provider.prepares,["EP-P02"])
        third=self.run_batch()
        self.assertEqual(third["recorded_fake_receipts"],2)
        self.assertEqual(self.provider.prepares,["EP-P02"])
        self.assertEqual(len(self.journal.read()[1]["attempts"]),8)

    def test_crash_after_reservation_halts_forever_without_second_attempt(self):
        with self.assertRaisesRegex(SceneBlocked,"BATCH_FAKE_CRASH_AFTER_RESERVATION"):
            self.run_batch(crash_after_reservation=True)
        self.assertEqual(self.provider.prepares,["EP-P01"])
        out=self.run_batch()
        self.assertEqual(out["status"],"OFFLINE_HALTED_UNCERTAIN_NO_RETRY")
        self.assertEqual(out["pending_shot_id"],"EP-P01")
        self.assertEqual(self.provider.prepares,["EP-P01"])
        self.assertEqual(len(self.journal.read()[1]["attempts"]),7)
        self.assertEqual(self.journal.read()[1]["attempts"][:6],self.baseline["attempts"])

    def test_missing_fake_reference_never_creates_model_reservation(self):
        self.drive.references={}
        with self.assertRaisesRegex(SceneBlocked,"BATCH_FAKE_REFERENCE_HASH_OR_BYTES_MISSING"):
            self.run_batch()
        self.assertEqual(self.provider.prepares,[])
        self.assertEqual(len(self.journal.read()[1]["attempts"]),6)
        self.drive.references={self.ref["path"]:self.refbytes}
        self.assertEqual(self.run_batch()["recorded_fake_receipts"],2)

    def test_changed_scene_spec_same_request_cannot_reuse_old_reservations(self):
        self.run_batch()
        tampered=copy.deepcopy(self.packet)
        tampered["jobs"][0]["asset_key"]="e"*64
        tampered["packet_sha256"]=digest({k:v for k,v in tampered.items() if k!="packet_sha256"})
        preview=copy.deepcopy(self.previews)
        preview["jobs"][0]["asset_key"]="e"*64
        preview["scene_packet_sha256"]=tampered["packet_sha256"]
        preview["preview_sha256"]=digest({k:v for k,v in preview.items() if k!="preview_sha256"})
        with self.assertRaisesRegex(SceneBlocked,"M3_REMOTE_REQUEST_SCOPE_CHANGED"):
            rehearse_once(tampered,preview,drive=self.drive,provider=self.provider,
                journal=self.journal,baseline=self.baseline,request_id=self.request_id,max_attempts=2)
        self.assertEqual(len(self.journal.read()[1]["attempts"]),8)

    def test_fake_scope_tampering_and_non_mock_dependencies_fail_closed(self):
        for key,value in (("provider_dispatch_authorized",True),
                          ("native_legacy_engine_compatible",True)):
            changed=copy.deepcopy(self.previews)
            changed[key]=value
            changed["preview_sha256"]=digest({k:v for k,v in changed.items() if k!="preview_sha256"})
            with self.assertRaisesRegex(SceneBlocked,"BATCH_FAKE_REQUIRES_CLOSED_SAFE_PREVIEW"):
                rehearse_once(self.packet,changed,drive=self.drive,provider=self.provider,
                    journal=self.journal,baseline=self.baseline,request_id=self.request_id,max_attempts=2)
        with self.assertRaisesRegex(SceneBlocked,"BATCH_ONLY_FAKE_DEPENDENCIES_ALLOWED"):
            rehearse_once(self.packet,self.previews,drive=object(),provider=self.provider,
                journal=self.journal,baseline=self.baseline,request_id=self.request_id,max_attempts=2)
        self.assertEqual(self.journal.writes,0)

    def test_untrusted_preview_cannot_claim_reference_rights_or_remove_blocks(self):
        changed=copy.deepcopy(self.previews)
        changed["jobs"][0]["reference_rights_scope"]="APPROVED"
        changed["preview_sha256"]=digest({k:v for k,v in changed.items() if k!="preview_sha256"})
        with self.assertRaisesRegex(SceneBlocked,"BATCH_FAKE_JOB_OR_GATE_CHANGED"):
            rehearse_once(self.packet,changed,drive=self.drive,provider=self.provider,
                journal=self.journal,baseline=self.baseline,request_id=self.request_id,max_attempts=2)
        self.assertEqual(self.journal.writes,0)

    def test_foreign_history_or_new_request_cannot_rebase_old_fake_budget(self):
        self.run_batch()
        new_id="e"*32
        with self.assertRaisesRegex(SceneBlocked,"M3_REMOTE_HISTORY_CHANGED"):
            rehearse_once(self.packet,self.previews,drive=self.drive,provider=self.provider,
                journal=self.journal,baseline=self.baseline,request_id=new_id,max_attempts=2)
        v,journal=self.journal.read()
        journal["attempts"].append({"key":"FOREIGN_WRITER","status":"UNKNOWN"})
        self.assertTrue(self.journal.compare_and_swap(v,journal))
        with self.assertRaisesRegex(SceneBlocked,"M3_REMOTE_HISTORY_CHANGED|M3_REMOTE_FOREIGN_HISTORY_CHANGE"):
            self.run_batch()
        self.assertEqual(self.provider.submit_calls,0)


if __name__=="__main__":unittest.main()
