import logging
from pathlib import Path


def log_heading(logger, heading):
    logger.info("\n")
    logger.info("-" * 80)
    logger.info(f"{heading}")
    logger.info("-" * 80)


def get_logger(name, log_dir: Path = Path("./autoconf/logs"), reset=False):
    log_dir.mkdir(exist_ok=True)

    logfile = log_dir / f"{name}.log"

    if reset:
        open(logfile, "w").close()

    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)

    file_handler = logging.FileHandler(logfile)
    file_handler.setLevel(logging.INFO)
    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    # (Removed console handler)

    return logger
