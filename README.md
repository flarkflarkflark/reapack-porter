# ReaPack Porter

ReaPack Porter exports and imports REAPER ReaPack repository lists, so you can move your ReaPack setup between systems with one portable ZIP.

## Features

- Export ReaPack repositories from `reapack.ini`
- Create a portable ZIP for transfer by USB, network, mail, or cloud
- Import from a ZIP or folder
- Skip repositories that already exist
- Create a timestamped backup before import
- ReaImGui GUI inside REAPER with simple dialog fallback
- CLI mode for automation

## Dependencies

Required:

- REAPER with Lua/ReaScript, or standalone Lua for CLI use

Optional:

- ReaImGui: enables the tabbed GUI inside REAPER
- js_ReaScriptAPI: enables folder browse dialogs in the GUI
- `zip` and `unzip` on Linux/macOS: needed for ZIP export/import
- PowerShell `Compress-Archive` and `Expand-Archive` on Windows: needed for ZIP export/import

Without ReaImGui, the script falls back to REAPER's built-in dialogs. Without ZIP tooling, folder export still works as a fallback.

## Screenshots

![Export tab](assets/reapack-porter_export.png)

![Import tab](assets/reapack-porter_import.png)

## REAPER Usage

1. Copy `reapack_porter.lua` into your REAPER Scripts folder.
2. In REAPER, open `Actions > Show action list`.
3. Click `Load...` and select `reapack_porter.lua`.
4. Run the action.

When ReaImGui is installed, ReaPack Porter opens a tabbed GUI. Without ReaImGui, it falls back to REAPER's built-in dialogs.

## CLI Usage

Export repositories:

```bash
lua reapack_porter.lua export --zip
```

Import repositories:

```bash
lua reapack_porter.lua import --bundle "/path/to/reapack-portable.zip"
```

Optional paths:

```bash
lua reapack_porter.lua export --source "/path/to/reapack.ini" --out "/path/to/output" --zip
lua reapack_porter.lua import --bundle "/path/to/bundle-or.zip" --target "/path/to/reapack.ini"
```

## Import Safety

Before import, ReaPack Porter creates a timestamped backup of the target `reapack.ini`, for example:

```text
reapack.ini.bak.20260529-161947
```

If a backup already exists for the same second, a suffix is added:

```text
reapack.ini.bak.20260529-161947-1
```

Existing repository URLs are detected and skipped. Only missing URLs are added.
