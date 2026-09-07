# lx-annotate Secure HLS: Architecture, Operations, and Incident Response

This document is the end-to-end production contract for encrypted video
playback in an lx-annotate deployment. It connects the implementation spread
across `endoreg-db`, `lx-annotate`, and LuxNix and explains what an operator must
verify before video playback is considered ready.

The production contract is deliberately narrow:

- browser playback uses authenticated HLS, not progressive MP4
- raw and processed video are materialized for local encrypted HLS playback
- raw clinical media is never eligible for hub export
- a successful dispatcher unit means work was queued, not that every video is
  ready
- a frontend source build is not deployed until it is packaged in the runtime
  wheel and that wheel is selected by the host configuration

## Why the migration was necessary

The old browser contract assigned a video stream URL directly to a `<video>`
element and expected a progressively playable media file. The backend contract
now redirects legacy video URLs to an HLS playlist. The response MIME type
`application/vnd.apple.mpegurl` is therefore correct, but Firefox cannot consume
that manifest through a plain `<video src>` assignment.

The production frontend must use Hls.js, or native HLS where the browser safely
supports it, so that the player can fetch the playlist, AES key, and individual
segments. Those requests must carry the authenticated browser session. The
shared player also validates that the playlist is same-origin, has an HLS MIME
type, and starts with `#EXTM3U` before attaching it to a media element.

This is why the observed browser message:

```text
HTTP Content-Type of application/vnd.apple.mpegurl is not supported
```

did not indicate a bad backend MIME type. It indicated that an old frontend
still treated an HLS manifest as a directly playable MP4-like resource.

## End-to-end lifecycle

```text
clinical source
  -> encrypted import storage
  -> raw-file and anonymized processed-file validation
  -> raw and processed HLS materialization
       -> AES-128 encrypted MPEG-TS segments
       -> playlist containing authenticated key and segment URLs
       -> content key wrapped by the application master key
       -> VideoHlsArtifact status = ready
  -> authenticated Django playlist/key/segment authorization
  -> Nginx X-Accel-Redirect for authorized file delivery
  -> same-origin Hls.js/native-HLS browser playback
```

Hub transfer is a separate data plane:

```text
eligible anonymized processed file
  -> explicit upload authorization and durable transfer ledger
  -> TLS + client certificate + node request secret
  -> central-hub transfer API
  -> verified apply and conservative local cleanup policy
```

The hub does not receive the local HLS content key or an HLS playback bundle.
It receives only the eligible anonymized processed media defined by the hub
transfer contract.

## Import and readiness contract

For new imports, raw and processed HLS readiness are part of successful video
finalization. `endoreg-db` materializes both kinds synchronously after the
source and anonymized output are attached. A materialization error propagates
to the import workflow, leaving the import retryable instead of publishing a
successful but partially unstreamable video.

This produces the following invariant:

> A newly finalized video import must not be reported as successful unless its
> raw and processed HLS artifacts are ready.

Legacy processed videos predate that invariant. LuxNix provides dispatchers to
backfill them through the dedicated `ffmpeg_media` Celery queue:

- `lx-annotate-hls-backfill.service` runs automatically at boot when enabled
- `lx-annotate-hls-materialization.service` is the manual dispatcher
- `lx-annotate-celery-ffmpeg-worker.service` performs the actual transcoding

Both dispatcher units run `materialize_video_hls --apply --json` for raw and
processed artifacts by default. The wrapper accepts an explicit `--artifact-kind
raw`, `processed`, or `both`, but rejects unsupported artifact kinds,
`--force`, and `--inline`. Force and inline repair runs require an explicit,
audited management command outside the normal service path.

### State meanings

| State or result | Meaning | Production interpretation |
| --- | --- | --- |
| `queued` | A Celery task was accepted by the `ffmpeg_media` queue. | Not playable yet. |
| `materializing` | A worker owns an in-progress artifact record. | Not playable yet. A duplicate dispatcher must not start a second transcode. |
| `ready` / `already_ready` | Database metadata, playlist, segments, and wrapped key identify a complete artifact. | Eligible for the playback API. |
| `failed` | Transcoding, source decryption, validation, publication, or cleanup failed. | Not playable; inspect `last_error` and the worker journal. |
| systemd oneshot `Finished` | Selection and dispatch completed successfully. | It does **not** mean queued Celery tasks completed. |

