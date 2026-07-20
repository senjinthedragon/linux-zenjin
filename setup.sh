#!/usr/bin/env bash
# setup.sh — Velociraptor custom linux-zen kernel build setup
# Run once to clone the PKGBUILD and prepare the workspace.
# Re-run after a zen version bump to update and rebuild.
#
# NOTE: Run this from linux-zenjin (the default boot kernel) so that
# lsmod.txt reflects the correct module set and the build runs at full turbo.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ZEN_DIR="$SCRIPT_DIR/linux-zen"
PKGBUILD_REPO="https://gitlab.archlinux.org/archlinux/packaging/packages/linux-zen.git"

# ── Clone or update the PKGBUILD repo ────────────────────────────────────────
TARGET_TAG="${1:-}"

if [[ -d "$ZEN_DIR/.git" ]]; then
    echo "==> Updating linux-zen PKGBUILD..."
    git -C "$ZEN_DIR" restore PKGBUILD 2>/dev/null || true
    git -C "$ZEN_DIR" fetch --tags
    if [[ -z "$TARGET_TAG" ]]; then
        TARGET_TAG=$(git -C "$ZEN_DIR" tag -l | grep -v '\-rc' | sort -V | tail -1)
    fi
    echo "    Checking out $TARGET_TAG"
    git -C "$ZEN_DIR" checkout "$TARGET_TAG"
else
    echo "==> Cloning linux-zen PKGBUILD..."
    git clone "$PKGBUILD_REPO" "$ZEN_DIR"
fi

# ── Copy our files into the PKGBUILD directory ────────────────────────────────
echo "==> Capturing lsmod snapshot (lsmod.txt)..."
lsmod > "$SCRIPT_DIR/lsmod.txt"
echo "    Captured $(wc -l < "$SCRIPT_DIR/lsmod.txt") modules"
echo "    NOTE: run with your regular hardware connected for best results"

echo "==> Copying config.custom and lsmod.txt..."
cp "$SCRIPT_DIR/config.custom" "$ZEN_DIR/config.custom"
cp "$SCRIPT_DIR/lsmod.txt"     "$ZEN_DIR/lsmod.txt"

echo "==> Copying kernel patches..."
cp "$SCRIPT_DIR"/ntfs3-*.patch "$ZEN_DIR/" 2>/dev/null && echo "    Copied ntfs3 patches" || echo "    (no ntfs3 patches found)"

# ── Apply PKGBUILD patches ────────────────────────────────────────────────────
echo "==> Patching PKGBUILD..."
cd "$ZEN_DIR"
python3 "$SCRIPT_DIR/patch_pkgbuild.py"

# ── Check build dependencies ──────────────────────────────────────────────────
echo ""
echo "==> Checking build dependencies..."
# clang and lld are needed for LTO build
missing=()
for tool in clang lld llvm-ar llvm-nm llvm-strip; do
    command -v "$tool" &>/dev/null || missing+=("$tool")
done
if [[ ${#missing[@]} -gt 0 ]]; then
    echo "WARN: Missing tools: ${missing[*]}"
    echo "      Install with: sudo pacman -S clang lld llvm"
else
    echo "    Clang toolchain: OK ($(clang --version | head -1))"
fi

# ── Summary ───────────────────────────────────────────────────────────────────
echo ""
echo "================================================================"
echo " Workspace ready: $ZEN_DIR"
echo ""
echo " To build:"
echo "   cd $ZEN_DIR"
echo "   makepkg -s --cleanbuild 2>&1 | tee build.log"
echo ""
echo " Estimated build time: 30-90 min (12-thread, ThinLTO, hardware-stripped)."
echo " Watch progress: tail -f $ZEN_DIR/build.log"
echo ""
echo " After a successful build, install with:"
echo "   sudo pacman -U linux-zenjin-*.pkg.tar.zst \\"
echo "                  linux-zenjin-headers-*.pkg.tar.zst"
echo ""
echo " DKMS modules (nvidia, looking-glass, v4l2loopback, vboxhost)"
echo " will rebuild automatically on install via pacman hooks."
echo "================================================================"
