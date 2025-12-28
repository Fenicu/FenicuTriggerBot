import logging.config
from pathlib import Path

import yaml


def setup_logging(config_path: str = "logging.yaml") -> None:
    """Загружает конфигурацию логирования из YAML файла."""
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
