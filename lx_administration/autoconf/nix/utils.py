"""Write rendered Nix configuration files."""

import logging
import shutil
import subprocess
import tempfile
from collections.abc import Callable, Iterable
from pathlib import Path

from ..errors import AutoconfPipelineError

RenderedNixOutput = tuple[Path, str]
NixfmtRunner = Callable[[Path], None]


def run_nixfmt(source: Path) -> None:
    """Format one temporary Nix file with LuxNix's repository formatter."""
    try:
        subprocess.run(
            ("nixfmt", str(source)),
            check=True,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError as exc:
        raise AutoconfPipelineError(
            "Cannot format generated Nix output because the required repository "
            "formatter 'nixfmt' is not available on PATH"
        ) from exc
    except subprocess.CalledProcessError as exc:
        raise AutoconfPipelineError(
            "Cannot format generated Nix output with the repository formatter "
            f"'nixfmt' (exit status {exc.returncode})"
        ) from exc


def format_nix_outputs(
    outputs: Iterable[RenderedNixOutput],
    *,
    formatter_runner: NixfmtRunner | None = None,
) -> list[RenderedNixOutput]:
    """Return all rendered outputs normalized by the repository's ``nixfmt``.

    Formatting happens in a private temporary directory, before an output path
    is changed.  This keeps the normal and isolated publication paths
    deterministic while making the formatter dependency straightforward to
    replace in focused tests.
    """
    runner = formatter_runner or run_nixfmt
    formatted_outputs: list[RenderedNixOutput] = []
    with tempfile.TemporaryDirectory(prefix="luxnix-autoconf-nixfmt-") as temp_dir:
        workspace = Path(temp_dir)
        for index, (destination, content) in enumerate(outputs):
            temporary_output = workspace / f"{index}.nix"
            temporary_output.write_text(content, encoding="utf-8")
            try:
                runner(temporary_output)
            except AutoconfPipelineError as exc:
                raise AutoconfPipelineError(
                    f"Generated Nix output {destination} failed formatting: {exc}"
                ) from exc
            except OSError as exc:
                raise AutoconfPipelineError(
                    f"Generated Nix output {destination} failed formatting: "
                    "the required "
                    "repository formatter 'nixfmt' could not run"
                ) from exc
            except Exception as exc:
                raise AutoconfPipelineError(
                    f"Generated Nix output {destination} failed formatting with the "
                    "repository "
                    "formatter 'nixfmt'"
                ) from exc
            formatted_outputs.append(
                (destination, temporary_output.read_text(encoding="utf-8"))
            )
    return formatted_outputs


def write_nix_file(
    content: str,
    filepath: str | Path,
    logger: logging.Logger | None = None,
) -> None:
    """Write one already-normalized rendered Nix file."""
    destination = Path(filepath)
    destination.write_text(content, encoding="utf-8")


def write_nix_outputs(
    outputs: Iterable[RenderedNixOutput],
    logger: logging.Logger | None = None,
    *,
    formatter_runner: NixfmtRunner | None = None,
) -> None:
    """Normalize every output, then publish the complete rendered sequence."""
    formatted_outputs = format_nix_outputs(
        outputs,
        formatter_runner=formatter_runner,
    )
    for destination, content in formatted_outputs:
        destination.parent.mkdir(parents=True, exist_ok=True)
        write_nix_file(content, destination, logger=logger)
        if logger is not None:
            logger.info("Wrote generated Nix configuration: %s", destination)


def write_new_nix_output_tree(
    outputs: Iterable[RenderedNixOutput],
    output_root: str | Path,
    logger: logging.Logger | None = None,
    *,
    formatter_runner: NixfmtRunner | None = None,
) -> None:
    """Publish outputs into one previously nonexistent output root.

    This is intentionally stricter than :func:`write_nix_outputs`: it reserves
    a new root with ``mkdir(exist_ok=False)`` and rejects any rendered path that
    escapes that root.  A failed publication removes only the root this call
    created, so an isolated render never replaces an existing output tree.
    """
    root = Path(output_root).expanduser().resolve()
    rendered_outputs = list(outputs)
    destinations: set[Path] = set()
    for destination, _content in rendered_outputs:
        resolved_destination = destination.expanduser().resolve()
        try:
            resolved_destination.relative_to(root)
        except ValueError as exc:
            raise AutoconfPipelineError(
                "Isolated Nix render produced a path outside its output root: "
                f"{resolved_destination}"
            ) from exc
        if resolved_destination in destinations:
            raise AutoconfPipelineError(
                "Isolated Nix render produced the same output more than once: "
                f"{resolved_destination}"
            )
        destinations.add(resolved_destination)

    try:
        root.mkdir(parents=True, exist_ok=False)
    except FileExistsError as exc:
        raise AutoconfPipelineError(
            "Isolated Nix render target must be a new directory: "
            f"{root}"
        ) from exc

    try:
        write_nix_outputs(
            rendered_outputs,
            logger=logger,
            formatter_runner=formatter_runner,
        )
    except Exception:
        shutil.rmtree(root)
        raise
