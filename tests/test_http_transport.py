"""stdlib_transport against a real local http.server on 127.0.0.1 (never the internet)."""

import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from lit_vault_tools.clients.http import HttpResponse, stdlib_transport

seen: list[dict] = []


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def _record(self, body: bytes = b""):
        seen.append({"method": self.command, "path": self.path, "headers": list(self.headers.keys()), "body": body})

    def do_GET(self):
        self._record()
        if self.path == "/missing":
            self.send_response(404)
            self.send_header("Content-Length", "0")
            self.end_headers()
        elif self.path == "/redirect":
            self.send_response(302)
            self.send_header("Location", "/final")
            self.send_header("Content-Length", "0")
            self.end_headers()
        else:
            payload = b"hello " + self.path.encode()
            self.send_response(200)
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

    def do_POST(self):
        body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        self._record(body)
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


@pytest.fixture
def base():
    seen.clear()
    server = HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}"
    server.shutdown()
    server.server_close()


def test_200_returns_status_and_body(base):
    assert stdlib_transport("GET", base + "/ok?a=1", {}, None) == HttpResponse(200, b"hello /ok?a=1")


def test_404_is_returned_not_raised(base):
    assert stdlib_transport("GET", base + "/missing", {}, None).status == 404


def test_post_body_arrives_byte_identical(base):
    body = b'{"ids": ["a", "b"]}\x00\xff'
    response = stdlib_transport("POST", base + "/batch", {"Content-Type": "application/json"}, body)
    assert response == HttpResponse(200, body)
    assert seen[-1]["method"] == "POST"
    assert seen[-1]["body"] == body


def test_302_is_followed_to_location(base):
    response = stdlib_transport("GET", base + "/redirect", {}, None)
    assert response == HttpResponse(200, b"hello /final")
    assert [s["path"] for s in seen] == ["/redirect", "/final"]


def test_header_name_case_is_preserved(base):
    stdlib_transport("GET", base + "/ok", {"x-api-key": "test-key"}, None)
    assert "x-api-key" in seen[-1]["headers"]
