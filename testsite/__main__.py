"""手動啟動測試網站：uv run python -m testsite --port 8765"""

import argparse
import sys

from testsite.server import create_server


def main() -> int:
    parser = argparse.ArgumentParser(description="本機測試網站（只綁定 127.0.0.1）")
    parser.add_argument("--port", type=int, default=8765)
    port = parser.parse_args().port
    server = create_server(port)
    sys.stderr.write(f"測試網站：http://127.0.0.1:{server.server_port}/（Ctrl+C 結束）\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
