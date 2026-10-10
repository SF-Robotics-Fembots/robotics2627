import json
import socket
import sys
import time

import pygame


def main(ip_server, stop_event):
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    client_socket = None
    server_socket.settimeout(0.5)

    try:
        pygame.joystick.init()
        if pygame.joystick.get_count() == 0:
            raise RuntimeError("No joystick detected")

        joystick = pygame.joystick.Joystick(0)
        joystick.init()
        if joystick.get_numaxes() < 4:
            raise RuntimeError("Joystick must provide at least four axes")
        if joystick.get_numhats() < 1:
            raise RuntimeError("Joystick must provide a hat for pitch and roll")

        server_socket.bind((ip_server, 9090))
        server_socket.listen(1)
        print("Joystick socket listening")

        while not stop_event.is_set():
            try:
                client_socket, client_address = server_socket.accept()
                break
            except socket.timeout:
                continue
        else:
            return

        client_socket.settimeout(1.0)
        mode = 0
        previous_mode = mode
        ratio = 0.6

        while not stop_event.is_set():
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    stop_event.set()
                    return
                if event.type == pygame.JOYDEVICEREMOVED:
                    raise RuntimeError("Joystick disconnected")

            if joystick.get_button(1):
                mode = 0
            elif joystick.get_button(4):
                mode = 1
            elif joystick.get_button(2):
                mode = 0.5

            # CHECK: Confirm these axis indexes and signs on this joystick.
            # The Extreme 3D Pro's throttle may not center at zero.
            hat_x, hat_y = joystick.get_hat(0)
            speeds = {
                "x_speed": joystick.get_axis(0) * mode,
                "y_speed": joystick.get_axis(1) * mode,
                "r_speed": joystick.get_axis(2) * mode,
                "v_speed": joystick.get_axis(3) * mode,
                # CHECK: The hat is digital; verify pitch/roll signs match the vehicle.
                "pitch_speed": hat_y * mode,
                "roll_speed": hat_x * mode,
            }

            if mode == 0.5:
                speeds = {key: value * ratio for key, value in speeds.items()}

            if mode != previous_mode:
                mode_name = {0: "STOP", 0.5: "SLOW", 1: "FAST"}[mode]
                print(f"{mode_name} MODE")
                previous_mode = mode

            message = json.dumps(speeds).encode("utf-8") + b"\n"
            client_socket.sendall(message)

            print(
                f"Time:{time.time()} | "
                + " | ".join(f"{key}:{value}" for key, value in speeds.items())
            )
            time.sleep(0.01)
    finally:
        if client_socket is not None:
            client_socket.close()
        server_socket.close()


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python joyServer.py <ip_server>")
        raise SystemExit(1)
    import threading

    pygame.init()
    main(sys.argv[1], threading.Event())
    pygame.quit()
