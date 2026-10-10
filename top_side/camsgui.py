#i changed camera switching for screenshot
import cv2
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QLabel,
    QGridLayout, QScrollArea, QSizePolicy,
    QPushButton, QHBoxLayout
)
from PyQt5.QtGui import QPixmap, QImage, QFont, QPalette
from PyQt5.QtCore import QThread, pyqtSignal, Qt, QTimer
import sys, time, os, json, datetime, queue
import numpy as np

# Target display rate per camera. We always read frames to stay at the live
# edge, but only process/emit this often so the Qt queue can't back up.
DISPLAY_FPS = 20

# Base folders for screenshots (D: preferred, home folder as fallback). Each run
# gets its own dated subfolder under one of these.
PREFERRED_SHOT_DIR = r"D:\camsgui_screenshots"
FALLBACK_SHOT_DIR = os.path.join(os.path.expanduser("~"), "camsgui_screenshots")

# Persisted settings, saved next to this script.
ROTATION_CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "camera_rotations.json")
SCREENSHOT_CAMERA_CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "screenshot_default_camera.json")

#need to change this to the correct timezone for seattle, washington 
def _newfoundland_is_dst(utc_dt):
    # Newfoundland DST: 2nd Sunday of March 02:00 local -> 1st Sunday of Nov 02:00 local.
    year = utc_dt.year

    def nth_sunday(month, n):
        first = datetime.date(year, month, 1)
        first_sunday = 1 + (6 - first.weekday()) % 7   # weekday(): Mon=0..Sun=6
        return first_sunday + (n - 1) * 7

    start_local = datetime.datetime(year, 3, nth_sunday(3, 2), 2, 0)    # clocks on NST (UTC-3:30)
    end_local   = datetime.datetime(year, 11, nth_sunday(11, 1), 2, 0)  # clocks on NDT (UTC-2:30)
    start_utc = start_local + datetime.timedelta(hours=3, minutes=30)
    end_utc   = end_local + datetime.timedelta(hours=2, minutes=30)
    naive_utc = utc_dt.replace(tzinfo=None)
    return start_utc <= naive_utc < end_utc


def stjohns_now():
    # Current time in St. John's, Newfoundland. Uses the tz database if present
    # (e.g. `pip install tzdata`), otherwise computes the NL offset directly.
    utc_now = datetime.datetime.now(datetime.timezone.utc)
    try:
        from zoneinfo import ZoneInfo
        return utc_now.astimezone(ZoneInfo("America/St_Johns"))
    except Exception:
        offset = datetime.timedelta(hours=-2, minutes=-30) if _newfoundland_is_dst(utc_now) \
            else datetime.timedelta(hours=-3, minutes=-30)
        return (utc_now + offset).replace(tzinfo=None)


def create_session_dir():
    # Make a dated subfolder for this run; returns (path, used_fallback).
    session_name = stjohns_now().strftime("%Y-%m-%d_%H-%M-%S")
    for base in (PREFERRED_SHOT_DIR, FALLBACK_SHOT_DIR):
        try:
            session_dir = os.path.join(base, session_name)
            os.makedirs(session_dir, exist_ok=True)
            return session_dir, (base != PREFERRED_SHOT_DIR)
        except OSError as e:
            print(f"Could not use {base}: {e}")
    return None, False


