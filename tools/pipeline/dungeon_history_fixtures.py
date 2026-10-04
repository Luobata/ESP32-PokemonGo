"""Read the immutable public V3 run sample; never regenerate it in tests."""
import hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
def c_dungeon_history():
 folder=ROOT/'tools/pipeline/fixtures/dungeon_history'
 record=json.loads((folder/'manifest.json').read_text())
 data=(folder/record['file']).read_bytes()
 assert len(data)==record['size'] and hashlib.sha256(data).hexdigest()==record['sha256']
 assert int.from_bytes(data[:4],'little')==3
 return 'static const unsigned char dungeon_history[]={' + ','.join(map(str,data)) + '};\n'
