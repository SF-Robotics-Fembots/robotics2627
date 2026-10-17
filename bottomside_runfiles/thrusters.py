import json #decodes joystick messages
import math #has math functions so you can do more complex calculations
import socket #connects topside and bottomside/ client and server
import time #delays code for a certain amount of time

#for the gui so cynthia can get bottomside pwm values
TELEMETRY_PORT = 7071

#set_neutral overall sets every thruster channel to the same neutral PWM signal
def set_neutral(thruster_channels, neutral_pwm): # defines the function; thruster_channels is a collection of PWN channels
	neutral_duty = int(neutral_pwm / 10000 * 65536) # sets the PWM frequency to about 100 Hz, 
	#giving a 10000 microsecond period. so a neutral value of 1500 becomes a duty-cycle value of about 9830
	for channel in thruster_channels: #for loop that goes through each channel in the thruster_channels collection
		channel.duty_cycle = neutral_duty # sets the duty cycle for each thruster channel to the neutral value of 1500
		#this does not mean it cuts power because neutral might not be exactly 1500 on the actual thruster

# converts a pulse-width value into the PWM format expected by the hardware then applies to one channel
def set_throttle(channel, throttle_in, delay=0): #defines function; channel is a single PWM channel, throttle_in is the desired pulse width in microseconds, delay is optional - not used in the function
	throttle_pwm = int(throttle_in / 10000 * 65536) # converts the pulse width in microseconds to the PWM duty cycle format expected by the hardware. The formula scales the input value (throttle_in) from a range of 0-10000 microseconds to a range of 0-65536, which is the resolution of the PWM controller.
	channel.duty_cycle = throttle_pwm # applies duty cycle value to the specified channel, effectively setting the throttle for that thruster.
	time.sleep(0) #'delay' but not actually delaying anything since its 0 seconds; actually don't know why this is necessary

# ajusts the PWM value to account for startup compensation thresholds, ensuring that the thruster starts moving as expected. 
# It takes into account the neutral PWM value and applies the appropriate compensation based on whether the input PWM is above or below neutral.
def apply_startup_compensation(pwm, thresholds, neutral_pwm): # pwm - comamand to adjust, thresholds - dictionary with positive and negative compensation values, neutral_pwm - the neutral PWM value for the thruster
	if pwm == neutral_pwm:
		return neutral_pwm #if the command is exactly neutral, return the neutral value without any compensation
	if pwm > neutral_pwm: #if its above neutral, apply positive compensation
		return pwm + (thresholds["positive"] - neutral_pwm)
	return pwm - (neutral_pwm - thresholds["negative"]) #same thing for negative but in opposite direction

#keeps a PWM command within an optional range of limits. 
# If no limits are provided, the PWM command is returned unchanged. 
# This function ensures that the PWM value does not exceed specified minimum and maximum bounds, 
# which can be important for protecting hardware or ensuring safe operation.
def clamp_pwm(pwm, limits): #pwm - value to check, limits - either None or a tuple containing (min_pwm, max_pwm)
	if limits is None:
		return pwm #if no limits are provided, return the original PWM value
	min_pwm, max_pwm = limits #unpack the minimum and maximum PWM values from the limits tuple
	return max(min_pwm, min(max_pwm, pwm)) # ensures that the PWM value is not less than min_pwm and not greater than max_pwm.
	# bounds the commanded value; doesn't confirm the limoits are appropriate for the connected thruster of ESC

# converts one joystick input value into a PWM command for a horizontal thruster, taking into account a deadzone and the direction of the thruster.
def calcHorizontal(joyValue, thrusterNum, direction): #joyValue - joystick input, thrusterNum - selectts which thruster's direction value to use, direction - array of signs that determine whether this thruster's contribution is positive or negative
	if -5 <= joyValue <= 5: 
		return 0 # if the joystick input is within the deadzone (-5 to 5), return 0 to indicate no movement
	joyValue = joyValue - ((abs(joyValue) / joyValue) * 5) # adjusts the joystick value to account for the deadzone, effectively reducing the input range by 5 units in the direction of the input
	return joyValue * direction[thrusterNum] # multiplies the adjusted joystick value by the direction sign for the specified thruster, returning the final PWM command for that thruster based on the joystick input and its configured direction.

