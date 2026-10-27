#pragma once
#include "protocol.h"

typedef struct {
    command_t plan;
    stats_t stats;
    bool armed, started, sending, finished;
    int64_t armed_at_us, start_us, end_us, next_send_us, drain_deadline_us, last_activity_us;
    uint32_t window_ms;
    uint8_t seen[(LAB_MAX_PACKETS+7)/8];
    uint8_t echoes[(LAB_MAX_PACKETS+7)/8];
    uint64_t previous_rtt;
} experiment_t;

bool experiment_arm(experiment_t *exp,const command_t *plan,uint16_t own_id,uint16_t peer_id,int64_t now);
void experiment_run(experiment_t *exp,int64_t now);
void experiment_stop(experiment_t *exp,int64_t now);
bool experiment_receive(experiment_t *exp,const wire_header_t *header,int8_t rssi,int64_t received);
void experiment_echo(experiment_t *exp,const wire_header_t *header,int64_t received);
void experiment_tick(experiment_t *exp,int64_t now,bool sender);
void experiment_peer_stats(experiment_t *exp,const stats_t *peer,int64_t now);
