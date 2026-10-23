import logging
from pathlib import Path

from ..permissions import PRIVATE_FILE_MODE, ensure_private_directory


DEFAULT_LOG_DIR = Path(__file__).resolve().parents[2] / "autoconf" / "logs"


def log_heading(logger: logging.Logger, heading: str) -> None:
    logger.info("\n")
    logger.info("-" * 80)
    logger.info(heading)
    logger.info("-" * 80)


def _default_formatter() -> logging.Formatter:
    return logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")


def get_logger(
    name: str,
    log_dir: Path = DEFAULT_LOG_DIR,
    reset: bool = False,
    log_level: int = logging.INFO,
) -> logging.Logger:
    """Create or retrieve one file logger in ``log_dir``.

    Repeated calls reuse the matching handler. Moving a named logger to another
    directory closes its previous file handler instead of duplicating output.
    """
    if not name or Path(name).name != name:
        raise ValueError("Logger name must be a non-empty filename component")

    log_dir = ensure_private_directory(log_dir.expanduser().resolve())
    logfile = log_dir / f"{name}.log"

    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)
    logger.propagate = False

    file_handler = None
    for handler in list(logger.handlers):
        if not isinstance(handler, logging.FileHandler):
            continue
        if Path(handler.baseFilename) == logfile:
            file_handler = handler
            continue
        logger.removeHandler(handler)
        handler.close()

    if reset:
        logfile.write_text("", encoding="utf-8")

    if file_handler is None:
        file_handler = logging.FileHandler(logfile, encoding="utf-8")
    logfile.chmod(PRIVATE_FILE_MODE)
    file_handler.setLevel(log_level)
    file_handler.setFormatter(_default_formatter())
    if file_handler not in logger.handlers:
        logger.addHandler(file_handler)

    return logger


def close_logger(name: str) -> None:
    """Close and remove all handlers from the named logger."""
    logger = logging.getLogger(name)
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        try:
            handler.close()
        except Exception:
            pass


def shutdown_logging() -> None:
    """Gracefully close all logging handlers across the process."""
    logging.shutdown()
