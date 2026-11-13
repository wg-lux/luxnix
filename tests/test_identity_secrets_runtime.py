from __future__ import annotations

from pathlib import Path
import runpy
import subprocess
import sys
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_retired_launcher_fails_before_network_or_exec() -> None:
    module = runpy.run_path(str(ROOT / "scripts/run-identity-secrets.py"))
    with patch("subprocess.run") as network, patch("os.execve") as launch:
        with pytest.raises(
            SystemExit, match="Central identity salt provisioning is disabled"
        ):
            module["main"]()
        network.assert_not_called()
        launch.assert_not_called()


def test_retired_launcher_command_fails_without_configuration() -> None:
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts/run-identity-secrets.py")],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0
    assert "Central identity salt provisioning is disabled" in result.stderr
    assert not result.stdout


def test_central_provisioner_rejects_before_file_access(tmp_path: Path) -> None:
    module = runpy.run_path(str(ROOT / "scripts/provision-identity-salts.py"))
    with patch("os.open") as opened:
        with pytest.raises(
            ValueError, match="Central identity salt provisioning is disabled"
        ):
            module["provision_center"](
                tmp_path, tmp_path, tmp_path, 0, 0, tmp_path / "absent", "center"
            )
        opened.assert_not_called()
    assert list(tmp_path.iterdir()) == []
