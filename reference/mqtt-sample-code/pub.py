import  paho.mqtt.client as mqtt
import  time
mqttc = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)

mqttc.connect("mqtt-dashboard.com", 1883)
while True: 
	mqttc.publish("test/pub", "Hello World",qos=1)
	time.sleep(2)
