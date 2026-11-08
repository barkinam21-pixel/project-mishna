"""Restore one owner-private unapproved OPN02 candidate and review it offline.

No API calls, generation, automatic approvals, manifest mutation, or publication.
All archive members and hashes are validated before any private file is written.
"""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import stat
import tempfile
import zipfile

IMAGE = "private-media/introduction/OPN02-recovered.png"
CANDIDATES = "private-media/scene-review/verified-candidates.json"
EXPECTED_ARCHIVE_SHA256 = "370d9da290c0204b94ba72a0d4e7a5873abc9b75a44599fca2421ee111ebf0a2"
EXPECTED_IMAGE_SHA256 = "e144d087fd438892725e5409096b51cf5cc1f3b82010b9a8f44acd2dbde92552"
MAX_IMAGE_BYTES = 12 * 1024 * 1024
MAX_ARCHIVE_BYTES = 15 * 1024 * 1024


def sha_bytes(value):
    return hashlib.sha256(value).hexdigest()


def private_path(root, relative):
    root = Path(root).resolve()
    path = (root / relative).resolve()
    if not path.is_relative_to(root) or "private-media" not in path.relative_to(root).parts:
        raise ValueError("Private candidate path must be inside private-media")
    return path


def unpack_verified_bundle(archive, root, *, expected_archive_sha256=EXPECTED_ARCHIVE_SHA256,
                           expected_image_sha256=EXPECTED_IMAGE_SHA256):
    """Install only exact verified files, never overwriting different private bytes."""
    root = Path(root).resolve()
    archive = Path(archive)
    if archive.stat().st_size > MAX_ARCHIVE_BYTES:
        raise ValueError("Archive too large")
    raw = archive.read_bytes()
    if sha_bytes(raw) != expected_archive_sha256:
        raise ValueError("PRIVATE_BUNDLE_HASH_MISMATCH")
    expected_names = {IMAGE, CANDIDATES}
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        members = z.infolist()
        if len(members) != 2 or {item.filename for item in members} != expected_names:
            raise ValueError("Unexpected private bundle layout")
        for item in members:
            if (item.is_dir() or item.flag_bits & 0x1 or
                    stat.S_IFMT(item.external_attr >> 16) == stat.S_IFLNK or
                    item.file_size > MAX_IMAGE_BYTES):
                raise ValueError("Unsafe private bundle member")
            private_path(root, item.filename)
        blob = z.read(IMAGE)
        manifest_bytes = z.read(CANDIDATES)
    if sha_bytes(blob) != expected_image_sha256:
        raise ValueError("PRIVATE_IMAGE_HASH_MISMATCH")
    try:
        manifest = json.loads(manifest_bytes.decode("utf-8"))
    except (ValueError, UnicodeError) as exc:
        raise ValueError("Malformed private candidate manifest") from exc
    if not isinstance(manifest, dict) or set(manifest) != {"OPN02"}:
        raise ValueError("Only OPN02 may be restored")
    candidate = manifest["OPN02"]
    if not isinstance(candidate, dict) or not (candidate.get("status") == "CANDIDATE" and
            candidate.get("accepted") is False and candidate.get("path") == IMAGE and
            candidate.get("sha256") == expected_image_sha256):
        raise ValueError("Candidate metadata must remain unapproved")
    from PIL import Image as PillowImage
    try:
        with PillowImage.open(io.BytesIO(blob)) as image:
            image.verify()
            if image.format != "PNG":
                raise ValueError("Candidate must be PNG")
            dimensions = list(image.size)
    except (OSError, SyntaxError) as exc:
        raise ValueError("Invalid private candidate image") from exc
    if dimensions != [1024, 576]:
        raise ValueError("Unexpected private candidate dimensions")
    payload = {IMAGE: blob, CANDIDATES: manifest_bytes}
    # Preflight all potential conflicts: neither file is altered on mismatch.
    for name, data in payload.items():
        dest = private_path(root, name)
        if dest.exists() and (not dest.is_file() or dest.read_bytes() != data):
            raise ValueError("EXISTING_PRIVATE_FILE_CONFLICT: " + name)
    reused = []
    for name, data in payload.items():
        dest = private_path(root, name)
        if dest.is_file():
            reused.append(name)
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.parent.chmod(0o700)
        fd, tmp = tempfile.mkstemp(dir=dest.parent, prefix=".verified-", suffix=".tmp")
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(data)
            os.chmod(tmp, 0o600)
            os.replace(tmp, dest)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)
    return {"status": "RESTORED_UNAPPROVED_CANDIDATE", "candidate": "OPN02",
            "verified_sha256": expected_image_sha256, "reused": reused,
            "accepted": False, "rights_approved": False, "provider_calls": 0}


def review_private_scene(root, bundle):
    root = Path(root).resolve()
    receipt = unpack_verified_bundle(bundle, root)
    from tools.scene_pack_preflight import build
    from tools.scene_review_board import render_board
    report = build(root)
    state_path = private_path(root, "private-media/director-images/state.json")
    state = json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else {}
    candidates = json.loads(private_path(root, CANDIDATES).read_text(encoding="utf-8"))
    board_path = "private-media/scene-review/scene-contact-sheet.png"
    board = render_board(report, state, root, board_path, candidates)
    if board["approval_granted"] or "OPN02" not in board["images_shown"]:
        raise ValueError("Review failed to display verified unapproved OPN02")
    return {**receipt, "review_board": board, "film_ready": False,
            "note": "Candidate view only; existing film manifest and approvals unchanged"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bundle", help="Owner-private ZIP file, never a public URL")
    parser.add_argument("--root", default=".")
    parser.add_argument("--restore-only", action="store_true",
                        help="Offline restore without scene imports")
    args = parser.parse_args()
    result = (unpack_verified_bundle(args.bundle, args.root) if args.restore_only else
              review_private_scene(args.root, args.bundle))
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
