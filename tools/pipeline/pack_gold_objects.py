#!/usr/bin/env python3
"""Share immutable OAM shapes; keep every occurrence's position and order."""
from __future__ import annotations

import hashlib
import re
import struct


def pack_objects(rows: list[tuple[int, ...]]) -> tuple[str, dict]:
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
    text += table('gold_object_ref_t', 'gold_object_refs', refs)
    text += '''static inline gold_object_t gold_object_at(unsigned index) {
    const gold_object_ref_t *ref = &gold_object_refs[index];
    const gold_shape_t *shape = &gold_shapes[ref->shape];
    return (gold_object_t){shape->tile,ref->x,ref->y,shape->flags,shape->dx,shape->dy};
}
'''
    canonical = b''.join(struct.pack('<HBBBbb', *row) for row in rows)
    return text, {'objects': len(rows), 'shapes': len(shapes),
                  'canonical_sha256': hashlib.sha256(canonical).hexdigest(),
                  'original_bytes': len(rows)*8, 'indexed_bytes': len(refs)*4+len(shapes)*6}


def compact_header(header: str) -> tuple[str, dict]:
    """Repack a checked-in source-derived header without rerunning the ROM."""
    pattern = r'static const gold_object_t gold_objects\[\] = \{(.*?)\};\n'
    match = re.search(pattern, header, re.S)
    if not match:
        raise ValueError('expected an unpacked source-derived OAM table')
    rows = [tuple(map(int, row.split(','))) for row in re.findall(r'\{([^{}]+)\}', match[1])]
    packed, manifest = pack_objects(rows)
    return header[:match.start()] + packed + header[match.end():], manifest
