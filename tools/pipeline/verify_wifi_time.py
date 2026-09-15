#!/usr/bin/env python3
"""Compile production Wi-Fi service against a deterministic ESP/network boundary."""
import json,subprocess,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
STUB=r'''
#pragma once
#include <assert.h>
#include <stdint.h>
#include <stdbool.h>
#include <stddef.h>
#include <string.h>
#include <sys/time.h>
#include <sys/socket.h>
#include <netinet/in.h>
typedef int esp_err_t;
#define ESP_OK 0
#define ESP_FAIL -1
#define portMUX_INITIALIZER_UNLOCKED 0
typedef int portMUX_TYPE;
#define portENTER_CRITICAL(p) ((void)(p))
#define portEXIT_CRITICAL(p) ((void)(p))
typedef const char *esp_event_base_t;
#define IP_EVENT ((esp_event_base_t)1)
#define WIFI_EVENT ((esp_event_base_t)2)
#define IP_EVENT_STA_GOT_IP 1
#define WIFI_EVENT_STA_DISCONNECTED 2
#define WIFI_MODE_STA 1
#define WIFI_MODE_APSTA 3
#define WIFI_IF_AP 1
#define WIFI_IF_STA 0
#define WIFI_AUTH_WPA2_PSK 3
#define WIFI_AUTH_OPEN 0
typedef union {struct {unsigned char ssid[32],password[64];int ssid_len,authmode,max_connection,channel;} ap;struct {unsigned char ssid[32],password[64];struct {int authmode;} threshold;} sta;} wifi_config_t;
static int64_t now=1000000;static unsigned connects,saves,restarts,syncs;static int store_error,world_error;static wifi_config_t station;
static int64_t esp_timer_get_time(void){return now;}
static uint32_t esp_random(void){return 123456;}
static int esp_wifi_disconnect(void){return 0;}
static int esp_wifi_set_config(int iface,const wifi_config_t *c){if(iface==WIFI_IF_STA)station=*c;return 0;}
static int esp_wifi_set_mode(int mode){return 0;}
static int esp_wifi_connect(void){connects++;return 0;}
static void *esp_netif_create_default_wifi_ap(void){return (void*)1;}
static int esp_event_handler_register(esp_event_base_t b,int id,void(*cb)(void*,esp_event_base_t,int32_t,void*),void*a){return 0;}
typedef unsigned nvs_handle_t;
#define NVS_READWRITE 1
#define NVS_READONLY 0
static int nvs_flash_init_partition(const char *p){assert(!strcmp(p,"wifi_config"));return 0;}
static int nvs_open_from_partition(const char*p,const char*n,int mode,nvs_handle_t*h){assert(!strcmp(p,"wifi_config"));*h=1;return 0;}
static int nvs_get_blob(nvs_handle_t h,const char*k,void*v,size_t*n){return -1;}
static int nvs_set_blob(nvs_handle_t h,const char*k,const void*v,size_t n){return store_error?-1:0;}
static int nvs_commit(nvs_handle_t h){saves++;return 0;}
static void nvs_close(nvs_handle_t h){}
#define SNTP_OPMODE_POLL 0
static void esp_sntp_setoperatingmode(int mode){}
static void esp_sntp_setservername(unsigned i,const char*s){assert(i<2);}
static void esp_sntp_set_time_sync_notification_cb(void(*cb)(struct timeval*)){}
static void esp_sntp_init(void){}
static bool esp_sntp_restart(void){restarts++;return true;}
typedef struct {int content_len;} httpd_req_t;
typedef void*httpd_handle_t;
typedef struct {int stack_size,max_open_sockets,recv_wait_timeout;bool lru_purge_enable;} httpd_config_t;
#define HTTPD_DEFAULT_CONFIG() ((httpd_config_t){0})
#define HTTPD_403_FORBIDDEN 403
#define HTTPD_400_BAD_REQUEST 400
#define HTTPD_RESP_USE_STRLEN -1
#define HTTP_GET 0
#define HTTP_POST 1
typedef struct {const char*uri;int method;esp_err_t(*handler)(httpd_req_t*);} httpd_uri_t;
static const char *body_input,*origin_input;static unsigned body_offset;static uint32_t local_ip=0xc0a80401;static char response[2000];
static int httpd_req_to_sockfd(httpd_req_t*r){return 7;}
static int test_getsockname(int fd,struct sockaddr*a,socklen_t*n){struct sockaddr_in*v=(void*)a;v->sin_family=AF_INET;v->sin_addr.s_addr=htonl(local_ip);return 0;}
#define getsockname test_getsockname
static int httpd_resp_send_err(httpd_req_t*r,int code,const char*t){return code;}
static int httpd_resp_set_type(httpd_req_t*r,const char*t){return 0;}
static int httpd_resp_set_hdr(httpd_req_t*r,const char*k,const char*v){return 0;}
static int httpd_resp_send(httpd_req_t*r,const char*b,int n){snprintf(response,sizeof(response),"%s",b);return 0;}
#define httpd_resp_sendstr(r,s) httpd_resp_send(r,s,-1)
static size_t httpd_req_get_hdr_value_len(httpd_req_t*r,const char*k){return origin_input?strlen(origin_input):0;}
static int httpd_req_get_hdr_value_str(httpd_req_t*r,const char*k,char*out,size_t n){snprintf(out,n,"%s",origin_input);return 0;}
static int httpd_req_recv(httpd_req_t*r,char*b,size_t n){if(n>3)n=3;memcpy(b,body_input+body_offset,n);body_offset+=n;return n;}
static int httpd_stop(httpd_handle_t h){return 0;}
static int httpd_start(httpd_handle_t*h,httpd_config_t*c){*h=(void*)1;return 0;}
static int httpd_register_uri_handler(httpd_handle_t h,const httpd_uri_t*u){return 0;}
'''
DRIVER=r'''
#include <stdio.h>
#include "wifi_time.c"
bool world_sync_time(int64_t t,uint8_t *g){syncs++;*g=50;return !world_error;}
static int submit(const char*b){body_input=b;body_offset=0;httpd_req_t r={.content_len=strlen(b)};return configure(&r);}
int main(void){
 credentials_t c={.ssid="Test",.password="12345678"};assert(valid_credentials(&c));c.password[2]=0;assert(!valid_credentials(&c));c.password[0]=0;assert(valid_credentials(&c));
 char out[33];assert(field("ssid=%E5%AE%B6%E9%87%8C+WiFi&password=","ssid",out,sizeof(out))&&!strcmp(out,"家里 WiFi"));
 assert(!field("ssid=a&ssid=b","ssid",out,sizeof(out)));assert(!field("ssid=%00","ssid",out,sizeof(out)));assert(!field("ssid=%GG","ssid",out,sizeof(out)));assert(!field("ssid=%0A","ssid",out,sizeof(out)));
 wifi_time_start();assert(view.state==WIFI_TIME_UNCONFIGURED&&!configured);
 wifi_time_setup_request(true);wifi_time_poll();assert(view.setup&&!wifi_time_scan_allowed());
 char form[180];snprintf(form,sizeof(form),"ssid=Home&password=12345678&token=%s",view.password);
 origin_input="https://untrusted.test";assert(submit(form)==403);origin_input=NULL;
 local_ip=0xc0a80102;assert(submit(form)==403);local_ip=0xc0a80401;
 assert(submit("ssid=x&password=12345678&token=wrong")==400);
 assert(submit(form)==0);wifi_time_poll();assert(connects==1&&save_credentials&&!saves&&!strcmp((char*)station.sta.ssid,"Home"));
 network_event(NULL,IP_EVENT,IP_EVENT_STA_GOT_IP,NULL);wifi_time_poll();assert(saves==1&&view.state==WIFI_TIME_WAITING&&sntp_started);
 struct timeval tv={.tv_sec=1800000000};synchronized(&tv);wifi_time_poll();assert(syncs==1&&view.state==WIFI_TIME_READY&&view.recovered==50);
 // New configuration while already connected must reconnect BEFORE saving.
 wifi_time_setup_request(true);wifi_time_poll();snprintf(form,sizeof(form),"ssid=New&password=abcdefgh&token=%s",view.password);
 assert(submit(form)==0);wifi_time_poll();assert(connects==2&&saves==1&&save_credentials&&!atomic_load(&connected));
 network_event(NULL,IP_EVENT,IP_EVENT_STA_GOT_IP,NULL);store_error=1;wifi_time_poll();assert(view.state==WIFI_TIME_ERROR&&saves==1);
 store_error=0;wifi_time_poll();assert(saves==1);now+=30000000;wifi_time_poll();assert(saves==2&&restarts==1&&view.state==WIFI_TIME_WAITING);
 world_error=1;synchronized(&tv);wifi_time_poll();assert(syncs==2&&view.state==WIFI_TIME_ERROR);wifi_time_poll();assert(syncs==2);
 world_error=0;now+=30000000;wifi_time_poll();assert(syncs==3&&view.state==WIFI_TIME_READY);
 network_event(NULL,WIFI_EVENT,WIFI_EVENT_STA_DISCONNECTED,NULL);wifi_time_poll();assert(connects==3&&!was_connected);
 network_event(NULL,IP_EVENT,IP_EVENT_STA_GOT_IP,NULL);wifi_time_poll();assert(restarts==2&&view.state==WIFI_TIME_WAITING);
 wifi_time_setup_request(true);wifi_time_poll();assert(view.setup);now+=301000000;wifi_time_poll();assert(!view.setup&&!view.password[0]&&wifi_time_scan_allowed());
 puts("{\"network_boundary\":\"simulated\",\"credential_validation\":true,\"ap_only_http\":true,\"credential_replace_after_ip\":true,\"save_retry_backoff\":true,\"reconnect_sntp\":true,\"setup_timeout\":true}");
}
'''
def run():
 with tempfile.TemporaryDirectory(prefix='wifi-time-') as tmp:
  p=Path(tmp);(p/'stubs.h').write_text(STUB)
  for name in ('esp_wifi.h','esp_netif.h','esp_event.h','esp_http_server.h','esp_sntp.h','esp_random.h','esp_timer.h','nvs_flash.h','nvs.h','freertos/FreeRTOS.h'):
   q=p/name;q.parent.mkdir(parents=True,exist_ok=True);q.write_text('#include "stubs.h"\n')
  (p/'driver.c').write_text(DRIVER)
  subprocess.run(['cc','-std=gnu11','-O1','-g','-fsanitize=address,undefined','-Wall','-Wextra','-Werror','-Wno-unused-function','-Wno-unused-parameter','-Wno-unused-variable','-I',str(p),'-I',str(ROOT/'firmware/main'),str(p/'driver.c'),'-o',str(p/'probe')],check=True,capture_output=True,text=True)
  r=subprocess.run([str(p/'probe')],capture_output=True,text=True);assert r.returncode==0,r.stdout+r.stderr
  return json.loads(r.stdout)
if __name__=='__main__':
 try:print(json.dumps(run(),indent=2))
 except subprocess.CalledProcessError as e: print(e.stderr);raise
