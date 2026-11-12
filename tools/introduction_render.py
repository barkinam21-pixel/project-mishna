"""Local FFmpeg opening assembly. No generation APIs; test fixtures cannot approve media."""
import argparse
import hashlib
import json
import subprocess
import tempfile
import wave
from pathlib import Path
from tools.introduction_proof import plan, SHOTS, CUES, PROFILE, digest
from tools.private_proof_assembler import ffmpeg_args, verify_video, file_under
from tools import hebrew_captions as captions

def verified_output(path, total):
    if not verify_video(path,total): return False
    from fractions import Fraction
    streams=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_entries','stream=codec_type,duration_ts,time_base,start_time','-of','json',str(path)]))['streams']
    audio=next(x for x in streams if x['codec_type']=='audio')
    return Fraction(audio['time_base'])*audio['duration_ts']==Fraction(total,24) and float(audio['start_time'])==0

def validate(c, root, test_fixture=False):
    root=Path(root).resolve()
    if c.get('test_fixture') is True and not test_fixture: raise ValueError('Explicit test-fixture mode required')
    if test_fixture and c.get('test_fixture') is not True: raise ValueError('Not a test fixture')
    if c.get('scene')!='INTRO-A1-S01': raise ValueError('Wrong scene')
    if c.get('release_authorized') is not False or c.get('external_spend_usd')!=0 or c.get('profile')!=PROFILE: raise ValueError('Unsafe configuration')
    if not test_fixture:
        if c.get('script_approved') is not True or c.get('visual_approved') is not True: raise ValueError('Missing scene approvals')
    shots=c['shots']
    if [s['id'] for s in shots]!=SHOTS: raise ValueError('Wrong shot IDs')
    if any(type(s['duration_frames']) is not int or s['duration_frames']<=0 for s in shots): raise ValueError('Invalid frames')
    total=sum(s['duration_frames'] for s in shots)
    capfile=file_under(root,c['assets']['captions']['path']);master=json.loads(capfile.read_text())
    qa=captions.validate(master,require_approval=not test_fixture)
    if not qa['valid'] or (qa['warnings'] and not test_fixture): raise ValueError(str(qa['errors']+qa['warnings']))
    if any(x['end_frame']>total for x in master['cues']): raise ValueError('Caption beyond film')
    slots={};cursor=0
    for shot in shots:
        if shot.get('start_frame',cursor)!=cursor or shot.get('end_frame',cursor+shot['duration_frames'])!=cursor+shot['duration_frames']: raise ValueError('Shot frame boundaries disagree')
        slots[shot['id']]=(cursor,cursor+shot['duration_frames']);cursor+=shot['duration_frames']
    for cue in master['cues']:
        slot=slots.get(cue['shot_id'])
        if slot is None or not slot[0]<=cue['start_frame']<cue['end_frame']<=slot[1]: raise ValueError('Caption outside shot')
    voices=c['voice_takes']
    if [v['id'] for v in voices]!=CUES: raise ValueError('Two exact narration IDs required')
    previous_end=0
    for v in voices:
        start,end=v['start_frame'],v['end_frame']
        if type(start) is not int or type(end) is not int or not previous_end<=start<end<=total: raise ValueError('Voice overlap/range')
        if v.get('start_sample',start*2000)!=start*2000 or v.get('end_sample',end*2000)!=end*2000: raise ValueError('Audio sample/frame disagreement')
        previous_end=end
        item=c['assets'][v['id']]
        if v['path']!=item['path']: raise ValueError('Voice path mismatch')
        if not test_fixture and item.get('real_hebrew_speech_confirmed') is not True: raise ValueError('Real Hebrew speech confirmation required')
        path=file_under(root,v['path'])
        with wave.open(str(path)) as w:
            if (w.getframerate(),w.getnchannels(),w.getsampwidth())!=(48000,1,2) or w.getnframes()>(end-start)*2000: raise ValueError('Voice format/slot')
    if not test_fixture:
        import re
        script=(root/'scripts/introduction-working-draft.md').read_text()
        chunks=re.split(r'(?=^\*\*[^\n]*INTRO-A\d-S\d+-[NQ]\d+)',script,flags=re.M)
        expected={}
        for chunk in chunks[1:]:
            uid=re.search(r'INTRO-A\d-S\d+-[NQ]\d+',chunk).group()
            expected[uid]=' '.join(l[2:] for l in chunk.splitlines() if l.startswith('> '))
        normalize=lambda text:' '.join(text.split())
        for voice in voices:
            rows=[x for x in master['cues'] if x.get('voice_id')==voice['id']]
            if not rows or normalize(' '.join(x['spoken_text'] for x in rows))!=normalize(expected[voice['id']]): raise ValueError('Captions do not match scene narration')
            if any(not voice['start_frame']<=x['start_frame']<x['end_frame']<=voice['end_frame'] for x in rows): raise ValueError('Caption outside narration slot')
        if any(x.get('voice_id') not in CUES for x in master['cues']): raise ValueError('Unknown caption voice')
    paths={}
    for uid,item in c['assets'].items():
        path=file_under(root,item['path'])
        if path is None or not path.is_file() or digest(path)!=item['sha256']: raise ValueError('Missing/changed asset '+uid)
        paths[uid]=path
    if len({digest(paths[x]) for x in SHOTS})!=7: raise ValueError('Duplicate illustrations')
    return shots,total,master,voices,paths

