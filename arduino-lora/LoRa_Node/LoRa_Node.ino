/*******************************************************************************
 * LoRa Node: Arduino UNO R4 WiFi + Cytron LoRa RFM 915MHz shield
 *
 * Reads the MH-Sensor-Series light sensor (LDR) and sends it through
 * ChirpStack to the MQTT broker at lora.kmitl.ac.th.
 *
 * Uplink (fPort 1, every TX_INTERVAL seconds, 3 bytes):
 *   byte 0-1 : light_raw     (uint16, big endian, analogRead(A0) 0-1023)
 *   byte 2   : light_digital (digitalRead(D0) of MH-Sensor-Series, 0/1)
 *
 * Based on reference/lora-uno-r4/LoRa_OTAA.ino (MCCI LMIC, OTAA).
 * Keys live in secrets.h (copy secrets.example.h -> secrets.h).
 *******************************************************************************/

#include <lmic.h>
#include <hal/hal.h>
#include <SPI.h>
#include "secrets.h"

void os_getArtEui (u1_t* buf) { memcpy_P(buf, APPEUI, 8); }
void os_getDevEui (u1_t* buf) { memcpy_P(buf, DEVEUI, 8); }
void os_getDevKey (u1_t* buf) { memcpy_P(buf, APPKEY, 16); }

// MH-Sensor-Series light sensor (LDR) on the shield
const int LIGHT_ANALOG_PIN = A0;
const int LIGHT_DIGITAL_PIN = 0;

// Schedule TX every this many seconds (might become longer due to duty
// cycle limitations).
const unsigned TX_INTERVAL = 60;

// Pin mapping (Cytron LoRa RFM shield)
const lmic_pinmap lmic_pins = {
    .nss = 10,
    .rxtx = LMIC_UNUSED_PIN,
    .rst = 7,
    .dio = {2, 5, 6},
};

static uint8_t payload[3];
static osjob_t sendjob;

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
            // frameLen 16 = our 3-byte payload, ~12-15 = empty frame (MAC commands only)
            Serial.print(F("EV_TXSTART seqnoUp="));
            Serial.print(LMIC.seqnoUp);
            Serial.print(F(" frameLen="));
            Serial.println(LMIC.dataLen);
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

    Serial.print(F("light_raw="));
    Serial.print(lightRaw);
    Serial.print(F(" light_digital="));
    Serial.println(lightDigital);
    Serial.print(F("payload fPort=1 hex="));
    for (uint8_t i = 0; i < sizeof(payload); i++) {
        if (payload[i] < 0x10) Serial.print('0');
        Serial.print(payload[i], HEX);
        Serial.print(' ');
    }
    Serial.println();

    // Prepare upstream data transmission at the next possible time.
    LMIC_setTxData2(1, payload, sizeof(payload), 0);
    Serial.println(F("Packet queued"));
    // Next TX is scheduled after TX_COMPLETE event.
}

void setup() {
    Serial.begin(9600);
    Serial.println(F("Starting"));

    pinMode(LIGHT_DIGITAL_PIN, INPUT);

    // LMIC init
    os_init();
    // Reset the MAC state. Session and pending data transfers will be discarded.
    LMIC_reset();
    // UNO R4 clock is not as precise as LMIC expects: widen the RX windows
    // so the JoinAccept / downlinks are not missed.
    LMIC_setClockError(MAX_CLOCK_ERROR * 1 / 100);

    LMIC_setupChannel(
        0,
        924200000,
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
