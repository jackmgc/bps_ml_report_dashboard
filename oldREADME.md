# Indonesian Regional Development Indicators - ETL & ML Pipeline

## 📋 Project Overview

This is a comprehensive **ETL (Extract, Transform, Load) + ML (Machine Learning) pipeline** designed to process Indonesian regional socioeconomic indicators and perform advanced analytics. The system orchestrates data from multiple CSV sources, loads them into a PostgreSQL data warehouse, and applies machine learning algorithms (clustering, regression) to identify patterns and relationships.

### Key Capabilities
- **ETL Pipeline**: Extract CSV data → Transform to canonical format → Load to staging/DW schemas
- **Data Validation**: Quality checks, reconciliation against source data, integrity verification
- **Data Aggregation**: Create ML-ready aggregated tables (province-level & province-year level)
- **ML Models**: K-Means clustering, HDBSCAN, Linear Regression, Random Forest, Spearman correlation
- **Reporting**: Enhanced HTML reports with visualizations (heatmaps, regression plots, cluster analysis)

### Data Domains Covered
- **Ekonomi** (Economics): Poverty rates, average wages
- **Kesehatan** (Health): Life expectancy, unmet healthcare needs
- **Ketenagakerjaan** (Employment): Formal and informal employment rates
- **Pendidikan** (Education): School enrollment rates (APM/APK), average years of education
- **Teknologi** (Technology): Mobile phone and internet access

---

## 🏗️ Architecture Overview

```
┌──────────────────────────────────────────────────────────────────┐
│                        ETL + ML PIPELINE                          │
├──────────────────────────────────────────────────────────────────┤
│                                                                    │
│  1. EXTRACT         2. TRANSFORM        3. LOAD        4. VALIDATE│
│  └─ CSV Files       └─ Clean & Validate └─ Staging     └─ Quality │
│                       └─ Canonicalize    └─ DW Schema      Checks  │
│                                                                    │
│  5. RECONCILE       6. AGGREGATE        7. ML PIPELINE 8. REPORT  │
│  └─ Staging vs      └─ Create Data      └─ Clustering  └─ HTML   │
│     Source           Mart Tables         └─ Regression   Report  │
│                                                                    │
└──────────────────────────────────────────────────────────────────┘

DATA FLOW:
  CSV Files (data/)
       ↓
  [EXTRACT & CLEAN]
       ↓
  Cleaned DataFrames
       ↓
  [TRANSFORM & VALIDATE]
       ↓
  Canonical Format DataFrame
       ↓
  [LOAD TO STAGING SCHEMA]
       ↓
  staging.indikator_raw
       ↓
  [RECONCILE]
       ↓
  [CREATE DW SCHEMA & LOAD]
       ↓
  dw.fact_indikator + dimension tables
       ↓
  [AGGREGATE TO DATA MART]
       ↓
  dm.agg_province_ml (for clustering)
  dm.agg_timeseries (for time series)
       ↓
  [ML PIPELINE]
       ↓
  ml_results.json
       ↓
  [GENERATE REPORTS]
       ↓
  HTML reports + visualizations
```

---

## 📁 File Structure & Descriptions

### Root Level Files

| File | Purpose |
|------|---------|
| **main.py** | **Main orchestrator** - Controls the entire ETL+ML pipeline with phase-based execution |
| **results.py** | Standalone ML runner - Executes ML pipeline and generates HTML report (deprecated in favor of main.py phases) |
| **report_generator.py** | Report generation module - Creates enhanced HTML reports with embedded visualizations |
| **export_aggregations.py** | Export utility - Exports aggregated tables from database to CSV for external use |
| **requirements.txt** | Python dependencies - Lists all required packages (pandas, scikit-learn, etc.) |

### Configuration Folder (`config/`)

| File | Purpose |
|------|---------|
| **db_config.py** | Database configuration - Reads PostgreSQL connection details from `.env` file, sets up connection string |
| **constants.py** | Constants & mappings - Defines canonical province list, dropped provinces, numeric ranges for validation |
| **indicators_mapping.py** | Indicator definitions - Maps indicator names to categories, units, sources, CSV filenames, year ranges |
| **ml_config.json** | ML model parameters - Stores K-Means clusters, HDBSCAN parameters, regression settings |
| **__init__.py** | Package initializer - Makes config folder a Python package |

### ETL Folder (`etl/`)

