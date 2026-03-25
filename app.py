"""
CleanAgent — Flask Application v2.0
Thread-safe, AI-powered recommendations, auto-browser launch.
"""

import os
import sys
import threading
import webbrowser
import platform
import logging
from flask import Flask, render_template, jsonify, request, send_from_directory
from scanner import SystemScanner
from cleaner import SystemCleaner
from ai_advisor import AIAdvisor

# ── Logging ──────────────────────────────────────────────
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("cleanagent")

# ── Resolve paths for PyInstaller bundled mode ───────────
def resource_path(relative_path):
    """Get absolute path to resource — works for dev and PyInstaller."""
    if getattr(sys, "_MEIPASS", None):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.abspath(os.path.dirname(__file__)), relative_path)


template_dir = resource_path("templates")
static_dir = resource_path("static")
app = Flask(__name__, template_folder=template_dir, static_folder=static_dir)

# ── Thread-safe state ────────────────────────────────────
_lock = threading.Lock()
scan_results = {}
scan_in_progress = False
scan_progress = {"stage": "", "percent": 0}
pre_cleanup_score = None


# ── Routes ───────────────────────────────────────────────

@app.route("/")
def dashboard():
    return render_template("dashboard.html")


@app.route("/api/scan", methods=["POST"])
def start_scan():
    global scan_results, scan_in_progress, scan_progress

    with _lock:
        if scan_in_progress:
            return jsonify({"error": "Scan already in progress"}), 409

    def run_scan():
        global scan_results, scan_in_progress, scan_progress
        with _lock:
            scan_in_progress = True
            scan_progress = {"stage": "Starting...", "percent": 0}

        try:
            scanner = SystemScanner()

            with _lock:
                scan_progress = {"stage": "Collecting system metrics...", "percent": 10}
            metrics = scanner.get_metrics()

            with _lock:
                scan_progress = {"stage": "Analyzing caches...", "percent": 25}
            caches = scanner.analyze_caches()

            with _lock:
                scan_progress = {"stage": "Finding large files...", "percent": 40}
            large_files = scanner.find_large_files()

            with _lock:
                scan_progress = {"stage": "Detecting duplicates...", "percent": 55}
            duplicates = scanner.find_duplicates()

            with _lock:
                scan_progress = {"stage": "Analyzing downloads...", "percent": 70}
            downloads = scanner.analyze_downloads()


            with _lock:
                scan_progress = {"stage": "Scanning installed apps...", "percent": 78}
            installed_apps = scanner.scan_installed_apps()
            unused_apps = [a for a in installed_apps if a.get("is_unused")]

            with _lock:
                scan_progress = {"stage": "Checking processes & startup...", "percent": 85}
            startup = scanner.get_startup_items()
            processes = scanner.get_top_processes()

            # Recoverable space calculation
            recoverable = caches["total_size_mb"]
            recoverable += sum(d["wasted_mb"] for d in duplicates)
            recoverable += sum(f["size_mb"] for f in downloads.get("old_files", []))

            raw_data = {
                "metrics": metrics.to_dict(),
                "caches": caches,
                "large_files": large_files,
                "duplicates": duplicates,
                "downloads": downloads,
                "installed_apps": installed_apps,
                "unused_apps": unused_apps,
                "startup_items": startup,
                "top_processes": processes,
                "summary": {
                    "performance_score": metrics.performance_score,
                    "recoverable_space_mb": round(recoverable, 1),
                    "total_issues": (
                        (1 if caches["total_size_mb"] > 500 else 0)
                        + len(duplicates)
                        + (1 if len(downloads.get("old_files", [])) > 5 else 0)
                        + (1 if metrics.memory_usage > 80 else 0)
                        + (1 if metrics.disk_usage > 85 else 0)
                    ),
                },
            }

            # AI recommendations
            with _lock:
                scan_progress = {"stage": "Generating AI recommendations...", "percent": 95}
            try:
                advisor = AIAdvisor()
                ai_result = advisor.analyze(raw_data)
                raw_data["ai_advice"] = ai_result
            except Exception as e:
                log.warning(f"AI advisor failed (non-fatal): {e}")
                raw_data["ai_advice"] = {"recommendations": [], "summary": {"verdict": "unknown", "verdict_text": "Analysis unavailable."}}

            with _lock:
                scan_progress = {"stage": "Complete!", "percent": 100}
                scan_results = raw_data
                log.info(f"Scan complete — score: {metrics.performance_score}, recoverable: {recoverable:.1f} MB")

        except Exception as e:
            log.error(f"Scan failed: {e}", exc_info=True)
            with _lock:
                scan_results = {"error": str(e)}
        finally:
            with _lock:
                scan_in_progress = False

    threading.Thread(target=run_scan, daemon=True).start()
    return jsonify({"status": "started"})


