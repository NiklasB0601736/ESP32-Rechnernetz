#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "cJSON.h"
#include "driver/uart.h"
#include "freertos/task.h"
#include "gateway.h"
#include "sdkconfig.h"

static QueueHandle_t commands;
static QueueHandle_t serial_output;

static void emit(cJSON *root){
    char *line=cJSON_PrintUnformatted(root);
    if(line){
        if(serial_output){
            // Never block the experiment task on serial throughput. ACKs are retryable,
            // cumulative status/final reports repeat if the bounded queue is full.
            if(xQueueSend(serial_output,&line,0)!=pdTRUE)free(line);
        }else{printf("%s\n",line);fflush(stdout);free(line);}
    }
    cJSON_Delete(root);
}
static cJSON *base(const char *type,uint16_t node_id){
    cJSON *root=cJSON_CreateObject();
    cJSON_AddNumberToObject(root,"v",1);cJSON_AddStringToObject(root,"type",type);
    cJSON_AddNumberToObject(root,"node_id",node_id);return root;
}

void gateway_warning(const char *message){
    cJSON *root=base("warning",CONFIG_LAB_NODE_ID);
    cJSON_AddStringToObject(root,"message",message);emit(root);
}

void gateway_status(uint16_t nid,const node_status_t *s){
    cJSON *root=base("status",nid);
    char mac[18];snprintf(mac,sizeof(mac),"%02X:%02X:%02X:%02X:%02X:%02X",s->mac[0],s->mac[1],s->mac[2],s->mac[3],s->mac[4],s->mac[5]);
    cJSON_AddStringToObject(root,"mac",mac);
    cJSON_AddStringToObject(root,"chip","ESP32");cJSON_AddStringToObject(root,"idf","v6.0.1");
    cJSON_AddStringToObject(root,"role",s->role?"master":"slave");
    cJSON_AddStringToObject(root,"profile",s->profile<6?lab_profiles[s->profile]:"unknown");
    cJSON_AddNumberToObject(root,"power_qdbm",s->power_qdbm);
    cJSON_AddNumberToObject(root,"channel",s->channel);cJSON_AddNumberToObject(root,"bandwidth_mhz",s->bandwidth_mhz);
    cJSON_AddNumberToObject(root,"tx_total",s->tx_total);cJSON_AddNumberToObject(root,"rx_total",s->rx_total);
    cJSON_AddNumberToObject(root,"peer_id",s->peer_id);cJSON_AddNumberToObject(root,"boot_id",s->boot_id);
    cJSON_AddNumberToObject(root,"transaction",s->transaction);
    cJSON_AddNumberToObject(root,"seen_peer_transaction",s->seen_peer_transaction);
    cJSON_AddBoolToObject(root,"link_healthy",s->link_healthy);cJSON_AddBoolToObject(root,"provisional",s->provisional);
    cJSON *powers=cJSON_AddArrayToObject(root,"powers_qdbm"),*profiles=cJSON_AddArrayToObject(root,"profiles");
    for(int i=0;i<11;i++)if(s->powers_mask&(1U<<i))cJSON_AddItemToArray(powers,cJSON_CreateNumber(lab_powers[i]));
    for(int i=0;i<6;i++)if(s->profiles_mask&(1U<<i))cJSON_AddItemToArray(profiles,cJSON_CreateString(lab_profiles[i]));
    emit(root);
}

void gateway_stats(uint16_t nid,const stats_t *s){
    cJSON *root=base("stats",nid);
#define FIELD(key) cJSON_AddNumberToObject(root,#key,(double)s->key)
    FIELD(test_id);FIELD(tx);FIELD(rx_unique);FIELD(duplicates);FIELD(late);FIELD(mac_ok);FIELD(mac_fail);
    FIELD(send_errors);FIELD(app_acks);FIELD(rtt_count);FIELD(rtt_sum_us);FIELD(jitter_sum_us);
    FIELD(rssi_count);FIELD(rssi_sum);FIELD(elapsed_ms);FIELD(queue_drops);
#undef FIELD
    cJSON_AddBoolToObject(root,"done",s->done);emit(root);
}

void gateway_ack(uint16_t nid,const control_ack_t *a){
    cJSON *root=base("ack",nid);
    cJSON_AddNumberToObject(root,"id",a->id);cJSON_AddBoolToObject(root,"ok",a->ok);
    cJSON_AddStringToObject(root,"op",a->op<7?lab_operations[a->op]:"invalid");
    if(!a->ok){char message[64];snprintf(message,sizeof(message),"Knoten lehnt Befehl ab (Code %u)",a->error);cJSON_AddStringToObject(root,"error",message);}
    emit(root);
}

