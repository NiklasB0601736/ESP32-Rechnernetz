#include <stdio.h>
#include <string.h>
#include "sdkconfig.h"
#include "esp_idf_version.h"
#include "esp_event.h"
#include "esp_netif.h"
#include "esp_now.h"
#include "esp_timer.h"
#include "esp_wifi.h"
#include "freertos/semphr.h"
#include "radio.h"

#if !CONFIG_IDF_TARGET_ESP32
#error "This capability table is validated for ESP32-WROOM-32 only"
#endif
#if ESP_IDF_VERSION != ESP_IDF_VERSION_VAL(6,0,1)
#error "Use ESP-IDF v6.0.1 or explicitly review the API and capability table before porting"
#endif

const int8_t lab_powers[11]={8,20,28,34,44,52,56,60,66,72,80};
const char *const lab_profiles[6]={"ofdm6","ofdm12","ofdm24","ofdm54","ht_mcs0","ht_mcs7"};
const char *const lab_operations[7]={"invalid","configure","commit","rollback","arm","run","stop"};
static const wifi_phy_rate_t rates[6]={WIFI_PHY_RATE_6M,WIFI_PHY_RATE_12M,WIFI_PHY_RATE_24M,
                                     WIFI_PHY_RATE_54M,WIFI_PHY_RATE_MCS0_LGI,WIFI_PHY_RATE_MCS7_LGI};
static QueueHandle_t rx_queue;
static SemaphoreHandle_t sent;
static uint8_t peer_mac[6];
static bool peer_valid, outstanding;
static volatile int last_status;
static uint32_t queue_drops;
static uint16_t power_mask;
static uint8_t profile_mask;

static void receive_callback(const esp_now_recv_info_t *info,const uint8_t *data,int len){
    if(!info || !peer_valid || memcmp(info->src_addr,peer_mac,6) || len<(int)sizeof(wire_header_t) || len>250)return;
    wire_header_t h;
    memcpy(&h,data,sizeof(h));
    if(h.magic!=LAB_MAGIC || h.version!=LAB_VERSION || h.source!=CONFIG_LAB_PEER_ID ||
       h.destination!=CONFIG_LAB_NODE_ID || h.payload_len>LAB_MAX_PAYLOAD ||
       len!=(int)(sizeof(h)+h.payload_len))return;
    rx_event_t event={0};
    memcpy(&event.packet,data,(size_t)len);
    event.rssi=info->rx_ctrl?info->rx_ctrl->rssi:-127;
    event.received_us=esp_timer_get_time();
    if(xQueueSend(rx_queue,&event,0)!=pdTRUE)__atomic_fetch_add(&queue_drops,1,__ATOMIC_RELAXED);
}

static void send_callback(const esp_now_send_info_t *info,esp_now_send_status_t status){
    (void)info;
    last_status=(status==ESP_NOW_SEND_SUCCESS)?1:0;
    xSemaphoreGive(sent);
}

static esp_err_t set_profile(uint8_t index){
    if(index>=6 || !peer_valid)return ESP_ERR_INVALID_ARG;
    esp_now_rate_config_t cfg={.phymode=index<4?WIFI_PHY_MODE_11G:WIFI_PHY_MODE_HT20,
                               .rate=rates[index],.ersu=false,.dcm=false};
    return esp_now_set_peer_rate_config(peer_mac,&cfg);
}

