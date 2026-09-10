"""
start.py — Launches both dashboard server and daily scheduler in parallel.
Railway only needs one service to run both.
"""

import threading
import os
from dashboard_server import DashboardHandler, PORT
from http.server import HTTPServer


def run_dashboard():
    print(f"[Dashboard] Starting on port {PORT}")
    server = HTTPServer(("0.0.0.0", PORT), DashboardHandler)
    server.serve_forever()


def run_scheduler():
    import time
    import datetime
    import traceback

    RUN_TIME = os.getenv("RUN_TIME_UTC", "04:00")
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
    # Dashboard runs in background thread
    dashboard_thread = threading.Thread(target=run_dashboard, daemon=True)
    dashboard_thread.start()

    # Scheduler runs in main thread
    run_scheduler()
