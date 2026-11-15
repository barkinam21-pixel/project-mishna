"""Owner-scoped, read-only Drive-to-private-cache bridge for Mishnah reference ZIP.

This module does not instantiate Drive or authenticate: caller injects the existing
PINNED runtime's owner-only Drive client (metadata and download). This keeps
OAuth, scopes and network behavior in the already-reviewed implementation. No
inference, uploaded bytes, public artifacts, permission or Drive mutations.
"""
from __future__ import annotations

import os
import re
import tempfile
from pathlib import Path

from tools.scene_reference_archive import BUNDLE_FILENAME, BUNDLE_SHA256, validate_bytes

FILE_ID = re.compile(r'^[A-Za-z0-9_-]{10,200}$')
CACHE_NAME = 'owner-reference-master-20261115.zip'
MAX_BUNDLE_BYTES = 64 * 1024 * 1024


class OwnerArchiveFetchBlocked(ValueError):
    pass


def _resolve_private_locator(locator):
    """Locate the ONE trusted ZIP by stable Drive ID; never search by name."""
    if not isinstance(locator, dict):
        raise OwnerArchiveFetchBlocked('OWNER_ARCHIVE_LOCATOR_INVALID')
    if (locator.get('schema_version') != 1
        or locator.get('privacy') != 'OWNER_PRIVATE_ONLY_NO_PUBLICATION'
        or locator.get('project') != 'barkinam21-pixel/project-mishna'
        or locator.get('bundle_filename') != BUNDLE_FILENAME
        or locator.get('bundle_sha256') != BUNDLE_SHA256
        or locator.get('folder_name') != '00-PRIVATE-VISUAL-REFERENCE-MASTER-20261115'
        or locator.get('lookup_mode') != 'use exact Drive file IDs; verify bytes SHA; no fuzzy search and no live inference'):
        raise OwnerArchiveFetchBlocked('OWNER_ARCHIVE_LOCATOR_SCOPE_CHANGED')
    folder_id = locator.get('folder_id')
    files = locator.get('files')
    if (not isinstance(folder_id, str) or not FILE_ID.fullmatch(folder_id)
        or not isinstance(files, list) or len(files) != 14):
        raise OwnerArchiveFetchBlocked('OWNER_ARCHIVE_LOCATOR_FILES_INVALID')
    ids, names, matches = set(), set(), []
    for item in files:
        if not isinstance(item, dict) or set(item) != {'filename', 'sha256', 'drive_file_id'}:
            raise OwnerArchiveFetchBlocked('OWNER_ARCHIVE_FILE_ENTRY_INVALID')
        name, digest, drive_id = item['filename'], item['sha256'], item['drive_file_id']
        if (not isinstance(name, str) or not isinstance(digest, str)
            or not re.fullmatch(r'[a-f0-9]{64}', digest)
            or not isinstance(drive_id, str) or not FILE_ID.fullmatch(drive_id)
            or drive_id == folder_id or name in names or drive_id in ids):
            raise OwnerArchiveFetchBlocked('OWNER_ARCHIVE_FILE_ENTRY_INVALID')
        names.add(name); ids.add(drive_id)
        if name == BUNDLE_FILENAME:
            matches.append(item)
    if len(matches) != 1 or matches[0]['sha256'] != BUNDLE_SHA256:
        raise OwnerArchiveFetchBlocked('OWNER_ARCHIVE_ZIP_NOT_PINNED')
    return folder_id, matches[0]['drive_file_id']


def _owner_only(meta, expected_id, expected_mime):
    """Recheck exact owner-only metadata, independent of Drive client internals."""
    if (not isinstance(meta, dict) or meta.get('id') != expected_id
        or meta.get('shared') is not False
        or not isinstance(meta.get('permissions'), list)
        or len(meta['permissions']) != 1
        or meta['permissions'][0].get('type') != 'user'
        or meta['permissions'][0].get('role') != 'owner'
        or meta.get('mimeType') != expected_mime):
        raise OwnerArchiveFetchBlocked('OWNER_ARCHIVE_DRIVE_NOT_PRIVATE_OR_WRONG_TYPE')


