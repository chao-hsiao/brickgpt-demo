"""Point a separate adapter configuration at the pinned local base weights."""
from pathlib import Path
import json, os
HERE = Path(__file__).resolve().parent
def prepare():
    m = json.loads((HERE/'model_manifest.json').read_text())
    if m['status'] != 'complete':
        raise RuntimeError('Official downloads are not complete')
    base = Path(next(x['snapshot'] for x in m['models'] if x['repo'].startswith('meta-llama/')))
    adapter = Path(next(x['snapshot'] for x in m['models'] if x['repo']=='AvaLovelace/BrickGPT'))
    dest = HERE.parent/'models/BrickGPT-local'
    dest.mkdir(exist_ok=True)
    for f in adapter.iterdir():
        if not f.is_file() or f.name=='adapter_config.json':
            continue
        link = dest/f.name
        if not link.exists():
            link.symlink_to(os.path.relpath(f, dest))
    cfg = json.loads((adapter/'adapter_config.json').read_text())
    cfg['base_model_name_or_path'] = str(base)
    (dest/'adapter_config.json').write_text(json.dumps(cfg, indent=2))
    m['runtime_adapter'] = str(dest)
    m['local_config_note'] = 'Only base_model_name_or_path redirected to pinned local snapshot; official snapshots and weights unmodified.'
    (HERE/'model_manifest.json').write_text(json.dumps(m, indent=2))
    return dest
if __name__=='__main__':
    print(prepare())
