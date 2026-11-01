"""Block accidental public upload-artifact of unencrypted media by CI.

The public GitHub repository can expose artifacts to readers. Synthetic
technical samples are still not public deliverables, so retain QA metadata
without uploading MP4/PNG/WAV/JPEG/WEBP. Encrypted .bin is permitted.
"""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github/workflows"
MEDIA_RE = re.compile(r"(?i)\.(?:mp4|mov|png|jpe?g|webp|wav|flac)(?:\s|$)")


def artifact_upload_file_entries(path: Path):
    lines = path.read_text(encoding="utf-8").splitlines()
    for index, line in enumerate(lines):
        if "uses: actions/upload-artifact@" not in line:
            continue
        # Scan only its path entries, stopping at next step/field.
        for following in lines[index + 1:]:
            clean = following.strip()
            if clean.startswith("- name:") or clean.startswith("- uses:"):
                break
            if clean.startswith("path:"):
                inline = clean.split("path:", 1)[1].strip()
                if inline and inline != "|":
                    yield inline
                continue
            if clean.startswith("if-no-files-found:"):
                break
            if clean.startswith(("build/", "${{", "episodes/", "security/", "./")):
                yield clean


class PublicArtifactSafetyTests(unittest.TestCase):
    def test_no_raw_media_path_in_public_upload_artifact_steps(self):
        workflows = list(WORKFLOWS.glob("*.yml")) + list(WORKFLOWS.glob("*.yaml"))
        self.assertTrue(workflows)
        for workflow in workflows:
            for candidate in artifact_upload_file_entries(workflow):
                with self.subTest(workflow=workflow.name, path=candidate):
                    self.assertNotRegex(candidate, MEDIA_RE)

    def test_studio_sync_report_does_not_upload_mp4(self):
        workflow = WORKFLOWS / "studio-check.yml"
        paths = list(artifact_upload_file_entries(workflow))
        self.assertIn("build/sync-probe/sync-qa.json", paths)
        self.assertIn("build/sync-probe/sync-test.srt", paths)
        self.assertNotIn("build/sync-probe/sync-test.mp4", paths)

    def test_fal_workflow_uploads_encrypted_bin_only(self):
        workflow = WORKFLOWS / "fal-private-sh01.yml"
        paths = list(artifact_upload_file_entries(workflow))
        self.assertTrue(paths)
        self.assertTrue(all(path.endswith(".bin") for path in paths))


    def test_legacy_manual_paid_workflows_are_inert(self):
        # Historical workflows must remain viewable for audit, but cannot charge.
        for name in ("fal-private-sh01.yml", "fal-private-opn01.yml"):
            with self.subTest(name=name):
                body = (WORKFLOWS / name).read_text(encoding="utf-8")
                self.assertIn("if: ${{ false }}", body)
                self.assertNotIn("if: ${{ inputs.confirm_paid == 'YES' }}", body)

    def test_retired_sh09_does_not_redirect_to_paid_sh01(self):
        body = (WORKFLOWS / "fal-sh09-manual.yml").read_text(encoding="utf-8")
        self.assertIn("fal-private-opn01-single-use-push.yml", body)
        self.assertNotIn("Use fal-private-sh01.yml", body)


if __name__ == "__main__":
    unittest.main()
