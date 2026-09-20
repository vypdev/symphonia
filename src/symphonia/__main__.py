"""Command-line entry point for the dependency-free runtime foundation."""

from __future__ import annotations

import argparse
import os

from symphonia.runtime import RuntimeConfig, create_server


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
    server = create_server(config.host, config.port, config.database_path, config.ingress_path)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        server.close_resources()


if __name__ == "__main__":
    main()
