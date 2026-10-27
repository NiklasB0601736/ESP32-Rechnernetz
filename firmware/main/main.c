#include <stdio.h>
#include <string.h>
#include "sdkconfig.h"
#include "esp_mac.h"
#include "esp_random.h"
#include "esp_timer.h"
#include "esp_wifi.h"
#include "freertos/task.h"
#include "nvs_flash.h"
#include "gateway.h"
#include "metrics.h"
#include "radio.h"

#ifdef CONFIG_LAB_MASTER
#define IS_MASTER 1
#else
#define IS_MASTER 0
#endif

static experiment_t experiment;
static node_status_t local;
static int8_t power=72,old_power=72;
static uint8_t profile,old_profile;
static uint32_t transaction;
static int64_t lease_deadline,peer_seen;
static uint32_t remote_peer_age=UINT32_MAX;
static uint32_t remote_seen_transaction;
static bool provisional,backup_valid;
static control_ack_t cache[32];
static size_t cache_next;

static bool active(void){return experiment.armed && !experiment.finished;}

static control_ack_t execute(const command_t *c,int64_t now){
    for(size_t i=0;i<32;i++)if(cache[i].id==c->id && cache[i].op==c->op)return cache[i];
    control_ack_t ack={.id=c->id,.op=c->op,.ok=0,.error=1};
    esp_err_t result=ESP_ERR_INVALID_ARG;
    switch(c->op){
    case OP_CONFIGURE:
        if(active() || provisional || c->lease_ms!=15000)break;
        old_power=power;old_profile=profile;backup_valid=true;
        result=radio_apply(c->power_qdbm,c->profile);
        if(result==ESP_OK){
            power=c->power_qdbm;profile=c->profile;transaction=c->id;
            provisional=true;lease_deadline=now+(int64_t)c->lease_ms*1000;
        }else radio_apply(old_power,old_profile);
        break;
    case OP_COMMIT:
        if(c->transaction!=transaction || !provisional || !peer_seen || now-peer_seen>2500000 ||
           remote_peer_age>2500 || remote_seen_transaction!=transaction)break;
        provisional=false;result=ESP_OK;
        break;
    case OP_ROLLBACK:
        if(c->transaction!=transaction || !backup_valid)break;
        result=radio_apply(old_power,old_profile);
        if(result==ESP_OK){power=old_power;profile=old_profile;provisional=false;backup_valid=false;}
        break;
    case OP_ARM:
        if(provisional)break;
        result=experiment_arm(&experiment,c,CONFIG_LAB_NODE_ID,CONFIG_LAB_PEER_ID,now)?ESP_OK:ESP_ERR_INVALID_ARG;
        break;
    case OP_RUN:
        if(!experiment.armed || experiment.plan.test_id!=c->test_id || experiment.plan.source!=CONFIG_LAB_NODE_ID)break;
        experiment_run(&experiment,now);result=ESP_OK;
        break;
    case OP_STOP:
        if(!experiment.armed || experiment.plan.test_id!=c->test_id)break;
        if(experiment.plan.source==CONFIG_LAB_NODE_ID){
            if(!experiment.started)experiment_run(&experiment,now);
            experiment_stop(&experiment,now);
        }else if(!experiment.started){experiment.finished=true;experiment.stats.done=1;}
        result=ESP_OK;
        break;
    default:break;
    }
    ack.ok=result==ESP_OK;ack.error=(uint16_t)result;
    cache[cache_next++%32]=ack;return ack;
}

static void update_status(int64_t now){
    local.uptime_ms=(uint32_t)(now/1000);local.power_qdbm=power;local.profile=profile;
    local.transaction=transaction;local.provisional=provisional;
    local.peer_age_ms=peer_seen?(uint32_t)((now-peer_seen)/1000):UINT32_MAX;
    local.link_healthy=local.peer_age_ms<2500 && remote_peer_age<2500 &&
        (!provisional || remote_seen_transaction==transaction);
    local.queue_drops=radio_queue_drops();
}

static void process_rx(const rx_event_t *event){
    const wire_header_t *h=&event->packet.header;
    const uint8_t *body=event->packet.body;
    int64_t now=esp_timer_get_time();peer_seen=event->received_us;
    switch(h->kind){
    case PK_CONTROL:
        if(!IS_MASTER && h->payload_len==sizeof(command_t)){
            command_t command;memcpy(&command,body,sizeof(command));
            control_ack_t ack=execute(&command,now);
            radio_send(PK_CONTROL_ACK,0,0,0,0,0,&ack,sizeof(ack),NULL);
        }break;
    case PK_CONTROL_ACK:
        if(IS_MASTER && h->payload_len==sizeof(control_ack_t)){
            control_ack_t ack;memcpy(&ack,body,sizeof(ack));gateway_ack(h->source,&ack);
        }break;
    case PK_STATUS:
        if(h->payload_len==sizeof(node_status_t)){
            node_status_t status;memcpy(&status,body,sizeof(status));remote_peer_age=status.peer_age_ms;
            local.seen_peer_transaction=status.transaction;
            remote_seen_transaction=status.seen_peer_transaction;
            if(IS_MASTER)gateway_status(h->source,&status);
        }break;
    case PK_STATS:
        if(h->payload_len==sizeof(stats_t)){
            stats_t stats;memcpy(&stats,body,sizeof(stats));
            if(IS_MASTER)gateway_stats(h->source,&stats);
            if(experiment.plan.destination==CONFIG_LAB_NODE_ID)experiment_peer_stats(&experiment,&stats,now);
        }break;
    case PK_DATA:
        if(experiment.plan.destination==CONFIG_LAB_NODE_ID && h->source==experiment.plan.source){
            bool unique=experiment_receive(&experiment,h,event->rssi,event->received_us);
            if(unique)local.rx_total++;
            if(unique && (h->flags&1))radio_send(PK_ECHO,h->test_id,h->sequence,h->timestamp_us,h->elapsed_ms,0,NULL,0,NULL);
        }break;
    case PK_ECHO:
        if(h->payload_len==0 && experiment.plan.source==CONFIG_LAB_NODE_ID)experiment_echo(&experiment,h,event->received_us);
        break;
    default:break;
    }
}