| Module | Purpose | Key Functions |
|--------|---------|----------------|
| **extractor.py** | CSV extraction & cleaning | `extract_all_csvs()` - Reads CSV files and applies table-specific cleaning logic |
| **table_cleaners.py** | CSV format handlers | `_filter_provinces()`, `clean_apm_csv()`, `clean_ahh_csv()` - Specialized cleaners for different CSV formats |
| **transformer.py** | Data standardization | `transform_to_canonical()` - Validates provinces, numeric ranges, adds metadata, flags quality issues |
| **loader_python.py** | Database loading | `load_to_staging()`, `create_dw_schema()`, `load_to_dw()` - Creates schemas and loads data into PostgreSQL |
| **validator.py** | Quality assurance | `generate_quality_report()` - Validates data integrity, generates reconciliation reports |
| **reconciler.py** | Source data validation | `reconcile_staging_to_source()` - Compares staging data against source CSVs to ensure completeness |
| **aggregator.py** | ML data preparation | `refresh_data_mart()`, `aggregate_for_clustering()`, `aggregate_for_timeseries()` - Creates aggregated tables for ML |
| **ml_pipeline.py** | Machine learning | `MLPipeline` class with methods for K-Means, HDBSCAN, Linear Regression, Random Forest, Spearman correlation |
| **__init__.py** | Package initializer | Makes etl folder a Python package |

### Data Folder (`data/`)

| File | Content | Variables |
|------|---------|-----------|
| **Ekonomi_persentase_penduduk_miskin.csv** | Poverty rates | Years: 2021-2025, Units: %, Provinces: 35 |
| **Ekonomi_upah_rata-rata.csv** | Average wages | Years: 2020-2024, Units: Rupiah/Jam, Provinces: 35 |
| **Kesehatan_angka_harapan_hidup.csv** | Life expectancy | Years: 2020-2024, Split by gender (Laki/Perempuan), Units: Years |
| **Kesehatan_unmet_layanan_kesehatan.csv** | Unmet healthcare | Years: 2020-2024, Units: %, Provinces: 35 |
| **Ketenagakerjaan_formal.csv** | Formal employment | Years: 2020-2024, Units: %, Provinces: 35 |
| **Ketenagakerjaan_informal.csv** | Informal employment | Years: 2020-2024, Units: %, Provinces: 35 |
| **Pendidikan_APK_PT_provinsi.csv** | Higher ed enrollment | Years: 2020-2024, Units: %, Provinces: 35 |
| **Pendidikan_APM_provinsi.csv** | School enrollment | Years: 2020-2024, Split by level (SD/SMP/SM), Units: % |
| **Pendidikan_Rata-rata_lama_sekolah.csv** | Avg years of education | Years: 2020-2024, Units: Years, Provinces: 35 |
| **Teknologi_memiliki_telepon_seluler.csv** | Mobile phone access | Years: 2020-2024, Units: %, Provinces: 35 |
| **Teknologi_mengakses_internet.csv** | Internet access | Years: 2020-2024, Units: %, Provinces: 35 |

### Utils Folder (`utils/`)

| File | Purpose | Key Functions |
|------|---------|----------------|
| **logger.py** | Logging configuration | `get_logger(name)` - Returns configured logger with console & file output |
| **helpers.py** | Utility functions | `validate_province()`, `execute_sql_script()`, `query_database()` - Common helper functions |
| **__init__.py** | Package initializer | Makes utils folder a Python package |

### Reports Folder (`reports/`)

| File | Purpose |
|------|---------|
| **ml_analysis_report_enhanced.html** | Main output report - Interactive HTML with embedded visualizations, tables, and cluster analysis |
| **ml_results.json** | ML model results - JSON file containing clustering assignments, regression coefficients, metrics |
| **validation_report.txt** | Data quality report - Text report of validation checks and issues found |
| **reconciliation_report.txt** | Data reconciliation report - Comparison of staging vs. source data |
| **etl.log** | Pipeline execution log - Detailed logs of all ETL operations |

### Scratch Folder (`scratch/`)

| File | Purpose |
|------|---------|
| **analyze_dist.py** | Exploratory analysis - Standalone script for analyzing data distributions (development/testing) |

---

## 🚀 Getting Started

### Prerequisites
- **Python 3.8+**
- **PostgreSQL 12+** (with proper encoding UTF-8)
- **Virtual environment** (venv, conda, etc.)

### Installation Steps

1. **Clone/Setup the repository**
   ```bash
   cd f:\BINUS\SEMS 8\code-program
   ```

