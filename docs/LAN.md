# Explicit trusted-LAN sharing

## Scope and threat boundary

Requested workflow: a second trusted person may receive files, Slice, review /
download, Save, explicitly Start/Cancel and read status. These are the same
server-side operations/limits as local use, **not automatic print start** or a
new remote G-code console. Physical manual-control buttons remain locked.
Everyone with the password shares **one printer, current slot, saved-file
identity and job result**; coordinate with the other operator. This is a shared
login, not separate accounts, per-user ownership or audit attribution.

Default web startup is still loopback-only. LAN sharing needs an explicit
interface address plus `--lan`. Only IPv4 peers in192.168.0.0/16 (or an explicit
narrower CIDR), plus local IPv4 peers, are eligible, and **all require a password**.
Bind to a specific allowed interface, never0.0.0.0 or a guessed printer IP.
The socket peer is checked; Forwarded/X-Forwarded-For are ignored. Fixed Host,
exact Origin/per-run CSRF token, CSP/no-CORS and operation/firmware guards remain.

**HTTP is not encrypted.** Basic authentication is encoding, not encryption:
network observers can steal credentials/models or modify traffic. Use only a
trusted home network where that risk is acceptable; this is not suitable for
public/shared Wi-Fi, untrusted guests, Internet exposure or a security-hardened
multi-user service. Use a separately designed HTTPS setup before broadening
that trust boundary; TLS/reverse-proxy integration is not provided here.
192.168 addresses are private, not a guarantee of localness/trust: VPNs, VLANs
and router/NAT forwarding can expose the service too. Do not forward the port,
use a public tunnel or put a reverse proxy in front that hides peer identity.

## Short full-workflow launcher

Keep the deliberately configured recording proxy running locally. Close
FlashPrint/other control clients before automatic status connects. Stop only
the old web process when it is not saving/slicing; do not interrupt printer or
proxy. Both old/new web launchers use the same workspace lock and cannot run
concurrently against that slot.

No IP argument is needed:

```sh
./tools/start_lan_web.sh
```

Share the link printed by the launcher/server, then log in as described below.
The printer proxy remains **localhost9000**; it is not the browser's address.
The script reads only this Linux computer's local interface configuration
(SIOCGIFFLAGS/SIOCGIFADDR, at most256 interfaces). No DNS, network probes,
printer discovery, outgoing connection or packet is used to select the address.
It chooses the sole primary IPv4 address on an UP interface in the allowed
192.168 subnet. Password, source filter, exact Host/Origin checks and the
specific-interface bind remain unchanged—no wildcard/LAN trust broadening.

If no eligible address exists, connect to the home network and retry. If several
exist (for example a VPN and Wi-Fi), it lists candidates instead of guessing.
Advanced overrides still work; example addresses below are not actual targets:

```sh
./tools/start_lan_web.sh --lan-network 192.168.1.0/24
./tools/start_lan_web.sh 192.168.1.20
# Equivalent automatic selection on the normal proxy launcher:
./tools/start_proxy_web.sh --lan-host auto
```

Automatic selection requires Linux and reads primary addresses only; use the
explicit override for secondary addresses or other supported POSIX hosts.

The wrapper explicitly enables existing upload, generated-output Save and
confirmed Start/Cancel, uses the existing private draft02/Orca setup, and starts
status polling of the configured loopback proxy9000. No new profile is guessed
and no change to draft02/startup/temperature/retraction is made. Models and
expanded footprints still need review; sharing/enabling output Save does not
certify them printable or motion-safe. This launcher is an intentional
full-workflow policy selection; normal proxy/offline launchers keep their
existing action gates. It requires the same local Orca/private profiles as the
ordinary proxy page; missing profiles are not auto-downloaded or substituted.
`--proxy-port`, `--port`, `--orca`, `--no-monitor` and `--check` work as before.
`--check` reads local interface/file configuration only, binds nothing, sends
no packets and generates no password.

The server prints:

- exact URL, e.g. `http://192.168.1.20:8000` (use this on **both computers**);
- username **finder**;
- a strong random **initial** password on the first startup without a saved
  verifier. It now persists across restarts; later logs say it is unchanged.
  Set your own in the page's **LAN login password** form. Share privately; never
  put it in URLs, shell arguments, captures, screenshots or public logs.
  See [PASSWORDS.md](PASSWORDS.md) for salted storage, change and offline reset.

The browser prompts for the password before serving HTML/assets/config or any
API/file/status response. Reopening tabs does not create another printer owner
or auto-start a job. After restart the same password works, but reload for the
new per-run token; stale saved identities are not reused. There is no per-user
logout/revocation. An authenticated GUI password change affects all users and
survives restart; it requires the current password and no local busy operation.
Someone at the computer must supervise physical printing/clearance; the remote
Start confirmation acknowledges possible heating/motion. Cancel is not emergency
stop. Old saved-file references are in-memory only and lost on web restart.

If a host firewall blocks access, allow only the selected HTTP port from the
intended private subnet/client. Do not disable the firewall globally or expose
printer8899/proxy9000. Guest Wi-Fi isolation can intentionally prevent access.
No firewall/router configuration is changed by the scripts.

## Other modes and local auth rehearsal

`./tools/start_proxy_web.sh --lan-host 192.168.1.20` shares the normal proxy page
with its existing action flags instead of implicitly selecting the full policy.
LAN selection alone never grants job/upload/generated-output capabilities.
Low-level equivalent flags: `python3 -m finderlab web --lan --listen-host IP`
with whatever explicit printer/slicer options the operator deliberately chooses.

For an **authenticated loopback-only rehearsal**, no Orca/profile needed:

```sh
python3 -m finderlab web --dummy --lan --listen-host 127.0.0.1 \
  --listen-port 8002 --data-dir web-data/lan-rehearsal
```

This special loopback rehearsal still requires the random LAN-mode password but
never opens a LAN listener or uses an existing proxy. `--dummy` owns its fresh
simulator; confirmed virtual Start/Cancel execute no G-code. The short LAN
wrapper requires a real192.168 interface, so this rehearsal uses the raw CLI.

## Checks and limitations

Tests bind **only fresh ephemeral loopback endpoints**. Pure policy tests
exercise private/subnet/public/mapped/wildcard/invalid addresses without LAN
binds. HTTP tests cover401 challenges, all protected assets/read/mutating routes,
no side effects before authentication, no password in config/printer captures,
shared exact Save and separately confirmed Start/Cancel, status polling and
fake offline Slice, plus Host/Origin/token and peer rejection. Wrapper checks
verify automatic/no-argument startup, explicit interfaces/CIDR, missing/multiple
addresses, bounded local ioctl reads without connect/send/DNS, and unchanged
capability gates. Existing Python,
Node UI and reviewed-trace checks remain applicable.

An actual CLI smoke check also ran `web --dummy --lan` with an ephemeral
loopback listener and project-local temporary workspace, checked the printed
per-run login,401 challenge and authenticated config, then stopped cleanly.
No LAN listener/printer was involved and no password was published/retained.

Actual access from a second computer, browser Basic-auth caching/prompts,
firewall/Wi-Fi and native host slicing remain operator acceptance checks. No
agent LAN service, physical printer connection or firewall change was performed.
This remains a bounded experimental stdlib HTTP server, not a production or
Internet-facing gateway. Native slicer/models/profiles and all authenticated
users, local processes and browser extensions are trusted.
