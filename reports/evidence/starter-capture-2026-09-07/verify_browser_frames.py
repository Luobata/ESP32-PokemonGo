"""Compare observed browser Canvas readbacks with matching actual C input runs."""
from pathlib import Path
import sys,json,hashlib
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'tools/inspector'))
from native import Renderer,build,rgb888,png
exe,version=build()
assert version=='788d5f7752742418ba6c'
results=[]
def capture(label,frame,want):
    rgb=rgb888(frame['pixels'])
    rgba=b''.join(rgb[i:i+3]+b'\xff' for i in range(0,len(rgb),3))
    got=hashlib.sha256(rgba).hexdigest()
    assert got==want,(label,got,want)
    Path(__file__).with_name(label+'.png').write_bytes(png(frame['pixels']))
    results.append(dict(label=label,page=frame['page'],ms=frame['ms'],rgba_sha256=got,match=True))
r=Renderer(exe)
try:
 r.command('boot 3 25 100 19 1 1 0');r.command('key 1 1')
 capture('victory',r.command('tick 4320'),'22c52830743d5b53a56dfa76db5ef4b5a76a2d88945d766d1890a81c2cb8c485')
 capture('last-capture-poke',r.command('key 0 1'),'1f358089b7baa5bfc8cdc02b58d54d6ff6a9cef238f39d49136443b49229f61d')
 capture('last-capture-great',r.command('key 1 1'),'cd1349b75f3375cbbaf6897b23fdc71c8fe48f2e631d8ff064b2fb102d204166')
 capture('last-capture-ultra',r.command('key 1 1'),'35228aa1a61be3ab5febe8b9ff7fa58a1c0cd57e0a32237e8074046c54e51bf4')
 r.command('key 1 1')
 capture('last-capture-success',r.command('key 0 1'),'35b3a123010f2b439e1175d7fa51d06c78ac765da1086f9699c2b889577a7cef')
 r.command('key 2 1')
 capture('caught-encounter-list',r.command('tick 60'),'2fcc4ee85a2a932d8dc1313eac4c7d13fc352d2b6df737fe298a70e038f8260e')
finally:r.close()
r=Renderer(exe)
try:
 r.command('boot 3 139 100 137 1 3 0');r.command('key 1 1')
 capture('porygon-victory',r.command('tick 1920'),'72bfd6cb28782c3ab4c739d6466806de23cd08f2e7a873eb219bdaa4101235b5')
 r.command('key 0 1');r.command('key 1 1')
 capture('porygon-last-throw-miss',r.command('key 0 1'),'d10e9d719eb9bb827fac1f386297da1886c90dcb0be8fb332fe591b215bf078e')
 r.command('key 2 1')
 capture('porygon-escaped-list',r.command('tick 60'),'2fcc4ee85a2a932d8dc1313eac4c7d13fc352d2b6df737fe298a70e038f8260e')
finally:r.close()
r=Renderer(exe)
try:
 r.command('boot 3 25 12 19 1 7 0');r.command('key 0 1')
 capture('prebattle-capture-miss',r.command('key 0 1'),'331070424cf68ee4d82ea1e53a06c81906b3a9143fbc2808084e67badd9bc60c')
 r.command('key 2 1')
 capture('mandatory-retaliation',r.command('tick 60'),'1e89c94899c90e30a19fab54d16b96605fdda0847270e5f478ac0cfcbe2437a6')
 capture('retaliation-cannot-cancel',r.command('key 2 1'),'1e89c94899c90e30a19fab54d16b96605fdda0847270e5f478ac0cfcbe2437a6')
finally:r.close()
r=Renderer(exe)
try:
 frame=r.command('boot 9 25 12 74 3 1 0')
 for sid,want in [(1,'9d4a22810694d1f4d659a4538473a8817be3699d4c7b824e99ca818e66b85354'),(4,'77aa0aae592b7a6fb22e302cefb19a5a9a01173ddddff09ddff043329e61f1e6'),(7,'17a95f058bbca1022975883f1010823c9453df09285b8eb3fce0cb553434068a'),(25,'4177b87acd669b7b5fe7bc90857f9f09693e868ee8123d1072d333b969aa208d')]:
  capture(f'starter-{sid:03d}',frame,want)
  frame=r.command('key 1 1')
finally:r.close()
result=dict(build=version,frames=len(results),pixels_compared=len(results)*240*320,mismatches=0,results=results)
Path(__file__).with_name('browser-parity.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps({k:v for k,v in result.items() if k!='results'}))
