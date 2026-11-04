"""MCP server tools for the AI chat box (Claude Desktop / Claude Code)."""
from mcp.server.mcpserver import MCPServer

from . import config
from .mqtt_bridge import topic
from .service import IoTService


def create_mcp(service: IoTService) -> MCPServer:
    mcp = MCPServer(
        "raspberry-pi-iot",
        instructions="Read and control IoT devices: Raspberry Pi sensors/LED, a LoRa light sensor node, and MQTT topics.",
    )

    @mcp.tool()
    def read_pi_sensors() -> dict:
        """Read the Raspberry Pi sensors right now: temperature (°C) and humidity (%RH)
        from the SHT3x, and distance (cm) from the HC-SR04 ultrasonic sensor.
        Also returns the current LED state. A null value means the sensor read failed."""
        values = service.read_pi_sensors()
        return {**values, "led": service.devices.led}

    @mcp.tool()
    def control_pi_led(on: bool) -> dict:
        """Turn the LED on the Raspberry Pi (GPIO 23) on or off."""
        return {"led": service.set_pi_led(on)}

    @mcp.tool()
    def read_lora_node() -> dict:
        """Read the latest uplink from the LoRa node (Arduino UNO R4 + light sensor).
        light_raw is the raw analogRead (0-1023) of the MH light sensor, light_digital is its
        threshold output (0/1), received_at is a unix timestamp, rssi/snr are the radio signal.
        The node only sends every ~60 s, so this is the last received value, not a live read."""
        return service.status()["lora"]

    @mcp.tool()
    def list_mqtt_topics() -> dict:
        """List MQTT topics (under the project prefix) that have received a message."""
        return {"prefix": config.TOPIC_PREFIX, "topics": service.mqtt.topics()}

    @mcp.tool()
    def read_mqtt(topic_name: str) -> dict:
        """Read the latest message on an MQTT topic. topic_name is relative to the project
        prefix, e.g. 'pi/sensor/temperature', 'pi/device/led' or 'lora/node1/data'."""
        full = topic(topic_name.strip("/"))
        msg = service.mqtt.get(full)
        if msg is None:
            return {"topic": full, "error": "no message received on this topic yet"}
        return {"topic": full, **msg}

    @mcp.tool()
    def publish_mqtt(topic_name: str, payload: str, retain: bool = False) -> dict:
        """Publish a message to the MQTT broker. topic_name is relative to the project prefix.
        Publishing 'on'/'off' to 'pi/device/led/set' controls the Pi LED."""
        full = topic(topic_name.strip("/"))
        return {"topic": full, "published": service.mqtt.publish(full, payload, retain=retain)}

    return mcp