esp_err_t radio_init(QueueHandle_t receive_queue){
    rx_queue=receive_queue;
    sent=xSemaphoreCreateBinary();
    if(!sent)return ESP_ERR_NO_MEM;
    ESP_ERROR_CHECK(esp_netif_init());
    ESP_ERROR_CHECK(esp_event_loop_create_default());
    wifi_init_config_t init=WIFI_INIT_CONFIG_DEFAULT();
    ESP_ERROR_CHECK(esp_wifi_init(&init));
    ESP_ERROR_CHECK(esp_wifi_set_storage(WIFI_STORAGE_RAM));
    ESP_ERROR_CHECK(esp_wifi_set_mode(WIFI_MODE_STA));
    ESP_ERROR_CHECK(esp_wifi_start());
    ESP_ERROR_CHECK(esp_wifi_set_ps(WIFI_PS_NONE));
    ESP_ERROR_CHECK(esp_wifi_set_protocol(WIFI_IF_STA,WIFI_PROTOCOL_11B|WIFI_PROTOCOL_11G|WIFI_PROTOCOL_11N));
    ESP_ERROR_CHECK(esp_wifi_set_bandwidth(WIFI_IF_STA,WIFI_BW20));
    ESP_ERROR_CHECK(esp_wifi_set_channel(CONFIG_LAB_CHANNEL,WIFI_SECOND_CHAN_NONE));
    ESP_ERROR_CHECK(esp_now_init());
    ESP_ERROR_CHECK(esp_now_register_recv_cb(receive_callback));
    ESP_ERROR_CHECK(esp_now_register_send_cb(send_callback));
    unsigned values[6];
    if(sscanf(CONFIG_LAB_PEER_MAC,"%2x:%2x:%2x:%2x:%2x:%2x",&values[0],&values[1],&values[2],&values[3],&values[4],&values[5])!=6)
        return ESP_ERR_INVALID_ARG;
    uint8_t any=0;
    for(int i=0;i<6;i++){peer_mac[i]=(uint8_t)values[i];any|=peer_mac[i];}
    peer_valid=any && !(peer_mac[0]&1) && CONFIG_LAB_NODE_ID!=CONFIG_LAB_PEER_ID;
    if(peer_valid){
        esp_now_peer_info_t peer={.channel=CONFIG_LAB_CHANNEL,.ifidx=WIFI_IF_STA,.encrypt=false};
        memcpy(peer.peer_addr,peer_mac,6);
        ESP_ERROR_CHECK(esp_now_add_peer(&peer));
        for(int i=0;i<6;i++)if(set_profile(i)==ESP_OK)profile_mask|=(1U<<i);
        ESP_ERROR_CHECK(set_profile(0));
    }
    // Advertise only canonical API levels accepted and read back exactly on this device.
    for(int i=0;i<11;i++){
        int8_t actual=0;
        if(esp_wifi_set_max_tx_power(lab_powers[i])==ESP_OK &&
           esp_wifi_get_max_tx_power(&actual)==ESP_OK && actual==lab_powers[i])power_mask|=(1U<<i);
    }
    ESP_ERROR_CHECK(esp_wifi_set_max_tx_power(72));
    return ESP_OK;
}

esp_err_t radio_apply(int8_t power,uint8_t profile){
    bool supported=false;
    for(int i=0;i<11;i++)if(lab_powers[i]==power && (power_mask&(1U<<i)))supported=true;
    if(!supported || profile>=6 || !(profile_mask&(1U<<profile)))return ESP_ERR_INVALID_ARG;
    esp_err_t result=set_profile(profile);
    if(result!=ESP_OK)return result;
    result=esp_wifi_set_max_tx_power(power);
    if(result!=ESP_OK)return result;
    int8_t actual;
    result=esp_wifi_get_max_tx_power(&actual);
    return result==ESP_OK && actual==power?ESP_OK:ESP_FAIL;
}

esp_err_t radio_send(uint8_t kind,uint32_t test_id,uint32_t sequence,uint64_t timestamp,
                     uint32_t elapsed_ms,uint16_t flags,const void *body,uint16_t len,int *mac_status){
    if(mac_status)*mac_status=-1;
    if(!peer_valid || len>LAB_MAX_PAYLOAD)return ESP_ERR_INVALID_ARG;
    // One outstanding frame; a late callback must never be attributed to a different frame.
    if(outstanding){
        if(xSemaphoreTake(sent,0)!=pdTRUE)return ESP_ERR_TIMEOUT;
        outstanding=false;
    }
    wire_packet_t packet={.header={.magic=LAB_MAGIC,.version=LAB_VERSION,.kind=kind,
        .source=CONFIG_LAB_NODE_ID,.destination=CONFIG_LAB_PEER_ID,.test_id=test_id,
        .sequence=sequence,.timestamp_us=timestamp,.payload_len=len,.flags=flags,.elapsed_ms=elapsed_ms}};
    if(body && len)memcpy(packet.body,body,len);
    esp_err_t result=esp_now_send(peer_mac,(uint8_t *)&packet,sizeof(wire_header_t)+len);
    if(result!=ESP_OK)return result;
    outstanding=true;
    if(xSemaphoreTake(sent,pdMS_TO_TICKS(100))==pdTRUE){
        outstanding=false;
        if(mac_status)*mac_status=last_status;
    }
    return ESP_OK;
}

void radio_capabilities(uint16_t *powers,uint8_t *profiles){*powers=power_mask;*profiles=profile_mask;}
uint32_t radio_queue_drops(void){return __atomic_load_n(&queue_drops,__ATOMIC_RELAXED);}
bool radio_has_peer(void){return peer_valid;}
