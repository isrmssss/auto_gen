import sys

from openrd.eval.harness import run_suite

if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    suite = args[0] if args else "smoke"
    raise SystemExit(run_suite(suite))
