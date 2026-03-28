# canon-download

Download all files from a Canon camera over USB on macOS — no SD card reader needed.

Connects to a Canon 5D Mark II (or any PTP-compatible camera) via macOS ImageCaptureCore, downloads every file, and optionally mounts them as a Finder volume.

## How it works

1. Creates a sparse disk image that appears as a volume in Finder (or uses a custom output directory)
2. Browses for USB-connected PTP cameras
3. Downloads all files, preserving the camera's folder structure (e.g. `DCIM/100EOS5D/`)
4. Skips files that already exist — safe to re-run

## Requirements

- macOS (uses ImageCaptureCore framework)
- Python 3.12+
- Canon camera connected via USB (tested with 5D Mark II)

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install pyobjc-core pyobjc-framework-Cocoa pyobjc-framework-ImageCaptureCore
```

## Usage

```bash
source .venv/bin/activate
python mount_camera.py
```

Plug in your camera after starting the script. It will detect the connection, enumerate files, and begin downloading. Press `Ctrl+C` to stop.

### Options

```bash
# Download to a specific directory instead of a Finder volume
python mount_camera.py --output ~/Pictures/canon

# Flat mode — all files in one directory, no DCIM subfolder structure
python mount_camera.py --flat

# Combine options
python mount_camera.py --output ~/Pictures/shoot --flat
```

## Output

```
=== Canon Camera Mount Server ===
Volume: /Volumes/Canon 5D Mark II
Plug in your Canon camera via USB...

Camera found: Canon EOS 5D Mark II
Connected. Reading file list...
Found 847 files on camera.
  [1/847] IMG_0001.CR2 (25.3 MB)  ok
  [2/847] IMG_0002.CR2 (24.8 MB)  ok
  ...

========================================
Download complete!
  Downloaded: 847
  Skipped:    0 (already exist)
  Location:   /Volumes/Canon 5D Mark II
========================================
```

## Notes

- The Finder volume is a 128 GB sparse image stored at `~/.canon_mount/canon5d.sparseimage` — it only uses disk space for actual files
- Re-running skips already-downloaded files, so interrupted downloads resume where they left off
- The volume persists after the script exits; eject it from Finder when done
