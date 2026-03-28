#!/usr/bin/env python3
"""
Canon Camera Mount Server
Connects to a Canon 5D Mark II (or any PTP camera), downloads all files,
and mounts them as a volume visible in Finder.

Usage:
    python mount_camera.py
    python mount_camera.py --flat          # no folder structure, all files in one dir
    python mount_camera.py --output DIR    # custom output directory
"""

import os
import sys
import subprocess
import argparse
import objc
from Foundation import NSObject, NSRunLoop, NSDate, NSURL, NSDefaultRunLoopMode
from ImageCaptureCore import (
    ICDeviceBrowser,
    ICCameraDevice,
    ICCameraFile,
    ICCameraFolder,
    ICDeviceTypeMaskCamera,
    ICDeviceLocationTypeMaskLocal,
    ICDownloadsDirectoryURL,
    ICOverwrite,
)

VOLUME_NAME = "Canon 5D Mark II"
SPARSE_IMAGE_DIR = os.path.expanduser("~/.canon_mount")
SPARSE_IMAGE_PATH = os.path.join(SPARSE_IMAGE_DIR, "canon5d.sparseimage")


def create_volume():
    """Create and mount a sparse disk image that appears as a volume in Finder."""
    mount_point = f"/Volumes/{VOLUME_NAME}"

    if os.path.ismount(mount_point):
        return mount_point

    os.makedirs(SPARSE_IMAGE_DIR, exist_ok=True)

    if not os.path.exists(SPARSE_IMAGE_PATH):
        print(f"Creating volume '{VOLUME_NAME}'...")
        subprocess.run(
            [
                "hdiutil", "create",
                "-size", "128g",
                "-fs", "APFS",
                "-volname", VOLUME_NAME,
                "-type", "SPARSE",
                SPARSE_IMAGE_PATH.replace(".sparseimage", ""),
            ],
            check=True,
            capture_output=True,
        )

    print(f"Mounting volume...")
    subprocess.run(
        ["hdiutil", "attach", SPARSE_IMAGE_PATH, "-mountpoint", mount_point],
        check=True,
        capture_output=True,
    )
    return mount_point


def eject_volume():
    """Eject the mounted volume."""
    mount_point = f"/Volumes/{VOLUME_NAME}"
    if os.path.ismount(mount_point):
        subprocess.run(["hdiutil", "detach", mount_point], capture_output=True)


def get_camera_path(item):
    """Get the relative path for a camera item (preserves DCIM/100EOS5D/ structure)."""
    parts = []
    folder = item.parentFolder()
    while folder is not None:
        name = folder.name()
        if name:
            parts.append(name)
        folder = folder.parentFolder()
    parts.reverse()
    return os.path.join(*parts) if parts else ""


