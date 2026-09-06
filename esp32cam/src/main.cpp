#include <Arduino.h>
#include <WiFi.h>
#include <WebServer.h>
#include "esp_camera.h"

#include "network_secrets.hpp"

// -----------------------------------------------------------------------------
// AI Thinker ESP32-CAM pinout
// -----------------------------------------------------------------------------

#define PWDN_GPIO_NUM     32
#define RESET_GPIO_NUM    -1
#define XCLK_GPIO_NUM      0
#define SIOD_GPIO_NUM     26
#define SIOC_GPIO_NUM     27

#define Y9_GPIO_NUM       35
#define Y8_GPIO_NUM       34
#define Y7_GPIO_NUM       39
#define Y6_GPIO_NUM       36
#define Y5_GPIO_NUM       21
#define Y4_GPIO_NUM       19
#define Y3_GPIO_NUM       18
#define Y2_GPIO_NUM        5

#define VSYNC_GPIO_NUM    25
#define HREF_GPIO_NUM     23
#define PCLK_GPIO_NUM     22

// -----------------------------------------------------------------------------
// HTTP server
// -----------------------------------------------------------------------------

WebServer server(80);

// -----------------------------------------------------------------------------
// Camera
// -----------------------------------------------------------------------------

bool initCamera() {
    camera_config_t config = {};

    config.ledc_channel = LEDC_CHANNEL_0;
    config.ledc_timer = LEDC_TIMER_0;

    config.pin_d0 = Y2_GPIO_NUM;
    config.pin_d1 = Y3_GPIO_NUM;
    config.pin_d2 = Y4_GPIO_NUM;
    config.pin_d3 = Y5_GPIO_NUM;
    config.pin_d4 = Y6_GPIO_NUM;
    config.pin_d5 = Y7_GPIO_NUM;
    config.pin_d6 = Y8_GPIO_NUM;
    config.pin_d7 = Y9_GPIO_NUM;

    config.pin_xclk = XCLK_GPIO_NUM;
    config.pin_pclk = PCLK_GPIO_NUM;
    config.pin_vsync = VSYNC_GPIO_NUM;
    config.pin_href = HREF_GPIO_NUM;

    config.pin_sccb_sda = SIOD_GPIO_NUM;
    config.pin_sccb_scl = SIOC_GPIO_NUM;

    config.pin_pwdn = PWDN_GPIO_NUM;
    config.pin_reset = RESET_GPIO_NUM;

    config.xclk_freq_hz = 20000000;

    config.pixel_format = PIXFORMAT_JPEG;

    if (psramFound()) {
        config.frame_size = FRAMESIZE_VGA;   // 640x480
        config.jpeg_quality = 10;
        config.fb_count = 2;
        config.grab_mode = CAMERA_GRAB_LATEST;
    } else {
        config.frame_size = FRAMESIZE_QVGA;  // 320x240
        config.jpeg_quality = 12;
        config.fb_count = 1;
        config.grab_mode = CAMERA_GRAB_WHEN_EMPTY;
    }

    esp_err_t err = esp_camera_init(&config);

    return err == ESP_OK;
}

// -----------------------------------------------------------------------------
// HTTP handlers
// -----------------------------------------------------------------------------

void handleRoot() {
    server.send(
        200,
        "text/plain",
        "secureGate ESP-CAM\n"
    );
}


void handleCapture() {
    camera_fb_t *fb = esp_camera_fb_get();

    if (!fb) {
        server.send(
            500,
            "text/plain",
            "Camera capture failed"
        );

        return;
    }

    server.setContentLength(fb->len);

    server.send(
        200,
        "image/jpeg",
        ""
    );

    WiFiClient client = server.client();

    client.write(
        fb->buf,
        fb->len
    );

    esp_camera_fb_return(fb);
}


void handleNotFound() {
    server.send(
        404,
        "text/plain",
        "Not found"
    );
}

// -----------------------------------------------------------------------------
// Wi-Fi
// -----------------------------------------------------------------------------

bool connectWiFi() {
    WiFi.mode(WIFI_STA);

    WiFi.setSleep(false);

    WiFi.begin(
        WIFI_SSID,
        WIFI_PASSWORD
    );

    const unsigned long timeout_ms = 30000;
    const unsigned long start = millis();

    while (WiFi.status() != WL_CONNECTED) {
        delay(250);

        if (millis() - start >= timeout_ms) {
            return false;
        }
    }

    return true;
}

// -----------------------------------------------------------------------------
// Setup
// -----------------------------------------------------------------------------

void setup() {
    delay(1000);

    if (!initCamera()) {
        while (true) {
            delay(1000);
        }
    }

    if (!connectWiFi()) {
        ESP.restart();
    }

    server.on(
        "/",
        HTTP_GET,
        handleRoot
    );

    server.on(
        "/capture",
        HTTP_GET,
        handleCapture
    );

    server.on(
        "/favicon.ico",
        HTTP_GET,
        []() {
            server.send(204);
        }
    );

    server.onNotFound(
        handleNotFound
    );

    server.begin();
}

// -----------------------------------------------------------------------------
// Runtime
// -----------------------------------------------------------------------------

void loop() {
    // Si se pierde Wi-Fi, reiniciar para recuperar conexión.
    if (WiFi.status() != WL_CONNECTED) {
        delay(1000);
        ESP.restart();
    }

    server.handleClient();

    delay(2);
}