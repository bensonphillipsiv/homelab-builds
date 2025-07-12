import time
import math

GRAVITY_G = 1
POS_TOLERANCE_G = 0.05
POS_TIME_S = 0.25

ROT_TIME_S = .25
ROT_THRESHOLD_D = 1
ROT_COUNT_N = 5

SHAKE_THRESHOLD_G = 1.5
SHAKE_TIME_S = 0.25
SHAKE_THRESHOLD_N = 3

def position(block, mpu_data):
    if abs(abs(mpu_data['accx']) - GRAVITY_G) < POS_TOLERANCE_G:
        position = "x+" if mpu_data['accx'] > 0 else 'x-'
    elif abs(abs(mpu_data['accy']) - GRAVITY_G) < POS_TOLERANCE_G:
        position = 'y+' if mpu_data['accy'] > 0 else 'y-'
    elif abs(abs(mpu_data['accz']) - GRAVITY_G) < POS_TOLERANCE_G:
        position = 'z+' if mpu_data['accz'] > 0 else 'z-'
    else:
        position = None
    
    if position is not None:
        if block.last_position == position and block.position != position:
            if time.time() - block.position_last_time > POS_TIME_S:
                return position
        else:
            block.setLastPosition(position)
    return None

def rotation(block, mpu_data):
    if block.position[0] == 'x':
        data = mpu_data['gyrx']
    elif block.position[0] == 'y':
        data = mpu_data['gyry']
    elif block.position[0] == 'z':
        data = mpu_data['gyrz']
    
    if block.position[1] == '+':
        data = -data

    enough_time = time.time() - block.rotation_last_time > ROT_TIME_S
    if abs(data) > ROT_THRESHOLD_D:
        direction = 1 if data > 0 else -1
        block.setRotationCount(direction)

        crossed_limit = block.rotation_count * direction > ROT_COUNT_N
        if crossed_limit and enough_time:
            block.time("rotation")
            return data
    elif enough_time and block.rotation_count != 0:
        block.setRotationCount(0)
        block.time('rotation')
    return None

def shake(block, mpu_data):
    acc_mag = math.sqrt(mpu_data['accx']**2 + mpu_data['accy']**2 + mpu_data['accz']**2)
    # print(acc_mag)
    if acc_mag > SHAKE_THRESHOLD_G:
        block.setShakeCount(1)
    else:
        block.setShakeCount(-1)

    if block.shake_count > SHAKE_THRESHOLD_N:
        if time.time() - block.position_last_time > SHAKE_TIME_S:
            block.time('position')
            return True
    return None