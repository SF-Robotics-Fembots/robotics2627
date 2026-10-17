import socket
import sys
import time

import pygame


def main(ip_server, stop_event):
    server_socket = None
    client_socket = None

    try:
        try:
            server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            server_socket.settimeout(0.5)
            server_socket.bind((ip_server, 7070))
            server_socket.listen(1)
        except OSError as exc:
            raise OSError(
                f"Could not set up direction socket on {ip_server}:7070: {exc}"
            ) from exc

        pygame.joystick.init()
        if pygame.joystick.get_count() == 0:
            raise RuntimeError("No joystick detected")

        joystick = pygame.joystick.Joystick(0)
        joystick.init()

        print("Direction socket listening")

        while not stop_event.is_set():
            try:
                client_socket, client_address = server_socket.accept()
                break
            except socket.timeout:
                continue
        else:
            return

        while not stop_event.is_set():
            if joystick.get_button(3):
                direction = "a"
                print("normal mode")
            elif joystick.get_button(5):
                direction = "b"
                print("inverse mode")
            else:
                direction = "c"

            client_socket.sendall(direction.encode("ascii") + b"\n")
            time.sleep(0.01)
    finally:
        if client_socket is not None:
            client_socket.close()
        if server_socket is not None:
            server_socket.close()


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python piServer.py <ip_server>")
        raise SystemExit(1)
    import threading

    pygame.init()
    main(sys.argv[1], threading.Event())
    pygame.quit()
