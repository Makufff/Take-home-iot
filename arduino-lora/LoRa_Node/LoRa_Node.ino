/*******************************************************************************
 * LoRa Node: Arduino UNO R4 WiFi + Cytron LoRa RFM 915MHz shield
 *
 * Uplink (fPort 1, every TX_INTERVAL seconds, 4 bytes):
 *   byte 0-1 : light_raw    (uint16, big endian, analogRead(A0) 0-1023)
 *   byte 2   : light_digital (digitalRead(D0) of MH-Sensor-Series, 0/1)
 *   byte 3   : led          (LED matrix state, 0 = off, 1 = on)
 *
 * Downlink (fPort 1, 1 byte):
 *   0x00 = LED matrix off, 0x01 = LED matrix on
 *
 * Based on reference/lora-uno-r4/LoRa_OTAA.ino (MCCI LMIC, OTAA).
 * Keys live in secrets.h (copy secrets.example.h -> secrets.h).
 *******************************************************************************/

#include <lmic.h>
#include <hal/hal.h>
#include <SPI.h>
#include "Arduino_LED_Matrix.h"
#include "secrets.h"

void os_getArtEui (u1_t* buf) { memcpy_P(buf, APPEUI, 8); }
void os_getDevEui (u1_t* buf) { memcpy_P(buf, DEVEUI, 8); }
void os_getDevKey (u1_t* buf) { memcpy_P(buf, APPKEY, 16); }

// MH-Sensor-Series light sensor (LDR) on the shield
const int LIGHT_ANALOG_PIN = A0;
const int LIGHT_DIGITAL_PIN = 0;

// Schedule TX every this many seconds (might become longer due to duty
// cycle limitations). A downlink is only received right after an uplink
// (Class A), so this is also the worst-case delay for an LED command.
const unsigned TX_INTERVAL = 60;

// Pin mapping (Cytron LoRa RFM shield)
const lmic_pinmap lmic_pins = {
    .nss = 10,
    .rxtx = LMIC_UNUSED_PIN,
    .rst = 7,
    .dio = {2, 5, 6},
};

static uint8_t payload[4];
static osjob_t sendjob;

ArduinoLEDMatrix matrix;
static bool ledOn = false;

// 8x12 light bulb icon shown when the LED is on
static uint8_t frameOn[8][12] = {
    { 0, 0, 0, 0, 1, 1, 1, 1, 0, 0, 0, 0 },
    { 0, 0, 0, 1, 1, 1, 1, 1, 1, 0, 0, 0 },
    { 0, 0, 1, 1, 1, 1, 1, 1, 1, 1, 0, 0 },
    { 0, 0, 1, 1, 1, 1, 1, 1, 1, 1, 0, 0 },
    { 0, 0, 0, 1, 1, 1, 1, 1, 1, 0, 0, 0 },
    { 0, 0, 0, 0, 1, 1, 1, 1, 0, 0, 0, 0 },
    { 0, 0, 0, 0, 1, 1, 1, 1, 0, 0, 0, 0 },
    { 0, 0, 0, 0, 0, 1, 1, 0, 0, 0, 0, 0 },
};
static uint8_t frameOff[8][12] = { 0 };

void setLed(bool on) {
    ledOn = on;
    if (on)
        matrix.renderBitmap(frameOn, 8, 12);
    else
        matrix.renderBitmap(frameOff, 8, 12);
    Serial.print(F("LED matrix: "));
    Serial.println(on ? F("ON") : F("OFF"));
}

void handleDownlink() {
    if (LMIC.dataLen == 0)
        return;

    Serial.print(F("Downlink fPort "));
    Serial.print(LMIC.frame[LMIC.dataBeg - 1]);
    Serial.print(F(", HEX: "));
    for (int i = 0; i < LMIC.dataLen; i++) {
        if (LMIC.frame[LMIC.dataBeg + i] < 0x10)
            Serial.print('0');
        Serial.print(LMIC.frame[LMIC.dataBeg + i], HEX);
        Serial.print(' ');
    }
    Serial.println();

    uint8_t cmd = LMIC.frame[LMIC.dataBeg];
    if (cmd == 0x00 || cmd == 0x01)
        setLed(cmd == 0x01);
    else
        Serial.println(F("Unknown command"));
}