2. **Create Python virtual environment**
   ```bash
   python -m venv venv
   # Windows
   venv\Scripts\activate
   # macOS/Linux
   source venv/bin/activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Create `.env` file** in the root directory
   ```
   PSQL_HOST=localhost
   PSQL_PORT=5432
   PSQL_USER=your_username
   PSQL_PASSWORD=your_password
   PSQL_DBNAME=skripsi
   DATA_FOLDER=./data
   REPORTS_FOLDER=./reports
   LOG_LEVEL=INFO
   RECONCILIATION_TOLERANCE=0.0001
   ```

5. **Verify CSV files** are in `data/` folder and PostgreSQL database exists

### Database Setup

The pipeline automatically creates the following schemas:
- **staging**: Raw extracted and transformed data
- **dw**: Dimensional data warehouse with fact & dimension tables
- **dm**: Data mart with aggregated tables for ML

No manual SQL scripts needed - all created programmatically by the pipeline.

---

## 🔄 Pipeline Execution

### Run Complete Pipeline
```bash
# Run entire ETL + ML pipeline
python main.py --phase all

# Run ETL only (up to validation)
python main.py --phase validate

# Run up to aggregation
python main.py --phase aggregation

# Run ML pipeline only
python main.py --phase ml-pipeline

# Generate ML report only
python main.py --phase ml-report

# Force DW load even if reconciliation fails (use with caution)
python main.py --phase all --force-dw-load
```

### Alternative: Using results.py (Standalone ML)
```bash
# Run ML pipeline and generate report (standalone mode)
python results.py
```

### Export Aggregations to CSV
```bash
# Export ML-ready data to CSV files
python export_aggregations.py

# Creates:
# - data/ml_clustering_aggregated.csv (province-level, for K-Means/HDBSCAN)
# - data/ml_timeseries_province_year.csv (province-year level, for regression)
```

---

## 📊 Pipeline Phases Explained

### Phase 1: EXTRACT
- **Module**: `etl/extractor.py`
- **Input**: CSV files from `data/` folder
- **Output**: Cleaned DataFrames
- **Operations**:
  - Reads each CSV using table-specific cleaners
  - Handles different formats (APM splits education levels, AHH splits by gender)
  - Filters to canonical 35 provinces
  - Converts wide format to long format

### Phase 2: TRANSFORM
- **Module**: `etl/transformer.py`
- **Input**: Cleaned DataFrames
- **Output**: Canonical format DataFrame
- **Operations**:
  - Validates province names against canonical list
  - Validates numeric values against known ranges
  - Flags data quality issues
  - Adds metadata columns (created_at, data_quality_flag)

### Phase 3: LOAD (Staging)
- **Module**: `etl/loader_python.py`
- **Input**: Canonical format DataFrame
- **Output**: `staging.indikator_raw` table
- **Operations**:
  - Creates staging schema
  - Loads data using SQLAlchemy batch inserts
  - Creates indexes on frequently queried columns

### Phase 4: VALIDATE
- **Module**: `etl/validator.py`
- **Input**: Staging data
- **Output**: `validation_report.txt`
- **Operations**:
  - Runs data quality checks
  - Validates referential integrity
  - Counts null values, unique values
  - Generates quality summary report

### Phase 5: RECONCILE
- **Module**: `etl/reconciler.py`
- **Input**: Staging data vs. original CSVs
- **Output**: `reconciliation_report.txt`
- **Operations**:
  - Compares row counts per province-year
  - Verifies all provinces represented
  - Checks data completeness against source
  - **Gate**: Prevents DW load if reconciliation fails (unless --force-dw-load)

### Phase 6: LOAD (Data Warehouse)
- **Module**: `etl/loader_python.py`
- **Input**: Staging data
- **Output**: `dw.*` schema with fact and dimension tables
- **Operations**:
  - Creates dimensional tables (provinces, years, indicators)
  - Creates fact table with foreign keys
  - Loads data from staging with referential integrity

### Phase 7: AGGREGATE
- **Module**: `etl/aggregator.py`
- **Input**: DW fact and dimension tables
- **Output**: `dm.agg_province_ml` and `dm.agg_timeseries` tables
- **Operations**:
  - Creates data mart schema
  - Aggregates by province (mean + trend % for clustering)
  - Aggregates by province-year (for time series regression)
  - Handles special lagging for poverty data (2021-2025 → used as predictor for 2020-2024)

### Phase 8: ML PIPELINE
- **Module**: `etl/ml_pipeline.py`
- **Input**: Aggregated data from data mart
- **Output**: `reports/ml_results.json`
- **Operations**:
  - **K-Means Clustering**: Groups provinces by similarity (default 3-5 clusters)
  - **HDBSCAN**: Density-based clustering for discovering natural groupings
  - **Spearman Correlation**: Calculates rank correlation between predictors and targets
  - **Linear Regression**: Fits linear models for each target variable
  - **Random Forest**: Ensemble method for non-linear relationships
  - Calculates metrics (silhouette score, R², MAE, etc.)

### Phase 9: REPORT GENERATION
- **Module**: `report_generator.py`
- **Input**: ML results JSON
- **Output**: `reports/ml_analysis_report_enhanced.html`
- **Operations**:
  - Generates correlation heatmaps
  - Creates cluster visualization plots
  - Produces regression analysis graphs
  - Embeds all images as base64 in HTML
  - Includes summary tables with metrics

---

## 🔐 Configuration Details

### Database Configuration (`.env`)
```
# PostgreSQL Connection
PSQL_HOST=localhost                 # Server hostname
PSQL_PORT=5432                      # Default PostgreSQL port
PSQL_USER=postgres                  # Database user
PSQL_PASSWORD=your_password         # Database password (URL-encoded if special chars)
PSQL_DBNAME=skripsi                 # Database name