class CameraMount(NSObject):
    def init(self):
        self = objc.super(CameraMount, self).init()
        if self is None:
            return None
        self.camera = None
        self.files = []
        self.current = 0
        self.skipped = 0
        self.errors = 0
        self.done = False
        self.downloading = False
        self.catalog_ready = False
        self.output_dir = None
        self.flat = False
        return self

    # --- ICDeviceBrowserDelegate ---

    def deviceBrowser_didAddDevice_moreComing_(self, browser, device, moreComing):
        if not isinstance(device, ICCameraDevice):
            return
        print(f"\nCamera found: {device.name()}")
        self.camera = device
        device.setDelegate_(self)
        device.requestOpenSession()

    def deviceBrowser_didRemoveDevice_moreGoing_(self, browser, device, moreGoing):
        if device is self.camera:
            print("\nCamera disconnected.")
            self.done = True

    # --- ICDeviceDelegate ---

    def didOpenSessionOnDevice_(self, device):
        print("Connected. Reading file list...")

    def didCloseSessionOnDevice_(self, device):
        pass

    def didRemoveDevice_(self, device):
        if device is self.camera:
            print("\nCamera removed.")
            self.done = True

    def device_didReceiveStatusInformation_(self, device, status):
        pass

    def device_didEncounterError_(self, device, error):
        desc = error.localizedDescription() if hasattr(error, "localizedDescription") else str(error)
        print(f"Device error: {desc}")

    # --- ICCameraDeviceDelegate ---

    def cameraDevice_didAddItems_(self, camera, items):
        for item in items:
            if isinstance(item, ICCameraFile):
                self.files.append(item)

        print(f"Found {len(self.files)} files on camera...", end="\r", flush=True)

    def deviceDidBecomeReadyWithCompleteContentCatalog_(self, device):
        self.catalog_ready = True
        print(f"Found {len(self.files)} files on camera.   ")
        if self.files and not self.downloading:
            self._download_next()

    def cameraDevice_didRemoveItems_(self, camera, items):
        pass

    def cameraDevice_didCompleteDeleteFilesWithError_(self, camera, error):
        pass

    def cameraDevice_didRenameItems_(self, camera, items):
        pass

    # --- Download ---

    def _dest_for(self, item):
        """Get the destination directory for a file, creating it if needed."""
        if self.flat:
            return self.output_dir

        subdir = get_camera_path(item)
        dest = os.path.join(self.output_dir, subdir)
        os.makedirs(dest, exist_ok=True)
        return dest

    def _download_next(self):
        self.downloading = True

        # Skip files that already exist
        while self.current < len(self.files):
            item = self.files[self.current]
            dest = self._dest_for(item)
            filepath = os.path.join(dest, item.name())
            if os.path.exists(filepath):
                self.skipped += 1
                self.current += 1
                continue
            break

        if self.current >= len(self.files):
            self.downloading = False
            self._finish()
            return

        item = self.files[self.current]
        dest = self._dest_for(item)
        n = self.current + 1
        total = len(self.files)
        size_mb = (item.fileSize() or 0) / (1024 * 1024)
        print(f"  [{n}/{total}] {item.name()} ({size_mb:.1f} MB)", end="", flush=True)

        dest_url = NSURL.fileURLWithPath_(dest)
        options = {ICDownloadsDirectoryURL: dest_url, ICOverwrite: True}

        self.camera.requestDownloadFile_options_downloadDelegate_didDownloadSelector_contextInfo_(
            item,
            options,
            self,
            b"didDownloadFile:error:options:contextInfo:",
            None,
        )

    @objc.typedSelector(b"v@:@@@@")
    def didDownloadFile_error_options_contextInfo_(self, file, error, options, ctx):
        if error:
            desc = error.localizedDescription() if hasattr(error, "localizedDescription") else str(error)
            print(f"  FAILED: {desc}")
            self.errors += 1
        else:
            print("  ok")
        self.current += 1
        self._download_next()

    def _finish(self):
        downloaded = self.current - self.skipped - self.errors
        print(f"\n{'='*40}")
        print(f"Download complete!")
        print(f"  Downloaded: {downloaded}")
        print(f"  Skipped:    {self.skipped} (already exist)")
        if self.errors:
            print(f"  Failed:     {self.errors}")
        print(f"  Location:   {self.output_dir}")
        print(f"{'='*40}")
        subprocess.run(["open", self.output_dir])
        self.done = True


def main():
    parser = argparse.ArgumentParser(description="Mount Canon camera in Finder")
    parser.add_argument(
        "--output", "-o",
        help="Download directory (default: mounts as Finder volume)",
    )
    parser.add_argument(
        "--flat", action="store_true",
        help="Download all files to a single directory (no folder structure)",
    )
    args = parser.parse_args()

    # Determine output directory
    if args.output:
        output_dir = os.path.expanduser(args.output)
        os.makedirs(output_dir, exist_ok=True)
    else:
        output_dir = create_volume()

    print(f"=== Canon Camera Mount Server ===")
    print(f"Volume: {output_dir}")
    print(f"Plug in your Canon camera via USB...")
    print(f"Press Ctrl+C to stop.\n")

    handler = CameraMount.alloc().init()
    handler.output_dir = output_dir
    handler.flat = args.flat

    browser = ICDeviceBrowser.alloc().init()
    browser.setDelegate_(handler)
    browser.setBrowsedDeviceTypeMask_(ICDeviceTypeMaskCamera | ICDeviceLocationTypeMaskLocal)
    browser.start()

    try:
        while not handler.done:
            NSRunLoop.currentRunLoop().runMode_beforeDate_(
                NSDefaultRunLoopMode,
                NSDate.dateWithTimeIntervalSinceNow_(0.5),
            )
    except KeyboardInterrupt:
        print("\n\nShutting down...")
    finally:
        browser.stop()
        if handler.camera:
            handler.camera.requestCloseSession()

    print("Done.")


if __name__ == "__main__":
    main()
