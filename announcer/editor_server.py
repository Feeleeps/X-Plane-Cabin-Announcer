"""
Lightweight local HTTP server for the HTML Visual Aircraft Config Editor.
Uses Python's standard library http.server (zero third-party dependencies).
Serves the web editor UI and provides REST endpoints to load/save aircraft configs.
"""

import os
import json
import urllib.parse
import threading
import webbrowser
import logging
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler

logger = logging.getLogger("CabinAnnouncer.WebEditor")

_server_instance = None
_server_thread = None

class ConfigEditorHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, base_dir=None, config_manager=None, **kwargs):
        self.base_dir = base_dir or os.getcwd()
        self.config_manager = config_manager
        self.configs_dir = os.path.join(self.base_dir, "aircraft_configs")
        self.web_dir = os.path.join(self.base_dir, "web_editor")
        super().__init__(*args, directory=self.web_dir, **kwargs)

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        query = urllib.parse.parse_qs(parsed.query)

        # 1. API: List available aircraft configs
        if path == "/api/configs":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            files = []
            if os.path.exists(self.configs_dir):
                files = [f for f in os.listdir(self.configs_dir) if f.lower().endswith((".json", ".yaml", ".yml")) and not f.startswith("_")]
            self.wfile.write(json.dumps(sorted(files)).encode("utf-8"))
            return

        # 2. API: Load a specific config file
        if path == "/api/config":
            filename = query.get("file", [""])[0]
            # Prevent directory traversal
            clean_filename = os.path.basename(filename)
            full_path = os.path.join(self.configs_dir, clean_filename)

            if os.path.exists(full_path):
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                try:
                    with open(full_path, "r", encoding="utf-8") as fp:
                        content = fp.read()
                    self.wfile.write(content.encode("utf-8"))
                except Exception as e:
                    self.wfile.write(json.dumps({"error": str(e)}).encode("utf-8"))
            else:
                self.send_error(404, "Config file not found")
            return

        # Default: Serve static files from web_editor/
        if path == "/" or path == "":
            self.path = "/index.html"
        super().do_GET()

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/api/save":
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length).decode("utf-8")

            try:
                payload = json.loads(body)
                raw_filename = payload.get("filename", "Aircraft_Config.json")
                config_data = payload.get("config", {})

                # Prevent directory traversal
                clean_filename = os.path.basename(raw_filename)
                if not clean_filename.lower().endswith(".json"):
                    clean_filename += ".json"

                os.makedirs(self.configs_dir, exist_ok=True)
                full_path = os.path.join(self.configs_dir, clean_filename)

                # Clean internal fields
                config_data.pop("_filename", None)
                config_data.pop("_filepath", None)

                with open(full_path, "w", encoding="utf-8") as fp:
                    json.dump(config_data, fp, indent=2)

                logger.info(f"Saved aircraft config via Web Editor: {clean_filename}")

                # Refresh ConfigManager if available
                if self.config_manager:
                    self.config_manager.rescan()

                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"success": True, "file": clean_filename}).encode("utf-8"))
            except Exception as e:
                logger.error(f"Failed to save config via Web Editor: {e}")
                self.send_response(500)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"error": str(e)}).encode("utf-8"))
            return

        self.send_error(404)

    def log_message(self, format, *args):
        # Mute noisy console access logs
        logger.debug("%s - - [%s] %s" % (self.client_address[0], self.log_date_time_string(), format % args))


def start_editor_server(base_dir, port=8765, open_browser=True, config_manager=None):
    """
    Starts the local HTTP server on a daemon thread and opens the web editor in default browser.
    """
    global _server_instance, _server_thread

    url = f"http://127.0.0.1:{port}"

    if _server_instance is not None:
        if open_browser:
            webbrowser.open(url)
        return url

    def _handler_factory(*args, **kwargs):
        return ConfigEditorHandler(*args, base_dir=base_dir, config_manager=config_manager, **kwargs)

    try:
        _server_instance = ThreadingHTTPServer(("127.0.0.1", port), _handler_factory)
        _server_thread = threading.Thread(target=_server_instance.serve_forever, daemon=True)
        _server_thread.start()
        logger.info(f"HTML Config Editor server listening at: {url}")
    except OSError:
        # Port might already be in use or bound
        logger.info(f"Server already active or bound on port {port}.")

    if open_browser:
        webbrowser.open(url)

    return url

def stop_editor_server():
    global _server_instance
    if _server_instance:
        try:
            _server_instance.shutdown()
        except Exception:
            pass
        _server_instance = None
