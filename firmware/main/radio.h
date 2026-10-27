#pragma once
#include "esp_err.h"
#include "freertos/FreeRTOS.h"
#include "freertos/queue.h"
#include "protocol.h"

typedef struct {
    wire_packet_t packet;
    int8_t rssi;
    int64_t received_us;
} rx_event_t;

esp_err_t radio_init(QueueHandle_t receive_queue);
esp_err_t radio_apply(int8_t power, uint8_t profile);
esp_err_t radio_send(uint8_t kind, uint32_t test_id, uint32_t sequence, uint64_t timestamp,
                     uint32_t elapsed_ms, uint16_t flags, const void *body, uint16_t len, int *mac_status);
void radio_capabilities(uint16_t *powers, uint8_t *profiles);
uint32_t radio_queue_drops(void);
bool radio_has_peer(void);
