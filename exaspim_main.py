import argparse
import os
from exaspim_userinterface import UserInterface
from coloredlogs import ColoredFormatter
import traceback
import logging
import sys
import ctypes
from pathlib import Path


class SpimLogFilter(logging.Filter):
    # Note: add additional modules that we want to catch here.
    VALID_LOGGER_BASES = {'spim_core', 'exaspim', 'camera', }#'tigerasi'}

    def filter(self, record):
        """Returns true for a record that matches a log we want to keep."""
        return record.name.split('.')[0].lower() in \
            self.__class__.VALID_LOGGER_BASES


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument("--config_path", type=str, default=None)
    parser.add_argument("--log_level", type=str, default="DEBUG",
                        choices=["INFO", "DEBUG"])
    parser.add_argument("--console_output", default=True,
                        help="whether or not to print to the console.")
    parser.add_argument("--simulated", default=False, action="store_true",
                        help="Simulate hardware device connections.")
    # Note: colored console output is buggy on Windows.
    parser.add_argument("--color_console_output", type=bool,
                        default=True)

    args = parser.parse_args()
    # Check if we didn't supply a config file and populate a safe guess.
    if not args.config_path:
        args.config_path = str(Path('./config.toml').absolute())

    # Setup logging.
    # Create log handlers to dispatch:
    # - User-specified level and above to print to console if specified.
    logger = logging.getLogger()  # get the root logger.
    # Remove any handlers already attached to the root logger.
    logging.getLogger().handlers.clear()
    # logger level must be set to the lowest level of any handler.
    logger.setLevel(logging.DEBUG)
    fmt = '%(asctime)s.%(msecs)03d %(levelname)s %(name)s: %(message)s'
    fmt = "[SIM] " + fmt if args.simulated else fmt
    datefmt = '%Y-%m-%d,%H:%M:%S'
    log_formatter = ColoredFormatter(fmt=fmt, datefmt=datefmt) \
        if args.color_console_output \
        else logging.Formatter(fmt=fmt, datefmt=datefmt)
    if args.console_output:
        log_handler = logging.StreamHandler(sys.stdout)
        log_handler.addFilter(SpimLogFilter())
        log_handler.setLevel(args.log_level)
        log_handler.setFormatter(log_formatter)
        logger.addHandler(log_handler)

    # Windows-based console needs to accept colored logs if running with color.
    if os.name == 'nt' and args.color_console_output:
        kernel32 = ctypes.windll.kernel32
        kernel32.SetConsoleMode(kernel32.GetStdHandle(-11), 7)

    run = UserInterface(config_filepath=args.config_path,
                        console_output_level=args.log_level,
                        simulated=args.simulated)