# File Paths
DATA_FOLDER=./data                  # CSV input folder
REPORTS_FOLDER=./reports            # Output reports folder

# Pipeline Settings
LOG_LEVEL=INFO                      # Logging level (DEBUG, INFO, WARNING, ERROR)
RECONCILIATION_TOLERANCE=0.0001     # Tolerance for numeric comparisons
```

### ML Configuration (`config/ml_config.json`)
```json
{
  "kmeans": {
    "n_clusters": 4,
    "random_state": 42,
    "n_init": 10
  },
  "hdbscan": {
    "min_cluster_size": 3,
    "min_samples": 2
  },
  "linear_regression": {
    "fit_intercept": true
  },
  "random_forest": {
    "n_estimators": 100,
    "random_state": 42,
    "max_depth": 10
  }
}
```

### Indicator Mappings (`config/indicators_mapping.py`)
Maps indicator keys to metadata:
- Category (Ekonomi, Kesehatan, etc.)
- Unit of measurement
- Data source
- CSV filename
- Year range available

### Constants (`config/constants.py`)
- **CANONICAL_PROVINCES**: List of 35 valid provinces (34 provinces + INDONESIA national aggregate)
- **DROPPED_PROVINCES**: 4 new PAPUA provinces with incomplete data (Papua Barat Daya, dll)
- **NUMERIC_RANGES**: Valid ranges for each indicator (e.g., poverty 0-100%)
- **CSV_FILES**: List of all expected CSV filenames

---

## 📈 Data Models

### Staging Schema (`staging.indikator_raw`)
```
Columns:
- id (PK): Auto-increment record ID
- provinsi: Province name
- tahun: Year
- kategori: Category (Ekonomi, Kesehatan, etc.)
- indikator: Indicator key
- dimensi: Sub-dimension (e.g., gender, education level)
- nilai: Numeric value
- satuan: Unit of measurement
- is_national_aggregate: Boolean flag for INDONESIA rows
- sumber: Data source
- data_kualitas_flag: Quality flag (VALID, OUTLIER, SUSPICIOUS)
- catatan: Notes/comments
- created_at: Timestamp
```

### Data Warehouse Schema (`dw.*`)
Dimensional data warehouse structure:
- **dim_provinsi**: Province dimension
- **dim_tahun**: Year dimension
- **dim_indikator_dimensi**: Indicator-dimension combinations
- **fact_indikator**: Fact table with foreign keys

### Data Mart Schema (`dm.*`)
ML-ready aggregated tables:
- **dm.agg_province_ml**: Province-level (35 rows × ~50 columns) for clustering
  - Predictors: mean & trend % for 8 indicators (ekonomi, kesehatan, ketenagakerjaan, teknologi)
  - Targets: mean values for 5 education indicators
- **dm.agg_timeseries**: Province-year level (~175 rows × 23 columns) for regression
  - Years: 2020-2024 (5 years × 35 provinces)
  - Variables: Predictors + targets for time series analysis

---

## 🎯 Key Data Transformations

### Lagging Logic
Poverty data (`ekonomi_miskin`) is available from **2021-2025**, one year ahead of other indicators (2020-2024).
To use it as a predictor for 2020-2024 targets:
- **2020 targets** ← Poverty 2021 value (lagged)
- **2021 targets** ← Poverty 2022 value (lagged)
- **2022 targets** ← Poverty 2023 value (lagged)
- **2023 targets** ← Poverty 2024 value (lagged)
- **2024 targets** ← Poverty 2025 value (lagged)

### Format Conversions
- **APM Data**: Split single indicator into 3 (SD/SMP/SM education levels)
- **AHH Data**: Split by gender into 2 dimensions (Laki-laki/Perempuan)
- **Wide to Long**: Convert from year-columns to row-based format

### Aggregation Methods
- **Mean**: Average value across selected years
- **Trend %**: Percentage change from first to last year in range
- **Grouping**: Province-level (for clustering) and province-year level (for time series)

---

## 📊 Machine Learning Models

### 1. K-Means Clustering
- **Purpose**: Group provinces by similarity across socioeconomic indicators
- **Input**: 16 predictors (2 × 8 indicators) from `dm.agg_province_ml`
- **Output**: Cluster assignments + silhouette scores
- **Config**: Number of clusters, random state, initialization method

### 2. HDBSCAN Clustering
- **Purpose**: Density-based clustering to identify natural groupings
- **Input**: Same 16 predictors
- **Output**: Cluster labels + noise points
- **Advantage**: Automatically detects optimal number of clusters

### 3. Linear Regression
- **Purpose**: Identify linear relationships between predictors and targets
- **Input**: Time series data (province-year level)
- **Output**: Coefficients, R² score, MAE, RMSE
- **Targets**: 5 education indicators (APM SD/SMP/SM, APK PT, avg years)

### 4. Random Forest Regression
- **Purpose**: Capture non-linear relationships
- **Input**: Same time series data
- **Output**: Feature importance, R² score, MAE, RMSE
- **Advantage**: Handles interactions between predictors

### 5. Spearman Correlation
- **Purpose**: Rank-based correlation analysis
- **Input**: Time series data
- **Output**: Correlation matrix, p-values
- **Advantage**: Non-parametric, robust to outliers

---

## 📋 Quality Assurance & Validation

### Data Quality Checks
1. **Province Validation**: Ensures only canonical 35 provinces
2. **Numeric Range Validation**: Checks values within expected ranges
3. **Null Value Checks**: Identifies missing data
4. **Duplicate Detection**: Flags duplicate records
5. **Type Validation**: Ensures correct data types

### Reconciliation Checks
1. **Row Count Reconciliation**: Compares staging vs. source CSVs
2. **Province Completeness**: Verifies all provinces represented
3. **Year Range Validation**: Checks expected year coverage
4. **Dimension Splits**: Verifies correct number of splits (gender, education level)

### Reports Generated
- `validation_report.txt`: Detailed quality check results
- `reconciliation_report.txt`: Data completeness analysis
- `etl.log`: Execution log with all operations
- `ml_analysis_report_enhanced.html`: Final analysis and visualizations

---

## 🛠️ Troubleshooting

### Common Issues

**Issue**: "PSQL_USER not configured in .env file"
- **Solution**: Ensure `.env` file exists with PSQL_USER and PSQL_PASSWORD

**Issue**: "CSV file not found" error
- **Solution**: Verify all CSV files present in `data/` folder with exact filenames

**Issue**: "Connection refused" to PostgreSQL
- **Solution**: Check PostgreSQL is running, correct host/port in `.env`

**Issue**: Reconciliation fails
- **Solution**: Check for missing provinces in source CSVs, or use `--force-dw-load` flag to skip

**Issue**: Special characters in password break connection
- **Solution**: URL-encode password in `.env` (e.g., `p@ss%40word` for `p@ss@word`)

---

## 📊 Output Files

### Primary Outputs

| File | Format | Purpose |
|------|--------|---------|
| `reports/ml_analysis_report_enhanced.html` | HTML | Interactive report with visualizations |
| `reports/ml_results.json` | JSON | Raw ML model results for external use |
| `data/ml_clustering_aggregated.csv` | CSV | Province-level aggregated data |
| `data/ml_timeseries_province_year.csv` | CSV | Province-year level time series data |

### Secondary Outputs (Logs)

| File | Format | Purpose |
|------|--------|---------|
| `reports/etl.log` | Text | Complete execution log |
| `reports/validation_report.txt` | Text | Data quality validation results |
| `reports/reconciliation_report.txt` | Text | Data reconciliation checks |

---

## 🔄 Workflow Examples

### Example 1: Full Pipeline Execution
```bash
# Run complete ETL + ML + report generation
python main.py --phase all

