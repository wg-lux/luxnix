from pathlib import Path


def str2path(
    path: str,
    expanduser: bool = True,
    resolve: bool = True,
    return_as_string: bool = False,
) -> Path:
    p = Path(path)

    if expanduser:
        p = p.expanduser()

    if resolve:
        p = p.resolve()

    if return_as_string:
        return p.as_posix()

    return p
