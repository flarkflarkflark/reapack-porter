from __future__ import annotations

from pathlib import Path


WORKFLOW = Path(__file__).resolve().parents[1] / ".github" / "workflows" / "release.yml"


def _text() -> str:
    return WORKFLOW.read_text(encoding="utf-8")


def _uses_lines(text: str) -> list[str]:
    return [line.strip().removeprefix("uses: ") for line in text.splitlines() if line.strip().startswith("uses: ")]


def _plain_run_scalar_offenders(text: str) -> list[tuple[int, str]]:
    offenders: list[tuple[int, str]] = []
    for line_number, line in enumerate(text.splitlines(), 1):
        stripped = line.lstrip()
        if not stripped.startswith("run: "):
            continue
        scalar = stripped.removeprefix("run: ")
        if ": " in scalar:
            offenders.append((line_number, line))
    return offenders


def test_release_workflow_exists_and_has_safe_triggers() -> None:
    text = _text()
    trigger_block = text.split("\npermissions:", maxsplit=1)[0]
    assert WORKFLOW.is_file()
    assert text.startswith("name: Build release candidate\n")
    assert "workflow_dispatch:" in trigger_block
    assert 'tags:\n      - "v*.*.*"' in trigger_block
    assert "pull_request_target" not in trigger_block
    assert "pull_request:" not in trigger_block
    assert "release:" not in trigger_block
    assert "schedule:" not in trigger_block
    assert "branches:" not in trigger_block


def test_release_workflow_permissions_and_concurrency() -> None:
    text = _text()
    assert "permissions:\n  contents: read" in text
    assert "group: release-${{ github.ref }}" in text
    assert "cancel-in-progress: false" in text
    assert text.count("contents: write") == 1
    draft_section = text.split("create-draft-release:", maxsplit=1)[1]
    assert "contents: write" in draft_section


def test_build_job_uses_local_reusable_workflow_without_write_permissions() -> None:
    text = _text()
    build_section = text.split("  build:", maxsplit=1)[1].split("  collect:", maxsplit=1)[0]
    assert "uses: ./.github/workflows/build-artifacts.yml" in build_section
    assert "contents: read" in build_section
    assert "contents: write" not in build_section
    assert "secrets:" not in build_section


def test_collect_job_downloads_verifies_and_uploads_candidate() -> None:
    text = _text()
    collect = text.split("  collect:", maxsplit=1)[1].split("  create-draft-release:", maxsplit=1)[0]
    assert "runs-on: ubuntu-22.04" in collect
    assert "actions/checkout@v7" in collect
    assert "actions/download-artifact@v8" in collect
    assert "actions/upload-artifact@v7" in collect
    assert "pattern: ReaPack-Porter-*" in collect
    assert "merge-multiple: true" in collect
    assert "path: release-assets" in collect
    assert "python tools/package_artifacts.py verify-set" in collect
    assert "--manifest release-assets/SHA256SUMS.txt" in collect
    assert "retention-days: 30" in collect
    assert "version:" in collect
    assert "expected-tag:" in collect
    assert "candidate-artifact-name:" in collect
    assert "git fetch origin main --no-tags" in collect
    assert 'TAG_SHA="$(git rev-list -n 1 "$GITHUB_REF_NAME")"' in collect
    assert '[[ "$GITHUB_SHA" != "$TAG_SHA" ]]' in collect
    assert 'git merge-base --is-ancestor "$GITHUB_SHA" origin/main' in collect
    assert '[[ "${GITHUB_REF_NAME}" != "$EXPECTED_TAG" ]]' in collect


def test_draft_release_job_only_runs_for_tag_push_and_creates_draft() -> None:
    text = _text()
    draft = text.split("  create-draft-release:", maxsplit=1)[1]
    assert "if: github.event_name == 'push' && github.ref_type == 'tag'" in draft
    assert "workflow_dispatch" not in draft
    assert "runs-on: ubuntu-22.04" in draft
    assert "actions/checkout@v7" in draft
    assert "actions/download-artifact@v8" in draft
    assert "path: release-ready" in draft
    assert "python tools/package_artifacts.py verify-set" in draft
    assert "gh release view \"$TAG\"" in draft
    assert "gh release create \"$TAG\"" in draft
    assert "--verify-tag" in draft
    assert "--draft" in draft
    assert "--notes-file docs/release-notes/v0.1.0.md" in draft
    assert "--generate-notes" not in draft
    assert "--prerelease" not in draft


def test_release_workflow_uses_only_expected_actions_and_no_secrets_or_pat() -> None:
    text = _text()
    assert _uses_lines(text) == [
        "./.github/workflows/build-artifacts.yml",
        "actions/checkout@v7",
        "actions/setup-python@v6",
        "actions/download-artifact@v8",
        "actions/upload-artifact@v7",
        "actions/checkout@v7",
        "actions/setup-python@v6",
        "actions/download-artifact@v8",
    ]
    assert "secrets." not in text
    assert "PAT" not in text
    assert "pull_request_target" not in text
    assert _plain_run_scalar_offenders(text) == []


def test_release_jobs_pin_python_311_before_python_commands() -> None:
    text = _text()
    collect = text.split("  collect:", maxsplit=1)[1].split("  create-draft-release:", maxsplit=1)[0]
    draft = text.split("  create-draft-release:", maxsplit=1)[1]

    assert collect.count("uses: actions/setup-python@v6") == 1
    assert collect.count('python-version: "3.11"') == 1
    collect_checkout = collect.index("uses: actions/checkout@v7")
    collect_setup = collect.index("uses: actions/setup-python@v6")
    collect_version = collect.index('python-version: "3.11"')
    collect_validate = collect.index("- name: Validate version and tag")
    assert collect_checkout < collect_setup < collect_version < collect_validate
    assert collect_setup < collect.index("import tomllib")
    assert collect_setup < collect.index("python tools/package_artifacts.py verify-set")
    assert collect_setup < collect.index("python - <<'PY'")

    assert draft.count("uses: actions/setup-python@v6") == 1
    assert draft.count('python-version: "3.11"') == 1
    draft_checkout = draft.index("uses: actions/checkout@v7")
    draft_setup = draft.index("uses: actions/setup-python@v6")
    draft_version = draft.index('python-version: "3.11"')
    draft_validate = draft.index("- name: Validate release candidate")
    assert draft_checkout < draft_setup < draft_version < draft_validate
    assert draft_setup < draft.index("python tools/package_artifacts.py verify-set")


def test_release_workflow_uploads_or_publishes_exact_checked_asset_set() -> None:
    text = _text()
    for filename in [
        "ReaPack-Porter-0.1.0-linux-x86_64.tar.gz",
        "ReaPack-Porter-0.1.0-linux-x86_64.tar.gz.sha256",
        "ReaPack-Porter-0.1.0-macos-arm64.zip",
        "ReaPack-Porter-0.1.0-macos-arm64.zip.sha256",
        "ReaPack-Porter-0.1.0-macos-x86_64.zip",
        "ReaPack-Porter-0.1.0-macos-x86_64.zip.sha256",
        "ReaPack-Porter-0.1.0-windows-x86_64.zip",
        "ReaPack-Porter-0.1.0-windows-x86_64.zip.sha256",
        "SHA256SUMS.txt",
    ]:
        assert filename in text
    assert '"${#ASSETS[@]}" -ne 9' in text
