#!/usr/bin/env bash
# check_profile_coverage.sh — warn if AutoFDO/Propeller profiles look stale
# against a freshly built vmlinux.
#
# Usage: bash check_profile_coverage.sh [/path/to/vmlinux]
# With no argument, auto-detects the newest src/linux-*/vmlinux under
# ~/kernel-build/linux-zen (must run before makepkg strips it).

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WARN_THRESHOLD=90   # below this % coverage, recommend re-profiling

VMLINUX="${1:-}"
if [[ -z "$VMLINUX" ]]; then
    VMLINUX=$(ls -t "$SCRIPT_DIR"/linux-zen/src/linux-*/vmlinux 2>/dev/null | head -1)
fi
if [[ -z "$VMLINUX" || ! -f "$VMLINUX" ]]; then
    echo "ERROR: no vmlinux found. Pass a path explicitly, or run before makepkg strips it." >&2
    exit 1
fi

AFDO="$SCRIPT_DIR/kernel.afdo"
PROPELLER_CC="$SCRIPT_DIR/kernel_propeller_cc_profile.txt"
PROPELLER_LD="$SCRIPT_DIR/kernel_propeller_ld_profile.txt"
TMPDIR=$(mktemp -d)
trap 'rm -rf "$TMPDIR"' EXIT

echo "==> Using vmlinux: $VMLINUX"

# All defined function/text symbols in the fresh build.
nm --defined-only "$VMLINUX" 2>/dev/null | awk '$2 ~ /[tT]/ {print $3}' | sort -u > "$TMPDIR/vmlinux_syms.txt"
total_syms=$(wc -l < "$TMPDIR/vmlinux_syms.txt")
echo "    ($total_syms text symbols in this build)"
echo ""

report() {
    local label="$1" profiled_file="$2"
    local profiled matched pct
    profiled=$(wc -l < "$profiled_file")
    if [[ "$profiled" -eq 0 ]]; then
        echo "$label: no entries found, skipping"
        return
    fi
    matched=$(comm -12 "$profiled_file" "$TMPDIR/vmlinux_syms.txt" | wc -l)
    pct=$(( matched * 100 / profiled ))
    echo "$label: $matched / $profiled profiled functions still present ($pct%)"
    if [[ "$pct" -lt "$WARN_THRESHOLD" ]]; then
        echo "  ⚠ below ${WARN_THRESHOLD}% — consider re-profiling (AutoFDO + Propeller)"
    fi
}

# --- AutoFDO: top-level (non-indented) entries are "func:total:count" ---
if [[ -f "$AFDO" ]]; then
    llvm-profdata merge -sample -text -output="$TMPDIR/afdo.txt" "$AFDO"
    grep -E '^[A-Za-z_][A-Za-z0-9_.]*:' "$TMPDIR/afdo.txt" | cut -d: -f1 | sort -u > "$TMPDIR/afdo_funcs.txt"
    report "AutoFDO      " "$TMPDIR/afdo_funcs.txt"
else
    echo "AutoFDO      : $AFDO not found, skipping"
fi

# --- Propeller cc profile: "f <funcname>" lines ---
if [[ -f "$PROPELLER_CC" ]]; then
    awk '$1 == "f" {print $2}' "$PROPELLER_CC" | sort -u > "$TMPDIR/propeller_cc_funcs.txt"
    report "Propeller cc " "$TMPDIR/propeller_cc_funcs.txt"
else
    echo "Propeller cc : $PROPELLER_CC not found, skipping"
fi

# --- Propeller ld profile: one symbol per line ---
if [[ -f "$PROPELLER_LD" ]]; then
    sort -u "$PROPELLER_LD" > "$TMPDIR/propeller_ld_funcs.txt"
    report "Propeller ld " "$TMPDIR/propeller_ld_funcs.txt"
else
    echo "Propeller ld : $PROPELLER_LD not found, skipping"
fi

echo ""
echo "Note: this only detects functions that appeared/vanished, not functions"
echo "that changed shape while keeping their name — a clean report doesn't"
echo "guarantee the profile is still optimal, just that it isn't obviously stale."
