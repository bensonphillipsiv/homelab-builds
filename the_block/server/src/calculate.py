import time
import math

GRAVITY_G = 1
POS_TOLERANCE_G = 0.05
POS_TIME_S = 0.25

ROT_THRESHOLD_D = 1

SHAKE_THRESHOLD_G = 1.5
SHAKE_TIME_S = 0.25
SHAKE_THRESHOLD_N = 3

def position(mpu_data):
    if abs(abs(mpu_data['accx']) - GRAVITY_G) < POS_TOLERANCE_G:
        position = "x+" if mpu_data['accx'] > 0 else 'x-'
    elif abs(abs(mpu_data['accy']) - GRAVITY_G) < POS_TOLERANCE_G:
        position = 'y+' if mpu_data['accy'] > 0 else 'y-'
    elif abs(abs(mpu_data['accz']) - GRAVITY_G) < POS_TOLERANCE_G:
        position = 'z+' if mpu_data['accz'] > 0 else 'z-'
    else:
        position = None
    
    return position

def rotation(position, mpu_data):
    if position[0] == 'x':
        data = mpu_data['gyrx']
    elif position[0] == 'y':
        data = mpu_data['gyry']
    elif position[0] == 'z':
        data = mpu_data['gyrz']
    
    if position[1] == '+':
        data = -data

    if abs(data) > ROT_THRESHOLD_D:
        direction = 1 if data > 0 else -1
        return direction

    return 0

def shaking(mpu_data):
    acc_mag = math.sqrt(mpu_data['accx']**2 + mpu_data['accy']**2 + mpu_data['accz']**2)
    if acc_mag > SHAKE_THRESHOLD_G:
        return True
    else:
        return False
