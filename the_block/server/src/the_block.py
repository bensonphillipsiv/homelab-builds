import calculate, mqtt5, homeassistant
import os, time, random
import json
from dotenv import load_dotenv
load_dotenv()

SHAKE_COUNT_MAX_N = 10
ROTATION_COUNT_MAX_N = 10

class Block:
    def __init__(self):
        self.navi_json = json.loads(os.getenv("NAVI_JSON"))
        self.menu = "menu.main"
        self.position = 'z+'
        self.last_position = 'z+'
        self.rotation_count = 0
        self.shake_count = 0
        self.position_last_time = time.time()
        self.rotation_last_time = time.time()

    def time(self, type):
        if type == 'position':
            self.position_last_time = time.time()
        elif type == 'rotation':
            self.rotation_last_time = time.time()
    
    def getService(self, position=None):
        if position is None:
            position = self.position
        return self.navi_json.get(self.menu, {}).get(position)
    
    def getDomain(self, position=None):
        if position is None:
            position = self.position
        return self.navi_json.get(self.menu, {}).get(position).split('.')[0]
    
    def setRotationCount(self, val):
        if val == 0 and self.rotation_count != 0:
           self.rotation_count = self.rotation_count + (-1 if self.rotation_count > 0 else 1)
        elif val > 0 and self.rotation_count < ROTATION_COUNT_MAX_N:
            self.rotation_count += 1
        elif val < 0 and self.rotation_count > -ROTATION_COUNT_MAX_N:
            self.rotation_count -= 1

    def setShakeCount(self, val):
        self.shake_count += val
        self.shake_count = min(max(self.shake_count, 0), SHAKE_COUNT_MAX_N)

    def setPosition(self, position):
        if self.getDomain(position) == 'menu':
            self.menu = self.getService(position)
        self.position = position

    def setLastPosition(self, last_position):
        self.last_position = last_position
        self.position_last_time = time.time()

    def randomService(self):
        options = [
            pos for pos, service in self.navi_json[self.menu].items() 
            if len(service.split('.')) == 3
        ]
        if options:
            random_service = random.choice(options)
            return random_service

block = Block()


def determinePosition(position):
    service = block.getService(position)
    domain = block.getDomain(position)
    if len(service.split('.')) == 3:
        homeassistant.callService(service)
    elif domain == 'scene':
        print(f"Scene selected: {service}")
    block.setPosition(position)

def determineRotation(value):
    if block.getDomain() == 'media_player':
        if value > 1:
            homeassistant.callService(f"{block.getService()}.volume_up")
        else:
            homeassistant.callService(f"{block.getService()}.volume_down")
    elif block.getDomain() == 'bright':
        _, action = block.getService().split('.', 1)
        service = f"light.{action}"

        brightness = homeassistant.getEntityState(service).attributes.get("brightness") or 0
        pct_brightness = int(brightness * 100/255)

        if value > 1:
            new_brightness = min(pct_brightness + 10, 100)
            homeassistant.callService(f"{service}.turn_on", brightness_pct=new_brightness)
        else:
            new_brightness = max(pct_brightness - 10, 0)
            homeassistant.callService(f"{service}.turn_on", brightness_pct=new_brightness)

def determineShake():
    random_service = block.randomService()
    if random_service:
        print("made it")
        homeassistant.callService(block.getService(random_service))
    else:
        print("No valid service found for random selection.")

def onMessage(client, userdata, message):  
    mpu_data = json.loads(message.payload.decode("utf-8"))
    print(mpu_data)

    if calculate.shake(block, mpu_data) is not None:
        print("made it 1")
        determineShake()
    if (position := calculate.position(block, mpu_data)) is not None:
        determinePosition(position)
    if block.getDomain() == 'media_player' or block.getDomain() == 'bright':
        if (rotation := calculate.rotation(block, mpu_data)) is not None:
            determineRotation(rotation)

def main() -> None:
    client = mqtt5.setupMQTT()
    client.on_message = onMessage

if __name__ == "__main__":
    main()