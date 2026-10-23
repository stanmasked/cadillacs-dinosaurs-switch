#!/bin/sh
# Stage333: safe local Wine launcher for the private MAME 0.106 audit tools.
# Original ROM, INP, WLF, MNG and trace files must stay outside the repository.
set -eu

fail() {
    printf '%s\n' "$1" >&2
    exit 64
}

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P) || fail "cannot resolve launcher directory"
repo_root=$(CDPATH= cd -- "$script_dir/.." && pwd -P) || fail "cannot resolve repository root"

[ -n "${MAME0106_EXE:-}" ] || fail "MAME0106_EXE must name the private MAME 0.106 executable"
case "$MAME0106_EXE" in
    /*) ;;
    *) fail "MAME0106_EXE must be an absolute path" ;;
esac
[ ! -L "$MAME0106_EXE" ] || fail "MAME0106_EXE must not be a symlink"
[ -f "$MAME0106_EXE" ] || fail "MAME0106_EXE must be a regular file"
mame_exe=$(realpath -e -- "$MAME0106_EXE") || fail "cannot resolve MAME0106_EXE"
case "$mame_exe" in
    "$repo_root"|"$repo_root"/*) fail "MAME executable must remain outside the repository" ;;
esac

[ -n "${WINEPREFIX:-}" ] || fail "WINEPREFIX must point to a private prefix outside the repository"
case "$WINEPREFIX" in
    /*) ;;
    *) fail "WINEPREFIX must be an absolute path" ;;
esac
prefix_parent=$(CDPATH= cd -- "$(dirname -- "$WINEPREFIX")" && pwd -P) || fail "WINEPREFIX parent must exist"
prefix_path="$prefix_parent/$(basename -- "$WINEPREFIX")"
if [ -e "$prefix_path" ] || [ -L "$prefix_path" ]; then
    [ -d "$prefix_path" ] && [ ! -L "$prefix_path" ] || fail "WINEPREFIX must be a real directory, not a symlink"
fi
case "$prefix_path" in
    "$repo_root"|"$repo_root"/*) fail "WINEPREFIX must remain outside the repository" ;;
esac

wine_bin=${WINE_BIN:-wine}
command -v "$wine_bin" >/dev/null 2>&1 || fail "WINE_BIN is not executable"
export MAME0106_EXE="$mame_exe"
export WINEPREFIX="$prefix_path"
wine_arch=${WINEARCH:-win32}
case "$wine_arch" in
    win32|win64) ;;
    *) fail "WINEARCH must be win32 or win64" ;;
esac
export WINEARCH="$wine_arch"
export WINEDEBUG=${WINEDEBUG:--all}

exec "$wine_bin" "$MAME0106_EXE" "$@"
