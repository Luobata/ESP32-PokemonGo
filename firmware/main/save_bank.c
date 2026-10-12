#include "save_bank.h"
#include "save_storage.h"
#include <string.h>

static uint32_t rd32(const uint8_t *p) {
    return (uint32_t)p[0]|((uint32_t)p[1]<<8)|((uint32_t)p[2]<<16)|((uint32_t)p[3]<<24);
}
static void wr32(uint8_t *p,uint32_t v) { for(unsigned i=0;i<4;i++)p[i]=(uint8_t)(v>>(8*i)); }
static uint32_t crc_update(uint32_t c,const uint8_t *p,size_t n) {
    while(n--){c^=*p++;for(unsigned i=0;i<8;i++)c=(c>>1)^(0xedb88320u&-(c&1u));}return c;
}
uint32_t save_bank_length(const save_bank_ref_t *ref) { return ref?rd32(ref->bytes+8):0; }
bool save_bank_ref_valid(const save_bank_ref_t *ref) {
    if(!ref)return false;
    const uint8_t *p=ref->bytes;uint32_t n=save_bank_length(ref);
    return save_le16(p)==23&&!memcmp(p+2,"PWR1",4)&&!save_le16(p+6)&&
        n>=2&&n<=SAVE_BANK_PAYLOAD_MAX&&(rd32(p+16)||rd32(p+20))&&
        !rd32(p+24)&&rd32(p+28)==save_storage_crc(p,28);
}
static bool bank_valid(const save_bank_io_t *io,unsigned bank,const save_bank_ref_t *ref) {
    save_bank_ref_t check;uint8_t buf[256];uint32_t crc=~0u,n=save_bank_length(ref);
    uint32_t at=bank*SAVE_BANK_STRIDE;
    if(!io->read(at,&check,sizeof(check))||memcmp(&check,ref,sizeof(check)))return false;
    for(uint32_t i=0;i<n;i+=sizeof(buf)){
        size_t count=n-i<sizeof(buf)?n-i:sizeof(buf);
        if(!io->read(at+SAVE_BANK_DATA_AT+i,buf,count))return false;
        if(!i&&save_le16(buf)!=23)return false;
        crc=crc_update(crc,buf,count);
    }
    return ~crc==rd32(ref->bytes+12);
}
bool save_bank_check(const save_bank_io_t *io,unsigned bank,const save_bank_ref_t *ref) {
 return io&&io->read&&bank<2&&save_bank_ref_valid(ref)&&bank_valid(io,bank,ref);
}
int save_bank_find(const save_bank_io_t *io,const save_bank_ref_t *ref) {
    if(!io||!io->read||!save_bank_ref_valid(ref))return -1;
    for(unsigned i=0;i<2;i++)if(bank_valid(io,i,ref))return (int)i;
    return -1;
}
bool save_bank_read(const save_bank_io_t *io,const save_bank_ref_t *ref,void *out,size_t capacity) {
    int bank=save_bank_find(io,ref);size_t size=save_bank_length(ref);
    if(bank<0||!out||capacity<size)return false;
    if(!io->read(bank*SAVE_BANK_STRIDE+SAVE_BANK_DATA_AT,out,size))return false;
    return save_storage_crc(out,size)==rd32(ref->bytes+12);
}
bool save_bank_prepare(const save_bank_io_t *io,const save_bank_ref_t *committed,
                       const void *payload,size_t size,save_bank_ref_t *next) {
    if(!io||!io->read||!io->write||!io->erase||!payload||!next||size<2||
        size>SAVE_BANK_PAYLOAD_MAX||save_le16(payload)!=23)return false;
    int active=committed?save_bank_find(io,committed):-1;
    if(committed&&active<0)return false; // Never recycle an unverified active save.
    uint64_t sequence=committed?((uint64_t)rd32(committed->bytes+20)<<32)|rd32(committed->bytes+16):0;
    if(sequence==UINT64_MAX)return false;
    sequence++;
    save_bank_ref_t ref={{0}};save_put16(ref.bytes,23);memcpy(ref.bytes+2,"PWR1",4);
    wr32(ref.bytes+8,(uint32_t)size);wr32(ref.bytes+12,save_storage_crc(payload,size));
    wr32(ref.bytes+16,(uint32_t)sequence);wr32(ref.bytes+20,(uint32_t)(sequence>>32));
    wr32(ref.bytes+28,save_storage_crc(ref.bytes,28));
    unsigned bank=active<0?0:1u-(unsigned)active;uint32_t at=bank*SAVE_BANK_STRIDE;
    if(!io->erase(at,SAVE_BANK_STRIDE))return false;
    const uint8_t *p=payload;uint8_t check[256];
    for(size_t i=0;i<size;i+=sizeof(check)){
        size_t count=size-i<sizeof(check)?size-i:sizeof(check);
        if(!io->write(at+SAVE_BANK_DATA_AT+i,p+i,count)||
           !io->read(at+SAVE_BANK_DATA_AT+i,check,count)||memcmp(check,p+i,count))return false;
    }
    // Header is the bank's commit marker; NVS remains the authoritative pointer.
    if(!io->write(at,&ref,sizeof(ref))||!bank_valid(io,bank,&ref))return false;
    *next=ref;return true;
}