void onEvent (ev_t ev) {
    Serial.print(os_getTime());
    Serial.print(": ");
    switch(ev) {
        case EV_JOINING:
            Serial.println(F("EV_JOINING"));
            break;
        case EV_JOINED:
            Serial.println(F("EV_JOINED"));
            // Disable link check validation (automatically enabled
            // during join, but because slow data rates change max TX
            // size, we don't use it in this example.
            LMIC_setLinkCheckMode(0);
            break;
        case EV_JOIN_FAILED:
            Serial.println(F("EV_JOIN_FAILED"));
            break;
        case EV_REJOIN_FAILED:
            Serial.println(F("EV_REJOIN_FAILED"));
            break;
        case EV_TXCOMPLETE:
            Serial.println(F("EV_TXCOMPLETE (includes waiting for RX windows)"));
            if (LMIC.txrxFlags & TXRX_ACK)
                Serial.println(F("Received ack"));
            handleDownlink();
            // Schedule next transmission
            os_setTimedCallback(&sendjob, os_getTime()+sec2osticks(TX_INTERVAL), do_send);
            break;
        case EV_RESET:
            Serial.println(F("EV_RESET"));
            break;
        case EV_LINK_DEAD:
            Serial.println(F("EV_LINK_DEAD"));
            break;
        case EV_LINK_ALIVE:
            Serial.println(F("EV_LINK_ALIVE"));
            break;
        case EV_TXSTART:
            Serial.println(F("EV_TXSTART"));
            break;
        case EV_TXCANCELED:
            Serial.println(F("EV_TXCANCELED"));
            break;
        case EV_RXSTART:
            /* do not print anything -- it wrecks timing */
            break;
        case EV_JOIN_TXCOMPLETE:
            Serial.println(F("EV_JOIN_TXCOMPLETE: no JoinAccept"));
            break;
        default:
            Serial.print(F("Event: "));
            Serial.println((unsigned) ev);
            break;
    }
}

void do_send(osjob_t* j){
    // Check if there is not a current TX/RX job running
    if (LMIC.opmode & OP_TXRXPEND) {
        Serial.println(F("OP_TXRXPEND, not sending"));
        return;
    }

    uint16_t lightRaw = analogRead(LIGHT_ANALOG_PIN);
    uint8_t lightDigital = digitalRead(LIGHT_DIGITAL_PIN);

    payload[0] = lightRaw >> 8;
    payload[1] = lightRaw & 0xFF;
    payload[2] = lightDigital;
    payload[3] = ledOn ? 1 : 0;

    Serial.print(F("light_raw="));
    Serial.print(lightRaw);
    Serial.print(F(" light_digital="));
    Serial.print(lightDigital);
    Serial.print(F(" led="));
    Serial.println(ledOn);

    // Prepare upstream data transmission at the next possible time.
    LMIC_setTxData2(1, payload, sizeof(payload), 0);
    Serial.println(F("Packet queued"));
    // Next TX is scheduled after TX_COMPLETE event.
}

void setup() {
    Serial.begin(9600);
    Serial.println(F("Starting"));

    pinMode(LIGHT_DIGITAL_PIN, INPUT);
    matrix.begin();
    setLed(false);

    // LMIC init
    os_init();
    // Reset the MAC state. Session and pending data transfers will be discarded.
    LMIC_reset();

    LMIC_setupChannel(
        0,
        923200000,
        DR_RANGE_MAP(DR_SF12, DR_SF7),
        BAND_CENTI
    );
    LMIC_setDrTxpow(DR_SF12, 14);
    // Start job (sending automatically starts OTAA too)
    do_send(&sendjob);
}

void loop() {
    os_runloop_once();
}
