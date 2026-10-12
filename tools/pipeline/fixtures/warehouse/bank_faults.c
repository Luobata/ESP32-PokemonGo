#include "save_bank.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>
static unsigned char flash[SAVE_BANK_PARTITION_SIZE],baseline[SAVE_BANK_PARTITION_SIZE];
static unsigned char old[19000],fresh[19000],loaded[19000];
static int calls,fail_at=-1,partial;
static bool fail(void){return calls++==fail_at;}
static bool read_flash(uint32_t at,void *out,size_t n){assert(at+n<=sizeof(flash));if(fail())return false;memcpy(out,flash+at,n);return true;}
static bool write_flash(uint32_t at,const void *p,size_t n){assert(at+n<=sizeof(flash));bool bad=fail();size_t count=bad?(partial?n/2:0):n;for(size_t i=0;i<count;i++){assert((flash[at+i]&((const unsigned char*)p)[i])==((const unsigned char*)p)[i]);flash[at+i]&=((const unsigned char*)p)[i];}return !bad;}
static bool erase_flash(uint32_t at,size_t n){assert(at%4096==0&&n%4096==0&&at+n<=sizeof(flash));bool bad=fail();if(!bad||partial)memset(flash+at,255,bad?n/2:n);return !bad;}
static const save_bank_io_t io={read_flash,write_flash,erase_flash};
int main(void){
 memset(flash,255,sizeof(flash));for(unsigned i=0;i<sizeof(old);i++){old[i]=(i*73+41)%251;fresh[i]=(i*31+17)%253;}old[0]=fresh[0]=23;old[1]=fresh[1]=0;
 save_bank_ref_t first,next;
 assert(save_bank_prepare(&io,NULL,old,sizeof(old),&first));assert(save_bank_ref_valid(&first));assert(save_bank_read(&io,&first,loaded,sizeof(loaded)));assert(!memcmp(loaded,old,sizeof(old)));
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
 // Identity follows the record, not physical bank index.
 int bank=save_bank_find(&io,&current);assert(bank>=0);memcpy(flash+(1-bank)*SAVE_BANK_STRIDE,flash+bank*SAVE_BANK_STRIDE,SAVE_BANK_STRIDE);memset(flash+bank*SAVE_BANK_STRIDE,255,SAVE_BANK_STRIDE);assert(save_bank_read(&io,&current,loaded,sizeof(loaded)));
 flash[(1-bank)*SAVE_BANK_STRIDE+SAVE_BANK_DATA_AT+42]^=1;assert(!save_bank_read(&io,&current,loaded,sizeof(loaded)));calls=0;assert(!save_bank_prepare(&io,&current,old,sizeof(old),&next));
 printf("bank faults: %d single/partial failures, 500 replacements, corrupt/missing bank rejection PASS\n",2*total);
}
