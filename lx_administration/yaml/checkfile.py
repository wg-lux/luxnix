import os
import glob
import yaml
import pwd
import grp
import stat
from pydantic import BaseModel, Field, field_validator
from typing import Optional, List


class CheckFile(BaseModel):
    path: str
    relative: bool = Field(default=True)
    exists: bool = Field(default=True)
    symlink: bool = Field(default=False)
    directory: bool = Field(default=False)
    owner: Optional[str] = None
    group: Optional[str] = None
    filemode: Optional[str] = None

    @field_validator("filemode")
    def validate_filemode(cls, v):
        if v is not None:
            # Simple check to ensure filemode is 4 digits
            if len(v) != 4 or not all(c.isdigit() for c in v):
                raise ValueError("Invalid filemode format (use '0XYZ')")
        return v

    def check_and_fix(self):
        target_path = (
            os.path.join(os.getcwd(), self.path) if self.relative else self.path
        )
        if self.exists and not os.path.exists(target_path):
            raise ValueError(f"{target_path} expected but not found.")
        if self.directory and not os.path.isdir(target_path):
            raise ValueError(f"{target_path} is not a directory.")
        if self.owner:
            current_owner = pwd.getpwuid(os.stat(target_path).st_uid).pw_name
            if current_owner != self.owner:
                print(
                    f"Warning: Owner mismatch, correcting {current_owner} -> {self.owner}"
                )
                os.chown(
                    target_path,
                    pwd.getpwnam(self.owner).pw_uid,
                    os.stat(target_path).st_gid,
                )
        if self.group:
            current_group = grp.getgrgid(os.stat(target_path).st_gid).gr_name
            if current_group != self.group:
                print(
                    f"Warning: Group mismatch, correcting {current_group} -> {self.group}"
                )
                os.chown(
                    target_path,
                    os.stat(target_path).st_uid,
                    grp.getgrnam(self.group).gr_gid,
                )
        if self.filemode:
            desired_mode = int(self.filemode, 8)
            current_mode = stat.S_IMODE(os.stat(target_path).st_mode)
            if current_mode != desired_mode:
                print(
                    f"Warning: Filemode mismatch, correcting {oct(current_mode)} -> {oct(desired_mode)}"
                )
                os.chmod(target_path, desired_mode)


def load_check_files(folder: str) -> List[CheckFile]:
    check_files = []
    for file_path in glob.glob(os.path.join(folder, "*.yaml")):
        with open(file_path, "r") as f:
            data = yaml.safe_load(f)
            if not isinstance(data, list):
                raise ValueError(f"YAML in {file_path} must be a list of objects.")
            for item in data:
                check_files.append(CheckFile(**item))
    return check_files


def apply_checks(check_files: List[CheckFile]):
    for cf in check_files:
        target_path = os.path.join(os.getcwd(), cf.path) if cf.relative else cf.path
        print(f"Checking path: {target_path}")
        print(f" - Must exist: {cf.exists}")
        print(f" - Must be symlink: {cf.symlink}")
        print(f" - Must be directory: {cf.directory}")
        if cf.owner:
            print(f" - Desired owner: {cf.owner}")
        if cf.group:
            print(f" - Desired group: {cf.group}")
        if cf.filemode:
            print(f" - Desired filemode: {cf.filemode}")
        print("------------")
        cf.check_and_fix()


if __name__ == "__main__":
    folder_path = "./checks"  # folder with YAML files
    checks = load_check_files(folder_path)
    apply_checks(checks)
