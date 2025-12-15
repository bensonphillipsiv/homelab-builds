import calculate, mqtt5, homeassistant
import os, time, random
import json
from dotenv import load_dotenv
load_dotenv()

SHAKE_COUNT_MAX_N = 10
ROTATION_COUNT_MAX_N = 10
MIN_ROT_TIME_S = .5
ROT_COUNT_N = 5

POS_TIME_S = 0.25

class Block:
    def __init__(self):
        self.navi_json = json.loads(os.getenv("NAVI_JSON"))
        self.scene_json = json.loads(os.getenv("SCENE_JSON"))
        self.menu = "menu.main"
        self.position = 'z+'
        self.last_position = 'z+'
        self.rotation_count = 0
        self.shake_count = 0
        self.last_position_time = time.time()
        self.last_rotation_time = time.time()
        self.all_basic_services = self._getAllBasicServices()

    def _getAllBasicServices(self):
        services = []
        for pos, potential_service in self.navi_json['menu.main'].items():
            if potential_service.startswith('switch.') or potential_service.startswith('light.'):
                services.append(potential_service)
            elif potential_service.startswith('scene.'):
                for potential_service2 in self.scene_json.get(potential_service, []):
                    if potential_service2.startswith('switch.') or potential_service.startswith('light.'):
                        services.append(potential_service2)
        print("Discovered basic services:" + str(services))
        return services

    def onMessage(self, client, userdata, message):  
        mpu_data = json.loads(message.payload.decode("utf-8"))
        # print(mpu_data)

        if (position := calculate.position(mpu_data)) is not None:
            if self.positionIsTrigged(position):
                self.setPosition(position)

        if calculate.shaking(mpu_data):
            self.processShake(calculate.shaking(mpu_data))

        if (direction := calculate.rotation(self.position, mpu_data)) is not None:
            if self.rotationIsTriggered(direction):
                self.setRotation(direction)

    def setPosition(self, position):
        self.position = position
        self.last_position = position
        self.last_position_time = time.time()

        entry = self.getEntry(position)
        domain = self.getDomain(position)

        if len(entry.split('.')) == 3:
            print(f"Service selected: {entry}")
            homeassistant.callService(entry)
        elif domain == 'scene':
            print(f"Scene selected: {entry}")
            self.setScene(entry)
        elif domain == 'menu':
            print(f"Menu selected: {entry}")
            self.menu = entry

    def positionIsTrigged(self, position):
        if self.last_position == position and self.position != position:
            if time.time() - self.last_position_time > POS_TIME_S:
                return True
        else:
            self.last_position = position
            self.last_posistion_time = time.time()
        
        return False
    
    def rotationIsTriggered(self, direction):
        enough_time = time.time() - self.last_rotation_time > MIN_ROT_TIME_S
        
        if direction == 0 and self.rotation_count != 0 and enough_time:
           self.rotation_count = self.rotation_count + (-1 if self.rotation_count > 0 else 1)
        elif direction == 1:
            self.rotation_count = min(ROTATION_COUNT_MAX_N, self.rotation_count + 1)
        elif direction == -1:
            self.rotation_count = max(-ROTATION_COUNT_MAX_N, self.rotation_count - 1)

        crossed_limit = self.rotation_count * direction > ROT_COUNT_N
        if crossed_limit and enough_time:
            self.last_rotation_time = time.time()
            return True
            
        return False
    
    def setRotation(self, direction):
        print(f"Rotation detected: {direction} on {self.getEntry()}")
        if self.getDomain() == 'media_player':
            if direction == 1:
                homeassistant.callService(f"{self.getEntry()}.volume_up")
            else:
                homeassistant.callService(f"{self.getEntry()}.volume_down")
        elif self.getDomain() == 'bright':
            _, action = self.getEntry().split('.', 1)
            service = f"light.{action}"

            brightness = homeassistant.getEntityState(service).attributes.get("brightness") or 0
            pct_brightness = int(brightness * 100/255)

            if direction == 1:
                new_brightness = min(pct_brightness + 10, 100)
                homeassistant.callService(f"{service}.turn_on", brightness_pct=new_brightness)
            else:
                new_brightness = max(pct_brightness - 10, 0)
                homeassistant.callService(f"{service}.turn_on", brightness_pct=new_brightness)

    def processShake(self, shaking):
        if shaking:
            self.shake_count = min(SHAKE_COUNT_MAX_N, self.shake_count + 1)

            if self.shake_count >= SHAKE_COUNT_MAX_N:
                random_service = random.choice(self.all_basic_services)
                base, _ = random_service.rsplit('.', 1)
                toggle_service = f"{base}.toggle"

                print(f"Shaking - random service toggled: {random_service} - menu reset to main")
                self.menu = "menu.main"
                homeassistant.callService(toggle_service)
        else:
            self.shake_count = max(0, self.shake_count - 1)

    def getEntry(self, position=None):
        if position is None:
            position = self.position
        return self.navi_json.get(self.menu, {}).get(position)
    
    def getDomain(self, position=None):
        if position is None:
            position = self.position
        return self.navi_json.get(self.menu, {}).get(position).split('.')[0]
    
    def setScene(self, scene):
        scene_services = self.scene_json.get(scene)
        if scene_services:
            for service in scene_services:
                homeassistant.callService(service)
        else:
            print(f"No {scene} found for menu: {self.menu}")
    

def main() -> None:
    homeassistant.start()
    block = Block()
    client = mqtt5.setupMQTT()
    client.on_message = block.onMessage
    client.loop_forever()

if __name__ == "__main__":
    main()