@app.route("/api/scan/progress")
def get_progress():
    with _lock:
        return jsonify({
            "in_progress": scan_in_progress,
            "stage": scan_progress.get("stage", ""),
            "percent": scan_progress.get("percent", 0),
        })


@app.route("/api/scan/results")
def get_results():
    with _lock:
        if scan_in_progress:
            return jsonify({"status": "scanning"})
        if not scan_results:
            return jsonify({"status": "no_scan"})
        return jsonify({"status": "complete", "data": scan_results})


@app.route("/api/cleanup", methods=["POST"])
def run_cleanup():
    global pre_cleanup_score
    try:
        scanner = SystemScanner()
        pre_metrics = scanner.get_metrics()
        pre_cleanup_score = {
            "disk_free_gb": pre_metrics.disk_free_gb,
            "performance_score": pre_metrics.performance_score,
        }

        cleaner = SystemCleaner()
        results = cleaner.run_all()

        post_metrics = scanner.get_metrics()
        results["comparison"] = {
            "disk_before_gb": pre_cleanup_score["disk_free_gb"],
            "disk_after_gb": post_metrics.disk_free_gb,
            "disk_recovered_gb": round(post_metrics.disk_free_gb - pre_cleanup_score["disk_free_gb"], 1),
            "score_before": pre_cleanup_score["performance_score"],
            "score_after": post_metrics.performance_score,
        }

        log.info(f"Cleanup complete — freed {results['total_space_freed_display']}")
        return jsonify({"status": "complete", "data": results})
    except Exception as e:
        log.error(f"Cleanup failed: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@app.route("/api/cleanup/duplicates", methods=["POST"])
def cleanup_duplicates():
    try:
        data = request.get_json()
        groups = data.get("groups", [])
        if not groups:
            return jsonify({"error": "No groups provided"}), 400
        result = SystemCleaner.delete_duplicates(groups)
        return jsonify({"status": "complete", "data": result})
    except Exception as e:
        log.error(f"Duplicate cleanup failed: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@app.route("/api/cleanup/files", methods=["POST"])
def cleanup_files():
    try:
        data = request.get_json()
        paths = data.get("paths", [])
        if not paths:
            return jsonify({"error": "No paths provided"}), 400
        result = SystemCleaner.delete_files(paths)
        return jsonify({"status": "complete", "data": result})
    except Exception as e:
        log.error(f"File cleanup failed: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500




@app.route("/api/uninstall", methods=["POST"])
def uninstall_app():
    try:
        data = request.get_json()
        app_path = data.get("path", "")
        if not app_path:
            return jsonify({"error": "No app path provided"}), 400
        result = SystemCleaner.uninstall_app(app_path)
        if result.get("success"):
            return jsonify({"status": "complete", "data": result})
        else:
            return jsonify({"error": result.get("error", "Unknown error")}), 500
    except Exception as e:
        log.error(f"Uninstall failed: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500

@app.route("/api/metrics")
def live_metrics():
    try:
        scanner = SystemScanner()
        return jsonify(scanner.get_metrics().to_dict())
    except Exception as e:
        log.error(f"Metrics failed: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/info")
def app_info():
    return jsonify({
        "name": "CleanAgent",
        "version": "2.0.0",
        "platform": platform.system(),
        "python": platform.python_version(),
    })


# ── Auto-open browser ───────────────────────────────────
def open_browser():
    """Open the dashboard in the default browser after a short delay."""
    import time
    time.sleep(1.5)
    webbrowser.open("http://127.0.0.1:5000")


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    log.info(f"CleanAgent v2.0 starting on http://127.0.0.1:{port}")

    # Auto-open browser (only in production / exe mode, not during dev reload)
    if not os.environ.get("WERKZEUG_RUN_MAIN"):
        threading.Thread(target=open_browser, daemon=True).start()

    app.run(host="127.0.0.1", port=port, debug=False)
