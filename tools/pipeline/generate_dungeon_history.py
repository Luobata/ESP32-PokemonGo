#!/usr/bin/env python3
"""Append-only historical V3 fixture, using the last public release's headers."""
import hashlib,json,subprocess,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
DEST=ROOT/'tools/pipeline/fixtures/dungeon_history'
ref='0f76077'
def git(*args):return subprocess.check_output(['git',*args],cwd=ROOT)
sha=git('rev-parse',ref).decode().strip()
with tempfile.TemporaryDirectory() as tmp:
 t=Path(tmp);hashes={}
 paths=git('ls-tree','-r','--name-only',sha,'firmware/main','firmware/components/bsp/include').decode().splitlines()
 for path in paths:
  if not path.endswith('.h'):continue
  data=git('show',f'{sha}:{path}');(t/Path(path).name).write_bytes(data);hashes[path]=hashlib.sha256(data).hexdigest()
 (t/'esp_err.h').write_text('typedef int esp_err_t;\n')
 subprocess.run(['cc','-std=gnu11','-I',str(t),str(ROOT/'tools/pipeline/fixtures/historical_dungeon_writer.c'),'-o',str(t/'writer')],check=True)
 subprocess.run([str(t/'writer'),str(t/'run.bin')],check=True)
 data=(t/'run.bin').read_bytes();name=f'v3-{ref}.bin';record=dict(file=name,version=3,size=len(data),sha256=hashlib.sha256(data).hexdigest(),source_commit=sha,source_type='dungeon_t',source_hashes=hashes,provenance='Synthetic nonempty V3 run built from published headers')
 DEST.mkdir(parents=True,exist_ok=True)
 target=DEST/name
 if target.exists():assert target.read_bytes()==data,'Never replace historical bytes'
 else:target.write_bytes(data)
 manifest=DEST/'manifest.json'
 encoded=json.dumps(record,indent=2)+'\n'
 if manifest.exists():assert manifest.read_text()==encoded
 else:manifest.write_text(encoded)
 print(f'Frozen dungeon V3: {len(data)} bytes')
