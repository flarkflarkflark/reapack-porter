# Changelog

## [0.1.1]

### Fixed

- ReaPack Porter can now read existing `reapack.ini` files using Windows-1252 / legacy Windows ANSI encoding instead of crashing on non-UTF-8 characters.
- Export, Preview Import, and Real Import all support these configs.
- Import preserves the original supported config encoding, including UTF-8, UTF-8 with BOM, and Windows-1252, and keeps existing backup and atomic-write protections in place.
- Import safely rejects repository names that cannot be represented in the target config encoding before modifying the target or creating a backup.

## [0.1.0]

### Added

- Standalone cross-platform GUI
- Standalone CLI
- Folder and ZIP export bundles
- Safe import preview and dry-run
- REAPER process guard
- URL normalization and duplicate skipping
- Timestamped backups and atomic writes
- Automatic path detection and persistent path settings
- GUI tooltips
- Frozen Linux, Windows and macOS builds
- SHA256 sidecars
- Cross-platform GitHub Actions validation

### Legacy

- `reapack_porter.lua` remains available for existing workflows.
