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


if __name__ == "__main__":
    unittest.main()
