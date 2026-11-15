"""The launcher's "port in use" check must look at listeners, not lingering connections."""

import shutil
import socket
import time

import pytest

from agent.dev import port_is_free

needs_lsof = pytest.mark.skipif(shutil.which("lsof") is None, reason="lsof unavailable")


def listener(host: str) -> socket.socket:
    server = socket.socket()
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)  # as uvicorn and Next do
    server.bind((host, 0))
    server.listen()
    return server


@needs_lsof
def test_a_port_with_only_lingering_connections_is_free():
    # The server stops first, as when Cues is stopped while a browser tab is still open.
    server = listener("127.0.0.1")
    port = server.getsockname()[1]
    client = socket.create_connection(("127.0.0.1", port))
    connection, _ = server.accept()
    connection.close()
    server.close()
    time.sleep(0.2)
    try:
        with socket.socket() as probe:
            try:
                probe.bind(("127.0.0.1", port))
            except OSError:
                pass  # the situation under test: a plain bind refuses the port
            else:
                pytest.skip("this system does not hold the port after a server stops")
        assert port_is_free(port)  # nothing is listening: the real servers would start fine
    finally:
        client.close()


@needs_lsof
@pytest.mark.parametrize("host", ["127.0.0.1", "0.0.0.0"])
def test_a_live_listener_is_in_use(host):
    # Including a wildcard listener like Next's, which a SO_REUSEADDR bind would slip past.
    server = listener(host)
    try:
        assert not port_is_free(server.getsockname()[1])
    finally:
        server.close()


@needs_lsof
def test_a_port_nobody_has_used_is_free():
    server = listener("127.0.0.1")
    port = server.getsockname()[1]
    server.close()
    assert port_is_free(port)


def test_without_lsof_it_falls_back_to_the_strict_bind_test(monkeypatch):
    import agent.dev as dev

    def missing(*args, **kwargs):
        raise FileNotFoundError("lsof")

    monkeypatch.setattr(dev.subprocess, "run", missing)
    server = listener("127.0.0.1")
    port = server.getsockname()[1]
    try:
        assert not port_is_free(port)  # in use: the strict bind is refused
    finally:
        server.close()
    assert port_is_free(port) in (True, False)  # a closed port never raises
