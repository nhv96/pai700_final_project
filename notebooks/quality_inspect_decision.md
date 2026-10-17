# Introduction

After running the `quality_scan_htot` notebook we can inspect the quality of the source dataset, then make decision on which building to use, what column to use, how to handle gaps,...

This file is to keep track of each decision made for selecting dataset to train model, so that we can always revise the plan when evaluate the model performance.

| Date | Building to Include/Exclude | Column used | Gap rules | Train/Test set split |
|------|-----------------------------|-------------|-----------|----------------------|
|2026-10-15| Drop all Drammen buildings. Use Oslo: 8105, 8107, 8116. These building has long time span data, low rate of NaN and Flat data, better chance for good window dataset.   | 'TimeStamp', 'HtTot', 'Tout', 'WindSpd', 'SolGlob', 'WindDir'            |     Weather: linear interpolation for gaps of at most 3 hours, longer gaps stay empty and those rows are dropped. `Tout` sentinel (< -100) treated as empty, negative `SolGlob` clipped to 0. HtTot: drop empty rows, drop `HtTot == 0` rows, drop flat runs (6+ identical hours above zero). `HtDH` and `RH` left out.      |       Chronological split within each building, 70% train / 15% validation / 15% test, no shuffling. Whole-building split postponed until more buildings are used.               |

## Notes

- 2026-10-15: implemented in `etl/preprocess_htot.py`. Silver (`data/silver/building_<id>.parquet`) keeps all hours on a full hourly grid with only the sentinel and negative-solar fixes. Gold (`data/gold/htot_oslo.parquet`) applies the gap rules above and adds a `split` column.
- 2026-10-15: gold also has calendar features `hour` (0-23), `weekday` (Monday = 0) and `month` (1-12), plain integers in the data's fixed UTC+1 time.
- 2026-10-17: `SolGlob == 0` rows are kept. Zero is a real value (no sun) in about 28% of rows, mostly evening, night and early morning. Dropping them would remove those hours and break the hourly windows.
- 2026-10-17: modelling plan. Horizons 1 h, 6 h and 24 h. Inputs: past `HtTot`, weather, calendar, `year_of_construction`. Future weather comes from measured values (a "perfect forecast" replay), so setups can be compared on equal terms. Real forecast errors are not included, so scores are an upper bound for deployment.
- 2026-10-17: validation uses a rolling-origin (expanding window) split, never random. Features are scaled with statistics fitted on the training part only. Metrics: MAE and RMSE in kWh (`HtTot` is Wh per hour, divide by 1000) and WAPE (sum of absolute errors / sum of actuals), compared with a seasonal-naive baseline.
- 2026-10-17: the number of `HtTot` files is 37 (33 Oslo + 4 Drammen), none empty. The earlier count of 38 was wrong.
- Dropping `HtTot == 0` also removes legitimate summer hours when heating is off. If the model later fails in summer, revisit this rule first.