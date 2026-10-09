"""Host-local API admission and trailing background-resource throttle.

systemd owns the socket and activity file. Clients hold shared file locks for
their request lifetime; this controller never stores request identities.
"""

from __future__ import annotations

import argparse
from collections.abc import Callable
from dataclasses import dataclass
import fcntl
import json
import math
from pathlib import Path
import pwd
import selectors
import socket
import struct
import subprocess
import time
from typing import BinaryIO

POLL_SECONDS = 0.1
HANDSHAKE_SECONDS = 1.0
MAX_PENDING_CONNECTIONS = 128
SLICE = "lx-annotate-background.slice"


def has_activity(activity_file: BinaryIO) -> bool:
    try:
        fcntl.flock(activity_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        return True
    fcntl.flock(activity_file.fileno(), fcntl.LOCK_UN)
    return False


@dataclass
class ThrottleState:
    tail_seconds: float
    apply: Callable[[bool], None]
    throttled: bool | None = None
    idle_since: float | None = None

    def __post_init__(self) -> None:
        if not math.isfinite(self.tail_seconds) or self.tail_seconds < 0:
            raise ValueError("Request throttle tail must be finite and non-negative")

    def set_mode(self, active: bool) -> None:
        if self.throttled != active:
            self.apply(active)
            self.throttled = active

    def admit(self) -> None:
        self.idle_since = None
        self.set_mode(True)

    def reconcile(self, *, active: bool, now: float) -> None:
        if active:
            self.admit()
            return
        if self.idle_since is None:
            self.idle_since = now
        self.set_mode(now - self.idle_since < self.tail_seconds)


def apply_profile(
    active: bool, *, systemctl: str, cpu_quota: str, cpu_weight: int, io_weight: int
) -> None:
    subprocess.run(
        [
            systemctl,
            "set-property",
            "--runtime",
            SLICE,
            f"CPUQuota={cpu_quota if active else ''}",
            f"CPUWeight={cpu_weight if active else 100}",
            f"IOWeight={io_weight if active else 100}",
        ],
        check=True,
        capture_output=True,
        timeout=2,
    )
    print(
        json.dumps({"event": "request_throttle.profile", "active": active}), flush=True
    )


class Controller:
    def __init__(
        self,
        *,
        listener: socket.socket,
        activity_file: BinaryIO,
        allowed_uid: int,
        state: ThrottleState,
    ) -> None:
        self.listener = listener
        self.activity_file = activity_file
        self.allowed_uid = allowed_uid
        self.state = state
        self.selector = selectors.DefaultSelector()
        self.pending: dict[socket.socket, float] = {}
        listener.setblocking(False)
        self.selector.register(listener, selectors.EVENT_READ)

    def _drop(self, connection: socket.socket) -> None:
        self.pending.pop(connection)
        self.selector.unregister(connection)
        connection.close()

    def _accept(self) -> None:
        connection, _ = self.listener.accept()
        credentials = connection.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12)
        _, uid, _ = struct.unpack("3i", credentials)
        if uid != self.allowed_uid or len(self.pending) >= MAX_PENDING_CONNECTIONS:
            connection.close()
            return
        connection.setblocking(False)
        self.pending[connection] = time.monotonic() + HANDSHAKE_SECONDS
        self.selector.register(connection, selectors.EVENT_READ)

    def step(self) -> None:
        for key, _ in self.selector.select(POLL_SECONDS):
            if key.fileobj is self.listener:
                self._accept()
                continue
            connection = key.fileobj
            if not isinstance(connection, socket.socket):
                raise TypeError("Unexpected throttle selector entry")
            try:
                request = connection.recv(2)
            except (ConnectionResetError, BlockingIOError):
                self._drop(connection)
                continue
            if request == b"+":
                # Never acknowledge a request before systemd confirms the limit.
                self.state.admit()
                try:
                    connection.sendall(b"+")
                except (BrokenPipeError, ConnectionResetError, BlockingIOError):
                    pass  # The client abandoned admission; its lock controls expiry.
            self._drop(connection)
        now = time.monotonic()
        for connection, deadline in tuple(self.pending.items()):
            if now >= deadline:
                self._drop(connection)
        self.state.reconcile(active=has_activity(self.activity_file), now=now)

    def close(self) -> None:
        for connection in tuple(self.pending):
            self._drop(connection)
        self.selector.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--user", required=True)
    parser.add_argument("--systemctl", required=True)
    parser.add_argument("--tail-seconds", type=float, required=True)
    parser.add_argument("--cpu-quota", required=True)
    parser.add_argument("--cpu-weight", type=int, required=True)
    parser.add_argument("--io-weight", type=int, required=True)
    args = parser.parse_args()
    if not 1 <= args.cpu_weight <= 10000 or not 1 <= args.io_weight <= 10000:
        parser.error("Resource weights must be between 1 and 10000")

    def apply(active: bool) -> None:
        apply_profile(
            active,
            systemctl=args.systemctl,
            cpu_quota=args.cpu_quota,
            cpu_weight=args.cpu_weight,
            io_weight=args.io_weight,
        )

    state = ThrottleState(args.tail_seconds, apply)
    with (
        socket.socket(fileno=3) as listener,
        (args.directory / "activity.lock").open("rb") as activity_file,
    ):
        controller = Controller(
            listener=listener,
            activity_file=activity_file,
            allowed_uid=pwd.getpwnam(args.user).pw_uid,
            state=state,
        )
        try:
            state.reconcile(active=has_activity(activity_file), now=time.monotonic())
            while True:
                controller.step()
        finally:
            controller.close()


if __name__ == "__main__":
    try:
        main()
    except (OSError, subprocess.SubprocessError, ValueError) as exc:
        print(
            json.dumps(
                {
                    "event": "request_throttle.controller_failed",
                    "error_type": type(exc).__name__,
                }
            ),
            flush=True,
        )
        raise SystemExit(1) from None