# --- Camera capture thread ---
class CaptureCam(QThread):
    ImageUpdate = pyqtSignal(QImage)
    RawFrameUpdate = pyqtSignal(object)

    def __init__(self, url, high_res=False, rotation=0):
        super().__init__()
        self.url = url
        self.high_res = high_res
        self.threadActive = True
        self.last_qt_image = None
        self.rotation = rotation

    ROTATION_MAP = {
        90: cv2.ROTATE_90_CLOCKWISE,
        180: cv2.ROTATE_180,
        270: cv2.ROTATE_90_COUNTERCLOCKWISE,
    }

    def open_capture(self):
        capture = cv2.VideoCapture(self.url)
        capture.set(cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, 10000)
        capture.set(cv2.CAP_PROP_READ_TIMEOUT_MSEC, 10000)
        # keep the internal buffer tiny so latency can't accumulate over time
        try:
            capture.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        except Exception:
            pass
        return capture

    def run(self):
        capture = self.open_capture()

        min_period = 1.0 / DISPLAY_FPS
        last_process = 0.0
        consecutive_failures = 0

        while self.threadActive:
            ret, frame = capture.read() if capture is not None else (False, None)

            if not ret:
                consecutive_failures += 1
                # a stream that has gone bad over time: drop it and reconnect fresh
                if consecutive_failures >= 20:
                    if capture is not None:
                        capture.release()
                    capture = self.open_capture()
                    consecutive_failures = 0
                placeholder = self.create_placeholder()
                self.ImageUpdate.emit(self.cv_to_qt(placeholder))
                time.sleep(0.5)
                continue

            consecutive_failures = 0

            # We just consumed a frame (draining any backlog so we stay live).
            # Only do the heavy convert/emit at the target rate so the GUI's
            # cross-thread queue can't grow without bound.
            now = time.monotonic()
            if now - last_process < min_period:
                continue
            last_process = now

            if self.rotation in self.ROTATION_MAP:
                frame = cv2.rotate(frame, self.ROTATION_MAP[self.rotation])

            cv_rgb_image = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            height, width, channels = cv_rgb_image.shape
            bytes_per_line = width * channels

            if self.high_res:
                self.RawFrameUpdate.emit(cv_rgb_image)

            qt_rgb_image = QImage(cv_rgb_image.data, width, height, bytes_per_line, QImage.Format_RGB888)
            qt_rgb_image_scaled = qt_rgb_image.scaled(520, 480, Qt.KeepAspectRatio)
            self.ImageUpdate.emit(qt_rgb_image_scaled)

        if capture is not None:
            capture.release()
        self.quit()

    def cv_to_qt(self, frame):
        h, w, c = frame.shape
        bytes_per_line = c * w
        qt_img = QImage(frame.data, w, h, bytes_per_line, QImage.Format_RGB888)
        return qt_img.scaled(520, 480, Qt.KeepAspectRatio)

    def create_placeholder(self):
        img = np.ones((480, 640, 3), dtype=np.uint8) * 255
        img[:] = [255, 232, 240]

        offline_text = "CAMERA OFFLINE (*_*)"
        text_scale = 2
        text_thickness = 4
        text_size = cv2.getTextSize(offline_text, cv2.FONT_HERSHEY_SIMPLEX, text_scale, text_thickness)[0]
        text_x = (img.shape[1] - text_size[0]) // 2
        text_y = (img.shape[0] + text_size[1]) // 2

        cv2.putText(img, offline_text, (text_x, text_y),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    text_scale, (255, 0, 128),
                    text_thickness, cv2.LINE_AA)

        return img

    def stop(self):
        self.threadActive = False


# --- Background screenshot writer ---
class ScreenshotWriter(QThread):
    # success, filename, used_fallback_folder  (emitted per completed write)
    finished_signal = pyqtSignal(bool, str, bool)

    def __init__(self):
        super().__init__()
        # Writes are serialized through this queue. USB flash drives are very
        # slow under concurrent writes, so we save one image at a time.
        self.queue = queue.Queue()

    def submit(self, frame_rgb, filename, used_fallback):
        self.queue.put((frame_rgb, filename, used_fallback))

    def run(self):
        while True:
            item = self.queue.get()   # blocks until a job (or the stop sentinel)
            if item is None:
                break
            frame_rgb, filename, used_fallback = item
            try:
                frame = frame_rgb
                h, w, _ = frame.shape
                if w < 3840 or h < 2160:
                    frame = cv2.resize(frame, (3840, 2160), interpolation=cv2.INTER_CUBIC)
                ok = cv2.imwrite(filename, cv2.cvtColor(frame, cv2.COLOR_RGB2BGR))
            except cv2.error as e:
                print(f"cv2.imwrite error: {e}")
                ok = False
            if ok:
                print(f"Saved screenshot to {filename}")
            self.finished_signal.emit(ok, filename, used_fallback)

    def stop(self):
        # queued writes still ahead of the sentinel finish first
        self.queue.put(None)


