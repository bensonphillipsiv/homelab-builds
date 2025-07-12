import the_block
import paho.mqtt.client as mqtt

def setupMQTT():
    client = connect("block/data")
    client.on_message = the_block.onMessage
    client.loop_forever()

    return client

def on_connect(client, userdata, flags, rc, properties=None):
    print("Connected with result code " + str(rc))

def connect(topic):
    client = mqtt.Client(protocol=mqtt.MQTTv5)
    client.on_connect = on_connect
    client.connect("192.168.1.111", 1883, 60)
    client.subscribe(topic, 0)

    return client
