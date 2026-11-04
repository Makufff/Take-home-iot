import  paho.mqtt.client as mqtt
import  time
mqttc = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, protocol=mqtt.MQTTv5)

mqttc.connect("mqtt-dashboard.com", 1883)


index = 1
while True: 
    mqttc.publish("test/pub", "Hello "+ str(index) ,qos=1)
    time.sleep(2)
    index = index+1
