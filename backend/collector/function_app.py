"""Collector Function app.

A timer trigger runs the Azure CLI (az) on a schedule, builds the availability
snapshot (regions, VM SKUs, Azure Managed Redis, other services) and publishes it
to Azure Managed Redis. The schedule is the NCRONTAB expression in the
COLLECT_SCHEDULE app setting (UTC, default every 6 hours).
"""
import json
import logging

import azure.functions as func

app = func.FunctionApp()


@app.timer_trigger(schedule="%COLLECT_SCHEDULE%", arg_name="timer",
                   run_on_startup=False, use_monitor=True)
def collect(timer: func.TimerRequest) -> None:
    # Imported lazily so the Functions host indexes this app quickly.
    from availability import collector

    if timer.past_due:
        logging.warning("Schedule is past due, collecting now.")
    stats = collector.run(trigger="timer")
    logging.info("Collection finished: %s", json.dumps(stats))
