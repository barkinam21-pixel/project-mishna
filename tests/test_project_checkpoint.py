"""No provider calls: historic evidence is durable, consumed tickets still closed."""
import copy
import json
import unittest
from pathlib import Path
from tools.project_checkpoint import summarize, CheckpointError, main

ROOT = Path(__file__).resolve().parents[1]


class ProjectCheckpointTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.facts = json.loads((ROOT/'docs/PROJECT-VERIFIED-FACTS.json').read_text())
        cls.gate = json.loads((ROOT/'episodes/berakhot-01-01/generation-safety.json').read_text())

    def test_historic_free_and_success_survive_closed_one_shot_gate(self):
        x = summarize(self.facts, self.gate)
        self.assertEqual(x['status'], 'CHECKPOINT_REUSED_NO_NEW_PROVIDER_CALL')
        self.assertFalse(x['reask_owner_for_historical_facts'])
        self.assertIn('cloudflare_free_owner_confirmed', x['reusable_verified_facts'])
        self.assertIn('cloudflare_model_successful_before', x['reusable_verified_facts'])
        self.assertFalse(x['provider_dispatch_authorized'])
        self.assertFalse(x['last_consumed_generation_gate_open'])
        self.assertEqual(x['image_requests'], 0)

    def test_historic_evidence_is_not_a_live_pass_even_with_open_gate_bits(self):
        g = dict(self.gate, privacy_verified=True, free_hard_cap_verified=True, quota_verified=True)
        x = summarize(self.facts, g)
        self.assertTrue(x['last_consumed_generation_gate_open'])
        self.assertFalse(x['provider_dispatch_authorized'])
        self.assertEqual(x['external_cost_usd'], 0)

    def test_no_forged_fact_or_missing_source(self):
        f = copy.deepcopy(self.facts)
        f['verified_reusable_facts'][0]['value'] = False
        with self.assertRaises(CheckpointError):
            summarize(f, self.gate)
        f = copy.deepcopy(self.facts)
        f['verified_reusable_facts'][0]['evidence'] = ''
        with self.assertRaises(CheckpointError):
            summarize(f, self.gate)
        f = copy.deepcopy(self.facts)
        f['verified_reusable_facts'][0]['key'] = 'invented'
        with self.assertRaises(CheckpointError):
            summarize(f, self.gate)

    def test_artistic_brief_locked_to_actual_ep_p07_scene(self):
        scene = json.loads((ROOT/'episodes/berakhot-01-01/scene-prologue-v02.json').read_text())
        shot = next(x for x in scene['shots'] if x['id'] == 'EP-P07')
        self.assertEqual((shot['start_frame'],shot['end_frame']),(840,1008))
        self.assertEqual(shot['blocking']['time_of_day'],'dawn')
        self.assertEqual(shot['blocking']['positions'],{'elder':'screen-left','younger':'screen-right'})
        self.assertFalse(shot['asset']['accepted'])
        text = (ROOT/'docs/EP-P07-FIRST-DAWN-IMAGE-BRIEF.md').read_text()
        self.assertIn('REF01_CAST_HERO_PAINTED_MASTER.jpg',text)
        self.assertIn('REF03_TRAVEL_REAR_WIDE.jpg',text)
        self.assertIn('REF04_JOURNEY_WIDE_ORIGINAL.jpg',text)
        self.assertIn('dawn',text.lower())
        self.assertIn('NOT',text)


if __name__ == '__main__':unittest.main()