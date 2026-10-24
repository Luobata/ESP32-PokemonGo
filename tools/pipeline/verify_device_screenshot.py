#!/usr/bin/env python3
"""Reject incomplete serial captures instead of inventing black display rows."""
from pathlib import Path
import base64,contextlib,io,json,sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'device'))
import screenshot

def shot(fmt='be',height=5):
    parts=[f'@@SHOT 2 {height} rgb565{fmt} 2\n'.encode()]
    for y in range(0,height,2):
        # Red then green, known independently of the screenshot converter.
        pixel=b'\xf8\x00\x07\xe0' if fmt=='be' else b'\x00\xf8\xe0\x07'
        parts.append(f'@@BAND {y}\n'.encode()+base64.b64encode(pixel*min(2,height-y))+b'\n')
    return parts+[b'@@SHOTEND\n']

for fmt in ('be','le'):
    data=screenshot.parse(b''.join(shot(fmt)))
    assert data and data[:2]==(2,5) and data[3]==3
    assert data[2]==[bytes((255,0,0,0,255,0))]*5
parts=shot();first=parts[1]
bad=[
    b''.join(parts[:-1]),                    # no terminal marker
    b''.join(parts[:1]+parts[2:]),           # a whole band missing
    b''.join(parts[:2]+[first]+parts[2:]),    # duplicate band
    b''.join(parts).replace(first,b'@@BAND 0\n+A AH4A==\n'),
    b''.join(parts).replace(first,b'@@BAND 0\n'+base64.b64encode(b'\xf8\x00\x07\xe0')+b'\n'), # valid base64, short bytes
    b''.join(parts).replace(b'@@BAND 2',b'@@BAND 3'),
    b''.join(parts).replace(b'@@BAND 2',b'@@BAND 6'),
    b''.join(parts).replace(b'@@SHOT 2 5',b'@@SHOT 99999999 5'),
]
with contextlib.redirect_stderr(io.StringIO()):
    for data in bad:assert screenshot.parse(data) is None
print(json.dumps({'passed':True,'complete_endian_cases':2,'corrupt_captures_rejected':len(bad),'last_partial_height_supported':True}))