The automatic backfill starts after the web unit, encrypted-storage preflight,
and FFmpeg worker, with the local Redis service required when configured.
Neither the web unit nor preflight depends on the corpus scan: slow or failed
reconciliation must not hold the frontend offline. The recurring timer retries
deferred scans, including scans skipped while imports are active. A database or
runtime error in that check fails the unit instead of silently skipping it. Systemd worker
startup ordering does not prove broker connectivity or task completion; web
startup does not prove that the legacy backlog has drained. The production
readiness check remains the launch gate.

External archive storage uses the host-owned
`roles.endoreg-client.paths.storagePersistingDeviceId` (the verified
`/dev/disk/by-id` basename without partition suffix) and
`storagePersistingDevicePart` options. These propagate the same identity to the
mount unit and emergency-relief verifier. Development `secretspec` values are
compatibility defaults, not a production provisioning mechanism. Missing device
identity, an unavailable disk, a mount failure, or a mounted device-number
mismatch fails the mount unit. A stale mount after USB reconnection must remain
untouched for operator inspection; never repair, replace, or relocate data onto
it automatically. Configure a host identity only from verified device evidence
and retain the encrypted-at-rest archive requirements.

## Artifact and encryption design

Each video has at most one `VideoHlsArtifact` record per raw or processed
artifact kind. The record tracks its lifecycle, key identifier, wrapped content key,
nonce, IV, playlist and segment paths, segment count, source name, and bounded
failure detail.

Materialization uses:

- AES-128 HLS segment encryption
- a fresh 16-byte content-encryption key
- a fresh HLS IV
- AES-GCM wrapping of the content key with the application master key
- artifact-bound additional authenticated data when wrapping the key
- H.264 High Profile, `yuv420p`, with bounded FFmpeg resource and progress
  watchdogs

The plaintext content key exists only where FFmpeg needs it during
materialization and when Django unwraps it for an authorized key request. The
database stores the wrapped key, not the plaintext content key. Temporary key
and seekable-source paths use restrictive directory/file modes and are cleaned
after use. The protected runtime root should additionally remain on the managed
LUKS volume; temporary-file cleanup is not a substitute for encrypted storage.

Published HLS artifacts live below the protected processed-video HLS root. Path
resolution is constrained to that root to prevent traversal or arbitrary file
delivery.

## HTTP playback contract

