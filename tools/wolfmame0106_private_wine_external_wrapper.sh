#!/bin/sh
# Stage337: external adapter so private playback tools can call the repository's
# guarded Wine launcher while keeping the emulator wrapper outside the checkout.
set -eu

fail() {
    printf '%s\n' "$1" >&2
    exit 64
}

launcher=$(printenv REPO_WINE_LAUNCHER 2>/dev/null || true)
[ -n "$launcher" ] || fail "REPO_WINE_LAUNCHER must name the guarded repository launcher"
case "$launcher" in
    /*) ;;
    *) fail "REPO_WINE_LAUNCHER must be an absolute path" ;;
esac
[ ! -L "$launcher" ] || fail "REPO_WINE_LAUNCHER must not be a symlink"
[ -f "$launcher" ] || fail "REPO_WINE_LAUNCHER must be a regular file"

exec sh "$launcher" "$@"
