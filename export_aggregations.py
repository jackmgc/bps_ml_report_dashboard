#!/usr/bin/env python3
"""Export aggregated tables to CSV for ML pipeline"""

from etl.aggregator import aggregate_for_clustering, aggregate_for_timeseries

# Export Table 1: Clustering
print("Exporting clustering table...")
df_clust = aggregate_for_clustering()
output_file_1 = "data/ml_clustering_aggregated.csv"
df_clust.to_csv(output_file_1, index=False)
print(f"[OK] Exported {len(df_clust)} provinces x {len(df_clust.columns)} columns to {output_file_1}")

# Export Table 2: Time Series
print("\nExporting time series table...")
df_ts = aggregate_for_timeseries()
output_file_2 = "data/ml_timeseries_province_year.csv"
df_ts.to_csv(output_file_2, index=False)
print(f"[OK] Exported {len(df_ts)} records x {len(df_ts.columns)} columns to {output_file_2}")

# Summary
print("\n" + "="*80)
print("AGGREGATION EXPORT SUMMARY")
print("="*80)
print(f"\nTable 1 - K-MEANS/HDBSCAN Clustering:")
print(f"  File: {output_file_1}")
print(f"  Rows: {len(df_clust)} provinces")
print(f"  Columns: {len(df_clust.columns)} (26 predictors/targets + metadata)")
print(f"  Structure: 1 row per province")
print(f"  Predictors: Mean + % trend (2021-2025 for ekonomi_miskin [LAGGED], 2020-2024 for others)")
print(f"  Targets: Mean only (2020-2024)")

print(f"\nTable 2 - Spearman/Linear Regression/Random Forest:")
print(f"  File: {output_file_2}")
print(f"  Rows: {len(df_ts)} province-year combinations")
print(f"  Columns: {len(df_ts.columns)} (17 predictors/targets + metadata)")
print(f"  Year Range: 2020-2024")
print(f"  Provinces: {df_ts['provinsi'].nunique()}")
print(f"  Structure: 1 row per province x year")
print(f"  ekonomi_miskin: LAGGED from 2021-2025 data")
print(f"  All others: raw values from 2020-2024")

print("\n" + "="*80)
print("IMPORTANT NOTE ON LAGGING")
print("="*80)
print("ekonomi_miskin data is available from 2021-2025 (one year ahead).")
print("To use it as a predictor for 2020-2024 targets, we LAGGED it:")
print("  - 2020 target row: ekonomi_miskin = 2021 value (lagged)")
print("  - 2021 target row: ekonomi_miskin = 2022 value (lagged)")
print("  - 2022 target row: ekonomi_miskin = 2023 value (lagged)")
print("  - 2023 target row: ekonomi_miskin = 2024 value (lagged)")
print("  - 2024 target row: ekonomi_miskin = 2025 value (lagged)")
print("\nThis ensures:")
print("  1. ekonomi_miskin precedes the target variable temporally")
print("  2. All 5 years (2020-2024) have complete predictor data")
print("  3. No missing values due to data availability")


print("\n" + "="*80)
print("Column Definitions")
print("="*80)
print("\nTable 1 - Predictors (mean + trend %):")
print("  - ekonomi_miskin_*: % population in poverty")
print("  - ekonomi_upah_*: Average wage per hour")
print("  - kesehatan_ahh_laki_*: Life expectancy (Male)")
print("  - kesehatan_ahh_perempuan_*: Life expectancy (Female)")
print("  - kesehatan_unmet_*: Unmet health service needs %")
print("  - ketenagakerjaan_formal_*: % formal employment")
print("  - ketenagakerjaan_informal_*: % informal employment")
print("  - teknologi_telepon_*: % with mobile phone")
print("  - teknologi_internet_*: % with internet access")
print("\nTable 1 - Targets (mean only):")
print("  - apm_sd_mean: Net participation rate (Primary)")
print("  - apm_smp_mean: Net participation rate (Junior Secondary)")
print("  - apm_sm_mean: Net participation rate (Senior Secondary)")
print("  - apk_pt_mean: Gross participation rate (Higher Education)")
print("  - rata_rata_lama_sekolah_mean: Average years of schooling")

print("\nTable 2 - All indicators:")
print("  Same structure but with raw yearly values per province")
print("  Use for time-series analysis, correlation, regression, random forest")
