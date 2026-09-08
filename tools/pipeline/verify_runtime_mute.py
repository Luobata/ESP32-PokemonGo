#!/usr/bin/env python3
"""Exercise real SFX worker and BSP, replacing only device and scheduler APIs."""
from pathlib import Path
import subprocess,tempfile
import verify_silent_boot as base
ROOT=base.ROOT
s=base.DRIVER
s=s[:s.index('int main(int argc')]
s=s.replace('#include <stdio.h>','#include <stdio.h>\n#include <setjmp.h>\nstatic jmp_buf done;static int step,closed;static bool muted=true,sleeping;static unsigned desired_volume=55,last_volume,last_effect=999;static void (*worker)(void *);')
s=s.replace('bool audio_settings_muted(void) {return false;}','bool audio_settings_muted(void) {return muted;}').replace('bool screen_idle_is_off(void) {return false;}','bool screen_idle_is_off(void) {return sleeping;}')
s=s.replace('uint8_t audio_settings_volume(void) {return 55;}','uint8_t audio_settings_volume(void) {return desired_volume;}').replace('(void)d;(void)volume;volumes++;','(void)d;last_volume=volume;volumes++;').replace('(void)m;(void)id;}\nvoid sound_mixer_move', 'm->active=true;last_effect=id;}\nvoid sound_mixer_move')
s=s.replace('(void)m;memset(out,0,n*2);','m->active=false;memset(out,0,n*2);')
s=s.replace('(void)fn;(void)name;', 'worker=fn;(void)name;').replace('int esp_codec_dev_close(void *d) { (void)d;return 0; }','int esp_codec_dev_close(void *d) { (void)d;closed++;return 0; }')
s=s.replace('void sound_mixer_music(sound_mixer_t *m,music_id_t id) {(void)m;(void)id;}','void sound_mixer_music(sound_mixer_t *m,music_id_t id) {m->music.id=id;}')
s=s.replace('(void)q;(void)id;(void)wait;abort();','''(void)q;(void)id;(void)wait;
 switch(++step){
 case 1:assert(!formats&&!output&&!codec);break;
 case 2:assert(!formats&&!output&&!codec);muted=false;break;
 case 3:assert(formats==1&&output==1&&last_volume==55);desired_volume=100;break;
 case 4:assert(output==2&&last_volume==100);muted=true;break;
 case 5:assert(closed==1&&output==2);muted=false;break;
 case 6:assert(formats==2&&output==3);sleeping=true;break;
 case 7:assert(closed==2&&output==3);sfx_encounter(4,false);sfx_encounter(1,true);sfx_encounter(1,false);break;
 case 8:assert(formats==3&&output==4&&last_effect==SFX_SHINY);break;
 case 9:assert(closed==3&&output==4);muted=true;sfx_encounter(5,true);break;
 default:assert(formats==3&&output==4&&closed==3);longjmp(done,1);
 }return 0;''')
s+='''int main(void){assert(bsp_audio_boot_quiet()==0);sfx_start();sfx_music_play(MUSIC_HOME);assert(worker);if(!setjmp(done))worker(0);puts("PASS: muted boot creates no codec; unmute opens; mute/sleep close; live volume changes; sleep alert prioritizes shiny and closes codec; mute suppresses alerts");return 0;}\n'''
with tempfile.TemporaryDirectory() as d:
 t=Path(d);(t/'platform.h').write_text(base.PLATFORM);(t/'driver.c').write_text(s)
 for n in ('esp_err.h','sdkconfig.h','driver/gpio.h','driver/i2c_master.h','driver/i2s_std.h','esp_codec_dev.h','esp_codec_dev_defaults.h','es8311_codec.h','esp_log.h','esp_heap_caps.h','esp_system.h','esp_timer.h','freertos/FreeRTOS.h','freertos/queue.h','freertos/task.h'):
  p=t/n;p.parent.mkdir(parents=True,exist_ok=True);p.write_text('#include "platform.h"\n')
 # Use the exact established mocked board boundary from the BSP test.
 txt=Path(base.__file__).read_text();pins=txt.split("(tmp/'bsp_pins.h').write_text('''",1)[1].split("''')",1)[0];(t/'bsp_pins.h').write_text(pins)
 (t/'bsp_i2c.h').write_text('#include "platform.h"\nesp_err_t bsp_i2c_init(void);void *bsp_i2c_bus(void);\n')
 (t/'bsp_audio.c').write_text((base.BSP/'src/bsp_audio.c').read_text())
 cmd=['cc','-std=c11','-O1','-Wall','-Wextra','-Werror','-Wno-unused-function','-Wno-unused-variable','-fsanitize=address,undefined','-DCONFIG_POKEWALK_SILENT_BOOT=0','-DTEST_PA=-1','-I',str(t),'-I',str(base.BSP/'include'),'-I',str(base.MAIN),str(t/'driver.c'),str(t/'bsp_audio.c'),str(base.MAIN/'sfx.c'),'-o',str(t/'probe')]
 r=subprocess.run(cmd,capture_output=True,text=True);assert not r.returncode,r.stderr
 r=subprocess.run([str(t/'probe')],capture_output=True,text=True,timeout=10);assert not r.returncode,r.stderr;print(r.stdout)
