#include "wifi_time.h"
#include "world.h"
#include "rest_clock.h"
#include "esp_wifi.h"
#include "esp_netif.h"
#include "esp_event.h"
#include "esp_http_server.h"
#include "esp_sntp.h"
#include "esp_random.h"
#include "esp_timer.h"
#include "nvs_flash.h"
#include "nvs.h"
#include "freertos/FreeRTOS.h"
#include <stdatomic.h>
#include <stdio.h>
#include <string.h>
#include <sys/time.h>
#include <sys/socket.h>
#include <arpa/inet.h>

#define CONFIG_PARTITION "wifi_config"
#define SETUP_SECONDS 300
// A separate NVS partition prevents home-network credentials from appearing in
// USB game backups or being replaced by a game-save import.
typedef struct { char ssid[33],password[65]; } credentials_t;
static credentials_t credentials,pending;
static portMUX_TYPE lock=portMUX_INITIALIZER_UNLOCKED;
static wifi_time_view_t view;
static atomic_bool connected,needs_sync;
static atomic_int setup_request,retry_request;
static bool incoming,configured,save_credentials,storage_ok,sntp_started;
static bool ap_created,was_connected;
static httpd_handle_t server;
static int64_t retry_at,connecting_until,setup_until,close_at,save_retry_at,sync_retry_at;

