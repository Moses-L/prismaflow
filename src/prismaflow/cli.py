"""Command-line interface: ``prismaflow template`` and ``prismaflow draw``."""

from __future__ import annotations

import argparse
import sys

from . import __version__
from .data import PrismaData, example_data
from .render import ALL_FORMATS, render


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="prismaflow", description="PRISMA 2020 flow diagrams from a CSV.")
    p.add_argument("--version", action="version", version=f"prismaflow {__version__}")
    sub = p.add_subparsers(dest="cmd", required=True)

    t = sub.add_parser("template", help="write a blank CSV template")
    t.add_argument("-o", "--output", default="prisma_template.csv")

    d = sub.add_parser("draw", help="draw a diagram from a filled-in CSV")
    d.add_argument("csv", nargs="?", help="input CSV (omit with --example)")
    d.add_argument("-o", "--output", default="prisma_flow", help="output path stem (default: prisma_flow)")
    d.add_argument("-f", "--format", nargs="+", default=["png"], choices=ALL_FORMATS, help="one or more formats")
    d.add_argument("--dpi", type=int, default=300, help="PNG resolution (default 300)")
    d.add_argument("--title", default=None)
    d.add_argument("--example", action="store_true", help="draw the built-in worked example")

    args = p.parse_args(argv)

    if args.cmd == "template":
        PrismaData.write_template(args.output)
        print(f"Wrote {args.output}")
        return 0

    if not args.example and not args.csv:
        d.error("provide a CSV file or use --example")
    try:
        data = example_data() if args.example else PrismaData.from_csv(args.csv)
        for w in data.validate():
            print(f"warning: {w}", file=sys.stderr)
        for path in render(data, args.output, args.format, dpi=args.dpi, title=args.title):
            print(f"Wrote {path}")
    except FileNotFoundError as exc:
        print(f"error: file not found: {exc.filename}", file=sys.stderr)
        return 1
    except (ValueError, RuntimeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
