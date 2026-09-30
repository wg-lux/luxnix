# Clinical Guide: Sending Anonymized Data to the Central Hub

This guide is for physicians, study nurses, clinical researchers, and other
authorized personnel who have not used a distributed data-transfer system
before. It explains the normal workflow without requiring command-line or
server-administration knowledge.

The current LuxNix deployment sends approved data from the local study server
`gc-02` to the central hub `gs-02`.

## The short version

For normal daily work:

1. Sign in to lx-annotate on the local study server.
2. Finish and validate anonymization.
3. Finish the required video segment review, when the resource is a video.
4. Open **Hub Export** (`/hub-export`).
5. Confirm that the destination is **gs-02**.
6. Review the privacy summary and the resource's status.
7. Select only the intended resource.
8. Choose **Für Hub markieren**.
9. Wait for the status to become `completed`.

Marking an item starts the transfer automatically. Clinical users do not copy
files, manage certificates, enter server passwords, or start services.

## What the system protects

The system is designed so that:

- raw clinical media cannot be exported;
- only processed media that passed the required validation gates is eligible;
- the local and central servers authenticate each other with mTLS;
- the connection is encrypted while data is travelling;
- processed media is encrypted with a fresh per-transfer data-encryption key;
- only the hub's X25519 recipient private key can unwrap that transfer key;
- the central hub independently authenticates the sending node;
- data stays inside encrypted storage on each server;
- failed or inconsistent transfers stop and retain an audit trail;
- no long-lived application master key is transmitted.

The current transfer combines mTLS over HTTPS with payload envelope encryption.
The sender encrypts processed media with a fresh data-encryption key, wraps that
key to the hub's X25519 public recipient key, and requires a matching typed
receipt from the hub. The hub recipient private key and both nodes' long-lived
application master keys are never transmitted.

## Roles and responsibilities

### Clinical user

The clinical user:

- completes the clinical workflow;
- validates anonymization;
- verifies that the displayed resource is the intended one;
- considers the displayed privacy warning;
- marks an eligible resource for transfer;
- checks that the transfer completes;
- reports failures without trying to bypass them.

### Privacy or study lead

The privacy or study lead defines when a cohort is appropriate to export. A
technical `eligible` status means that the media passed the application's
required processing gates. It does not replace the study protocol, consent,
data-use agreement, or local privacy review.

The **K-Anonymität** panel is advisory in the current interface. If it says
**nicht ausreichend** or **nicht berechenbar**, stop and obtain approval from
the privacy or study lead. Do not treat the enabled transfer button as privacy
approval.

### System administrator

The administrator maintains VPN access, server configuration, Vault, mTLS
certificates, node enrollment, services, and incident logs. Clinical users
should never receive or handle Vault recovery material, private keys, node
secrets, or the application master key.

## One-time workstation setup for a clinical user

Ask the local administrator to provide:

- an approved workstation;
- access to the LuxNix VPN or clinical network;
- an lx-annotate/Keycloak account;
- the roles required for the clinical workflow and Hub Export page;
- the local lx-annotate web address;
- the local support contact and incident procedure.

Then complete this check once:

1. Connect the workstation to the approved network or VPN.
2. Open the local lx-annotate address in the managed browser.
3. Sign in with the assigned personal account.
4. Confirm that the expected center is shown.
5. Open **Hub Export** and confirm that **Hub-Ziel** contains one destination,
   `gs-02`.
6. If **Konfiguration unvollständig** appears, stop and contact the
   administrator.

Do not share accounts. The audit record associates transfer marking with the
authenticated user.

## Before a resource can be transferred

### Video

A video becomes eligible only when all of the following are true:

- anonymization is validated;
- a non-empty processed video exists;
- required segment annotation and review are final;
- any required outside-segment cleanup has completed successfully;
- the video state is ready for export;
- the processed-file SHA-256 integrity value is recorded.

### Report

A report becomes eligible only when:

- anonymization is validated;
- a non-empty processed report exists;
- the processed-file integrity state is valid when a hash is required.

If a checkbox is disabled, do not try to work around it. Read the **Hinweis**
column and return to the named workflow step.

## Daily transfer workflow

### 1. Complete the resource workflow

Finish processing and validation in lx-annotate. For videos, anonymization
validation and segment validation are separate gates; completing one does not
complete the other.

### 2. Open Hub Export

Open **Hub Export** from the application navigation or visit `/hub-export` on
the local server.

The page is labelled in German:

| Screen label | Meaning |
| --- | --- |
| **Hub-Ziel** | Destination hub; normally `gs-02` |
| **Aktualisieren** | Refresh the displayed state |
| **Für Hub markieren** | Approve the selected eligible items for transfer |
| **Markierung entfernen** | Cancel a transfer that has only been marked and has not progressed |
| **Processed Media** | Whether an anonymized processed artifact exists |
| **Markiert** | Whether a transfer job exists for this resource |
| **Status** | Current transfer stage |
| **Hinweis** | Blocking reason or most recent error |

### 3. Confirm the destination and privacy information

Confirm all of the following before selecting a resource:

- **Hub-Ziel** is `gs-02`;
- no configuration warning is displayed;
- the correct center is shown;
- the file and resource type are the intended ones;
- anonymization says **Validiert**;
- **Processed Media** says **Ja**;
- the privacy summary is acceptable under the study protocol.

