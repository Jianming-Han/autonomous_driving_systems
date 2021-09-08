#!/usr/bin/env python

"""
These are the libraries you need to import in your project in order to
be able to communicate with the Gazebo simulator
"""

from bfmclib.gps_s import Gps
from bfmclib.bno055_s import BNO055
from bfmclib.camera_s import CameraHandler
from bfmclib.controller_p import Controller
from bfmclib.trafficlight_s import TLColor, TLLabel, TrafficLight

from bfmclib.pid import PID
from bfmclib.global_planning import planning

import rospy
import cv2
from time import sleep, time
import math
import _thread
from multiprocessing import Process, Queue, Pipe
import os

from process import lane_keeping_process, object_detection_process


dir_path = os.path.dirname(os.path.realpath(__file__))
graph_path = os.path.join(dir_path, 'bfmclib/fixed_track.graphml')


# This line should be the first line in your program
rospy.init_node('ma=in_node', anonymous=True)

# Initialize necessary objects
cam = CameraHandler()
print("Camera loaded")

car = Controller()
print("Controller loaded")

sem = TrafficLight()
print("Traffic lights listener")

gps = Gps()
print("Gps loaded")

bno = BNO055()
print("BNO055 loaded")

pla = planning(graph_path)
print ("global planning loaded")

pid = PID(0.5, 0, 0.3)
# pid3 = PID(0.04, 0, 0.01)
pid2 = PID(40, 0, 10)
print ("PID loaded")

print("Select \"Frame preview\" window and press Q to exit")

sleep(1)

# Generate target path
begin_node = "86"
finish_node = "99"
path = pla.plan(begin_node, finish_node)
begin_node = "100"
finish_node = "116"
path += pla.plan(begin_node, finish_node)
begin_node = "117"
finish_node = "300"
path += pla.plan(begin_node, finish_node)
begin_node = "301"
finish_node = "196"
path += pla.plan(begin_node, finish_node)
begin_node = "197"
finish_node = "85"
path += pla.plan(begin_node, finish_node)

# dalete nodes in roundabout (for now)
del(path[path.index('302')])
del(path[path.index('303')])
del(path[path.index('304')])
del(path[path.index('305')])
del(path[path.index('306')])

# delete nodes in intersection (for now)
for index, val in enumerate(path):
    if val in pla.get_middle_list():
        del(path[index])
print ('path by global planning: {}'.format(path))
    

# Initialize parameters
pos = {'x':None, 'y':None}
flag = 0

PrevPosi = {'x': None, 'y': None}	# The gps is not updating all the time, we have to check it.
PrevGpsPosi = {'timestamp': None, 'coor': None}
my_position = {'x': None, 'y': None}

PrevTime = 0.0
speed = 0.3
steering = 0

not_finished = False
direction = ''

err = 0
err2 = 0
lk_image = cam.getImage()
od_image = cam.getImage()

turnon_lk = True
turnon_od = True

achieve_goal = False

exception_nodes = ['295','296','302','303','304','305','306','265','266','95','96','97']
tl_nodes = [['86','77'],['69','110','2'],['98','99','100','4'],['33','113','6']]


# lane switch
def switch(way):
    if way == 'r':
        t1 = time()
        while time() - t1 < 1.7:
            r_ctr_val = max(10-err2*0.08, 3)
            r_speed = 0.3
            car.drive(r_speed, r_ctr_val)
        t1 = time()
        while time() - t1 < 0.6:
            l_ctr_val = 4
            l_speed = 0.3
            car.drive(l_speed, l_ctr_val)
    
    if way == 'l':
        t1 = time()
        while time() - t1 < 1.7:
            l_ctr_val = min(10-err2*0.08, -3)
            r_speed = 0.3
            car.drive(l_speed, l_ctr_val)
        t1 = time()
        while time() - t1 < 0.6:
            r_ctr_val = 4
            r_speed = 0.3
            car.drive(r_speed, r_ctr_val)     


