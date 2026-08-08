#!/usr/bin/env python3
"""
Patches the linux-zen PKGBUILD to:
  1. Rename pkgbase to linux-zenjin
  2. Add config.custom and lsmod.txt to source_x86_64
  3. Add SKIP checksums for each local file
  4. In prepare(): run localmodconfig, merge config.custom
  5. Switch build() to Clang + ThinLTO + -march=native (no -O flag — zen uses -O3)

Run from inside the linux-zen clone directory.
Safe to re-run: each section is guarded by a marker string.

Note: the ntfs3 patches (mft-bitmap-run-extents, 64bit-cluster-maxbytes-sparse)
were removed 2026-07-31 — both fixes landed upstream by kernel 7.1.5.
"""

import sys
from pathlib import Path

PKGBUILD = Path("PKGBUILD")

if not PKGBUILD.exists():
    sys.exit("ERROR: PKGBUILD not found. Run this from inside the linux-zen clone.")

lines = PKGBUILD.read_text().splitlines(keepends=True)
changed = False

def find_line(pattern, start=0):
    for i, line in enumerate(lines[start:], start):
        if pattern in line:
            return i
    return -1

LSMOD_FILE  = "lsmod.txt"

# ── 0. Rename pkgbase ────────────────────────────────────────────────────────
if "pkgbase=linux-zenjin" not in "".join(lines):
    i = find_line("pkgbase=linux-zen")
    if i == -1:
        sys.exit("ERROR: Could not find pkgbase=linux-zen.")
    lines[i] = lines[i].replace("pkgbase=linux-zen", "pkgbase=linux-zenjin")
    print("✓ Renamed pkgbase to linux-zenjin")
    changed = True
else:
    print("· pkgbase already linux-zenjin")

# ── 1. Add local files to source_x86_64 ─────────────────────────────────────
source_block = "".join(lines)

for fname, label in [
    ("config.custom", "config.custom"),
    (LSMOD_FILE,      LSMOD_FILE),
]:
    if fname not in source_block:
        i = find_line("source_x86_64=(config.")
        if i == -1:
            sys.exit("ERROR: Could not find source_x86_64 line.")
        lines[i] = lines[i].rstrip("\n").rstrip(")") + f" {fname})\n"
        source_block = "".join(lines)
        print(f"✓ Added {label} to source_x86_64")
        changed = True
    else:
        print(f"· source_x86_64 already contains {label}")

# ── 2. Add SKIP entries to b2sums_x86_64 ────────────────────────────────────
custom_files = ["config.custom", LSMOD_FILE]
all_lines = "".join(lines)
b2_start    = find_line("b2sums_x86_64")
b2_line_idx = find_line("b2sums_x86_64=(", b2_start) if b2_start >= 0 else -1
if b2_line_idx >= 0:
    existing_skips = lines[b2_line_idx].count("'SKIP'")
    needed_skips   = sum(1 for f in custom_files if f in all_lines)
    skips_to_add   = needed_skips - existing_skips
    if skips_to_add > 0:
        for _ in range(skips_to_add):
            lines[b2_line_idx] = lines[b2_line_idx].rstrip("\n").rstrip(")") + " 'SKIP')\n"
        print(f"✓ Added {skips_to_add} SKIP(s) to b2sums_x86_64")
        changed = True
    else:
        print("· b2sums_x86_64 already has correct SKIP count")

# ── 4. Merge config.custom in prepare() (after make olddefconfig) ────────────
FRAGMENT_MARKER = "Velociraptor custom config"
if FRAGMENT_MARKER not in "".join(lines):
    i = find_line("  make olddefconfig")
    if i == -1:
        sys.exit("ERROR: Could not find 'make olddefconfig' in prepare().")
    insert = [
        "\n",
        "  # === Velociraptor custom config fragment ===\n",
        "  ./scripts/kconfig/merge_config.sh -m .config \"${srcdir}/config.custom\"\n",
        "  make LLVM=1 LLVM_IAS=1 olddefconfig\n",
        "  # ============================================\n",
    ]
    lines[i+1:i+1] = insert
    print("✓ Inserted config fragment merge into prepare()")
    changed = True
else:
    print("· Config fragment merge already in prepare()")

# ── 5. Run localmodconfig in prepare() (before config fragment merge) ─────────
# Strips modules not present in lsmod.txt; config.custom then re-enables
# hardware that wasn't loaded at snapshot time (e.g. unplugged devices).
LSMOD_MARKER = "Velociraptor custom config + localmodconfig"
if LSMOD_MARKER not in "".join(lines):
    j = find_line("merge_config.sh")
    if j == -1:
        # Fallback: insert after make olddefconfig
        j = find_line("  make olddefconfig") + 1
    insert = [
        "\n",
        "  # === Velociraptor custom config + localmodconfig strip ===\n",
        "  echo 'Stripping unused modules (localmodconfig)...'\n",
        "  make LSMOD=\"${srcdir}/lsmod.txt\" localmodconfig\n",
        "  echo 'Applying custom config fragment...'\n",
        "  # =========================================================\n",
    ]
    lines[j:j] = insert
    print("✓ Inserted localmodconfig step into prepare()")
    changed = True
else:
    print("· localmodconfig step already in prepare()")

# ── 5b. Remove bpftool vmlinux.h step from build() ──────────────────────────
# We have no use for CO-RE vmlinux.h on this desktop kernel — scx-scheds ships
# its own pre-built schedulers. Drop the step regardless of BTF config.
BPFTOOL_BUILD = "make -C tools/bpf/bpftool vmlinux.h"
BPFTOOL_INSTALL = "tools/bpf/bpftool/vmlinux.h"
if BPFTOOL_BUILD in "".join(lines):
    for idx, line in enumerate(lines):
        if BPFTOOL_BUILD in line:
            # Entire line is the bpftool build command — blank it wholesale.
            lines[idx] = ""
            print("✓ Removed bpftool vmlinux.h build step (not needed, no CO-RE use)")
            changed = True
            break
