#pragma once
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <string.h>

// V22 storage envelope, independent of compiler padding: little-endian fields.
// 0 schema, 2 codec magic PWZ1, 6 raw length, 8 payload length, 10 reserved=0,
// 12 raw CRC32. Packets 0..127 copy 1..128 bytes, 128..255 emit 1..128 zeros.
// Every decoded byte (including old padding) is preserved. No heap or big stack.
#define SAVE_STORAGE_VERSION 22
#define SAVE_STORAGE_HEADER 16
static inline unsigned save_le16(const uint8_t *p) {return p[0]|((unsigned)p[1]<<8);}
static inline void save_put16(uint8_t *p,unsigned v) {p[0]=(uint8_t)v;p[1]=(uint8_t)(v>>8);}
static inline uint32_t save_storage_crc(const uint8_t *p,size_t n) {
 uint32_t crc=UINT32_MAX;
 for(size_t i=0;i<n;i++){crc^=p[i];for(unsigned b=0;b<8;b++)crc=(crc>>1)^(0xedb88320u&-(crc&1u));}
 return ~crc;
}
static inline size_t save_storage_encode(uint8_t *out,size_t cap,const void *raw,size_t n) {
 const uint8_t *p=raw;size_t at=0,w=SAVE_STORAGE_HEADER;
 if(!out||!p||n<2||n>UINT16_MAX||cap<w||save_le16(p)!=SAVE_STORAGE_VERSION)return 0;
 while(at<n){
  size_t zeros=0;while(at+zeros<n&&p[at+zeros]==0&&zeros<128)zeros++;
  if(zeros>=3){if(w>=cap)return 0;out[w++]=(uint8_t)(127+zeros);at+=zeros;}
  else{
   size_t begin=at;at++;
   while(at<n&&at-begin<128){if(at+2<n&&!p[at]&&!p[at+1]&&!p[at+2])break;at++;}
   size_t count=at-begin;if(count+1>cap-w)return 0;
   out[w++]=(uint8_t)(count-1);memcpy(out+w,p+begin,count);w+=count;
  }
 }
 if(w-SAVE_STORAGE_HEADER>UINT16_MAX)return 0;
 save_put16(out,SAVE_STORAGE_VERSION);memcpy(out+2,"PWZ1",4);
 save_put16(out+6,(unsigned)n);save_put16(out+8,(unsigned)(w-SAVE_STORAGE_HEADER));save_put16(out+10,0);
 uint32_t crc=save_storage_crc(p,n);for(unsigned i=0;i<4;i++)out[12+i]=(uint8_t)(crc>>(8*i));
 return w;
}
static inline bool save_storage_decode(void *raw,size_t n,const uint8_t *p,size_t len) {
 if(!raw||!p||n<2||n>UINT16_MAX||len<SAVE_STORAGE_HEADER||save_le16(p)!=SAVE_STORAGE_VERSION||memcmp(p+2,"PWZ1",4)||
    save_le16(p+6)!=n||save_le16(p+8)!=len-SAVE_STORAGE_HEADER||save_le16(p+10))return false;
 uint8_t *out=raw;size_t at=SAVE_STORAGE_HEADER,w=0;
 while(at<len){
  unsigned token=p[at++];size_t count=(token&127)+1;
  if(count>n-w)return false;
  if(token&128)memset(out+w,0,count);
  else{if(count>len-at)return false;memcpy(out+w,p+at,count);at+=count;}
  w+=count;
 }
 uint32_t crc=0;for(unsigned i=0;i<4;i++)crc|=(uint32_t)p[12+i]<<(8*i);
 return w==n&&save_le16(out)==SAVE_STORAGE_VERSION&&save_storage_crc(out,n)==crc;
}