static bool integer(cJSON *root,const char *key,double min,double max,uint32_t *out){
    cJSON *item=cJSON_GetObjectItemCaseSensitive(root,key);
    if(!cJSON_IsNumber(item) || item->valuedouble<min || item->valuedouble>max ||
       item->valuedouble!=(double)(uint32_t)item->valuedouble)return false;
    *out=(uint32_t)item->valuedouble;return true;
}

static bool parse(const char *line,gateway_command_t *out){
    cJSON *root=cJSON_Parse(line);if(!root)return false;
    uint32_t value=0;bool ok=false;command_t *c=&out->command;memset(out,0,sizeof(*out));
    if(!integer(root,"v",1,1,&value) || !integer(root,"id",1,4294967295.0,&c->id) ||
       !integer(root,"node_id",1,65535,&value))goto done;
    out->target=(uint16_t)value;
    if(out->target!=CONFIG_LAB_NODE_ID && out->target!=CONFIG_LAB_PEER_ID)goto done;
    cJSON *op=cJSON_GetObjectItemCaseSensitive(root,"op");if(!cJSON_IsString(op))goto done;
    for(int i=1;i<7;i++)if(!strcmp(op->valuestring,lab_operations[i]))c->op=i;
    if(!c->op)goto done;
    if(c->op==OP_CONFIGURE){
        if(!integer(root,"power_qdbm",8,80,&value))goto done;
        c->power_qdbm=(int8_t)value;
        if(!integer(root,"lease_ms",15000,15000,&c->lease_ms))goto done;
        cJSON *p=cJSON_GetObjectItemCaseSensitive(root,"profile");if(!cJSON_IsString(p))goto done;
        c->profile=255;
        for(int i=0;i<6;i++)if(!strcmp(p->valuestring,lab_profiles[i]))c->profile=i;
        if(c->profile==255)goto done;
    }else if(c->op==OP_COMMIT || c->op==OP_ROLLBACK){
        if(!integer(root,"transaction",1,4294967295.0,&c->transaction))goto done;
    }else{
        if(!integer(root,"test_id",1,4294967295.0,&c->test_id))goto done;
        if(c->op==OP_ARM){
            if(!integer(root,"source",1,65535,&value))goto done;
            c->source=value;
            if(!integer(root,"destination",1,65535,&value))goto done;
            c->destination=value;
            if(!integer(root,"payload_bytes",1,LAB_MAX_PAYLOAD,&value))goto done;
            c->payload_bytes=value;
            if(!integer(root,"rate_pps",1,500,&value))goto done;
            c->rate_pps=value;
            if(!integer(root,"duration_ms",1000,120000,&c->duration_ms))goto done;
        }
    }
    ok=true;
done:
    cJSON_Delete(root);return ok;
}

static void serial_reader(void *unused){
    (void)unused;
    char line[512];size_t used=0;bool dropping=false;
    for(;;){
        uint8_t buffer[64];int len=uart_read_bytes(UART_NUM_0,buffer,sizeof(buffer),pdMS_TO_TICKS(100));
        for(int i=0;i<len;i++){
            uint8_t b=buffer[i];
            if(b=='\n'){
                line[used]=0;gateway_command_t parsed;
                if(!dropping && parse(line,&parsed))xQueueSend(commands,&parsed,pdMS_TO_TICKS(100));
                used=0;dropping=false;
            }else if(!dropping && b!='\r'){
                if(used+1<sizeof(line))line[used++]=(char)b;
                else{used=0;dropping=true;}
            }
        }
    }
}

static void serial_writer(void *unused){
    (void)unused;
    for(;;){
        char *line=NULL;
        if(xQueueReceive(serial_output,&line,portMAX_DELAY)==pdTRUE){
            uart_write_bytes(UART_NUM_0,line,strlen(line));
            uart_write_bytes(UART_NUM_0,"\n",1);
            free(line);
        }
    }
}

void gateway_init(QueueHandle_t queue){
    commands=queue;
    ESP_ERROR_CHECK(uart_driver_install(UART_NUM_0,2048,4096,0,NULL,0));
    uart_config_t config={.baud_rate=115200,.data_bits=UART_DATA_8_BITS,.parity=UART_PARITY_DISABLE,
        .stop_bits=UART_STOP_BITS_1,.flow_ctrl=UART_HW_FLOWCTRL_DISABLE,.source_clk=UART_SCLK_DEFAULT};
    ESP_ERROR_CHECK(uart_param_config(UART_NUM_0,&config));
    serial_output=xQueueCreate(16,sizeof(char *));
    configASSERT(serial_output);
    if(xTaskCreate(serial_reader,"serial_rx",4096,NULL,4,NULL)!=pdPASS)abort();
    if(xTaskCreate(serial_writer,"serial_tx",3072,NULL,3,NULL)!=pdPASS)abort();
}
