"""
start.py — Launches both dashboard server and daily scheduler in parallel.
"""

import threading
import os
import time
from http.server import HTTPServer

PORT = int(os.getenv("PORT", "8080"))


def run_dashboard():
    from dashboard_server import DashboardHandler
    for attempt in range(5):
        try:
            print(f"[Dashboard] Starting on port {PORT}")
            server = HTTPServer(("0.0.0.0", PORT), DashboardHandler)
            server.serve_forever()
            break
        except OSError as e:
            if "Address already in use" in str(e) and attempt < 4:
                print(f"[Dashboard] Port {PORT} busy — waiting 10s before retry {attempt+1}/5...")
                time.sleep(10)
            else:
                print(f"[Dashboard] Could not start — {e}")
                break


def run_scheduler():
    import datetime
    import traceback

    RUN_TIME = os.getenv("RUN_TIME_UTC", "04:15")
    print(f"[Scheduler] Daily run time: {RUN_TIME} UTC")

    while True:
        now      = datetime.datetime.utcnow()
        hour, minute = map(int, RUN_TIME.split(":"))
        next_run = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if next_run <= now:
            next_run += datetime.timedelta(days=1)

        wait_sec = (next_run - now).total_seconds()
        print(f"[Scheduler] Next run at {next_run.strftime('%Y-%m-%d %H:%M')} UTC ({wait_sec/3600:.1f}h away)")
        time.sleep(wait_sec)

        print(f"\n[Scheduler] Starting pipeline run...\n")
        try:
            from main import run_pipeline
            run_pipeline()
            print(f"\n[Scheduler] Pipeline complete\n")
        except Exception as e:
            print(f"\n[Scheduler] Pipeline failed: {e}")
            traceback.print_exc()

        time.sleep(60)


if __name__ == "__main__":
    # Wait on startup to let old process release port
    time.sleep(5)

    # Dashboard in background thread
    dashboard_thread = threading.Thread(target=run_dashboard, daemon=True)
    dashboard_thread.start()

    # Scheduler in main thread
    run_scheduler()
