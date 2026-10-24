#!/usr/bin/env python3
"""Build an isolated, verified Johto asset review. Never installs/flashes assets."""
import argparse,json,subprocess,sys,struct,tempfile,shutil
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
PIPE=ROOT/'tools/pipeline'

def build(src:Path):
    assets=ROOT/'assets/johto-candidate'
    report=ROOT/'reports/evidence/johto-gameplay-2026-10-17'
    report.mkdir(parents=True,exist_ok=True)
    dest=ROOT/'tools/inspector/johto-assets'
    def run(name,*args):
        subprocess.run([sys.executable,str(PIPE/name),*map(str,args)],check=True)
    run('convert_johto.py','--src',src,'--out',assets)
    run('convert_font.py','--species-bin',assets/'gen1.bin','--out',assets)
    # The ready manifest is replaced only after every source/renderer check passes.
    with tempfile.TemporaryDirectory(prefix='johto-verified-preview-',dir=dest.parent) as folder:
        temp=Path(folder)
        run('verify_pokemon_art.py','--src',src,'--assets',assets,'--preview-dir',temp,'--report',report/'art.json')
        run('verify_pokemon_animation.py','--src',src,'--assets',assets,'--preview-dir',temp,'--report',report/'animation.json')
        run('verify_johto.py','--assets',assets,'--report',report/'chapter.json')
        catalog=json.loads((assets/'johto_catalog.json').read_text())
        blob=(assets/'gen1.bin').read_bytes();_,_,stride,count,_=struct.unpack_from('<4sHHII',blob)
        for row in catalog['pokemon']:
            record=16+(row['id']-1)*stride
            off=struct.unpack_from('<H',blob,record+20)[0];size=blob[record+22]
            row['name_zh']=blob[16+count*stride+off:16+count*stride+off+size].decode()
        data={'source':catalog['commit'],'pokemon':catalog['pokemon'],
              'timing':json.loads((temp/'timing.json').read_text()),
              'chapter':json.loads((report/'chapter.json').read_text()),
              'status':'development_gameplay','live_game_species':251,'warehouse_capacity':453,
              'pending':['跨世代特殊进化与追加道具、成就','主题副本、终战专属结局与选择奖励','第二世代叫声与剩余招式机制','未知图腾其他形态、写生与果然翁专门机制','真机内存、导入覆盖与整段流程验收']}
        (temp/'catalog.json').write_text(json.dumps(data,ensure_ascii=False,separators=(',',':'))+'\n')
        old=dest.with_name('johto-assets.previous')
        if old.exists():shutil.rmtree(old)
        if dest.exists():dest.rename(old)
        try:shutil.copytree(temp,dest)
        except Exception:
            if dest.exists():shutil.rmtree(dest)
            if old.exists():old.rename(dest)
            raise
        if old.exists():shutil.rmtree(old)
    print('Verified local review: http://127.0.0.1:8766/johto.html')

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--src',type=Path,required=True)
    build(p.parse_args().src)
