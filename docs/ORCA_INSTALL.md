# Local Orca installation and host setup

## Current agent-environment state

User authorized downloading/installing the official AppImage, not a printer trial. Architecture: x86_64; environment: Debian 12 (glibc 2.36).

Downloaded and extracted under ignored `.local-tools/`, without sudo:

| Build | Local executable | Observed status |
| --- | --- | --- |
| Official 2.5.0 Ubuntu2404 x86_64 AppImage | `.local-tools/orca-2.5.0/AppRun` | Cannot run here: requires GLIBC 2.38 and GLIBCXX 3.4.32, plus missing desktop runtime libraries. Do not replace the system glibc to make it work. |
| Official 2.3.0 non-Ubuntu2404 x86_64 AppImage | `.local-tools/orca-2.3.0/AppRun` | No missing GLIBC/GLIBCXX versions in the loader check; runtime libraries still missing. Native `--help`/slicing has not succeeded yet. |

`.local-tools/orca-slicer` points to the extracted 2.3.0 AppRun. Both original AppImages and download provenance JSON remain local; this uses about 1.3 GiB. No binaries or extracted third-party files are committed. The original AppRun files are unmodified. Their resource directories must stay alongside them; do not copy only the internal executable.

Direct AppImage execution failed because this environment has no FUSE device/fusermount. Extraction succeeded and avoids that requirement. The 2.3.0 loader identified missing GTK/WebKit/OpenGL dependencies. A request for `libwebkit2gtk-4.0-37`, `libgl1`, and `libegl1` is the next step; their dependencies provide the other missing desktop libraries. This requests packages for the agent environment, not an automatic host OS installation.

Only isolated `--help`/loader probes were attempted. No model was sliced, no GUI opened intentionally, and no printer connected. After package approval: retry help using isolated project-local data/cache/temp paths, record the actual advertised CLI flags, then decide the next offline profile trial. An installed application is not a validated Finder profile.

## On the host: reuse the shared files

If the host sees this same project directory, the downloads/extracted applications may already be available. From the repository root:

```sh
mkdir -p .tmp/orca-host/{tmp,data,config,cache}
```

On Ubuntu 24.04 or another compatible modern x86_64 system, probe the newer build:

```sh
TMPDIR="$PWD/.tmp/orca-host/tmp" \
XDG_CONFIG_HOME="$PWD/.tmp/orca-host/config" \
XDG_CACHE_HOME="$PWD/.tmp/orca-host/cache" \
XDG_DATA_HOME="$PWD/.tmp/orca-host/data" \
  .local-tools/orca-2.5.0/AppRun --help \
  --datadir "$PWD/.tmp/orca-host/data"
```

If it reports missing runtime libraries, on Ubuntu 24.04 the relevant packages are normally:

```sh
sudo apt update
sudo apt install libwebkit2gtk-4.1-0 libopengl0 libgl1 libegl1
```

On **Debian 12**, use the older `.local-tools/orca-2.3.0/AppRun` in that help command instead. Its requested runtime packages are:

```sh
sudo apt update
sudo apt install libwebkit2gtk-4.0-37 libgl1 libegl1
```

Do not mix these Debian/Ubuntu package instructions indiscriminately: match the host distribution and selected build. Package installation is a deliberate host action. It may be unnecessary on a desktop that already supplies the libraries. A missing DISPLAY/GTK initialization error is a separate issue; a headless build may require a virtual display, not printer access. The old 2.3.0 AppRun also has limited handling of installation paths containing spaces; keep this installation path space-free.

Once help succeeds, pass the selected extracted AppRun path via `--orca` to `finderlab slice`. Keep configuration isolation and start with offline export only; see [SLICING.md](SLICING.md). For normal GUI setup on the host, run the selected AppRun without `--help` yourself; that launches the application rather than our offline protocol tool. Do not choose an unrelated FlashForge model or initiate discovery/printing as part of the CLI validation.

## On a host without the shared downloads

Use the official release pages, not similarly named third-party download sites:

- [OrcaSlicer 2.5.0](https://github.com/OrcaSlicer/OrcaSlicer/releases/tag/v2.5.0): `OrcaSlicer_Linux_AppImage_Ubuntu2404_V2.5.0.AppImage` for modern x86_64 Linux.
- [OrcaSlicer 2.3.0](https://github.com/OrcaSlicer/OrcaSlicer/releases/tag/v2.3.0): `OrcaSlicer_Linux_AppImage_V2.3.0.AppImage` for this older-runtime attempt; **not** its Ubuntu2404 asset.

ARM hosts must choose the matching architecture instead; the above files are x86_64. The Finderlab adapter currently supports POSIX/Linux, not Windows.

Save the chosen file inside project-local `.local-tools/` and make it executable. To extract without FUSE, substitute the exact downloaded filename below:

```sh
mkdir -p .local-tools .tmp/orca-extract/tmp
chmod +x .local-tools/SELECTED.AppImage
# Start with an empty extraction directory; do not overwrite a prior installation.
(cd .tmp/orca-extract && TMPDIR="$PWD/tmp" \
  ../../.local-tools/SELECTED.AppImage --appimage-extract)
# Only if the destination does not already exist:
mv .tmp/orca-extract/squashfs-root .local-tools/orca-selected
```

The launcher is then `.local-tools/orca-selected/AppRun`. Keep all extraction/temp work inside `.tmp/`; do not extract into the repository's tracked source tree. Direct executable AppImages can work on hosts with FUSE, but extracted AppRun avoids per-job mount/extraction overhead and fits the adapter's workspace limits better.

## Download integrity/provenance

2.5.0 asset: 214571512 bytes. GitHub release API published SHA-256 `d13eb0a9cd618ed080ab6b82c64c0a60c4501aac91e88d5ac2c3b526fb141a7c`; the local download matched. You can check a separately downloaded copy with `sha256sum` against that value.

2.3.0 asset: 112784576 bytes. Observed local SHA-256 `73079d88ec36f0615db7919d00aa26fe301e348ba6e051862a7cfc4040150c03`. GitHub's API did **not** publish a digest for this asset, so this is local provenance, not independent upstream checksum verification. Downloads used the official GitHub HTTPS release URLs; hashes do not constitute an independent security audit or signing certificate.

Runtime validation and any profile adjustments remain outstanding. Do not infer hardware, toolpath or firmware compatibility from downloading/extracting an application.