def render(c, root, out, test_fixture=False):
    root=Path(root).resolve();out=Path(out).resolve()
    if not test_fixture:
        report=plan(c,root)
        if report['errors'] or report['missing']: raise ValueError('Missing or unapproved production inputs')
    shots,total,master,voices,paths=validate(c,root,test_fixture)
    out.mkdir(parents=True,exist_ok=True);cache=out/'cache';cache.mkdir(exist_ok=True)
    font=Path(subprocess.check_output(['fc-match','-f','%{file}','Noto Sans Hebrew']).decode())
    dependencies=Path(__file__).read_bytes()+(root/'tools/private_proof_assembler.py').read_bytes()+Path(captions.__file__).read_bytes()+font.read_bytes()+subprocess.check_output(['ffmpeg','-version'])
    key=hashlib.sha256(json.dumps(c,sort_keys=True).encode()+dependencies).hexdigest()
    receipt=out/'receipt.json';video=out/'private-review.mp4'
    if receipt.exists() and video.exists():
        old=json.loads(receipt.read_text())
        if old['key']==key and old['video_sha256']==digest(video) and all((out/name).is_file() and digest(out/name)==sha for name,sha in old.get('sidecars',{}).items()) and len(old.get('sidecars',{}))==3 and verified_output(video,total):
            return dict(old,cache_hit=True,normalized_images_created=0)
    normalized=[];created=0
    from PIL import Image,ImageOps,ImageDraw,__version__ as pillow_version
    for uid in SHOTS:
        k=hashlib.sha256((digest(paths[uid])+str(test_fixture)+'1920x1080-v1'+pillow_version).encode()).hexdigest();dest=cache/(k+'.png');stamp=cache/(k+'.json')
        if not dest.exists() or not stamp.exists() or json.loads(stamp.read_text()).get('sha256')!=digest(dest):
            with Image.open(paths[uid]) as im: im=ImageOps.fit(im.convert('RGB'),(1920,1080))
            if test_fixture: ImageDraw.Draw(im).text((80,80),'TECHNICAL TEST - SYNTHETIC MEDIA - NOT APPROVED',fill='white',stroke_width=2)
            im.save(dest);stamp.write_text(json.dumps({'sha256':digest(dest)}));created+=1
        normalized.append({'shot_id':uid,'path':str(dest.relative_to(root))})
    media={'images':normalized,'voice_takes':voices};blueprint={'shots':shots,'target_duration_frames':total}
    with tempfile.TemporaryDirectory(dir=out) as folder:
        tmp=Path(folder);srt=[];vtt=['WEBVTT',''];ass=[captions.ASS_HEADER]
        for i,cue in enumerate(master['cues'],1):
            a,b,text=cue['start_frame'],cue['end_frame'],cue['display_text']
            srt += [str(i),captions.timestamp(a,'srt')+' --> '+captions.timestamp(b,'srt'),text,'']
            vtt += [captions.timestamp(a,'vtt')+' --> '+captions.timestamp(b,'vtt'),text,'']
            ass.append('Dialogue: 0,%s,%s,Hebrew,,0,0,0,,%s'%(captions.timestamp(a,'ass'),captions.timestamp(b,'ass'),text.replace('\n',r'\N')))
        for ext,lines in [('srt',srt),('vtt',vtt),('ass',ass)]: (tmp/('private-captions.'+ext)).write_text('\n'.join(lines)+'\n')
        cmd=ffmpeg_args(media,blueprint,root,tmp);cmd[1:1]=['-threads','1'];subprocess.run(cmd,cwd=tmp,check=True)
        candidate=tmp/'private-review.mp4'
        if not verified_output(candidate,total): raise ValueError('Output QA failed')
        subprocess.run(['ffmpeg','-v','error','-i',str(candidate),'-f','null','-'],check=True)
        candidate.replace(video)
        for ext in ['srt','vtt','ass']: (out/('private-captions.'+ext)).write_bytes((tmp/('private-captions.'+ext)).read_bytes())
    sidecars={('private-captions.'+ext):digest(out/('private-captions.'+ext)) for ext in ['srt','vtt','ass']}
    result={'sidecars':sidecars,'key':key,'video_sha256':digest(video),'cache_hit':False,'normalized_images_created':created,'test_fixture':test_fixture,'frames':total,'audio_samples':total*2000,'release_authorized':False}
    temp=receipt.with_suffix('.tmp');temp.write_text(json.dumps(result,indent=2));temp.replace(receipt);return result

def main():
    p=argparse.ArgumentParser();p.add_argument('config');p.add_argument('--out',default='build/introduction-render');p.add_argument('--test-fixture',action='store_true');a=p.parse_args();root=Path.cwd();print(json.dumps(render(json.loads(Path(a.config).read_text()),root,root/a.out,a.test_fixture)))
if __name__=='__main__':main()
