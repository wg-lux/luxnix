import grp
import os
import pwd
import stat
from argparse import ArgumentParser
from collections.abc import Iterable
from pathlib import Path

from pydantic import BaseModel, Field, field_validator

from .loading import load_unique_yaml_file


class CheckFile(BaseModel):
    path: str
    relative: bool = Field(default=True)
    exists: bool = Field(default=True)
    symlink: bool = Field(default=False)
    directory: bool = Field(default=False)
    owner: str | None = None
    group: str | None = None
    filemode: str | None = None

    @field_validator("filemode")
    @classmethod
    def validate_filemode(cls, value: str | None) -> str | None:
        if value is not None:
            if len(value) != 4 or not all(character.isdigit() for character in value):
                raise ValueError("Invalid filemode format (use '0XYZ')")
        return value

    def resolved_path(self) -> Path:
        """Return the configured path relative to the current working directory."""
        path = Path(self.path).expanduser()
        return Path.cwd() / path if self.relative else path

    def check_and_fix(self) -> None:
        """Validate one path and correct explicitly configured ownership or mode."""
        target_path = self.resolved_path()
        if self.exists and not target_path.exists():
            raise ValueError(f"{target_path} expected but not found.")
        if self.symlink and not target_path.is_symlink():
            raise ValueError(f"{target_path} is not a symbolic link.")
        if self.directory and not target_path.is_dir():
            raise ValueError(f"{target_path} is not a directory.")
        if self.owner:
            current_owner = pwd.getpwuid(target_path.stat().st_uid).pw_name
            if current_owner != self.owner:
                print(
                    "Warning: Owner mismatch, correcting "
                    f"{current_owner} -> {self.owner}"
                )
                os.chown(
                    target_path,
                    pwd.getpwnam(self.owner).pw_uid,
                    target_path.stat().st_gid,
                )
        if self.group:
            current_group = grp.getgrgid(target_path.stat().st_gid).gr_name
            if current_group != self.group:
                print(
                    "Warning: Group mismatch, correcting "
                    f"{current_group} -> {self.group}"
                )
                os.chown(
                    target_path,
                    target_path.stat().st_uid,
                    grp.getgrnam(self.group).gr_gid,
                )
        if self.filemode:
            desired_mode = int(self.filemode, 8)
            current_mode = stat.S_IMODE(target_path.stat().st_mode)
            if current_mode != desired_mode:
                print(
                    "Warning: Filemode mismatch, correcting "
                    f"{oct(current_mode)} -> {oct(desired_mode)}"
                )
                target_path.chmod(desired_mode)


def load_check_files(folder: str | Path) -> list[CheckFile]:
    """Load `.yml` and legacy `.yaml` check definitions in filename order."""
    folder_path = Path(folder)
    definitions = sorted((*folder_path.glob("*.yml"), *folder_path.glob("*.yaml")))
    check_files: list[CheckFile] = []
    for file_path in definitions:
        data = load_unique_yaml_file(file_path)
        if not isinstance(data, list):
            raise ValueError(f"YAML in {file_path} must be a list of objects.")
        check_files.extend(CheckFile(**item) for item in data)
    return check_files


def apply_checks(check_files: Iterable[CheckFile]) -> None:
    for check_file in check_files:
        target_path = check_file.resolved_path()
        print(f"Checking path: {target_path}")
        print(f" - Must exist: {check_file.exists}")
        print(f" - Must be symlink: {check_file.symlink}")
        print(f" - Must be directory: {check_file.directory}")
        if check_file.owner:
            print(f" - Desired owner: {check_file.owner}")
        if check_file.group:
            print(f" - Desired group: {check_file.group}")
        if check_file.filemode:
            print(f" - Desired filemode: {check_file.filemode}")
        print("------------")
        check_file.check_and_fix()


def main() -> None:
    parser = ArgumentParser(
        description="Validate paths and apply explicitly configured ownership/modes."
    )
    parser.add_argument(
        "folder",
        nargs="?",
        type=Path,
        default=Path("conf/check_files"),
        help="folder containing .yml check definitions (default: conf/check_files)",
    )
    args = parser.parse_args()
    apply_checks(load_check_files(args.folder))


if __name__ == "__main__":
    main()
