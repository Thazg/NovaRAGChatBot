"""Launcher failure/ownership contracts; no app, model or network installation."""
from pathlib import Path
import os
import socket
import subprocess
import sys
from tempfile import TemporaryDirectory
import time
import unittest
from unittest.mock import Mock, patch

from _dev_processes import Services
import dev


class LauncherContracts(unittest.TestCase):
    def test_model_matching_respects_explicit_tags_and_registry_ports(self):
        tags = {"models": [{"name": "qwen3:4b-instruct"}, {"name": "registry:5000/model:latest"}]}
        self.assertTrue(dev.model_installed(tags, "qwen3:4b-instruct"))
        self.assertTrue(dev.model_installed(tags, "registry:5000/model"))
        self.assertFalse(dev.model_installed(tags, "qwen3:8b"))

    def test_only_local_plain_http_endpoints_can_be_auto_started(self):
        self.assertEqual(dev.local_ollama_host("http://127.0.0.1:12000"), "127.0.0.1:12000")
        self.assertEqual(dev.local_ollama_host("http://[::1]:11434"), "[::1]:11434")
        for url in ("https://localhost:11434", "http://remote.example:11434", "http://user:password@localhost", "http://localhost/proxy"):
            with self.subTest(url=url), self.assertRaises(RuntimeError):
                dev.local_ollama_host(url)

    def test_existing_ollama_is_reused_without_starting_or_stopping_it(self):
        services = Mock()
        config = {"ollama_url": "http://localhost:11434", "model": "qwen3:4b-instruct"}
        with patch.object(dev, "get_json", return_value={"models": [{"name": config["model"]}]}):
            dev.ensure_ollama(config, services, {}, 1, False, Path("."))
        services.start.assert_not_called()
        services.close.assert_not_called()

    def test_missing_model_does_not_download_without_opt_in(self):
        services = Mock()
        with patch.object(dev, "get_json", return_value={"models": []}), patch.object(dev.shutil, "which") as which:
            with self.assertRaisesRegex(RuntimeError, "--pull-model"):
                dev.ensure_ollama({"ollama_url": "http://localhost:11434", "model": "missing:4b"}, services, {}, 1, False, Path("."))
        services.start.assert_not_called()
        which.assert_not_called()

    def test_busy_port_fails_without_disrupting_the_listener(self):
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            listener.listen()
            port = listener.getsockname()[1]
            with self.assertRaisesRegex(RuntimeError, "already in use"):
                dev.require_free_port(port)
            with socket.create_connection(("127.0.0.1", port), timeout=1):
                pass

    def test_readiness_timeout_and_child_failure_cannot_report_success(self):
        services = Mock()
        with self.assertRaisesRegex(RuntimeError, "Timed out"):
            dev.wait_for("API", lambda: False, services, 0.01)
        services.check.side_effect = RuntimeError("API stopped")
        with self.assertRaisesRegex(RuntimeError, "API stopped"):
            dev.wait_for("API", lambda: True, services, 1)

    def test_custom_ports_override_stale_frontend_env_and_allow_its_origin(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "frontend/node_modules/vite/bin").mkdir(parents=True)
            (root / "frontend/node_modules/vite/bin/vite.js").touch()
            services = Mock()
            services.check.side_effect = KeyboardInterrupt
            config = {"provider": "groq", "groq_configured": True, "environment": "development", "redis": False, "cors": []}
            args = dev.parser().parse_args(["--no-browser", "--backend-port", "18000", "--frontend-port", "15173"])
            with patch.object(dev, "backend_python", return_value=Path(sys.executable)), \
                 patch.object(dev.shutil, "which", return_value="node"), \
                 patch.object(dev.subprocess, "check_output", return_value="24.0.0"), \
                 patch.object(dev, "read_config", return_value=config), \
                 patch.object(dev, "require_free_port"), patch.object(dev, "wait_for"), \
                 patch.object(dev, "ensure_ollama") as ollama, \
                 patch.dict(os.environ, {"VITE_API_BASE_URL": "https://stale.example"}):
                with self.assertRaises(KeyboardInterrupt):
                    dev.run(args, services, root)
            api, ui = services.start.call_args_list
            self.assertIn("http://127.0.0.1:15173", api.args[3]["CORS_ORIGINS"])
            self.assertEqual(ui.args[3]["VITE_API_BASE_URL"], "http://127.0.0.1:18000")
            self.assertIn("--strictPort", ui.args[1])
            ollama.assert_not_called()


class ProcessTreeContracts(unittest.TestCase):
    def test_cleanup_kills_owned_grandchild_after_parent_exit_but_leaves_other_process_alive(self):
        # The grandchild listens on an ephemeral port, letting us verify real
        # cleanup without relying on reused PIDs or an installed Ollama/Node.
        with TemporaryDirectory(prefix="nova dev ") as directory:
            root = Path(directory)
            marker = root / "grandchild.txt"
            child = (
                "import socket,time,pathlib; s=socket.socket(); s.bind(('127.0.0.1',0)); s.listen(); "
                f"pathlib.Path({str(marker)!r}).write_text(str(s.getsockname()[1])); time.sleep(60)"
            )
            parent = f"import subprocess,sys; subprocess.Popen([sys.executable,'-c',{child!r}])"
            external = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"],
                                        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            services = Services()
            try:
                owned = services.start("test", [sys.executable, "-c", parent], root, os.environ.copy())
                deadline = time.monotonic() + 10
                while not marker.exists() and time.monotonic() < deadline:
                    time.sleep(0.05)
                self.assertTrue(marker.exists(), "Grandchild never started")
                port = int(marker.read_text())
                owned.wait(timeout=5)
                with self.assertRaisesRegex(RuntimeError, "stopped"):
                    services.check()
                services.close()
                deadline = time.monotonic() + 5
                while time.monotonic() < deadline:
                    with socket.socket() as probe:
                        if probe.connect_ex(("127.0.0.1", port)) != 0:
                            break
                    time.sleep(0.05)
                else:
                    self.fail("Owned grandchild survived cleanup")
                self.assertIsNone(external.poll(), "Unrelated process was stopped")
            finally:
                services.close()
                external.terminate()
                external.wait(timeout=5)


if __name__ == "__main__":
    unittest.main()
