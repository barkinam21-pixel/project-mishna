"""Manual protected Azure audition. Never log credentials or response bodies."""
import argparse,json,os,subprocess,urllib.request
from pathlib import Path
from tools.voice_take_audit import hebrew_rehearsal_ssml,inspect_wav
from tools.seal_private_media import seal


def verify_resource(resource,region):
    if (resource.get('type','').lower()!='microsoft.cognitiveservices/accounts'
        or resource.get('kind')!='SpeechServices' or resource.get('sku',{}).get('name')!='F0'
        or resource.get('location','').replace(' ','').lower()!=region):
        raise ValueError('Resource type, SpeechServices kind, F0 tier and region must match')


def main():
    p=argparse.ArgumentParser();p.add_argument('--synthesize',action='store_true');a=p.parse_args()
    key=os.environ.get('AZURE_SPEECH_KEY','');region=os.environ.get('AZURE_SPEECH_REGION','')
    rid=os.environ.get('AZURE_SPEECH_RESOURCE_ID','')
    if not key or not rid:raise ValueError('Missing protected connection settings')
    import re
    if region and not re.fullmatch('[a-z0-9-]{2,30}',region):raise ValueError('Invalid region')
    # Live ARM read using the explicitly configured federated Azure identity.
    result=subprocess.run(['az','resource','show','--ids',rid,'--output','json'],capture_output=True,check=True,text=True)
    resource=json.loads(result.stdout)
    region=region or resource.get('location','').replace(' ','').lower()
    if not re.fullmatch('[a-z0-9-]{2,30}',region):raise ValueError('Invalid resource region')
    if resource.get('id','').lower()!=rid.lower():raise ValueError('Resource ID mismatch')
    verify_resource(resource,region)
    base='https://'+region+'.tts.speech.microsoft.com/cognitiveservices/'
    headers={'Ocp-Apim-Subscription-Key':key}
    with urllib.request.urlopen(urllib.request.Request(base+'voices/list',headers=headers),timeout=20) as r:
        voices=json.load(r)
    if not any(v.get('ShortName')=='he-IL-AvriNeural' for v in voices):raise ValueError('Hebrew voice unavailable')
    print('LIVE_ARM_F0_AND_HEBREW_VOICE_CHECK_PASSED')
    if not a.synthesize:return
    # Exactly one short request, no retry, no fallback or pricing change.
    ssml=hebrew_rehearsal_ssml('ערב יורד על הכפר. רַבָּן גַּמְלִיאֵל, תְּרוּמָה, עַמּוּד הַשַּׁחַר.','narrator')
    headers.update({'Content-Type':'application/ssml+xml','X-Microsoft-OutputFormat':'riff-48khz-16bit-mono-pcm'})
    req=urllib.request.Request(base+'v1',data=ssml.encode(),headers=headers,method='POST')
    with urllib.request.urlopen(req,timeout=30) as r:data=r.read(8*1024*1024+1)
    if len(data)>8*1024*1024:raise ValueError('Excessive audio response')
    out=Path('private-media/azure-audition');out.mkdir(parents=True,exist_ok=False)
    wav=out/'audition.wav';wav.write_bytes(data)
    info=inspect_wav(wav)
    if info['is_silent'] or info['sample_rate']!=48000:raise ValueError('Invalid audio')
    seal(out,Path('security/production_artifacts_public_key.pem'),Path('build/azure-audition.bin'))
    print('ENCRYPTED_AUDITION_CREATED_NOT_LISTENED_OR_APPROVED')

if __name__=='__main__':
    try:main()
    except Exception:
        print('AZURE_CHECK_BLOCKED_OR_FAILED; no retry; sensitive details withheld')
        raise SystemExit(2)
