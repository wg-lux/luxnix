from pathlib import Path
import os
import shutil
import subprocess

import pytest

from nix_eval_helpers import REPO_ROOT, eval_json

SQL = REPO_ROOT / "modules/nixos/roles/postgres-default/collation-repair.sql"


@pytest.fixture
def database(tmp_path):
    if not shutil.which("initdb") or not shutil.which("pg_ctl"):
        pytest.skip("PostgreSQL server binaries required")
    data = tmp_path / "data"
    subprocess.run(["initdb", "-D", str(data), "-A", "trust", "-U", "postgres",
                    "--locale=en_US.utf8", "--encoding=UTF8"], check=True, capture_output=True)
    subprocess.run(["pg_ctl", "-D", str(data), "-l", str(tmp_path / "log"),
                    "-o", f"-k {tmp_path} -c listen_addresses=''", "-w", "start"],
                   check=True, capture_output=True)
    env = {**os.environ, "PGHOST": str(tmp_path), "PGPORT": "5432",
           "PGUSER": "postgres", "PGDATABASE": "postgres"}
    env.pop("PGOPTIONS", None)

    def query(*args, options=None):
        return subprocess.run(["psql", "-XAt", "-v", "ON_ERROR_STOP=1", *args],
                              env={**env, **(options or {})}, capture_output=True, text=True)

    try:
        yield query
    finally:
        subprocess.run(["pg_ctl", "-D", str(data), "-m", "immediate", "-w", "stop"],
                       check=True, capture_output=True)


def test_rebuild_precedes_refresh_and_matching_start_is_noop(database):
    assert database("-c", "CREATE TABLE example (value text PRIMARY KEY);").returncode == 0
    before = database("-c", "SELECT relfilenode FROM pg_class WHERE relname='example_pkey'").stdout
    assert database("-c", "UPDATE pg_database SET datcollversion='old' WHERE datname=current_database()").returncode == 0
    result = database("-f", str(SQL))
    assert result.returncode == 0, result.stderr
    after = database("-c", "SELECT relfilenode FROM pg_class WHERE relname='example_pkey'").stdout
    assert before != after
    assert database("-c", "SELECT datcollversion IS NOT DISTINCT FROM pg_database_collation_actual_version(oid) FROM pg_database WHERE datname=current_database()").stdout.strip() == "t"
    assert database("-f", str(SQL)).returncode == 0
    assert database("-c", "SELECT relfilenode FROM pg_class WHERE relname='example_pkey'").stdout == after


def test_rebuild_failure_does_not_refresh_version(database):
    assert database("-c", "CREATE ROLE guest; UPDATE pg_database SET datcollversion='old' WHERE datname=current_database()").returncode == 0
    result = database("-f", str(SQL), options={"PGOPTIONS": "-c role=guest"})
    assert result.returncode != 0
    assert database("-c", "SELECT datcollversion FROM pg_database WHERE datname=current_database()").stdout.strip() == "old"


def test_gc02_repairs_before_local_application_setup_only():
    contract = eval_json('''
      let f = builtins.getFlake "__LUXNIX_FLAKE_URI__";
          c = f.nixosConfigurations.gc-02.config;
      in {
        enabled = c.roles.postgres.default.automaticCollationRepair;
        other = f.nixosConfigurations.gc-10.config.roles.postgres.default.automaticCollationRepair;
        requires = c.systemd.services.postgres-endoreg-setup.requires;
        repair = { inherit (c.systemd.services.postgresql-collation-repair) after serviceConfig; };
      }
    ''')
    assert contract["enabled"] and not contract["other"]
    assert "postgresql-collation-repair.service" in contract["requires"]
    assert "postgresql-setup.service" in contract["repair"]["after"]
    assert contract["repair"]["serviceConfig"]["User"] == "postgres"


@pytest.mark.parametrize("object_sql", [
    "CREATE MATERIALIZED VIEW cached AS SELECT 'text'::text AS value",
    "CREATE TABLE partitioned (id integer, label text) PARTITION BY RANGE (id, label)",
])
def test_non_index_dependencies_require_review(database, object_sql):
    assert database("-c", object_sql).returncode == 0
    assert database("-c", "UPDATE pg_database SET datcollversion='old' WHERE datname=current_database()").returncode == 0
    result = database("-f", str(SQL))
    assert result.returncode != 0
    assert "requires review" in result.stderr
    assert database("-c", "SELECT datcollversion FROM pg_database WHERE datname=current_database()").stdout.strip() == "old"
