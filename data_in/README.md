# Drop real data here

Put your real NSE data in this folder, then run:

```bash
python -m scripts.run_real_validation
```

Expected layout (only `bhavcopy/` is required):

```
data_in/
  bhavcopy/        # NSE bhavcopy CSVs (one or many). Legacy or UDiFF columns auto-detected.
  sectors.csv      # optional: columns  symbol,sector
  fundamentals.csv # optional: columns  symbol,availability_date,roe,accruals,earnings_vol
  macro.csv        # optional: columns  date,repo_rate,cpi,iip
```

See `../Research/Datasets/REAL_DATA_RUNBOOK.md` for where to get the files and the
column formats. Contents of this folder are git-ignored.
