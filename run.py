"""Поднять шлюз, всех агентов и страницу Vite.

Остановка: Ctrl+C. Страница ходит в шлюз :8080. Агенты слушают только 127.0.0.1.
"""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BACKEND = ROOT / "backend"
FRONTEND = ROOT / "frontend"
PYTHON = ROOT / ".venv" / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")

SERVICES = (
    ("gateway", "gateway.main:app", 8080),
    ("geo", "geo.main:app", 8081),
    ("view", "view.main:app", 8082),
    ("noise", "noise.main:app", 8083),
    ("mobility", "mobility.main:app", 8084),
    ("events", "events.main:app", 8085),
    ("hotelier", "hotelier.main:app", 8086),
    ("conflict", "conflict.main:app", 8087),
    ("search", "search.main:app", 8088),
    ("hotel_faq", "hotel_faq.main:app", 8092),
)
FRONTEND_PORT = 5173


def port_busy(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.3)
        return sock.connect_ex(("127.0.0.1", port)) == 0


def pump(name: str, proc: subprocess.Popen[str]) -> None:
    if proc.stdout is None:
        return
    for line in proc.stdout:
        print(f"[{name}] {line}", end="", flush=True)


def stop(procs: list[tuple[str, subprocess.Popen[str]]]) -> None:
    for _name, proc in procs:
        if proc.poll() is not None:
            continue
        if sys.platform == "win32":
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )
        else:
            proc.terminate()
    for _name, proc in procs:
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


def wait_ready(name: str, proc: subprocess.Popen[str], port: int, timeout: float = 90) -> bool:
    import urllib.error
    import urllib.request

    deadline = time.monotonic() + timeout
    url = f"http://127.0.0.1:{port}/health"
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            print(f"{name} завершился с кодом {proc.returncode}", file=sys.stderr)
            return False
        try:
            with urllib.request.urlopen(url, timeout=1) as response:
                if response.status == 200:
                    return True
        except (urllib.error.URLError, TimeoutError, OSError):
            time.sleep(0.3)
    print(f"{name} не ответил на {url} за {int(timeout)} с", file=sys.stderr)
    return False


def spawn(name: str, args: list[str], cwd: Path, flags: int) -> subprocess.Popen[str]:
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    proc = subprocess.Popen(
        args,
        cwd=cwd,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        creationflags=flags,
    )
    threading.Thread(target=pump, args=(name, proc), daemon=True).start()
    return proc


def main() -> int:
    if not PYTHON.exists():
        print("Нет .venv. Из корня: python -m venv .venv", file=sys.stderr)
        print("Затем: .\\.venv\\Scripts\\python.exe -m pip install -r backend\\requirements.txt", file=sys.stderr)
        return 1
    if not (FRONTEND / "node_modules").exists():
        print("Нет frontend/node_modules. В каталоге frontend: npm ci", file=sys.stderr)
        return 1

    taken = [port for _name, _module, port in SERVICES if port_busy(port)]
    if port_busy(FRONTEND_PORT):
        taken.append(FRONTEND_PORT)
    if taken:
        ports = ", ".join(str(port) for port in taken)
        print(f"Порт уже занят: {ports}. Остановите прошлый запуск и повторите.", file=sys.stderr)
        return 1

    print("Страница  http://127.0.0.1:5173")
    print("Шлюз     http://127.0.0.1:8080")
    for name, _module, port in SERVICES:
        if name == "gateway":
            continue
        print(f"{name:<10} http://127.0.0.1:{port}/health")
    print("Остановка: Ctrl+C")

    flags = subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0
    procs: list[tuple[str, subprocess.Popen[str]]] = []
    try:
        gateway_name, gateway_module, gateway_port = SERVICES[0]
        gateway = spawn(
            gateway_name,
            [str(PYTHON), "-m", "uvicorn", gateway_module, "--host", "127.0.0.1", "--port", str(gateway_port)],
            BACKEND,
            flags,
        )
        procs.append((gateway_name, gateway))
        if not wait_ready(gateway_name, gateway, gateway_port):
            return 1

        for name, module, port in SERVICES[1:]:
            proc = spawn(
                name,
                [str(PYTHON), "-m", "uvicorn", module, "--host", "127.0.0.1", "--port", str(port)],
                BACKEND,
                flags,
            )
            procs.append((name, proc))

        npm = "npm.cmd" if sys.platform == "win32" else "npm"
        front = spawn(
            "frontend",
            [npm, "run", "dev", "--", "--host", "127.0.0.1", "--port", str(FRONTEND_PORT)],
            FRONTEND,
            flags,
        )
        procs.append(("frontend", front))

        while True:
            for name, proc in procs:
                code = proc.poll()
                if code is not None:
                    print(f"{name} завершился с кодом {code}", file=sys.stderr)
                    return code or 1
            time.sleep(0.5)
    except KeyboardInterrupt:
        print("\nОстанавливаю процессы.")
        return 0
    finally:
        stop(procs)


if __name__ == "__main__":
    raise SystemExit(main())
