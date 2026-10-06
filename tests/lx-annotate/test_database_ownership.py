"""Evaluate database ownership independently of endpoint spelling and hub hostname."""

import pytest

from nix_eval_helpers import eval_json


@pytest.fixture(scope="module")
def contracts():
    return eval_json("""
      let
        flake = builtins.getFlake "__LUXNIX_FLAKE_URI__";
        base = flake.nixosConfigurations.gc-10;
        extend = module: base.extendModules { modules = [ module ]; };
        inspect = system: let
          c = system.config;
          d = c.services.luxnix.lxAnnotateLocal.database;
          env = c.systemd.services.lx-annotate.environment;
        in {
          database = { inherit (d) ownership host port name user; };
          aiDatabase = c.services.luxnix.lxAiLocal.database;
          inherit (c.services.luxnix.lxAnnotateLocal.hub) enable;
          localPostgres = c.services.postgresql.enable;
          runtimeAfter = c.systemd.services.lx-annotate-runtime-env.after;
          runtimeRequires = c.systemd.services.lx-annotate-runtime-env.requires;
          migrateAfter = c.systemd.services.lx-annotate-migrate.after;
          environment = {
            inherit (env) DJANGO_DB_HOST DJANGO_DB_PORT DJANGO_DB_NAME DJANGO_DB_USER;
          };
          optionTypes = builtins.mapAttrs (_: o: o.type.name)
            (builtins.removeAttrs
              (system.options.services.luxnix.lxAnnotateLocal.database.type
                .getSubOptions []) [ "_module" ]);
          failures = map (a: a.message) (builtins.filter
            (a: !a.assertion
              && flake.inputs.nixpkgs.lib.hasPrefix "LX-Annotate " a.message)
            c.assertions);
        };
        external = {
          services.luxnix.lxAnnotateLocal.runtime.externalServices = {
            postgresHost = "postgres.example.internal";
            postgresPort = 6543;
          };
        };
      in {
        client = inspect base;
        gpuHub = inspect flake.nixosConfigurations.gs-02;
        remoteHub = inspect flake.nixosConfigurations.s-04;
        remoteGpu = inspect flake.nixosConfigurations.gs-01;
        gc02 = inspect flake.nixosConfigurations.gc-02;
        direct = inspect (extend ({lib,...}: {
          roles.endoreg-client.enable = lib.mkForce false;
          services.luxnix.lxAnnotateLocal.enable = true;
        }));
        remote = inspect (extend external);
        customRole = inspect (extend {
          roles.endoreg-client.database = { host = "custom.internal"; port = 6544; };
          services.luxnix.lxAnnotateLocal.database.ownership = "external";
        });
        serviceOverride = inspect (extend {
          services.luxnix.lxAnnotateLocal.database = {
            ownership = "external"; host = "custom.internal"; port = 6544;
          };
        });
        directExternal = inspect (extend ({lib,...}: {
          imports = [ external ];
          roles.endoreg-client.enable = lib.mkForce false;
          services.luxnix.lxAnnotateLocal.enable = true;
        }));
        externalLoopback = inspect (extend {
          services.luxnix.lxAnnotateLocal.database.ownership = "external";
        });
        managedLoopbackAlias = inspect (extend {
          services.luxnix.lxAnnotateLocal = {
            database.ownership = "local";
            runtime.externalServices.postgresHost = "127.0.0.1";
          };
        });
        serviceConflict = inspect (extend {
          imports = [ external ];
          services.luxnix.lxAnnotateLocal.database.host = "different.example.internal";
        });
        roleConflict = inspect (extend {
          imports = [ external ];
          roles.endoreg-client.database.host = "different.example.internal";
        });
        portConflict = inspect (extend {
          imports = [ external ];
          services.luxnix.lxAnnotateLocal.database.port = 6544;
        });
        wrongLocalName = inspect (extend {
          roles.endoreg-client.database.name = "not_provisioned";
        });
        wrongLocalPort = inspect (extend {
          roles.endoreg-client.database.port = 6544;
        });
        wrongLocalCredential = inspect (extend ({lib,...}: {
          roles.endoreg-client.enable = lib.mkForce false;
          services.luxnix.lxAnnotateLocal = {
            enable = true;
            database.endoregLocalUserPasswordFile = "/run/secrets/unmanaged-db";
          };
        }));
        missingLocalProvisioner = inspect (extend ({lib,...}: {
          roles.postgres.default.enable = lib.mkForce false;
        }));
        remoteOwnedLocally = inspect (extend {
          imports = [ external ];
          services.luxnix.lxAnnotateLocal.database.ownership = "local";
        });
        renamedHub = inspect (extend ({lib,...}: {
          networking.hostName = lib.mkForce "ownership-test-hub";
          profiles.endoregCentralHub.enable = true;
          roles.postgres.default.defaultDbName = "endoregDbCentral";
        }));
      }
    """)


