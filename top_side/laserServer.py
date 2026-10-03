import json
import socket
import threading

from pynput.keyboard import Key, Listener


PORT = 3030


def main(ip_address, stop_event):
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    client_socket = None
    server_socket.settimeout(0.5)
    laser_enabled = False

    try:
        server_socket.bind((ip_address, PORT))
        server_socket.listen(1)
        print("Laser socket listening")

        while not stop_event.is_set():
            try:
                client_socket, client_address = server_socket.accept()
                break
            except socket.timeout:
                continue
        else:
            return

        def on_release(key):
            nonlocal laser_enabled
            if key == Key.f1:
                laser_enabled = not laser_enabled
                message = json.dumps({"lasers": int(laser_enabled)}).encode("utf-8")
                try:
                    client_socket.sendall(message)
                except OSError as exc:
                    print(f"Laser client disconnected: {exc}")
                    stop_event.set()
                    return False

        def on_press(key):
            if key == Key.esc:
                stop_event.set()
                return False

        with Listener(on_press=on_press, on_release=on_release) as listener:
            while not stop_event.wait(0.1):
                if not listener.is_alive():
                    break
            if listener.is_alive():
                listener.stop()
    finally:
        if client_socket is not None:
            client_socket.close()
        server_socket.close()


if __name__ == "__main__":
    import sys

    if len(sys.argv) != 2:
        print("Usage: python laserServer.py <ip_server>")
        raise SystemExit(1)
    main(sys.argv[1], threading.Event())
