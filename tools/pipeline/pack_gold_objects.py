#!/usr/bin/env python3
"""Share immutable OAM shapes; keep every occurrence's position and order."""
from __future__ import annotations

import hashlib
import re
import struct
from collections import defaultdict


def pack_objects(rows: list[tuple[int, ...]], spans=None) -> tuple[str, dict]:
    """Deduplicate shapes/adjacent pairs; optionally remap span offsets in place.

    Span packing shares exact subsequences only. It never edits a frame, object,
    palette, timeline or ordering; both levels remain random-access Flash tables.
    """
    original=rows
    if spans is not None:
        sequences=[tuple(rows[a:a+n]) for a,n in spans]
        prefixes=defaultdict(set)
        for i,seq in enumerate(sequences):
            for n in range(1,len(seq)+1):prefixes[seq[:n]].add(i)
        rows=[];positions=defaultdict(list);todo=set(range(len(sequences)));mapped={}
        max_length=max(map(len,sequences),default=0)
        while todo:
            chosen=None;overlap=0
            for n in range(min(max_length,len(rows)),0,-1):
                matches=prefixes[tuple(rows[-n:])]&todo
                if matches:chosen=min(matches,key=lambda i:(-len(sequences[i]),i));overlap=n;break
            if chosen is None:chosen=min(todo,key=lambda i:(-len(sequences[i]),i))
            seq=sequences[chosen];todo.remove(chosen)
            reuse=next((p for p in positions[seq[0]] if tuple(rows[p:p+len(seq)])==seq),None) if seq else 0
            if reuse is not None:mapped[chosen]=reuse;continue
            mapped[chosen]=len(rows)-overlap
            for value in seq[overlap:]:positions[value].append(len(rows));rows.append(value)
        assert all(tuple(rows[mapped[i]:mapped[i]+len(seq)])==seq for i,seq in enumerate(sequences))
        spans[:]=[(mapped[i],len(seq)) for i,seq in enumerate(sequences)]
    shapes, ids, refs = [], {}, []
    for tile, x, y, flags, dx, dy in rows:
        if not (0 <= tile <= 65535 and all(0 <= v <= 255 for v in (x, y, flags))
                and all(-128 <= v <= 127 for v in (dx, dy))):
            raise ValueError('OAM field is outside its original storage range')
        shape = (tile, flags, dx, dy)
        if shape not in ids:
            if len(shapes) >= 65536:
                raise ValueError('OAM shape dictionary exceeds uint16')
            ids[shape] = len(shapes)
            shapes.append(shape)
        refs.append((ids[shape], x, y))
    def table(ctype, name, values):
        return f'static const {ctype} {name}[] = {{\n' + ''.join(
            ' {' + ','.join(map(str, row)) + '},\n' for row in values) + '};\n'
    text = ('typedef struct { uint16_t tile; uint8_t flags; int8_t dx,dy; } gold_shape_t;\n'
            'typedef struct { uint16_t shape; uint8_t x,y; } gold_object_ref_t;\n')
    text += table('gold_shape_t', 'gold_shapes', shapes)
    pairs, pair_ids, blocks=[],{},[]
    for i in range(0,len(refs),2):
        pair=tuple(refs[i:i+2]);pair=pair if len(pair)==2 else pair+((0,0,0),)
        if pair not in pair_ids:pair_ids[pair]=len(pairs);pairs.append(pair)
        blocks.append((pair_ids[pair],))
    assert len(pairs)<65536
    text += f'enum {{ GOLD_OBJECT_COUNT = {len(refs)} }};\n'
    text += table('gold_object_ref_t', 'gold_object_refs', [ref for pair in pairs for ref in pair])
    text += 'static const uint16_t gold_object_blocks[] = {\n'
    text += '\n'.join(','.join(str(b[0]) for b in blocks[i:i+24])+',' for i in range(0,len(blocks),24))+'\n};\n'
    text += '''static inline gold_object_t gold_object_at(unsigned index) {
    const gold_object_ref_t *ref = &gold_object_refs[gold_object_blocks[index/2]*2+index%2];
    const gold_shape_t *shape = &gold_shapes[ref->shape];
    return (gold_object_t){shape->tile,ref->x,ref->y,shape->flags,shape->dx,shape->dy};
}
'''
    canonical = b''.join(struct.pack('<HBBBbb', *row) for row in original)
    return text, {'objects': len(original), 'shapes': len(shapes), 'stored_occurrences':len(rows),'pairs':len(pairs),
                  'canonical_sha256': hashlib.sha256(canonical).hexdigest(),
                  'original_bytes': len(original)*8, 'indexed_bytes': len(pairs)*8+len(blocks)*2+len(shapes)*6}


def compact_header(header: str) -> tuple[str, dict]:
    """Repack a checked-in source-derived header without rerunning the ROM."""
    pattern = r'static const gold_object_t gold_objects\[\] = \{(.*?)\};\n'
    match = re.search(pattern, header, re.S)
    if not match:
        raise ValueError('expected an unpacked source-derived OAM table')
    rows = [tuple(map(int, row.split(','))) for row in re.findall(r'\{([^{}]+)\}', match[1])]
    packed, manifest = pack_objects(rows)
    return header[:match.start()] + packed + header[match.end():], manifest
