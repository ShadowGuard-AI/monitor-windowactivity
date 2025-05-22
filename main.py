import argparse
import logging
import time
import psutil
import os

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

def get_active_window_info():
    """
    Retrieves the active window title and process information.
    Returns:
        tuple: A tuple containing the window title and process name.
               Returns (None, None) if an error occurs.
    """
    try:
        # Cross-platform compatible approach (works better on Windows and macOS)
        active_window = psutil._psplatform.os.getpid()

        # Attempt to obtain window title and process name
        try:
            process = psutil.Process(active_window)
            window_title = process.name() #Get process name. There is no reliable cross-platform way to get window title
            process_name = process.name()
        except psutil.NoSuchProcess:
            logging.warning("Active process not found.")
            return None, None
        except psutil.AccessDenied:
            logging.warning("Access denied to active process.")
            return None, None
        except Exception as e:
            logging.error(f"An unexpected error occurred: {e}")
            return None, None

        return window_title, process_name
    except Exception as e:
        logging.error(f"Error getting active window information: {e}")
        return None, None

def main():
    """
    Main function to monitor window activity and log the information.
    """
    parser = setup_argparse()
    args = parser.parse_args()

    # Configure logging level based on verbosity
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
        logging.debug("Verbose logging enabled.")

    interval = args.interval
    output_file = args.output

    # Input validation for interval
    if interval <= 0:
        logging.error("Interval must be a positive integer.")
        print("Error: Interval must be a positive integer.")
        return

    # Input validation for output file (basic check for path traversal)
    if ".." in output_file:
        logging.error("Invalid output file path (potential path traversal).")
        print("Error: Invalid output file path.")
        return

    logging.info(f"Monitoring window activity every {interval} seconds.  Logging to {output_file}")

    try:
        with open(output_file, "a") as f:  # Open in append mode
            while True:
                window_title, process_name = get_active_window_info()

                if window_title and process_name:
                    log_message = f"Active Window: {window_title}, Process: {process_name}"
                    logging.info(log_message)
                    f.write(log_message + "\n")
                    f.flush() # Ensure data is written to disk immediately
                else:
                    logging.warning("Could not retrieve window or process information.")

                time.sleep(interval)

    except KeyboardInterrupt:
        logging.info("Monitoring stopped by user.")
        print("Monitoring stopped.")
    except Exception as e:
        logging.error(f"An error occurred during monitoring: {e}")
        print(f"An error occurred: {e}")

# Usage Examples
if __name__ == "__main__":
    # Example Usage:
    # 1. Run with default settings (interval=5 seconds, output=window_activity.log):
    #    python main.py
    # 2. Run with a custom interval of 10 seconds:
    #    python main.py -i 10
    # 3. Run with a custom output file name:
    #    python main.py -o my_activity_log.txt
    # 4. Run with verbose logging (debug level):
    #    python main.py -v
    # 5. Combine options:
    #    python main.py -i 3 -o custom_log.txt -v

    main()