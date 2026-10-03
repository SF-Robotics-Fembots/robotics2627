import queue
import threading

import pygame

import joyServer
import laserServer
import piServer


IP_SERVER = "192.168.1.67"


def main():
    pygame.init()
    stop_event = threading.Event()
    errors = queue.Queue()

    def run_server(name, target):
        try:
            target(IP_SERVER, stop_event)
            if not stop_event.is_set():
                errors.put((name, RuntimeError("server exited unexpectedly")))
                stop_event.set()
        except Exception as exc:
            errors.put((name, exc))
            stop_event.set()

    servers = [
        threading.Thread(
            target=run_server,
            args=("joystick", joyServer.main),
            name="joystick-server",
        ),
        threading.Thread(
            target=run_server,
            args=("direction", piServer.main),
            name="direction-server",
        ),
        threading.Thread(
            target=run_server,
            args=("laser", laserServer.main),
            name="laser-server",
        ),
    ]

    try:
        for server in servers:
            server.start()
        for server in servers:
            server.join()
    finally:
        pygame.quit()

    if not errors.empty():
        failures = []
        while not errors.empty():
            name, exc = errors.get()
            failures.append(f"{name}: {exc!r}")
        raise RuntimeError("Server worker failure(s): " + "; ".join(failures))


if __name__ == "__main__":
    main()
