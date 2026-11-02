#!/usr/bin/env python3
"""Offline QA for private opening animation blockout; no AI calls or charges."""
import argparse, hashlib, json, subprocess, sys
from pathlib import Path

def probe(path):
    r=subprocess.run(['ffprobe','-v','error','-show_entries',
     'format=duration,size:stream=index,codec_type,codec_name,width,height,nb_frames,avg_frame_rate,pix_fmt,color_space,color_transfer,color_primaries,sample_rate,channels',
     '-of','json',str(path)],capture_output=True,text=True,check=True)
    return json.loads(r.stdout)

def validate(path):
    data=probe(path)
    vs=[s for s in data.get('streams',[]) if s.get('codec_type')=='video']
    ads=[s for s in data.get('streams',[]) if s.get('codec_type')=='audio']
    errs=[]
    if len(vs)!=1: errs.append('one video stream expected')
    if len(ads)!=1: errs.append('one audio stream expected')
    if vs:
      v=vs[0]
      for key,expected in {'codec_name':'h264','width':960,'height':540,'avg_frame_rate':'24/1','pix_fmt':'yuv420p','color_space':'bt709','color_primaries':'bt709','color_transfer':'bt709'}.items():
        if v.get(key)!=expected: errs.append(f'video.{key}: expected {expected!r}, got {v.get(key)!r}')
      if v.get('nb_frames') not in ('1080',1080):errs.append('must have 1080 rendered frames')
    if ads:
      a=ads[0]
      if a.get('codec_name')!='aac' or a.get('sample_rate')!='48000' or a.get('channels')!=2:errs.append('AAC stereo 48000 required')
    if abs(float(data['format']['duration'])-45)>0.01:errs.append('must be 45.0 seconds')
    decoder=subprocess.run(['ffmpeg','-v','error','-xerror','-i',str(path),'-f','null','-'],capture_output=True,text=True)
    if decoder.returncode:errs.append('full decode failed: '+decoder.stderr[-500:])
    return {'status':'PASS_BLOCKOUT_ONLY_NOT_FINAL' if not errs else 'FAIL','errors':errs,'frames':int(vs[0].get('nb_frames',-1)) if vs else 0,'duration_seconds':float(data['format']['duration']),'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'no_paid_ai_generation':True,'real_illustrations':0,'natural_hebrew_voice_recorded':False,'public_release_authorized':False}

def main():
    p=argparse.ArgumentParser();p.add_argument('file',type=Path);p.add_argument('--out',type=Path)
    a=p.parse_args();data=validate(a.file)
    if a.out:a.out.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print(json.dumps(data,ensure_ascii=False,indent=2));return int(data['status'].startswith('FAIL'))

if __name__=='__main__':sys.exit(main())