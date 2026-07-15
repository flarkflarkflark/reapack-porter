from __future__ import annotations

from pathlib import Path


WORKFLOW = Path(__file__).resolve().parents[1] / ".github" / "workflows" / "build-artifacts.yml"


def _workflow_text() -> str:
    return WORKFLOW.read_text(encoding="utf-8")


def test_workflow_has_expected_triggers_and_no_publication_triggers() -> None:
    text = _workflow_text()
    assert "workflow_dispatch:" in text
    assert "push:" in text
    assert "feature/standalone-app" in text
    assert "pull_request:" in text
    assert "pull_request_target" not in text
    assert "release:" not in text
    assert "tags:" not in text


def test_workflow_permissions_and_concurrency_are_read_only() -> None:
    text = _workflow_text()
    assert "permissions:\n  contents: read" in text
    assert "group: build-artifacts-${{ github.workflow }}-${{ github.ref }}" in text
    assert "cancel-in-progress: true" in text
    assert "contents: write" not in text
    assert "continue-on-error" not in text


def test_workflow_matrix_is_exact() -> None:
    text = _workflow_text()
    expected = [
        ("ubuntu-22.04", "linux", "x86_64", "ReaPack-Porter-linux-x86_64"),
        ("windows-2022", "windows", "x86_64", "ReaPack-Porter-windows-x86_64"),
        ("macos-15-intel", "macos", "x86_64", "ReaPack-Porter-macos-x86_64"),
        ("macos-15", "macos", "arm64", "ReaPack-Porter-macos-arm64"),
    ]
    assert text.count("- runner:") == 4
    for runner, platform, arch, artifact in expected:
        assert f"runner: {runner}" in text
        assert f"platform-id: {platform}" in text
        assert f"arch-id: {arch}" in text
        assert f"artifact-id: {artifact}" in text
    assert "latest" not in text
    assert "self-hosted" not in text


def test_workflow_uses_only_expected_actions_and_versions() -> None:
    text = _workflow_text()
    assert "uses: actions/checkout@v7" in text
    assert "uses: actions/setup-python@v6" in text
    assert "uses: actions/upload-artifact@v4" in text
    assert text.count("uses: ") == 3
    assert 'python-version: "3.11"' in text
    assert '"PyInstaller==6.19.0"' in text


def test_workflow_plain_run_scalars_do_not_contain_colon_space() -> None:
    offenders: list[tuple[int, str]] = []

    for line_number, line in enumerate(_workflow_text().splitlines(), 1):
        stripped = line.lstrip()
        if not stripped.startswith("run: "):
            continue
        scalar = stripped.removeprefix("run: ")
        if ": " in scalar:
            offenders.append((line_number, line))

    assert offenders == []


def test_workflow_runs_validation_build_verify_package_and_uploads_only_artifact_files() -> None:
    text = _workflow_text()
    assert "python -m pytest -q" in text
    assert "python -m compileall -q src tools" in text
    assert "python -m reapack_porter --help" in text
    assert "import reapack_porter.gui, reapack_porter.tooltip, reapack_porter.operations" in text
    assert "python tools/build_release.py --target all --clean" in text
    assert "python tools/verify_frozen_build.py --platform ${{ matrix.platform-id }} --arch ${{ matrix.arch-id }} --dist-dir dist" in text
    assert "python tools/package_artifacts.py --platform ${{ matrix.platform-id }} --arch ${{ matrix.arch-id }} --dist-dir dist --output-dir release --force" in text
    assert "python tools/package_artifacts.py verify --archive" in text
    assert "if-no-files-found: error" in text
    assert "retention-days: 14" in text
    assert "release/" not in text.split("path: |", maxsplit=1)[1]


def test_workflow_colon_bearing_checks_use_block_scalars() -> None:
    text = _workflow_text()
    assert "Verify PyInstaller version\n        run: >-" in text
    assert "Check runner architecture\n        run: >-" in text
    assert "Unexpected PyInstaller version: " in text
    assert "Architecture mismatch: expected " in text
