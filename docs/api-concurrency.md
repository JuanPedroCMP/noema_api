# API concurrency

Start the API with:

```bash
python run.py
```

This configures Uvicorn to allow up to 100 concurrent connections/tasks per
process. Requests above that limit receive HTTP 503; this is a limit, not a
queue. Set `PORT` to override the default port `8000`.

If the API is deployed with a platform-specific startup command, change that
command to `python run.py` for this setting to take effect. Multiple processes
or replicas each have their own limit, so total concurrency is multiplied by
their count.

The database pool is separate from the request limit. This project defaults to
15 connections plus up to 15 overflow connections per process
(`DB_POOL_SIZE` and `DB_MAX_OVERFLOW`). Tune those values only against the
database's total connection capacity, accounting for all API processes and
other clients.