# The function for turning at intersection
def turn():
    global flag
    global base
    global speed
    global steering
    global my_position
    global direction

    tmp = False
    cur_node = pla.locate(my_position)
    target_node = path[0]
    cur_x, cur_y = pla.get_node(cur_node)
    target_x, target_y = pla.get_node(target_node)

    if flag == 0:
        base = bno.getYaw()
        # check direction
        if math.pi/4 < bno.getYaw() < 3*math.pi/4:
            if target_x - cur_x < 0:
                direction = 'left'
            else:
                direction = 'right'

        if -math.pi/4 < bno.getYaw() < math.pi/4:
            if target_y - cur_y > 0:
                direction = 'left'
            else:
                direction = 'right'

        if -3*math.pi/4 < bno.getYaw() < -math.pi/4:
            if target_x - cur_x > 0:
                direction = 'left'
            else:
                direction = 'right'

        if 3*math.pi/4 < bno.getYaw() < math.pi or -math.pi < bno.getYaw() < -3*math.pi/4:
            if target_y - cur_y < 0:
                direction = 'left'
            else:
                direction = 'right'

        if math.pi/4 < bno.getYaw() < 3*math.pi/4 or -3*math.pi/4 < bno.getYaw() < -math.pi/4:
            err_x = target_y - my_position['y']      
            flag = 1
        else:
            err_x = target_x - my_position['x']
            flag = 2

    elif flag == 2:
        err_x = target_x - my_position['x']
    elif flag == 1:
        err_x = target_y - my_position['y']

    # speed = 0.3
    steering = 0

    if direction == 'right' and -0.5 < err_x < 0.5:
        tmp = True
    elif direction == 'left' and -0.3 < err_x < 0.3:
        tmp = True

    if tmp:
        if direction == 'right':
            target = base - math.pi/2   # turn left
        elif direction == 'left':
            target = base + math.pi/2   # turn right

        err_yaw = target - bno.getYaw()
    
        # speed = 0.3
        steering = -err_yaw*60 
    
        if -0.005 < err_yaw < 0.005:
            return False
        else:
            return True


# [1] Thread for lane keeping
def lk_data_thread(name):
    global err
    global err2
    global lk_image
    global sender

    while 1:
        img = cam.getImage()
        sender.send(img)
        err, err2, lk_image = receiver2.recv()


# [2] Thread for object detection
pedestrian = False
stop_sign = False
tl_signal = None
parking_sign = False
crosswalk_sign = False
priority_sign = False
roundabout_sign = False

sign_text = ''


def od_data_thread(name):
    global od_image
    global speed
    global pedestrian
    global stop_sign
    global tl_signal
    global parking_sign
    global lk_image
    global turnon_lk
    global crosswalk_sign
    global priority_sign
    global roundabout_sign

    while 1:
        if turnon_lk:
            sender3.send([lk_image, speed])
        else:
            sender3.send([cam.getImage(), speed])
        
        crosswalk_sign, pedestrian, priority_sign, roundabout_sign, \
        stop_sign, tl_signal, parking_sign, od_image = receiver4.recv()


cur_node = 0
gps_steering = 0
def localize_thread(name, sample_rate):
    # Localization
    global cur_node
    global my_position
    global achieve_goal

    while 1:
        PrevPosi['x'] = my_position['x']
        PrevPosi['y'] = my_position['y']
        gps_position = gps.getGpsData()

        if gps_position['coor']:
            if gps_position['coor'] != PrevGpsPosi['coor']: # When the gps data changes
                my_position['x'] = gps_position['coor'][0].real
                my_position['y'] = gps_position['coor'][0].imag
                PrevGpsPosi['coor'] = gps_position['coor']
            else:
                deltaX, deltaY = pla.localize_update(PrevTime, speed, bno.getYaw())
                my_position['x'] += deltaX
                my_position['y'] += deltaY
        PrevTime = rospy.get_time()	
        if pla.locate(my_position) not in pla.get_middle_list():
            cur_node = pla.locate(my_position)
        # print ('current node is ' + str(cur_node))

         # Update the path
        if path:
            if cur_node == path[0]:
                del(path[0])
        else:
            achieve_goal = True
        
        # refresh rate
        sleep((1/sample_rate))