def fetch_archive(locator, drive, private_root):
    """Download exact pinned bytes once, verify first, atomically cache privately.

    Calls only the existing Drive.metadata and Drive.download READ methods. The
    client must be owner-scoped and previously authenticated by the caller.
    Returns local path for the existing offline build_reference_plan pipeline.
    Existing valid cache is reusable, corrupted cache is a hard stop; never clobber.
    """
    folder_id, bundle_id = _resolve_private_locator(locator)
    raw_root = Path(private_root).absolute()
    if raw_root.name != 'private-media' or raw_root.is_symlink() or raw_root.parent.is_symlink():
        raise OwnerArchiveFetchBlocked('OWNER_ARCHIVE_DESTINATION_NOT_PRIVATE')
    root = raw_root.resolve()
    if root.name != 'private-media' or root.is_symlink() or root.parent.is_symlink():
        raise OwnerArchiveFetchBlocked('OWNER_ARCHIVE_DESTINATION_NOT_PRIVATE')
    target = root / CACHE_NAME
    if root.exists() and not root.is_dir():
        raise OwnerArchiveFetchBlocked('OWNER_ARCHIVE_DESTINATION_INVALID')
    if target.is_symlink():
        raise OwnerArchiveFetchBlocked('OWNER_ARCHIVE_CACHE_SYMLINK_FORBIDDEN')
    if target.exists():
        if not target.is_file():
            raise OwnerArchiveFetchBlocked('OWNER_ARCHIVE_CACHE_NOT_FILE')
        try:
            validated = validate_bytes(target.read_bytes())
        except Exception as e:
            raise OwnerArchiveFetchBlocked('OWNER_ARCHIVE_CACHE_TAMPERED') from e
        return {'status': 'OWNER_PRIVATE_REFERENCE_ARCHIVE_VERIFIED',
                'cache_hit': True, 'bundle_sha256': validated['bundle_sha256'],
                'archive_path': str(target), 'remote_reads': 0,
                'model_calls': 0, 'remote_writes': 0,
                'generation_authorized': False}
    try:
        _owner_only(drive.metadata(folder_id), folder_id, 'application/vnd.google-apps.folder')
        _owner_only(drive.metadata(bundle_id), bundle_id, 'application/zip')
    except OwnerArchiveFetchBlocked:
        raise
    except Exception as e:
        raise OwnerArchiveFetchBlocked('OWNER_ARCHIVE_PRIVATE_METADATA_FAILED') from e
    try:
        blob = drive.download(bundle_id)
    except Exception as e:
        raise OwnerArchiveFetchBlocked('OWNER_ARCHIVE_DOWNLOAD_FAILED_NO_RETRY') from e
    if not isinstance(blob, bytes) or len(blob) > MAX_BUNDLE_BYTES:
        raise OwnerArchiveFetchBlocked('OWNER_ARCHIVE_BUNDLE_SIZE_INVALID')
    try:
        verified = validate_bytes(blob)
    except Exception as e:
        raise OwnerArchiveFetchBlocked('OWNER_ARCHIVE_BYTES_FAILED_PINNED_VERIFICATION') from e
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    if root.is_symlink() or target.exists():
        raise OwnerArchiveFetchBlocked('OWNER_ARCHIVE_CACHE_CONCURRENT_CHANGE')
    stage = None
    try:
        with tempfile.NamedTemporaryFile(prefix='.owner-reference-staging-', suffix='.zip',
                                         dir=root, delete=False) as temp:
            stage = Path(temp.name)
            os.chmod(stage, 0o600)
            temp.write(blob)
            temp.flush()
            os.fsync(temp.fileno())
        if target.exists() or target.is_symlink():
            raise OwnerArchiveFetchBlocked('OWNER_ARCHIVE_CACHE_CONCURRENT_CHANGE')
        os.link(stage, target)
    except FileExistsError as e:
        raise OwnerArchiveFetchBlocked('OWNER_ARCHIVE_CACHE_CONCURRENT_CHANGE') from e
    finally:
        if stage is not None:
            stage.unlink(missing_ok=True)
    return {'status': 'OWNER_PRIVATE_REFERENCE_ARCHIVE_VERIFIED',
            'cache_hit': False, 'bundle_sha256': verified['bundle_sha256'],
            'archive_path': str(target), 'remote_reads': 1,
            'model_calls': 0, 'remote_writes': 0,
            'generation_authorized': False}


def safe_status(result):
    """Safe to print in private run logs (without IDs, paths or image content)."""
    return {k: result[k] for k in ('status','cache_hit','bundle_sha256',
                                 'remote_reads','model_calls','remote_writes',
                                 'generation_authorized')}
