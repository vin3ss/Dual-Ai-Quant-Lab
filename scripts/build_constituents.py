#!/usr/bin/env python3
"""Build best-effort point-in-time NIFTY constituent snapshots (issue #21).

Output schema (consumed by nse_alpha_forge.portfolio.universe.constituent_mask):

    date,symbol

Approach: start from the current NSE/NiftyIndices constituent list and walk BACKWARD
through reconstitution events (additions/removals with effective dates):
    previous_before = current_after - additions + removals
emitting a membership snapshot just before each effective date.

FREE-SOURCE REALITY (honest): this is best-effort PiT, NOT institutional-grade.
- Current constituents: archives.nseindia.com/content/indices/ind_nifty500list.csv
- Historical changes: NSE/NiftyIndices reconstitution circulars (semi-annual, Jan/Jul
  cut-offs) — public but NOT a clean structured DB. You curate data_in/index_events.csv
  by hand from those circulars. Without events, output is just the current (survivorship-
  biased) baseline. A complete audited history with renames/mergers/delistings is paid data.
"""

from __future__ import annotations

import argparse
import io
import re
import sys
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

try:
    import requests
except ImportError:
    requests = None


CURRENT_LIST_URLS = {
    "NIFTY500": "https://archives.nseindia.com/content/indices/ind_nifty500list.csv",
    "NIFTY200": "https://archives.nseindia.com/content/indices/ind_nifty200list.csv",
}
HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"),
    "Accept": "text/csv,*/*",
    "Referer": "https://www.niftyindices.com/",
}
SYMBOL_RE = re.compile(r"^[A-Z0-9&\-]+$")


@dataclass(frozen=True)
class IndexEvent:
    effective_date: pd.Timestamp
    add_symbol: str | None
    remove_symbol: str | None
    source: str = ""


def normalize_symbol(symbol) -> str | None:
    if symbol is None or pd.isna(symbol):
        return None
    s = re.sub(r"\s+", "", str(symbol).upper().strip().replace(".NS", ""))
    return None if (not s or s in {"NAN", "-", "NA", "N.A."}) else s


def load_aliases(path: Path | None) -> dict[str, str]:
    if path is None or not path.exists():
        return {}
    df = pd.read_csv(path)
    df.columns = [c.lower().strip() for c in df.columns]
    if not {"old_symbol", "new_symbol"}.issubset(df.columns):
        raise ValueError("aliases CSV must contain old_symbol,new_symbol")
    out = {}
    for _, r in df.iterrows():
        o, n = normalize_symbol(r["old_symbol"]), normalize_symbol(r["new_symbol"])
        if o and n:
            out[o] = n
    return out


def alias(sym, aliases):
    return aliases.get(sym, sym) if sym else None


def load_current(index: str, current_csv: Path | None) -> set[str]:
    if current_csv is not None:
        raw = current_csv.read_bytes()
    else:
        if requests is None:
            raise SystemExit("requests not installed and no --current-csv given.")
        r = requests.get(CURRENT_LIST_URLS[index.upper()], headers=HEADERS, timeout=30)
        r.raise_for_status()
        raw = r.content
    df = pd.read_csv(io.BytesIO(raw))
    df.columns = [c.lower().strip() for c in df.columns]
    col = next((c for c in ("symbol", "ticker", "nse symbol") if c in df.columns), None)
    if col is None:
        raise ValueError(f"No symbol column in current list. Columns={list(df.columns)}")
    return {s for s in (normalize_symbol(x) for x in df[col]) if s}


def load_events(path: Path, aliases: dict[str, str]) -> list[IndexEvent]:
    if not path.exists():
        return []
    df = pd.read_csv(path)
    df.columns = [c.lower().strip() for c in df.columns]
    if not {"effective_date", "add_symbol", "remove_symbol"}.issubset(df.columns):
        raise ValueError("events CSV must have effective_date,add_symbol,remove_symbol")
    events = []
    for _, r in df.iterrows():
        add = alias(normalize_symbol(r["add_symbol"]), aliases)
        rem = alias(normalize_symbol(r["remove_symbol"]), aliases)
        if not add and not rem:
            continue
        events.append(IndexEvent(pd.Timestamp(r["effective_date"]).normalize(), add, rem,
                                 str(r.get("source", path.name))))
    return sorted(events, key=lambda e: e.effective_date, reverse=True)


def reconstruct_backward(current: set[str], events: list[IndexEvent],
                         current_date: pd.Timestamp, min_date: pd.Timestamp | None) -> pd.DataFrame:
    members = set(current)
    rows = []

    def emit(dt, source):
        for sym in sorted(members):
            rows.append({"date": dt.date().isoformat(), "symbol": sym, "source": source})

    emit(current_date, "current_baseline")

    grouped: dict[pd.Timestamp, list[IndexEvent]] = {}
    for ev in events:
        if min_date is not None and ev.effective_date < min_date:
            continue
        if ev.effective_date > current_date:
            continue
        grouped.setdefault(ev.effective_date, []).append(ev)

    for eff in sorted(grouped, reverse=True):
        for ev in grouped[eff]:
            if ev.add_symbol:
                members.discard(ev.add_symbol)   # undo an addition
            if ev.remove_symbol:
                members.add(ev.remove_symbol)     # undo a removal
        src = ";".join(sorted({e.source for e in grouped[eff] if e.source})) or "events"
        emit(eff - pd.Timedelta(days=1), src)

    out = pd.DataFrame(rows).drop_duplicates(["date", "symbol"]).sort_values(["date", "symbol"])
    return out[["date", "symbol", "source"]]


def main(argv=None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--index", default="NIFTY500", choices=["NIFTY500", "NIFTY200"])
    p.add_argument("--current-csv", type=Path, default=None)
    p.add_argument("--events-csv", type=Path, default=Path("data_in/index_events.csv"))
    p.add_argument("--aliases-csv", type=Path, default=Path("data_in/symbol_aliases.csv"))
    p.add_argument("--out", type=Path, default=Path("data_in/constituents.csv"))
    p.add_argument("--current-date", default=None)
    p.add_argument("--min-date", default=None)
    p.add_argument("--include-source", action="store_true")
    args = p.parse_args(argv)

    current_date = (pd.Timestamp(args.current_date) if args.current_date
                    else pd.Timestamp.today()).normalize()
    min_date = pd.Timestamp(args.min_date).normalize() if args.min_date else None

    aliases = load_aliases(args.aliases_csv)
    current = {s for s in (alias(x, aliases) for x in load_current(args.index, args.current_csv)) if s}
    events = load_events(args.events_csv, aliases)

    if not events:
        print("WARNING: no events found -> output is only the current (survivorship-biased) "
              "baseline. Curate data_in/index_events.csv from reconstitution circulars.",
              file=sys.stderr)

    snaps = reconstruct_backward(current, events, current_date, min_date)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    cols = ["date", "symbol", "source"] if args.include_source else ["date", "symbol"]
    snaps[cols].to_csv(args.out, index=False)

    print(f"Wrote {args.out} rows={len(snaps):,} | current members={len(current):,} | events={len(events):,}")
    print("NOTE: best-effort PiT, not institutional-grade. QA before trusting; "
          "renames/mergers need data_in/symbol_aliases.csv.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