else:
    print("· bpftool vmlinux.h build step already absent")

if BPFTOOL_INSTALL in "".join(lines):
    for idx, line in enumerate(lines):
        if BPFTOOL_INSTALL in line:
            # The install token sits among other files on the line — excise only it.
            new_line = line.replace(BPFTOOL_INSTALL, "").rstrip()
            if not new_line.strip():
                lines[idx] = ""
                if idx > 0 and lines[idx - 1].rstrip("\n").endswith("\\"):
                    lines[idx - 1] = lines[idx - 1].rstrip("\n").rstrip("\\").rstrip() + "\n"
            else:
                lines[idx] = new_line + "\n"
            print("✓ Removed bpftool vmlinux.h install step (not needed, no CO-RE use)")
            changed = True
            break
else:
    print("· bpftool vmlinux.h install step already absent")

# ── 6a. Fix KCFLAGS -O2 bug on already-patched PKGBUILDs ────────────────────
# -O2 in KCFLAGS is appended after zen's KBUILD_CFLAGS, overriding zen's -O3.
# zen sets CONFIG_CC_OPTIMIZE_FOR_PERFORMANCE_O3=y; we must not clobber it.
old_kcflags = '-march=native -O2 -pipe'
new_kcflags = '-march=native -pipe'
if old_kcflags in "".join(lines):
    for idx, line in enumerate(lines):
        if old_kcflags in line:
            lines[idx] = line.replace(old_kcflags, new_kcflags)
            print("✓ Fixed KCFLAGS: removed -O2 (was overriding zen's -O3)")
            changed = True
            break
else:
    print("· KCFLAGS -O2 already absent")

# ── 6b. Add Clang/LLVM exports to build() ───────────────────────────────────
LLVM_MARKER = "Velociraptor: Clang"
if LLVM_MARKER not in "".join(lines):
    i = find_line("build() {")
    if i == -1:
        sys.exit("ERROR: Could not find build() function.")
    j = find_line("  cd $_srcname", i)
    if j == -1:
        sys.exit("ERROR: Could not find 'cd $_srcname' inside build().")
    insert = [
        "\n",
        "  # === Velociraptor: Clang + ThinLTO + native CPU ===\n",
        "  export LLVM=1\n",
        "  export LLVM_IAS=1\n",
        '  export KCFLAGS="-march=native -pipe"\n',
        '  export KCPPFLAGS="-march=native"\n',
        "  export MAKEFLAGS=\"-j$(nproc)\"\n",
        "  # ==================================================\n",
    ]
    lines[j+1:j+1] = insert
    print("✓ Added LLVM/Clang/KCFLAGS exports to build()")
    changed = True
else:
    print("· Clang/LLVM exports already in build()")

# ── 6c. Add AutoFDO profile export to build() ────────────────────────────────
AUTOFDO_MARKER = "Velociraptor: AutoFDO"
if AUTOFDO_MARKER not in "".join(lines):
    j = find_line("Velociraptor: Clang")
    if j == -1:
        sys.exit("ERROR: Could not find Clang export block in build().")
    # Find the closing marker of that block
    k = find_line("  # ==================================================", j)
    if k == -1:
        sys.exit("ERROR: Could not find end of Clang export block.")
    insert = [
        "\n",
        "  # === Velociraptor: AutoFDO profile ===\n",
        '  export CLANG_AUTOFDO_PROFILE="/home/senjin/kernel-build/kernel.afdo"\n',
        "  # =====================================\n",
    ]
    lines[k+1:k+1] = insert
    print("✓ Added CLANG_AUTOFDO_PROFILE export to build()")
    changed = True
else:
    print("· AutoFDO profile export already in build()")

# ── 6d. Add Propeller profile export to build() ──────────────────────────────
PROPELLER_MARKER = "Velociraptor: Propeller"
if PROPELLER_MARKER not in "".join(lines):
    k = find_line("Velociraptor: AutoFDO")
    if k == -1:
        sys.exit("ERROR: Could not find AutoFDO export block in build().")
    m = find_line("  # =====================================", k)
    if m == -1:
        sys.exit("ERROR: Could not find end of AutoFDO export block.")
    insert = [
        "\n",
        "  # === Velociraptor: Propeller profiles ===\n",
        '  export CLANG_PROPELLER_PROFILE_PREFIX="/home/senjin/kernel-build/kernel_propeller"\n',
        "  # =========================================\n",
    ]
    lines[m+1:m+1] = insert
    print("✓ Added CLANG_PROPELLER_PROFILE_PREFIX export to build()")
    changed = True
else:
    print("· Propeller profile export already in build()")

# ── 6e. Run profile coverage check right after make all (before stripping) ──
COVERAGE_MARKER = "Velociraptor: profile coverage check"
if COVERAGE_MARKER not in "".join(lines):
    i = find_line("  make all")
    if i == -1:
        sys.exit("ERROR: Could not find 'make all' in build().")
    insert = [
        "\n",
        "  # === Velociraptor: profile coverage check ===\n",
        "  bash /home/senjin/kernel-build/check_profile_coverage.sh \"$PWD/vmlinux\" || true\n",
        "  # ==============================================\n",
    ]
    lines[i+1:i+1] = insert
    print("✓ Added profile coverage check after make all")
    changed = True
else:
    print("· Profile coverage check already in build()")

# ── Write result ──────────────────────────────────────────────────────────────
if changed:
    PKGBUILD.write_text("".join(lines))
    print("\nPKGBUILD patched successfully.")
else:
    print("\nNo changes needed — PKGBUILD already patched.")