# Checks:
# ✓ Extracts and cleans CSVs
# ✓ Transforms to canonical format
# ✓ Loads to staging
# ✓ Validates data quality
# ✓ Reconciles with source
# ✓ Creates DW schema
# ✓ Creates data mart
# ✓ Runs ML models
# ✓ Generates report
```

### Example 2: Incremental Development
```bash
# Test extraction only
python main.py --phase validate

# Verify reconciliation
# (Review reconciliation_report.txt)

# Then run rest of pipeline
python main.py --phase ml-pipeline --force-dw-load
python main.py --phase ml-report
```

### Example 3: ML Experimentation
```bash
# Export aggregated data for external analysis
python export_aggregations.py

# Edit config/ml_config.json with new parameters

# Re-run ML pipeline with updated config
python main.py --phase ml-pipeline
python main.py --phase ml-report
```

---

## 📚 Code Architecture Patterns

### Pattern 1: Modular Phases
- Each ETL phase is independent and can be run separately
- State passed between phases via global variables or database
- Enables incremental debugging and development

### Pattern 2: Table-Specific Cleaners
- Different CSV formats handled by specialized cleaner functions
- Registered in `table_cleaners.py` via `get_cleaner(filename)`
- Easy to add new CSV types without modifying core logic

### Pattern 3: Configuration as Code
- ML model parameters defined in `config/ml_config.json`
- Database config from `.env` file
- Indicator metadata in `config/indicators_mapping.py`
- Easy to tune without code changes

### Pattern 4: Inline SQL (No .sql Files)
- DDL statements written as Python strings in modules
- Easier version control, self-contained modules
- No external SQL file dependencies

### Pattern 5: Comprehensive Logging
- Dual output: console (INFO+) and file (DEBUG+)
- Module-specific loggers for traceability
- All logs stored in `reports/etl.log`

---

## 🔍 Key Concepts

### Canonical Format
Unified data structure all records conform to:
```
provinsi | tahun | kategori | indikator | dimensi | nilai | satuan | ...
```
- Enables consistent loading and aggregation
- Quality flags track data issues
- Metadata columns for tracking provenance

### Reconciliation as GATE
Reconciliation phase acts as quality gate:
- Compares staging vs. source CSVs
- Validates row counts and completeness
- **Blocks DW load** if issues found (unless --force-dw-load)
- Ensures DW always consistent with source

### Data Mart for ML
Aggregated tables specifically designed for ML:
- **Clustering table**: Province-level (1 row per province)
- **Time series table**: Province-year level (175 rows)
- Pre-computed means and trends
- Missing value handling
- Proper scaling ready for algorithms

### Lagging for Time Series
Handles data availability differences:
- Poverty data one year ahead of others
- Lagged (shifted) to align time series
- Enables regression models to work correctly

---

## 📞 Support & Development

### Adding a New Indicator
1. Add CSV file to `data/` folder
2. Register in `config/constants.py` (CSV_FILES list)
3. Add mapping to `config/indicators_mapping.py`
4. Create cleaner function in `etl/table_cleaners.py`
5. Add validation rules to `config/constants.py` (NUMERIC_RANGES)
6. Run pipeline: `python main.py --phase all`

### Modifying ML Models
1. Edit `config/ml_config.json` with new parameters
2. Update model in `etl/ml_pipeline.py` if needed
3. Run: `python main.py --phase ml-pipeline`
4. Review results in `reports/ml_results.json` and HTML report

### Customizing Reports
1. Edit `report_generator.py`
2. Add new visualizations, tables, sections
3. Run: `python main.py --phase ml-report`
4. Check output in `reports/ml_analysis_report_enhanced.html`

---

## 📄 License & Attribution

This project processes indicators from:
- **BPS** (Badan Pusat Statistik - Indonesian Central Statistics Bureau)
- **Susenas**: National Economic Survey
- **Sakernas**: National Labor Force Survey

---

## 🎓 Project Context

**Status**: Thesis/Skripsi project (BINUS University, Semester 8)
**Purpose**: Analyze Indonesian regional socioeconomic indicators and identify patterns through clustering and regression analysis
**Data Period**: 2020-2025 (with lagged poverty data from 2021-2025)
**Geographic Scope**: 34 provinces + INDONESIA national aggregate

---

**Last Updated**: 2026-04-28  
**Database**: PostgreSQL (skripsi)  
**Python Version**: 3.8+
