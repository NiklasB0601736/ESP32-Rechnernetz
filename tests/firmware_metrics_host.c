// Runs the actual firmware metrics.c on a host, without ESP-IDF or radio mocks.
#include <stddef.h>
#include "metrics.h"

void *memset(void *dest,int value,size_t length){
    unsigned char *p=dest;for(size_t i=0;i<length;i++)p[i]=(unsigned char)value;return dest;
}
void *memcpy(void *dest,const void *source,size_t length){
    unsigned char *p=dest;const unsigned char *s=source;for(size_t i=0;i<length;i++)p[i]=s[i];return dest;
}

static experiment_t receiver,sender;
#define CHECK(expression) do{if(!(expression))return __LINE__;}while(0)

__declspec(dllexport) int run_tests(void){
    command_t plan={.test_id=123,.source=1,.destination=2,.payload_bytes=128,.rate_pps=50,.duration_ms=1000};
    CHECK(experiment_arm(&receiver,&plan,2,1,1000000));
    wire_header_t data={.test_id=123,.sequence=4,.payload_len=128,.elapsed_ms=30};
    CHECK(experiment_receive(&receiver,&data,-60,1040000));
    CHECK(!experiment_receive(&receiver,&data,-30,1040100));
    data.sequence=1;CHECK(experiment_receive(&receiver,&data,-70,1040200));
    CHECK(receiver.stats.rx_unique==2 && receiver.stats.duplicates==1);
    CHECK(receiver.stats.rssi_count==2 && receiver.stats.rssi_sum==-130);
    data.sequence=5;data.elapsed_ms=1000;CHECK(!experiment_receive(&receiver,&data,-60,1040300));
    data.elapsed_ms=30;data.test_id=124;CHECK(!experiment_receive(&receiver,&data,-60,1040400));
    CHECK(receiver.stats.late==1 && receiver.stats.rx_unique==2);
    data.test_id=123;data.sequence=60000;CHECK(!experiment_receive(&receiver,&data,-60,1040500));
    CHECK(receiver.stats.late==2);
    CHECK(experiment_arm(&receiver,&plan,2,1,1040600)); // repeated arm never resets counters
    CHECK(receiver.stats.rx_unique==2);

    CHECK(experiment_arm(&sender,&plan,1,2,1000000));
    experiment_run(&sender,1000000);sender.stats.tx=31;
    wire_header_t echo={.test_id=123,.sequence=0,.timestamp_us=1000100};
    experiment_echo(&sender,&echo,1010100);
    echo.sequence=10;echo.timestamp_us=1020000;experiment_echo(&sender,&echo,1034000);
    experiment_echo(&sender,&echo,1034500); // duplicate
    CHECK(sender.stats.app_acks==2 && sender.stats.rtt_count==2);
    CHECK(sender.stats.rtt_sum_us==24000 && sender.stats.jitter_sum_us==4000);
    echo.sequence=20;echo.timestamp_us=1040000;experiment_echo(&sender,&echo,2040001);
    CHECK(sender.stats.app_acks==3 && sender.stats.rtt_count==2); // late echo is not a valid RTT
    echo.sequence=50;experiment_echo(&sender,&echo,2040010);
    CHECK(sender.stats.app_acks==3); // unsent sequence

    experiment_stop(&sender,1123456);
    CHECK(sender.window_ms==124 && sender.stats.elapsed_ms==124);
    experiment_tick(&sender,1123456+LAB_DRAIN_US-1,true);CHECK(!sender.finished);
    experiment_tick(&sender,1123456+LAB_DRAIN_US,true);CHECK(sender.stats.done && sender.finished);
    stats_t done=sender.stats;experiment_peer_stats(&receiver,&done,3000000);
    CHECK(receiver.stats.elapsed_ms==124);
    experiment_tick(&receiver,3000000+LAB_DRAIN_US,false);CHECK(receiver.finished && receiver.stats.done);
    data.sequence=6;data.elapsed_ms=40;CHECK(!experiment_receive(&receiver,&data,-60,5000000));
    CHECK(receiver.stats.rx_unique==2 && receiver.stats.late==3);

    plan.test_id=125;CHECK(experiment_arm(&receiver,&plan,2,1,6000000));
    data.test_id=125;data.sequence=0;CHECK(experiment_receive(&receiver,&data,-60,6001000));
    experiment_tick(&receiver,18000000,false);
    CHECK(receiver.finished && !receiver.stats.done); // source vanished: recover without fabricated DONE
    plan.test_id=126;CHECK(experiment_arm(&receiver,&plan,2,1,18000001));
    plan.payload_bytes=219;CHECK(!experiment_arm(&sender,&plan,1,2,19000000));
    return 0;
}
