# ReaPack Porter

ReaPack Porter is a standalone companion utility for ReaPack. It exports and imports ReaPack repository lists outside REAPER, with frozen GUI and CLI builds for Linux, Windows and macOS. The legacy Lua/ReaScript tool remains available in this repository for existing workflows.

## Download

Published builds are distributed through GitHub Releases. Each release contains four platform archives, and each archive has a `.sha256` sidecar using this format:

```text
HASH  FILENAME
```

The v0.1.0 archive names are:

- `ReaPack-Porter-0.1.0-linux-x86_64.tar.gz`
- `ReaPack-Porter-0.1.0-windows-x86_64.zip`
- `ReaPack-Porter-0.1.0-macos-x86_64.zip`
- `ReaPack-Porter-0.1.0-macos-arm64.zip`

## Platform Installation

### Linux

Extract the `.tar.gz` archive and keep the full `ReaPack-Porter` directory together. Start the GUI with:

```bash
./ReaPack-Porter/ReaPack-Porter
```

Start the CLI with:

```bash
./reapack-porter-cli
```

Frozen builds do not require a local Python installation. The first supported Linux architecture is `x86_64`.

### Windows

Extract the full ZIP archive. Do not copy only the `.exe` out of the GUI directory: `ReaPack-Porter\_internal` must stay next to the GUI executable.

GUI:

```text
ReaPack-Porter\ReaPack-Porter.exe
```

CLI:

```text
reapack-porter-cli.exe
```

Windows builds are not digitally signed yet, so Windows SmartScreen may show a warning.

### macOS

Choose the ZIP for your Mac, extract it, and optionally move `ReaPack Porter.app` to Applications.

- Intel build: `x86_64`
- Apple Silicon build: `arm64`
- No universal2 binary is produced.

macOS builds are not codesigned or notarized yet, so Gatekeeper may show a warning. Prefer opening the app intentionally from Finder with Control-click or right-click > Open.

## Quick Start

Export:

1. Check the automatically detected source `reapack.ini`.
2. Choose an output folder.
3. Optionally choose ZIP output.
4. Click Export.

Import:

1. Close all REAPER processes.
2. Choose a ZIP or bundle folder.
3. Check the target `reapack.ini`.
4. Use Preview.
5. Run Import.
6. Start REAPER.
7. Run `Extensions > ReaPack > Synchronize packages`.

## Critical Import Safety

Export is read-only and may be used while REAPER is running.

Import requires REAPER to be fully closed. If process status cannot be determined reliably, import fails closed. Preview and dry-run do not write anything. A real import first creates a timestamped backup, adds only missing repository URLs, preserves other INI sections, and writes by atomic replacement.

## Automatic Path Detection

Default `reapack.ini` locations:

Windows:

```text
%APPDATA%\REAPER\reapack.ini
```

Linux:

```text
${XDG_CONFIG_HOME:-~/.config}/REAPER/reapack.ini
```

macOS:

```text
~/Library/Application Support/REAPER/reapack.ini
```

The GUI can also reuse a remembered manual path, detect a portable REAPER folder when `reaper.ini` and `reapack.ini` are together, and still lets you browse manually.

## CLI Usage

Help:

```bash
reapack-porter-cli --help
```

Linux and macOS examples:

```bash
./reapack-porter-cli export --zip
```

```bash
./reapack-porter-cli export \
  --source "/path/to/reapack.ini" \
  --out "/path/to/output" \
  --zip \
  --keep-folder
```

```bash
./reapack-porter-cli import \
  --bundle "/path/to/ReaPack-Porter-export.zip" \
  --target "/path/to/reapack.ini" \
  --dry-run
```

```bash
./reapack-porter-cli import \
  --bundle "/path/to/ReaPack-Porter-export.zip" \
  --target "/path/to/reapack.ini"
```

Windows examples can use `reapack-porter-cli.exe`.

Exit codes:

- `0`: success
- `2`: usage error
- `3`: REAPER running or process detection failure
- `4`: invalid input
- `5`: operational error
- `6`: unexpected internal error

## Bundle Contents

Folder and ZIP bundles are supported. An export bundle contains:

- `repos.tsv`
- `repos_urls.txt`
- `remotes_section.ini`
- `README_IMPORT.txt`

## Checksum Verification

Linux:

```bash
sha256sum -c ReaPack-Porter-0.1.0-linux-x86_64.tar.gz.sha256
```

macOS:

```bash
shasum -a 256 -c ReaPack-Porter-0.1.0-macos-arm64.zip.sha256
```

Windows PowerShell:

```powershell
$expected = (Get-Content .\ReaPack-Porter-0.1.0-windows-x86_64.zip.sha256).Split()[0]
$actual = (Get-FileHash .\ReaPack-Porter-0.1.0-windows-x86_64.zip -Algorithm SHA256).Hash.ToLower()
$actual -eq $expected
```

## Building From Source

```bash
python -m venv .venv
```

Linux and macOS:

```bash
source .venv/bin/activate
```

Windows:

```text
.venv\Scripts\activate
```

Then:

```bash
python -m pip install -e ".[dev,build]"
python -m pytest -q
python tools/build_release.py --target all --clean
```

PyInstaller must build on each target platform itself.

## Legacy Lua Tool

The original `reapack_porter.lua` ReaScript remains available. It still supports GUI export inside REAPER, and existing workflows can continue using it.

Reliable import should use the standalone application or standalone CLI while REAPER is closed.

## Legacy ReaScript Screenshots

These screenshots show the legacy ReaImGui interface running inside REAPER.

![Export tab](assets/reapack-porter_export.png)

![Import tab](assets/reapack-porter_import.png)

## Disclaimer

ReaPack Porter is an independent companion utility for ReaPack. It is not affiliated with, maintained by or endorsed by the developers of REAPER or ReaPack.
