import argparse
import ctypes
import logging
import sys
import time
from datetime import datetime

import psutil

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def setup_argparse():
    """
    Sets up the argument parser for the command-line interface.
    Returns:
        argparse.ArgumentParser: The argument parser object.
    """
    parser = argparse.ArgumentParser(description="Monitor active window titles and processes.")
    parser.add_argument("-i", "--interval", type=int, default=5,
                        help="Interval (in seconds) between checks. Default: 5")
    parser.add_argument("-o", "--output", type=str, default="window_activity.log",
                        help="Output log file. Default: window_activity.log")
    parser.add_argument("-v", "--verbose", action="store_true",
                        help="Enable verbose logging (debug level).")
    return parser

def windows_provider():
    """Foreground window lookup on Windows, through ctypes and psutil."""
    user32 = ctypes.windll.user32
    hwnd = user32.GetForegroundWindow()
    if not hwnd:
        return None, None
    length = user32.GetWindowTextLengthW(hwnd)
    buffer = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd, buffer, length + 1)
    window_title = buffer.value
    pid = ctypes.c_ulong(0)
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    process_name = None
    if pid.value:
        try:
            process_name = psutil.Process(pid.value).name()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            process_name = None
    return window_title, process_name

def macos_provider():
    """Foreground window lookup on macOS, through Quartz."""
    import Quartz
    windows = Quartz.CGWindowListCopyWindowInfo(
        Quartz.kCGWindowListOptionOnScreenOnly | Quartz.kCGWindowListExcludeDesktopElements,
        Quartz.kCGNullWindowID)
    for window in windows:
        if window.get("kCGWindowLayer", 0) != 0:
            continue
        window_title = window.get("kCGWindowName") or ""
        process_name = window.get("kCGWindowOwnerName")
        pid = window.get("kCGWindowOwnerPID")
        if pid and not process_name:
            try:
                process_name = psutil.Process(pid).name()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                process_name = None
        return window_title, process_name
    return None, None

def linux_provider():
    """Foreground window lookup on Linux (X11), through Xlib."""
    from Xlib import display
    disp = display.Display()
    focus = disp.get_input_focus().focus
    if focus is None:
        return None, None
    window_title = focus.get_wm_name()
    process_name = None
    pid_property = focus.get_full_property(disp.intern_atom('_NET_WM_PID'), 0)
    if pid_property and pid_property.value:
        try:
            process_name = psutil.Process(int(pid_property.value[0])).name()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            process_name = None
    return window_title, process_name

def get_provider():
    """
    Returns the foreground window provider for this platform, or None
    when no provider is available on this machine. Each platform
    dispatches to its own provider module: ctypes on Windows, Quartz
    on macOS, and Xlib on Linux.
    """
    if sys.platform.startswith("win"):
        try:
            ctypes.windll.user32  # noqa: B018
            return windows_provider
        except Exception:
            return None
    if sys.platform == "darwin":
        try:
            import Quartz  # noqa: F401
            return macos_provider
        except Exception:
            return None
    if sys.platform.startswith("linux"):
        try:
            import Xlib  # noqa: F401
            return linux_provider
        except Exception:
            return None
    return None

def get_active_window_info(provider):
    """
    Retrieves the active window title and owning process through the
    platform provider. Returns (None, None) on error. This never falls
    back to the monitor's own process.
    """
    try:
        return provider()
    except Exception as e:
        logging.error(f"Error getting active window information: {e}")
        return None, None

def main():
    """
    Main function to monitor window activity and log the information.
    Returns an exit code: 0 for a run stopped by the user, 1 for any
    refused or failed run.
    """
    parser = setup_argparse()
    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
        logging.debug("Verbose logging enabled.")

    interval = args.interval
    output_file = args.output

    if interval <= 0:
        logging.error("Interval must be a positive integer.")
        print("Error: Interval must be a positive integer.")
        return 1

    if ".." in output_file:
        logging.error("Invalid output file path (potential path traversal).")
        print("Error: Invalid output file path.")
        return 1

    provider = get_provider()
    if provider is None:
        logging.error("No foreground window provider is available on this platform.")
        print("Error: No foreground window provider is available on this platform: Windows needs ctypes, macOS needs the Quartz module, and Linux needs the Xlib module for X11.")
        return 1

    logging.info(f"Monitoring window activity every {interval} seconds.  Logging to {output_file}")

    previous_pair = None
    previous_since = None

    def close_previous(handle, when):
        if previous_pair is not None and previous_since is not None:
            duration = (when - previous_since).total_seconds()
            end_message = (f"Ended: {previous_pair[0]}, Process: {previous_pair[1]}, "
                           f"Duration: {duration:.0f} seconds")
            logging.info(end_message)
            handle.write(f"{when.isoformat(timespec='seconds')} - {end_message}\n")
            handle.flush()

    try:
        with open(output_file, "a") as f:
            while True:
                window_title, process_name = get_active_window_info(provider)

                if window_title and process_name:
                    current_pair = (window_title, process_name)
                    if current_pair != previous_pair:
                        now = datetime.now()
                        close_previous(f, now)
                        log_message = f"Active Window: {window_title}, Process: {process_name}"
                        logging.info(log_message)
                        f.write(f"{now.isoformat(timespec='seconds')} - {log_message}\n")
                        f.flush()
                        previous_pair = current_pair
                        previous_since = now
                else:
                    logging.warning("Could not retrieve window or process information.")

                time.sleep(interval)

    except KeyboardInterrupt:
        try:
            with open(output_file, "a") as f:
                close_previous(f, datetime.now())
        except OSError:
            pass
        logging.info("Monitoring stopped by user.")
        print("Monitoring stopped.")
        return 0
    except Exception as e:
        logging.error(f"An error occurred during monitoring: {e}")
        print(f"An error occurred: {e}")
        return 1
    return 0

if __name__ == "__main__":
    # Example Usage:
    # 1. Run with default settings (interval=5 seconds, output=window_activity.log):
    #    python3 main.py
    # 2. Run with a custom interval of 10 seconds:
    #    python3 main.py -i 10
    # 3. Run with a custom output file name:
    #    python3 main.py -o my_activity_log.txt
    # 4. Run with verbose logging (debug level):
    #    python3 main.py -v
    # 5. Combine options:
    #    python3 main.py -i 3 -o custom_log.txt -v
    sys.exit(main())