# --- Screenshot window ---
class ScreenshotWindow(QMainWindow):
    def __init__(self, camera_threads, start_index=1, on_camera_change=None,
                 session_dir=None, used_fallback=False):
        super().__init__()

        self.camera_threads = camera_threads
        # start on the last-used camera (clamped to a valid index)
        self.current_index = start_index if 0 <= start_index < len(camera_threads) else 0
        self.on_camera_change = on_camera_change
        self.session_dir = session_dir          # dated subfolder for this run
        self.session_used_fallback = used_fallback
        self.current_frame_cv = None
        self.last_qt_image = None

        self.setWindowTitle("← → to switch cameras | P to screenshot")
        self.showMaximized()

        self.label = QLabel()
        self.label.setAlignment(Qt.AlignCenter)
        self.setCentralWidget(self.label)

        # Screenshots are deferred to the next freshly delivered frame so a
        # rapid press never grabs a half-decoded (partially black) frame.
        self.pending_screenshots = 0
        self.screenshot_wait = 0       # frames waited for the current request

        # Single writer thread serializes disk writes (fast on USB keys).
        self.writer = ScreenshotWriter()
        self.writer.finished_signal.connect(self.on_screenshot_saved)
        self.writer.start()

        self.toast = QLabel("", self)
        self.toast.setAlignment(Qt.AlignCenter)
        self.toast.hide()
        self.toast_timer = QTimer(self)
        self.toast_timer.setSingleShot(True)
        self.toast_timer.timeout.connect(self.toast.hide)

        self.connect_camera(self.current_index)

    def show_toast(self, text, color="#2e7d32", duration_ms=2000):
        self.toast.setText(text)
        self.toast.setStyleSheet(
            f"background: {color}; color: white; padding: 12px 20px;"
            "border-radius: 8px; font-weight: bold; font-size: 16px;"
        )
        self.toast.adjustSize()
        self.toast.move(
            (self.width() - self.toast.width()) // 2,
            self.height() - self.toast.height() - 50,
        )
        self.toast.show()
        self.toast.raise_()
        self.toast_timer.start(duration_ms)

    def on_screenshot_saved(self, ok, filename, used_fallback):
        if not ok:
            self.show_toast("Screenshot failed to save", "#c62828")
        elif used_fallback:
            self.show_toast(f"Saved locally (D: unavailable): {os.path.basename(filename)}", "#ef6c00", 3500)
        else:
            self.show_toast(f"Saved {os.path.basename(filename)}", "#2e7d32")

    def connect_camera(self, index):
        for cam in self.camera_threads:
            try:
                cam.ImageUpdate.disconnect(self.update_image)
                cam.RawFrameUpdate.disconnect(self.store_raw_frame)
            except:
                pass

        cam = self.camera_threads[index]
        cam.ImageUpdate.connect(self.update_image)
        cam.RawFrameUpdate.connect(self.store_raw_frame)

        # cancel any queued screenshot so it can't save from the new camera
        self.pending_screenshots = 0
        self.screenshot_wait = 0

        # remember this as the new default for next time
        if self.on_camera_change is not None:
            self.on_camera_change(index)

    def store_raw_frame(self, frame):
        self.current_frame_cv = frame

        # Service a queued screenshot using this fresh, complete frame. Skip a
        # frame that looks truncated, but give up waiting after a few tries so a
        # request is never silently dropped.
        if self.pending_screenshots > 0:
            self.screenshot_wait += 1
            if (not self.is_truncated_frame(frame)) or self.screenshot_wait >= 5:
                self.pending_screenshots -= 1
                self.screenshot_wait = 0
                self.save_frame(frame.copy())

    @staticmethod
    def is_truncated_frame(frame):
        # A dropped/partial MJPEG frame ends in a block of identical (usually
        # black) rows. Flag it if the whole bottom 10% is one flat color.
        h = frame.shape[0]
        band = max(1, h // 10)
        return bool(np.all(frame[h - band:] == frame[-1, -1]))

    def save_frame(self, frame):
        save_path = self.session_dir
        used_fallback = self.session_used_fallback

        # session dir is created at startup; recreate defensively in case it was
        # removed, or fall back if it was never available
        if not save_path:
            save_path, used_fallback = create_session_dir()
            self.session_dir, self.session_used_fallback = save_path, used_fallback
        if save_path is None:
            self.show_toast("Screenshot failed: no writable folder", "#c62828", 3500)
            return
        try:
            os.makedirs(save_path, exist_ok=True)
        except OSError as e:
            self.show_toast("Screenshot failed: folder error", "#c62828", 3500)
            print(f"Could not create {save_path}: {e}")
            return

        # millisecond-resolution stamp so rapid shots never collide / overwrite
        timestamp = time.strftime("%Y%m%d_%H%M%S") + f"_{int((time.time() % 1) * 1000):03d}"
        filename = os.path.join(save_path, f"cam_{self.current_index+1}_{timestamp}.png")

        # queue the resize + write; the writer thread saves them one at a time
        self.writer.submit(frame, filename, used_fallback)

    def update_image(self, qt_image):
        self.last_qt_image = qt_image

        pixmap = QPixmap.fromImage(qt_image)
        self.label.setPixmap(
            pixmap.scaled(
                self.label.size(),
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation
            )
        )

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Left:
            self.current_index = (self.current_index - 1) % len(self.camera_threads)
            self.connect_camera(self.current_index)

        elif event.key() == Qt.Key_Right:
            self.current_index = (self.current_index + 1) % len(self.camera_threads)
            self.connect_camera(self.current_index)

        elif event.key() == Qt.Key_P:
            if self.current_frame_cv is None:
                self.show_toast("No frame yet", "#c62828", 1500)
                return

            # queue the request; it's saved from the next fresh, complete frame
            self.pending_screenshots += 1
            self.show_toast("Saving screenshot…", "#1565c0", 1500)

    def resizeEvent(self, event):
        if self.last_qt_image is not None:
            self.update_image(self.last_qt_image)
        super().resizeEvent(event)

    def closeEvent(self, event):
        # let queued screenshots finish writing, then stop the writer thread
        self.writer.stop()
        self.writer.wait(5000)
        super().closeEvent(event)


# --- Main GUI ---
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self.urls = [
            'http://192.168.1.68:8080/stream',
            'http://192.168.1.68:8082/stream',
            'http://192.168.1.68:8084/stream',
            'http://192.168.1.68:8086/stream',
            'http://192.168.1.68:8088/stream',
            'http://192.168.1.68:8090/stream'
        ]

        self.cameras = {}
        self.scroll_areas = {}

        for i in range(6):
            cam_label = QLabel()
            cam_label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Ignored)
            cam_label.setScaledContents(True)

            scroll_area = QScrollArea()
            scroll_area.setBackgroundRole(QPalette.Dark)
            scroll_area.setWidgetResizable(True)
            scroll_area.setWidget(cam_label)

            self.cameras[f"Camera_{i+1}"] = cam_label
            self.scroll_areas[f"Camera_{i+1}"] = scroll_area

        labels = [
            "back photosphere ♡",
            "back gripper ୨ৎ",
            "top photosphere ♡",
            "nav cam ❀",
            "front gripper ୨ৎ",
            "tools cam ❀"
        ]

        # Per-camera rotation, loaded from disk (falls back to defaults below)
        self.rotation_states = self.load_rotation_states()

        # Default camera for the screenshot window, remembered across sessions
        self.screenshot_default_index = self.load_screenshot_default_index()

        # One dated subfolder for this whole run (St. John's, NL time)
        self.session_dir, self.session_used_fallback = create_session_dir()
        if self.session_dir:
            print(f"Screenshots this session: {self.session_dir}")
        else:
            print("WARNING: could not create a screenshot folder for this session")

        rotate_btn_style = """
            QPushButton {
                border-radius: 8px;
                padding: 4px 10px;
                font-weight: bold;
                background: qlineargradient(
                    x1:0, y1:0, x2:0, y2:1,
                    stop:0 #ffc0cb, stop:1 #ffffff
                );
            }
            QPushButton:hover {
                background: qlineargradient(
                    x1:0, y1:0, x2:0, y2:1,
                    stop:0 #ff69b4, stop:1 #ffb6c1
                );
            }
        """

        self.camera_label_widgets = []
        self.rotate_buttons = []
        for i, text in enumerate(labels):
            label = QLabel(text)
            label.setStyleSheet("color: black")
            label.setAlignment(Qt.AlignCenter)

            rotate_btn = QPushButton(f"⟳ {self.rotation_states[i]}°")
            rotate_btn.setStyleSheet(rotate_btn_style)
            rotate_btn.clicked.connect(lambda _, n=i: self.rotate_camera(n))

            container = QWidget()
            row = QHBoxLayout(container)
            row.setContentsMargins(0, 0, 0, 0)
            row.addStretch()
            row.addWidget(label)
            row.addWidget(rotate_btn)
            row.addStretch()

            self.camera_label_widgets.append(container)
            self.rotate_buttons.append(rotate_btn)

        self.__SetupStopwatch()

        self.screenshot_btn = QPushButton("Screenshot!")
        self.screenshot_btn.clicked.connect(self.open_screenshot_window)
        self.screenshot_btn.setStyleSheet("""
            QPushButton {
                border-radius: 10px;
                padding: 10px;
                font-weight: bold;
                background: qlineargradient(
                    x1:0, y1:0, x2:0, y2:1,
                    stop:0 #ffc0cb, stop:1 #ffffff
                );
            }
            QPushButton:hover {
                background: qlineargradient(
                    x1:0, y1:0, x2:0, y2:1,
                    stop:0 #ff69b4, stop:1 #ffb6c1
                );
            }
        """)

        self.__SetupUI()

        self.cam_threads = []
        for i, url in enumerate(self.urls):
            high_res = True
            cam_thread = CaptureCam(url, high_res=high_res, rotation=self.rotation_states[i])
            cam_thread.ImageUpdate.connect(lambda img, n=i+1: self.ShowCamera(n, img))
            cam_thread.start()
            self.cam_threads.append(cam_thread)

    def __SetupStopwatch(self):
        self.stopwatch_elapsed_ms = 0
        self.stopwatch_running = False
        self.stopwatch_start_t = None  # time.monotonic() seconds at last Start

        self.stopwatch_display = QLabel("00:00.0")
        self.stopwatch_display.setAlignment(Qt.AlignCenter)
        self.stopwatch_display.setStyleSheet("""
            color: black;
            font-size: 24px;
            font-weight: bold;
            padding: 4px 14px;
            border-radius: 8px;
            background: white;
        """)

        sw_btn_style = """
            QPushButton {
                border-radius: 8px;
                padding: 6px 14px;
                font-weight: bold;
                background: qlineargradient(
                    x1:0, y1:0, x2:0, y2:1,
                    stop:0 #ffc0cb, stop:1 #ffffff
                );
            }
            QPushButton:hover {
                background: qlineargradient(
                    x1:0, y1:0, x2:0, y2:1,
                    stop:0 #ff69b4, stop:1 #ffb6c1
                );
            }
        """

        self.sw_start_btn = QPushButton("Start")
        self.sw_stop_btn = QPushButton("Stop")
        self.sw_reset_btn = QPushButton("Reset")
        for b in (self.sw_start_btn, self.sw_stop_btn, self.sw_reset_btn):
            b.setStyleSheet(sw_btn_style)

        self.sw_start_btn.clicked.connect(self.stopwatch_start)
        self.sw_stop_btn.clicked.connect(self.stopwatch_stop)
        self.sw_reset_btn.clicked.connect(self.stopwatch_reset)

        self.stopwatch_widget = QWidget()
        sw_layout = QHBoxLayout(self.stopwatch_widget)
        sw_layout.setContentsMargins(0, 0, 0, 0)
        sw_layout.addStretch()
        sw_layout.addWidget(self.stopwatch_display)
        sw_layout.addWidget(self.sw_start_btn)
        sw_layout.addWidget(self.sw_stop_btn)
        sw_layout.addWidget(self.sw_reset_btn)
        sw_layout.addStretch()

        self.stopwatch_timer = QTimer(self)
        self.stopwatch_timer.setInterval(50)
        self.stopwatch_timer.timeout.connect(self._refresh_stopwatch_display)

    def stopwatch_start(self):
        if not self.stopwatch_running:
            self.stopwatch_start_t = time.monotonic()
            self.stopwatch_running = True
            self.stopwatch_timer.start()

    def stopwatch_pause(self):
        if self.stopwatch_running:
            self.stopwatch_elapsed_ms += int((time.monotonic() - self.stopwatch_start_t) * 1000)
            self.stopwatch_start_t = None
            self.stopwatch_running = False
            self.stopwatch_timer.stop()
            self._refresh_stopwatch_display()

    def stopwatch_stop(self):
        self.stopwatch_pause()

    def stopwatch_reset(self):
        self.stopwatch_running = False
        self.stopwatch_start_t = None
        self.stopwatch_elapsed_ms = 0
        self.stopwatch_timer.stop()
        self._refresh_stopwatch_display()

    def _refresh_stopwatch_display(self):
        total_ms = self.stopwatch_elapsed_ms
        if self.stopwatch_running and self.stopwatch_start_t is not None:
            total_ms += int((time.monotonic() - self.stopwatch_start_t) * 1000)
        total_secs = total_ms // 1000
        h = total_secs // 3600
        m = (total_secs % 3600) // 60
        s = total_secs % 60
        tenths = (total_ms % 1000) // 100
        if h > 0:
            text = f"{h:02d}:{m:02d}:{s:02d}.{tenths}"
        else:
            text = f"{m:02d}:{s:02d}.{tenths}"
        self.stopwatch_display.setText(text)

    def load_rotation_states(self):
        # Default rotations (matches previous hardcoded behavior for 8080 and 8084)
        defaults = [180, 0, 180, 0, 0, 0]
        try:
            with open(ROTATION_CONFIG_PATH, "r") as f:
                saved = json.load(f)
            # only accept a list of 6 valid rotations; otherwise fall back
            if isinstance(saved, list) and len(saved) == 6:
                return [r if r in (0, 90, 180, 270) else defaults[i]
                        for i, r in enumerate(saved)]
        except (FileNotFoundError, json.JSONDecodeError, ValueError):
            pass
        return defaults

    def save_rotation_states(self):
        try:
            with open(ROTATION_CONFIG_PATH, "w") as f:
                json.dump(self.rotation_states, f)
        except OSError as e:
            print(f"Could not save camera rotations: {e}")

    def rotate_camera(self, index):
        new_rotation = (self.rotation_states[index] + 90) % 360
        self.rotation_states[index] = new_rotation
        self.cam_threads[index].rotation = new_rotation
        self.rotate_buttons[index].setText(f"⟳ {new_rotation}°")
        self.save_rotation_states()

    def open_screenshot_window(self):
        self.screenshot_window = ScreenshotWindow(
            self.cam_threads,
            start_index=self.screenshot_default_index,
            on_camera_change=self.set_screenshot_default_index,
            session_dir=self.session_dir,
            used_fallback=self.session_used_fallback,
        )
        self.screenshot_window.show()

    def load_screenshot_default_index(self):
        try:
            with open(SCREENSHOT_CAMERA_CONFIG_PATH, "r") as f:
                index = json.load(f)
            if isinstance(index, int) and 0 <= index < 6:
                return index
        except (FileNotFoundError, json.JSONDecodeError, ValueError):
            pass
        return 1   # previous hardcoded default

    def set_screenshot_default_index(self, index):
        self.screenshot_default_index = index
        try:
            with open(SCREENSHOT_CAMERA_CONFIG_PATH, "w") as f:
                json.dump(index, f)
        except OSError as e:
            print(f"Could not save screenshot default camera: {e}")

    def __SetupUI(self):
        grid_layout = QGridLayout()

        positions = [(0,0),(0,1),(0,2),(2,0),(2,1),(2,2)]
        label_positions = [(1,0),(1,1),(1,2),(3,0),(3,1),(3,2)]

        for i in range(6):
            grid_layout.addWidget(self.scroll_areas[f"Camera_{i+1}"], *positions[i])
            grid_layout.addWidget(self.camera_label_widgets[i], *label_positions[i])

        grid_layout.addWidget(self.screenshot_btn, 4, 0)
        grid_layout.addWidget(self.stopwatch_widget, 4, 1, 1, 2)

        self.widget = QWidget()
        self.widget.setLayout(grid_layout)
        self.setCentralWidget(self.widget)

        self.widget.setStyleSheet("""
            background: qlineargradient(
                x1:0, y1:0, x2:0, y2:1,
                stop:0 #add8e6, stop:1 #ffffff
            );
        """)

        self.setMinimumSize(1570, 1440)
        self.setWindowTitle("CAMERA GUI")

    def ShowCamera(self, cam_number, frame):
        self.cameras[f"Camera_{cam_number}"].setPixmap(QPixmap.fromImage(frame))


# --- Run ---
def main():
    app = QApplication(sys.argv)
    app.setFont(QFont("Helvetica", 14, QFont.Bold))
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())


if __name__ == '__main__':
    main()