#!/usr/bin/env python3
"""Repack checked-in display data, preserving the frozen logical OAM stream."""
import argparse, hashlib, json, re, struct
from pathlib import Path
from pack_gold_objects import pack_objects
ROOT=Path(__file__).resolve().parents[2]

def repack(source):
    def table(name):
        return [tuple(map(int,row.split(','))) for row in re.findall(r'\{([^{}]+)\}',source.split(name+'[] = {')[1].split('};')[0])]
    refs=table('gold_object_refs');shapes=table('gold_shapes');spans=table('gold_object_spans')
    blocks=[int(x) for x in re.findall(r'\d+',source.split('gold_object_blocks[] = {')[1].split('};')[0])] if 'gold_object_blocks' in source else None
    def decode(i):
        shape,x,y=refs[blocks[i//2]*2+i%2 if blocks else i];tile,flags,dx,dy=shapes[shape]
        return tile,x,y,flags,dx,dy
    rows=[decode(a+i) for a,n in spans for i in range(n)]
    # Current public stream (including late beam/capture fixes), not the stale
    # pre-Johto 103495-object stream. Never derive this expected hash at runtime.
    assert len(rows)==106223
    assert hashlib.sha256(b''.join(struct.pack('<HBBBbb',*r) for r in rows)).hexdigest()=='0afdd7838747b9d224678a97987bf1a99f1579010e32415bbd0f0948155efd6d'
    original=[];offset=0
    for _,n in spans:original.append((offset,n));offset+=n
    packed,meta=pack_objects(rows,original)
    packed+='static const gold_span_t gold_object_spans[] = {\n'+''.join('{%u,%u},\n'%s for s in original)+'};\n'
    start=source.index('typedef struct { uint16_t tile; uint8_t flags;')
    end=source.index('static const gold_frame_t gold_frames')
    return source[:start]+packed+source[end:],meta

def main():
    p=argparse.ArgumentParser();p.add_argument('--check',action='store_true');a=p.parse_args()
    path=ROOT/'firmware/main/gold_fx_data.h';out,meta=repack(path.read_text())
    mp=ROOT/'assets/gold_fx_sources.json';m=json.loads(mp.read_text());m['object_packing']=meta;m['header_sha256']=hashlib.sha256(out.encode()).hexdigest()
    if a.check:
        assert path.read_text()==out
        assert json.loads(mp.read_text())==m
    else:path.write_text(out);mp.write_text(json.dumps(m,indent=2)+'\n')
    print(json.dumps(meta))
if __name__=='__main__':main()