If more than one hub is displayed, or the destination can be changed to an
unexpected node, stop and contact the administrator. Normal sender mode is
configured for exactly one active central hub.

### 4. Mark the resource

Select the checkbox beside the intended resource and choose **Für Hub
markieren**.

On `gc-02`, marking an eligible resource automatically queues it. Do not upload
the same file manually and do not create a second copy to retry the operation.
The transfer workflow is idempotent and has its own bounded retry process.

### 5. Monitor the status

Choose **Aktualisieren** to see the latest state.

| Status | What it means | What the user should do |
| --- | --- | --- |
| `marked` | Approved for transfer but not yet queued | Wait briefly, then refresh |
| `queued` | Waiting for the transfer worker | Wait and refresh |
| `registering` | Creating or confirming the job at gs-02 | Wait; do not mark it again |
| `awaiting_media` | gs-02 accepted the metadata and expects processed media | Wait |
| `uploading` | Processed bytes are travelling over the mTLS connection | Keep the local server online |
| `completed` | gs-02 accepted the transfer and confirmed its state | Record completion according to the study procedure |
| `failed` | The transfer stopped safely | Follow the failure procedure below |

`completed` is the only normal success state. A missing source file, a browser
refresh, or a disappeared row is not proof that the hub received the data.

## If no resources are available

The message **Keine exportierbaren Ressourcen** usually means that no item has
passed every eligibility gate yet. It is not normally a network error.

Check:

1. Was anonymization explicitly validated?
2. Does processed media exist?
3. For video, was segment review finalized?
4. Did required cleanup finish without an error?
5. Does the **Hinweis** column name a missing step?

If all clinical steps appear complete, contact support and provide the resource
identifier and the exact displayed message. Do not include patient names or
other identifying data in ordinary email or chat.

## Failure procedure

When a status says `failed`:

1. Do not delete or rename the local resource.
2. Do not copy the file to gs-02 manually.
3. Do not disable anonymization or certificate checks.
4. Record the time, resource identifier, displayed status, and **Hinweis** text.
5. Contact the local administrator through the approved channel.
6. Wait for the administrator to confirm whether automatic recovery will retry
   the existing job.

The system retries stale or retryable jobs a bounded number of times. Reusing
the existing transfer identity avoids duplicate hub records.

Escalate immediately to the privacy or security contact if the screen appears
to offer raw media, the wrong center, the wrong hub, or patient-identifying
information that should have been removed.

## Actions clinical personnel must never take

- Never export raw video or raw reports.
- Never use removable media, personal cloud storage, email, or chat to move a
  resource between nodes.
- Never accept a browser certificate warning.
- Never ask for or store mTLS private keys, Vault tokens, recovery shares, node
  secrets, or application master keys.
- Never restart servers or unseal Vault unless this is an assigned
  administrator responsibility.
- Never delete local media merely because a transfer appears to have started.
- Never interpret technical eligibility as consent or governance approval.

## Administrator handoff checklist

Before telling clinical personnel that Hub Export is ready, the administrator
should confirm:

- gc-02 and gs-02 are on their intended persistent LuxNix system profiles;
- Vault on gs-02 is initialized and unsealed;
- the gc-02 Vault AppRole and mTLS client certificate are valid;
- the gs-02 client CA publisher, nginx, Django, and PostgreSQL are active;
- the gc-02 lx-annotate service, local Redis, and dedicated `hub_transfer`
  worker are active;
- the worker reports connected to `redis://localhost:6379/1` and ready;
- gs-02 contains the active gc-02 `NetworkNode` with a hashed request secret;
- an authenticated mTLS preflight reaches the hub without an OIDC redirect;
- the Hub Export page names exactly one central destination, gs-02;
- the clinical user has received no infrastructure secret.

Useful non-secret service checks are:

```bash
# On gc-02
systemctl is-active \
  lx-annotate.service \
  lx-annotate-celery-hub-transfer-worker.service \
  lx-annotate-hub-node-provisioning.service \
  redis-lx-annotate.service

# On gs-02
systemctl is-active \
  vault.service \
  luxnix-vault-publish-hub-client-ca.service \
  nginx.service \
  postgresql.service \
  lx-annotate.service \
  lx-annotate-hub-node-provisioning.service
```

If Vault is sealed after a restart, an authorized custodian must follow the
approved recovery ceremony. Never place an unseal share on gs-02 beside Vault's
Raft storage.

## What happens behind the screen

The simplified path is:

```text
validated processed resource on gc-02
  -> dedicated hub-transfer worker
  -> per-transfer encrypted media envelope
  -> Python requests streaming multipart HTTPS with mTLS
  -> VPN network
  -> nginx on gs-02 verifies the mTLS client certificate
  -> Django verifies the gc-02 node key and request secret
  -> gs-02 unwraps the transfer key, authenticates and applies the media
  -> sender validates the typed envelope receipt
```

The browser does not carry the clinical payload to gs-02. It only records the
authorized user's decision to mark an eligible resource. The server-side worker
sends the bytes.

## Technical references

- [lx-annotate secure HLS and hub security boundary](./lx-annotate-secure-hls.md)
- [lx-annotate encrypted data](./lx-annotate-encrypted-data.md)
- [LuxNix Vault-backed transfer implementation](https://github.com/wg-lux/luxnix/blob/main/modules/nixos/services/lx-annotate-local/README.md#vault-backed-transfer-pki)
