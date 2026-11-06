"""Repository CLI for the canonical secret storage boundary verifier."""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from lx_administration.secret_storage import encrypted_storage, main  # noqa: E402

__all__ = ["encrypted_storage", "main"]

if __name__ == "__main__":
    main()
