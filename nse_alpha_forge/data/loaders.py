"""Real-data loaders for NSE Alpha Forge.

No network calls happen at import time.

Primary entry point:
    load_universe(start, end, universe="NIFTY500")

Data-quality warnings are intentionally loud because real NSE backtests are easy
to bias through survivorship, stale fundamentals, future corporate actions, and
reconstructed adjusted prices.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import hashlib
import logging
import warnings

import pandas as pd

from .market_data import MarketData

log = logging.getLogger(__name__)


class DataQualityWarning(RuntimeWarning):
    """Warning for data issues that can bias backtests."""


@dataclass(frozen=True)
class LoaderConfig:
    cache_dir: Path = Path(".cache/nse_alpha_forge")
    source: str = "csv"  # csv | nsepython | nsefin
    bhavcopy_dir: Path | None = None
    sectors_path: Path | None = None
    fundamentals_path: Path | None = None
    corporate_actions_path: Path | None = None
    macro_path: Path | None = None
    option_chain_path: Path | None = None
    fii_deriv_path: Path | None = None
    use_cache: bool = True
    refresh: bool = False
    resample: str | None = "ME"  # keep current engine compatible with monthly bars


def load_universe(
    start: str | pd.Timestamp,
    end: str | pd.Timestamp,
    universe: str = "NIFTY500",
    config: LoaderConfig | None = None,
) -> MarketData:
    """Load a MarketData snapshot for the requested universe.

    Notes
    -----
    - Returned prices are adjusted *as of the loader end date*.
    - If the universe source does not include historical constituents/delisted
      names, this is survivorship-biased and a warning is emitted.
    - Fundamentals must be indexed by availability/filing date, not fiscal
      period end. This loader refuses period-end-only fundamentals.
    """
    cfg = config or LoaderConfig()
    start_ts = pd.Timestamp(start)
    end_ts = pd.Timestamp(end)

    if start_ts > end_ts:
        raise ValueError("start must be <= end")

    cache_key = _cache_key(start_ts, end_ts, universe, cfg)
    cache_path = cfg.cache_dir / f"{cache_key}.parquet"

    if cfg.use_cache and cache_path.exists() and not cfg.refresh:
        return _read_marketdata_cache(cache_path)

    warnings.warn(
        "Universe membership is assumed current unless you provide a point-in-time "
        "constituent file. This can introduce survivorship bias, especially for "
        "NIFTY500-style backtests.",
        DataQualityWarning,
        stacklevel=2,
    )

    if cfg.source == "csv":
        raw_prices = _load_bhavcopy_csv(cfg.bhavcopy_dir, start_ts, end_ts)
    elif cfg.source == "nsepython":
        raw_prices = _load_bhavcopy_nsepython(start_ts, end_ts, universe)
    elif cfg.source == "nsefin":
        raw_prices = _load_bhavcopy_nsefin(start_ts, end_ts, universe)
    else:
        raise ValueError(f"Unsupported source: {cfg.source}")

    prices = _build_adjusted_close(
        raw_prices=raw_prices,
        corporate_actions_path=cfg.corporate_actions_path,
        as_of=end_ts,
    )

    sectors = _load_sectors(cfg.sectors_path, prices.columns)

    fundamentals = _load_fundamentals(
        cfg.fundamentals_path,
        start=start_ts,
        end=end_ts,
        tickers=list(prices.columns),
    )

    macro = _load_optional_frame(cfg.macro_path, start_ts, end_ts)
    option_chain = _load_optional_frame(cfg.option_chain_path, start_ts, end_ts)
    fii_deriv = _load_optional_frame(cfg.fii_deriv_path, start_ts, end_ts)

    if cfg.resample:
        prices = prices.resample(cfg.resample).last()
        # Drop the resample-stamped index freq: it is fragile metadata that does
        # not survive serialization, so a fresh load and a cached load would
        # otherwise differ on it. reindex below propagates the freq-less index.
        prices.index.freq = None
        fundamentals = {
            k: v.resample(cfg.resample).last().reindex(prices.index).ffill()
            for k, v in fundamentals.items()
        }
        if macro is not None:
            macro = macro.resample(cfg.resample).last()
            macro.index.freq = None
        if option_chain is not None:
            option_chain = option_chain.resample(cfg.resample).last()
            option_chain.index.freq = None
        if fii_deriv is not None:
            fii_deriv = fii_deriv.resample(cfg.resample).last()
            fii_deriv.index.freq = None

    data = MarketData(
        prices=prices,
        sectors=sectors,
        fundamentals=fundamentals,
        option_chain=option_chain,
        fii_deriv=fii_deriv,
        macro=macro,
    )

    if cfg.use_cache:
        cfg.cache_dir.mkdir(parents=True, exist_ok=True)
        _write_marketdata_cache(cache_path, data)

    return data


def _load_bhavcopy_csv(
    bhavcopy_dir: Path | None,
    start: pd.Timestamp,
    end: pd.Timestamp,
) -> pd.DataFrame:
    if bhavcopy_dir is None:
        raise ValueError("bhavcopy_dir is required when source='csv'")

    files = sorted(Path(bhavcopy_dir).glob("*.csv"))
    if not files:
        raise FileNotFoundError(f"No CSV files found in {bhavcopy_dir}")

    frames = []
    for file in files:
        df = pd.read_csv(file)
        df.columns = [c.lower().strip() for c in df.columns]

        rename = {
            "timestamp": "date",
            "trad_dt": "date",
            "symbol": "symbol",
            "ticker": "symbol",
            "close": "close",
            "close_price": "close",
            "adj_close": "adj_close",
            "adjusted_close": "adj_close",
        }
        df = df.rename(columns={c: rename.get(c, c) for c in df.columns})

        required = {"date", "symbol"}
        if not required.issubset(df.columns):
            raise ValueError(f"{file} must contain date and symbol columns")

        if "adj_close" not in df.columns and "close" not in df.columns:
            raise ValueError(f"{file} must contain close or adj_close")

        df["date"] = pd.to_datetime(df["date"])
        df["symbol"] = df["symbol"].astype(str).str.upper().str.strip()
        frames.append(df)

    out = pd.concat(frames, ignore_index=True)
    out = out[(out["date"] >= start) & (out["date"] <= end)]
    return out.sort_values(["date", "symbol"])


def _build_adjusted_close(
    raw_prices: pd.DataFrame,
    corporate_actions_path: Path | None,
    as_of: pd.Timestamp,
) -> pd.DataFrame:
    df = raw_prices.copy()

    if "adj_close" in df.columns:
        price_col = "adj_close"
        warnings.warn(
            "Using vendor-provided adjusted close. Verify that the vendor's "
            "adjustment history is point-in-time; fully reconstructed adjusted "
            "prices may leak future corporate actions into earlier dates.",
            DataQualityWarning,
            stacklevel=2,
        )
    else:
        price_col = "close"
        warnings.warn(
            "No adjusted close supplied. Raw close is being used unless corporate "
            "actions are supplied. Split/bonus/dividend events can distort returns.",
            DataQualityWarning,
            stacklevel=2,
        )

    prices = df.pivot(index="date", columns="symbol", values=price_col).sort_index()

    if corporate_actions_path is None:
        return prices.astype(float)

    actions = pd.read_csv(corporate_actions_path)
    actions.columns = [c.lower().strip() for c in actions.columns]

    required = {"symbol", "ex_date", "factor"}
    if not required.issubset(actions.columns):
        raise ValueError(
            "corporate_actions_path must contain symbol, ex_date, factor. "
            "Optional: availability_date."
        )

    if "availability_date" not in actions.columns:
        warnings.warn(
            "Corporate actions file has no availability_date. Assuming actions "
            "are known on ex_date. This may be optimistic.",
            DataQualityWarning,
            stacklevel=2,
        )
        actions["availability_date"] = actions["ex_date"]

    actions["symbol"] = actions["symbol"].astype(str).str.upper().str.strip()
    actions["ex_date"] = pd.to_datetime(actions["ex_date"])
    actions["availability_date"] = pd.to_datetime(actions["availability_date"])
    actions["factor"] = actions["factor"].astype(float)

    actions = actions[
        (actions["availability_date"] <= as_of)
        & (actions["ex_date"] <= as_of)
    ]

    adjusted = prices.copy().astype(float)

    for _, row in actions.iterrows():
        sym = row["symbol"]
        if sym not in adjusted.columns:
            continue
        ex_date = row["ex_date"]
        factor = row["factor"]

        if factor <= 0:
            raise ValueError(f"Invalid corporate action factor for {sym}: {factor}")

        adjusted.loc[adjusted.index < ex_date, sym] = (
            adjusted.loc[adjusted.index < ex_date, sym] / factor
        )

    warnings.warn(
        "Corporate-action adjustment is applied as-of loader end date. For a fully "
        "point-in-time historical backtest, store adjustment snapshots by signal date "
        "or use raw prices plus an event-time return adjustment engine.",
        DataQualityWarning,
        stacklevel=2,
    )

    return adjusted


def _load_sectors(path: Path | None, tickers: pd.Index) -> pd.Series:
    if path is None:
        warnings.warn(
            "No sector map supplied. Assigning all tickers to UNKNOWN; sector "
            "neutralization/caps will be weak.",
            DataQualityWarning,
            stacklevel=2,
        )
        return pd.Series("UNKNOWN", index=tickers, name="sector")

    df = pd.read_csv(path)
    df.columns = [c.lower().strip() for c in df.columns]

    if not {"symbol", "sector"}.issubset(df.columns):
        raise ValueError("sectors_path must contain symbol and sector columns")

    df["symbol"] = df["symbol"].astype(str).str.upper().str.strip()
    sectors = df.drop_duplicates("symbol").set_index("symbol")["sector"]
    sectors = sectors.reindex(tickers).fillna("UNKNOWN")
    sectors.name = "sector"

    if (sectors == "UNKNOWN").any():
        warnings.warn(
            "Some tickers have missing sectors and were assigned UNKNOWN.",
            DataQualityWarning,
            stacklevel=2,
        )

    return sectors


def _load_fundamentals(
    path: Path | None,
    start: pd.Timestamp,
    end: pd.Timestamp,
    tickers: list[str],
) -> dict[str, pd.DataFrame]:
    if path is None:
        warnings.warn(
            "No fundamentals supplied. QualitySignal will not run unless "
            "roe/accruals/earnings_vol are provided.",
            DataQualityWarning,
            stacklevel=2,
        )
        return {}

    df = pd.read_csv(path)
    df.columns = [c.lower().strip() for c in df.columns]

    if "period_end" in df.columns and "availability_date" not in df.columns:
        raise ValueError(
            "Fundamentals contain period_end but no availability_date. "
            "This would leak future information. Provide filing/availability dates."
        )

    required = {"availability_date", "symbol"}
    if not required.issubset(df.columns):
        raise ValueError("fundamentals_path must contain availability_date and symbol")

    df["availability_date"] = pd.to_datetime(df["availability_date"])
    df["symbol"] = df["symbol"].astype(str).str.upper().str.strip()
    df = df[(df["availability_date"] >= start) & (df["availability_date"] <= end)]

    fields = [c for c in df.columns if c not in {"availability_date", "symbol", "period_end"}]
    out: dict[str, pd.DataFrame] = {}

    for field in fields:
        frame = (
            df.pivot_table(
                index="availability_date",
                columns="symbol",
                values=field,
                aggfunc="last",
            )
            .sort_index()
            .reindex(columns=tickers)
        )
        out[field] = frame

    return out


def _load_optional_frame(
    path: Path | None,
    start: pd.Timestamp,
    end: pd.Timestamp,
) -> pd.DataFrame | None:
    if path is None:
        return None

    df = pd.read_csv(path)
    df.columns = [c.lower().strip() for c in df.columns]

    if "date" not in df.columns:
        raise ValueError(f"{path} must contain date column")

    df["date"] = pd.to_datetime(df["date"])
    df = df[(df["date"] >= start) & (df["date"] <= end)]
    return df.set_index("date").sort_index()


def _load_bhavcopy_nsepython(
    start: pd.Timestamp,
    end: pd.Timestamp,
    universe: str,
) -> pd.DataFrame:
    try:
        import nsepython  # noqa: F401
    except ImportError as exc:
        raise ImportError(
            "nsepython is not installed. Install it or use source='csv'."
        ) from exc

    raise NotImplementedError(
        "nsepython adapter is intentionally lazy. Wire the exact project-approved "
        "nsepython function here after validating schema, corporate actions, and "
        "rate-limit behavior. Tests must continue to use source='csv'."
    )


def _load_bhavcopy_nsefin(
    start: pd.Timestamp,
    end: pd.Timestamp,
    universe: str,
) -> pd.DataFrame:
    try:
        import nsefin  # noqa: F401
    except ImportError as exc:
        raise ImportError(
            "nsefin is not installed. Install it or use source='csv'."
        ) from exc

    raise NotImplementedError(
        "nsefin adapter is intentionally lazy. Wire the exact project-approved "
        "nsefin function here after validating schema, corporate actions, and "
        "rate-limit behavior. Tests must continue to use source='csv'."
    )


def _cache_key(
    start: pd.Timestamp,
    end: pd.Timestamp,
    universe: str,
    cfg: LoaderConfig,
) -> str:
    raw = "|".join(
        [
            str(start.date()),
            str(end.date()),
            universe,
            cfg.source,
            str(cfg.bhavcopy_dir),
            str(cfg.sectors_path),
            str(cfg.fundamentals_path),
            str(cfg.corporate_actions_path),
            str(cfg.macro_path),
            str(cfg.option_chain_path),
            str(cfg.fii_deriv_path),
            str(cfg.resample),
        ]
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def _write_marketdata_cache(path: Path, data: MarketData) -> None:
    rows = []

    def add_frame(name: str, frame: pd.DataFrame | None) -> None:
        if frame is None:
            return
        tmp = frame.copy()
        tmp.index.name = "date"
        long = tmp.reset_index().melt(id_vars="date", var_name="field", value_name="value")
        long["component"] = name
        rows.append(long)

    add_frame("prices", data.prices)

    for key, frame in data.fundamentals.items():
        add_frame(f"fundamentals:{key}", frame)

    if data.macro is not None:
        tmp = data.macro.copy()
        tmp.index.name = "date"
        long = tmp.reset_index().melt(id_vars="date", var_name="field", value_name="value")
        long["component"] = "macro"
        rows.append(long)

    if data.option_chain is not None:
        add_frame("option_chain", data.option_chain)

    if data.fii_deriv is not None:
        add_frame("fii_deriv", data.fii_deriv)

    cache = pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()
    cache.to_parquet(path, index=False)

    sectors = data.sectors.rename("sector").reset_index().rename(columns={"index": "symbol"})
    sectors.to_parquet(path.with_suffix(".sectors.parquet"), index=False)


def _read_marketdata_cache(path: Path) -> MarketData:
    cache = pd.read_parquet(path)
    sectors_df = pd.read_parquet(path.with_suffix(".sectors.parquet"))
    sectors = sectors_df.set_index("symbol")["sector"]

    def get_component(name: str, columns_name: str | None) -> pd.DataFrame | None:
        part = cache[cache["component"] == name]
        if part.empty:
            return None
        frame = part.pivot(index="date", columns="field", values="value").sort_index()
        # Restore the original column-axis name so a cached load is byte-identical
        # to a fresh one (the long-format cache uses a generic 'field' axis).
        frame.columns.name = columns_name
        return frame

    # Price/fundamental frames are keyed by ticker symbol; macro-style frames are not.
    prices = get_component("prices", columns_name="symbol")
    if prices is None:
        raise ValueError("Cached MarketData has no prices component")

    fundamentals: dict[str, pd.DataFrame] = {}
    for component in cache["component"].dropna().unique():
        if str(component).startswith("fundamentals:"):
            key = str(component).split(":", 1)[1]
            frame = get_component(component, columns_name="symbol")
            if frame is not None:
                fundamentals[key] = frame

    return MarketData(
        prices=prices,
        sectors=sectors,
        fundamentals=fundamentals,
        macro=get_component("macro", columns_name=None),
        option_chain=get_component("option_chain", columns_name="symbol"),
        fii_deriv=get_component("fii_deriv", columns_name="symbol"),
    )
