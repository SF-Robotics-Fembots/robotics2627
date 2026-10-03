import json
import socket
import sys
import time

import pygame


def main(ip_server):
    serverSocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    serverSocket.settimeout(10.0)
    print(ip_server)

    pygame.init()
    pygame.joystick.init()

    if pygame.joystick.get_count() == 0:
        print("No joystick detected")
        serverSocket.close()
        return

    joystick = pygame.joystick.Joystick(0)
    joystick.init()

    try:
        serverSocket.bind((ip_server, 9090))
        serverSocket.listen(1)
        print("socket listening joystick")
        clientConnected, clientAddress = serverSocket.accept()
    except OSError as exc:
        print(f"Failed to bind/listen for joystick server: {exc}")
        serverSocket.close()
        return

    mode = 0
    prev_mode = mode
    ratio = 0.6

    try:
        while True:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    print("Joystick server shutting down")
                    return

            if joystick.get_button(1):
                mode = 0
            elif joystick.get_button(4):
                mode = 1
            elif joystick.get_button(2):
                mode = 0.5

            x_speed = joystick.get_axis(0)
            y_speed = joystick.get_axis(1)
            r_speed = joystick.get_axis(2)
            v_speed = joystick.get_axis(3)

            if mode == 0:
                x_speed = y_speed = r_speed = v_speed = 0
            else:
                x_speed *= mode
                y_speed *= mode
                r_speed *= mode
                v_speed *= mode

                if mode == 0.5:
                    x_speed *= ratio
                    y_speed *= ratio
                    r_speed *= ratio
                    v_speed *= ratio

            if mode != prev_mode:
                if mode == 1:
                    print("FAST MODE")
                elif mode == 0.5:
                    print("SLOW MODE")
                elif mode == 0:
                    print("STOP MODE")
            prev_mode = mode

            thrusterMovements = {
                'x_speed': x_speed,
                'y_speed': y_speed,
                'r_speed': r_speed,
                'v_speed': v_speed,
            }

            message = json.dumps(thrusterMovements).encode()
            try:
                clientConnected.send(message)
            except (BrokenPipeError, OSError):
                print("Client disconnected")
                return

            print(f"Time:{time.time()} | x_speed:{x_speed} | y_speed:{y_speed} | r_speed:{r_speed} | v_speed:{v_speed}")
            time.sleep(0.01)
    finally:
        try:
            clientConnected.close()
        except Exception:
            pass
        serverSocket.close()
        pygame.quit()


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python joyServer.py <ip_server>")
        raise SystemExit(1)
    main(sys.argv[1])