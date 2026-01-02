import logging.config
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

from app.core.time_util import get_timezone


def custom_time_converter(*args: Any) -> time.struct_time:
    """Converter for logging to use the configured timezone."""
    utc_dt = datetime.fromtimestamp(args[0], get_timezone())
    return utc_dt.timetuple()


def setup_logging(config_path: str = "logging.yaml") -> None:
    """Загружает конфигурацию логирования из YAML файла."""
    logging.Formatter.converter = custom_time_converter

    path = Path(config_path)
    if not path.exists():
        logging.basicConfig(level=logging.INFO)
        logging.warning(f"Logging config file not found at {path}. Using basicConfig.")
        return

    with open(path) as f:
        try:
            config = yaml.safe_load(f.read())
            logging.config.dictConfig(config)
        except Exception as e:
            logging.basicConfig(level=logging.INFO)
            logging.error(f"Error loading logging config: {e}")
            logging.error("Using basicConfig as fallback.")
