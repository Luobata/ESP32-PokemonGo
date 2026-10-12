#include "save_bank.h"
#include "esp_partition.h"
static const esp_partition_t *partition(void) {
    const esp_partition_t *p=esp_partition_find_first(ESP_PARTITION_TYPE_DATA,0x41,"pokewalk_store");
    return p&&p->address==SAVE_BANK_PARTITION_AT&&p->size==SAVE_BANK_PARTITION_SIZE?p:NULL;
}
static bool read_bank(uint32_t at,void *out,size_t n) {
    const esp_partition_t *p=partition();return p&&esp_partition_read(p,at,out,n)==ESP_OK;
}
static bool write_bank(uint32_t at,const void *data,size_t n) {
    const esp_partition_t *p=partition();return p&&esp_partition_write(p,at,data,n)==ESP_OK;
}
static bool erase_bank(uint32_t at,size_t n) {
    const esp_partition_t *p=partition();return p&&esp_partition_erase_range(p,at,n)==ESP_OK;
}
const save_bank_io_t *save_bank_platform(void) {
    static const save_bank_io_t io={read_bank,write_bank,erase_bank};
    return partition()?&io:NULL;
}
