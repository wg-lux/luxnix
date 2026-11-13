"""One portable, fail-closed ciphertext publisher for independent recovery hosts."""

# Recovery hosts need only the Python standard library, not this package.
REMOTE_EXPORT = r'''
import fcntl, os, re, secrets, stat, sys
from pathlib import Path

def private(fd, directory=False):
    info = os.fstat(fd)
    kind = stat.S_ISDIR if directory else stat.S_ISREG
    mode = 0o700 if directory else 0o600
    if (not kind(info.st_mode) or info.st_uid != os.geteuid()
            or stat.S_IMODE(info.st_mode) != mode
            or (not directory and info.st_nlink != 1)):
        raise ValueError('Unsafe recovery export permissions, owner or file type')

def directory(parent, name):
    try:
        os.mkdir(name, 0o700, dir_fd=parent)
        os.fsync(parent)
    except FileExistsError:
        pass
    fd = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
    try:
        private(fd, directory=True)
    except BaseException:
        os.close(fd)
        raise
    return fd

def main(kind):
    owner, identifier = sys.argv[1:]
    if kind == 'volume':
        valid = (re.fullmatch(r'[0-9a-f]{32}', owner)
                 and re.fullmatch(r'[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}', identifier))
        parents = [owner]
    elif kind == 'openbao-local':
        valid = (re.fullmatch(r'[a-z0-9][a-z0-9-]*', owner)
                 and identifier in ('seal-key', 'enrollment', 'boot-passphrase'))
        parents = [kind, owner]
    else:
        raise ValueError('Unknown recovery export kind')
    if not valid:
        raise ValueError('Invalid recovery export identity')
    data = sys.stdin.buffer.read()
    header, separator, body = data.partition(b'\n')
    if (header != b'$ANSIBLE_VAULT;1.2;AES256;luxnix-master' or not separator
            or not body or not re.fullmatch(rb'[0-9a-f]+(?:\n[0-9a-f]+)*\n?', body)
            or len(body.replace(b'\n', b'')) % 2):
        raise ValueError('Expected master-vault ciphertext')
    home = Path.home()
    if home.resolve() != home:
        raise ValueError('Symlink in recovery home')
    descriptors = [os.open(home, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)]
    try:
        root = directory(descriptors[-1], '.luxnix-recovery')
        descriptors.append(root)
        lock = os.open('.lock', os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK,
                       0o600, dir_fd=root)
        descriptors.append(lock)
        private(lock)
        fcntl.flock(lock, fcntl.LOCK_EX)
        parent = root
        for name in parents:
            parent = directory(parent, name)
            descriptors.append(parent)
        name = identifier + '.vault'
        try:
            fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
        except FileNotFoundError:
            temporary = '.recovery-' + secrets.token_hex(16)
            fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                         0o600, dir_fd=parent)
            try:
                with os.fdopen(fd, 'wb') as stream:
                    stream.write(data)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.link(temporary, name, src_dir_fd=parent, dst_dir_fd=parent,
                        follow_symlinks=False)
            finally:
                os.unlink(temporary, dir_fd=parent)
            fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
        with os.fdopen(fd, 'rb') as stream:
            private(stream.fileno())
            stored = stream.read()
        if stored != data:
            raise ValueError('Conflicting recovery export')
        os.fsync(parent)
        sys.stdout.buffer.write(stored)
    finally:
        for fd in reversed(descriptors):
            os.close(fd)
'''


def export_script(kind):
    """Render the same publisher with the selected namespace and argument contract."""
    if kind not in {'volume', 'openbao-local'}:
        raise ValueError('Unknown recovery export kind')
    return REMOTE_EXPORT + '\nmain(' + repr(kind) + ')\n'
