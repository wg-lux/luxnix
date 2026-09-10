from lx_administration.password.files import (
    PRIVATE_FILE_MODE as PASSWORD_FILE_MODE,
)
from lx_administration.permissions import (
    PRIVATE_DIRECTORY_MODE,
    PRIVATE_FILE_MODE,
    ensure_private_directory,
)
from lx_administration.yaml import (
    PRIVATE_DIRECTORY_MODE as YAML_DIRECTORY_MODE,
)
from lx_administration.yaml import (
    PRIVATE_FILE_MODE as YAML_FILE_MODE,
)


def test_private_artifact_modes_have_one_compatible_source():
    assert PRIVATE_FILE_MODE == PASSWORD_FILE_MODE == YAML_FILE_MODE == 0o600
    assert PRIVATE_DIRECTORY_MODE == YAML_DIRECTORY_MODE == 0o700


def test_ensure_private_directory_creates_and_hardens_path(tmp_path):
    directory = tmp_path / "nested/private"
    directory.mkdir(parents=True)
    directory.chmod(0o755)

    result = ensure_private_directory(directory)

    assert result == directory
    assert directory.stat().st_mode & 0o777 == PRIVATE_DIRECTORY_MODE
