#!/usr/bin/env python3
"""Enforce the legacy codec and V23 streaming target compiler stack budget.

Needs a built firmware compile_commands.json. This does not measure live heap
fragmentation or task high-water marks; physical-device checks remain separate.
"""
import json
import re
from pathlib import Path
import shlex
import subprocess
import tempfile

ROOT=Path(__file__).resolve().parents[2]
entries=json.loads((ROOT/'firmware/build/compile_commands.json').read_text())
entry=next(e for e in entries if e['file'].endswith('/main/save.c'))
budgets={'save_storage_decode':64,'save_decode':128,'save_decode_legacy':512,
         'save_write':160,'save_read_status':64,'save_validate_world':32}
with tempfile.TemporaryDirectory() as tmp:
    obj=Path(tmp)/'save.o'
    args=shlex.split(entry['command']);args[args.index('-o')+1]=str(obj);args.append('-fstack-usage')
    subprocess.run(args,cwd=entry['directory'],check=True,capture_output=True,text=True)
    frames={}
    for line in (Path(tmp)/'save.su').read_text().splitlines():
        source,size,kind=line.split('\t');name=source.rsplit(':',1)[-1]
        if name in budgets:
            assert kind=='static' and int(size)<=budgets[name],line
            frames[name]=int(size)
    assert set(frames)==set(budgets),frames
    nm=Path(args[0]).with_name('riscv32-esp-elf-nm')
    symbols=subprocess.check_output([str(nm),'-S',str(obj)],text=True)
    workspace=next(x.split() for x in symbols.splitlines() if x.endswith(' storage_buf'))
    assert int(workspace[1],16)==7792,workspace
    objdump=nm.with_name('riscv32-esp-elf-objdump')
    sections=subprocess.check_output([str(objdump),'-t',str(obj)],text=True)
    assert re.search(r'\.rtc_noinit\.\d+\s+00001e70\s+storage_buf',sections),sections
    linked=subprocess.check_output([str(nm),'-S',str(ROOT/'firmware/build/PokeWalk.elf')],text=True)
    address=int(next(x.split()[0] for x in linked.splitlines() if x.endswith(' storage_buf')),16)
    assert 0x50000000<=address and address+7792<=0x50001fd8,hex(address)
    size=nm.with_name('riscv32-esp-elf-size')
    sizes=subprocess.check_output([str(size),'-A',str(ROOT/'firmware/build/PokeWalk.elf')],text=True)
    rtc=sum(int(x.split()[1]) for x in sizes.splitlines() if x.startswith('.rtc'))
    assert rtc<=8192-256,rtc
    assert not any(x.split()[-1] in ('malloc','calloc','realloc','heap_caps_malloc','heap_caps_calloc','alloca') for x in symbols.splitlines())
    print(json.dumps({'target':'esp32c3','stack_frames':frames,'codec_rtc_bytes':7792,'main_dram_codec_bytes':0,'rtc_used_bytes':rtc,'rtc_free_bytes':8192-rtc,
                      'new_dynamic_allocations':0,'runtime_heap_measured':False,'passed':True}))

# Expanded storage must stay chunked. Catch accidental full-party locals and
# fresh heap workspaces in the real target build, not just in host test binaries.
module_limits={'save_bank':384,'save_bank_device':64,'usb_backup_device':384,
               'restore_journal':448,'world':512,'play_capture':256,'play_party':512,'usb_backup':768}
module_frames={}
for module,limit in module_limits.items():
    entry=next(e for e in entries if e['file'].endswith('/main/'+module+'.c'))
    with tempfile.TemporaryDirectory() as tmp:
        obj=Path(tmp)/'unit.o';args=shlex.split(entry['command']);args[args.index('-o')+1]=str(obj);args.append('-fstack-usage')
        subprocess.run(args,cwd=entry['directory'],check=True,capture_output=True,text=True)
        frames={}
        for line in (Path(tmp)/'unit.su').read_text().splitlines():
            source,size,kind=line.split('\t');assert kind=='static' and int(size)<=limit,(module,line)
            frames[source.rsplit(':',1)[-1]]=int(size)
        module_frames[module]=max(frames.values())
        if module in ('save_bank','save_bank_device','usb_backup_device','restore_journal'):
            symbols=subprocess.check_output([str(nm),'-S',str(obj)],text=True)
            assert not any(x.split()[-1] in ('malloc','calloc','realloc','heap_caps_malloc','heap_caps_calloc','alloca') for x in symbols.splitlines()),module
print(json.dumps({'expanded_storage_max_frame':module_frames,'new_storage_heap_allocations':0,'runtime_stack_measured':False,'passed':True}))
