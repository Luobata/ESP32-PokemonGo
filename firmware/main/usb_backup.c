#include "usb_backup.h"
#include "restore_journal.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static bool (*read_snapshot)(uint8_t *, size_t);
static void (*send_line)(const char *);
static bool (*stage_import)(const uint8_t *,size_t,unsigned);
static void (*restart_device)(void);
static char device_id[13], firmware_id[65], session[33], line[448];
static unsigned schema, used, import_version;
static bool reserved, overflow, connected, import_mode, importing;
static uint32_t now, heartbeat, started, request_id, offset, checksum, import_crc, boot_crc;
static int boot_result;
static usb_restore_detail_t restore_detail;
static uint8_t *payload;
static const usb_backup_stream_t *stream;
static uint32_t export_size=USB_BACKUP_BYTES,import_size=USB_BACKUP_BYTES,received_crc;
static uint32_t last_data_ms;
static uint32_t crc_update(uint32_t c,const uint8_t *p,size_t n){
 while(n--){c^=*p++;for(unsigned b=0;b<8;b++)c=(c>>1)^(0xedb88320u&-(c&1u));}return c;
}
void usb_backup_stream_hooks(const usb_backup_stream_t *hooks){stream=hooks;}

static usb_backup_state_t state;
static bool recent(uint32_t since, uint32_t limit) { return (uint32_t)(now-since)<limit; }
static bool busy(void) {return state==USB_BACKUP_SENDING||state==USB_BACKUP_WAIT_ACK||state==USB_RESTORE_RECEIVING||state==USB_RESTORE_STAGED;}
static void fail(void) { if(stream&&stream->cancel)stream->cancel();free(payload);payload=NULL;importing=false;state=USB_BACKUP_FAILED; }
static void error(const char *why) {char b[100];snprintf(b,sizeof(b),"!PWBACKUP ERROR %s\n",why);send_line(b);}
static void stage_error(void) {
 static const char *const reasons[]={"STAGE","STAGE LAYOUT","STAGE FLASH","STAGE NVS","STAGE MEMORY","STAGE READ","STAGE VERSION","STAGE CONTENT","STAGE CHECKPOINT","STAGE JOURNAL"};
 unsigned detail=(unsigned)restore_detail;fail();error(reasons[detail<sizeof(reasons)/sizeof(reasons[0])?detail:0]);
}
void usb_backup_restore_detail(usb_restore_detail_t detail) {restore_detail=detail;}
void usb_backup_init(bool (*snapshot)(uint8_t *,size_t), void (*emit)(const char *),
                     const char *device, const char *firmware, unsigned save_version) {
    if(stream&&stream->cancel)stream->cancel();
    stream=NULL;
    free(payload);payload=NULL;read_snapshot=snapshot;send_line=emit;
    snprintf(device_id,sizeof(device_id),"%s",device);snprintf(firmware_id,sizeof(firmware_id),"%s",firmware);
    schema=save_version;session[0]=0;state=USB_BACKUP_IDLE;connected=import_mode=importing=false;
    stage_import=NULL;restart_device=NULL;boot_result=0;boot_crc=0;
    used=0;reserved=overflow=false;now=heartbeat=started=request_id=offset=checksum=0;
}
void usb_backup_restore_hooks(bool (*stage)(const uint8_t *,size_t,unsigned),void (*restart)(void),int result,uint32_t crc) {
    stage_import=stage;restart_device=restart;boot_result=result;boot_crc=crc;
}
usb_backup_state_t usb_backup_state(void) { return state; }
bool usb_backup_import_mode_active(void) {return import_mode;}
void usb_backup_import_mode(bool enabled) {
    if(busy())return;
    import_mode=enabled;importing=false;state=USB_BACKUP_IDLE;
}
static bool hex(const char *s,size_t n) {
    if(strlen(s)!=n)return false;
    for(unsigned i=0;i<n;i++)if(!((s[i]>='0'&&s[i]<='9')||(s[i]>='a'&&s[i]<='f')))return false;
    return true;
}
static void command(void) {
    char verb[12], token[33], extra;unsigned id;
    if(sscanf(line,"!PWBACKUP %11s %32s %c",verb,token,&extra)==2 && hex(token,32)) {
        if(!strcmp(verb,"HELLO")) {
            if(state==USB_RESTORE_STAGED)return;
            if(busy()||state==USB_RESTORE_OFFER)fail();
            strcpy(session,token);connected=true;heartbeat=now;
            char reply[150];snprintf(reply,sizeof(reply),"!PWBACKUP READY %s %s\n",session,device_id);send_line(reply);
            if(boot_result){snprintf(reply,sizeof(reply),"!PWBACKUP RESTORED %s %d %08lx\n",session,boot_result,(unsigned long)boot_crc);send_line(reply);}
        } else if(!strcmp(verb,"PING")&&!strcmp(token,session))heartbeat=now;
        else if(!strcmp(verb,"BYE")&&!strcmp(token,session)) {
            connected=false;if(state!=USB_RESTORE_STAGED&&(busy()||state==USB_RESTORE_OFFER))fail();
        }
        return;
    }
    if(sscanf(line,"!PWBACKUP %11s %32s %u %c",verb,token,&id,&extra)==3 && !strcmp(token,session)&&id==request_id) {
        if(!strcmp(verb,"ACK")&&state==USB_BACKUP_WAIT_ACK) {
            if(!importing){if(stream&&stream->cancel)stream->cancel();state=USB_BACKUP_DONE;}
            else {
                if(stream&&stream->cancel)stream->cancel();
                if(stream){restore_detail=USB_RESTORE_DETAIL_NONE;if(!stream->import_begin(import_size,import_version)){stage_error();return;}}
                else{payload=malloc(USB_BACKUP_BYTES);if(!payload){fail();error("MEMORY");return;}}
                received_crc=~0u;
                offset=0;state=USB_RESTORE_RECEIVING;started=now;
                char out[80];snprintf(out,sizeof(out),"!PWBACKUP UPLOAD %lu\n",(unsigned long)request_id);send_line(out);
            }
        } else if(!strcmp(verb,"FAIL")&&state!=USB_RESTORE_STAGED&&busy())fail();
        else if(!strcmp(verb,"RFIN")&&state==USB_RESTORE_RECEIVING) {
            if(offset!=import_size||(stream?~received_crc:restore_crc32(payload,USB_BACKUP_BYTES))!=import_crc) {fail();error("CHECKSUM");return;}
            restore_detail=USB_RESTORE_DETAIL_NONE;
            if(stream?!stream->import_finish(import_crc):(!stage_import||!stage_import(payload,USB_BACKUP_BYTES,import_version))){
                stage_error();return;
            }
            free(payload);payload=NULL;state=USB_RESTORE_STAGED;started=now;
            char out[80];snprintf(out,sizeof(out),"!PWBACKUP STAGED %08lx\n",(unsigned long)import_crc);send_line(out);
        }
        return;
    }
    char mac[13],fw[65],crc[9];unsigned version,size;
    if(sscanf(line,"!PWBACKUP OFFER %32s %12s %64s %u %u %8s %c",token,mac,fw,&version,&size,crc,&extra)==6) {
        if(!connected||strcmp(token,session)||!recent(heartbeat,15000))return;
        if(!import_mode||(!stage_import&&!stream)){error("OPEN_IMPORT");return;}
        if(busy()||state==USB_RESTORE_OFFER){error("BUSY");return;}
        if(strcmp(mac,device_id)||!hex(fw,64)||version<5||version>schema||!(((version<=22||!stream)&&size==USB_BACKUP_BYTES)||(stream&&version==23&&size==USB_BACKUP_EXTENDED_BYTES)||(stream&&version>=24&&version<=27&&size==USB_BACKUP_EXPANDED_BYTES)||(stream&&version>=28&&size==USB_BACKUP_WAREHOUSE_BYTES))||!hex(crc,8)){error("INCOMPATIBLE");return;}
        boot_result=0;boot_crc=0; // A new offer invalidates the previous boot receipt.
        import_size=size;import_version=version;import_crc=(uint32_t)strtoul(crc,NULL,16);importing=true;state=USB_RESTORE_OFFER;started=now;send_line("!PWBACKUP OFFERED\n");return;
    }
    unsigned at;char bytes[257];
    if(sscanf(line,"!PWBACKUP RDATA %32s %u %u %256s %c",token,&id,&at,bytes,&extra)==4) {
        if(!connected||strcmp(token,session)||id!=request_id||state!=USB_RESTORE_RECEIVING)return;
        if(at!=offset||offset+128>import_size||!hex(bytes,256)){fail();error("SEQUENCE");return;}
        uint8_t chunk[128];
        for(unsigned i=0;i<128;i++){char pair[3]={bytes[2*i],bytes[2*i+1],0};chunk[i]=(uint8_t)strtoul(pair,NULL,16);}
        if(stream){if(!stream->import_write(offset,chunk,sizeof(chunk))){fail();error("STAGE FLASH");return;}received_crc=crc_update(received_crc,chunk,sizeof(chunk));}
        else memcpy(payload+offset,chunk,sizeof(chunk));
        offset+=128;started=now;char out[80];snprintf(out,sizeof(out),"!PWBACKUP NEXT %lu %lu\n",(unsigned long)request_id,(unsigned long)offset);send_line(out);
    }
}
bool usb_backup_feed(char c) {
    if(!reserved) { if(c!='!')return false;reserved=true;used=0;overflow=false; }
    if(c=='\r'||c=='\n') {
        line[used]=0;if(!overflow&&send_line)command();reserved=false;used=0;return true;
    }
    if(used<sizeof(line)-1)line[used++]=c;else overflow=true;
    return true;
}
void usb_backup_request(void) {
    if(busy())return;
    if((!read_snapshot&&!stream)||!send_line||!connected||!recent(heartbeat,15000)) {state=USB_BACKUP_NO_HOST;return;}
    export_size=USB_BACKUP_BYTES;
    if(stream){if(!stream->export_begin(&export_size,&checksum)){fail();error("SNAPSHOT");return;}}
    else {
        payload=malloc(USB_BACKUP_BYTES);
        if(!payload) {fail();error("MEMORY");return;}
        if(!read_snapshot(payload,USB_BACKUP_BYTES)) {fail();error("SNAPSHOT");return;}
        checksum=restore_crc32(payload,USB_BACKUP_BYTES);
    }
    offset=0;started=now;++request_id;
    if(!request_id)++request_id;
    char out[240];snprintf(out,sizeof(out),"\n!PWBACKUP BEGIN %s %lu %s %s %u %u %u %08lx\n",
       session,(unsigned long)request_id,device_id,firmware_id,schema,0x9000,(unsigned)export_size,(unsigned long)checksum);
    send_line(out);state=USB_BACKUP_SENDING;
}
void usb_backup_restore_confirm(bool accept) {
    if(state!=USB_RESTORE_OFFER)return;
    if(!accept){importing=false;state=USB_BACKUP_IDLE;send_line("!PWBACKUP CANCELLED\n");return;}
    usb_backup_request(); // export current NVS; never receive import before its disk ACK
}
void usb_backup_tick(uint32_t ms) {
    now=ms;
    if(state==USB_RESTORE_STAGED) {if(!recent(started,1000)&&restart_device)restart_device();return;}
    if(!busy()&&state!=USB_RESTORE_OFFER)return;
    if(!recent(started,60000)||!connected||!recent(heartbeat,15000)) {fail();error("TIMEOUT");return;}
    if(state!=USB_BACKUP_SENDING)return;
    // dbg polls once per received character as well as on its idle timer.
    // Heartbeats must not turn into a burst of DATA lines that overflows the
    // USB console while the host is processing them. Do not catch up in bursts.
    if(offset&&recent(last_data_ms,20))return;
    last_data_ms=now;
    char out[330];int n=snprintf(out,sizeof(out),"!PWBACKUP DATA %lu %lu ",(unsigned long)request_id,(unsigned long)offset);
    uint8_t chunk[128];
    if(stream){if(!stream->export_read(offset,chunk,sizeof(chunk))){fail();error("SNAPSHOT");return;}}
    else memcpy(chunk,payload+offset,sizeof(chunk));
    for(unsigned i=0;i<128;i++)n+=snprintf(out+n,sizeof(out)-n,"%02x",chunk[i]);
    out[n++]='\n';out[n]=0;send_line(out);offset+=128;
    if(offset==export_size) {
        snprintf(out,sizeof(out),"!PWBACKUP END %lu %08lx\n",(unsigned long)request_id,(unsigned long)checksum);send_line(out);
        free(payload);payload=NULL;state=USB_BACKUP_WAIT_ACK;started=now;
    }
}