The authoritative backend permission and request-flow reference is
[`endoreg-db/docs/video_hls_permissions_and_streaming.md`](https://github.com/wg-lux/endoreg-db/blob/HEAD/docs/video_hls_permissions_and_streaming.md).
It documents the current Keycloak-to-Django role synchronization, compatibility
roles, `PortalUserInfo → Examiner → Center` provisioning requirement, masked
center-scope `404` behavior, and each playlist/key/segment gate.

### Operator role model

Keycloak realm roles are the source of truth for technical permissions. On
each successful login they are copied by exact name into local Django groups;
the previous synchronized memberships are replaced. Keycloak group names are
not permissions by themselves. A group named `video_group`, for example, must
map realm roles such as `video:read` into the token.

The current frontend has a global `endoregdb_user` gate. Thus a normal browser
user currently needs all of the following:

```text
Keycloak: endoregdb_user
Keycloak: explicit workflow roles such as video:read
local DB: PortalUserInfo -> Examiner -> Center assignment
```

`endoregdb_user` is a broad compatibility role that also satisfies every
ordinary backend route role. The explicit workflow roles document intended
access but do not make that compatibility role least-privileged. The stricter
`center_scope:admin` role is checked by exact name and is not implied by
`endoregdb_user` or `data:write`.

Local records are node-specific. A user must log into each independent node
once, and center assignments and Django superuser promotion must be performed
separately on each node. A gc-02 promotion does not promote gc-10. Keycloak role
changes take effect after a fresh successful login; manual edits to synchronized
Django groups are unsupported because the next login replaces them.

The complete role catalogue, compatibility hierarchy, decision examples, and
administrative invariants are maintained in the authoritative backend contract
linked above.

The canonical local playlist URLs are:

```text
/endoreg-api/media/videos/<video-id>/hls/playlist.m3u8?type=processed
/endoreg-api/media/videos/<video-id>/hls/playlist.m3u8?type=raw
```

The compatibility endpoints:

```text
/endoreg-api/media/videos/<video-id>/stream/
/endoreg-api/media/videos/<video-id>/
```

redirect to that processed playlist. Legacy query parameters do not restore
progressive playback. In particular, `stream/?type=raw` still redirects to the
processed HLS playlist.

| Resource | MIME type | Cache policy | Delivery path |
| --- | --- | --- | --- |
| Playlist | `application/vnd.apple.mpegurl` | `no-store, private` | Django authorization, optionally followed by protected Nginx offload |
| Content key | `application/octet-stream` | `no-store, private` | Django unwraps and returns it only after authorization |
| Segment | `video/mp2t` | `private, max-age=31536000, immutable` | Django authorization followed by Nginx `X-Accel-Redirect` |

Every endpoint performs environment-aware authentication, policy permission
checks, video lookup, and center-scope authorization. Key and segment URLs bind
the key identifier to the requested video. Responses use
`X-Content-Type-Options: nosniff`. CORS is added only for an explicitly resolved
frontend origin; the expected production topology is same-origin.

Segments fail closed when protected Nginx offload is not configured. Nginx does
not make the authorization decision: Django first validates the request and
then hands the already-authorized path to an internal location.

## Frontend playback contract

All Vue views that display production video must use the shared authenticated
stream composable. They must not bind a legacy stream URL directly with
`<video src>`.

The shared player:

- builds the canonical HLS playlist URL from the actual `VideoFile` identifier
- rejects cross-origin and non-HTTP(S) media URLs
- preflights the playlist with the credentialed Axios instance
- validates both the response MIME type and `#EXTM3U` signature
- configures Hls.js XHR requests with credentials for playlist, key, and
  segments
- uses native credentialed HLS only when the browser reports support
- bounds back-buffer and forward-buffer growth
- makes one Hls.js media-error recovery attempt
- aborts stale preflight requests and destroys Hls.js on source change or
  component unmount
- clears the media source so buffered decrypted video is released when the view
  is left
- fails closed; it does not silently fall back to progressive plaintext media

Expected frontend error classes distinguish authentication failure (`401`),
authorization failure (`403`), artifact unavailability (`404`), invalid
playlist responses, transport failure, and fatal playback failure. Operators
should preserve that distinction when reporting an incident.

### Raw-video boundary

The backend permits raw HLS only as protected local-node playback. Raw and
processed requests pass the same authentication, `video:read`, center-scope,
artifact binding, key wrapping, and protected Nginx gates. Raw artifacts live
below the protected raw-media HLS root and are not public files.

This local playback contract:

- cannot be enabled on a central hub
- cannot make raw media hub-transfer eligible
- preserves the same authentication, center scope, protected storage, key
  wrapping, Nginx authorization, and audit properties
- remains distinct from the anonymized hub-export data plane

## Known gaps before a production-grade assertion

The following items are visible in the current cross-repository state and must
not be lost in a successful-path report:

1. **Center scope remains a separate clinical assignment.** OIDC synchronizes
   users and roles but does not silently grant a center. An exact
   `center_scope:admin` administrator uses the audited Administration workflow;
   global superusers may transactionally provision an incomplete local
   `PortalUserInfo → Examiner` relationship.
2. **Sensitive frontend diagnostics remain.** Current frontend source contains
   console statements that can log sensitive-metadata objects, patient-facing
   payloads, video identifiers, and API responses. The reported production
   console also exposed request headers including a CSRF token. These logging
   paths must be removed or replaced with a production-safe structured
   telemetry policy, and the compiled production bundle must be inspected to
   confirm the values are absent.
3. **Source and deployed assets can diverge in wheel mode.** A passing local
   frontend build does not correct a host that still serves an older wheel.
   The new bundle must be packaged, selected in LuxNix, deployed, and verified
   on the target host.
4. **Backfill success is asynchronous.** Legacy videos in `failed` or
   `materializing` state remain unavailable even after the dispatcher unit
   exits successfully. Every eligible raw and processed video must pass the readiness
   gate after worker completion.
5. **Envelope encryption is release- and deployment-gated.** Current source
   encrypts each processed-media payload with a fresh data-encryption key,
   wraps that key to the hub's X25519 recipient key, and validates the hub's
   typed receipt. Every deployed sender and receiver must run a compatible
   release and pass the envelope-key preflight; a source-only implementation or
   stale wheel is not production evidence.

Until items 1 through 5 are resolved for the deployed release, source-level
readiness must not be represented as deployed clinical readiness.

## Hub transfer security boundary

HLS browser delivery and inter-node hub transfer solve different problems and
must not share an implicit trust decision.

Site-node outbound transfer is enabled separately with
`hub.outboundTransfer.enable`. LuxNix refuses the configuration unless the node:

- has deployment role `site_node`
- requires mTLS
- supplies a client certificate and private key outside the Nix store
- supplies a source-node request secret outside the Nix store
- optionally pins the private CA used to validate the hub

The sender validates eligibility before network I/O, transfers only explicitly
marked anonymized processed media, verifies the hub certificate, presents its
client certificate, refuses redirects, authenticates with the separate node
secret, uses deterministic transfer identity, and records retryable progress in
a durable ledger.

On the receiving side, Nginx verifies the client certificate and forwards a
verification attestation to Django. Django independently checks the configured
mTLS attestation and `NetworkNode` shared-secret authentication. Neither signal
replaces the other.

Current hub transfer uses both TLS/mTLS and payload-level envelope encryption.
The sender creates a fresh data-encryption key per transfer, encrypts only
eligible processed media, wraps the data key to the hub's X25519 public
recipient key, and requires the hub's typed receipt. The corresponding private
recipient key remains on the hub. Envelope encryption does not replace
destination storage encryption, certificate lifecycle, CA protection, secret
rotation, request logging policy, or the hub's own access controls.

## Deployment contract

A local frontend build is not a deployment. Wheel-mode hosts serve the static
assets packaged with the selected lx-annotate wheel. To make an HLS frontend
fix live:

1. Run the frontend type checks, focused tests, and production build from the
   lx-annotate flake environment.
2. Build a new lx-annotate wheel containing the resulting static assets.
3. Publish or otherwise make that immutable wheel available to LuxNix.
4. Update `runtime.wheelPath` and the package version/hash expected by the host.
5. Rebuild the target host.
6. Confirm the runtime installed the intended wheel and synchronized its static
   assets.
7. Drain or materialize the legacy HLS backlog.
8. Run the production acceptance/readiness checks.
9. Test an authorized and an unauthorized browser session.

Rebuilding only `/home/admin/dev/lx-annotate/frontend` does not change the
bundle served from a wheel-mode production host.

## Production runbook

### 1. Inspect the service chain

```bash
systemctl status lx-annotate.service
systemctl status lx-annotate-master-key-check.service
systemctl status lx-annotate-celery-ffmpeg-worker.service
systemctl status nginx.service
```

The web service and FFmpeg worker must have passed the same encrypted-storage,
runtime-environment, migration, base-data, and master-key gates.

### 2. Dispatch legacy materialization

For the configured automatic boot dispatcher:

```bash
systemctl status lx-annotate-hls-backfill.service
journalctl -u lx-annotate-hls-backfill.service -b --no-pager
```

For an explicit bounded/manual run:

```bash
sudo systemctl start lx-annotate-hls-materialization.service
journalctl -u lx-annotate-hls-materialization.service -b --no-pager
```

After deploying an `endoreg-db` release whose `materialize_video_hls` command
accepts raw artifacts, dispatch the legacy raw backlog with:

```bash
sudo runLxAnnotateHlsMaterialization --artifact-kind raw
```

Where operators intentionally have no interactive application shell, make the
same bounded run declarative for one rollout:

```nix
services.luxnix.lxAnnotateLocal.hlsBackfill.extraArgs = [
  "--artifact-kind"
  "raw"
];
```

Rebuild the host, monitor the dispatcher and `ffmpeg_media` worker to terminal
results, run the acceptance gate, then remove the temporary raw-only override
so the normal boot dispatcher returns to its processed default. Repeating a
non-forced raw run is idempotent for artifacts already in `ready` state.

Do not configure or execute this raw command against `endoreg-db==1.0.5.8`:
that published command is processed-only. Publish and select the updated wheel
first. The wrapper's processed default is retained so an existing deployment
does not begin a failing raw job during a partial rollout.

Read the JSON results as dispatch receipts. A `task_id` and `queued` result are
not completion evidence.

### 3. Observe actual worker completion

```bash
journalctl -u lx-annotate-celery-ffmpeg-worker.service -b -f
```

Correlate each dispatcher `task_id` and `video_id` with a worker terminal result.
Do not start duplicate forced work merely because the dispatcher exited.

### 4. Run the launch gate

```bash
sudo systemctl start lx-annotate-acceptance.service
systemctl status lx-annotate-acceptance.service
journalctl -u lx-annotate-acceptance.service -b --no-pager
```

The HLS readiness command checks, among other things:

- application master-key availability
- protected Nginx offload configuration
- ready raw and processed artifacts for every eligible video
- playlist, first-segment, and wrapped-key filesystem sanity
- absence of legacy streamable-path launch blockers
- serializer playback URLs resolving to HLS

Acceptance must pass after the worker backlog is complete, not immediately
after dispatch.

### 5. Verify browser behavior

In browser developer tools, verify:

- the page is serving the newly deployed hashed frontend bundle
- the initial request targets `/hls/playlist...`, not the legacy `/stream/`
  endpoint
- playlist, key, and segment requests remain same-origin and carry the session
- the response MIME types match the table above
- no media URL, content key, cookie, or clinical identifier is written to
  production console logs
- an unauthenticated user receives `401`/`403`, while an out-of-center user
  receives the deliberately masked `404`; neither receives media bytes

## Incident triage

| Symptom | Likely cause | First checks |
| --- | --- | --- |
| Browser rejects `application/vnd.apple.mpegurl` on `/stream/` | Old frontend assigned the compatibility redirect target directly to `<video src>`. | Verify deployed wheel/static bundle, then confirm the view uses the authenticated HLS composable. |
| Playlist returns `404` | Center scope denied, no ready artifact of the requested kind, or artifact files are missing. | Check assignment and requested `type` before inspecting `VideoHlsArtifact`, dispatcher JSON, and FFmpeg worker logs. |
| Playlist returns `401` or `403` | Missing/expired session, policy denial, or center-scope denial. | Verify the browser session and authorization; do not weaken media endpoint permissions. |
| Playlist works but key fails | Key ID/video mismatch, permission failure, or master-key mismatch. | Check key URL binding, master-key gate, and artifact key metadata. |
| Key works but segment is `404` | Nginx offload disabled/misconfigured, stale artifact paths, or missing segment. | Check `SERVE_WITH_NGINX`, protected media location, readiness check, and Nginx journal. |
| Dispatcher says `Finished` but video is unavailable | The oneshot only queued asynchronous tasks. | Correlate task IDs in the FFmpeg worker and wait for `ready`. |
| `already materializing` | A live or stale artifact already owns materialization. | Check worker activity and artifact timestamp before considering an audited repair. |
| `Unsupported encrypted file format` | Legacy source cannot be decrypted/read with the active storage format or key. | Quarantine the affected item, verify source provenance and master key, and repair explicitly; do not force-convert unknown bytes. |
| Frontend source fix works locally but not on the host | The host still serves an older wheel's compiled static assets. | Inspect configured wheel path/version and rebuild the host with a newly packaged wheel. |

## Security non-negotiables

- Never expose the application master key, HLS content key, client private key,
  node shared secret, cookies, or raw clinical media through Nix store values,
  browser logs, task results, or ordinary application logs.
- Never add an unauthenticated Nginx alias to the HLS directory.
- Never treat obscured UUID paths as authorization.
- Never enable progressive plaintext fallback to make a browser appear to work.
- Never mark a video import successful before its required raw and processed
  HLS artifacts are ready.
- Never infer materialization completion from dispatcher exit status.
- Never transfer raw media to the hub under the processed-media contract.
- Never disable certificate verification or permit redirects in the hub sender.
- Never claim payload-level hub encryption when only TLS/mTLS is configured.
- Never deploy unversioned frontend output independently of the selected runtime
  artifact.

## Ownership map

| Concern | Owning implementation |
| --- | --- |
| Import success and HLS materialization | `endoreg-db` import state management and HLS media service |
| Playlist, key, segment authorization and MIME/cache headers | `endoreg-db` HLS views |
| Artifact state and wrapped-key metadata | `endoreg-db` `VideoHlsArtifact` model |
| Browser HLS and credential propagation | lx-annotate frontend authenticated stream composable |
| View integration and media element lifecycle | lx-annotate Vue video components |
| Runtime package/static asset selection | lx-annotate wheel plus LuxNix wheel-mode configuration |
| Worker isolation, service ordering, backfill dispatch, Nginx handoff | LuxNix lx-annotate-local module |
| Site-to-hub sender ledger and request behavior | lx-annotate hub export worker |
| Hub transfer authorization and apply contract | `endoreg-db` hub transfer services/views |
| mTLS identity, secret paths, and fail-closed deployment assertions | LuxNix lx-annotate-local hub options/configuration |

Changes to any row must be reviewed against the complete lifecycle. Passing a
unit test in one repository is not sufficient evidence that production video is
ready.
