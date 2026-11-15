"""One-call PRIVATE, read-only owner-Drive archive -> 15-shot routing pipeline.

Runs under an owner-private, authenticated host: pass the existing vetted Drive
client with metadata/download methods. No credentials, provider, paid API or
Drive writes are imported. Public GitHub Actions MUST NOT fetch owner artwork.
"""
from __future__ import annotations

import os
from pathlib import Path

from tools.scene_factory import SceneBlocked, load, within
from tools.scene_production_packet import build_packet
from tools.scene_cloudflare_spec_adapter import compile_previews
from tools.scene_reference_routing import build_reference_plan, summarize
from tools.scene_owner_archive_fetch import fetch_archive, safe_status


class OwnerPrivateSceneBlocked(ValueError):
    pass


def prepare_owner_private_scene(*, locator, drive, project_root, legacy_template):
    """Verify owner archive & route 15 dawn shots; never prepare/submit model.

    Caller supplies a trusted authenticated read-only Drive client and a
    private locator already retrieved through an owner's connected app.
    Returns a PRIVATE review-only plan and a safe public summary. Must not run
    on a public GitHub Actions runner, even if a secret is inadvertently set.
    """
    if os.environ.get('GITHUB_ACTIONS', '').lower() == 'true':
        raise OwnerPrivateSceneBlocked('OWNER_REFERENCES_FORBIDDEN_IN_PUBLIC_GITHUB_ACTIONS')
    root = Path(project_root).resolve()
    if not root.is_dir():
        raise OwnerPrivateSceneBlocked('OWNER_PRIVATE_PROJECT_ROOT_MISSING')
    template = Path(legacy_template).resolve()
    if not template.is_file() or template.is_symlink():
        raise OwnerPrivateSceneBlocked('OWNER_PINNED_LEGACY_TEMPLATE_MISSING')
    if not isinstance(locator, dict):
        raise OwnerPrivateSceneBlocked('OWNER_PRIVATE_LOCATOR_REQUIRED')

    # Read-only exact owner Drive ID fetch + pinned SHA cache; never search.
    fetched = fetch_archive(locator, drive, root / 'private-media')
    scene = load(within(root, 'episodes/berakhot-01-01/scene-prologue-v02.json'))
    bible = load(within(root, scene['bible']['path']))
    packet = build_packet(scene, bible, root)
    preview = compile_previews(packet, load(template), root)
    # The legacy OPN references (if missing) remain separate blockers; the
    # owner reference registry is never passed into model conditioning.
    plan = build_reference_plan(packet, preview, fetched['archive_path'], root,
                                restore=True)
    if (len(plan['jobs']) != 15 or plan.get('provider_calls') != 0 or
        plan.get('provider_dispatch_authorized') is not False or
        plan['visual_reference_master']['routed_shots'] != 15 or
        plan['visual_reference_master']['independent_shot_images_generated'] != 0):
        raise OwnerPrivateSceneBlocked('OWNER_PRIVATE_PLAN_NOT_CLOSED')
    report = summarize(plan)
    report['archive_fetch'] = safe_status(fetched)
    report['legacy_reference_status'] = list(preview['reference_status'])
    report['storage_scope'] = 'OWNER_PRIVATE_ONLY_NOT_PUBLIC_CI'
    report['rights_for_synthesis'] = 'NOT_EVALUATED'
    report['production_approved'] = False
    return {'private_review_plan': plan, 'safe_summary': report}


def _git_blob_sha(raw):
    """Verify an immutable Git blob independently of the moving branch head."""
    import hashlib
    return hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest()


PINNED_LEGACY_SHA = '80ba1559b785855a1f9f4cbd90083fd0228eec96'
PINNED_LEGACY_DRIVE_BLOB = 'a366426aba26874e72cc44463deaf55147ea97ee'


