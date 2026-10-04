#!/usr/bin/env python3
"""Real ESP-IDF NVS + production staging/journal/save decode, on RAM-backed flash.

Requires the ESP-IDF used for firmware (IDF_PATH or --idf-path), C/C++ and zlib.
No device access. ROM CRC, flash I/O, logs and locks are host adapters; NVS blob
selection, staging mount, save migration/validation and restore journal are real.
"""
from pathlib import Path
import argparse
import os
import subprocess
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[2]
headers={
 'sdkconfig.h':'#define CONFIG_NVS_ASSERT_ERROR_CHECK 1\n',
 'esp_attr.h':'#define IDF_DEPRECATED(x)\n#define IRAM_ATTR\n',
 'esp_log.h':'#define ESP_LOGE(...) ((void)0)\n#define ESP_LOGW(...) ((void)0)\n#define ESP_LOGI(...) ((void)0)\n#define ESP_LOGD(...) ((void)0)\n#define ESP_LOGV(...) ((void)0)\n#define ESP_LOG_LEVEL(...) ((void)0)\n',
 'esp_heap_caps.h':'#include <stdlib.h>\n#define MALLOC_CAP_INTERNAL 0\n#define MALLOC_CAP_8BIT 0\n#define heap_caps_malloc(n,c) malloc(n)\n#define heap_caps_calloc(n,s,c) calloc(n,s)\n#define heap_caps_free free\n',
 'spi_flash_mmap.h':'#define SPI_FLASH_SEC_SIZE 4096\n#define ESP_ERR_FLASH_OP_FAIL 0x6001\n',
 'bsd/string.h':'''#include <string.h>
#ifndef __APPLE__
#define strlcpy pw_host_strlcpy
static inline size_t pw_host_strlcpy(char *d,const char *s,size_t n){size_t len=strlen(s);if(n){size_t k=len<n-1?len:n-1;memcpy(d,s,k);d[k]=0;}return len;}
#endif
''',
 'esp_rom_crc.h':'''#include <stdint.h>
#include <stddef.h>
#include <zlib.h>
static inline uint32_t esp_rom_crc32_le(uint32_t c,const uint8_t *p,uint32_t n){return crc32(c,p,n);}
''',
 'esp_partition.h':'''#pragma once
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include "esp_err.h"
#define ESP_ENCRYPT_BLOCK_SIZE 16
#define ESP_PARTITION_TYPE_DATA 1
#define ESP_PARTITION_SUBTYPE_DATA_NVS 2
#define ESP_PARTITION_SUBTYPE_DATA_NVS_KEYS 4
#ifdef __cplusplus
extern "C" {
#endif
typedef struct {unsigned type,subtype,address,size;char label[17];bool encrypted,readonly;} esp_partition_t;
const esp_partition_t *esp_partition_find_first(unsigned,unsigned,const char*);
esp_err_t esp_partition_read(const esp_partition_t*,size_t,void*,size_t);
esp_err_t esp_partition_write(const esp_partition_t*,size_t,const void*,size_t);
esp_err_t esp_partition_read_raw(const esp_partition_t*,size_t,void*,size_t);
esp_err_t esp_partition_write_raw(const esp_partition_t*,size_t,const void*,size_t);
esp_err_t esp_partition_erase_range(const esp_partition_t*,size_t,size_t);
uint32_t esp_partition_get_main_flash_sector_size(void);
#ifdef __cplusplus
}
#endif
'''}

headers.update({
 'esp_app_desc.h':'#include <stdint.h>\ntypedef struct {uint8_t app_elf_sha256[32];} esp_app_desc_t;\nconst esp_app_desc_t *esp_app_get_description(void);\n',
 'esp_mac.h':'#define ESP_MAC_WIFI_STA 0\nesp_err_t esp_read_mac(uint8_t*,unsigned);\n',
 'esp_system.h':'void esp_restart(void);\n',
})

def run(idf):
 idf=Path(idf)/'components';nvs=idf/'nvs_flash'
 if not (nvs/'src/nvs_api.cpp').is_file():raise SystemExit('Set IDF_PATH or --idf-path to ESP-IDF v5.5.3; test was not run')
 with tempfile.TemporaryDirectory(prefix='pokewalk-real-nvs-') as d:
  t=Path(d)
  for name,content in headers.items():
   p=t/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(content)
  incs=[t,nvs/'include',nvs/'private_include',nvs/'src',idf/'esp_common/include',idf/'esp_rom/include',ROOT/'firmware/main',ROOT/'firmware/components/bsp/include']
  flags=['-DLINUX_TARGET=1','-DESP_PLATFORM','-DHOST_BUILD','-O1','-g','-fsanitize=address,undefined','-ffunction-sections','-fdata-sections']+[x for i in incs for x in ['-I',str(i)]]
  sources=['nvs_api','nvs_item_hash_list','nvs_page','nvs_pagemanager','nvs_storage','nvs_handle_simple','nvs_handle_locked','nvs_partition','nvs_partition_lookup','nvs_partition_manager','nvs_types','nvs_platform']
  game=['save','restore_journal','party','encounter','exploration','nurture','exp','items','evolution','trainer','combat','battle','assets','pokemon_names','dungeon','dungeon_rewards']
  for name in sources:
   subprocess.run(['c++','-std=c++17',*flags,'-c',str(nvs/'src'/f'{name}.cpp'),'-o',str(t/f'{name}.o')],check=True)
  for name in game+['driver']:
   src=ROOT/'tools/pipeline/fixtures/nvs_restore_driver.c' if name=='driver' else ROOT/'firmware/main'/f'{name}.c'
   subprocess.run(['cc','-std=gnu11',*flags,'-c',str(src),'-o',str(t/f'{name}.o')],check=True)
  asm=[]
  for name in ('gen1.bin','gen1_front.bin','gen1_back.bin','palettes.bin','font16.bin','moves.bin','ui.bin'):
   sy='_binary_'+name.replace('.','_');asm+=['.balign 4',f'.global {sy}_start',f'.global {sy}_end',f'{sy}_start:',f'.incbin "{ROOT/"assets"/name}"',f'{sy}_end:']
  (t/'assets.S').write_text('\n'.join(asm)+'\n')
  subprocess.run(['cc','-c',str(t/'assets.S'),'-o',str(t/'asset_data.o')],check=True)
  subprocess.run(['c++','-fsanitize=address,undefined',*[str(t/f'{n}.o') for n in sources+game+['driver','asset_data']],'-lz','-Wl,-dead_strip' if sys.platform=='darwin' else '-Wl,--gc-sections','-o',str(t/'test')],check=True)
  subprocess.run([str(t/'test')],check=True)

if __name__=='__main__':
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--idf-path',default=os.environ.get('IDF_PATH',str(Path.home()/'esp/esp-idf')))
 run(parser.parse_args().idf_path)
