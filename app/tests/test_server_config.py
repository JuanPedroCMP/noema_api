import run


def test_server_starts_with_concurrency_limit_of_100(monkeypatch):
    server_options = {}
    monkeypatch.setenv("PORT", "9000")
    monkeypatch.setattr(
        run.uvicorn,
        "run",
        lambda *_args, **kwargs: server_options.update(kwargs),
    )

    run.main()

    assert server_options["limit_concurrency"] == 100
    assert server_options["port"] == 9000
    assert server_options["workers"] == 1


def test_server_concurrency_and_workers_are_configurable(monkeypatch):
    server_options = {}
    monkeypatch.setenv("UVICORN_LIMIT_CONCURRENCY", "10000")
    monkeypatch.setenv("WEB_CONCURRENCY", "2")
    monkeypatch.setattr(
        run.uvicorn,
        "run",
        lambda *_args, **kwargs: server_options.update(kwargs),
    )

    run.main()

    assert server_options["limit_concurrency"] == 10000
    assert server_options["workers"] == 2


def test_server_rejects_invalid_concurrency_configuration(monkeypatch):
    monkeypatch.setenv("UVICORN_LIMIT_CONCURRENCY", "unlimited")

    try:
        run.main()
    except RuntimeError as error:
        assert "UVICORN_LIMIT_CONCURRENCY" in str(error)
    else:
        raise AssertionError("Invalid concurrency configuration was accepted.")
