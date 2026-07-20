# linux-zenjin

A custom `linux-zen` kernel build for **Velociraptor** — a specific desktop machine with an Intel i7-8700K (Coffee Lake) and NVIDIA RTX 2080.

**This is not a general-purpose kernel.** It is aggressively optimized for one specific machine and will likely not boot on yours without significant changes. If you're looking for a drop-in kernel, use [linux-zen](https://archlinux.org/packages/extra/x86_64/linux-zen/) from the Arch repos instead.

## What makes it different

- **`-march=native`** — compiled specifically for Coffee Lake, using instructions unavailable on older CPUs
- **AutoFDO + Propeller** — profile-guided optimization: the kernel is profiled under real workloads and rebuilt to optimize hot code paths and code layout. Measured ~80% improvement in LLM prompt evaluation throughput
- **Clang + ThinLTO** — full LLVM toolchain with link-time optimization
- **Hardware-stripped** — unused drivers, subsystems, and CPU counts removed via `localmodconfig` + custom config fragment; build time and binary size cut significantly
- **sched-ext (scx_lavd)** — BPF scheduler framework enabled; `scx_lavd` runs automatically under GameMode for gaming sessions
- **ntfs3 patches** — two custom kernel patches for large NTFS volumes (16TB BitLocker datastore with fragmented MFT bitmaps and 64-bit cluster counts)
- **BBR + FQ** — TCP congestion control tuned for throughput

## Hardware this is built for

| Component | Details |
|-----------|---------|
| CPU | Intel i7-8700K (Coffee Lake, 6C/12T) |
| GPU | NVIDIA RTX 2080 (proprietary driver via DKMS) |
| Board | ASUS Prime Z390-A |
| Storage | NVMe + 16TB NTFS BitLocker datastore |
| OS | Garuda Linux (Arch-based) |

## Repository contents

| File | Purpose |
|------|---------|
| `setup.sh` | Run once per kernel version: pulls the upstream linux-zen PKGBUILD, snapshots loaded modules, copies all files, patches the PKGBUILD |
| `patch_pkgbuild.py` | Automates all PKGBUILD modifications (idempotent) |
| `config.custom` | Kernel config fragment applied on top of linux-zen defaults |
| `ntfs3-mft-bitmap-run-extents.patch` | Fixes MFT bitmap run list loading for heavily-fragmented large NTFS volumes |
| `ntfs3-64bit-cluster-maxbytes-sparse.patch` | Fixes `maxbytes_sparse` sign error on 64-bit cluster volumes |

## Usage

```bash
cd ~/kernel-build
bash setup.sh          # prepare for latest linux-zen version
cd linux-zen
makepkg -s --cleanbuild 2>&1 | tee build.log
sudo pacman -U linux-zenjin-*.pkg.tar.zst linux-zenjin-headers-*.pkg.tar.zst
```

`lsmod.txt` (hardware module snapshot) is captured fresh by `setup.sh` each run and is not tracked in this repo — it's specific to what's plugged in at build time.

## AutoFDO + Propeller profiles

Profile files (`kernel.afdo`, `kernel_propeller_cc_profile.txt`, `kernel_propeller_ld_profile.txt`) are not tracked here — they're large binary/text artifacts tied to a specific kernel build. They live in `~/kernel-build/` alongside this repo. See `patch_pkgbuild.py` for how they're wired into the build.
