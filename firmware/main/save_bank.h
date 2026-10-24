#pragma once
#define SAVE_BANK_CURRENT_VERSION 31
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

// All offsets are relative to pokewalk_store. Existing partitions never move.
#define SAVE_BANK_PARTITION_AT 0x380000u
#define SAVE_BANK_PARTITION_SIZE 0x20000u
#define SAVE_BANK_STRIDE 0x10000u
#define SAVE_BANK_LEGACY_STRIDE 0x8000u
#define SAVE_BANK_DATA_AT 0x1000u
#define SAVE_BANK_V23_IMAGE_SIZE 0x6000u
#define SAVE_BANK_V27_IMAGE_SIZE 0x8000u
#define SAVE_BANK_IMAGE_SIZE 0xc000u
#define SAVE_BANK_PAYLOAD_MAX (SAVE_BANK_IMAGE_SIZE-SAVE_BANK_DATA_AT)
// NVS snapshot occupies the two gaps between/after 48 KiB banks.
#define SAVE_BANK_EXPORT_AT 0xc000u
#define SAVE_BANK_EXPORT_SPLIT 0x4000u
#define SAVE_BANK_EXPORT_TAIL 0x1c000u
#define SAVE_BANK_EXPORT_SIZE 0x6000u
_Static_assert(SAVE_BANK_IMAGE_SIZE==SAVE_BANK_EXPORT_AT,"Bank/export overlap");
_Static_assert(SAVE_BANK_EXPORT_TAIL+SAVE_BANK_EXPORT_SIZE-SAVE_BANK_EXPORT_SPLIT<=SAVE_BANK_PARTITION_SIZE,"Snapshot exceeds partition");
uint32_t save_bank_offset(unsigned bank);
unsigned save_bank_next(int active);
#define SAVE_BANK_REF_SIZE 32u
typedef struct { uint8_t bytes[SAVE_BANK_REF_SIZE]; } save_bank_ref_t;
typedef struct {
    bool (*read)(uint32_t at, void *out, size_t size);
    bool (*write)(uint32_t at, const void *data, size_t size);
    bool (*erase)(uint32_t at, size_t size);
} save_bank_io_t;

// References contain schema, length, CRC and generation, never a bank number.
// Copying a backup into either inactive bank therefore preserves its identity.
bool save_bank_ref_valid(const save_bank_ref_t *ref);
uint32_t save_bank_length(const save_bank_ref_t *ref);
bool save_bank_check(const save_bank_io_t *io,unsigned bank,const save_bank_ref_t *ref);
int save_bank_find(const save_bank_io_t *io, const save_bank_ref_t *ref);
bool save_bank_read(const save_bank_io_t *io, const save_bank_ref_t *ref,
                    void *out, size_t capacity);
// Does not commit the NVS reference. Caller MUST hold the save lock, and only
// adopt next after this succeeds and the atomic NVS reference write succeeds.
// committed=NULL is permitted only for a verified legacy/empty NVS state.
bool save_bank_prepare(const save_bank_io_t *io, const save_bank_ref_t *committed,
                       const void *payload, size_t size, save_bank_ref_t *next);

// Platform adapter validates the exact dedicated partition before every use.
const save_bank_io_t *save_bank_platform(void);
// Called under the world save lock during a USB import transaction.
void save_bank_reserve(bool reserved);
