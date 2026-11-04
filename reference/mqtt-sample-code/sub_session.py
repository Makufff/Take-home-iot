import paho.mqtt.client as mqtt

def on_message(client, userdata, msg):
    print("client =", client)
    print("userdata =", userdata)
    print("topic =", msg.topic)
    print("payload =", msg.payload.decode())
    print("QoS     :", msg.qos)
    print("Retain  :", msg.retain)
    print("MID     :", msg.mid)

mqttc = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, 
    client_id="panwit-sub" , 
    protocol=mqtt.MQTTv5)

mqttc.on_message = on_message


properties = mqtt.Properties(mqtt.PacketTypes.CONNECT)
properties.SessionExpiryInterval = 3600


mqttc.connect("mqtt-dashboard.com", 1883 ,clean_start=False ,properties=properties)


mqttc.subscribe("test/pub", qos=2)

mqttc.loop_forever()