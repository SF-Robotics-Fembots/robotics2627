#!/bin/bash

rmmod uvcvideo
modprobe uvcvideo quirks=0x80
nice -n -19 bash /home/geneseas/robotics2627/camera_bottomside/startupcams.sh & python3 main.py 2> err.log && fg