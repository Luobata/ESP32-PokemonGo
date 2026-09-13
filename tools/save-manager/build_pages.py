#!/usr/bin/env python3
"""Build only public save-manager assets for GitHub Pages; never package saves."""
import argparse
from pathlib import Path
from server import ROOT, local_bundle

WEB_FILES = ('index.html', 'style.css', 'app.mjs', 'backup.mjs')

def build(output):
    output = Path(output)
    if output.exists() and any(output.iterdir()):
        raise ValueError('Output directory must be empty')
    output.mkdir(parents=True, exist_ok=True)
    for name in WEB_FILES:
        (output/name).write_bytes((ROOT/'web'/name).read_bytes())
    (output/'.nojekyll').touch()
    download = output/'download'
    download.mkdir()
    (download/'PokeWalkSaveManager.zip').write_bytes(local_bundle())
    return output

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    print(build(parser.parse_args().output))
