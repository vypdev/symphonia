"""Command-line entry point for the dependency-free runtime foundation."""

from __future__ import annotations

import argparse
import os
import signal
from types import FrameType

from symphonia.runtime import RuntimeConfig, create_server


def _handle_sigterm(_signum: int, _frame: FrameType | None) -> None:
    raise KeyboardInterrupt


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Symphonia runtime foundation")
    parser.add_argument("--host", default=os.getenv("SYMPHONIA_HOST", "127.0.0.1"))
    parser.add_argument("--port", default=os.getenv("SYMPHONIA_PORT", "8099"))
    parser.add_argument(
        "--database",
        default=os.getenv("SYMPHONIA_DATABASE", "./symphonia.sqlite3"),
        help="SQLite path; Home Assistant App deployments should use /data/symphonia.sqlite3",
    )
    parser.add_argument(
        "--ingress-path",
        default=os.getenv("SYMPHONIA_INGRESS_PATH", "/"),
        help="Ingress base path, for example /local_symphonia",
    )
    args = parser.parse_args()
    try:
        config = RuntimeConfig(
            host=args.host,
            port=args.port,
            database_path=args.database,
            ingress_path=args.ingress_path,
        )
    except ValueError as error:
        parser.error(str(error))
    previous_sigterm_handler = signal.signal(signal.SIGTERM, _handle_sigterm)
    server = None
    try:
        server = create_server(config.host, config.port, config.database_path, config.ingress_path)
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        try:
            if server is not None:
                try:
                    server.server_close()
                finally:
                    server.close_resources()
        finally:
            signal.signal(signal.SIGTERM, previous_sigterm_handler)


if __name__ == "__main__":
    main()
