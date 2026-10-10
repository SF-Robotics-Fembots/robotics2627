#!/bin/bash

bash cameraon.sh	

#ok lets see if this fixes the error!
# Kill any processes using cameras
sudo fuser -k /dev/video0
sudo fuser -k /dev/video2
sudo fuser -k /dev/video4
sudo fuser -k /dev/video6
sudo fuser -k /dev/video8
sudo fuser -k /dev/video10
#sudo fuser -k /dev/video12
#sudo fuser -k /dev/video14

#camera on by default  2/28 i added sudo
sudo rmmod uvcvideo
sudo modprobe uvcvideo nodrop=1 timeout=5000 quirks=0x80
bash /home/geneseas/robotics2627/camera_bottomside/focusscript.sh
bash /home/geneseas/robotics2627/camera_bottomside/camerarun.sh 0 & sleep 3
bash /home/geneseas/robotics2627/camera_bottomside/camerarun.sh 2 & sleep 3
bash /home/geneseas/robotics2627/camera_bottomside/camerarun.sh 4 & sleep 3
bash /home/geneseas/robotics2627/camera_bottomside/camerarun.sh 6 & sleep 3
bash /home/geneseas/robotics2627/camera_bottomside/camerarun.sh 8 & sleep 3
bash /home/geneseas/robotics2627/camera_bottomside/camerarun.sh 10 & sleep 3
#bash /home/geneseas/robotics2627/camera_bottomside/camerarun.sh 12 & sleep 3
#bash /home/geneseas/robotics2627/camera_bottomside/camerarun.sh 14 & sleep 3


