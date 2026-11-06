"""Start the native local Nova stack; no launcher dependencies are required."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import signal
import socket
import subprocess
import time
from urllib.error import URLError
from urllib.parse import urlsplit
from urllib.request import urlopen
import webbrowser

from _dev_processes import Services

ROOT = Path(__file__).resolve().parents[1]


def backend_python(root: Path) -> Path:
    for path in (root / ".venv/Scripts/python.exe", root / ".venv/bin/python"):
        if path.is_file():
            return path
    raise RuntimeError("Missing .venv. Follow README Quick start to install the backend first.")


def read_config(python: Path, root: Path) -> dict:
    # Use exactly the backend's dotenv/default/OS-environment precedence. Return
    # only the fields needed by the launcher, never keys or database URLs.
    probe = """
import importlib.util, json
from config.settings import settings as s
assert importlib.util.find_spec('uvicorn'), 'Install backend/requirements.txt'
print(json.dumps(dict(provider=s.LLM_PROVIDER, model=s.MODEL_NAME,
    ollama_url=s.OLLAMA_URL, environment=s.ENVIRONMENT, redis=bool(s.REDIS_URL),
    groq_configured=bool(s.GROQ_API_KEY) and not s.GROQ_API_KEY.startswith('gsk_your'),
    cors=s.CORS_ORIGINS)))
