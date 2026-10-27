#pragma once
#include "freertos/FreeRTOS.h"
#include "freertos/queue.h"
#include "protocol.h"

typedef struct {uint16_t target;command_t command;} gateway_command_t;
void gateway_init(QueueHandle_t queue);
void gateway_status(uint16_t node_id,const node_status_t *status);
void gateway_stats(uint16_t node_id,const stats_t *stats);
void gateway_ack(uint16_t node_id,const control_ack_t *ack);
void gateway_warning(const char *message);
