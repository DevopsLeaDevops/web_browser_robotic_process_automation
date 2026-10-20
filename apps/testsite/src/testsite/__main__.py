"""手動啟動測試網站：uv run python -m testsite --port 8765 [--host 0.0.0.0]"""

import argparse
import sys

from testsite.server import DEFAULT_PORT, LOOPBACK, create_server


def main() -> int:
    parser = argparse.ArgumentParser(description="本機測試網站（預設只綁定 127.0.0.1）")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument(
        "--host", default=LOOPBACK, help="監聽的位址；0.0.0.0 讓其他電腦也連得到（沒有任何保護）"
    )
    args = parser.parse_args()
    server = create_server(args.port, args.host)
    sys.stderr.write(f"測試網站：http://{args.host}:{server.server_port}/（Ctrl+C 結束）\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
