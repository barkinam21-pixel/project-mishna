"""Private noncommercial Hebrew voice canary; no API, cloning or publication."""
from pathlib import Path
import json
import torch
import scipy.io.wavfile
from transformers import VitsModel, AutoTokenizer, set_seed
from tools.seal_private_media import seal

out = Path('private-media/mms-canary')
out.mkdir(parents=True, exist_ok=True)
model_id = 'facebook/mms-tts-heb'
revision = '6c8e209bb946753c77cc196c18c45b839e9b174b'
text = 'זהו מבחן פרטי של קול ותמונה. האיור הוא שחזור אמנותי, ולא תיעוד היסטורי.'
set_seed(37)
torch.set_num_threads(2)
model = VitsModel.from_pretrained(model_id, revision=revision)
tokenizer = AutoTokenizer.from_pretrained(model_id, revision=revision)
with torch.no_grad():
    samples = model(**tokenizer(text, return_tensors='pt')).waveform[0].cpu().numpy()
assert len(samples) > model.config.sampling_rate
scipy.io.wavfile.write(out/'voice.wav', model.config.sampling_rate, samples)
(out/'voice.json').write_text(json.dumps(dict(text=text,model=model_id,revision=revision,
    license='CC-BY-NC-4.0',seed=37,rate=model.config.sampling_rate,
    external_spend_usd=0,workspace_usage='unknown',approved=False),ensure_ascii=False))
seal(out, Path('security/voice-canary-session-public.pem'), Path('build/voice-canary.bin'))
print('ENCRYPTED_VOICE_CANARY_CREATED_NOT_APPROVED')