# converts one joystick input value into a PWM command for a vertical thruster, taking into account a deadzone and the direction of the thruster.
def calcVertical(joyValue, thrusterNum, direction): #joyValue - joystick input, thrusterNum - selects which thruster's direction value to use, direction - array of signs that determine whether this thruster's contribution is positive or negative
	if -15 <= joyValue <= 15:
		return 0 # if the joystick input is within the deadzone (-15 to 15), return 0 to indicate no movement
	joyValue = joyValue - ((abs(joyValue) / joyValue) * 10) # adjusts the joystick value to account for the deadzone, effectively reducing the input range by 10 units in the direction of the input
	return joyValue * direction[thrusterNum] # multiplies the adjusted joystick value by the direction sign for the specified thruster, returning the final PWM command for that thruster based on the joystick input and its configured direction.


def main(ip_server, shield):

	#setting up the median of the 'off' values for the thrusters
	horiz_off_value = 1500
	horiz_thrust_offset = 0
	vert_off_value = 1500
	vert_thrust_offset = 0
	neutral_pwm = 1500 #sets neutral to 1500
	max_horizontal_thrust = 50
	max_vertical_thrust = 50
	# This caps aggregate PWM distance from neutral, not measured electrical power.
	max_total_pwm_delta_us = 1200
	pitch_scale = 85
	roll_scale = 85
	# CHECK: Set these signs for the actual T5-T8 positions and push directions.
	vertical_mix = [
		(1, 1),    # T5: pitch sign, roll sign
		(1, -1),   # T6
		(-1, 1),   # T7
		(-1, -1),  # T8
	]

	#add this to control/config panel
	thruster_startup_pwm = [
		{"positive": 1510, "negative": 1460},  # T1
		{"positive": 1510, "negative": 1465},  # T2
		{"positive": 1555, "negative": 1445},  # T3
		{"positive": 1560, "negative": 1455},  # T4
		{"positive": 1560, "negative": 1445},  # T5
		{"positive": 1560, "negative": 1450},  # T6
		{"positive": 1500, "negative": 1500},  # T7: CHECK/calibrate startup compensation
		{"positive": 1500, "negative": 1500},  # T8: CHECK/calibrate startup compensation
	]

	#add this to control/config panel
	thruster_pwm_limits = [
		None,          # T1
		None,          # T2
		None,          # T3
		None,          # T4
		(1165, 1825),  # T5
		(1165, 1825),  # T6
		(1165, 1825),  # T7: CHECK allowed PWM range for this ESC/thruster
		(1165, 1825),  # T8: CHECK allowed PWM range for this ESC/thruster
	]
	dynamic_change = 999

	#MODE1_REG = 0x00

	#debug! make more laters
	debug_l2 = 0

	#add to config/control panel
	#rotation compensation
	rot_comp = 0#was -0.08
	slide_comp =0 #0.19

	# CHECK HARDWARE: Set the PCA9685 channel numbers actually wired to T7 and T8.
	# Keep unset rather than risking output to the wrong ESC channel.

	shield_channels = [8, 12, 13, 11, 9, 14, 1, 2]
	thruster_channels = []
	for shield_channel in shield_channels[:6]:
		thruster_channels.append(shield.channels[shield_channel])

	set_neutral(thruster_channels, neutral_pwm)
	print("about to connect")

	clientSocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
	
	clientSocket1 = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
	try:
		clientSocket.connect((ip_server, 9090))
		clientSocket1.connect((ip_server, 7070))
		clientSocket.settimeout(2.0)
		clientSocket1.settimeout(2.0)
	except OSError:
		clientSocket.close()
		clientSocket1.close()
		set_neutral(thruster_channels, neutral_pwm)
		raise

	joystick_stream = clientSocket.makefile("rb")
	direction_stream = clientSocket1.makefile("rb")
	telemetry_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
	telemetry_address = (ip_server, TELEMETRY_PORT)
	print("connected")
	prevX = 0
	prevY = 0
	prevV = 0
	prevR = 0
	#everytime data is sent, previous values are set to 0 (updates & loops values)

	directionRecieved = "a" #not in pilot inversion
	direction = 1

	# main loop
	while True:
		try:
			message = joystick_stream.readline()
			if not message:
				raise ConnectionError("Joystick client disconnected")
			dataFraud = message.decode("utf-8").strip()
			thrusterMovements = json.loads(dataFraud)
			if not isinstance(thrusterMovements, dict):
				raise ValueError("Joystick message must be a JSON object")

			speed_keys = (
				"x_speed",
				"y_speed",
				"r_speed",
				"v_speed",
				"pitch_speed",
				"roll_speed",
			)
			speeds = [thrusterMovements.get(key) for key in speed_keys]
			if any(
				isinstance(value, bool)
				or not isinstance(value, (int, float))
				or not math.isfinite(value)
				or not -1 <= value <= 1
				for value in speeds
			):
				raise ValueError("Joystick speeds must be finite numbers in [-1, 1]")

			thrusterMovements = dict(zip(speed_keys, map(float, speeds)))
			#print(thrusterMovements)
			#time.sleep(1)
			if debug_l2: print("datafraud: " + dataFraud)
			#data = (clientSocket.recv(1024)).decode()

			print(f"Loop Start -------------------------------------------------")


			
			#x_speed = x_speed[1:]
			#[1:]: used for inverse orders/directions
			x_speed = thrusterMovements['x_speed']
			x_speed = float(x_speed)
	
			#y_speed = data[data.find('y'):data.find('r')]
			#y_speed = y_speed[1:]
			y_speed = thrusterMovements['y_speed']
			y_speed = float(y_speed)
			
			#r_speed = data[data.find('r'):data.find('v')]
			#r_speed = r_speed[1:]
			r_speed = thrusterMovements['r_speed']
			r_speed = float(r_speed)
			
			#v_speed = data[data.find('v'):data.find('x')]
			#v_speed = v_speed[1:]
			v_speed = thrusterMovements['v_speed']
			v_speed = float(v_speed)
			pitch_speed = thrusterMovements["pitch_speed"]
			roll_speed = thrusterMovements["roll_speed"]
			

			#lines 157-190: translates first measured joystick values, which comes as a float, from top side
			#then, the float goes through a char*
			#the float is translated through the char* (via parsing) into another float that the top computer can understand&receive

			diffX = x_speed - prevX
			diffY = y_speed - prevY
			diffR = r_speed - prevR
			diffV = v_speed - prevV
			#finding difference of speeds to evaluate which ones need power limiting 
			#values used in next if statement
			print(f"Time:{time.time()} | from topside - x_speed: {x_speed} | prevX: {prevX} |  y_speed: {y_speed} | prevY: {prevY}")

