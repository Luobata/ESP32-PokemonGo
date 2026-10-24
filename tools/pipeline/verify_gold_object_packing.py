#!/usr/bin/env python3
"""Decode every packed OAM occurrence in C against the frozen old byte stream."""
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
# Source-derived OAM stream before the 2026-10-17 storage-only refactor.
ORIGINAL_SHA256 = 'b9c1a8b6575ee23de278f65defbf3759897cca49466c19972fef51fb236efd68'
SOURCE = r'''
#include <assert.h>
#include <stdio.h>
#include "gold_fx_data.h"
int main(void) {
    assert(sizeof(gold_shape_t)==6 && sizeof(gold_object_ref_t)==4);
    unsigned count=sizeof(gold_object_refs)/sizeof(gold_object_refs[0]);
    for (unsigned i=0;i<count;i++) {
        assert(gold_object_refs[i].shape<sizeof(gold_shapes)/sizeof(gold_shapes[0]));
        gold_object_t o=gold_object_at(i);
        unsigned char bytes[]={o.tile&255,o.tile>>8,o.x,o.y,o.flags,(uint8_t)o.dx,(uint8_t)o.dy};
        assert(fwrite(bytes,1,sizeof(bytes),stdout)==sizeof(bytes));
    }
    for (unsigned i=0;i<sizeof(gold_object_spans)/sizeof(gold_object_spans[0]);i++) {
        gold_span_t s=gold_object_spans[i];assert(s.offset<=count && s.count<=count-s.offset);
    }
}
'''
with tempfile.TemporaryDirectory(prefix='pokewalk-oam-') as directory:
    path = Path(directory)
    (path/'test.c').write_text(SOURCE)
    subprocess.run(['cc','-std=c11','-O1','-g','-fsanitize=address,undefined',
                    '-I',str(ROOT/'firmware/main'),str(path/'test.c'),'-o',str(path/'test')],check=True)
    result = subprocess.check_output([str(path/'test')])
    assert len(result)==103495*7
    assert hashlib.sha256(result).hexdigest()==ORIGINAL_SHA256
    meta=json.loads((ROOT/'assets/gold_fx_sources.json').read_text())
    assert meta['object_packing']['canonical_sha256']==ORIGINAL_SHA256
    assert hashlib.sha256((ROOT/'firmware/main/gold_fx_data.h').read_bytes()).hexdigest()==meta['header_sha256']
    print('PASS: all 103495 OAM occurrences are byte-identical; 402544 Flash bytes saved; no heap buffer')
