# Docker Compose server deployment (Linux)

## Status and boundaries

The repository now provides a safe default Compose service, an optional native
Orca image, and an opt-in recording proxy. **Docker/Podman is unavailable in the
agent environment**: command/configuration tests pass, but actual image builds,
Compose provider compatibility and container/browser/native runtime acceptance
must be verified on the deployment host. Do not describe this as a completed
container or hardware trial. No agent printer/LAN connection was made.

Supported deployment shape: a trusted **Linux server**, local loopback or an
explicit192.168 interface under the existing password/peer/Host/Origin policy.
No public IP, wildcard bind, router forwarding, public reverse proxy or Internet
service. Linux host networking is intentional: it preserves exact-interface
binds and lets web reach a deliberately selected host-loopback proxy. There is
no `ports:` wildcard publication, device passthrough, privileged mode or engine
socket. Docker Desktop/Windows/macOS host networking is not supported here.

## 1. Clone and run the safe default

```sh
git clone https://github.com/mls-m5/flashforge-api.git
cd flashforge-api
cp .env.example .env
docker compose up --build -d
docker compose logs -f finder-web
```

Open **http://127.0.0.1:8000 on that server**. Default `FINDER_MODE=dummy` creates
its **own fresh ephemeral simulator**, never reusing a printer or existing
proxy. Uploads and confirmed virtual Start/Cancel target that dummy only; it
never executes G-code/heats/moves. STL mesh/plate editing and existing print-file
virtual saving are available. **Slice needs step2**, not a guessed profile.
No OctoPrint/submodule initialization, pip/npm installation or cloud service.

To view from another computer on your trusted home network, edit `.env`:

```dotenv
# This SERVER's actual specific interface, not the printer IP or an example:
FINDER_LISTEN_HOST=192.168.1.50
```

Replace the example with your server's address. The entrypoint automatically
enables **mandatory per-run Basic login** for this non-loopback bind, using
existing subnet/peer rules. It does not enumerate/probe interfaces or discover
a printer. Optional `FINDER_LAN_NETWORK=192.168.1.0/24` narrows access. Other
private ranges (10/8,172.16/12), domains and0.0.0.0 are deliberately not silently
supported. Allow the chosen port in your host firewall only for the trusted
subnet. Set `FINDER_WEB_PORT` to change it, and use that exact IP/port URL.

```sh
docker compose up -d --force-recreate finder-web
docker compose logs finder-web
```

Use username **finder** and the random password printed in those private logs.
It changes on every restart/recreate; environment files do not embed a reusable
UI password. Console/logs contain credentials: do not publish them. **HTTP is
unencrypted**, including Basic credentials/models. This is not a public-service
security design. No automatic print is triggered by opening/reloading the page.

## 2. Add Orca and your trusted Finder profiles

A public clone cannot include the private local Finder profiles, their geometry
or raw evidence. There is **no universally validated print-ready Finder preset**
in Git. Do not substitute an Adventurer/Creator/Guider profile or silently change
firmware flavor. Copy your existing separately reviewed self-contained profile
directory from your working machine, retaining its provenance/license files:

```text
local-profiles/finder-offline-03/
  machine.json
  process.json
  filament.json
  ...originals/provenance/license attribution...
```

For this user's current setup,03 is the deliberately selected native-skirt
profile. Keep the originals; the service mounts them read-only. For a different
trusted directory, set `FINDER_PROFILE_DIR=/absolute/server/path/to/profiles` in
`.env`. Paths are server files, never uploaded/browser-supplied configuration.
All3 JSON files must exist and be readable by the container's UID1000; bad/missing
paths fail without automatically creating an empty directory/fallback preset.
Native profile validation still runs on every explicit Slice.

```sh
docker compose -f docker-compose.yml -f compose.slicing.yml up --build -d
docker compose -f docker-compose.yml -f compose.slicing.yml logs -f finder-web
```

The optional image uses Linux/amd64 **Orca2.3.0**, not your host's2.5 binary. Build
installs Debian bookworm runtime packages, downloads the official asset using
our existing pinned size/SHA256 downloader, extracts without FUSE, retains
upstream resources/licenses and probes bounded `--help` without a model/printer.
No private profiles, uploaded models, captures, .env, Git metadata or host binary
are copied into the build context/image. Profiles remain bind-mounted read-only.
No host apt/runtime installation or serial device access is needed.

The2.3 pin matches native offline evidence and glibc in the base image. It is
**not** proof that a container build behaves identically to the user's2.5 host;
re-slice/download/review a small model offline before hardware use. Do not disable
checks or symlink incompatible WebKit/glibc libraries on failures. The entrypoint
adds `--check-priming` with configured profiles; no native guessed settings.
Optional image includes corresponding-source URLs and asset hash in
`/opt/orca/FINDERLAB-PROVENANCE.txt`. Project is GPLv3; Orca upstream AGPL3 and
bundled third-party notices/resources remain. If redistributing images, review
and satisfy the applicable corresponding-source/notice obligations, not just
link to an unrelated current source revision. No upstream source was modified.

Expect a substantially larger image/download than the Python-only default;
plan several GiB free for build layers plus private volumes. Slicer service has
4GiB container memory,2 CPUs and256 PID/thread budget; existing adapter subprocess
limits still apply. ARM/RaspberryPi native slicing is not supported by this
x86_64 asset; emulation and other image/runtime architectures are unverified.
Base/apt tags can update: only the Orca asset is content-pinned, not a bit-for-bit
reproducible distro image. No GPU/display/FUSE is required for this path.

## 3. Deliberately connect the server workflow

Keep the default dummy until profiles/output/target are reviewed. For an already
user-owned recording proxy on **this server** at127.0.0.1:9000, set:

