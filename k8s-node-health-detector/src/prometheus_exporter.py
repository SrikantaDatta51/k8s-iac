#!/usr/bin/env python3
"""Prometheus Exporter — exposes health check results as Prometheus metrics.
Runs an HTTP server on a configurable port (default 9101).
"""
import http.server
import threading
import logging
import time
from typing import List

logger = logging.getLogger("node-health-detector")

METRICS_PREFIX = "node_health"


class PrometheusExporter:
    """HTTP server that serves Prometheus metrics from health check results."""

    def __init__(self, port: int = 9101):
        self.port = port
        self._metrics_text = ""
        self._lock = threading.Lock()
        self._server = None

    def update_metrics(self, results: list, summary: dict):
        """Update the metrics text from latest check results."""
        lines = []

        # Overall node health
        lines.append(f"# HELP {METRICS_PREFIX}_node_healthy Node health status (1=healthy, 0=unhealthy)")
        lines.append(f"# TYPE {METRICS_PREFIX}_node_healthy gauge")
        healthy = 1 if summary.get("status") == "healthy" else 0
        node = summary.get("node", "unknown")
        lines.append(f'{METRICS_PREFIX}_node_healthy{{node="{node}"}} {healthy}')

        # Should cordon
        lines.append(f"# HELP {METRICS_PREFIX}_should_cordon Whether node should be cordoned (1=yes)")
        lines.append(f"# TYPE {METRICS_PREFIX}_should_cordon gauge")
        cordon = 1 if summary.get("should_cordon") else 0
        lines.append(f'{METRICS_PREFIX}_should_cordon{{node="{node}"}} {cordon}')

        # Check counts
        for counter in ["passed", "failed", "warned", "checks_run"]:
            lines.append(f"# HELP {METRICS_PREFIX}_{counter} Number of checks in {counter} state")
            lines.append(f"# TYPE {METRICS_PREFIX}_{counter} gauge")
            lines.append(f'{METRICS_PREFIX}_{counter}{{node="{node}"}} {summary.get(counter, 0)}')

        # Per-check status
        lines.append(f"# HELP {METRICS_PREFIX}_check_status Check status (0=pass, 1=warn, 2=fail, 3=unknown)")
        lines.append(f"# TYPE {METRICS_PREFIX}_check_status gauge")
        for m in results:
            labels = (f'node="{m["node"]}",check="{m["name"]}",'
                      f'component="{m["component"]}",severity="{m["severity"]}"')
            lines.append(f'{METRICS_PREFIX}_check_status{{{labels}}} {m["status"]}')

        # Per-check cordon signal
        lines.append(f"# HELP {METRICS_PREFIX}_check_cordon Check requests cordon (1=yes)")
        lines.append(f"# TYPE {METRICS_PREFIX}_check_cordon gauge")
        for m in results:
            labels = (f'node="{m["node"]}",check="{m["name"]}",'
                      f'component="{m["component"]}"')
            lines.append(f'{METRICS_PREFIX}_check_cordon{{{labels}}} {m["should_cordon"]}')

        # Per-component worst status
        lines.append(f"# HELP {METRICS_PREFIX}_component_status Worst check status per component")
        lines.append(f"# TYPE {METRICS_PREFIX}_component_status gauge")
        components = {}
        for m in results:
            comp = m["component"]
            components[comp] = max(components.get(comp, 0), m["status"])
        for comp, status in components.items():
            lines.append(f'{METRICS_PREFIX}_component_status{{node="{node}",component="{comp}"}} {status}')

        # Last check timestamp
        lines.append(f"# HELP {METRICS_PREFIX}_last_check_timestamp_seconds Last check run time")
        lines.append(f"# TYPE {METRICS_PREFIX}_last_check_timestamp_seconds gauge")
        lines.append(f'{METRICS_PREFIX}_last_check_timestamp_seconds{{node="{node}"}} {time.time():.0f}')

        with self._lock:
            self._metrics_text = "\n".join(lines) + "\n"

    def _handler_factory(self):
        exporter = self

        class MetricsHandler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                if self.path in ("/metrics", "/"):
                    with exporter._lock:
                        body = exporter._metrics_text.encode()
                    self.send_response(200)
                    self.send_header("Content-Type", "text/plain; version=0.0.4")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                elif self.path == "/healthz":
                    self.send_response(200)
                    self.end_headers()
                    self.wfile.write(b"ok")
                else:
                    self.send_response(404)
                    self.end_headers()

            def log_message(self, format, *args):
                pass  # Suppress access log noise

        return MetricsHandler

    def start(self):
        """Start the metrics HTTP server in a background thread."""
        handler = self._handler_factory()
        self._server = http.server.HTTPServer(("0.0.0.0", self.port), handler)
        thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        thread.start()
        logger.info(f"Prometheus exporter started on :{self.port}/metrics")

    def stop(self):
        if self._server:
            self._server.shutdown()
