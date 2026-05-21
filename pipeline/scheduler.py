"""
scheduler.py — Daily pipeline runner

Runs as a long-lived process on Railway.
Wakes up every day at RUN_TIME (UTC) and fires the pipeline.
"""

import os
import time
import datetime
import traceback

# Run time in UTC — change this to whatever time you want
RUN_TIME = os.getenv("RUN_TIME_UTC", "04:40")


def get_next_run(run_time_str: str) -> datetime.datetime:
    """Calculate the next run datetime from a HH:MM string."""
    now = datetime.datetime.utcnow()
    hour, minute = map(int, run_time_str.split(":"))

    next_run = now.replace(hour=hour, minute=minute, second=0, microsecond=0)

    # If that time already passed today, schedule for tomorrow
    if next_run <= now:
        next_run += datetime.timedelta(days=1)

    return next_run


def run_pipeline():
    """Import and run the pipeline."""
    from main import run_pipeline as _run
    _run()


def main():
    print("═══════════════════════════════════════")
    print("  Animal Reels Scheduler")
    print(f"  Daily run time: {RUN_TIME} UTC")
    print("═══════════════════════════════════════\n")

    while True:
        next_run = get_next_run(RUN_TIME)
        now      = datetime.datetime.utcnow()
        wait_sec = (next_run - now).total_seconds()

        print(f"[{now.strftime('%Y-%m-%d %H:%M:%S')} UTC] Next run scheduled at {next_run.strftime('%Y-%m-%d %H:%M:%S')} UTC")
        print(f"  Sleeping for {wait_sec / 3600:.1f} hours...\n")

        time.sleep(wait_sec)

        # Run the pipeline
        run_time = datetime.datetime.utcnow()
        print(f"\n[{run_time.strftime('%Y-%m-%d %H:%M:%S')} UTC] ▶ Starting daily pipeline run...\n")

        try:
            run_pipeline()
            print(f"\n[{datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC] ✓ Pipeline complete\n")
        except Exception as e:
            print(f"\n[{datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC] ✗ Pipeline failed: {e}")
            traceback.print_exc()
            print("\nScheduler will retry tomorrow.\n")

        # Small buffer to avoid double-firing
        time.sleep(60)


if __name__ == "__main__":
    main()
