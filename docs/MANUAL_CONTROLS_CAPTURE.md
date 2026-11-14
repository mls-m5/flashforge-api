# Finder manual controls: user-run capture, no replay

## Source and scope

User operated FlashPrint controls through the already running proxy and reported
this order: stepper controllers on/off, servo controls on/off, LED color,
extruder forward/reverse/stop, then X/Y/Z jog. Source:
`captures/20261114T194822Z-b991640f7b31`, session`s0001`. It was still running
at inspection; its incomplete manifest is expected and not final integrity
proof. Only complete commands/reply frames in the observed prefix are discussed.
Firmware observed V1.5 20170419, user model Finder2. FlashPrint version unknown;
host locale unknown (decimal commas are observed, not explained).

The agent read private local logs only; it did not connect, replay commands or
perform hardware experiments. These observations do not authorize future
motion/heat tests. The user's report establishes UI order; mapping to commands
is a correlated interpretation, not an independently isolated button trial.
The preceding status traffic showed READY and cooled temperatures before this
sequence; confirmation that the print had completed at button-operation time
was requested. Print completion/end quality remains user-observed, not inferred
solely from network ACKs.

## Observed request sequence

Timestamps below are UTC from the capture, not guessed local wall time. Raw
request bytes include a leading`~` and trailing CRLF. Decimal commas, letter
case and spacing below are preserved intentionally; do not normalize/replay.

| UTC (2026-11-14) | Request body (without CRLF) | Correlation / limits |
| --- | --- | --- |
| 20:02:24.388839 | `~G91` | Relative mode, possibly entering manual control; no isolated UI identification |
| 20:02:39.367921 | `~M17` | First reported controller-on action |
| 20:02:40.478480 | `~M18` | First reported controller-off action |
| 20:03:06.653780 | `~M116` | Correlates with reported servo-controls on |
| 20:03:07.520332 | `~M117` | Correlates with reported servo-controls off |
| 20:03:33.518786 | `~M146 r136 g138 b133 F0` | Reported LED-color action; lowercase RGB fields observed, F0 meaning unverified |
| 20:03:52.970153 | `~M17` | Another motor-enable request before extrusion; UI ownership/automatic emission not established |
| 20:03:58.494280 | `~G1 E14,399 F172,787` | Reported forward action; magnitude/decimal interpretation not independently measured |
| 20:03:59.752242 | `~G1 E-14,399 F172,787` | Reported reverse action |
| 20:04:01.077089 | `~M112` | After reported extruder Stop; **not an emergency-stop guarantee** |
| 20:04:57.966045 | `~G1 X-1000,000 F2000,000` | Large jog target, not a measured 1000 mm movement |
| 20:04:58.296321 | `~M112` | Following X jog |
| 20:05:00.219889 | `~G1 Y-1000,000 F2000,000` | Large jog target |
| 20:05:00.313239 | `~M112` | Following Y jog |
| 20:05:02.700735 | `~G1 Z1000,000 F800,000` | Large jog target |
| 20:05:02.877097 | `~M112` | Following Z jog |

M114 position queries follow the three axis-stop pairs; ordinary
M105/M119/M27 polling continues around these operations. Do not interpret
reported coordinates under manual control as a validated physical origin,
build envelope or swept-volume boundary. Motor release may invalidate assumed
position. No travel-limit, actual extruded length or cold-extrusion behavior
was independently measured in this investigation.

## Mixed reply terminators: preserve raw bytes

Echo-framed replies for G91/M17/M18/M116/M117/M146/G1 in this prefix use:

```text
CMD <code> Received.\r\nok\n
```

M112 replies use `CMD M112 Received.\r\nok\r\n`; M114 replies retain CRLF
frames and coordinates. This difference matters: do not pair every reply by
searching only for`\r\nok\r\n`, which incorrectly merges LF-terminated manual
ACKs with later status replies. The echo starts locate these complete reply
frames in the byte-preserved server stream. Example reviewed half-open ranges:
G91`[151606,151628)`, firstM17`[154694,154716)`, M116`[160526,160549)`,
M146`[166172,166195)`, firstG1`[171514,171535)`, firstM112`[172047,172071)`.

No client-parser relaxation is introduced here: our web/CLI upload and job
controls remain scoped to their reviewed response formats. Adding manual
control would require its own operation/mode/cancellation parser design and
fault tests, not a blanket line-ending normalization in the recording proxy.
The proxy still forwards exact bytes and is not a safety filter.

## User clarification: Continuous jog selected

The user subsequently confirmed the UI said **Continuous jog**, and that
separate millimetre-step choices are available. This supports interpreting the
large relative targets as continuous-jog implementation details rather than
ordinary step sizes. The user suggests press starts a long-target movement and
release sends the interruption. The observed rapid G1→M112 sequence is
consistent with that hypothesis, but button press/release events and actual
travel were not independently recorded. Do not label it proven or treat M112 as
a general emergency stop. Millimetre-mode wire behavior remains unobserved and
requires its own explicitly approved controlled trial; no agent motion action
was taken. Do not transplant continuous-jog targets into a generic motion API.

## Next steps, before implementing motion controls

- Confirm physical completion, actual button behavior, FlashPrint version,
  jog-step/continuous settings, locale and whether controls are press-and-hold.
- Distinguish continuous jog cancellation from print cancel: observedM112
  here is not evidence of emergency behavior or equivalent to observedM26.
- Use explicitly approved, empty/clear/cool supervised tests only after mode,
  origin and direction are understood. Never send the captured±1000 targets as
  generic steps, replay the whole trace, or try this during printing.
- Do not interpret command names using generic Marlin meanings; M116/M117
  have different common meanings elsewhere. Their Finder UI correlation is
  the evidence here, not a portable command specification.
- Status-only web monitoring can be designed separately around existing
  M105/M119/M27 evidence, with one session owner and no competing clients.
