"""
CleanAgent — AI Advisor Engine v2.0
Analyzes scan results and generates prioritized, actionable recommendations.
"""

from dataclasses import dataclass, asdict
from typing import List, Dict


@dataclass
class Recommendation:
    id: str
    priority: str
    category: str
    title: str
    description: str
    impact_label: str
    impact_score: float
    action: str
    auto_fixable: bool
    icon: str

    def to_dict(self):
        return asdict(self)


PRIORITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}


class AIAdvisor:
    def analyze(self, scan_data: Dict) -> Dict:
        recs: List[Recommendation] = []
        metrics = scan_data.get("metrics", {})
        caches = scan_data.get("caches", {})
        duplicates = scan_data.get("duplicates", [])
        downloads = scan_data.get("downloads", {})
        large_files = scan_data.get("large_files", [])
        processes = scan_data.get("top_processes", [])

        self._check_caches(recs, caches)
        self._check_duplicates(recs, duplicates)
        self._check_downloads(recs, downloads)
        self._check_large_files(recs, large_files)
        self._check_cpu(recs, metrics)
        self._check_memory(recs, metrics)
        self._check_disk(recs, metrics)
        self._check_uptime(recs, metrics)
        self._check_processes(recs, processes)
        unused_apps = scan_data.get("unused_apps", [])
        self._check_unused_apps(recs, unused_apps)

        recs.sort(key=lambda r: (PRIORITY_ORDER.get(r.priority, 9), -r.impact_score))

        critical = sum(1 for r in recs if r.priority == "critical")
        high = sum(1 for r in recs if r.priority == "high")
        auto_fix = sum(1 for r in recs if r.auto_fixable)

        if critical > 0:
            verdict, verdict_text = "needs_attention", "Your system needs attention — critical issues found."
        elif high > 0:
            verdict, verdict_text = "fair", "Running okay, but optimizations would help."
        elif recs:
            verdict, verdict_text = "good", "System is in good shape. Minor tweaks available."
        else:
            verdict, verdict_text = "excellent", "Running great! No issues detected."

        return {
            "recommendations": [r.to_dict() for r in recs],
            "summary": {
                "total": len(recs),
                "critical": critical,
                "high": high,
                "auto_fixable": auto_fix,
                "verdict": verdict,
                "verdict_text": verdict_text,
            },
        }

    def _check_caches(self, recs, caches):
        mb = caches.get("total_size_mb", 0)
        disp = caches.get("total_display", f"{mb:.0f} MB")
        if mb > 2000:
            recs.append(Recommendation("cache_critical", "critical", "storage", "Massive cache buildup", f"Caches total {disp}. Slowing I/O and eating disk.", f"{disp} recoverable", min(40, mb/100), "Run Safe Cleanup.", True, "🗑️"))
        elif mb > 500:
            recs.append(Recommendation("cache_high", "high", "storage", "Large cache accumulation", f"Caches total {disp}.", f"{disp} recoverable", min(25, mb/100), "Run Safe Cleanup.", True, "🗑️"))
        elif mb > 100:
            recs.append(Recommendation("cache_medium", "medium", "storage", "Moderate cache size", f"Caches are {disp}.", f"{disp} recoverable", min(10, mb/100), "Cleanup when convenient.", True, "📦"))

    def _check_duplicates(self, recs, duplicates):
        if not duplicates: return
        w = sum(d.get("wasted_mb", 0) for d in duplicates)
        p = "critical" if w > 500 else ("high" if w > 100 else "medium")
        recs.append(Recommendation("duplicates", p, "storage", f"{len(duplicates)} duplicate groups", f"Identical files wasting ~{w:.0f} MB.", f"{w:.0f} MB recoverable", min(20, w/50), "Remove All Duplicates.", True, "📋"))

    def _check_downloads(self, recs, downloads):
        old = downloads.get("old_files", [])
        if not old: return
        mb = sum(f.get("size_mb", 0) for f in old)
        p = "high" if (mb > 500 or len(old) > 15) else "medium"
        recs.append(Recommendation("old_downloads", p, "storage", f"{len(old)} old files in Downloads", f"Files older than 30 days (~{mb:.0f} MB).", f"~{mb:.0f} MB recoverable", min(15, mb/100), "Review and delete.", True, "📥"))

    def _check_large_files(self, recs, large_files):
        if not large_files: return
        t = sum(f.get("size_mb", 0) for f in large_files)
        recs.append(Recommendation("large_files", "medium", "storage", f"{len(large_files)} large files ({t:.0f} MB)", "Files over 100 MB. Consider external storage.", f"{t:.0f} MB potential", min(15, t/500), "Review Large Files.", False, "📦"))

    def _check_cpu(self, recs, m):
        cpu = m.get("cpu_usage", 0)
        if cpu > 80:
            recs.append(Recommendation("cpu_high", "critical", "performance", "CPU very high", f"CPU at {cpu}%. Expect slowdowns.", "System slowdown", 30, "Quit unused apps.", False, "🔥"))
        elif cpu > 50:
            recs.append(Recommendation("cpu_moderate", "medium", "performance", "Elevated CPU", f"CPU at {cpu}%.", "Moderate impact", 10, "Review processes.", False, "⚡"))

    def _check_memory(self, recs, m):
        mem = m.get("memory_usage", 0)
        if mem > 85:
            recs.append(Recommendation("mem_critical", "critical", "performance", "Memory pressure critical", f"Memory at {mem}%. Likely swapping.", "Severe slowdown", 35, "Close apps or restart.", False, "🧠"))
        elif mem > 70:
            recs.append(Recommendation("mem_high", "high", "performance", "High memory usage", f"Memory at {mem}%.", "Performance risk", 15, "Close tabs and apps.", False, "🧠"))

    def _check_disk(self, recs, m):
        d = m.get("disk_usage", 0)
        f = m.get("disk_free_gb", "?")
        if d > 90:
            recs.append(Recommendation("disk_critical", "critical", "performance", "Disk almost full", f"Only {f} GB free. OS needs 10-15% for swap.", "Critical", 40, "Free space now.", True, "💾"))
        elif d > 80:
            recs.append(Recommendation("disk_high", "high", "performance", "Disk space low", f"{f} GB free.", f"{f} GB remaining", 20, "Run cleanup.", True, "💾"))

    def _check_uptime(self, recs, m):
        days = m.get("uptime_days", 0)
        if days > 14:
            recs.append(Recommendation("uptime_long", "high", "maintenance", f"No restart in {int(days)} days", "Accumulated memory leaks and bloat.", "Quick boost", 20, "Restart your computer.", False, "🔄"))
        elif days > 7:
            recs.append(Recommendation("uptime_moderate", "medium", "maintenance", f"Consider restart ({int(days)}d uptime)", "Weekly restarts help.", "Moderate", 10, "Restart when convenient.", False, "🔄"))


    def _check_unused_apps(self, recs, apps):
        if not apps:
            return
        unused = [a for a in apps if a.get("is_unused")]
        if not unused:
            return
        total_mb = sum(a.get("size_mb", 0) for a in unused)
        p = "critical" if total_mb > 2000 else ("high" if total_mb > 500 else "medium")
        recs.append(Recommendation(
            "unused_apps", p, "storage",
            f"{len(unused)} unused applications ({total_mb:.0f} MB)",
            f"Apps not opened in 6+ months. Removing them frees significant disk space.",
            f"{total_mb:.0f} MB recoverable",
            min(30, total_mb / 100),
            "Review and uninstall unused apps.",
            True, "\U0001f4f1"
        ))

    def _check_processes(self, recs, processes):
        heavy = [p for p in processes if p.get("cpu_percent", 0) > 30]
        if not heavy: return
        names = ", ".join(p["name"] for p in heavy[:3])
        recs.append(Recommendation("heavy_procs", "medium", "performance", f"{len(heavy)} heavy processes", f"High usage: {names}", "Background drain", 10, "Close if not needed.", False, "📊"))
