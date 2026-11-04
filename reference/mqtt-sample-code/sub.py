import paho.mqtt.client as mqtt

def on_message(client, userdata, msg):
    print("client =", client)
    print("userdata =", userdata)
    print("topic =", msg.topic)
    print("payload =", msg.payload.decode())
    print("QoS     :", msg.qos)
    print("Retain  :", msg.retain)
    print("MID     :", msg.mid)

mqttc = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)

mqttc.on_message = on_message

mqttc.connect("mqtt-dashboard.com", 1883)

mqttc.subscribe("test/pub", qos=2)

mqttc.loop_forever()