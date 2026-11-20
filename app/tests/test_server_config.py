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
