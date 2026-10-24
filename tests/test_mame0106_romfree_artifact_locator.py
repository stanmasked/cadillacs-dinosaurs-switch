"""Stage382 synthetic metadata only; no ROMs, binaries, tokens or network."""
from datetime import datetime, timezone, timedelta
import unittest
from unittest.mock import patch
from tools import mame0106_romfree_artifact_locator as p


class RomfreeArtifactLocatorTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 10, 24, 9, 0, tzinfo=timezone.utc)
        self.fixture = {
            "id": 12461451785,
            "name": p.NAME,
            "size_in_bytes": p.ARCHIVE_SIZE,
            "digest": "sha256:" + p.ARCHIVE_SHA256,
            "expired": False,
            "created_at": "2026-10-23T20:00:00Z",
            "expires_at": "2026-10-25T20:00:00Z",
            "workflow_run": {"id": 39859311511}
        }

    def select(self, *artifacts, now=None):
        return p.choose([{"artifacts": list(artifacts)}], now or self.now)

    def test_exact_artifact_chosen_without_original_game(self):
        answer = self.select(self.fixture)
        self.assertEqual(answer["run_id"], 39859311511)
        self.assertEqual(answer["archive_sha256"], p.ARCHIVE_SHA256)
        self.assertIs(answer["original_game_data_included"], False)

    def test_stage383_renewed_90day_zip_is_preapproved(self):
        renewed = dict(self.fixture,
                       id=12551316232,
                       digest="sha256:" + p.RENEWED_ARCHIVE_SHA256,
                       created_at="2026-10-24T09:00:00Z",
                       expires_at="2027-01-22T06:29:55Z",
                       workflow_run={"id": 40070433630})
        selected = self.select(self.fixture, renewed, now=self.now.replace(hour=10))
        self.assertEqual(selected["run_id"], 40070433630)
        self.assertEqual(selected["artifact_id"], 12551316232)
        self.assertEqual(selected["archive_sha256"], p.RENEWED_ARCHIVE_SHA256)
        self.assertFalse(selected["original_game_data_included"])

    def test_stage383_newly_compiled_executable_not_an_approved_zip(self):
        # A successful source compile is NOT equivalent to the frozen EXE.
        for other in (
                "9f6a1acec78c103013bbe516109b6636863703176d7ba5d0414e0097877e9bea",
                "f12ba8b5702c19b5b43a69379ba371f9bcb5f71fb67d9c128629e17f5b73dcd0",
        ):
            with self.subTest(digest=other):
                candidate = dict(self.fixture, digest="sha256:" + other)
                with self.assertRaisesRegex(p.ArtifactSelectionError, "no_live_exact"):
                    self.select(candidate)

    def test_newest_matching_run_selected(self):
        next_one = dict(self.fixture, id=999,
                        created_at="2026-10-24T08:00:00Z",
                        expires_at="2026-10-27T10:00:00Z",
                        workflow_run={"id": 40000000001})
        answer = self.select(self.fixture, next_one)
        self.assertEqual(answer["run_id"], 40000000001)
        self.assertEqual(answer["artifact_id"], 999)

    def test_malicious_digest_mismatch_rejected(self):
        bad = dict(self.fixture, digest="sha256:" + "0"*64)
        with self.assertRaisesRegex(p.ArtifactSelectionError, "no_live_exact"):
            self.select(bad)

    def test_artifact_expired_even_when_flag_is_false(self):
        bad = dict(self.fixture, expires_at="2026-10-24T08:00:00Z")
        with self.assertRaisesRegex(p.ArtifactSelectionError, "no_live_exact"):
            self.select(bad)

    def test_flag_expired_rejected(self):
        with self.assertRaisesRegex(p.ArtifactSelectionError, "no_live_exact"):
            self.select(dict(self.fixture, expired=True))

    def test_romfree_artifact_name_is_mandatory(self):
        with self.assertRaisesRegex(p.ArtifactSelectionError, "no_live_exact"):
            self.select(dict(self.fixture, name="dino-private-rom.zip"))

    def test_byte_count_is_mandatory(self):
        with self.assertRaisesRegex(p.ArtifactSelectionError, "no_live_exact"):
            self.select(dict(self.fixture, size_in_bytes=p.ARCHIVE_SIZE+1))

    def test_workflow_run_must_be_valid(self):
        for bad in ({}, {"id": 0}, {"id": "39859311511"}, None):
            with self.subTest(run=bad):
                with self.assertRaisesRegex(p.ArtifactSelectionError, "no_live_exact"):
                    self.select(dict(self.fixture, workflow_run=bad))

    def test_unknown_future_artifact_is_rejected(self):
        with self.assertRaisesRegex(p.ArtifactSelectionError, "no_live_exact"):
            self.select(dict(self.fixture, created_at="2026-10-25T09:00:00Z"))

    def test_wrong_page_schema_fails_closed(self):
        with self.assertRaisesRegex(p.ArtifactSelectionError, "invalid_artifact_page"):
            p.choose([{"artifact": [self.fixture]}], self.now)
        with self.assertRaisesRegex(p.ArtifactSelectionError, "invalid_artifact_entry"):
            p.choose([{"artifacts": [None]}], self.now)

    def test_no_hardcoded_run_fallback(self):
        with self.assertRaisesRegex(p.ArtifactSelectionError, "no_live_exact"):
            self.select()

    def test_timezone_aware_selection_is_required(self):
        with self.assertRaisesRegex(p.ArtifactSelectionError, "selector_inputs_invalid"):
            p.choose([{"artifacts": [self.fixture]}], datetime(2026,10,24,9))

    def test_multiple_pages_choose_newest(self):
        old = self.fixture
        fresh = dict(old, created_at="2026-10-24T06:00:00Z",
                     expires_at="2026-10-28T06:00:00Z", id=1000,
                     workflow_run={"id": 40000000111})
        result = p.choose([{"artifacts": [old]}, {"artifacts": [fresh]}], self.now)
        self.assertEqual(result["run_id"], 40000000111)

    def test_no_live_artifact_before_any_git_download(self):
        with patch.object(p, "query", return_value=[{"artifacts": []}]):
            self.assertEqual(p.main([]), 2)


if __name__ == "__main__":
    unittest.main()
