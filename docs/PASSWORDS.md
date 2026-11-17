# Persistent LAN login and changing the password

## User workflow

LAN mode still uses the shared username **finder**. On the first startup with
this feature and no saved record, the server generates/prints a strong initial
password once. Existing older per-run passwords are not recoverable or silently
imported from console logs. Sign in with that first new password, then use the
**LAN login password** form near the top of the page:

1. Enter the current password.
2. Enter/repeat a new password (12–128 characters, no control characters).
3. Click **Save login password · no printer action** while no local job is active.

The new login applies to all shared users immediately and survives web/container
restarts. Your browser may ask you to log in again; refresh and use the new
password if it still has the old Basic credential cached. There are no individual
accounts or per-user revocation. All logged-in users know the same credential.
A lost response is not automatically retried: try the new login or use offline
reset. The form clears password inputs after an attempt/pagehide, never stores
them in browser localStorage or includes them in a URL. It initiates no file,
printer or slicer action. Busy rejects password changes; a bounded local busy
period prevents another job starting while the credential is being persisted.

On later startups logs say `Login password: unchanged ...`, not the password:
a salted hash cannot recover its plaintext. Do not share logs with an initial /
reset password. Keep your password in a private password manager.

## Storage and protection

`DATA_DIR/auth.json` is a private regular owner-only file (created0600), separate
from file slots/captures. It contains only a version, algorithm, work factor,
32-byte random salt and32-byte PBKDF2-HMAC-SHA256 verifier (**600000 iterations**).
No plaintext/Base64 password, HTTP Authorization header or password-change body
is stored in it, operation captures, public config/state or normal logs. Each
change uses a fresh salt. Atomic same-directory replacement/flush precedes the
in-memory switch; ordinary write failures retain the old verifier/login. Bad
schema/size/work factor/permissions or symlinks fail startup rather than silently
resetting/bypassing login. Private datadir and local filesystem writers remain
trusted; this is not an OS sandbox or a full power-loss audit guarantee.

The existing workspace lock covers record creation/change; a second server or
offline reset cannot race an active workspace. KDF work runs off the asyncio
loop, serialized with credential replacement; cancellation joins the worker
before unlocking, preventing late old-credential cache writes after rotation.
A single per-process keyed HMAC fingerprint caches successful authentication
for repeated assets/polls without storing Basic/plaintext credentials; it is
invalidated on change. Invalid credentials are not cached. Existing16-client /
HTTP limits apply; this remains a trusted-home-network service, not a hardened
public brute-force/DoS gateway.

POST `/api/password` accepts exactly `confirm:true`, `current_password`,
`new_password`. Usual LAN Basic/peer/Host, exact Origin, per-run token, JSON/body
limits apply before routing. Current-password verification is also required.
Local-only mode does not enable this form/API and creates no auth record. No
GET changes credentials. Per-run CSRF tokens still rotate on restart even though
the password now persists. No capture/job state/save identity is reset by a
password change. Discard and automatic recording archive do not move/delete it.

In Compose the record lives in the existing persistent **web-data named volume**.
Keep that volume and Compose project name on update; a fresh/removed volume gets
a new initial password. Back up the verifier privately with the volume: it is
sensitive even though salted. Never commit or include it in source releases.

**HTTP is still unencrypted.** Passwords are hashed at rest only; Basic auth and
the change form transmit credentials over HTTP. All previous specific-interface
LAN/peer/Host/Origin/token rules remain. Trusted home network only, no Internet /
router forwarding/public tunnel/reverse proxy. There is no TLS claim.

## Forgotten password — offline reset, not an unauthenticated API

When no upload/Slice/start is active, on the server in the deployment directory:

```sh
podman compose stop finder-web
podman compose run --rm --no-deps --entrypoint python3 finder-web \
  -m finderlab.web_password --data-dir /app/web-data
./tools/start_server.sh
```

Docker Compose is equivalent. Keep the same project/private .env so the one-off
container uses the existing volume. Reset prints a **new random password once**;
it does not reveal the old password and takes no secret CLI arguments. It holds
the workspace lock and refuses while web is running. It opens no printer/socket,
reads no model/capture, clears no job/file data and does not start the proxy
(`--no-deps`). Web startup after reset has the ordinary configured monitor policy.
Actual container/provider reset acceptance remains host-run here.

For native use after stopping web: `python3 -m finderlab.web_password --data-dir
YOUR_EXISTING_WEB_DATA_DIR`. Damaged permissions/links/oversized records need
explicit local administrator review; never solve it by a public reset route or
auth fallback. No automatic deletion/repair of credential or evidence files.

## Checks

Pure verifier tests cover independent PBKDF, salt uniqueness, schema/work bounds,
private permissions/links, persistent login, cache invalidation and atomic-write
failure. Owned ephemeral loopback HTTP checks cover authenticated change, strict
fields/current-password/origin/token/busy/local-mode gates, restart/old-login
rejection, no capture/credential leakage, serialized worker cancellation and
locked/offline reset. Node checks cover capability-gated explicit submission,
repeat validation, field clearing, no retry/double-submit and no printer routes.
Validation: a clean staged-source checkout passed360 Python tests,17 Node scripts
and reviewed-trace integrity via `./tools/check.sh`; diff whitespace checks passed.
This includes14 password/storage/HTTP/reset/cancellation contracts plus the new
Node form check. Real browser credential caching and container/provider acceptance
remain manual. No agent LAN/hardware action was performed or authorized.
