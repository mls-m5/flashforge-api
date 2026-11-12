# Reverse-engineering experiments

## Scope and safety

Start with passive observation, then a byte-preserving proxy, then a simulator based on evidence. Hardware experiments require the user's explicit approval and physical supervision. Do not run active scans or replay captures against a real printer by default.

A transparent proxy does not block heating, movement, deletion, or print-start commands. Confirm whether FlashPrint offers upload without printing before attempting a transfer. If that workflow is unavailable, first investigate connection/status traffic and explicitly plan any later physical print experiment. Never assume disconnecting the network stops a print or disables heaters.

Use a trusted LAN and a small model you own and can share. Record baseline printer state, close other clients, and know how to stop operations using the physical printer controls. Do not assume a network emergency-stop command is supported.

## 1. Record the environment

For every experiment, record:

- exact model designation and firmware shown by the printer;
- FlashPrint version, operating system, and selected printer profile;
- printer and capture-host network interfaces and addresses;
- topology: direct LAN, printer access point, VM/container, Wi-Fi or Ethernet;
- action taken, expected behavior, observed UI/device behavior, and capture timestamps;
- tool versions, experiment ID, and capture/session references.

Use `unknown` rather than guessing missing fields. Keep sensitive addresses and serial numbers in local notes rather than public fixtures.

## 2. Passive baseline capture

Use Wireshark or tcpdump on the machine running FlashPrint. Capturing there is usually more reliable than listening from a third computer: switched Ethernet and normal Wi-Fi operation do not expose every other device's unicast traffic.

Capture before launching discovery, connect normally, wait through several status polls, and disconnect. Repeat with the printer powered off to distinguish unanswered probes from replies. A second run can capture a known-safe upload workflow after separate approval.

Example Wireshark **display** filters, not shell commands:

```text
udp
ip.addr == 192.0.2.10
 tcp.port == 8899
```

Replace `192.0.2.10` with the actual printer address; it is only a documentation example. For discovery, initially retain all UDP rather than filtering on guessed ports. For a known host, consider all its TCP traffic so a second data connection is not missed. Capture on all relevant interfaces if a VPN or virtual adapter may affect routing.

Inspect both TCP streams and original packet timings. TCP segmentation, retransmission and ACKs are transport behavior, not necessarily application block boundaries or acknowledgements. Export binary streams without text conversion. Identify discovery queries/replies separately from the TCP session.

**Output:** baseline capture, environment notes, exact identity/status request-response exchanges, and an initial list of unknowns.

## 3. Proxy experiment

The recording proxy is now implemented and localhost-tested; see [PROXY.md](PROXY.md) for actual commands and limitations. For an explicitly approved hardware experiment, run it with an explicit printer target. Configure FlashPrint to connect to the proxy's reachable address, using manual IP connection if supported. The proxy and printer can both use port 8899 on different hosts. On the same host, a different bind address or port may be needed; whether FlashPrint accepts a different port is still unknown.

Verify the route using both proxy logs and, when possible, a host packet capture. FlashPrint might bypass the proxy by rediscovering the real printer. A connection appearing in the UI alone does not prove interception.

First compare connect → identify → status → disconnect through the proxy against the direct baseline. Then attempt an approved upload. Do not add delays or protocol rewrites to make a failing proxy appear compatible; investigate stream bytes, backpressure, shutdown and network reachability first.

If FlashPrint cannot manually address the proxy, capture discovery first and implement a separately tested discovery responder. Do not blindly broadcast another model's packet template.

**Output:** validated bidirectional recording, known complete/incomplete status, and a comparison with direct behavior.

## 4. Controlled upload comparisons

Change one variable per run and keep all other versions/settings fixed:

| Variable | Question |
| --- | --- |
| Same file, repeated upload | Which fields are session-dependent or randomized? |
| Filename only | Is metadata separate from payload? Which encoding/path rules apply? |
| File size | Does advertised length match source bytes or a wrapped payload? |
| Payload near an observed boundary | Are there fixed-size blocks, padding or a special final block? |
| `.gx` versus other formats produced for Finder 2 | Does FlashPrint wrap or transform the file? |
| Controlled interruption, initially simulator-only | What is committed, and what remains temporary? |

Compare the original source file against reconstructed application payloads by exact bytes and hash. File headers, previews and slicer metadata may explain differences; do not immediately conclude that they are transport headers.

If CRC-like fields appear, test competing interpretations offline: field location, width, endianness, initial value, polynomial, covered bytes and final XOR. Validate a candidate on multiple independent captures, including different final-block lengths. A repository's reported CRC error is not proof that Finder 2 uses a particular CRC scheme.

Do not mutate arbitrary binary payloads on hardware. First use captured files and offline analysis, then simulator tests, then narrowly approved hardware checks.

## 5. Bootstrap and validate the simulator

Without a real-printer capture, a synthetic simulator can test networking and expose what FlashPrint sends before its first missing response. It cannot guarantee that FlashPrint proceeds to upload. Record this limitation explicitly.

With a reference capture:

1. Create a versioned profile from observed identity/session/status exchanges.
2. Reproduce the known connection workflow, preserving response bytes and ordering.
3. Implement stateful upload framing from observed evidence, not the current script alone.
4. Run FlashPrint against the simulator with no physical-printer connection configured.
5. Compare the virtual file against the original source bytes.
6. Repeat with another filename, another size, idle polling and reconnect.
7. Record unsupported commands and gaps instead of returning unconditional success.

A strict replay fixture is useful to locate the first divergence. A stateful model is necessary once polling order, parameters or payloads differ.

## 6. Additional investigation options

- **Host-local packet capture:** an independent ground truth for proxy recordings and discovery. Useful before any project code exists.
- **Managed-switch port mirroring or router/AP capture:** useful if FlashPrint runs on another host; availability depends on network hardware and topology. A normal third LAN computer is not enough.
- **Offline stream diffing:** compare repeated runs, isolate constant headers and variable fields, and correlate commands with UI actions.
- **FlashPrint application logs/settings:** may expose selected ports, connection failures or model identifiers without protocol modification. Review privacy before sharing.
- **Existing open-source clients:** inspect packet construction, response parsing and upload issues, recording commit and license. Treat implementations as hypotheses until reproduced.
- **Controlled fault injection:** delayed replies, fragmented messages, storage-full errors and disconnects in a fake server/simulator; useful for hardening the client without risking hardware.
- **Differential testing:** issue the same safe operation through FlashPrint and the custom client, compare requests and printer outcomes. Never automatically replay a whole captured session on hardware: it may contain print-start or heating commands.
- **Firmware/update-package inspection:** optional later offline work on lawfully obtained material, if network evidence is insufficient. Firmware flashing, factory resets and physical disassembly are not part of the initial plan.

## Experiment record template

```text
Experiment ID:
Question / hypothesis:
Environment and initial state:
Safety approval and limits (if physical hardware is involved):
Capture ID and session IDs:
Procedure / single changed variable:
Expected observation:
Actual observation and byte offsets:
Conclusion / confidence / alternative explanations:
Recovery steps and final printer state:
Next experiment:
```