```dotenv
FINDER_MODE=proxy
FINDER_PROXY_PORT=9000
FINDER_ENABLE_UPLOAD=true
FINDER_ENABLE_JOB_CONTROLS=true
FINDER_ALLOW_SLICED_UPLOAD=true
FINDER_ENABLE_MONITOR=true
FINDER_AUTO_MONITOR=false
```

Generated-output saving requires the slicing override/profiles. You can omit
job/generated-output flags when only ordinary GX/G-code save is wanted. By
default status connection is **manual**, not automatic at service startup;
`FINDER_AUTO_MONITOR=true` is a separate explicit choice and opens status-only
connections on **every** restart. Close FlashPrint/other control clients first.
No hostname/target selection/discovery is accepted from browsers. Host-loopback
is not proof of a virtual target. Do not assume an existing port belongs to your
proxy. The container entrypoint never silently switches dummy to hardware.

To run the **bundled** recording proxy instead of a host process, additionally set:

```dotenv
# Replace with the deliberately verified printer IP; no default is guessed:
FINDER_PRINTER_HOST=192.168.1.60
FINDER_PRINTER_PORT=8899
FINDER_ALLOW_HARDWARE=true
```

Then (only after verifying target and intended capabilities):

```sh
docker compose -f docker-compose.yml -f compose.slicing.yml \
  --profile printer up --build -d
```

The profile starts `finder-proxy` bound to127.0.0.1 on the explicitly chosen proxy
port, with its own named recording volume. It rejects absent/nonliteral/self-loop
printer targets and requires hardware opt-in for non-loopback targets. It accepts
connections but injects no printer command at startup. Do not simultaneously run
another proxy on the same port. Web/relay startup is not an automatic successful
printer handshake; no blind retries hide readiness/errors. For an existing host
proxy, **omit `--profile printer`**.

**A transparent proxy is not a safety filter.** It forwards dangerous commands.
With job controls enabled, the browser's user-requested default-checked option
makes its button **Save + start**. Uncheck for save-only. Confirmed save, healthy
release/recording, fresh READY, exact identity and one-attempt/no-retry gates
remain. Cancel is separate/not emergency stop; no automatic stop/replay.
Physical manual jog/heater/extrusion controls remain locked. Image/header success
or a profile that slices is not a physical clearance certificate.

## Persistence, maintenance and logs

Named volumes retain web inputs/artifacts/captures/archive, project scratch and
separate raw proxy recordings. No host home/upload/source directory is mounted
except the deliberate read-only profile directory. UID1000 runs processes;
dedicated volumes initialize from owned image directories. On rootless Podman /
SELinux, verify provider volume ownership/labels and read permissions explicitly;
never solve this by privileged mode or mounting the engine socket/home directory.
`podman compose` may be used with a compatible Compose provider; provider/runtime
acceptance is host-tested, not established by text-only tests here.

```sh
# Rebuild/recreate after updating, only when no upload/slice/start is in flight:
git pull
docker compose -f docker-compose.yml -f compose.slicing.yml up --build -d
# Status/logs:
docker compose ps
docker compose logs --tail 100 finder-web
# Stop containers, preserving data:
docker compose down
```

Use the same `-f ...`/`--profile printer` options consistently for your chosen
configuration. `down -v` **deletes private volumes**; it is not routine cleanup.
Back up volumes/profile provenance before updates. Restart loses the in-memory
current plate/saved-file reference and owned-dummy RAM files; retained disk files
are not automatically reloaded or printed. Restart never resumes/retries Start.
Do not interrupt an upload or manipulate the proxy for ordinary UI reloads.

Web admission defaults256MiB, optional `FINDER_STORAGE_MIB=512` (bounded128–2048).
`FINDER_AUTO_ARCHIVE=true` archives complete inactive web records intact on
pressure into the same persistent volume, capped2GiB. No deletion of active logs /
model files. This is not disk-space reclamation. **Raw proxy captures are separate
and are not web-auto-archived**: proxy per-run quota remains256MiB; full/incomplete
recording stops affected connections and needs deliberate operator recovery,
not automatic replay. There is no unlimited global raw-proxy retention policy.
Monitor disk/volumes and archive old finalized proxy runs manually. Container
console logs rotate10MiB×3, but can include the per-run UI password.

Configuration is a fixed allowlist of `FINDER_*` variables; unknown native CLI /
command-line arguments are not silently accepted by the entrypoint. For an
advanced raw CLI invocation, explicitly override entrypoint with `python3` and
supply `-m finderlab web ...`; that bypasses the environment launcher, not backend
access/capability/resource policy. Default Docker image target is `web`; direct
`podman build`/`docker build` should specify `--target web` for the lightweight
image or `--target slicer` for native runtime. Compose selects these explicitly.

## Checks and known gaps

Dependency-free tests validate environment/CLI argv, safe owned-dummy default,
specific LAN/password policy, explicit hardware/capability opt-ins, invalid
settings, fixed profile/runtime paths and Compose/build privacy/target contracts.
The actual existing CLI parser accepts every generated argv, without launching
printers/listeners/native tools. Native upload/plate/GX/archive regression tests
remain ephemeral-loopback/fake or separately labelled offline evidence.

Run `python3 -m unittest discover -s tests -v`, existing Node checks, then on the
actual host `docker compose config` (and with the slicing/profile options),
`docker compose up --build`, browser/login/worker and small offline Slice/GX.
Do not share rendered config/logs containing private IPs or login passwords.
Container build/slicing, browser/LAN login and physical server deployment remain
unverified here because no Docker/Podman runtime is available. A real target/
upload/start trial still requires deliberate user operation/supervision.
