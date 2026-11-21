# API concurrency

Start the API with:

```bash
python run.py
```

By default, Uvicorn allows up to 100 concurrent connections/tasks per worker.
Configure the cap and worker-process count with `UVICORN_LIMIT_CONCURRENCY` and
`WEB_CONCURRENCY`. For example:

```bash
UVICORN_LIMIT_CONCURRENCY=10000 WEB_CONCURRENCY=2 python run.py
```

The cap is per worker process; the total configured cap is
`UVICORN_LIMIT_CONCURRENCY * WEB_CONCURRENCY` per application instance. Requests
above that cap receive HTTP 503; this is a limit, not a queue. Set `PORT` to
override the default port `8000`.

If the API is deployed with a platform-specific startup command, change that
command to `python run.py` for this setting to take effect. Replicas each have
their own processes and limits, so total concurrency is multiplied by the
number of replicas as well.

The database pool is separate from the request limit. This project defaults to
15 connections plus up to 15 overflow connections per process
(`DB_POOL_SIZE` and `DB_MAX_OVERFLOW`). Tune those values only against the
database's total connection capacity, accounting for all API processes and
other clients. A high request cap does not make the database or external AI and
Google APIs capable of the same concurrency; they remain bounded by their own
connection pools, quotas, and the instance's CPU and memory.

Some state is currently process-local, including the Google Drive request
rate-limit counters and access-token cache. Increasing `WEB_CONCURRENCY` or the
replica count does not share that state; distributed deployments need a shared
store for globally consistent limits and caches.
