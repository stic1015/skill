from __future__ import annotations

import argparse

from app.server import create_server


def main() -> None:
    parser = argparse.ArgumentParser(description="SkillMD Generator MVP server")
    parser.add_argument("--host", default="127.0.0.1", help="Host to bind")
    parser.add_argument("--port", type=int, default=8787, help="Port to bind")
    args = parser.parse_args()

    server = create_server(host=args.host, port=args.port)
    print(f"SkillMD server listening at http://{args.host}:{args.port}")
    server.serve_forever()


if __name__ == "__main__":
    main()