"""
    result = subprocess.run(
        [str(python), "-c", probe], cwd=root / "backend", capture_output=True,
        text=True, encoding="utf-8", timeout=20,
    )
    if result.returncode:
        raise RuntimeError("Cannot load backend settings/dependencies. Check backend/.env and install backend/requirements.txt.")
    return json.loads(result.stdout)


def require_free_port(port: int):
    with socket.socket() as listener:
        if os.name == "nt":
            listener.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        try:
            listener.bind(("127.0.0.1", port))
        except OSError as error:
            raise RuntimeError(f"Port {port} is already in use. Stop the existing service or choose another port; no process was killed.") from error


def get_json(url: str) -> dict:
    with urlopen(url, timeout=10) as response:
        value = json.load(response)
    if not isinstance(value, dict):
        raise ValueError("Expected a JSON object")
    return value


def wait_for(label, check, services: Services, timeout: float):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        services.check()
        try:
            value = check()
            if value:
                return value
        except (URLError, TimeoutError, ConnectionError, ValueError):
            pass
        time.sleep(0.5)
    raise RuntimeError(f"Timed out waiting for {label}. Check service logs and backend/.env.")


def model_installed(tags: dict, requested: str) -> bool:
    normalize = lambda name: name if ":" in name.rsplit("/", 1)[-1] else name + ":latest"
    return any(
        isinstance(item, dict) and isinstance(item.get("name"), str)
        and normalize(item["name"]) == normalize(requested)
        for item in tags.get("models", [])
    )


def local_ollama_host(url: str) -> str:
    parsed = urlsplit(url)
    if (parsed.scheme != "http" or parsed.hostname not in {"localhost", "127.0.0.1", "::1"}
            or parsed.username or parsed.password or parsed.path not in {"", "/"}
            or parsed.query or parsed.fragment):
        raise RuntimeError("OLLAMA_URL is not a local HTTP server. Start that provider separately; the launcher will reuse it when reachable.")
    host = f"[{parsed.hostname}]" if parsed.hostname == "::1" else parsed.hostname
    return f"{host}:{parsed.port or 80}"


def ensure_ollama(config, services: Services, env, timeout, pull_model, root):
    base = config["ollama_url"].rstrip("/")
    parsed = urlsplit(base)
    if parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.scheme not in {"http", "https"}:
        raise RuntimeError("OLLAMA_URL must be an HTTP(S) endpoint without embedded credentials, query or fragment.")
    try:
        tags = get_json(base + "/api/tags")
        print("[nova] Reusing the running Ollama server.", flush=True)
    except (URLError, TimeoutError, ConnectionError):
        host = local_ollama_host(base)
        executable = shutil.which("ollama")
        if not executable:
            raise RuntimeError("Ollama is not installed/on PATH. Install it, or configure Groq in backend/.env.")
        env = {**env, "OLLAMA_HOST": host}
        print("[nova] Starting Ollama...", flush=True)
        services.start("ollama", [executable, "serve"], root, env)
        tags = wait_for("Ollama", lambda: get_json(base + "/api/tags"), services, timeout)
    if model_installed(tags, config["model"]):
        return
    if not pull_model:
        raise RuntimeError(f"Model {config['model']} is not installed. Run again with --pull-model to download it once (may be several GB).")
    # Keep downloads explicit; this targets the configured server, not another
    # Ollama instance that happens to use the CLI default port.
    executable = shutil.which("ollama")
    if not executable:
        raise RuntimeError("The --pull-model option needs the Ollama CLI on PATH.")
    process = services.start("model-download", [executable, "pull", config["model"]], root,
                             {**env, "OLLAMA_HOST": base})
    while process.poll() is None:
        for name, child, _ in services.children:
            if name != "model-download" and child.poll() is not None:
                raise RuntimeError(f"{name} stopped during the model download.")
        time.sleep(0.5)
    # A completed one-shot download is not a long-running service.
    download = services.children.pop()
    if download[2]:
        download[2].close()
    if process.returncode or not model_installed(get_json(base + "/api/tags"), config["model"]):
        raise RuntimeError("Model download failed. Check the Ollama logs above.")


def parser():
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--no-browser", action="store_true", help="Do not open a browser automatically")
    result.add_argument("--pull-model", action="store_true", help="Download the configured Ollama model if missing (may be several GB)")
    result.add_argument("--reload", action="store_true", help="Reload the backend when Python source changes")
    result.add_argument("--backend-port", type=int, default=8000)
    result.add_argument("--frontend-port", type=int, default=5173)
    result.add_argument("--startup-timeout", type=float, default=120, help="Readiness timeout per service, seconds")
    return result


def run(args, services: Services, root: Path = ROOT):
    if (not 1 <= args.backend_port <= 65535 or not 1 <= args.frontend_port <= 65535
            or args.backend_port == args.frontend_port or args.startup_timeout <= 0):
        raise RuntimeError("Choose two different ports in 1..65535 and a positive startup timeout.")
    python = backend_python(root)
    node = shutil.which("node")
    vite = root / "frontend/node_modules/vite/bin/vite.js"
    if not node or not vite.is_file():
        raise RuntimeError("Install Node.js 22.12+ and run npm ci in frontend first.")
    version = subprocess.check_output([node, "-p", "process.versions.node"], text=True).strip()
    if tuple(map(int, version.split(".")[:2])) < (22, 12):
        raise RuntimeError("Node.js 22.12+ is required.")
    config = read_config(python, root)
    if config["environment"] != "development" or config["redis"]:
        raise RuntimeError("This launcher requires ENVIRONMENT=development and no REDIS_URL (in-process indexing). See docs/OPERATIONS.md for shared services.")
    if config["provider"] == "groq" and not config["groq_configured"]:
        raise RuntimeError("Configure GROQ_API_KEY in backend/.env, or use LLM_PROVIDER=ollama.")
    require_free_port(args.backend_port)
    require_free_port(args.frontend_port)
    api = f"http://127.0.0.1:{args.backend_port}"
    ui = f"http://127.0.0.1:{args.frontend_port}"
    env = {**os.environ, "PYTHONUNBUFFERED": "1", "PYTHONIOENCODING": "utf-8"}
    if config["provider"] == "ollama":
        ensure_ollama(config, services, env, args.startup_timeout, args.pull_model, root)
    else:
        print("[nova] Using Groq; no local model server is needed.", flush=True)
    api_env = {**env, "CORS_ORIGINS": ",".join(dict.fromkeys([*config["cors"], ui]))}
    print("[nova] Starting backend...", flush=True)
    command = [str(python), "-m", "uvicorn", "app:app", "--host", "127.0.0.1", "--port", str(args.backend_port)]
    if args.reload:
        command.append("--reload")
    services.start("api", command, root / "backend", api_env)
    wait_for("backend/provider readiness", lambda: get_json(api + "/health/ready?refresh=true").get("ready") is True,
             services, args.startup_timeout)
    print("[nova] Starting frontend...", flush=True)
    services.start("ui", [node, str(vite), "--host", "127.0.0.1", "--port", str(args.frontend_port), "--strictPort"],
                   root / "frontend", {**env, "VITE_API_BASE_URL": api})

    def frontend_ready():
        with urlopen(ui, timeout=3) as response:
            return response.status == 200

    wait_for("frontend", frontend_ready, services, args.startup_timeout)
    print(f"\n[nova] READY: {ui}\n[nova] API docs: {api}/docs\n[nova] Press Ctrl+C to stop services started by this launcher.\n", flush=True)
    if not args.no_browser:
        webbrowser.open(ui)
    while True:
        services.check()
        time.sleep(0.5)


def main(argv=None):
    args = parser().parse_args(argv)
    services = Services()

    def interrupted(_signal, _frame):
        raise KeyboardInterrupt

    for name in ("SIGTERM", "SIGBREAK"):
        if hasattr(signal, name):
            signal.signal(getattr(signal, name), interrupted)
    try:
        run(args, services)
    except KeyboardInterrupt:
        print("\n[nova] Stopping owned services...", flush=True)
        return 0
    except (RuntimeError, OSError, ValueError, subprocess.SubprocessError) as error:
        print(f"[nova] ERROR: {error}", flush=True)
        return 1
    finally:
        services.close()


if __name__ == "__main__":
    raise SystemExit(main())
