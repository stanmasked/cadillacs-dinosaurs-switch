"""Privacy-preserving failure classifications for the private MAME CLI."""
import io
import json
import unittest

from tools.mame_private_cli_errors import (
    public_failure_report, write_private_failure,
)


class PrivateCliErrorTests(unittest.TestCase):
    def test_all_codes_and_messages_are_fixed_safe_literals(self):
        samples = (
            (ValueError('Private workspace must have 0700-style permissions'),
             'PRIVATE_WORKSPACE_INVALID'),
            (ValueError('MAME identity/session-aware linked probe verification failed'),
             'MAME_BUILD_OR_IDENTITY_UNVERIFIED'),
            (ValueError('No private dino set entry found for first-run preflight'),
             'PRIVATE_ROM_LAYOUT_INVALID'),
            (ValueError('Local MAME session timed out; private files retained'),
             'LOCAL_MAME_PROCESS_FAILED'),
            (ValueError('Private capture is incomplete or invalid; no verified report'),
             'PRIVATE_CAPTURE_AUDIT_REFUSED'),
            (TypeError('preflight_only must be boolean'),
             'INVALID_LAUNCH_ARGUMENTS'),
            (OSError(13, 'Permission denied', '/local/private/dino.zip'),
             'PRIVATE_FILESYSTEM_ERROR'),
            (RuntimeError('PRIVATE_TOKEN'), 'UNEXPECTED_PRIVATE_LAUNCH_FAILURE'),
        )
        for error, expected in samples:
            with self.subTest(code=expected):
                report = public_failure_report(error)
                self.assertEqual(report['reason_code'], expected)
                self.assertEqual(report['status'], 'PRIVATE_MAME_CAPTURE_REFUSED')
                self.assertFalse(report['frame_sync_verified'])
                self.assertFalse(report['pixel_parity_eligible'])

    def test_messages_can_contain_sensitive_data_without_leaking_it(self):
        secrets = (
            '/mnt/secrets/private-original-dino.zip',
            'CPS1_DINO_CAPTURE_SESSION=00000000000000000000000000000001',
            'ROM_BYTES_SUPER_SECRET',
        )
        for secret in secrets:
            for error in (ValueError('capture failed ' + secret),
                          FileNotFoundError(2, 'Missing', secret),
                          RuntimeError('bad path ' + secret)):
                with self.subTest(error=type(error).__name__):
                    stream = io.StringIO()
                    write_private_failure(error, stream)
                    line = stream.getvalue()
                    self.assertNotIn(secret, line)
                    self.assertNotIn('Traceback', line)
                    self.assertNotIn('filename', line)
                    parsed = json.loads(line)
                    self.assertFalse(parsed['private_paths_disclosed'])
                    self.assertFalse(parsed['gameplay_verified'])

    def test_arbitrary_unknown_errors_never_echo_private_data(self):
        error = ValueError('CUSTOM_PRIVACY_SECRET /home/user/private/mame')
        report = public_failure_report(error)
        self.assertEqual(report['reason_code'], 'PRIVATE_LAUNCH_REJECTED')
        text = json.dumps(report)
        self.assertNotIn('CUSTOM_PRIVACY_SECRET', text)
        self.assertNotIn('/home/user', text)


if __name__ == '__main__':
    unittest.main()
