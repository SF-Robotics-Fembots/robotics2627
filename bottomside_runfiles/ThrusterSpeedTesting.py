import pygame   #pip install pygame
import board	#pip install board
import busio	#pip install adafruit-blinka
import adafruit_pca9685 #pip install adafruit-circuitpython-pca9685
import time

def main():
	# library setup
	pygame.init()

	wait_time = 0.3
	go_fwd = 1700
	go_bak = 1300

	i2c = busio.I2C(board.SCL, board.SDA)
	shield = adafruit_pca9685.PCA9685(i2c)
	shield.external_clock = True #enable 25MHz external crystal
	shield.frequency = 96

	thrusterChannels = [
		shield.channels[8],  # Thruster 1
		shield.channels[12], # Thruster 2
		shield.channels[13], # Thruster 3
		shield.channels[11], # Thruster 4
		shield.channels[9],  # Thruster 5
		shield.channels[14], # Thruster 6
	]
	thrusterChannels[0].duty_cycle = 0x2666

	for channel in thrusterChannels:
		throttlePW = int(2200/10000*65536)
		channel.duty_cycle = throttlePW
		time.sleep(0)
		throttlePW = int(1500/10000*65536)
		channel.duty_cycle = throttlePW
		time.sleep(0)
	
	while True:
		# Get thruster number from user
		thruster_num = input("Enter thruster number (1-6) or 'q' to quit: ").strip()
		
		if thruster_num.lower() == 'q':
			print("Exiting...")
			break
		
		try:
			thruster_num = int(thruster_num)
			if thruster_num < 1 or thruster_num > len(thrusterChannels):
				print(f"Invalid thruster number. Please enter 1-{len(thrusterChannels)}.")
				continue
		except ValueError:
			print(f"Invalid input. Please enter a number 1-{len(thrusterChannels)} or 'q' to quit.")
			continue
		
		# Test the selected thruster
		channel = thrusterChannels[thruster_num - 1]
		print(f"\nTesting Thruster {thruster_num}")
		input("Press Enter to start thruster...")
		
		throttlePW = int(go_fwd/10000*65536)
		channel.duty_cycle = throttlePW
		print(f"Thruster {thruster_num} running forward")
		time.sleep(wait_time)
		
		throttlePW = int(1500/10000*65536)
		channel.duty_cycle = throttlePW
		print(f"Thruster {thruster_num} stopped")
		time.sleep(wait_time)
		
		throttlePW = int(go_bak/10000*65536)
		channel.duty_cycle = throttlePW
		print(f"Thruster {thruster_num} running backward")
		time.sleep(wait_time)
		
		throttlePW = int(1500/10000*65536)
		channel.duty_cycle = throttlePW
		print(f"Thruster {thruster_num} stopped")
		time.sleep(wait_time)

if __name__ == "__main__":
	main()