void app_main(void){
    esp_err_t result=nvs_flash_init();
    if(result==ESP_ERR_NVS_NO_FREE_PAGES || result==ESP_ERR_NVS_NEW_VERSION_FOUND){
        ESP_ERROR_CHECK(nvs_flash_erase());result=nvs_flash_init();
    }
    ESP_ERROR_CHECK(result);
    QueueHandle_t receive_queue=xQueueCreate(48,sizeof(rx_event_t));
    QueueHandle_t command_queue=xQueueCreate(12,sizeof(gateway_command_t));
    configASSERT(receive_queue && command_queue);
    ESP_ERROR_CHECK(radio_init(receive_queue));
    local.boot_id=esp_random();local.role=IS_MASTER;local.peer_id=CONFIG_LAB_PEER_ID;
    local.channel=CONFIG_LAB_CHANNEL;local.bandwidth_mhz=20;
    uint16_t power_capabilities;uint8_t profile_capabilities;
    radio_capabilities(&power_capabilities,&profile_capabilities);
    local.powers_mask=power_capabilities;local.profiles_mask=profile_capabilities;
    ESP_ERROR_CHECK(esp_wifi_get_mac(WIFI_IF_STA,local.mac));
    ESP_ERROR_CHECK(esp_wifi_get_max_tx_power(&power));
    if(IS_MASTER)gateway_init(command_queue);
    printf("Funklabor STA MAC %02X:%02X:%02X:%02X:%02X:%02X · node %u\n",local.mac[0],local.mac[1],local.mac[2],local.mac[3],local.mac[4],local.mac[5],CONFIG_LAB_NODE_ID);
    if(!radio_has_peer())gateway_warning("Peer-MAC fehlt. In menuconfig unter Funklabor die erlaubte STA-MAC setzen.");
    int64_t next_report=0;
    uint8_t payload[LAB_MAX_PAYLOAD];
    for(int i=0;i<LAB_MAX_PAYLOAD;i++)payload[i]=(uint8_t)(i*73+19);
    for(;;){
        gateway_command_t cmd;
        while(xQueueReceive(command_queue,&cmd,0)==pdTRUE){
            if(cmd.target==CONFIG_LAB_NODE_ID){control_ack_t ack=execute(&cmd.command,esp_timer_get_time());gateway_ack(cmd.target,&ack);}
            else radio_send(PK_CONTROL,0,0,0,0,0,&cmd.command,sizeof(cmd.command),NULL);
        }
        rx_event_t received;
        // Bounded work prevents a full receive queue from starving watchdogs and control.
        for(int i=0;i<48 && xQueueReceive(receive_queue,&received,0)==pdTRUE;i++)process_rx(&received);
        int64_t now=esp_timer_get_time();
        if(provisional && now>=lease_deadline){
            if(radio_apply(old_power,old_profile)==ESP_OK){power=old_power;profile=old_profile;provisional=false;backup_valid=false;}
            gateway_warning("Konfigurationsfrist abgelaufen: vorherige Konfiguration wiederhergestellt.");
        }
        bool sender=experiment.plan.source==CONFIG_LAB_NODE_ID;
        experiment_tick(&experiment,now,sender);
        if(sender && experiment.sending && now>=experiment.next_send_us && experiment.stats.tx<LAB_MAX_PACKETS){
            uint32_t seq=experiment.stats.tx;
            int mac=-1;
            esp_err_t sent=radio_send(PK_DATA,experiment.plan.test_id,seq,(uint64_t)now,
                (uint32_t)((now-experiment.start_us)/1000),seq%10==0?1:0,payload,experiment.plan.payload_bytes,&mac);
            if(sent==ESP_OK){
                experiment.stats.tx++;local.tx_total++;
                if(mac==1)experiment.stats.mac_ok++;
                else if(mac==0)experiment.stats.mac_fail++;
            }else experiment.stats.send_errors++;
            // No catch-up burst when processing stalls; actual TX is always reported.
            experiment.next_send_us=now+1000000/experiment.plan.rate_pps;
        }
        if(now>=next_report){
            update_status(now);
            if(IS_MASTER)gateway_status(CONFIG_LAB_NODE_ID,&local);
            radio_send(PK_STATUS,0,0,0,0,0,&local,sizeof(local),NULL);
            if(experiment.armed){
                experiment.stats.queue_drops=radio_queue_drops();
                if(IS_MASTER)gateway_stats(CONFIG_LAB_NODE_ID,&experiment.stats);
                radio_send(PK_STATS,experiment.plan.test_id,0,0,0,0,&experiment.stats,sizeof(experiment.stats),NULL);
            }
            next_report=esp_timer_get_time()+1000000;
        }
        vTaskDelay(pdMS_TO_TICKS(1));
    }
}