static void state(wifi_time_state_t value){portENTER_CRITICAL(&lock);view.state=value;portEXIT_CRITICAL(&lock);}
void wifi_time_view(wifi_time_view_t *out){if(out){portENTER_CRITICAL(&lock);*out=view;portEXIT_CRITICAL(&lock);}}
void wifi_time_setup_request(bool start){atomic_store(&setup_request,start?1:-1);}
void wifi_time_retry(void){atomic_store(&retry_request,1);}
bool wifi_time_scan_allowed(void){wifi_time_view_t v;wifi_time_view(&v);return !v.setup&&esp_timer_get_time()>=connecting_until;}
static void network_event(void *arg,esp_event_base_t base,int32_t id,void *data){
 (void)arg;(void)data;
 if(base==IP_EVENT&&id==IP_EVENT_STA_GOT_IP)atomic_store(&connected,true);
 else if(base==WIFI_EVENT&&id==WIFI_EVENT_STA_DISCONNECTED)atomic_store(&connected,false);
}
static void synchronized(struct timeval *tv){
 if((int64_t)tv->tv_sec*1000000>=REST_CLOCK_MIN_US)atomic_store(&needs_sync,true);
}
static bool valid_credentials(const credentials_t *c){
 size_t n=strnlen(c->ssid,sizeof(c->ssid)),p=strnlen(c->password,sizeof(c->password));
 if(!n||n>32||p>64)return false;
 if(p&&p<8)return false;
 if(p==64)for(unsigned i=0;i<64;i++)if(!((c->password[i]>='0'&&c->password[i]<='9')||(c->password[i]>='a'&&c->password[i]<='f')||(c->password[i]>='A'&&c->password[i]<='F')))return false;
 return true;
}
static bool store_credentials(void){
 nvs_handle_t h;if(nvs_open_from_partition(CONFIG_PARTITION,"network",NVS_READWRITE,&h)!=ESP_OK)return false;
 esp_err_t err=nvs_set_blob(h,"credentials",&credentials,sizeof(credentials));if(err==ESP_OK)err=nvs_commit(h);nvs_close(h);return err==ESP_OK;
}
static bool ap_request(httpd_req_t *req){
 wifi_time_view_t v;wifi_time_view(&v);if(!v.setup)return false;
 struct sockaddr_in local;socklen_t len=sizeof(local);
 return getsockname(httpd_req_to_sockfd(req),(struct sockaddr*)&local,&len)==0&&local.sin_family==AF_INET&&ntohl(local.sin_addr.s_addr)==0xc0a80401u;
}
static esp_err_t page(httpd_req_t *req){
 if(!ap_request(req))return httpd_resp_send_err(req,HTTPD_403_FORBIDDEN,"Setup is not active");
 wifi_time_view_t v;wifi_time_view(&v);static char html[1700];
 snprintf(html,sizeof(html),"<!doctype html><meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'><title>PokeWalk Wi-Fi</title><style>body{max-width:420px;margin:40px auto;padding:20px;background:#f2efe5;color:#29302b;font:16px sans-serif}input,button{display:block;width:100%%;box-sizing:border-box;padding:12px;margin:10px 0 24px}button{background:#355c3d;color:white;border:0}</style><h1>PokeWalk Wi-Fi 校时</h1><p>连接 2.4GHz 家庭 Wi-Fi 或手机热点。配置成功后，设备开机自动联网，补回关机期间的体能。</p><form method=post action=/configure><input type=hidden name=token value='%s'><label>Wi-Fi 名称<input name=ssid maxlength=32 required autocomplete=off></label><label>Wi-Fi 密码<input name=password type=password maxlength=64 autocomplete=new-password></label><button>连接并保存</button></form><p>密码仅保存在这台设备，不进入游戏存档备份。首次校时建立基准，之前的关机时间无法补算。</p>",v.password);
 httpd_resp_set_type(req,"text/html; charset=utf-8");httpd_resp_set_hdr(req,"Cache-Control","no-store");return httpd_resp_send(req,html,HTTPD_RESP_USE_STRLEN);
}
static int hex(char c){return c>='0'&&c<='9'?c-'0':c>='a'&&c<='f'?c-'a'+10:c>='A'&&c<='F'?c-'A'+10:-1;}
static bool decode(const char *src,size_t n,char *out,size_t cap){
 size_t j=0;
 for(size_t i=0;i<n;i++){
  unsigned char c=src[i];if(c=='+')c=' ';else if(c=='%'){if(i+2>=n||hex(src[i+1])<0||hex(src[i+2])<0)return false;c=hex(src[i+1])*16+hex(src[i+2]);i+=2;}
  if(!c||c<32||c==127||j+1>=cap)return false;
  out[j++]=c;
 }
 out[j]=0;return true;
}
static bool field(const char *body,const char *name,char *out,size_t cap){
 size_t n=strlen(name);bool found=false;
 for(const char *p=body;*p;){
  const char *end=strchr(p,'&');if(!end)end=p+strlen(p);
  if((size_t)(end-p)>n&&p[n]=='='&&!memcmp(p,name,n)){
   if(found||!decode(p+n+1,end-p-n-1,out,cap))return false;
   found=true;
  }
  p=*end?end+1:end;
 }
 return found;
}
static esp_err_t configure(httpd_req_t *req){
 if(!ap_request(req))return httpd_resp_send_err(req,HTTPD_403_FORBIDDEN,"Setup is not active");
 if(req->content_len<=0||req->content_len>512)return httpd_resp_send_err(req,HTTPD_400_BAD_REQUEST,"Invalid form");
 char body[513],token[9],origin[64];credentials_t next={0};int have=0;
 size_t origin_len=httpd_req_get_hdr_value_len(req,"Origin");
 if(origin_len&&(origin_len>=sizeof(origin)||httpd_req_get_hdr_value_str(req,"Origin",origin,sizeof(origin))!=ESP_OK||strcmp(origin,"http://192.168.4.1")))return httpd_resp_send_err(req,HTTPD_403_FORBIDDEN,"Invalid origin");
 while(have<req->content_len){int n=httpd_req_recv(req,body+have,req->content_len-have);if(n<=0)return ESP_FAIL;have+=n;}body[have]=0;
 wifi_time_view_t v;wifi_time_view(&v);
 bool valid=field(body,"ssid",next.ssid,sizeof(next.ssid))&&field(body,"password",next.password,sizeof(next.password))&&field(body,"token",token,sizeof(token))&&!strcmp(token,v.password)&&valid_credentials(&next);
 memset(body,0,sizeof(body));
 if(!valid)return httpd_resp_send_err(req,HTTPD_400_BAD_REQUEST,"Check SSID (1-32 bytes) and password (8-63 bytes, or empty for open Wi-Fi)");
 portENTER_CRITICAL(&lock);pending=next;incoming=true;portEXIT_CRITICAL(&lock);memset(&next,0,sizeof(next));
 httpd_resp_set_type(req,"text/html; charset=utf-8");httpd_resp_set_hdr(req,"Cache-Control","no-store");
 return httpd_resp_sendstr(req,"<!doctype html><meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'><h2>已收到配置</h2><p>请返回设备查看连接与校时结果。连接成功后保存网络，下次开机自动连接。</p>");
}
static void stop_setup(void){
 if(server){httpd_stop(server);server=NULL;}
 (void)esp_wifi_set_mode(WIFI_MODE_STA);
 portENTER_CRITICAL(&lock);view.setup=false;memset(view.password,0,sizeof(view.password));portEXIT_CRITICAL(&lock);close_at=0;
}
static void start_setup(int64_t now){
 if(!storage_ok){state(WIFI_TIME_ERROR);return;}
 if(server)stop_setup();
 if(!ap_created){if(!esp_netif_create_default_wifi_ap()){state(WIFI_TIME_ERROR);return;}ap_created=true;}
 wifi_config_t cfg={0};char ssid[16]={0},password[9]={0};
 snprintf(ssid,sizeof(ssid),"PW-%06lX",(unsigned long)(esp_random()&0xffffff));snprintf(password,sizeof(password),"%08lu",(unsigned long)(10000000u+esp_random()%90000000u));
 memcpy(cfg.ap.ssid,ssid,strlen(ssid));cfg.ap.ssid_len=strlen(ssid);memcpy(cfg.ap.password,password,8);cfg.ap.authmode=WIFI_AUTH_WPA2_PSK;cfg.ap.max_connection=1;cfg.ap.channel=1;
 if(esp_wifi_set_mode(WIFI_MODE_APSTA)!=ESP_OK||esp_wifi_set_config(WIFI_IF_AP,&cfg)!=ESP_OK){stop_setup();state(WIFI_TIME_ERROR);return;}
 httpd_config_t config=HTTPD_DEFAULT_CONFIG();config.stack_size=6144;config.max_open_sockets=2;config.lru_purge_enable=true;config.recv_wait_timeout=5;
 if(httpd_start(&server,&config)!=ESP_OK){stop_setup();state(WIFI_TIME_ERROR);return;}
 httpd_uri_t get={.uri="/",.method=HTTP_GET,.handler=page},post={.uri="/configure",.method=HTTP_POST,.handler=configure};
 if(httpd_register_uri_handler(server,&get)!=ESP_OK||httpd_register_uri_handler(server,&post)!=ESP_OK){stop_setup();state(WIFI_TIME_ERROR);return;}
 portENTER_CRITICAL(&lock);view.setup=true;memcpy(view.ssid,ssid,sizeof(ssid));memcpy(view.password,password,sizeof(password));portEXIT_CRITICAL(&lock);
 setup_until=now+SETUP_SECONDS*1000000LL;
}
static void connect_network(int64_t now){
 wifi_config_t cfg={0};memcpy(cfg.sta.ssid,credentials.ssid,strlen(credentials.ssid));memcpy(cfg.sta.password,credentials.password,strlen(credentials.password));
 cfg.sta.threshold.authmode=credentials.password[0]?WIFI_AUTH_WPA2_PSK:WIFI_AUTH_OPEN;
 (void)esp_wifi_disconnect();atomic_store(&connected,false);
 if(esp_wifi_set_config(WIFI_IF_STA,&cfg)!=ESP_OK||esp_wifi_connect()!=ESP_OK){state(WIFI_TIME_OFFLINE);connecting_until=0;}
 else {state(WIFI_TIME_CONNECTING);connecting_until=now+15000000;}
 retry_at=now+30000000;
}
void wifi_time_start(void){
 storage_ok=nvs_flash_init_partition(CONFIG_PARTITION)==ESP_OK;
 if(!storage_ok){state(WIFI_TIME_ERROR);return;}
 nvs_handle_t h;size_t len=sizeof(credentials);
 if(nvs_open_from_partition(CONFIG_PARTITION,"network",NVS_READONLY,&h)==ESP_OK){
  configured=nvs_get_blob(h,"credentials",&credentials,&len)==ESP_OK&&len==sizeof(credentials)&&valid_credentials(&credentials);nvs_close(h);
 }
 if(esp_event_handler_register(IP_EVENT,IP_EVENT_STA_GOT_IP,network_event,NULL)!=ESP_OK ||
    esp_event_handler_register(WIFI_EVENT,WIFI_EVENT_STA_DISCONNECTED,network_event,NULL)!=ESP_OK){storage_ok=false;state(WIFI_TIME_ERROR);return;}
 state(configured?WIFI_TIME_CONNECTING:WIFI_TIME_UNCONFIGURED);
}
void wifi_time_poll(void){
 int64_t now=esp_timer_get_time();int request=atomic_exchange(&setup_request,0);
 if(request>0)start_setup(now);else if(request<0)stop_setup();
 wifi_time_view_t v;wifi_time_view(&v);if(v.setup&&(now>=setup_until||(close_at&&now>=close_at)))stop_setup();
 bool received=false;
 portENTER_CRITICAL(&lock);if(incoming){credentials=pending;memset(&pending,0,sizeof(pending));incoming=false;received=true;}portEXIT_CRITICAL(&lock);
 if(received){configured=true;save_credentials=true;save_retry_at=0;was_connected=false;close_at=now+4000000;connect_network(now);}
 if(atomic_exchange(&retry_request,0)){retry_at=0;sync_retry_at=0;save_retry_at=0;if(sntp_started)(void)esp_sntp_restart();}
 if(configured&&!atomic_load(&connected)&&now>=retry_at)connect_network(now);
 if(atomic_load(&connected)){
  connecting_until=0;
  if(save_credentials){
   if(now<save_retry_at)return;
   if(store_credentials())save_credentials=false;else {save_retry_at=now+30000000;state(WIFI_TIME_ERROR);return;}
  }
  if(!was_connected&&sntp_started){state(WIFI_TIME_WAITING);(void)esp_sntp_restart();}
  was_connected=true;
  if(!sntp_started){
   esp_sntp_setoperatingmode(SNTP_OPMODE_POLL);esp_sntp_setservername(0,"ntp.aliyun.com");esp_sntp_setservername(1,"pool.ntp.org");
   esp_sntp_set_time_sync_notification_cb(synchronized);esp_sntp_init();sntp_started=true;state(WIFI_TIME_WAITING);
  }
  if(now>=sync_retry_at&&atomic_exchange(&needs_sync,false)){
   struct timeval tv;gettimeofday(&tv,NULL);uint8_t gained=0;
   if(world_sync_time((int64_t)tv.tv_sec*1000000+tv.tv_usec,&gained)){
    portENTER_CRITICAL(&lock);view.state=WIFI_TIME_READY;view.recovered=gained;portEXIT_CRITICAL(&lock);
   }else {sync_retry_at=now+30000000;atomic_store(&needs_sync,true);state(WIFI_TIME_ERROR);}
  }
 }else {was_connected=false;if(configured&&now>=connecting_until)state(WIFI_TIME_OFFLINE);}
}
