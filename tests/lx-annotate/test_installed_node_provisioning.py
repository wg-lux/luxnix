"""Release parity lane: install the selected wheel, use real SQLite transactions.

Run with LX_ANNOTATE_PARITY_WHEEL and Django available. Lightweight domain models
exercise the application's model API contract, not the backend's own model suite.
"""

import hashlib
import importlib
import io
import json
import os
import shutil
from pathlib import Path
import subprocess
import sys
from types import ModuleType

import pytest


@pytest.fixture
def installed(tmp_path, monkeypatch):
    wheel = os.environ.get("LX_ANNOTATE_PARITY_WHEEL")
    if not wheel:
        pytest.skip("explicit installed-wheel parity lane")
    assert hashlib.sha256(Path(wheel).read_bytes()).hexdigest() == (
        "4cf2f7fd22fe68539a312ea709433601fd663338f97459cf1991e4d5c237152a"
    )
    import django
    from django.conf import settings
    from django.contrib.auth.hashers import check_password, make_password
    from django.db import connection, models

    if not settings.configured:
        settings.configure(
            DATABASES={
                "default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}
            },
            INSTALLED_APPS=[],
        )
        django.setup()

    class Center(models.Model):
        center_key = models.CharField(max_length=255, unique=True)

        class Meta:
            app_label = "parity"

    class NetworkNode(models.Model):
        class Role(models.TextChoices):
            STORAGE = "storage_node"

        node_key = models.CharField(max_length=255, unique=True)
        display_name = models.CharField(max_length=255)
        role = models.CharField(max_length=64)
        base_url = models.CharField(max_length=255)
        is_active = models.BooleanField(default=True)
        owning_center = models.ForeignKey(Center, on_delete=models.CASCADE)
        shared_secret_hash = models.TextField(default="")
        updated_at = models.DateTimeField(auto_now=True)

        def set_shared_secret(self, value):
            self.shared_secret_hash = make_password(value)

        def check_shared_secret(self, value):
            return check_password(value, self.shared_secret_hash)

        class Meta:
            app_label = "parity"

    backend = ModuleType("endoreg_db.models")
    backend.Center, backend.NetworkNode = Center, NetworkNode
    monkeypatch.setitem(sys.modules, "endoreg_db.models", backend)
    staged = tmp_path / "lx_annotate-1.7.2-py3-none-any.whl"
    shutil.copyfile(wheel, staged)
    target = tmp_path / "installed"
    subprocess.run(
        [
            sys.executable,
            "-m",
            "pip",
            "install",
            "--no-deps",
            "--no-index",
            "--target",
            str(target),
            str(staged),
        ],
        check=True,
        capture_output=True,
    )
    monkeypatch.syspath_prepend(str(target))
    monkeypatch.chdir(tmp_path)
    module = importlib.import_module(
        "lx_annotate.management.commands.provision_hub_nodes"
    )
    assert Path(module.__file__).is_relative_to(target)
    with connection.schema_editor() as schema:
        schema.create_model(Center)
        schema.create_model(NetworkNode)
    try:
        yield module, Center, NetworkNode
    finally:
        with connection.schema_editor() as schema:
            schema.delete_model(NetworkNode)
            schema.delete_model(Center)
        for name in list(sys.modules):
            if name == "lx_annotate" or name.startswith("lx_annotate."):
                monkeypatch.delitem(sys.modules, name)


def test_installed_provisioning_aliases_repeat_rotation_and_rollback(
    installed, tmp_path
):
    module, Center, NetworkNode = installed
    Center.objects.create(center_key="synthetic-center")
    secret = tmp_path / "synthetic-secret"
    secret.write_text("synthetic-initial-secret")
    spec = {
        "nodeKey": "synthetic-node",
        "displayName": "Synthetic node",
        "role": "storage_node",
        "baseUrl": "https://node.invalid",
        "centerKey": "synthetic-center",
        "sharedSecretFile": str(secret),
    }
    config = tmp_path / "nodes.json"

    def provision(specs):
        config.write_text(json.dumps(specs))
        output = io.StringIO()
        module.Command(stdout=output).handle(
            config=config, require_existing_centers=True
        )
        return output.getvalue()

    assert '"created": true' in provision([spec])
    initial = NetworkNode.objects.get()
    assert initial.check_shared_secret(secret.read_text())
    assert '"secret_changed": false' in provision([spec])
    assert NetworkNode.objects.get().shared_secret_hash == initial.shared_secret_hash
    secret.write_text("synthetic-rotated-secret")
    assert '"secret_changed": true' in provision([spec])
    assert NetworkNode.objects.get().check_shared_secret(secret.read_text())
    for bad in [
        dict(spec, centerKey="missing"),
        dict(spec, sharedSecretFile=str(tmp_path / "absent")),
    ]:
        with pytest.raises(module.CommandError):
            provision([dict(spec, displayName="must roll back"), bad])
        assert NetworkNode.objects.get().display_name == "Synthetic node"
        assert Center.objects.count() == NetworkNode.objects.count() == 1