@pytest.mark.parametrize(
    "case", ["client", "direct", "gc02", "gpuHub", "managedLoopbackAlias", "renamedHub"]
)
def test_local_ownership_requires_provisioning_before_runtime(contracts, case):
    result = contracts[case]
    assert result["failures"] == []
    assert result["database"]["ownership"] == "local"
    assert "postgres-endoreg-setup.service" in result["runtimeAfter"]
    assert "postgres-endoreg-setup.service" in result["runtimeRequires"]
    assert "postgresql.service" in result["migrateAfter"]


@pytest.mark.parametrize(
    "case", ["remote", "externalLoopback", "remoteHub", "remoteGpu"]
)
def test_external_ownership_does_not_depend_on_local_postgres(contracts, case):
    result = contracts[case]
    assert result["failures"] == []
    assert result["database"]["ownership"] == "external"
    assert "postgres-endoreg-setup.service" not in result["runtimeRequires"]
    assert "postgresql.service" not in result["migrateAfter"]
    # The fleet still provisions PostgreSQL for other consumers.
    assert result["localPostgres"] is True


def test_legacy_endpoint_aliases_reach_application_environment(contracts):
    assert contracts["remote"]["environment"] == {
        "DJANGO_DB_HOST": "postgres.example.internal",
        "DJANGO_DB_PORT": "6543",
        "DJANGO_DB_NAME": "endoregDbLocal",
        "DJANGO_DB_USER": "endoregDbLocal",
    }


@pytest.mark.parametrize(
    "case,fragment",
    [
        ("serviceConflict", "database.host conflicts"),
        ("roleConflict", "database.host conflicts"),
        ("portConflict", "database.port conflicts"),
        ("wrongLocalName", "managed-local database"),
        ("wrongLocalPort", "managed-local database"),
        ("wrongLocalCredential", "managed-local database"),
        ("missingLocalProvisioner", "requires the local PostgreSQL role"),
        ("remoteOwnedLocally", "requires a local database.host"),
    ],
)
def test_inconsistent_database_configuration_is_rejected(contracts, case, fragment):
    assert any(fragment in message for message in contracts[case]["failures"])


def test_hub_profile_is_independent_of_hostname(contracts):
    assert contracts["renamedHub"]["enable"] is True
    assert contracts["client"]["enable"] is False
    assert contracts["gpuHub"]["enable"] is True
    assert contracts["remoteHub"]["enable"] is True


def test_direct_service_defaults_match_local_provisioning(contracts):
    assert contracts["direct"]["database"] == {
        "ownership": "local",
        "host": "localhost",
        "port": 5432,
        "name": "endoregDbLocal",
        "user": "endoregDbLocal",
    }


@pytest.mark.parametrize("case", ["customRole", "serviceOverride"])
def test_centralized_endpoint_resolution_preserves_overrides(contracts, case):
    assert contracts[case]["failures"] == []
    assert contracts[case]["environment"]["DJANGO_DB_HOST"] == "custom.internal"
    assert contracts[case]["environment"]["DJANGO_DB_PORT"] == "6544"


def test_direct_service_keeps_aliases_and_existing_option_types(contracts):
    assert contracts["directExternal"]["failures"] == []
    assert (
        contracts["directExternal"]["environment"] == contracts["remote"]["environment"]
    )
    assert contracts["direct"]["optionTypes"] == {
        "ownership": "enum",
        "host": "str",
        "port": "unsignedInt16",
        "name": "str",
        "user": "str",
        "applicationPasswordFile": "path",
        "sslMode": "str",
        "endoregLocalUserPasswordFile": "path",
    }


def test_lx_ai_preserves_client_database_and_application_credential(contracts):
    database = contracts["customRole"]["aiDatabase"]
    assert (database["host"], database["port"]) == ("custom.internal", 6544)
    assert (
        database["applicationPasswordFile"]
        == "/var/lib/postgresql/endoregDbLocal.password"
    )
    assert database["sslMode"] == "prefer"


def test_password_names_preserve_alias_priority_and_reject_ambiguity():
    assert eval_json("""
      let
        f = builtins.getFlake "__LUXNIX_FLAKE_URI__";
        lib = f.inputs.nixpkgs.lib; o = f.nixosConfigurations.gc-10.options;
        check = option: let
          read = values: (lib.evalModules {
            modules = option.type.getSubModules ++ [ { config = values; } ];
          }).config.applicationPasswordFile;
          old = { endoregLocalUserPasswordFile = "/run/secrets/app"; };
          canonical = value: { applicationPasswordFile = value; };
          accepts = values: (builtins.tryEval (read values)).success;
        in [
          (read old == "/run/secrets/app")
          (read (canonical "/run/secrets/app") == read old)
          (read (old // canonical (lib.mkForce "/new")) == "/new")
          (!accepts (old // canonical "/other"))
          (!accepts { passwordFile = "/run/secrets/maintenance"; })
        ];
      in map check [ o.roles.endoreg-client.database
        o.services.luxnix.lxAnnotateLocal.database
        o.services.luxnix.lxAiLocal.database ]
    """) == [[True] * 5] * 3
