#!/usr/bin/env python3
"""Check target-compiler stack frames against the ESP32 input-task budget.

Desktop renderer tests run on much larger stacks. Compile with the actual
ESP-IDF target flags so a returned-by-value run copy cannot silently consume
most of the 3072/3584-byte debug/button stack again.
"""
import json,shlex,subprocess,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
entries=json.loads((ROOT/'firmware/build/compile_commands.json').read_text())
entry=next(e for e in entries if e['file'].endswith('/main/dungeon.c'))
budgets={'dungeon_load':128,'dungeon_new':512,'dungeon_resume':256,
         'dungeon_choose':256,'dungeon_finish':256,'dungeon_step':256,
         'dungeon_switch':256,'dungeon_retire':128,'dungeon_abandon':128}
with tempfile.TemporaryDirectory() as tmp:
 args=shlex.split(entry['command']);args[args.index('-o')+1]=str(Path(tmp)/'dungeon.o');args.append('-fstack-usage')
 subprocess.run(args,cwd=entry['directory'],check=True,capture_output=True,text=True)
 frames={}
 for line in (Path(tmp)/'dungeon.su').read_text().splitlines():
  source,amount,kind=line.split('\t');name=source.rsplit(':',1)[-1]
  if name in budgets:
   assert kind=='static',(name,kind)
   frames[name]=int(amount);assert frames[name]<=budgets[name],(name,frames[name],budgets[name])
 assert set(frames)==set(budgets),frames
 print(json.dumps({'target':'esp32c3','stack_frames':frames,'passed':True}))
