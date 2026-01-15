import logging
from pathlib import Path


def log_heading(logger, heading):
    logger.info("\n")
    logger.info("-" * 80)
    logger.info(f"{heading}")
    logger.info("-" * 80)


def _default_formatter() -> logging.Formatter:
    return logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )


def get_logger(
    name: str,
    log_dir: Path = Path("./autoconf/logs"),
    reset: bool = False,
    log_level: int = logging.INFO,
) -> logging.Logger:
    """
    Create or retrieve a logger that logs to a dedicated file in log_dir.

    This function is idempotent and will not leak file descriptors when
    called repeatedly with the same name. Existing FileHandlers targeting
    the same logfile are reused and updated instead of adding duplicates.

    - When reset=True, the logfile is truncated but handlers are reused.
    - logger.propagate is disabled to avoid duplicate console logging.
    """
    log_dir.mkdir(parents=True, exist_ok=True)
    logfile = log_dir / f"{name}.log"

    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)
    logger.propagate = False

    # Truncate existing log if requested
    if reset:
        logfile.parent.mkdir(parents=True, exist_ok=True)
        # Ensure file exists, then truncate
        logfile.touch(exist_ok=True)
        with open(logfile, "w", encoding="utf-8"):
            pass

    # Try to find an existing FileHandler for this logfile
    for handler in logger.handlers:
        if isinstance(handler, logging.FileHandler):
            base = getattr(handler, "baseFilename", None)
            if base == str(logfile):
                # Reuse existing handler; just update config
                handler.setLevel(log_level)
                # Ensure formatter is set
                if not isinstance(handler.formatter, logging.Formatter):
                    handler.setFormatter(_default_formatter())
                return logger

    # No matching handler found; create one
    file_handler = logging.FileHandler(logfile, encoding="utf-8")
    file_handler.setLevel(log_level)
    file_handler.setFormatter(_default_formatter())
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
