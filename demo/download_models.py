"""Download pinned official inference weights; never print credentials."""
from pathlib import Path
import json, os, time

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / 'models' / 'hf-cache'
os.environ['HF_HUB_CACHE'] = str(CACHE)
os.environ['HF_HUB_DISABLE_PROGRESS_BARS'] = '1'
token = os.environ.get('HUGGING_FACE_TOKEN') or os.environ.get('HF_TOKEN')
if token:
    os.environ['HF_TOKEN'] = token
from huggingface_hub import HfApi, snapshot_download, get_token
token = token or get_token()
OUT = ROOT / 'demo' / 'model_manifest.json'
manifest = {'started': time.time(), 'status': 'checking_access', 'models': []}
def save():
    OUT.write_text(json.dumps(manifest, indent=2))
save()
try:
    HfApi().whoami(token=token)
    revisions = {'meta-llama/Llama-3.2-1B-Instruct': '9213176726f574b556790deb65791e0c5aa438b6',
                 'AvaLovelace/BrickGPT': '19737def7bfe5950b2a466825ad7c6d74b7eafe3'}
    for repo, revision in revisions.items():
        info = HfApi().model_info(repo, revision=revision, token=token, files_metadata=True)
        entry = {'repo': repo, 'revision': info.sha,
                 'weight_bytes': sum((f.size or 0) for f in info.siblings if f.rfilename.endswith('.safetensors'))}
        manifest['models'].append(entry)
        manifest['status'] = 'downloading ' + repo
        save()
        print(json.dumps({'event': 'download', **entry}), flush=True)
        path = snapshot_download(repo, revision=info.sha, cache_dir=CACHE, token=token,
            allow_patterns=['*.json', '*.safetensors', 'tokenizer.model', 'LICENSE', 'USE_POLICY.md', 'README.md'],
            ignore_patterns=['original/*'], max_workers=3)
        entry['snapshot'] = path
        save()
    manifest['status'] = 'complete'
    manifest['elapsed_seconds'] = time.time() - manifest['started']
    save()
    print(json.dumps({'event': 'complete', 'seconds': manifest['elapsed_seconds']}), flush=True)
except Exception as exc:
    manifest['status'] = 'failed'
    manifest['error_type'] = type(exc).__name__
    manifest['http_status'] = getattr(getattr(exc, 'response', None), 'status_code', None)
    save()
    print(json.dumps({'event': 'failed', 'error_type': type(exc).__name__, 'http_status': manifest['http_status']}), flush=True)
    raise SystemExit(1)
