# Activation failure recovery

**Schema version:** 1

**Scope:** NixOS activation failures involving NVIDIA CDI and Vault hub client certificates

## Nvidia driver mismatch

### Evidence

- NVIDIA CDI reports 'Driver/library version mismatch'.
- The loaded NVIDIA module version differs from the incoming userspace driver.

### Inspect

- cat /sys/module/nvidia/version
- nvidia-smi
- readlink -f /run/current-system
- readlink -f /run/booted-system

**Prevention:** The shared GPU configuration checks the loaded module before live activation. A driver version change requires staging for boot and a maintenance reboot. This check also catches an already partially activated driver update.

### Recovery

- Verify the target host, reviewed revision, locked inputs, and clean source tree.
- Build and validate that exact configuration using the canonical project workflows.
- With operator authorization, stage it using nixos-rebuild boot and reboot the selected host.
- Verify nvidia-smi and nvidia-container-toolkit-cdi-generator.service after boot.

**Caution:** A failed test activation may already have changed /run/current-system without selecting that generation for the next boot. Do not assume a reboot alone will select the intended generation. Do not suppress CDI failure or unload in-use GPU modules to make activation appear successful.

## Vault client certificate

### Evidence

- A certificate requiring renewal triggers fresh AppRole authentication.
- Authentication failure is classified without logging raw Vault responses or credentials.

### Inspect

- luxnix-vault-enrollment-status
- journalctl -b -u luxnix-vault-issue-hub-client-certificate.service --no-pager

### Recovery by state

**`tls-trust-failed`:** Verify the configured CA and server leaf through the authenticated CA workflow.

**`vault-sealed`:** Ask the Vault custodian to unseal the server through the documented procedure.

**`vault-unreachable`:** Restore the configured VPN, DNS, and Vault connectivity.

**`auth-rejected`:** Use the documented site-specific AppRole recovery or rotation workflow.

**`vault-error`:** Inspect enrollment status; the error has not established a specific cause.

**Runbook:** `docs/vault-hub-machine-enrollment.md`

**Completion:** After authorized recovery, reissue the certificate using the documented workflow and verify receiver acceptance. Source changes cannot repair expired or revoked enrollment credentials. Do not bypass TLS or accept expired certificates.
