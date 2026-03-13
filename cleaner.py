"""
CleanAgent — Cleanup Engine v2.0
Cross-platform cleanup with bulletproof Windows support.
"""

import os
import shutil
import platform
import subprocess
import sys
from pathlib import Path
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict
from typing import List, Dict
from scanner import fmt_size

# Windows subprocess flag to hide console windows
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


@dataclass
class CleanupResult:
    operation: str
    label: str
    files_cleaned: int
    space_freed: int
    success: bool
    details: str

    def to_dict(self):
        d = asdict(self)
        d["space_freed_mb"] = round(self.space_freed / (1024 * 1024), 1)
        d["space_freed_display"] = fmt_size(self.space_freed)
        return d


def _safe_delete_file(p: Path) -> int:
    """Delete a file, return bytes freed. Returns 0 on failure."""
    try:
        size = p.stat().st_size
        p.unlink()
        return size
    except (PermissionError, OSError):
        return 0


def _safe_delete_dir(p: Path) -> int:
    """Delete a directory tree, return bytes freed. Returns 0 on failure."""
    try:
        size = sum(
            f.stat().st_size for f in p.rglob("*")
            if f.is_file()
        )
        shutil.rmtree(p, ignore_errors=True)
        return size
    except (PermissionError, OSError):
        return 0


