#!/usr/bin/env python3
"""Fail-closed privacy check of the STAGED Git index for a public code-only repo.

Run before every commit or push. No private filenames, staged blob bytes,
SHA values, full paths, or unexpected exception text are printed. CI uses
the same checker as the optional local pre-commit hook. This CANNOT undo
data already pushed or protect the history of a public repository.
"""
import argparse
import json
from pathlib import Path, PurePosixPath
import subprocess

MAX_SOURCE_BYTES = 256 * 1024
TEXT_SUFFIXES = frozenset({
    '.py', '.c', '.h', '.md', '.yml', '.yaml', '.json', '.txt', '.sh',
    '.lua', '.toml', '.xml', '.ini', '.cfg', '.gitignore',
})
SPECIAL_FILENAMES = frozenset({'Makefile', '.gitignore', '.gitattributes'})
FORBIDDEN_SUFFIXES = frozenset({
    '.zip', '.7z', '.rar', '.chd', '.bin', '.iso', '.cue', '.rom',
    '.gen', '.mdf', '.nro', '.nsp', '.xci', '.nca', '.nacp',
    '.nes', '.sfc', '.smc', '.gba', '.gb', '.gbc', '.n64',
    '.z64', '.v64', '.elf', '.exe', '.dll', '.so', '.a',
    '.png', '.jpg', '.jpeg', '.webp', '.bmp', '.tga',
})
FORBIDDEN_COMPONENTS = frozenset({
    'roms', 'mame-roms', 'game-roms', 'cps1-captures',
    'captures', 'local_outputs', 'palette_snapshots', 'private-roms',
    'private-captures', 'build',
})
BINARY_HEADERS = (
    b'PK\x03\x04', b'PK\x05\x06', b'Rar!\x1a\x07',
    b'7z\xbc\xaf\x27\x1c', b'\x7fELF', b'NES\x1a',
    b'MComprHD', b'\x1f\x8b',
)
LFS_HEADER = b'version https://git-lfs.github.com/spec/v1'


def _git(repository, *arguments):
    return subprocess.run(
        ['git', '-C', str(repository), *arguments],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        check=True, timeout=20).stdout


def check_staged_git_tree(repository):
    """Scan index blob IDs, not the possibly different working tree files."""
    index = _git(repository, 'ls-files', '--stage', '-z')
    problems = {
        'forbidden_paths': 0,
        'oversized_source_blobs': 0,
        'non_source_content': 0,
        'unsafe_git_entries': 0,
    }
    examined = 0
    for entry in filter(None, index.split(b'\0')):
        examined += 1
        try:
            metadata, raw_path = entry.split(b'\t', 1)
            mode, blob_id, stage = metadata.decode('ascii').split()
            path = raw_path.decode('utf-8', 'surrogateescape')
            parts = PurePosixPath(path).parts
            suffix = PurePosixPath(path).suffix.lower()
        except (ValueError, UnicodeError):
            problems['unsafe_git_entries'] += 1
            continue
        if (mode not in ('100644', '100755') or stage != '0' or
                not parts or path.startswith('/') or '..' in parts):
            problems['unsafe_git_entries'] += 1
            continue
        if (any(part.lower() in FORBIDDEN_COMPONENTS for part in parts[:-1])
                or suffix in FORBIDDEN_SUFFIXES or
                (suffix not in TEXT_SUFFIXES and parts[-1] not in SPECIAL_FILENAMES
                 and path != '.githooks/pre-commit')):
            problems['forbidden_paths'] += 1
            continue
        try:
            size = int(_git(repository, 'cat-file', '-s', blob_id).strip())
            if size > MAX_SOURCE_BYTES:
                problems['oversized_source_blobs'] += 1
                continue
            blob = _git(repository, 'cat-file', 'blob', blob_id)
        except (OSError, ValueError, subprocess.CalledProcessError,
                subprocess.TimeoutExpired):
            problems['unsafe_git_entries'] += 1
            continue
        if (len(blob) != size or b'\0' in blob or
                blob.startswith(LFS_HEADER) or
                any(blob.startswith(header) for header in BINARY_HEADERS)):
            problems['non_source_content'] += 1
    # Empty index is not a verified public code tree.
    if not examined:
        problems['unsafe_git_entries'] += 1
    return {
        'status': 'PUBLIC_CODE_TREE_ROM_FREE_METADATA_CHECK_PASSED'
        if not any(problems.values()) else 'PUBLIC_CODE_TREE_PRIVACY_CHECK_REFUSED',
        'tracked_entries_examined': examined,
        'rejected_entry_count': sum(problems.values()),
        'fixed_reason_counts': problems,
        'private_paths_or_blob_bytes_emitted': False,
        'untracked_files_checked': False,
        'git_history_checked': False,
        'license_or_copyright_rights_verified': False,
        'original_game_authenticity_verified': False,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repository', type=Path,
                        default=Path(__file__).resolve().parents[1])
    args = parser.parse_args(argv)
    try:
        report = check_staged_git_tree(args.repository)
    except Exception:
        # If Git fails, never reveal paths, ROM bytes or exception messages.
        report = {
            'status': 'PUBLIC_CODE_TREE_PRIVACY_CHECK_REFUSED',
            'rejected_entry_count': 1,
            'fixed_reason_counts': {'git_index_unavailable': 1},
            'private_paths_or_blob_bytes_emitted': False,
        }
    print(json.dumps(report, sort_keys=True))
    return 0 if report['status'] == 'PUBLIC_CODE_TREE_ROM_FREE_METADATA_CHECK_PASSED' else 2


if __name__ == '__main__':
    raise SystemExit(main())
