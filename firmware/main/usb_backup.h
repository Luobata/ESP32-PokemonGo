#pragma once
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#define USB_BACKUP_BYTES 0x6000
#define USB_BACKUP_EXTENDED_BYTES 0xc000 // Published v2/V23 envelope
#define USB_BACKUP_WAREHOUSE_BYTES 0x12000 // v4/V28: NVS + 48 KiB bank
#define USB_BACKUP_EXPANDED_BYTES 0xe000 // v3/V24: NVS + full 32 KiB bank
// All calls are serialized by the UI lock. The snapshot callback must quiesce
// other NVS writers until the complete partition has been copied.
typedef enum { USB_BACKUP_IDLE, USB_BACKUP_NO_HOST, USB_BACKUP_SENDING,
               USB_BACKUP_WAIT_ACK, USB_BACKUP_DONE, USB_BACKUP_FAILED, USB_RESTORE_OFFER, USB_RESTORE_RECEIVING, USB_RESTORE_STAGED } usb_backup_state_t;
void usb_backup_init(bool (*snapshot)(uint8_t *, size_t), void (*emit)(const char *),
                     const char *device, const char *firmware, unsigned save_version);
bool usb_backup_feed(char c); // reserves every !-prefixed line, including malformed commands
void usb_backup_tick(uint32_t now_ms);
void usb_backup_request(void); // only the physical/menu confirmation initiates export
usb_backup_state_t usb_backup_state(void);
void usb_backup_device_start(void);

void usb_backup_restore_hooks(bool (*stage)(const uint8_t *,size_t,unsigned),void (*restart)(void),int boot_result,uint32_t boot_crc);
typedef enum { USB_RESTORE_DETAIL_NONE, USB_RESTORE_DETAIL_LAYOUT,
 USB_RESTORE_DETAIL_FLASH, USB_RESTORE_DETAIL_NVS, USB_RESTORE_DETAIL_MEMORY,
 USB_RESTORE_DETAIL_READ, USB_RESTORE_DETAIL_VERSION, USB_RESTORE_DETAIL_CONTENT,
 USB_RESTORE_DETAIL_CHECKPOINT, USB_RESTORE_DETAIL_JOURNAL } usb_restore_detail_t;
// Optional detail after the existing ERROR STAGE prefix; old tools still reject safely.
void usb_backup_restore_detail(usb_restore_detail_t detail);
void usb_backup_import_mode(bool enabled); // device must explicitly enter import screen
bool usb_backup_import_mode_active(void);
void usb_backup_restore_confirm(bool accept);
bool usb_backup_restore_before_boot(void);

// V23 uses bounded chunks and an immutable flash snapshot. Legacy callbacks
// remain available for older protocol fixtures; the device always uses streams.
typedef struct {
 bool (*export_begin)(uint32_t *bytes,uint32_t *crc);
 bool (*export_read)(uint32_t at,void *out,size_t size);
 bool (*import_begin)(uint32_t bytes,unsigned version);
 bool (*import_write)(uint32_t at,const void *data,size_t size);
 bool (*import_finish)(uint32_t crc);
 void (*cancel)(void);
} usb_backup_stream_t;
void usb_backup_stream_hooks(const usb_backup_stream_t *hooks);
