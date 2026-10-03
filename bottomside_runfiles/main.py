import queue
import threading
import time

import adafruit_pca9685
import board
import busio
import pygame

import thrusters


IP_SERVER = "192.168.1.67"


def main():
    pygame.init()
    i2c = busio.I2C(board.SCL, board.SDA, frequency=50000)
    shield = adafruit_pca9685.PCA9685(i2c)

    # Configure the PCA9685 external clock at approximately 100 Hz.
    shield.mode1_reg = 0x10
    shield.mode1_reg = 0x10 | 0x40
    shield.prescale_reg = 60
    shield.mode1_reg = 0x40 | 0x20
    time.sleep(0.005)

    errors = queue.Queue()

    def run_thrusters():
        try:
            thrusters.main(IP_SERVER, shield)
        except Exception as exc:
            errors.put(exc)

    thruster_thread = threading.Thread(target=run_thrusters, name="thrusters")
    thruster_thread.start()
    thruster_thread.join()

    pygame.quit()
    if not errors.empty():
        raise RuntimeError("Thruster controller failed") from errors.get()


if __name__ == "__main__":
    main()
