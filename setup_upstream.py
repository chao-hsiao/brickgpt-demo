"""Fetch the fixed official source without installing its Blender extras."""
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parent
COMMIT = 'da01aab83f646a700e2270b66b4c00180523448b'
DEST = ROOT / 'repos/BrickGPT'

def setup():
    if not DEST.exists():
        DEST.parent.mkdir(exist_ok=True)
        subprocess.run(['git', 'clone', '--no-checkout',
                        'https://github.com/AvaLovelace1/BrickGPT.git', str(DEST)],
                       check=True, timeout=180)
        subprocess.run(['git', '-C', str(DEST), 'checkout', '--detach', COMMIT],
                       check=True, timeout=60)
    head = subprocess.check_output(['git', '-C', str(DEST), 'rev-parse', 'HEAD'], text=True).strip()
    dirty = subprocess.check_output(['git', '-C', str(DEST), 'status', '--porcelain'], text=True)
    if head != COMMIT or dirty:
        raise RuntimeError('Existing upstream checkout differs or has edits; preserve it and inspect manually.')
    print('Official BrickGPT source verified:', head)

if __name__ == '__main__':
    setup()