#MOD: diffValue = value_speed - prevValue

		# 	if (abs(diffX) > dynamic_change):
		# 		x_speed = prevX + ((diffX/abs(diffX)) * dynamic_change)
		# 	if (abs(diffY) > dynamic_change):
		# 		y_speed = prevY + ((diffY/abs(diffY)) * dynamic_change)
		# 	if (abs(diffR) > dynamic_change):
		# 		r_speed = prevR + ((diffR/abs(diffR)) * dynamic_change)
		# 	if (abs(diffV) > dynamic_change):
		# 		v_speed = prevV + ((diffV/abs(diffV)) * dynamic_change)
		# #helps manage power
		#if diffvalue is greater than .05, then it will assign speed a lower values by multiplying diffValue by .1
			print(f"Time:{time.time()} | after-adjusment x_speed:{x_speed} | y_speed:{y_speed} | r_speed:{r_speed} | v_speed:{v_speed}")

			prevX = x_speed
			prevY = y_speed
			prevR = r_speed
			prevV = v_speed

#MOD: prevValue = value_speed

			# multiplies original values by 100 (necessary for calculations)
			x_speed = int((x_speed)*50)
			y_speed = int((y_speed)*50)
			r_speed = int((r_speed)*25)
			v_speed = int(v_speed * 85)
			pitch_speed = int(pitch_speed * pitch_scale)
			roll_speed = int(roll_speed * roll_scale)

			#print("R Speed: " + str(r_speed))
			#rotation compensation :(
			r_speed = int(r_speed + rot_comp * y_speed)
			r_speed = int(r_speed + slide_comp * x_speed)

			
			direction_message = direction_stream.readline()
			if not direction_message:
				raise ConnectionError("Direction client disconnected")
			directionRecieved = direction_message.decode("ascii").strip()
			if (directionRecieved == "a"):
				direction = 1
			elif (directionRecieved == "b"):
				direction = -1
			elif directionRecieved == "c":
				direction = direction
			else:
				raise ValueError(f"Invalid direction message: {directionRecieved!r}")
			if debug_l2: print(directionRecieved)
			if debug_l2: print(direction)


			#xDirArray = [-1*direction, 1*direction, -1*direction, 1*direction]
			#yDirArray = [1*direction, 1*direction, -1*direction, -1*direction]
			#rDirArray = [-1, 1, 1, -1]
			#third thruster is now cw so the signs got flipped


            #REMEMBER TO TEST THESE NOW
			# FWD/BACK is "Y", SIDE TO SIDE is "X"
			# this is thruster 1 (front right), 2 (back right), 3 (front left), 4 (back left)
			# THIS IS FOR THRUSTER MOUNTING- CW/CCW is below (clock_array)
			
			yDirArray = [1*direction, -1*direction, 1*direction, -1*direction]
			xDirArray = [-1*direction, -1*direction, 1*direction, 1*direction]
			rDirArray = [-1, 1, 1, -1]
			# CHECK HARDWARE: Verify each vertical ESC/motor direction.
			vDirArray = [1, 1, 1, 1]

			# array for each horizontal thruster value
			oldThrusterVals = [0, 0, 0, 0]
			# array for each vertical thruster value
			oldVertThrusterVals = [0, 0, 0, 0]

			# loop to collect value for each thruster using horizontal calculation function
			for tNum in range(0,4):
				#goes through code four times
				oldThrusterVals[tNum] = int((calcHorizontal(x_speed, tNum, xDirArray) + calcHorizontal(y_speed, tNum, yDirArray) + calcHorizontal(r_speed, tNum, rDirArray)))
			# loop to collect value for each thruster using vertical calculation function
			for vNum, (pitch_sign, roll_sign) in enumerate(vertical_mix):
				combined_vertical = (
					v_speed
					+ pitch_speed * pitch_sign
					+ roll_speed * roll_sign
				)
				oldVertThrusterVals[vNum] = int(
					calcVertical(combined_vertical, vNum, vDirArray)
				)

			clockArray = [1, -1, 1, 1]    #1 for CW, -1 for CCW
			# CHECK HARDWARE: Verify/reverse these signs after testing each vertical thruster.
			clockVertArray = [1, 1, 1, 1]

			thrusterVals = [0, 0, 0, 0]
			vertThrusterVals = [0, 0, 0, 0]

			for tNum in range(0, 4):
				thrusterVals[tNum] = int(oldThrusterVals[tNum] * clockArray[tNum])

			for vNum in range(0, 4):
				vertThrusterVals[vNum] = int(oldVertThrusterVals[vNum] * clockVertArray[vNum])

		# original print
			# adjusting range
			max_thruster = 0
			for thrusters in range(0,4):
				max_thruster = max(max_thruster, abs(thrusterVals[thrusters]))

			if (max_thruster != 0) and (max_thruster >= max_horizontal_thrust):
				for thrusters in range(0, 4):
					thrusterVals[thrusters] = int(thrusterVals[thrusters] * (max_horizontal_thrust / max_thruster))
					#lines 284-291: finds the maximum value of all throttle values, then limits them if needed

			max_vert_thruster = 0
			for vertThrusters in range(0, 4):
				max_vert_thruster = max(max_vert_thruster, abs(vertThrusterVals[vertThrusters]))

			if (max_vert_thruster != 0) and (max_vert_thruster >= max_vertical_thrust):
				for vertThrusters in range(0, 4):
					vertThrusterVals[vertThrusters] = int(vertThrusterVals[vertThrusters] * (max_vertical_thrust / max_vert_thruster))


			# new lists for the adjusted values for our power functions
			powerThrusterVals = [0, 0, 0, 0]
			powerVertThrusterVals = [0, 0, 0, 0]

			# both for loops adjust the range of the thrusters to 1000-2000
			for thrusters in range(0, 4):
				if (thrusterVals[thrusters] == 0):
					powerThrusterVals[thrusters] = horiz_off_value
				else:
					#powerThrusterVals[thrusters] = 1489 + (((abs(thrusterVals[thrusters]))/thrusterVals[thrusters]) * (25 + (thrusterVals[thrusters] * 4.64)))
					powerThrusterVals[thrusters] = horiz_off_value + ((abs(thrusterVals[thrusters])/thrusterVals[thrusters]) * horiz_thrust_offset) + (thrusterVals[thrusters] * 7.0)
			#was 25 and 4.64
			#using 1489 because 1489 = median of thruster calibration (all thrusters stop at 1489)
			for vertThrusters in range(0, 4):
				if debug_l2: print(vertThrusterVals[vertThrusters])
				if (vertThrusterVals[vertThrusters] == 0):
					powerVertThrusterVals[vertThrusters] = vert_off_value
				else:
					#powerVertThrusterVals[vertThrusters] = 1489 + (((abs(vertThrusterVals[vertThrusters]))/vertThrusterVals[vertThrusters]) * (25 + (vertThrusterVals[vertThrusters] * 4.64)))
					powerVertThrusterVals[vertThrusters] = vert_off_value + ((abs(vertThrusterVals[vertThrusters])/vertThrusterVals[vertThrusters]) * vert_thrust_offset) + (vertThrusterVals[vertThrusters] * 7.0)
					#changed from *25 to *50 because verts on this year's robot have a 50 uS deadzone & horizontals only have 25 uS deadzone on each side of center
					#abs(vertThrusterVals[vertThrusters]) just tells direction



			#print("third print")
			#debug_l2 = 1
			
			#made changes starting here for duty cycle
			if debug_l2: print(powerThrusterVals)

			#Combine horizontal and vertical thruster values
			allPowerVals = powerThrusterVals + powerVertThrusterVals
			compensatedPowerVals = [
				apply_startup_compensation(
					val, thruster_startup_pwm[index], neutral_pwm
				)
				for index, val in enumerate(allPowerVals)
			]
			compensatedPowerVals = [
				clamp_pwm(val, thruster_pwm_limits[index])
				for index, val in enumerate(compensatedPowerVals)
			]
			neutralValues = (
				[horiz_off_value] * len(powerThrusterVals)
				+ [vert_off_value] * len(powerVertThrusterVals)
			)
			total_pwm_delta_us = sum(
				abs(value - neutral)
				for value, neutral in zip(compensatedPowerVals, neutralValues)
			)
			print(f"Aggregate PWM delta: {total_pwm_delta_us:.1f} us")
			if total_pwm_delta_us > max_total_pwm_delta_us:
				scale = max_total_pwm_delta_us / total_pwm_delta_us
				print(f"Aggregate PWM scale: {scale:.3f}")
				compensatedPowerVals = [
					neutral + (value - neutral) * scale
					for value, neutral in zip(compensatedPowerVals, neutralValues)
				]
				compensatedPowerVals = [
					clamp_pwm(val, thruster_pwm_limits[index])
					for index, val in enumerate(compensatedPowerVals)
				]

			# Combine corresponding thruster objects
			# Apply compensated PWM to each thruster and print values in a single row
			for thruster, val in zip(thruster_channels, compensatedPowerVals):
				thruster.duty_cycle = int(val / 10000 * 65536)

			# Send the commanded PWM pulse widths to the topside GUI. Keep this
			# list-based format so adding thrusters only requires extending labels
			# and values in this controller.
			labels = [f"T{i + 1}" for i in range(len(compensatedPowerVals))]
			telemetry = {
				"thrusters": [
					{"label": label, "pwm": int(round(val))}
					for label, val in zip(labels, compensatedPowerVals)
				]
			}
			try:
				telemetry_socket.sendto(json.dumps(telemetry).encode("utf-8"), telemetry_address)
			except OSError:
				# Telemetry is for display only; a network issue must not stop control.
				pass

			#print(*allPowerVals)

			# Print PWM values in a single row with labels
			labels = ["T1", "T2", "T3", "T4", "T5", "T6", "T7", "T8"]
			print(f"Time:{time.time()} | " + " | ".join(f"{label}:{val}" for label, val in zip(labels, compensatedPowerVals)))
			
			# Print actual ESC values (duty cycle)
			esc_vals = [int(val / 10000 * 65536) for val in compensatedPowerVals]
			print(f"ESC Values: " + " | ".join(f"{label}:{val}" for label, val in zip(labels, esc_vals)))


		except Exception as exc:
			set_neutral(thruster_channels, neutral_pwm)
			print(f"Thruster input/connection error: {exc}")
			joystick_stream.close()
			direction_stream.close()
			clientSocket.close()
			clientSocket1.close()
			telemetry_socket.close()
			if isinstance(exc, ConnectionError):
				break
			raise
