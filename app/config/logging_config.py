import logging
import sys

from app.config.config import LOG_LEVEL

COLOR_RESET = "\033[0m"
COLOR_BLUE = "\033[94m"
COLOR_YELLOW = "\033[93m"
COLOR_RED = "\033[91m"
COLOR_ORANGE = "\033[38;5;208m"
COLOR_DEFAULT = ""


class CustomColorFormatter(logging.Formatter):
    def format(self, record):
        log_fmt = "%(levelname)s | %(asctime)s | %(name)s:%(lineno)s | %(message)s"
        formatter = logging.Formatter(log_fmt)

        color = {
            logging.INFO: COLOR_BLUE,
            logging.WARNING: COLOR_YELLOW,
            logging.ERROR: COLOR_RED,
            logging.CRITICAL: COLOR_ORANGE,
            logging.DEBUG: COLOR_DEFAULT
        }.get(record.levelno, COLOR_DEFAULT)

        formatted_message = formatter.format(record)
        return f"{color}{formatted_message}{COLOR_RESET}"


logging.getLogger("urllib3").setLevel(logging.DEBUG)


def get_logger(class_name):
    """
    Get configured logger with color output
    """
    logger = logging.getLogger(class_name)
    logger.setLevel(LOG_LEVEL)

    handler = logging.StreamHandler(stream=sys.stdout)
    handler.setLevel(LOG_LEVEL)
    handler.setFormatter(CustomColorFormatter())
    logger.addHandler(handler)
    logger.propagate = False
    return logger
