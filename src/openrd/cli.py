from __future__ import annotations

import argparse
import os

import uvicorn

from openrd.settings import settings


def main() -> None:
    parser = argparse.ArgumentParser(prog="openrd", description="OpenRD local R&D agent")
    sub = parser.add_subparsers(dest="cmd")
    serve = sub.add_parser("serve", help="run API + UI")
    serve.add_argument("--host", default=settings.host)
    serve.add_argument("--port", type=int, default=settings.port)
    eval_p = sub.add_parser("eval", help="run the 1-2h eval harness")
    eval_p.add_argument("--suite", default="smoke")
    eval_p.add_argument("--provider-id", default="")
    args = parser.parse_args()
    if args.cmd == "eval":
        from openrd.eval.harness import run_suite

        raise SystemExit(run_suite(args.suite, args.provider_id or None))
    host = getattr(args, "host", settings.host)
    port = getattr(args, "port", settings.port)
    os.environ.setdefault("OPENRD_HOST", host)
    uvicorn.run("openrd.server.app:app", host=host, port=port, reload=False)


if __name__ == "__main__":
    main()
