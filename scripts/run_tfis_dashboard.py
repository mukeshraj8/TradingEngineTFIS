from __future__ import annotations

import argparse
import contextlib
import http.server
import json
import socketserver
import sys
from pathlib import Path
from urllib.parse import urlsplit


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from tfis.dashboard.api import DashboardApiRouter
from tfis.dashboard.events import build_sse_event_stream
from tfis.dashboard.professional import build_professional_dashboard
from tfis.runtime.multi_strategy import MultiStrategyRuntimeCoordinator, load_enabled_strategy_registry


class DashboardV1RequestHandler(http.server.SimpleHTTPRequestHandler):
    dashboard_root: Path
    projection: dict[str, object]
    router: DashboardApiRouter

    def do_GET(self) -> None:
        request = urlsplit(self.path)
        projection = self._load_projection()
        if request.path.startswith("/api/"):
            status, payload = DashboardApiRouter(projection).resolve(request.path)
            self._send_json(payload, status=status)
            return
        if request.path == "/events":
            body = build_sse_event_stream(projection).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        super().do_GET()

    def translate_path(self, path: str) -> str:
        request_path = urlsplit(path).path
        if request_path in ("", "/", "/index.html"):
            return str(self.dashboard_root / "index.html")
        relative = request_path.lstrip("/")
        return str(self.dashboard_root / relative)

    def _send_json(self, payload: dict[str, object], *, status: int = 200) -> None:
        body = json.dumps(payload, indent=2, sort_keys=True).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _load_projection(self) -> dict[str, object]:
        snapshot_path = self.dashboard_root / "api" / "snapshot.json"
        try:
            return json.loads(snapshot_path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            return dict(self.projection)


class ReusableTcpServer(socketserver.TCPServer):
    allow_reuse_address = True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build the professional TFIS operations dashboard.")
    parser.add_argument("--registry", default="config/internal_paper_strategy_instances.yaml")
    parser.add_argument("--projection", default="reports/dashboard_v1/s21_s22_s23_dashboard_projection.json")
    parser.add_argument("--output-root", default="tmp/tfis_dashboard_v1")
    parser.add_argument("--rebuild-projection", action="store_true")
    parser.add_argument("--serve", action="store_true", help="Serve the dashboard plus read-only APIs locally.")
    parser.add_argument("--port", type=int, default=8766)
    args = parser.parse_args(argv)
    projection_path = REPO_ROOT / args.projection
    if args.rebuild_projection or not projection_path.exists():
        registry = load_enabled_strategy_registry(REPO_ROOT / args.registry)
        projection = MultiStrategyRuntimeCoordinator(registry).run_deterministic_session()["dashboard_projection"]
    else:
        projection = json.loads(projection_path.read_text(encoding="utf-8"))
    result = build_professional_dashboard(projection, output_root=REPO_ROOT / args.output_root)
    print("TFIS professional dashboard build succeeded.")
    print(f"Index page: {result.index_html}")
    print(f"Snapshot: {result.snapshot_json}")
    if args.serve:
        handler = DashboardV1RequestHandler
        handler.dashboard_root = result.output_root.resolve()
        handler.projection = dict(projection)
        handler.router = DashboardApiRouter(projection)
        httpd = ReusableTcpServer(("127.0.0.1", args.port), handler)
        try:
            print(f"URL: http://127.0.0.1:{args.port}/index.html")
            print(f"API health: http://127.0.0.1:{args.port}/api/health")
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nStopping TFIS professional dashboard server.")
        finally:
            with contextlib.suppress(BaseException):
                httpd.shutdown()
            with contextlib.suppress(BaseException):
                httpd.server_close()
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
