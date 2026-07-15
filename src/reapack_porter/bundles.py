from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from zipfile import ZipFile

from .core import Remote, parse_remotes, render_remotes_section, sorted_bundle_remotes


class BundleError(RuntimeError):
    pass


def bundle_zip_path(bundle_dir: str | Path) -> Path:
    path = Path(bundle_dir)
    return path.parent / f"{path.name}.zip"


def _bundle_readme(source: str, repo_count: int, bundle_hint: str) -> str:
    generated = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return (
        "ReaPack portable export\n"
        f"Generated: {generated}\n"
        f"Source: {source}\n"
        f"Repos: {repo_count}\n"
        "\n"
        "Files:\n"
        "- repos_urls.txt      URLs only, one per line\n"
        "- remotes_section.ini complete [remotes] section\n"
        "\n"
        "Import:\n"
        "1) Close REAPER.\n"
        "2) Run this command:\n"
        f'   lua scripts/reapack_porter.lua import --bundle "{bundle_hint}"\n'
        "3) Start REAPER and run ReaPack > Synchronize packages.\n"
    )


def export_bundle(bundle_dir: str | Path, remotes: list[Remote], *, source: str) -> Path:
    target_dir = Path(bundle_dir)
    target_dir.mkdir(parents=True, exist_ok=True)

    ordered = sorted_bundle_remotes(remotes)
    repos_tsv_lines = [
        f"{remote.name}\t{remote.url}\t{remote.enabled}\t{remote.autosync}"
        for remote in ordered
    ]
    repos_urls_lines = [remote.url for remote in ordered]

    (target_dir / "repos.tsv").write_text("\n".join(repos_tsv_lines) + "\n", encoding="utf-8")
    (target_dir / "repos_urls.txt").write_text(
        "\n".join(repos_urls_lines) + "\n",
        encoding="utf-8",
    )
    (target_dir / "remotes_section.ini").write_text(
        render_remotes_section(ordered),
        encoding="utf-8",
    )
    (target_dir / "README_IMPORT.txt").write_text(
        _bundle_readme(source, len(ordered), str(target_dir)),
        encoding="utf-8",
    )
    return target_dir


def create_bundle_zip(bundle_dir: str | Path, zip_path: str | Path | None = None) -> Path:
    source_dir = Path(bundle_dir)
    if not source_dir.is_dir():
        raise BundleError(f"Bundle folder not found: {source_dir}")

    target_zip = Path(zip_path) if zip_path is not None else bundle_zip_path(source_dir)
    with ZipFile(target_zip, "w") as archive:
        for child in sorted(source_dir.rglob("*")):
            if child.is_file():
                archive.write(child, source_dir.name + "/" + str(child.relative_to(source_dir)))
    return target_zip


def _reject_unsafe_zip_name(name: str) -> None:
    if "\\" in name:
        raise BundleError(f"Unsafe ZIP entry path: {name}")
    if len(name) >= 2 and name[1] == ":":
        raise BundleError(f"Unsafe ZIP entry path: {name}")
    path = PurePosixPath(name)
    if path.is_absolute():
        raise BundleError(f"Unsafe ZIP entry path: {name}")
    if any(part == ".." for part in path.parts):
        raise BundleError(f"Unsafe ZIP entry path: {name}")


def _find_bundle_member(names: list[str]) -> str:
    normalized = [name for name in names if not name.endswith("/")]
    root = "remotes_section.ini"
    if root in normalized:
        return root

    nested = [
        name
        for name in normalized
        if PurePosixPath(name).name == "remotes_section.ini" and len(PurePosixPath(name).parts) == 2
    ]
    top_levels = {PurePosixPath(name).parts[0] for name in nested}
    if len(nested) == 1 and len(top_levels) == 1:
        return nested[0]
    raise BundleError("ZIP does not contain remotes_section.ini in the root or one nested bundle folder.")


def load_bundle_remotes(bundle_path: str | Path) -> list[Remote]:
    path = Path(bundle_path)
    if path.is_dir():
        remotes_path = path / "remotes_section.ini"
        if not remotes_path.is_file():
            raise BundleError(f"Bundle folder does not contain remotes_section.ini: {path}")
        with remotes_path.open("r", encoding="utf-8", newline="") as handle:
            parsed = parse_remotes(handle.read())
        if not parsed.remotes:
            raise BundleError("No repositories found in imported remotes_section.ini")
        return parsed.remotes

    if path.suffix.lower() != ".zip":
        raise BundleError(f"Unsupported bundle path: {path}")
    if not path.is_file():
        raise FileNotFoundError(f"Bundle file not found: {path}")

    with ZipFile(path) as archive:
        names = archive.namelist()
        for name in names:
            _reject_unsafe_zip_name(name)
        member = _find_bundle_member(names)
        data = archive.read(member).decode("utf-8")
    parsed = parse_remotes(data)
    if not parsed.remotes:
        raise BundleError("No repositories found in imported remotes_section.ini")
    return parsed.remotes
