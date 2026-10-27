#include <string.h>
#include "metrics.h"

bool experiment_arm(experiment_t *e,const command_t *p,uint16_t own,uint16_t peer,int64_t now){
    if(!p->test_id || p->source==p->destination ||
       !((p->source==own && p->destination==peer)||(p->source==peer && p->destination==own)) ||
       p->payload_bytes<1 || p->payload_bytes>LAB_MAX_PAYLOAD || p->rate_pps<1 || p->rate_pps>500 ||
       p->duration_ms<1000 || p->duration_ms>120000 ||
       (uint64_t)p->duration_ms*p->rate_pps>LAB_MAX_PACKETS*1000ULL)return false;
    if(e->armed && !e->finished && e->plan.test_id!=p->test_id)return false;
    if(e->plan.test_id==p->test_id && e->armed)return true;
    memset(e,0,sizeof(*e));
    e->plan=*p;e->armed=true;e->stats.test_id=p->test_id;
    e->window_ms=p->duration_ms;e->last_activity_us=now;e->armed_at_us=now;
    return true;
}

void experiment_run(experiment_t *e,int64_t now){
    if(!e->armed || e->started)return;
    e->started=true;e->sending=true;e->start_us=now;e->next_send_us=now;
}

void experiment_stop(experiment_t *e,int64_t now){
    if(!e->started || !e->sending)return;
    e->sending=false;e->end_us=now;
    uint32_t elapsed=(uint32_t)((now-e->start_us+999)/1000);
    e->window_ms=elapsed<e->plan.duration_ms?elapsed:e->plan.duration_ms;
    if(!e->window_ms)e->window_ms=1;
    e->stats.elapsed_ms=e->window_ms;
    e->drain_deadline_us=now+LAB_DRAIN_US;
}

bool experiment_receive(experiment_t *e,const wire_header_t *h,int8_t rssi,int64_t now){
    if(!e->armed || h->test_id!=e->plan.test_id)return false;
    if(e->finished || h->elapsed_ms>=e->window_ms || h->sequence>=LAB_MAX_PACKETS ||
       h->payload_len!=e->plan.payload_bytes){e->stats.late++;return false;}
    e->last_activity_us=now;
    e->started=true;
    uint8_t mask=1U<<(h->sequence%8);
    uint8_t *byte=&e->seen[h->sequence/8];
    if(*byte&mask){e->stats.duplicates++;return false;}
    *byte|=mask;e->stats.rx_unique++;
    if(rssi!=-127){e->stats.rssi_count++;e->stats.rssi_sum+=rssi;}
    return true;
}

void experiment_echo(experiment_t *e,const wire_header_t *h,int64_t now){
    if(!e->armed || !e->started || h->test_id!=e->plan.test_id || h->sequence>=e->stats.tx ||
       h->sequence%10 || h->timestamp_us>(uint64_t)now || h->timestamp_us<(uint64_t)e->start_us)return;
    uint8_t mask=1U<<(h->sequence%8),*byte=&e->echoes[h->sequence/8];
    if(*byte&mask)return;
    *byte|=mask;e->stats.app_acks++;
    uint64_t rtt=(uint64_t)now-h->timestamp_us;
    if(rtt>LAB_RTT_TIMEOUT_US || e->finished)return;
    if(e->stats.rtt_count)e->stats.jitter_sum_us+=rtt>e->previous_rtt?rtt-e->previous_rtt:e->previous_rtt-rtt;
    e->previous_rtt=rtt;e->stats.rtt_count++;e->stats.rtt_sum_us+=rtt;
}

void experiment_tick(experiment_t *e,int64_t now,bool sender){
    if(!e->armed || e->finished)return;
    if(sender && e->sending){
        int64_t elapsed=now-e->start_us;
        e->stats.elapsed_ms=(uint32_t)(elapsed/1000);
        if(elapsed>=(int64_t)e->plan.duration_ms*1000)experiment_stop(e,now);
    }
    if(e->drain_deadline_us && now>=e->drain_deadline_us){e->finished=true;e->stats.done=1;}
    if(!sender && now-e->armed_at_us>((int64_t)e->plan.duration_ms+10000)*1000)e->finished=true;
    if(sender && !e->started && now-e->armed_at_us>10000000)e->finished=true;
    // Receiver without DONE remains incomplete; backend times out. Do not fabricate final counts.
}

void experiment_peer_stats(experiment_t *e,const stats_t *peer,int64_t now){
    if(!e->armed || peer->test_id!=e->plan.test_id || e->finished)return;
    e->stats.elapsed_ms=peer->elapsed_ms;
    if(peer->done && !e->drain_deadline_us){
        e->window_ms=peer->elapsed_ms;
        e->drain_deadline_us=now+LAB_DRAIN_US;
    }
}
