#pragma once
#include <stdbool.h>
#include <stdint.h>

#define LAB_MAGIC 0x4c46
#define LAB_VERSION 1
#define LAB_MAX_PAYLOAD 218
#define LAB_MAX_PACKETS 60000
#define LAB_DRAIN_US 1500000LL
#define LAB_RTT_TIMEOUT_US 1000000LL

enum packet_kind { PK_CONTROL=1, PK_CONTROL_ACK, PK_STATUS, PK_STATS, PK_DATA, PK_ECHO };
enum operation { OP_CONFIGURE=1, OP_COMMIT, OP_ROLLBACK, OP_ARM, OP_RUN, OP_STOP };

// Packed, little endian, identical ESP32 targets. No pointers or platform enum fields on wire.
typedef struct __attribute__((packed)) {
    uint16_t magic;
    uint8_t version, kind;
    uint16_t source, destination;
    uint32_t test_id, sequence;
    uint64_t timestamp_us;
    uint16_t payload_len, flags; // flags bit 0: echo requested
    uint32_t elapsed_ms;
} wire_header_t;
_Static_assert(sizeof(wire_header_t)==32,"Wire header must be 32 bytes");

typedef struct {
    uint32_t id, transaction, test_id;
    uint16_t source, destination, payload_bytes, rate_pps;
    uint32_t duration_ms, lease_ms;
    int8_t power_qdbm;
    uint8_t profile, op, reserved;
} command_t;
_Static_assert(sizeof(command_t)==32,"Command must be 32 bytes");

typedef struct __attribute__((packed)) {
    uint32_t id;
    uint8_t op, ok;
    uint16_t error;
} control_ack_t;

typedef struct __attribute__((packed)) {
    uint32_t uptime_ms, boot_id, tx_total, rx_total, peer_age_ms, transaction, queue_drops, seen_peer_transaction;
    uint16_t peer_id, powers_mask;
    uint8_t role, profile, channel, bandwidth_mhz, profiles_mask;
    int8_t power_qdbm;
    uint8_t link_healthy, provisional, mac[6];
} node_status_t;
_Static_assert(sizeof(node_status_t)==50,"Status must be 50 bytes");

typedef struct __attribute__((packed)) {
    uint32_t test_id, tx, rx_unique, duplicates, late, mac_ok, mac_fail, send_errors;
    uint32_t app_acks, rtt_count, rssi_count, elapsed_ms, queue_drops;
    uint64_t rtt_sum_us, jitter_sum_us;
    int64_t rssi_sum;
    uint8_t done;
} stats_t;
_Static_assert(sizeof(stats_t)<=LAB_MAX_PAYLOAD,"Statistics must fit in one frame");

typedef struct __attribute__((packed)) {
    wire_header_t header;
    uint8_t body[LAB_MAX_PAYLOAD];
} wire_packet_t;
_Static_assert(sizeof(wire_packet_t)==250,"Maximum ESP-NOW v1 packet");

extern const int8_t lab_powers[11];
extern const char *const lab_profiles[6];
extern const char *const lab_operations[7];
