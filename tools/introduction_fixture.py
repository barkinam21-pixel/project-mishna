"""Original synthetic integration fixture; no real narrator or production approvals."""
import json,math,struct,wave
from pathlib import Path
from PIL import Image,ImageDraw
from tools.introduction_proof import SHOTS,CUES,PROFILE,digest
from tools.introduction_render import render

def run(root):
 root=Path(root).resolve();folder=root/'build/introduction-fixture';folder.mkdir(parents=True,exist_ok=True)
 c={'scene':'INTRO-A1-S01','profile':PROFILE,'test_fixture':True,'external_spend_usd':0,'release_authorized':False,'assets':{},'shots':[],'voice_takes':[]}
 for i,uid in enumerate(SHOTS):
  f=folder/(uid+'.png');im=Image.new('RGB',(640,360),(30+i*20,30,70));ImageDraw.Draw(im).rectangle((30+i*30,130,130+i*30,230),fill=(200,140,60));im.save(f);c['assets'][uid]={'path':str(f.relative_to(root)),'sha256':digest(f)};c['shots'].append({'id':uid,'duration_frames':24,'start_frame':i*24,'end_frame':(i+1)*24})
 for i,uid in enumerate(CUES):
  f=folder/(uid+'.wav')
  with wave.open(str(f),'wb') as w:
   w.setparams((1,2,48000,0,'NONE','not compressed'));w.writeframes(b''.join(struct.pack('<h',int(1000*math.sin(2*math.pi*(220+i*110)*n/48000))) for n in range(48000)))
  item={'path':str(f.relative_to(root)),'sha256':digest(f)};c['assets'][uid]=item;c['voice_takes'].append(dict(item,id=uid,start_frame=i*72,end_frame=i*72+24,start_sample=i*72*2000,end_sample=(i*72+24)*2000))
 master={'fps':24,'language':'he','cues':[{'id':str(i),'start_frame':i*24,'end_frame':(i+1)*24,'display_text':'בדיקה טכנית בלבד','spoken_text':'צליל בדיקה','pronunciation_text':'צליל בדיקה','speaker':'synthetic-test-tone','source':'TEST ONLY','shot_id':uid} for i,uid in enumerate(SHOTS)]}
 f=folder/'captions.json';f.write_text(json.dumps(master,ensure_ascii=False));c['assets']['captions']={'path':str(f.relative_to(root)),'sha256':digest(f)};(folder/'manifest.json').write_text(json.dumps(c,indent=2))
 out=folder/'output';a=render(c,root,out,True);b=render(c,root,out,True);assert b['cache_hit'] and b['normalized_images_created']==0
 # One changed original invalidates only its normalized derivative.
 f=folder/'OPN03.png';im=Image.open(f);im.putpixel((0,0),(255,0,0));im.save(f);c['assets']['OPN03']['sha256']=digest(f);changed=render(c,root,out,True);assert changed['normalized_images_created']==1 and not changed['cache_hit']
 f=folder/(CUES[0]+'.wav');raw=bytearray(f.read_bytes());raw[-2:]=b'\x01\x00';f.write_bytes(raw);c['assets'][CUES[0]]['sha256']=digest(f);c['voice_takes'][0]['sha256']=digest(f);audio_changed=render(c,root,out,True);assert audio_changed['normalized_images_created']==0 and not audio_changed['cache_hit']
 (folder/'manifest.json').write_text(json.dumps(c,indent=2));report={'first':a,'second':b,'one_image_replaced':changed,'one_audio_replaced':audio_changed,'test_only':True};(folder/'integration-result.json').write_text(json.dumps(report,indent=2));print(json.dumps(report))
if __name__=='__main__':run(Path.cwd())
