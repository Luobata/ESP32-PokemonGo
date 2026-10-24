#include "save_bank.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>
static unsigned char flash[SAVE_BANK_PARTITION_SIZE],baseline[SAVE_BANK_PARTITION_SIZE];
static unsigned char old[19000],fresh[SAVE_BANK_PAYLOAD_MAX],loaded[SAVE_BANK_PAYLOAD_MAX];
static int calls,fail_at=-1,partial;
static unsigned erased_sectors,written_bytes;
static bool fail(void){return calls++==fail_at;}
static bool read_flash(uint32_t at,void *out,size_t n){assert(at+n<=sizeof(flash));if(fail())return false;memcpy(out,flash+at,n);return true;}
static bool write_flash(uint32_t at,const void *p,size_t n){written_bytes+=n;assert(at+n<=sizeof(flash));bool bad=fail();size_t count=bad?(partial?n/2:0):n;for(size_t i=0;i<count;i++){assert((flash[at+i]&((const unsigned char*)p)[i])==((const unsigned char*)p)[i]);flash[at+i]&=((const unsigned char*)p)[i];}return !bad;}
static bool erase_flash(uint32_t at,size_t n){erased_sectors+=n/4096;assert(at%4096==0&&n%4096==0&&at+n<=sizeof(flash));bool bad=fail();if(!bad||partial)memset(flash+at,255,bad?n/2:n);return !bad;}
static const save_bank_io_t io={read_flash,write_flash,erase_flash};
int main(void){
 memset(flash,255,sizeof(flash));for(unsigned i=0;i<sizeof(old);i++){old[i]=(i*73+41)%251;}for(unsigned i=0;i<sizeof(fresh);i++)fresh[i]=(i*31+17)%253;old[0]=23;fresh[0]=SAVE_BANK_CURRENT_VERSION;old[1]=fresh[1]=0;
 save_bank_ref_t first,next;
 fresh[0]=23;assert(!save_bank_prepare(&io,NULL,fresh,sizeof(fresh),&next));fresh[0]=SAVE_BANK_CURRENT_VERSION+1;assert(!save_bank_prepare(&io,NULL,fresh,sizeof(fresh),&next));fresh[0]=SAVE_BANK_CURRENT_VERSION;
 assert(save_bank_prepare(&io,NULL,old,sizeof(old),&first));assert(save_bank_ref_valid(&first));assert(save_bank_read(&io,&first,loaded,sizeof(loaded)));assert(!memcmp(loaded,old,sizeof(old)));
 // Published V23 bank B lived at 32 KiB. A first V28 write must not erase
 // any of it, including on power interruption at every I/O boundary.
 memcpy(flash+SAVE_BANK_LEGACY_STRIDE,flash+SAVE_BANK_STRIDE,SAVE_BANK_V23_IMAGE_SIZE);
 memset(flash+SAVE_BANK_STRIDE,255,SAVE_BANK_IMAGE_SIZE);
 assert(save_bank_find(&io,&first)==2);
 memcpy(baseline,flash,sizeof(flash));calls=0;assert(save_bank_prepare(&io,&first,fresh,sizeof(fresh),&next));int total=calls;
 for(partial=0;partial<2;partial++)for(int point=0;point<total;point++){
  memcpy(flash,baseline,sizeof(flash));fail_at=point;calls=0;bool ok=save_bank_prepare(&io,&first,fresh,sizeof(fresh),&next);fail_at=-1;
  assert(save_bank_read(&io,&first,loaded,sizeof(loaded)));assert(!memcmp(loaded,old,sizeof(old)));
  if(ok){assert(save_bank_read(&io,&next,loaded,sizeof(loaded)));assert(!memcmp(loaded,fresh,sizeof(fresh)));}
  // NVS reference commit failed: retry against original reference, never erase it.
  assert(save_bank_prepare(&io,&first,fresh,sizeof(fresh),&next));assert(save_bank_read(&io,&first,loaded,sizeof(loaded)));assert(!memcmp(loaded,old,sizeof(old)));
  assert(save_bank_read(&io,&next,loaded,sizeof(loaded)));assert(!memcmp(loaded,fresh,sizeof(fresh)));
 }
 save_bank_ref_t current=next;
 for(unsigned cycle=0;cycle<500;cycle++){fresh[400]=cycle;assert(save_bank_prepare(&io,&current,fresh,sizeof(fresh),&next));current=next;assert(save_bank_read(&io,&current,loaded,sizeof(loaded)));assert(!memcmp(loaded,fresh,sizeof(fresh)));}
 // Prime both banks with the same dense payload. Subsequent transactions
 // must rewrite only changed sectors, while read errors still reject safely.
 assert(save_bank_prepare(&io,&current,fresh,sizeof(fresh),&next));current=next;
 erased_sectors=written_bytes=0;
 assert(save_bank_prepare(&io,&current,fresh,sizeof(fresh),&next));current=next;
 assert(erased_sectors==1&&written_bytes==SAVE_BANK_REF_SIZE);
 memcpy(baseline,flash,sizeof(flash));
 fresh[100]^=0x77;fresh[sizeof(fresh)-1]^=0x53;
 calls=0;erased_sectors=written_bytes=0;
 assert(save_bank_prepare(&io,&current,fresh,sizeof(fresh),&next));
 int sparse_total=calls;
 assert(erased_sectors==3&&written_bytes==8192+SAVE_BANK_REF_SIZE);
 for(partial=0;partial<2;partial++)for(int point=0;point<sparse_total;point++){
  memcpy(flash,baseline,sizeof(flash));fail_at=point;calls=0;
  bool ok=save_bank_prepare(&io,&current,fresh,sizeof(fresh),&next);fail_at=-1;
  assert(save_bank_read(&io,&current,loaded,sizeof(loaded)));
  assert(loaded[100]==(unsigned char)(fresh[100]^0x77));
  if(ok){assert(save_bank_read(&io,&next,loaded,sizeof(loaded)));assert(!memcmp(loaded,fresh,sizeof(fresh)));}
  assert(save_bank_prepare(&io,&current,fresh,sizeof(fresh),&next));
  assert(save_bank_read(&io,&next,loaded,sizeof(loaded)));assert(!memcmp(loaded,fresh,sizeof(fresh)));
 }
 current=next;
 printf("differential save: unchanged=1 header sector; two changed=3 sectors; %d partial/I-O failures PASS\n",sparse_total*2);
 // Identity follows the record, not physical bank index.
 int bank=save_bank_find(&io,&current);assert(bank>=0);memcpy(flash+(1-bank)*SAVE_BANK_STRIDE,flash+bank*SAVE_BANK_STRIDE,SAVE_BANK_STRIDE);memset(flash+bank*SAVE_BANK_STRIDE,255,SAVE_BANK_STRIDE);assert(save_bank_read(&io,&current,loaded,sizeof(loaded)));
 flash[(1-bank)*SAVE_BANK_STRIDE+SAVE_BANK_DATA_AT+42]^=1;assert(!save_bank_read(&io,&current,loaded,sizeof(loaded)));calls=0;assert(!save_bank_prepare(&io,&current,old,sizeof(old),&next));
 printf("bank faults: %d single/partial failures, 500 replacements, corrupt/missing bank rejection PASS\n",2*total);
}