class SystemCleaner:
    # ── Safe cache subdirectories to clean ───────────────
    MAC_SAFE_CACHES = [
        "Google/Chrome/Default/Cache",
        "Google/Chrome/Default/Code Cache",
        "com.apple.Safari/WebKitCache",
        "org.mozilla.firefox",
        "com.brave.Browser",
        "com.microsoft.edgemac",
        "com.spotify.client",
        "com.microsoft.VSCode",
        "com.apple.iTunes",
        "pip",
        "yarn",
        "com.docker.docker",
        "org.swift.swiftpm",
        "Homebrew",
    ]

    WIN_SAFE_CACHES = [
        # Relative to LOCALAPPDATA
        "Google/Chrome/User Data/Default/Cache",
        "Google/Chrome/User Data/Default/Code Cache",
        "Microsoft/Edge/User Data/Default/Cache",
        "Microsoft/Edge/User Data/Default/Code Cache",
        "BraveSoftware/Brave-Browser/User Data/Default/Cache",
        "Spotify/Data",
        "pip/cache",
        "yarn/Cache",
    ]

    WIN_APPDATA_CACHES = [
        # Relative to APPDATA
        "Mozilla/Firefox/Profiles",
    ]

    def __init__(self):
        self.home = Path.home()
        self.is_mac = platform.system() == "Darwin"
        self.is_win = platform.system() == "Windows"
        self.results: List[CleanupResult] = []

    def run_all(self) -> Dict:
        self.results = []
        self.clean_browser_caches()
        self.clean_system_logs()
        self.clean_temp_files()
        self.clean_trash()
        self.clean_package_caches()
        self.flush_dns()

        total_files = sum(r.files_cleaned for r in self.results)
        total_space = sum(r.space_freed for r in self.results)
        return {
            "total_files_cleaned": total_files,
            "total_space_freed_mb": round(total_space / (1024 * 1024), 1),
            "total_space_freed_display": fmt_size(total_space),
            "total_space_freed_bytes": total_space,
            "operations": [r.to_dict() for r in self.results],
            "timestamp": datetime.now().isoformat(),
        }

    # ── Browser & App Caches ─────────────────────────────
    def clean_browser_caches(self) -> CleanupResult:
        files_cleaned = 0
        space_freed = 0
        targets = []

        if self.is_mac:
            base = self.home / "Library" / "Caches"
            targets = [(base / sub) for sub in self.MAC_SAFE_CACHES]
        elif self.is_win:
            local = os.environ.get("LOCALAPPDATA", "")
            appdata = os.environ.get("APPDATA", "")
            if local:
                targets += [(Path(local) / sub) for sub in self.WIN_SAFE_CACHES]
            if appdata:
                targets += [(Path(appdata) / sub) for sub in self.WIN_APPDATA_CACHES]
        else:
            base = self.home / ".cache"
            targets = [
                base / "google-chrome",
                base / "mozilla",
                base / "BraveSoftware",
            ]

        for target in targets:
            if not target.exists():
                continue
            try:
                if target.is_file():
                    freed = _safe_delete_file(target)
                    if freed:
                        space_freed += freed
                        files_cleaned += 1
                    continue
                for f in target.rglob("*"):
                    if f.is_file():
                        freed = _safe_delete_file(f)
                        if freed:
                            space_freed += freed
                            files_cleaned += 1
            except (PermissionError, OSError):
                continue

        r = CleanupResult(
            "browser_caches", "Browser & App Caches",
            files_cleaned, space_freed, True,
            f"Cleaned {files_cleaned} files ({fmt_size(space_freed)})",
        )
        self.results.append(r)
        return r

    # ── System Logs ──────────────────────────────────────
    def clean_system_logs(self) -> CleanupResult:
        files_cleaned = 0
        space_freed = 0

        if self.is_mac:
            dirs = [self.home / "Library" / "Logs"]
        elif self.is_win:
            dirs = []
            temp = os.environ.get("TEMP")
            if temp:
                dirs.append(Path(temp))
            # Windows event logs are not safe to delete directly,
            # so we only clean temp logs
            local = os.environ.get("LOCALAPPDATA")
            if local:
                dirs.append(Path(local) / "CrashDumps")
        else:
            dirs = [Path("/var/log")]

        for d in dirs:
            if not d.exists():
                continue
            try:
                for pattern in ["*.log", "*.log.gz", "*.log.old", "*.dmp", "*.mdmp"]:
                    for f in d.rglob(pattern):
                        try:
                            st = f.stat()
                            age = datetime.now() - datetime.fromtimestamp(st.st_mtime)
                            if age.days > 7 or pattern.endswith((".gz", ".old", ".dmp", ".mdmp")):
                                freed = _safe_delete_file(f)
                                if freed:
                                    space_freed += freed
                                    files_cleaned += 1
                        except (PermissionError, OSError):
                            continue
            except (PermissionError, OSError):
                continue

        r = CleanupResult(
            "system_logs", "Old System Logs",
            files_cleaned, space_freed, True,
            f"Removed {files_cleaned} logs ({fmt_size(space_freed)})",
        )
        self.results.append(r)
        return r

    # ── Temp Files ───────────────────────────────────────
    def clean_temp_files(self) -> CleanupResult:
        files_cleaned = 0
        space_freed = 0

        if self.is_mac:
            dirs = [
                self.home / "Library" / "Caches" / "com.apple.dt.Xcode",
                Path("/private/var/folders"),  # partial temp cleanup
            ]
        elif self.is_win:
            dirs = []
            temp = os.environ.get("TEMP")
            if temp:
                dirs.append(Path(temp))
            local = os.environ.get("LOCALAPPDATA")
            if local:
                dirs.append(Path(local) / "Temp")
            # Windows temp cleanup
            dirs.append(Path("C:/Windows/Temp"))
        else:
            dirs = [Path("/tmp")]

        for d in dirs:
            if not d.exists():
                continue
            try:
                for f in d.rglob("*"):
                    if f.is_file():
                        try:
                            st = f.stat()
                            age = datetime.now() - datetime.fromtimestamp(st.st_mtime)
                            if age.days > 3:
                                freed = _safe_delete_file(f)
                                if freed:
                                    space_freed += freed
                                    files_cleaned += 1
                        except (PermissionError, OSError):
                            continue
            except (PermissionError, OSError):
                continue

        r = CleanupResult(
            "temp_files", "Temporary Files",
            files_cleaned, space_freed, True,
            f"Removed {files_cleaned} temp files ({fmt_size(space_freed)})",
        )
        self.results.append(r)
        return r

    # ── Trash / Recycle Bin ──────────────────────────────
    def clean_trash(self) -> CleanupResult:
        files_cleaned = 0
        space_freed = 0

        if self.is_mac:
            trash = self.home / ".Trash"
            if trash.exists():
                try:
                    for f in trash.iterdir():
                        try:
                            if f.is_file():
                                freed = _safe_delete_file(f)
                                if freed:
                                    space_freed += freed
                                    files_cleaned += 1
                            elif f.is_dir():
                                freed = _safe_delete_dir(f)
                                if freed:
                                    space_freed += freed
                                    files_cleaned += 1
                        except (PermissionError, OSError):
                            continue
                except (PermissionError, OSError):
                    pass

        elif self.is_win:
            try:
                result = subprocess.run(
                    [
                        "powershell", "-NoProfile", "-Command",
                        "Clear-RecycleBin -Force -ErrorAction SilentlyContinue",
                    ],
                    capture_output=True, timeout=30,
                    creationflags=_NO_WINDOW,
                )
                if result.returncode == 0:
                    files_cleaned = 1
            except Exception:
                pass

        r = CleanupResult(
            "trash", "Trash / Recycle Bin",
            files_cleaned, space_freed, True,
            f"Emptied {files_cleaned} items ({fmt_size(space_freed)})",
        )
        self.results.append(r)
        return r

    # ── Package Manager Caches ───────────────────────────
    def clean_package_caches(self) -> CleanupResult:
        files_cleaned = 0
        space_freed = 0

        # pip cache
        pip_cmd = "pip3" if not self.is_win else "pip"
        try:
            result = subprocess.run(
                [pip_cmd, "cache", "purge"],
                capture_output=True, timeout=30,
                creationflags=_NO_WINDOW if self.is_win else 0,
            )
            if result.returncode == 0:
                files_cleaned += 1
        except Exception:
            pass

        # Homebrew cache (Mac only)
        if self.is_mac:
            try:
                result = subprocess.run(
                    ["brew", "cleanup", "--prune=all", "-s"],
                    capture_output=True, timeout=60,
                )
                if result.returncode == 0:
                    files_cleaned += 1
            except Exception:
                pass

        # npm cache (cross-platform)
        try:
            result = subprocess.run(
                ["npm", "cache", "clean", "--force"],
                capture_output=True, timeout=30,
                creationflags=_NO_WINDOW if self.is_win else 0,
            )
            if result.returncode == 0:
                files_cleaned += 1
        except Exception:
            pass

        r = CleanupResult(
            "package_caches", "Package Caches (pip/brew/npm)",
            files_cleaned, space_freed, True,
            "Purged package manager caches",
        )
        self.results.append(r)
        return r

    # ── DNS Flush ────────────────────────────────────────
    def flush_dns(self) -> CleanupResult:
        success = False
        details = ""
        try:
            if self.is_mac:
                subprocess.run(
                    ["dscacheutil", "-flushcache"],
                    capture_output=True, timeout=10,
                )
                success = True
                details = "DNS cache flushed"
            elif self.is_win:
                subprocess.run(
                    ["ipconfig", "/flushdns"],
                    capture_output=True, timeout=10,
                    creationflags=_NO_WINDOW,
                )
                success = True
                details = "DNS cache flushed"
        except Exception as e:
            details = f"DNS flush skipped: {e}"

        r = CleanupResult("dns_flush", "DNS Cache", 0, 0, success, details)
        self.results.append(r)
        return r

    # ── Windows Disk Cleanup (Windows-only bonus) ────────
    def run_windows_disk_cleanup(self) -> CleanupResult:
        """Run built-in Windows Disk Cleanup utility."""
        if not self.is_win:
            r = CleanupResult("win_disk_cleanup", "Windows Disk Cleanup", 0, 0, False, "Not on Windows")
            self.results.append(r)
            return r

        try:
            # Run cleanmgr silently with sageset
            subprocess.run(
                ["cleanmgr", "/d", "C:", "/verylowdisk"],
                capture_output=True, timeout=120,
                creationflags=_NO_WINDOW,
            )
            r = CleanupResult(
                "win_disk_cleanup", "Windows Disk Cleanup",
                1, 0, True, "Windows Disk Cleanup completed",
            )
        except Exception as e:
            r = CleanupResult(
                "win_disk_cleanup", "Windows Disk Cleanup",
                0, 0, False, f"Disk Cleanup failed: {e}",
            )

        self.results.append(r)
        return r

    # ── Selective Cleanup Methods ────────────────────────

    @staticmethod
    def delete_files(file_paths: List[str]) -> Dict:
        """Delete specific files by path. Returns summary."""
        deleted = 0
        freed = 0
        errors = []

        for fp in file_paths:
            p = Path(fp)
            if not p.exists():
                errors.append(f"Not found: {p.name}")
                continue
            try:
                if p.is_file():
                    size = p.stat().st_size
                    p.unlink()
                    deleted += 1
                    freed += size
                elif p.is_dir():
                    ds = sum(x.stat().st_size for x in p.rglob("*") if x.is_file())
                    shutil.rmtree(p)
                    deleted += 1
                    freed += ds
            except (PermissionError, OSError) as e:
                errors.append(f"Can't delete {p.name}: {e}")

        return {
            "deleted": deleted,
            "space_freed_bytes": freed,
            "space_freed_display": fmt_size(freed),
            "errors": errors,
        }

    @staticmethod
    def delete_duplicates(duplicate_groups: List[Dict]) -> Dict:
        """For each group, keep the first file and delete the rest."""
        deleted = 0
        freed = 0
        errors = []

        for group in duplicate_groups:
            files = group.get("files", [])
            if len(files) < 2:
                continue
            for f in files[1:]:
                p = Path(f["path"])
                try:
                    if p.exists():
                        freed += p.stat().st_size
                        p.unlink()
                        deleted += 1
                except (PermissionError, OSError) as e:
                    errors.append(f"Can't delete {p.name}: {e}")

        return {
            "deleted": deleted,
            "space_freed_bytes": freed,
            "space_freed_display": fmt_size(freed),
            "errors": errors,
        }
