"""Restore the exact owner-private, eight-image Mishnah reference archive locally.

No network/provider upload, no image generation, no automatic approval.
The former two-image intake remains supported separately.
"""
import hashlib
import io
import json
from pathlib import Path
import zipfile

from PIL import Image

ARCHIVE_SHA256 = "1394a144f2731d229d0a38179aa351a1f6ff37b53c629bf18ba108481c75d3ef"
MASTER = "00_PRIMARY_REFERENCE/a_cinematic_detailed_illustration_in_the_same_rea.png"
BOARD = "00_PRIMARY_REFERENCE/a_cinematic_storyboard_collage_with_four_panels_t.png"
FILE_SHA256 = {
    MASTER: "e1391de34693cf897898a264662e6f4249bfa2f0a7b648c72fad49906da248f3",
    BOARD: "1d3eac22fbaee5f442044cd0f658d2a83f3158888dfa7405b7f7039e40a36bd5",
    "01_ACTIVE_GUIDES/1000139258.jpg": "92c49c0e3f11297703e7d84f630c2a7be771d967bfc00143481a42b18defe8fc",
    "01_ACTIVE_GUIDES/1000140566.jpg": "075df5aa113d874b5e8f6014ab5bc196ba52142e4388e48c966ef4aad4f3d277",
    "01_ACTIVE_GUIDES/1000139263.jpg": "17836ad16adc4b99d2e4e44bf24eafbe02d79dbd04b1129c38ca78f80a1f36f7",
    "01_ACTIVE_GUIDES/1000139262.jpg": "62f3cb6c6427423f3120b2195af8980314409037cc2858787432470bfa83c0cf",
    "01_ACTIVE_GUIDES/1000140597.jpg": "5f47c763270334c45f166cad98ef56a496d0532906d357e7a8b3900effe527f9",
    "01_ACTIVE_GUIDES/1000140603.jpg": "c481d9b9c86d9f92cdcf090ac1293fb85c8de7ec7a890e443619a37a8479d63c",
}


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def private_target(root, rel):
    root = Path(root).resolve()
    if not isinstance(rel, str) or not rel.startswith("private-media/introduction/"):
        raise ValueError("PRIVATE_REFERENCE_PATH_REQUIRED")
    result = (root / rel).resolve()
    if not result.is_relative_to(root / "private-media"):
        raise ValueError("REFERENCE_PATH_OUTSIDE_PRIVATE_ROOT")
    return result


def restore_eight_reference_pack(archive, root, manifest):
    archive = Path(archive)
    if digest(archive.read_bytes()) != ARCHIVE_SHA256:
        raise ValueError("CURATED_ARCHIVE_SHA256_MISMATCH")
    refs = manifest.get("references", [])
    board = manifest.get("direction_board")
    if len(refs) != 1 or not isinstance(board, dict):
        raise ValueError("PRIMARY_REFERENCE_MANIFEST_INVALID")
    if refs[0].get("sha256") != FILE_SHA256[MASTER] or board.get("sha256") != FILE_SHA256[BOARD]:
        raise ValueError("PRIMARY_REFERENCE_MANIFEST_HASH_MISMATCH")
    if refs[0].get("synthesis_rights_confirmed") is not True or not refs[0].get("rights_uri"):
        raise ValueError("OWNER_PRIVATE_PRESERVATION_RIGHTS_REQUIRED")
    source_paths = {
        MASTER: refs[0]["path"],
        BOARD: board["path"],
    }
    for path in FILE_SHA256:
        if path not in source_paths:
            source_paths[path] = "private-media/introduction/active-guides/" + Path(path).name
    prepared = []
    with zipfile.ZipFile(archive) as z:
        info = z.infolist()
        if len(info) != 10 or {i.filename for i in info} != set(FILE_SHA256) | {"manifest.json", "README.txt"}:
            raise ValueError("CURATED_ARCHIVE_MEMBERS_INVALID")
        if any(i.is_dir() or ((i.external_attr >> 16) & 0o170000) == 0o120000 or
               i.file_size > 12 * 1024 * 1024 for i in info):
            raise ValueError("UNSAFE_ARCHIVE_ENTRY")
        record = json.loads(z.read("manifest.json"))
        rows = record.get("records", [])
        if (record.get("included_reference_count") != 8 or
                record.get("status") != "PRIVATE_REFERENCE_ONLY_NOT_APPROVED_FOR_PROVIDER_UPLOAD" or
                not isinstance(rows, list) or len(rows) != 8):
            raise ValueError("CURATED_ARCHIVE_RECORD_INVALID")
        by_name = {r.get("archive_path"): r for r in rows if isinstance(r, dict)}
        if set(by_name) != set(FILE_SHA256):
            raise ValueError("CURATED_ARCHIVE_MANIFEST_PATHS_INVALID")
        for name, expected in FILE_SHA256.items():
            if by_name[name].get("sha256") != expected or by_name[name].get("provider_upload_allowed") is not False:
                raise ValueError("CURATED_ARCHIVE_RIGHTS_OR_HASH_INVALID")
            raw = z.read(name)
            if digest(raw) != expected:
                raise ValueError("CURATED_REFERENCE_HASH_MISMATCH")
            with Image.open(io.BytesIO(raw)) as image:
                image.load()
                kind = "PNG" if name.lower().endswith(".png") else "JPEG"
                if image.format != kind:
                    raise ValueError("REFERENCE_EXTENSION_FORMAT_MISMATCH")
                size = list(image.size)
            record_size = [by_name[name].get("width"), by_name[name].get("height")]
            if size != record_size:
                raise ValueError("CURATED_IMAGE_DIMENSION_MISMATCH")
            if name == MASTER and size != refs[0].get("expected_size"):
                raise ValueError("MASTER_DIMENSION_MISMATCH")
            if name == BOARD and size != board.get("dimensions"):
                raise ValueError("BOARD_DIMENSION_MISMATCH")
            target = private_target(root, source_paths[name])
            if target.is_symlink() or (target.exists() and digest(target.read_bytes()) != expected):
                raise ValueError("PRIVATE_REFERENCE_OVERWRITE_BLOCKED")
            prepared.append((target, raw))
    # All members decoded and verified before any private file is created.
    created = 0
    for path, raw in prepared:
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        path.parent.chmod(0o700)
        if not path.exists():
            tmp = path.with_name(path.name + ".restoring")
            if tmp.exists():
                raise ValueError("UNCERTAIN_REFERENCE_RESTORE_STATE")
            try:
                with tmp.open("xb") as f:
                    f.write(raw)
                tmp.chmod(0o600)
                tmp.replace(path)
            finally:
                if tmp.exists():
                    tmp.unlink()
            created += 1
    return {
        "status": "RESTORED_PRIVATE_REFERENCES_ONLY",
        "archive_sha256": ARCHIVE_SHA256,
        "verified_images": len(prepared),
        "created_files": created,
        "provider_upload_allowed": False,
        "generation_authorized": False,
        "public_release_authorized": False,
        "private_paths_only": True,
    }
