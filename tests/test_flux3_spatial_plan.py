import copy
import json
from pathlib import Path
import tempfile
import unittest

from tools.flux3_spatial_plan import export_plan, validate, write_private_boxes

PATH = Path(__file__).resolve().parents[1] / 'episodes/berakhot-01-01/flux3-opn02-layout.json'


class Flux3LayoutTest(unittest.TestCase):
    def setUp(self):
        self.spec = json.loads(PATH.read_text(encoding='utf-8'))

    def test_offline_output_is_vendor_compatible_and_blocked(self):
        plan = export_plan(self.spec)
        self.assertEqual([box['id'] for box in plan['vendor_cli_boxes']],
                         ['older_traveler', 'younger_traveler', 'distant_village'])
        self.assertEqual(plan['provider_requests'], 0)
        self.assertEqual(plan['external_spend_initiated_usd'], 0)
        self.assertIsNone(plan['generated_image'])
        self.assertFalse(plan['accepted'])
        self.assertTrue(plan['blocked'])
        self.assertEqual(plan['model'], 'black-forest-labs/flux-3-image-klein')

    def test_character_heights_are_thirty_percent(self):
        for box in validate(self.spec)[:2]:
            self.assertAlmostEqual((box['bbox'][2] - box['bbox'][0])*576, 172.8)

    def test_rejects_invalid_and_nonfinite_coordinates(self):
        for val in (-.01, 1.01, float('nan'), float('inf'), '0.6'):
            doc = copy.deepcopy(self.spec)
            doc['boxes'][0]['bbox'][0] = val
            with self.subTest(value=val), self.assertRaises(ValueError): validate(doc)

    def test_rejects_oversized_people_and_swapped_positions(self):
        for key, value in [('oversize', [0.10, .37, .90, .43]),
                           ('swapped', [0.60, .75, .90, .81])]:
            doc = copy.deepcopy(self.spec)
            doc['boxes'][0]['bbox'] = value
            with self.subTest(kind=key), self.assertRaises(ValueError): validate(doc)

    def test_rejects_duplicate_id_and_too_large_village(self):
        for kind in ['duplicate', 'village']:
            doc = copy.deepcopy(self.spec)
            if kind == 'duplicate': doc['boxes'][1]['id'] = 'older_traveler'
            else: doc['boxes'][2]['bbox'] = [.1, .68, .43, .77]
            with self.subTest(kind=kind), self.assertRaises(ValueError): validate(doc)

    def test_forbids_paid_api_or_generation_approval(self):
        for key, value in [('api_mode', 'cloudflare_paid'),
                           ('external_spend_limit_usd', 1),
                           ('generation_authorized', True),
                           ('release_authorized', True)]:
            doc = copy.deepcopy(self.spec)
            doc[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError): validate(doc)

    def test_no_private_reference_urls_or_secrets_in_public_spec(self):
        for key in ['private_reference', 'image_data', 'credentials']:
            doc = copy.deepcopy(self.spec)
            doc[key] = 'secret'
            with self.subTest(key=key), self.assertRaises(ValueError): validate(doc)

    def test_export_is_private_only_and_atomically_writes_vendor_boxes(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ValueError):
                write_private_boxes(directory, 'episodes/public.json', self.spec['boxes'])
            target = write_private_boxes(directory, 'private-media/studio/boxes.json', self.spec['boxes'])
            self.assertEqual(json.loads(Path(target).read_text(encoding='utf-8')), self.spec['boxes'])
            self.assertTrue(Path(target).is_file())


if __name__ == '__main__':
    unittest.main()
