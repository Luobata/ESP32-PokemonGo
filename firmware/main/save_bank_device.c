#include "save_bank.h"
#include "esp_partition.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
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
    const esp_partition_t *p=partition();
    if(!p || at%4096u || n%4096u || at>p->size || n>p->size-at)return false;
    // Give the PCM producer a scheduling point between cache-off erases,
    // including USB snapshot/restore users. No change to atomic commit order.
    for(size_t i=0;i<n;i+=4096u){
        if(esp_partition_erase_range(p,at+i,4096u)!=ESP_OK)return false;
        vTaskDelay(1);
    }
    return true;
}
const save_bank_io_t *save_bank_platform(void) {
    static const save_bank_io_t io={read_bank,write_bank,erase_bank};
    return partition()?&io:NULL;
}
