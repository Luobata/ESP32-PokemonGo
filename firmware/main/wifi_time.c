#include "wifi_time.h"
#include "world.h"
#include "rest_clock.h"
#include "language.h"
#include "esp_wifi.h"
#include "esp_netif.h"
#include "esp_event.h"
#include "esp_http_server.h"
#include "esp_sntp.h"
#include "esp_random.h"
#include "esp_timer.h"
#include "esp_log.h"
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
static uint16_t setup_client_aids[WIFI_SETUP_CLIENT_LIMIT];
// ESP HTTP handlers execute serially on the existing HTTP task.
static char html[1700];
static int64_t retry_at,connecting_until,setup_until,close_at,save_retry_at,sync_retry_at;

static void state(wifi_time_state_t value){portENTER_CRITICAL(&lock);view.state=value;portEXIT_CRITICAL(&lock);}
void wifi_time_view(wifi_time_view_t *out){if(out){portENTER_CRITICAL(&lock);*out=view;portEXIT_CRITICAL(&lock);}}
void wifi_time_setup_request(bool start){atomic_store(&setup_request,start?1:-1);}
void wifi_time_retry(void){atomic_store(&retry_request,1);}
bool wifi_time_scan_allowed(void){wifi_time_view_t v;wifi_time_view(&v);return !v.setup&&esp_timer_get_time()>=connecting_until;}
static void network_event(void *arg,esp_event_base_t base,int32_t id,void *data){
 (void)arg;
 if(base==IP_EVENT&&id==IP_EVENT_STA_GOT_IP){
  atomic_store(&connected,true);portENTER_CRITICAL(&lock);view.failure=WIFI_FAILURE_NONE;portEXIT_CRITICAL(&lock);
 }else if(base==WIFI_EVENT&&id==WIFI_EVENT_STA_DISCONNECTED){
  atomic_store(&connected,false);
  if(data){
   unsigned reason=((wifi_event_sta_disconnected_t*)data)->reason;
   // Explicit disconnection while changing modes is not a router rejection.
   if(reason!=WIFI_REASON_ASSOC_LEAVE){
    uint8_t failure=reason==WIFI_REASON_NO_AP_FOUND?WIFI_FAILURE_NOT_FOUND:
     (reason==WIFI_REASON_AUTH_FAIL||reason==WIFI_REASON_HANDSHAKE_TIMEOUT||reason==WIFI_REASON_4WAY_HANDSHAKE_TIMEOUT)?WIFI_FAILURE_AUTH:WIFI_FAILURE_CONNECTION;
    portENTER_CRITICAL(&lock);if(!view.setup)view.failure=failure;portEXIT_CRITICAL(&lock);
    ESP_LOGW("wifi_time","station disconnected reason=%u",reason);
   }
  }
 }else if(base==WIFI_EVENT&&data&&(id==WIFI_EVENT_AP_STACONNECTED||id==WIFI_EVENT_AP_STADISCONNECTED)){
  unsigned aid=id==WIFI_EVENT_AP_STACONNECTED?((wifi_event_ap_staconnected_t*)data)->aid:((wifi_event_ap_stadisconnected_t*)data)->aid;
  if(aid){
   portENTER_CRITICAL(&lock);
   // AID identifies a connection; it need not equal its slot or be <= the
   // configured client limit. Ignore duplicate events without double-counting.
   unsigned found=WIFI_SETUP_CLIENT_LIMIT,empty=WIFI_SETUP_CLIENT_LIMIT;
   for(unsigned i=0;i<WIFI_SETUP_CLIENT_LIMIT;i++){
    if(setup_client_aids[i]==aid)found=i;
    if(!setup_client_aids[i])empty=i;
   }
   if(id==WIFI_EVENT_AP_STACONNECTED&&found==WIFI_SETUP_CLIENT_LIMIT&&empty<WIFI_SETUP_CLIENT_LIMIT)setup_client_aids[empty]=aid;
   if(id==WIFI_EVENT_AP_STADISCONNECTED&&found<WIFI_SETUP_CLIENT_LIMIT)setup_client_aids[found]=0;
   view.setup_clients=0;for(unsigned i=0;i<WIFI_SETUP_CLIENT_LIMIT;i++)view.setup_clients+=setup_client_aids[i]!=0;
   portEXIT_CRITICAL(&lock);
  }
 }
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
 // ESP-IDF uses a dual-stack HTTP socket when IPv6 is enabled. An IPv4
 // connection to the AP then reports ::ffff:192.168.4.1 as its local address.
 struct sockaddr_storage local={0};socklen_t len=sizeof(local);
 if(getsockname(httpd_req_to_sockfd(req),(struct sockaddr*)&local,&len)!=0)return false;
 if(local.ss_family==AF_INET&&len>=sizeof(struct sockaddr_in))
  return ntohl(((struct sockaddr_in*)&local)->sin_addr.s_addr)==0xc0a80401u;
#if CONFIG_LWIP_IPV6
 if(local.ss_family==AF_INET6&&len>=sizeof(struct sockaddr_in6)){
  static const unsigned char ap_mapped[16]={0,0,0,0,0,0,0,0,0,0,0xff,0xff,192,168,4,1};
  return !memcmp(&((struct sockaddr_in6*)&local)->sin6_addr,ap_mapped,sizeof(ap_mapped));
 }
#endif
 return false;
}
static esp_err_t web_error(httpd_req_t *req,int code,const char *message){
 language_snprintf(html,sizeof(html),"%s",message);language_convert_in_place(html);
 httpd_resp_set_type(req,"text/html; charset=utf-8");
 return httpd_resp_send_err(req,code,html);
}
static esp_err_t page(httpd_req_t *req){
 if(!ap_request(req))return web_error(req,HTTPD_403_FORBIDDEN,"配网未开启，请在设备开启配网，连接 PW- 热点后重试。");
 wifi_time_view_t v;wifi_time_view(&v);
 language_snprintf(html,sizeof(html),"<!doctype html><meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'><title>PokeWalk Wi-Fi</title><style>body{max-width:420px;margin:40px auto;padding:20px;background:#f2efe5;color:#29302b;font:16px sans-serif}input,button{display:block;width:100%%;box-sizing:border-box;padding:12px;margin:10px 0 24px}button{background:#355c3d;color:white;border:0}</style><h1>PokeWalk Wi-Fi 校时</h1><p>连接 2.4GHz 家庭 Wi-Fi 或手机热点。配置成功后，设备开机自动联网，补回关机期间的体能。</p><form method=post action=/configure><input type=hidden name=token value='%s'><label>Wi-Fi 名称<input name=ssid maxlength=32 required autocomplete=off></label><label>Wi-Fi 密码<input name=password type=password maxlength=64 autocomplete=new-password></label><button>连接并保存</button></form><p>密码仅保存在这台设备，不进入游戏存档备份。首次校时建立基准，之前的关机时间无法补算。</p>",v.password);
 language_convert_in_place(html);
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
 if(!ap_request(req))return web_error(req,HTTPD_403_FORBIDDEN,"配网未开启，请在设备开启配网，连接 PW- 热点后重试。");
 if(req->content_len<=0||req->content_len>512)return web_error(req,HTTPD_400_BAD_REQUEST,"表单无效，请重新打开配网页。");
 char body[513],token[9],origin[64];credentials_t next={0};int have=0;
 size_t origin_len=httpd_req_get_hdr_value_len(req,"Origin");
 if(origin_len&&(origin_len>=sizeof(origin)||httpd_req_get_hdr_value_str(req,"Origin",origin,sizeof(origin))!=ESP_OK||strcmp(origin,"http://192.168.4.1")))return web_error(req,HTTPD_403_FORBIDDEN,"请连接设备热点，并从 http://192.168.4.1 打开配网页。");
 while(have<req->content_len){int n=httpd_req_recv(req,body+have,req->content_len-have);if(n<=0)return ESP_FAIL;have+=n;}body[have]=0;
 wifi_time_view_t v;wifi_time_view(&v);
 bool valid=field(body,"ssid",next.ssid,sizeof(next.ssid))&&field(body,"password",next.password,sizeof(next.password))&&field(body,"token",token,sizeof(token))&&!strcmp(token,v.password)&&valid_credentials(&next);
 memset(body,0,sizeof(body));
 if(!valid)return web_error(req,HTTPD_400_BAD_REQUEST,"请重新打开配网页，检查网络名称与密码。密码至少8位，开放网络可留空。");
 httpd_resp_set_type(req,"text/html; charset=utf-8");httpd_resp_set_hdr(req,"Cache-Control","no-store");
 language_snprintf(html,sizeof(html),"%s","<!doctype html><meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'><h2>已收到配置</h2><p>临时热点即将关闭，设备开始连接所填网络。请返回设备查看连接与校时结果。连接成功后保存网络，下次开机自动连接。</p>");
 language_convert_in_place(html);esp_err_t result=httpd_resp_sendstr(req,html);
 // Do not let the world task change the radio channel before the HTTP reply.
 if(result==ESP_OK){portENTER_CRITICAL(&lock);pending=next;incoming=true;portEXIT_CRITICAL(&lock);}
 memset(&next,0,sizeof(next));return result;
}
static void stop_setup(void){
 if(server){httpd_stop(server);server=NULL;}
 (void)esp_wifi_set_mode(WIFI_MODE_STA);
 portENTER_CRITICAL(&lock);view.setup=false;memset(view.password,0,sizeof(view.password));
 incoming=false;memset(setup_client_aids,0,sizeof(setup_client_aids));view.setup_clients=0;memset(&pending,0,sizeof(pending));portEXIT_CRITICAL(&lock);close_at=0;
}
static void setup_failed(const char *stage,esp_err_t err){
 stop_setup();
 portENTER_CRITICAL(&lock);view.setup_failed=true;view.state=WIFI_TIME_ERROR;portEXIT_CRITICAL(&lock);
 ESP_LOGE("wifi_time","setup failed: %s (%s)",stage,esp_err_to_name(err));
}
static void start_setup(int64_t now){
 portENTER_CRITICAL(&lock);view.setup_failed=false;view.failure=WIFI_FAILURE_NONE;memset(setup_client_aids,0,sizeof(setup_client_aids));view.setup_clients=0;portEXIT_CRITICAL(&lock);
 if(!storage_ok){setup_failed("storage",ESP_FAIL);return;}
 if(server)stop_setup();
 if(!ap_created){if(!esp_netif_create_default_wifi_ap()){setup_failed("ap interface",ESP_ERR_NO_MEM);return;}ap_created=true;}
 wifi_config_t cfg={0};char ssid[16]={0},password[9]={0};
 snprintf(ssid,sizeof(ssid),"PW-%06lX",(unsigned long)(esp_random()&0xffffff));snprintf(password,sizeof(password),"%08lu",(unsigned long)(10000000u+esp_random()%90000000u));
 memcpy(cfg.ap.ssid,ssid,strlen(ssid));cfg.ap.ssid_len=strlen(ssid);memcpy(cfg.ap.password,password,8);cfg.ap.authmode=WIFI_AUTH_WPA2_PSK;cfg.ap.max_connection=WIFI_SETUP_CLIENT_LIMIT;cfg.ap.channel=1;
 // Provisioning owns the radio until the form is received or setup closes.
 // APSTA reconnect scans/channel changes can interrupt a phone loading /.
 (void)esp_wifi_disconnect();atomic_store(&connected,false);was_connected=false;connecting_until=0;retry_at=0;
 esp_err_t err=esp_wifi_set_mode(WIFI_MODE_AP);
 if(err==ESP_OK)err=esp_wifi_set_config(WIFI_IF_AP,&cfg);
 if(err!=ESP_OK){setup_failed("ap start",err);return;}
 httpd_config_t config=HTTPD_DEFAULT_CONFIG();config.stack_size=6144;config.max_open_sockets=2;config.lru_purge_enable=true;config.recv_wait_timeout=5;
 err=httpd_start(&server,&config);
 if(err!=ESP_OK){setup_failed("http start",err);return;}
 httpd_uri_t get={.uri="/",.method=HTTP_GET,.handler=page},post={.uri="/configure",.method=HTTP_POST,.handler=configure};
 err=httpd_register_uri_handler(server,&get);
 if(err==ESP_OK)err=httpd_register_uri_handler(server,&post);
 if(err!=ESP_OK){setup_failed("http routes",err);return;}
 portENTER_CRITICAL(&lock);view.setup=true;view.state=configured?WIFI_TIME_OFFLINE:WIFI_TIME_UNCONFIGURED;
 memcpy(view.ssid,ssid,sizeof(ssid));memcpy(view.password,password,sizeof(password));portEXIT_CRITICAL(&lock);
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
    esp_event_handler_register(WIFI_EVENT,WIFI_EVENT_STA_DISCONNECTED,network_event,NULL)!=ESP_OK ||
    esp_event_handler_register(WIFI_EVENT,WIFI_EVENT_AP_STACONNECTED,network_event,NULL)!=ESP_OK ||
    esp_event_handler_register(WIFI_EVENT,WIFI_EVENT_AP_STADISCONNECTED,network_event,NULL)!=ESP_OK){storage_ok=false;state(WIFI_TIME_ERROR);return;}
 state(configured?WIFI_TIME_CONNECTING:WIFI_TIME_UNCONFIGURED);
}
void wifi_time_poll(void){
 int64_t now=esp_timer_get_time();int request=atomic_exchange(&setup_request,0);
 if(request>0)start_setup(now);else if(request<0)stop_setup();
 bool received=false;
 portENTER_CRITICAL(&lock);if(incoming){credentials=pending;memset(&pending,0,sizeof(pending));incoming=false;received=true;}portEXIT_CRITICAL(&lock);
 if(received){configured=true;save_credentials=true;save_retry_at=0;was_connected=false;close_at=now+4000000;retry_at=0;state(WIFI_TIME_CONNECTING);}
 wifi_time_view_t v;wifi_time_view(&v);
 if(v.setup){
  // Keep the response available for four seconds, then close AP before STA
  // scans/connects. No old-network retries or background scans during setup.
  if((close_at&&now>=close_at)||(!close_at&&now>=setup_until))stop_setup();
  else return;
 }
 if(atomic_exchange(&retry_request,0)){
  portENTER_CRITICAL(&lock);view.setup_failed=false;portEXIT_CRITICAL(&lock);
  retry_at=0;sync_retry_at=0;save_retry_at=0;if(sntp_started)(void)esp_sntp_restart();
 }
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
