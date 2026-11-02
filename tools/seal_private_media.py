"""Encrypt PRIVATE fal.ai output BEFORE storing in PUBLIC GitHub Actions artifacts.

Envelope: RSA-OAEP-SHA256 wraps a fresh 256-bit AES-GCM key. The authenticated
ciphertext contains a TAR of requested files; no filenames or images are logged
or present in plaintext in the artifact. Public key in the repo; PRIVATE key
must NEVER be uploaded to GitHub. Encryption is offline and costs no credits.

Requires: cryptography. This script contains no fal.ai HTTP or image generation.
"""
from __future__ import annotations
import argparse, io, os, pathlib, struct, tarfile
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

MAGIC=b'MISHNAH-SEALED-V1\x00'
MAX_PLAIN_BYTES=120*1024*1024
MAX_ARTIFACT_BYTES=150*1024*1024


def _safe_name(name:str)->bool:
    p=pathlib.PurePosixPath(name)
    return bool(name and not name.startswith('/') and '\\' not in name
                and '\x00' not in name and '..' not in p.parts and len(p.parts)<=4)


def read_tar(directory: pathlib.Path)->bytes:
    if not directory.is_dir() or directory.is_symlink():
        raise ValueError('Input must be an existing non-symlink private directory')
    sources=sorted(p for p in directory.rglob('*') if p.is_file())
    if not sources:raise ValueError('Private output directory has no files')
    raw=io.BytesIO()
    seen=set()
    with tarfile.open(fileobj=raw,mode='w') as tar:
        for source in sources:
            if source.is_symlink():raise ValueError('Symlink sources are prohibited')
            name=source.relative_to(directory).as_posix()
            if not _safe_name(name) or name in seen:
                raise ValueError('Unsafe or duplicate archived filename')
            seen.add(name)
            if source.stat().st_size>40*1024*1024:
                raise ValueError('One file exceeds private archive limit')
            info=tarfile.TarInfo(name)
            info.size=source.stat().st_size
            info.mode=0o600
            info.mtime=0
            with source.open('rb') as f:tar.addfile(info,f)
            if raw.tell()>MAX_PLAIN_BYTES:
                raise ValueError('Archive too large')
    return raw.getvalue()


def seal(directory:pathlib.Path, pubkey_file:pathlib.Path, result:pathlib.Path):
    if result.exists():raise ValueError('Refusing to overwrite encrypted artifact')
    key=serialization.load_pem_public_key(pubkey_file.read_bytes())
    if not isinstance(key,rsa.RSAPublicKey) or key.key_size<3072:
        raise ValueError('Expected RSA 3072+ public key')
    plain=read_tar(directory)
    secret=os.urandom(32);nonce=os.urandom(12)
    aes=AESGCM(secret)
    ct=aes.encrypt(nonce,plain,MAGIC)
    wrapped=key.encrypt(secret,padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()),algorithm=hashes.SHA256(),label=None))
    if len(wrapped)>1024:raise ValueError('Unsupported key size')
    blob=MAGIC+struct.pack('>H',len(wrapped))+wrapped+nonce+ct
    if len(blob)>MAX_ARTIFACT_BYTES:raise ValueError('Sealed artifact exceeds limit')
    result.parent.mkdir(parents=True,exist_ok=True)
    with result.open('xb') as f:
        os.fchmod(f.fileno(),0o600)
        f.write(blob)
    return {'status':'ENCRYPTED_PRIVATE_MEDIA','ciphertext_bytes':len(blob),'public_artifact_contains_plain_image':False}


def unseal(source:pathlib.Path,privatekey_file:pathlib.Path,outdir:pathlib.Path):
    if outdir.exists():raise ValueError('Refusing to overwrite any existing folder')
    blob=source.read_bytes()
    if not (len(MAGIC)+2+384+12+16<len(blob)<=MAX_ARTIFACT_BYTES):
        raise ValueError('Invalid sealed artifact size')
    if not blob.startswith(MAGIC):raise ValueError('Invalid sealed artifact header')
    cursor=len(MAGIC)
    num=struct.unpack('>H',blob[cursor:cursor+2])[0];cursor+=2
    if num<384 or num>1024:raise ValueError('Bad wrapped key length')
    wrapped=blob[cursor:cursor+num];cursor+=num
    nonce=blob[cursor:cursor+12];cursor+=12
    key=serialization.load_pem_private_key(privatekey_file.read_bytes(),password=None)
    if not isinstance(key,rsa.RSAPrivateKey):raise ValueError('Expected RSA private key')
    secret=key.decrypt(wrapped,padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()),algorithm=hashes.SHA256(),label=None))
    plain=AESGCM(secret).decrypt(nonce,blob[cursor:],MAGIC)
    if len(plain)>MAX_PLAIN_BYTES:raise ValueError('Plaintext too large')
    # Validate entire archive before extracting one byte.
    files=[]
    with tarfile.open(fileobj=io.BytesIO(plain),mode='r:') as tar:
        names=set()
        for t in tar.getmembers():
            if not t.isfile() or not _safe_name(t.name) or t.name in names or t.size>40*1024*1024:
                raise ValueError('Unsafe decrypted archive entry')
            names.add(t.name)
            f=tar.extractfile(t)
            if f is None:raise ValueError('Invalid archive payload')
            content=f.read()
            if len(content)!=t.size:raise ValueError('Truncated decrypted entry')
            files.append((t.name,content))
    outdir.mkdir(parents=True,exist_ok=False)
    os.chmod(outdir,0o700)
    for name,data in files:
        path=outdir/name
        path.parent.mkdir(parents=True,exist_ok=True)
        with path.open('xb') as f:
            os.fchmod(f.fileno(),0o600)
            f.write(data)
    return {'status':'DECRYPTED_TO_PRIVATE_DIRECTORY','file_count':len(files)}


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    sub=p.add_subparsers(dest='command',required=True)
    s=sub.add_parser('seal');s.add_argument('--input-dir',type=pathlib.Path,required=True)
    s.add_argument('--public-key',type=pathlib.Path,required=True)
    s.add_argument('--output',type=pathlib.Path,required=True)
    d=sub.add_parser('unseal');d.add_argument('--input',type=pathlib.Path,required=True)
    d.add_argument('--private-key',type=pathlib.Path,required=True)
    d.add_argument('--output-dir',type=pathlib.Path,required=True)
    a=p.parse_args(argv)
    try:
        r=seal(a.input_dir,a.public_key,a.output) if a.command=='seal' else unseal(a.input,a.private_key,a.output_dir)
        print(r);return 0
    except (ValueError,OSError,tarfile.TarError) as e:
        print({'status':'ERROR','error':type(e).__name__+': '+str(e)})
        return 2

if __name__=='__main__':raise SystemExit(main())