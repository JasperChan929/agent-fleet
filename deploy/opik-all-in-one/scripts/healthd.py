#!/usr/bin/env python3
import json
import os
import socket
import subprocess
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


def run(command, env=None):
    try:
        result = subprocess.run(
            command,
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=3,
            check=False,
        )
        return result.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def supervisor_running(program):
    try:
        result = subprocess.run(
            ["/usr/local/bin/supervisorctl", "status", program],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=3,
            check=False,
            text=True,
        )
        return result.returncode == 0 and " RUNNING " in result.stdout
    except (OSError, subprocess.TimeoutExpired):
        return False


def http_ok(url):
    try:
        with urllib.request.urlopen(url, timeout=3) as response:
            return 200 <= response.status < 300
    except Exception:
        return False


def tcp_ok(port, payload=None, expected=None):
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=2) as sock:
            if payload is not None:
                sock.sendall(payload)
                data = sock.recv(128)
                return expected is None or expected in data
            return True
    except OSError:
        return False


def readiness():
    mysql_env = os.environ.copy()
    mysql_env["MYSQL_PWD"] = os.environ.get("MYSQL_PASSWORD", "")
    redis_env = os.environ.copy()
    redis_env["REDISCLI_AUTH"] = os.environ.get("REDIS_PASSWORD", "")

    checks = {
        "bootstrap": os.path.exists("/run/opik/bootstrap-complete"),
        "mysql": run(
            ["/usr/bin/mysqladmin", "--protocol=tcp", "-h127.0.0.1", "-P3306", "-uopik", "ping"],
            mysql_env,
        ),
        "redis": run(["/usr/local/bin/redis-cli", "-h", "127.0.0.1", "-p", "6379", "ping"], redis_env),
        "zookeeper": tcp_ok(2181, b"ruok\n", b"imok"),
        "clickhouse": http_ok("http://127.0.0.1:8123/ping"),
        "minio": http_ok("http://127.0.0.1:9002/minio/health/live"),
        "backend": http_ok("http://127.0.0.1:8080/health-check"),
    }
    checks["supervisor"] = all(
        supervisor_running(program)
        for program in ("mysql", "redis", "zookeeper", "clickhouse", "minio", "opik-backend", "nginx")
    )
    return checks


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/health":
            self.respond(200, {"status": "ok"})
            return
        if self.path == "/readyz":
            checks = readiness()
            ready = all(checks.values())
            self.respond(200 if ready else 503, {"status": "ready" if ready else "not_ready", "checks": checks})
            return
        self.respond(404, {"status": "not_found"})

    def log_message(self, fmt, *args):
        return

    def respond(self, status, payload):
        body = (json.dumps(payload, sort_keys=True) + "\n").encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


if __name__ == "__main__":
    server = ThreadingHTTPServer(("127.0.0.1", 5180), Handler)
    server.serve_forever()
