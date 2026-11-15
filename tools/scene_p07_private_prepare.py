"""One private, read-only Drive-to-P07 conditioning preparation command.

This joins the existing authenticated 15-shot owner pipeline to the already
tested native P07 compiler. It NEVER submits an image, opens policy, or prints
private reference bytes/IDs. The returned provider-shaped draft is NOT a
Cloudflare request and must not be used as one without separate admission.
"""
from __future__ import annotations
import json
import os
from pathlib import Path
from tools.scene_owner_reference_pipeline import (
    OwnerPrivateSceneBlocked, PinnedReadOnlyDriveProcess,
    prepare_owner_private_scene, persist_private_plan,
)
from tools.scene_native_conditioning_preview import draft_conditioning, NativePreviewBlocked


def prepare_p07(*, locator, drive, project_root, legacy_template):
    if os.environ.get('GITHUB_ACTIONS', '').lower() == 'true':
        raise OwnerPrivateSceneBlocked('PRIVATE_P07_FORBIDDEN_IN_PUBLIC_ACTIONS')
    root = Path(project_root).resolve()
    result = prepare_owner_private_scene(
        locator=locator, drive=drive, project_root=root,
        legacy_template=legacy_template)
    plan = result['private_review_plan']
    draft = draft_conditioning(plan, root)
    if (draft['shot_id'] != 'EP-P07'
        or draft['provider_dispatch_authorized'] is not False
        or draft['provider_calls'] != 0
        or draft['rights_for_synthesis'] != 'NOT_EVALUATED'
        or draft['candidate_count'] != 3):
        raise NativePreviewBlocked('P07_DRAFT_UNEXPECTEDLY_EXECUTABLE')
    saved_plan = persist_private_plan(plan, root)
    # Save a private, immutable, SHA-addressed draft for a future rights-scoped
    # admission; no public repository file or logs contain owner reference IDs.
    private = root / 'private-media'
    if not private.is_dir() or private.is_symlink():
        raise OwnerPrivateSceneBlocked('P07_PRIVATE_FOLDER_UNSAFE')
    raw = json.dumps(draft, sort_keys=True, ensure_ascii=False,
                     separators=(',', ':')).encode('utf-8')
    name = 'p07-native-conditioning-' + draft['draft_sha256'] + '.json'
    target = private / name
    if target.is_symlink():
        raise OwnerPrivateSceneBlocked('P07_DRAFT_SYMLINK_FORBIDDEN')
    if target.exists():
        if not target.is_file() or target.read_bytes() != raw:
            raise OwnerPrivateSceneBlocked('P07_DRAFT_CACHE_CHANGED')
        hit = True
    else:
        import tempfile
        stage = None
        try:
            with tempfile.NamedTemporaryFile(
                prefix='.p07-draft-', dir=private, delete=False
            ) as tmp:
                stage = Path(tmp.name)
                os.chmod(stage, 0o600)
                tmp.write(raw)
                tmp.flush()
                os.fsync(tmp.fileno())
            os.link(stage, target)  # atomic, fail on concurrent creation
            hit = False
        except FileExistsError:
            if not target.is_file() or target.is_symlink() or target.read_bytes() != raw:
                raise OwnerPrivateSceneBlocked('P07_DRAFT_CONCURRENT_CHANGE') from None
            hit = True
        finally:
            if stage is not None:
                stage.unlink(missing_ok=True)
    return {
        'status': 'P07_OWNER_PRIVATE_DRAFT_PREPARED_NO_INFERENCE',
        'shot_id': 'EP-P07',
        'draft_sha256': draft['draft_sha256'],
        'reference_count': 3,
        'private_plan_sha256': saved_plan['plan_sha256'],
        'private_draft_cache_hit': hit,
        'provider_calls': 0,
        'generation_authorized': False,
        'rights_for_synthesis': 'NOT_EVALUATED',
        'next': 'REQUEST_SPECIFIC_RIGHTS_AND_DURABLE_PROVIDER_ADMISSION',
    }


def main(argv=None):
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', required=True)
    parser.add_argument('--legacy-runtime', required=True)
    parser.add_argument('--legacy-template', required=True)
    parser.add_argument('--private-locator', required=True)
    args = parser.parse_args(argv)
    try:
        if os.environ.get('GITHUB_ACTIONS', '').lower() == 'true':
            raise OwnerPrivateSceneBlocked('PRIVATE_P07_FORBIDDEN_IN_PUBLIC_ACTIONS')
        path = Path(args.private_locator)
        if path.is_symlink() or not path.is_file() or path.stat().st_size > 64000:
            raise OwnerPrivateSceneBlocked('PRIVATE_LOCATOR_INVALID')
        locator = json.loads(path.read_text(encoding='utf-8'))
        drive = PinnedReadOnlyDriveProcess(args.legacy_runtime)
        report = prepare_p07(locator=locator, drive=drive,
                            project_root=args.root,
                            legacy_template=args.legacy_template)
        print(json.dumps(report, ensure_ascii=False, sort_keys=True))
        return 0
    except Exception as exc:
        reason = str(exc) if isinstance(exc, (OwnerPrivateSceneBlocked, NativePreviewBlocked)) else type(exc).__name__
        print(json.dumps({'status':'BLOCKED','reason':reason,
                          'provider_calls':0,'generation_authorized':False},
                         sort_keys=True))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
