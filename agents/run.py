"""CLI entry point for the automated dual-AI quant loop.

    python -m agents.run --strategy "cross-sectional momentum" --max-iters 3

Writes the full transcript + final design to agents/outputs/.
"""

from __future__ import annotations
import argparse
import json
import pathlib
import datetime as dt

try:
    from dotenv import load_dotenv
    load_dotenv(pathlib.Path(__file__).parent / ".env")
except ImportError:
    pass


def main() -> None:
    ap = argparse.ArgumentParser(description="Dual-AI quant research/build loop")
    ap.add_argument("--strategy", required=True, help="strategy to research & design")
    ap.add_argument("--max-iters", type=int, default=3,
                    help="max critic/refiner rounds")
    args = ap.parse_args()

    # imported here so --help works without langgraph/keys installed
    from .graph import build_graph

    app = build_graph()
    final = app.invoke(
        {"strategy": args.strategy, "max_iterations": args.max_iters},
        {"recursion_limit": 50},
    )

    outdir = pathlib.Path(__file__).parent / "outputs"
    outdir.mkdir(exist_ok=True)
    stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    slug = args.strategy.lower().replace(" ", "_")[:40]

    (outdir / f"{slug}_{stamp}_design.md").write_text(final.get("design", ""))
    (outdir / f"{slug}_{stamp}_transcript.json").write_text(
        json.dumps(final.get("transcript", []), indent=2))

    print(f"Rounds run: {final.get('iteration', 0)}  |  approved: "
          f"{final.get('approved', False)}")
    print(f"Outputs written to {outdir}/{slug}_{stamp}_*")


if __name__ == "__main__":
    main()