class PinnedReadOnlyDriveProcess:
    """Reuse the historic, reviewed Google Drive client without copying OAuth.

    Its code runs in an isolated subprocess in the exact checked-out commit.
    Only Drive.metadata and Drive.download are invoked. No writes, no provider.
    This adapter is meant for an OWNER PRIVATE computer/service, never Actions.
    """

    def __init__(self, runtime_root):
        import subprocess
        root = Path(runtime_root).resolve()
        source = root / 'tools/private_drive_runtime.py'
        if source.is_symlink() or not source.is_file() or _git_blob_sha(source.read_bytes()) != PINNED_LEGACY_DRIVE_BLOB:
            raise OwnerPrivateSceneBlocked('OWNER_PINNED_DRIVE_SOURCE_MISMATCH')
        try:
            head = subprocess.run(['git','rev-parse','HEAD'],cwd=root,capture_output=True,
                                  timeout=8,check=True).stdout.decode().strip()
            dirty = subprocess.run(['git','status','--porcelain','--untracked-files=no'],
                                   cwd=root,capture_output=True,timeout=8,check=True).stdout
        except (OSError,subprocess.SubprocessError):
            raise OwnerPrivateSceneBlocked('OWNER_PINNED_RUNTIME_GIT_UNVERIFIED') from None
        if head != PINNED_LEGACY_SHA or dirty:
            raise OwnerPrivateSceneBlocked('OWNER_PINNED_RUNTIME_COMMIT_OR_WORKTREE_CHANGED')
        if not os.environ.get('MISHNAH_DRIVE_OAUTH_JSON'):
            raise OwnerPrivateSceneBlocked('OWNER_EXISTING_DRIVE_OAUTH_NOT_AVAILABLE')
        self.root = root

    def _request(self, kind, file_id):
        import subprocess
        import sys
        from tools.scene_owner_archive_fetch import FILE_ID
        if kind not in ('metadata','download') or not isinstance(file_id,str) or not FILE_ID.fullmatch(file_id):
            raise OwnerPrivateSceneBlocked('OWNER_READ_OPERATION_NOT_ALLOWLISTED')
        script = ("import json,os,sys;sys.path.insert(0,os.getcwd());"
                  "from tools.private_drive_runtime import Drive;"
                  "d=Drive();d.login();"
                  "raw=d.metadata(sys.argv[2]) if sys.argv[1]=='metadata' else d.download(sys.argv[2]);"
                  "sys.stdout.buffer.write(json.dumps(raw).encode('utf-8') if sys.argv[1]=='metadata' else raw)")
        try:
            p=subprocess.run([sys.executable,'-I','-c',script,kind,file_id],cwd=self.root,
                             stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,
                             timeout=70,check=True)
        except (OSError,subprocess.SubprocessError):
            raise OwnerPrivateSceneBlocked('OWNER_DRIVE_READ_FAILED_NO_RETRY') from None
        if len(p.stdout)>64*1024*1024:
            raise OwnerPrivateSceneBlocked('OWNER_DRIVE_READ_SIZE_EXCEEDED')
        if kind=='download':
            return p.stdout
        try:
            import json
            obj=json.loads(p.stdout)
            if not isinstance(obj,dict):raise ValueError()
            return obj
        except (ValueError,UnicodeDecodeError):
            raise OwnerPrivateSceneBlocked('OWNER_DRIVE_METADATA_INVALID') from None

    def metadata(self,file_id):
        return self._request('metadata',file_id)

    def download(self,file_id):
        return self._request('download',file_id)


def persist_private_plan(plan, project_root):
    """Save a content-addressed review plan in ignored private-media/, never Git."""
    import hashlib
    import json
    root=Path(project_root).resolve()
    private=root/'private-media'
    if not private.is_dir() or private.is_symlink():
        raise OwnerPrivateSceneBlocked('OWNER_PRIVATE_PLAN_FOLDER_UNSAFE')
    raw=json.dumps(plan,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()
    sha=hashlib.sha256(raw).hexdigest()
    target=private/('owner-scene-reference-plan-'+sha+'.json')
    if target.is_symlink():
        raise OwnerPrivateSceneBlocked('OWNER_PRIVATE_PLAN_SYMLINK_FORBIDDEN')
    if target.exists():
        if not target.is_file() or target.read_bytes()!=raw:
            raise OwnerPrivateSceneBlocked('OWNER_PRIVATE_PLAN_CACHE_CHANGED')
        return {'plan_sha256':sha,'cache_hit':True,'stored_privately':True}
    fd=None
    try:
        fd=os.open(target,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
        with os.fdopen(fd,'wb') as f:
            fd=None
            f.write(raw)
            f.flush()
            os.fsync(f.fileno())
    except FileExistsError:
        raise OwnerPrivateSceneBlocked('OWNER_PRIVATE_PLAN_CONCURRENT_CHANGE') from None
    finally:
        if fd is not None:os.close(fd)
    return {'plan_sha256':sha,'cache_hit':False,'stored_privately':True}


def main(argv=None):
    """One private command, using EXISTING OAuth and PINNED legacy Drive code."""
    import argparse
    import json
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root',required=True)
    p.add_argument('--legacy-runtime',required=True)
    p.add_argument('--legacy-template',required=True)
    p.add_argument('--private-locator',required=True)
    args=p.parse_args(argv)
    try:
        if os.environ.get('GITHUB_ACTIONS','').lower()=='true':
            raise OwnerPrivateSceneBlocked('OWNER_REFERENCES_FORBIDDEN_IN_PUBLIC_GITHUB_ACTIONS')
        locator_path=Path(args.private_locator).resolve()
        if not locator_path.is_file() or locator_path.is_symlink() or locator_path.stat().st_size>64000:
            raise OwnerPrivateSceneBlocked('OWNER_PRIVATE_LOCATOR_MISSING_OR_UNSAFE')
        # Do not print the locator's IDs or any private media paths.
        locator=json.loads(locator_path.read_text(encoding='utf-8'))
        drive=PinnedReadOnlyDriveProcess(args.legacy_runtime)
        result=prepare_owner_private_scene(locator=locator,drive=drive,
                      project_root=args.root,legacy_template=args.legacy_template)
        saved=persist_private_plan(result['private_review_plan'],args.root)
        print(json.dumps(dict(result['safe_summary'],private_plan=saved),ensure_ascii=False,sort_keys=True))
        return 0
    except Exception as e:
        # No exception messages from network/OAuth/trusted process to stdout.
        kind=(str(e) if isinstance(e,OwnerPrivateSceneBlocked)
              else type(e).__name__)
        print(json.dumps({'status':'BLOCKED','reason':kind,
                          'provider_calls':0,'new_images_generated':0,
                          'generation_authorized':False},sort_keys=True))
        return 2


if __name__=='__main__':
    raise SystemExit(main())