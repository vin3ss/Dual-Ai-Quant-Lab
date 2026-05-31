import pandas as pd
import pytest

from nse_alpha_forge.data.loaders import (
    DataQualityWarning,
    LoaderConfig,
    load_universe,
)


def test_load_universe_from_csv_fixture(tmp_path):
    bhav = tmp_path / "bhav"
    bhav.mkdir()

    pd.DataFrame(
        {
            "date": ["2024-01-31", "2024-01-31", "2024-02-29", "2024-02-29"],
            "symbol": ["AAA", "BBB", "AAA", "BBB"],
            "close": [100.0, 200.0, 110.0, 210.0],
            "adj_close": [100.0, 200.0, 110.0, 210.0],
        }
    ).to_csv(bhav / "part.csv", index=False)

    sectors = tmp_path / "sectors.csv"
    pd.DataFrame(
        {
            "symbol": ["AAA", "BBB"],
            "sector": ["IT", "BANK"],
        }
    ).to_csv(sectors, index=False)

    fundamentals = tmp_path / "fundamentals.csv"
    pd.DataFrame(
        {
            "availability_date": ["2024-01-31", "2024-01-31", "2024-02-29", "2024-02-29"],
            "symbol": ["AAA", "BBB", "AAA", "BBB"],
            "roe": [0.20, 0.10, 0.21, 0.11],
            "accruals": [0.02, 0.03, 0.01, 0.04],
            "earnings_vol": [0.10, 0.20, 0.11, 0.21],
        }
    ).to_csv(fundamentals, index=False)

    macro = tmp_path / "macro.csv"
    pd.DataFrame(
        {
            "date": ["2024-01-31", "2024-02-29"],
            "nifty_close": [21000.0, 22000.0],
            "india_vix": [14.0, 16.0],
            "fii_net": [100.0, -200.0],
        }
    ).to_csv(macro, index=False)

    cfg = LoaderConfig(
        cache_dir=tmp_path / "cache",
        source="csv",
        bhavcopy_dir=bhav,
        sectors_path=sectors,
        fundamentals_path=fundamentals,
        macro_path=macro,
        resample="ME",
    )

    with pytest.warns(DataQualityWarning):
        data = load_universe("2024-01-01", "2024-02-29", config=cfg)

    assert list(data.prices.columns) == ["AAA", "BBB"]
    assert data.prices.shape == (2, 2)
    assert data.sectors.loc["AAA"] == "IT"
    assert {"roe", "accruals", "earnings_vol"}.issubset(data.fundamentals)
    assert data.macro is not None
    assert "nifty_close" in data.macro.columns


def test_loader_uses_cache_without_re_reading_source(tmp_path):
    bhav = tmp_path / "bhav"
    bhav.mkdir()

    source_file = bhav / "part.csv"
    pd.DataFrame(
        {
            "date": ["2024-01-31"],
            "symbol": ["AAA"],
            "adj_close": [100.0],
        }
    ).to_csv(source_file, index=False)

    sectors = tmp_path / "sectors.csv"
    pd.DataFrame({"symbol": ["AAA"], "sector": ["IT"]}).to_csv(sectors, index=False)

    cfg = LoaderConfig(
        cache_dir=tmp_path / "cache",
        source="csv",
        bhavcopy_dir=bhav,
        sectors_path=sectors,
        use_cache=True,
        resample="ME",
    )

    with pytest.warns(DataQualityWarning):
        first = load_universe("2024-01-01", "2024-01-31", config=cfg)

    source_file.unlink()

    second = load_universe("2024-01-01", "2024-01-31", config=cfg)

    pd.testing.assert_frame_equal(first.prices, second.prices)
    pd.testing.assert_series_equal(first.sectors, second.sectors)


def test_fundamentals_without_availability_date_are_rejected(tmp_path):
    bhav = tmp_path / "bhav"
    bhav.mkdir()

    pd.DataFrame(
        {
            "date": ["2024-01-31"],
            "symbol": ["AAA"],
            "adj_close": [100.0],
        }
    ).to_csv(bhav / "part.csv", index=False)

    fundamentals = tmp_path / "fundamentals.csv"
    pd.DataFrame(
        {
            "period_end": ["2023-12-31"],
            "symbol": ["AAA"],
            "roe": [0.2],
        }
    ).to_csv(fundamentals, index=False)

    cfg = LoaderConfig(
        cache_dir=tmp_path / "cache",
        source="csv",
        bhavcopy_dir=bhav,
        fundamentals_path=fundamentals,
        use_cache=False,
    )

    with pytest.raises(ValueError, match="availability_date"):
        load_universe("2024-01-01", "2024-01-31", config=cfg)


def test_corporate_action_adjustment_uses_availability_date(tmp_path):
    bhav = tmp_path / "bhav"
    bhav.mkdir()

    pd.DataFrame(
        {
            "date": ["2024-01-31", "2024-02-29"],
            "symbol": ["AAA", "AAA"],
            "close": [100.0, 60.0],
        }
    ).to_csv(bhav / "part.csv", index=False)

    actions = tmp_path / "actions.csv"
    pd.DataFrame(
        {
            "symbol": ["AAA"],
            "ex_date": ["2024-02-15"],
            "availability_date": ["2024-02-15"],
            "factor": [2.0],
        }
    ).to_csv(actions, index=False)

    cfg = LoaderConfig(
        cache_dir=tmp_path / "cache",
        source="csv",
        bhavcopy_dir=bhav,
        corporate_actions_path=actions,
        use_cache=False,
        resample=None,
    )

    with pytest.warns(DataQualityWarning):
        data = load_universe("2024-01-01", "2024-02-29", config=cfg)

    assert data.prices.loc[pd.Timestamp("2024-01-31"), "AAA"] == 50.0
    assert data.prices.loc[pd.Timestamp("2024-02-29"), "AAA"] == 60.0