# The function for going straight forward at intersection or crosswalk
gps_steering = 0
def gps_path_follow(name, sample_rate):
    global path
    global gps_steering
    while 1:
        if path and my_position['x']:
            tolerant = 0.2
            next_node = path[0]
            target_x, target_y = pla.get_node(next_node)

            cur_x = float(my_position['x'])
            cur_y = float(my_position['y'])
            gps_steering = 0
            if target_y - cur_y < tolerant:
                if -3*math.pi/4 < bno.getYaw() < -math.pi/4:
                    gps_steering = -bno.getYaw() - math.pi/2
                elif -math.pi/4 < bno.getYaw() < 3*math.pi/4:
                    gps_steering = math.atan2(target_y-cur_y, target_x-cur_x)
                else:
                    gps_steering = min(bno.getYaw()-math.pi, bno.getYaw()+math.pi)
            elif target_x - cur_x < tolerant:
                gps_steering = -math.atan2(target_x-cur_x, target_y-cur_y)
        
        sleep(1/sample_rate)


# Pipe, data exchange of main and sub processes
sender, receiver = Pipe()
sender2, receiver2 = Pipe()

lk_p = Process(target=lane_keeping_process, args=(sender2, receiver))

lk_p.start()

sender3, receiver3 = Pipe()
sender4, receiver4 = Pipe()

od_p = Process(target=object_detection_process, args=(sender4, receiver3))

od_p.start()

lock = _thread.allocate_lock() # thread lock, to keep thread safety, maybe useful later
_thread.start_new_thread(lk_data_thread, ('Thread-1',))
_thread.start_new_thread(od_data_thread, ('Thread-5',))
_thread.start_new_thread(localize_thread, ('Thread-3', 20))
_thread.start_new_thread(gps_path_follow, ('Thread-4', 5))      


# [0] Main thread
while 1:
    # print ('---------------------------------------------------')
    sign_text = ''
    speed = 0.3

    turnon_lk = True
    
    # steering
    if cur_node in pla.get_entry_list() or not_finished:
        turnon_lk = False # turn off lane keeping
        cur_x, cur_y = pla.get_node(cur_node)
        t_x, t_y = pla.get_node(path[0])

        if -0.2 < cur_x-t_x < 0.2 or -0.2 < cur_y-t_y < 0.2:
            steering = -pid2.get_steering(gps_steering)
            flag = 1
            not_finished = False
        else:
            not_finished = turn()
    else:
        flag = 0

    
    # speed impact on road bending degree
    ctr_val = pid.get_steering(err)
    
    # Lane keeping mode
    if flag == 0:
        if cur_node in exception_nodes:
            turnon_lk = False # turn off lane keeping
            # print(gps_steering)
            steering = -gps_steering*20
        else:
            steering = ctr_val
    
    
    # ####################################################
    # Reaction towards traffic signs
    # print('current speed: {}'.format(speed))
    image_copy = od_image

    # print(bno.getPitch())
    if bno.getPitch() < -0.146:
        sign_text = 'Ramp deteced! Uphilling!'
    if bno.getPitch() > 0.146:
        sign_text = 'Ramp deteced! Downhilling!'

    if stop_sign:
        speed = 0.0
        sign_text = 'Stop sign detected! Stop!'

    if tl_signal == 0:
        speed = 0.0
        sign_text = 'Red light! Stop!'
    if tl_signal == 1:
        speed = 0.0
        sign_text = 'Yellow light! Wait!'
    if tl_signal == 2:
        speed = 0.3
        sign_text = 'Green light! Go!'
    
    if priority_sign:
        sign_text = 'Priority sign detected! You can pass!'
    
    if roundabout_sign:
        sign_text = 'Roundabout sign detected!'
    
    if parking_sign:
        speed = 0.2
        sign_text = 'Parking sign detected! You can park!'
    
    if crosswalk_sign:
        speed = 0.2
        sign_text = 'Crosswalk sign detected! Slow down!'
    
    if pedestrian:
        speed = 0.0
        sign_text = 'Pedestrian detected! Stop!'
    
    if achieve_goal:
        sign_text = 'Target achieved! Engine stop!'
        speed = 0
        steering = 0
    
    car.drive(speed,steering)

    if sign_text:
        cv2.putText(image_copy,sign_text,(10,50),cv2.FONT_HERSHEY_SIMPLEX,1,(0,0,255),2,cv2.LINE_AA)
    cv2.imshow("Driver View", image_copy)
    key = cv2.waitKey(1)
    if key == ord('q'):
        cv2.destroyAllWindows()
        break
    elif key == ord('a'):
        switch('l')
    elif key == ord('d'):
        switch('r')

print("Car stopped. \n END")
lk_p.kill()
od_p.kill()
car.stop(0.0)
