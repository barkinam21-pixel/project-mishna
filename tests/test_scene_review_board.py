import hashlib
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from tools.scene_review_board import render_board
from tools.scene_pack_preflight import EXPECTED_IDS


def dummy_report():
    return {"shots": [{"shot_id": sid, "key": "k" + sid,
                       "status": "BLOCKED_MISSING_PRIVATE_INPUT"} for sid in EXPECTED_IDS]}


class SceneReviewBoardTests(unittest.TestCase):
    def test_missing_images_make_one_board_without_claiming_approval(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            info = render_board(dummy_report(), {}, root, "private-media/review/board.png")
            self.assertEqual(info["placeholders"], 7)
            self.assertEqual(info["provider_calls"], 0)
            self.assertFalse(info["approval_granted"])
            with Image.open(root / info["output"]) as im:
                self.assertEqual(im.size, (960, 1314))

    def test_only_verified_local_media_is_displayed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            image = root / "private-media" / "one.png"
            image.parent.mkdir(parents=True)
            Image.new("RGB", (320, 180), "blue").save(image)
            digest = hashlib.sha256(image.read_bytes()).hexdigest()
            state = {"entries": {"kOPN02": {"status": "CANDIDATE",
                "path": "private-media/one.png", "sha256": digest}}}
            info = render_board(dummy_report(), state, root, "private-media/review/board.png")
            self.assertEqual(info["images_shown"], ["OPN02"])
            self.assertEqual(info["placeholders"], 6)
            self.assertEqual(state["entries"]["kOPN02"]["status"], "CANDIDATE")
            image.write_bytes(b"tampered")
            info2 = render_board(dummy_report(), state, root, "private-media/review/second.png")
            self.assertEqual(info2["images_shown"], [])

    def test_refuses_public_output_or_unknown_shots(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with self.assertRaisesRegex(ValueError, "private-media"):
                render_board(dummy_report(), {}, root, "build/board.png")
            r = dummy_report()
            r["shots"] = r["shots"][:-1]
            with self.assertRaisesRegex(ValueError, "Unexpected"):
                render_board(r, {}, root, "private-media/board.png")


    def test_recovered_unapproved_candidate_shows_only_if_hash_verified(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            candidate = root / "private-media" / "recovered-opn02.png"
            candidate.parent.mkdir(parents=True)
            Image.new("RGB", (320, 180), "orange").save(candidate)
            digest = hashlib.sha256(candidate.read_bytes()).hexdigest()
            entry = {"OPN02": {"status": "CANDIDATE",
                    "path": "private-media/recovered-opn02.png", "sha256": digest}}
            result = render_board(dummy_report(), {}, root,
                                  "private-media/review/first.png", entry)
            self.assertEqual(result["images_shown"], ["OPN02"])
            self.assertEqual(result["placeholders"], 6)
            self.assertFalse(result["approval_granted"])
            with self.assertRaisesRegex(ValueError, "private-media"):
                render_board(dummy_report(), {}, root,
                             "private-media/review/unsafe.png",
                             {"OPN02": dict(entry["OPN02"], path="outside.png")})
            entry["OPN02"]["sha256"] = "0" * 64
            blocked = render_board(dummy_report(), {}, root,
                                   "private-media/review/blocked.png", entry)
            self.assertEqual(blocked["images_shown"], [])
            self.assertFalse(blocked["approval_granted"])

if __name__ == "__main__":
    unittest.main()
