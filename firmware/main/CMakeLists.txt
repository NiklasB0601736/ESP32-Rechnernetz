idf_component_register(SRCS "main.c" "radio.c" "metrics.c" "gateway.c"
    INCLUDE_DIRS "." REQUIRES esp_wifi esp_event esp_netif nvs_flash esp_timer esp_driver_uart)
target_compile_options(${COMPONENT_LIB} PRIVATE -Wall -Wextra -Werror)
