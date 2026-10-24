"""Select a still-live exact SHA-pinned public MAME 0.106 ROM-free CI artifact.

This only selects a technical build; it NEVER downloads original game data
or claims ROM verification. GitHub metadata must match the frozen artifact
ZIP digest and byte count, then the native probe independently hashes every
extracted file before execution.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
import re
import sys
from urllib import request, error

NAME = "historical-mame0106-runtime-rom-free"
# Original immutable artifact ID 12461451785 on GitHub run #39859311511.
ARCHIVE_SHA256 = "5a495bdcbe832dbe1261fc935ef0f8db2f36c7eb21ad3c0be19385d87da5781a"
# Stage383 exact 12-file rearchive: every member SHA matches ARCHIVE_SHA256
# byte-for-byte, despite changed outer ZIP metadata. No rebuilt exe accepted.
RENEWED_ARCHIVE_SHA256 = "c9296bcc2608dae2ab82494ea89ad6a5f3850a3e145fce620272b798858bb53a"
ALLOWED_ARCHIVE_SHA256 = frozenset((ARCHIVE_SHA256, RENEWED_ARCHIVE_SHA256))
ARCHIVE_SIZE = 41450235
OWNER = "stanmasked"
REPOSITORY = "cadillacs-dinosaurs-switch"
MAX_PAGES = 5
MAX_RESULTS = 100
MAX_BODY_BYTES = 400_000
PIN = re.compile(r"[a-f0-9]{64}\Z")
GITHUB_RUN_ID = re.compile(r"[1-9][0-9]{0,17}\Z")


class ArtifactSelectionError(Exception):
    """Error codes never contain access tokens or API response bodies."""


def _parse_utc(value: object) -> datetime:
    if type(value) is not str or len(value) > 40:
        raise ArtifactSelectionError("invalid_artifact_timestamp")
    try:
        stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ArtifactSelectionError("invalid_artifact_timestamp") from exc
    if stamp.tzinfo is None:
        raise ArtifactSelectionError("timestamp_timezone_missing")
    return stamp.astimezone(timezone.utc)


def choose(pages: list[dict], now: datetime) -> dict[str, object]:
    """Pure offline selector. Old, expired, unknown-digest builds fail closed."""
    if not pages or now.tzinfo is None or any(not PIN.fullmatch(x) for x in ALLOWED_ARCHIVE_SHA256):
        raise ArtifactSelectionError("selector_inputs_invalid")
    candidates = []
    for page in pages:
        if type(page) is not dict or type(page.get("artifacts")) is not list:
            raise ArtifactSelectionError("invalid_artifact_page")
        for item in page["artifacts"]:
            if type(item) is not dict:
                raise ArtifactSelectionError("invalid_artifact_entry")
            workflow = item.get("workflow_run")
            if (item.get("name") != NAME or item.get("expired") is not False or
                    type(item.get("size_in_bytes")) is not int or
                    item["size_in_bytes"] != ARCHIVE_SIZE or
                    item.get("digest") not in {
                        "sha256:" + pin for pin in ALLOWED_ARCHIVE_SHA256
                    } or type(workflow) is not dict):
                continue
            run_id = workflow.get("id")
            if type(run_id) is not int or not GITHUB_RUN_ID.fullmatch(str(run_id)):
                continue
            expiration = _parse_utc(item.get("expires_at"))
            creation = _parse_utc(item.get("created_at"))
            if expiration <= now.astimezone(timezone.utc) or creation > now.astimezone(timezone.utc):
                continue
            if type(item.get("id")) is not int or item["id"] <= 0:
                continue
            candidates.append((creation, expiration, run_id, item["id"], item["digest"][7:]))
    if not candidates:
        raise ArtifactSelectionError("no_live_exact_pinned_romfree_artifact")
    created, expiration, run_id, artifact_id, approved_digest = max(candidates)
    return {
        "status": "exact_pinned_romfree_artifact_found",
        "run_id": run_id,
        "artifact_id": artifact_id,
        "archive_sha256": approved_digest,
        "expires_at": expiration.isoformat(),
        "original_game_data_included": False,
    }


def query(token: str) -> list[dict]:
    """GET only repository artifact metadata, never external private Drive data."""
    if not token or any(c.isspace() for c in token):
        raise ArtifactSelectionError("missing_or_invalid_github_token")
    pages = []
    for page in range(1, MAX_PAGES + 1):
        url = (
            f"https://api.github.com/repos/{OWNER}/{REPOSITORY}/actions/artifacts"
            f"?name={NAME}&per_page={MAX_RESULTS}&page={page}"
        )
        req = request.Request(url, headers={
            "Authorization": "Bearer " + token,
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "cadillacs-romfree-pinned-locator",
        })
        try:
            with request.urlopen(req, timeout=25) as response:
                raw = response.read(MAX_BODY_BYTES + 1)
        except (OSError, error.HTTPError) as exc:
            raise ArtifactSelectionError("artifact_metadata_request_failed") from exc
        if len(raw) > MAX_BODY_BYTES:
            raise ArtifactSelectionError("artifact_metadata_oversized")
        try:
            result = json.loads(raw.decode("utf-8"))
        except (UnicodeError, ValueError) as exc:
            raise ArtifactSelectionError("artifact_metadata_invalid_json") from exc
        if type(result) is not dict or type(result.get("artifacts")) is not list:
            raise ArtifactSelectionError("artifact_metadata_invalid_page")
        pages.append(result)
        if len(result["artifacts"]) < MAX_RESULTS:
            break
    return pages


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", help="GitHub Actions GITHUB_OUTPUT path")
    args = parser.parse_args(argv)
    try:
        selected = choose(query(os.getenv("GITHUB_TOKEN", "")), datetime.now(timezone.utc))
        print("status=" + selected["status"])
        print("chosen_run_id=" + str(selected["run_id"]))
        print("original_game_data_included=False")
        # Only public run ID and immutable digest are exposed.
        if args.output:
            with open(args.output, "a", encoding="utf-8") as output:
                output.write(f"run_id={selected['run_id']}\n")
                output.write(f"artifact_id={selected['artifact_id']}\n")
        return 0
    except (ArtifactSelectionError, OSError):
        print("status=exact_romfree_artifact_unavailable")
        print("original_game_data_included=False")
        return 2


if __name__ == "__main__":
    sys.exit(main())
