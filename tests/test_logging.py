import logging
from pathlib import Path
import stat

import pytest

from lx_administration.logging import DEFAULT_LOG_DIR, close_logger, get_logger
from lx_administration.autoconf.nix.nix_file_fixes import fix_yml_list_in_nix_file
from lx_administration.autoconf.nix.utils import write_nix_file


def _file_handlers(logger: logging.Logger) -> list[logging.FileHandler]:
    return [
        handler
        for handler in logger.handlers
        if isinstance(handler, logging.FileHandler)
    ]


def test_default_log_directory_is_repository_relative() -> None:
    assert DEFAULT_LOG_DIR.is_absolute()
    assert DEFAULT_LOG_DIR == Path(__file__).parents[1] / "autoconf/logs"


def test_get_logger_reuses_one_handler_and_moves_it_cleanly(tmp_path) -> None:
    name = f"logging-contract-{tmp_path.name}"
    first_dir = tmp_path / "first"
    second_dir = tmp_path / "second"

    try:
        logger = get_logger(name, log_dir=first_dir, reset=True)
        first_handler = _file_handlers(logger)[0]
        assert get_logger(name, log_dir=first_dir) is logger
        assert _file_handlers(logger) == [first_handler]

        moved_logger = get_logger(name, log_dir=second_dir, reset=True)
        second_handler = _file_handlers(moved_logger)[0]
        assert moved_logger is logger
        assert second_handler is not first_handler
        assert first_handler.stream is None
        assert Path(second_handler.baseFilename) == second_dir / f"{name}.log"
    finally:
        close_logger(name)


def test_get_logger_resets_content_and_restricts_artifacts(tmp_path) -> None:
    name = f"logging-permissions-{tmp_path.name}"
    log_dir = tmp_path / "logs"
    logfile = log_dir / f"{name}.log"

    try:
        logger = get_logger(name, log_dir=log_dir, reset=True)
        logger.info("old entry")
        _file_handlers(logger)[0].flush()

        logger = get_logger(name, log_dir=log_dir, reset=True)
        logger.info("fresh entry")
        _file_handlers(logger)[0].flush()

        assert "old entry" not in logfile.read_text(encoding="utf-8")
        assert "fresh entry" in logfile.read_text(encoding="utf-8")
        assert stat.S_IMODE(log_dir.stat().st_mode) == 0o700
        assert stat.S_IMODE(logfile.stat().st_mode) == 0o600
    finally:
        close_logger(name)


def test_nix_list_normalizer_does_not_log_generated_values(tmp_path) -> None:
    name = f"logging-redaction-{tmp_path.name}"
    logfile_dir = tmp_path / "logs"
    nix_file = tmp_path / "default.nix"
    nix_file.write_text(
        "sensitive.values = [TOP_SECRET, SECOND_SECRET];\n", encoding="utf-8"
    )

    try:
        logger = get_logger(name, log_dir=logfile_dir, reset=True)
        fix_yml_list_in_nix_file(nix_file, logger=logger)
        _file_handlers(logger)[0].flush()

        log_text = (logfile_dir / f"{name}.log").read_text(encoding="utf-8")
        assert "Normalized comma-separated list on line 1" in log_text
        assert "TOP_SECRET" not in log_text
        assert "SECOND_SECRET" not in log_text
    finally:
        close_logger(name)


def test_nix_writer_has_no_hidden_log_artifacts(tmp_path) -> None:
    output = tmp_path / "default.nix"
    content = "values = [one, two];\n"

    write_nix_file(content, output)

    assert output.read_text(encoding="utf-8") == content
    assert list(tmp_path.iterdir()) == [output]


@pytest.mark.parametrize("name", ("", "../escape", "nested/name"))
def test_get_logger_rejects_unsafe_names(tmp_path, name) -> None:
    with pytest.raises(ValueError, match="filename component"):
        get_logger(name, log_dir=tmp_path)
