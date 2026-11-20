import os

import uvicorn

UVICORN_LIMIT_CONCURRENCY = 100


def main() -> None:
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", "8000")),
        limit_concurrency=UVICORN_LIMIT_CONCURRENCY,
    )


if __name__ == "__main__":
    main()
