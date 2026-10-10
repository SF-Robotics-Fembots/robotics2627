import importlib
import sys

# Define expected environment baselines
EXPECTED_PYTHON_MAJOR = 3
EXPECTED_PYTHON_MINOR = 14
EXPECTED_UBUNTU_VERSION = "26.04"

# Corrected Python module import namespaces
CRITICAL_LIBRARIES = [
    "board",  # Provided by Adafruit-Blinka
    "adafruit_servokit",  # Provided by adafruit-circuitpython-servokit
    "pygame",  # Provided by pygame-ce
    "hid",  # Provided by hid
    "serial",  # Provided by pyserial
    "RPi.GPIO",  # Provided by rpi-lgpio
]


def check_system():
  print("=== Environment Verification Tool ===")
  all_passed = True

  # 1. Check Ubuntu Version
  try:
    with open("/etc/os-release", "r") as f:
      os_info = f.read()
    if f'VERSION_ID="{EXPECTED_UBUNTU_VERSION}"' in os_info:
      print(f" [PASS] Ubuntu Version matches: {EXPECTED_UBUNTU_VERSION}")
    else:
      print(
          f" [WARN] Ubuntu version mismatch or non-Ubuntu OS detected. Expected"
          f" {EXPECTED_UBUNTU_VERSION}"
      )
  except FileNotFoundError:
    print(" [INFO] Not running on Linux/Ubuntu (OS-release file not found).")

  # 2. Check Python Version
  py_version = sys.version_info
  print(
      f" [INFO] Current Python Version: {py_version.major}.{py_version.minor}.{py_version.micro}"
  )
  if (
      py_version.major == EXPECTED_PYTHON_MAJOR
      and py_version.minor >= EXPECTED_PYTHON_MINOR
  ):
    print(" [PASS] Python version requirement met (3.14+).")
  else:
    print(
        " [FAIL] Python version does not match expected"
        f" {EXPECTED_PYTHON_MAJOR}.{EXPECTED_PYTHON_MINOR}+"
    )
    all_passed = False

  # 3. Check Required Libraries
  print("\n--- Verifying Installed Libraries ---")
  for lib in CRITICAL_LIBRARIES:
    try:
      mod = importlib.import_module(lib)
      version = getattr(mod, "__version__", "Version unknown")
      print(f" [PASS] '{lib}' is installed (v{version})")
    except ImportError:
      print(f" [FAIL] '{lib}' could NOT be imported!")
      all_passed = False

  print("\n=====================================")
  if all_passed:
    print("STATUS: All environment checks PASSED successfully! 🚀")
  else:
    print("STATUS: Some checks FAILED. Review warnings/errors above.")
    sys.exit(1)


if __name__ == "__main__":
  check_system()