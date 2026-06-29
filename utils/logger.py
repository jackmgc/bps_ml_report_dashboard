"""Logging configuration for ETL pipeline"""
import logging
import os
from config.db_config import LOG_LEVEL, REPORTS_FOLDER

# Ensure reports folder exists
os.makedirs(REPORTS_FOLDER, exist_ok=True)

# Create logger
logger = logging.getLogger("ETL")
logger.setLevel(getattr(logging, LOG_LEVEL, logging.INFO))

# Console handler
console_handler = logging.StreamHandler()
console_handler.setLevel(getattr(logging, LOG_LEVEL, logging.INFO))
console_formatter = logging.Formatter(
    "%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
console_handler.setFormatter(console_formatter)

# File handler
file_handler = logging.FileHandler(os.path.join(REPORTS_FOLDER, "etl.log"))
file_handler.setLevel(logging.DEBUG)
file_formatter = logging.Formatter(
    "%(asctime)s [%(levelname)s] %(name)s - %(message)s [%(filename)s:%(lineno)d]",
    datefmt="%Y-%m-%d %H:%M:%S"
)
file_handler.setFormatter(file_formatter)

# Add handlers to logger
logger.addHandler(console_handler)
logger.addHandler(file_handler)

def get_logger(name):
    """Get a logger instance for a module"""
    return logger.getChild(name)
