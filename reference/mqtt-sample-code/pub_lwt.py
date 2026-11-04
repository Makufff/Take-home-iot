import  paho.mqtt.client as mqtt
import  time
mqttc = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)

mqttc.will_set(
    "test/status",
    payload="offline111",
    qos=1,
    retain=True
)

mqttc.connect("mqtt-dashboard.com", 1883)

index = 1
while True: 
    mqttc.publish("test/pub", "Hello "+ str(index) ,qos=1)
    time.sleep(2)
    index = index+1