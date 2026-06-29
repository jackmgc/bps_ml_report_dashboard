# Technical Architecture & Database Schema

## 🏛️ System Architecture

### High-Level System Design

```
┌─────────────────────────────────────────────────────────────────┐
│                    ETL + ML PIPELINE SYSTEM                      │
├─────────────────────────────────────────────────────────────────┤
│                                                                   │
│  INPUT LAYER                                                      │
│  ├─ CSV Files (11 indicators × 35 provinces × 5 years)          │
│  └─ Configuration (db_config, ml_config, constants)             │
│                                                                   │
│  EXTRACTION LAYER                                                 │
│  ├─ CSV Reader (pandas)                                          │
│  ├─ Table-Specific Cleaners (format normalization)              │
│  └─ Output: Cleaned DataFrames (wide & long format)             │
│                                                                   │
│  TRANSFORMATION LAYER                                             │
│  ├─ Canonical Format Converter                                   │
│  ├─ Data Validator (ranges, provinces)                           │
│  ├─ Quality Flagger                                               │
│  └─ Output: Canonical DataFrame (standardized)                   │
│                                                                   │
│  LOADING LAYER (STAGING)                                          │
│  ├─ Create Staging Schema                                        │
│  ├─ Batch Insert (SQLAlchemy)                                    │
│  └─ Output: staging.indikator_raw (SQL)                          │
│                                                                   │
│  VALIDATION LAYER                                                 │
│  ├─ Data Quality Checks                                          │
│  ├─ NULL Detection                                               │
│  ├─ Range Validation                                             │
│  └─ Output: validation_report.txt                                │
│                                                                   │
│  RECONCILIATION LAYER                                             │
│  ├─ Staging vs. Source CSV Comparison                            │
│  ├─ Row Count Verification                                       │
│  ├─ Province Completeness Check                                  │
│  └─ Output: reconciliation_report.txt [GATE]                    │
│                                                                   │
│  LOADING LAYER (DATA WAREHOUSE)                                   │
│  ├─ Create DW Schema (dimensions + facts)                        │
│  ├─ Load Dimensions (provinsi, tahun, indikator)                │
│  ├─ Load Facts (fact_indikator with FK)                          │
│  └─ Output: dw.* (normalized schema)                             │
│                                                                   │
│  AGGREGATION LAYER (DATA MART)                                    │
│  ├─ Aggregate by Province (for clustering)                       │
│  ├─ Aggregate by Province-Year (for time series)                │
│  ├─ Handle Special Cases (lagging, splits)                      │
│  └─ Output: dm.agg_province_ml, dm.agg_timeseries               │
│                                                                   │
│  ML LAYER                                                         │
│  ├─ Feature Scaling (RobustScaler, StandardScaler)              │
│  ├─ Clustering (K-Means, HDBSCAN)                               │
│  ├─ Correlation (Spearman)                                       │
│  ├─ Regression (Linear, Random Forest)                           │
│  └─ Output: ml_results.json                                      │
│                                                                   │
│  REPORTING LAYER                                                  │
│  ├─ Data Loading & Aggregation                                   │
│  ├─ Visualization Generation                                     │
│  ├─ HTML Report Creation                                         │
│  ├─ Base64 Image Embedding                                       │
│  └─ Output: ml_analysis_report_enhanced.html                     │
│                                                                   │
└─────────────────────────────────────────────────────────────────┘
```

---

## 🗄️ Database Schema

### Database: `skripsi`

#### Schema 1: STAGING (Raw Data)

**Purpose**: Temporary holding area for extracted and transformed data before validation

```sql
SCHEMA: staging

TABLE: indikator_raw
├─ id (PK, SERIAL)
├─ provinsi (VARCHAR 255, NOT NULL)
├─ tahun (INTEGER, NOT NULL)
├─ kategori (VARCHAR 255)
├─ indikator (VARCHAR 255, NOT NULL)
├─ dimensi (VARCHAR 255, NULL)
├─ nilai (NUMERIC 15,4, NULL)
├─ satuan (VARCHAR 100)
├─ is_national_aggregate (BOOLEAN, DEFAULT FALSE)
├─ sumber (VARCHAR 255)
├─ data_kualitas_flag (VARCHAR 20)  -- VALID, OUTLIER, SUSPICIOUS
├─ catatan (TEXT)
└─ created_at (TIMESTAMP, DEFAULT NOW())

INDEXES:
├─ PK: id
├─ idx_staging_provinsi (provinsi)
├─ idx_staging_tahun (tahun)
└─ idx_staging_indikator (indikator)

RECORDS: ~1,980 rows
└─ 35 provinces × 11 indicators × ~5 records/indicator (with splits)
```

**Quality Flags**:
- `VALID`: Data passed all validation checks
- `OUTLIER`: Value outside expected range (flagged, not excluded)
- `SUSPICIOUS`: Missing dimension or unusual pattern
- `NULL`: Value is missing

---

#### Schema 2: DW (Data Warehouse - Normalized Star Schema)

**Purpose**: Formal normalized data warehouse with dimensions and facts

```sql
SCHEMA: dw

┌─ DIMENSION TABLES ──────────────────────────────────────────────┐
│                                                                   │

TABLE: dim_provinsi
├─ provinsi_id (PK, INTEGER)
├─ provinsi_name (VARCHAR 255, UNIQUE)
├─ region (VARCHAR 100)  -- Java, Sumatra, etc.
├─ is_national_aggregate (BOOLEAN)
└─ created_at (TIMESTAMP)
RECORDS: 35 (34 provinces + INDONESIA)

TABLE: dim_tahun
├─ tahun_id (PK, INTEGER)
├─ tahun_value (INTEGER, UNIQUE)
└─ decade (INTEGER)
RECORDS: 5 (2020, 2021, 2022, 2023, 2024) + extras for lagging

TABLE: dim_indikator_dimensi
├─ indikator_dimensi_id (PK, INTEGER)
├─ indikator (VARCHAR 255)
├─ kategori (VARCHAR 255)
├─ dimensi (VARCHAR 255)
├─ satuan (VARCHAR 100)
├─ sumber (VARCHAR 255)
└─ created_at (TIMESTAMP)
RECORDS: ~40 (11 indicators, some with splits)

TABLE: validation_report
├─ id (PK, SERIAL)
├─ check_type (VARCHAR 255)
├─ status (VARCHAR 50)
├─ details (TEXT)
├─ row_count (INTEGER)
└─ created_at (TIMESTAMP)

│                                                                   │
└─────────────────────────────────────────────────────────────────┘

┌─ FACT TABLE ────────────────────────────────────────────────────┐
│                                                                   │

TABLE: fact_indikator (MEASURES)
├─ fact_indikator_id (PK, SERIAL)
├─ provinsi_id (FK → dim_provinsi.provinsi_id)
├─ tahun_id (FK → dim_tahun.tahun_id)
├─ indikator_dimensi_id (FK → dim_indikator_dimensi.indikator_dimensi_id)
├─ nilai (NUMERIC 15,4)  -- The actual measured value
├─ data_kualitas_flag (VARCHAR 20)
├─ catatan (TEXT)
└─ created_at (TIMESTAMP)

INDEXES:
├─ PK: fact_indikator_id
├─ FK: provinsi_id
├─ FK: tahun_id
├─ FK: indikator_dimensi_id
└─ COMPOSITE: (provinsi_id, tahun_id, indikator_dimensi_id)

RECORDS: ~1,960 rows
└─ 35 provinces × 5 years × ~11 indicators

│                                                                   │
└─────────────────────────────────────────────────────────────────┘
```

**Star Schema Diagram**:
```
              dim_provinsi
                    |
                    | FK
                    |
dim_tahun ── FK ── fact_indikator ── FK ─→ dim_indikator_dimensi
```

---

#### Schema 3: DM (Data Mart - Analytics Ready)

**Purpose**: Aggregated tables optimized for ML algorithms

```sql
SCHEMA: dm

┌─ TABLE 1: CLUSTERING DATA ─────────────────────────────────────┐
│                                                                   │

TABLE: agg_province_ml (WIDE FORMAT)
├─ provinsi_id (PK)
├─ provinsi (VARCHAR 255, UNIQUE)
│
├─ PREDICTORS (Mean & Trend %)
│  ├─ ekonomi_miskin_mean (NUMERIC)
│  ├─ ekonomi_miskin_trend_pct (NUMERIC)
│  ├─ ekonomi_upah_mean (NUMERIC)
│  ├─ ekonomi_upah_trend_pct (NUMERIC)
│  ├─ kesehatan_ahh_laki_mean (NUMERIC)
│  ├─ kesehatan_ahh_laki_trend_pct (NUMERIC)
│  ├─ kesehatan_ahh_perempuan_mean (NUMERIC)
│  ├─ kesehatan_ahh_perempuan_trend_pct (NUMERIC)
│  ├─ kesehatan_unmet_mean (NUMERIC)
│  ├─ kesehatan_unmet_trend_pct (NUMERIC)
│  ├─ ketenagakerjaan_formal_mean (NUMERIC)
│  ├─ ketenagakerjaan_formal_trend_pct (NUMERIC)
│  ├─ ketenagakerjaan_informal_mean (NUMERIC)
│  ├─ ketenagakerjaan_informal_trend_pct (NUMERIC)
│  ├─ teknologi_telepon_mean (NUMERIC)
│  ├─ teknologi_telepon_trend_pct (NUMERIC)
│  ├─ teknologi_internet_mean (NUMERIC)
│  └─ teknologi_internet_trend_pct (NUMERIC)
│
├─ TARGETS (Mean Only)
│  ├─ apm_sd_mean (NUMERIC)
│  ├─ apm_smp_mean (NUMERIC)
│  ├─ apm_sm_mean (NUMERIC)
│  ├─ apk_pt_mean (NUMERIC)
│  └─ rata_rata_lama_sekolah_mean (NUMERIC)
│
└─ METADATA
   └─ created_at (TIMESTAMP)

RECORDS: 35 rows (1 per province)
COLUMNS: ~50 (16 predictors + 5 targets + 2 metadata)

PURPOSE: Input for K-Means, HDBSCAN clustering
FORMAT: Wide format, ready for sklearn preprocessing

│                                                                   │
└─────────────────────────────────────────────────────────────────┘

┌─ TABLE 2: TIME SERIES DATA ────────────────────────────────────┐
│                                                                   │

TABLE: agg_timeseries (LONG FORMAT)
├─ id (PK, SERIAL)
├─ provinsi (VARCHAR 255)
├─ tahun (INTEGER)
│
├─ PREDICTORS (Raw Values)
│  ├─ ekonomi_miskin (NUMERIC)          -- LAGGED from 2021-2025
│  ├─ ekonomi_upah (NUMERIC)
│  ├─ kesehatan_ahh_laki (NUMERIC)
│  ├─ kesehatan_ahh_perempuan (NUMERIC)
│  ├─ kesehatan_unmet (NUMERIC)
│  ├─ ketenagakerjaan_formal (NUMERIC)
│  ├─ ketenagakerjaan_informal (NUMERIC)
│  ├─ teknologi_telepon (NUMERIC)
│  └─ teknologi_internet (NUMERIC)
│
├─ TARGETS (Raw Values)
│  ├─ apm_sd (NUMERIC)
│  ├─ apm_smp (NUMERIC)
│  ├─ apm_sm (NUMERIC)
│  ├─ apk_pt (NUMERIC)
│  └─ rata_rata_lama_sekolah (NUMERIC)
│
└─ METADATA
   └─ created_at (TIMESTAMP)

RECORDS: 175 rows (35 provinces × 5 years)
COLUMNS: 23 (9 predictors + 5 targets + 2 metadata)

PURPOSE: Input for Linear Regression, Random Forest, Spearman
FORMAT: Long format with time dimension

SPECIAL HANDLING:
├─ ekonomi_miskin LAGGED: 2020-2024 targets use 2021-2025 values
└─ Other indicators: Direct 2020-2024 values

│                                                                   │
└─────────────────────────────────────────────────────────────────┘
```

**Data Mart Philosophy**:
- Pre-aggregated and denormalized for ML
- No joins needed for ML algorithms
- Missing values explicitly handled
- Scaling applied at ML layer, not stored

---

## 🔄 Data Transformation Pipeline

### Phase 1: EXTRACTION & CLEANING

```
INPUT: CSV Files (Wide Format)
  Example: Ekonomi_upah_rata-rata.csv
  ┌─────────────────┬──────┬──────┬──────┐
  │ Provinsi        │ 2020 │ 2021 │ 2022 │
  ├─────────────────┼──────┼──────┼──────┤
  │ ACEH            │ 12.3 │ 13.1 │ 13.9 │
  │ SUMATERA UTARA  │ 14.2 │ 14.8 │ 15.5 │
  │ ...             │      │      │      │
  └─────────────────┴──────┴──────┴──────┘

TABLE-SPECIFIC CLEANERS:
├─ Standard (unpivot, rename, type)
├─ APM (split into SD/SMP/SM)
├─ AHH (split into Laki/Perempuan)
└─ Poverty (special year range)

OUTPUT: Cleaned DataFrame (Long Format)
  ┌──────────────┬──────┬────────────┬──────────┬──────┐
  │ provinsi     │ tahun│ indikator  │ kategori │ nilai│
  ├──────────────┼──────┼────────────┼──────────┼──────┤
  │ ACEH         │ 2020 │ekonomi_upah│ Ekonomi  │12.3  │
  │ ACEH         │ 2021 │ekonomi_upah│ Ekonomi  │13.1  │
  │ ACEH         │ 2022 │ekonomi_upah│ Ekonomi  │13.9  │
  │ SUMATERA...  │ 2020 │ekonomi_upah│ Ekonomi  │14.2  │
  │ ...          │      │            │          │      │
  └──────────────┴──────┴────────────┴──────────┴──────┘
```

---

### Phase 2: TRANSFORMATION

```
CANONICAL VALIDATION & FLAGGING:
├─ Province Name Check
│  ├─ Valid: In CANONICAL_PROVINCES list
│  ├─ Dropped: In DROPPED_PROVINCES (new PAPUA)
│  └─ Invalid: Filtered out with warning
│
├─ Numeric Range Check
│  ├─ Poverty: 0-100%
│  ├─ Education: 0-100%
│  ├─ Life Expectancy: 40-85 years
│  ├─ Employment: 0-100%
│  └─ Tech Access: 0-100%
│
├─ Missing Data Flag
│  ├─ Complete: No nulls → VALID
│  ├─ Partial: Some nulls → SUSPICIOUS
│  └─ All null: Excluded
│
└─ Metadata Addition
   ├─ created_at: Current timestamp
   ├─ is_national_aggregate: TRUE if provinsi == 'INDONESIA'
   ├─ data_kualitas_flag: Quality status
   └─ sumber: Data source

OUTPUT: Canonical Format DataFrame with 13 columns
  [provinsi, tahun, kategori, indikator, dimensi, nilai, satuan,
   is_national_aggregate, sumber, data_kualitas_flag, catatan, created_at]
```

---

### Phase 3: LOADING TO STAGING

```
BATCH INSERT OPERATIONS:
┌────────────────────────────────────────────┐
│ 1. Drop existing staging schema (CASCADE)  │
│ 2. Create staging schema                   │
│ 3. Create indikator_raw table              │
│ 4. Create indexes                          │
│ 5. Batch insert data (chunksize=1000)      │
│ 6. Commit transaction                      │
└────────────────────────────────────────────┘

PERFORMANCE:
├─ ~1,960 rows
├─ Batch size: 1,000
├─ Time: ~2-3 seconds
└─ Method: SQLAlchemy bulk_insert_mappings()

RESULT: staging.indikator_raw fully loaded
```

---

### Phase 4: VALIDATION

```
QUALITY CHECKS:

1. RECORD COUNTS
   ├─ Total records inserted
   ├─ Unique provinces
   ├─ Unique years
   ├─ Unique indicators
   └─ Unique categories

2. DATA COMPLETENESS
   ├─ NULL value count per column
   ├─ Empty string checks
   └─ Type validation

3. CATEGORICAL VALIDATION
   ├─ Province in canonical list
   ├─ Year in expected range
   ├─ Kategori in defined set
   └─ Dimensi valid for indicator

4. FACT TABLE INTEGRITY
   ├─ Referential integrity (FKs valid)
   ├─ No orphaned dimensions
   └─ Dimension row counts

OUTPUT: validation_report.txt with summary
```

---

### Phase 5: RECONCILIATION (GATE)

```
RECONCILIATION PROCESS:

1. READ SOURCE CSVs
   ├─ Parse each CSV file
   ├─ Extract provinces per CSV
   ├─ Extract years per CSV
   └─ Count expected rows

2. READ STAGING DATA
   ├─ Query staging.indikator_raw
   ├─ Group by (provinsi, tahun, indikator)
   └─ Count actual rows

3. COMPARE
   ├─ For each province-year-indicator
   │  ├─ Expected count vs. actual count
   │  ├─ If difference > TOLERANCE → FAIL
   │  └─ Track mismatches
   │
   └─ Overall: All provinces present?

4. DECISION GATE
   ├─ IF all checks pass → PROCEED to DW
   ├─ IF any check fails AND !force-dw-load → STOP
   └─ IF any check fails AND force-dw-load → PROCEED (risky)

OUTPUT: reconciliation_report.txt
```

---

### Phase 6: DATA WAREHOUSE LOAD

```
DIMENSIONAL MODEL CREATION:

1. CREATE DIM_PROVINSI (35 rows)
   ├─ PK: provinsi_id
   └─ Values: From distinct staging.provinsi

2. CREATE DIM_TAHUN (6 rows, includes extras for lagging)
   ├─ PK: tahun_id
   └─ Values: 2020-2025 (includes 2025 for lagged poverty)

3. CREATE DIM_INDIKATOR_DIMENSI (~40 rows)
   ├─ PK: indikator_dimensi_id
   ├─ From: Unique (indikator, dimensi) combinations
   └─ With: Kategori, satuan, sumber metadata

4. CREATE FACT_INDIKATOR (~1,960 rows)
   ├─ PK: fact_indikator_id
   ├─ FK: provinsi_id → dim_provinsi
   ├─ FK: tahun_id → dim_tahun
   ├─ FK: indikator_dimensi_id → dim_indikator_dimensi
   ├─ Measure: nilai (numeric value)
   └─ Quality: data_kualitas_flag

CONSTRAINTS:
├─ Primary Keys
├─ Foreign Keys (with CASCADE)
├─ NOT NULL constraints
├─ Composite indexes for query performance
└─ Check constraints on value ranges
```

---

### Phase 7: AGGREGATION (DATA MART)

```
AGGREGATION LOGIC:

TABLE 1: agg_province_ml (Province-Level)
┌─────────────────────────────────────────────┐
│ For each province:                          │
│ 1. Calculate mean (average across years)    │
│ 2. Calculate trend % (last - first) / first │
│ 3. For each of 8 indicators × 2 metrics    │
│                                             │
│ SPECIAL CASES:                              │
│ ├─ AHH: Only use Perempuan (female) data   │
│ ├─ APM: Keep separate (SD/SMP/SM)          │
│ └─ Poverty: Lagged (2021-2025 for lagging) │
└─────────────────────────────────────────────┘

TABLE 2: agg_timeseries (Province-Year-Level)
┌─────────────────────────────────────────────┐
│ For each province-year combination:         │
│ 1. Pull all predictor values (raw)          │
│ 2. Pull all target values (raw)             │
│ 3. Handle lagging for poverty               │
│ 4. Row = (provinsi, tahun, pred1...9,      │
│    target1...5, created_at)                 │
│                                             │
│ LAGGING DETAILS:                            │
│ ├─ 2020 row: poverty = 2021 value          │
│ ├─ 2021 row: poverty = 2022 value          │
│ ├─ 2022 row: poverty = 2023 value          │
│ ├─ 2023 row: poverty = 2024 value          │
│ └─ 2024 row: poverty = 2025 value          │
└─────────────────────────────────────────────┘

OUTPUT:
├─ dm.agg_province_ml: 35 × 50 columns
└─ dm.agg_timeseries: 175 × 23 columns
```

---

## 🤖 ML Pipeline Data Flow

### Feature Engineering

```
INPUT: dm.agg_province_ml (35 provinces × 50 columns)

1. FEATURE SELECTION
   Predictors (16 features):
   ├─ ekonomi_miskin_mean, ekonomi_miskin_trend_pct
   ├─ ekonomi_upah_mean, ekonomi_upah_trend_pct
   ├─ kesehatan_ahh_laki_mean, kesehatan_ahh_laki_trend_pct
   ├─ kesehatan_ahh_perempuan_mean, kesehatan_ahh_perempuan_trend_pct
   ├─ kesehatan_unmet_mean, kesehatan_unmet_trend_pct
   ├─ ketenagakerjaan_formal_mean, ketenagakerjaan_formal_trend_pct
   ├─ ketenagakerjaan_informal_mean, ketenagakerjaan_informal_trend_pct
   ├─ teknologi_telepon_mean, teknologi_telepon_trend_pct
   └─ teknologi_internet_mean, teknologi_internet_trend_pct

   Targets (5 features):
   ├─ apm_sd_mean
   ├─ apm_smp_mean
   ├─ apm_sm_mean
   ├─ apk_pt_mean
   └─ rata_rata_lama_sekolah_mean

2. MISSING VALUE HANDLING
   ├─ Forward fill strategy
   ├─ OR drop if excessive
   └─ Document imputation

3. SCALING / NORMALIZATION
   FOR CLUSTERING:
   └─ RobustScaler (resistant to outliers)

   FOR REGRESSION:
   ├─ StandardScaler (zero mean, unit variance)
   └─ Applied separately to X and y

4. OUTPUT
   └─ Scaled feature matrix (35 × 16)
   └─ Unscaled target matrix (35 × 5)
```

### Clustering Models

```
MODEL 1: K-MEANS CLUSTERING
├─ Algorithm: Lloyd's algorithm
├─ Input: 35 provinces × 16 scaled predictors
├─ Config: n_clusters=4, random_state=42, n_init=10
├─ Metrics:
│  ├─ Silhouette Score: [-1, 1] (higher better)
│  ├─ Inertia: Within-cluster sum of squares
│  └─ Davies-Bouldin Index: Cluster separation
└─ Output: Cluster assignments (0-3), one per province

MODEL 2: HDBSCAN CLUSTERING
├─ Algorithm: Density-based hierarchical
├─ Input: 35 provinces × 16 scaled predictors
├─ Config: min_cluster_size=3, min_samples=2
├─ Auto-detects: Number of clusters
├─ Advantages: 
│  ├─ No need to specify n_clusters
│  ├─ Identifies noise points (-1 label)
│  └─ More robust to outliers
└─ Output: Cluster assignments, including noise

INTERPRETATION:
├─ Clusters = groups of similar provinces
├─ K-Means: Optimizes within-cluster cohesion
├─ HDBSCAN: Preserves density structure
└─ Compare both for robustness
```

### Regression Models

```
INPUT: dm.agg_timeseries (175 rows × 23 columns)
├─ 35 provinces × 5 years
├─ 9 predictors (lagged poverty included)
└─ 5 targets (education metrics)

FOR EACH TARGET (5 separate models):
├─ apm_sd
├─ apm_smp
├─ apm_sm
├─ apk_pt
└─ rata_rata_lama_sekolah

MODEL 1: LINEAR REGRESSION
├─ Equation: y = β₀ + β₁x₁ + β₂x₂ + ... + βₙxₙ
├─ Method: Ordinary Least Squares (OLS)
├─ Metrics:
│  ├─ R² Score: Proportion of variance explained [0, 1]
│  ├─ MAE: Mean Absolute Error (average prediction error)
│  ├─ RMSE: Root Mean Squared Error
│  └─ Coefficients: Importance & direction of each predictor
└─ Interpretation: Linear relationships, interpretable

MODEL 2: RANDOM FOREST REGRESSION
├─ Ensemble: 100 decision trees
├─ Method: Bootstrap + feature subset sampling
├─ Metrics:
│  ├─ R² Score: Model fit
│  ├─ MAE: Prediction error
│  ├─ Feature Importance: Relative importance scores
│  └─ RMSE: Squared error metric
├─ Advantages:
│  ├─ Handles non-linear relationships
│  ├─ Captures interactions
│  └─ Robust to outliers
└─ Interpretation: Non-parametric, feature importance

MODEL 3: SPEARMAN CORRELATION
├─ Method: Rank-based correlation
├─ Input: All province-year combinations
├─ Output: Correlation matrix (9 × 5 = 45 correlations)
├─ Metrics:
│  ├─ Correlation coefficient: [-1, 1]
│  └─ P-value: Statistical significance
├─ Advantages:
│  ├─ Non-parametric
│  ├─ Monotonic relationships
│  └─ Robust to outliers & non-normality
└─ Visualization: Heatmap of all correlations
```

---

## 📊 Reporting Architecture

### Report Generation Pipeline

```
INPUT: ml_results.json (from ML pipeline)
       dm.agg_timeseries (from database)

PROCESSING STEPS:

1. DATA AGGREGATION
   ├─ Load ML results from JSON
   ├─ Load aggregated data from database
   ├─ Reshape for visualization
   └─ Compute correlation matrices

2. VISUALIZATION GENERATION
   ├─ Correlation Heatmap (seaborn)
   │  ├─ 9 predictors × 5 targets matrix
   │  ├─ Color scale: Blue (negative) → White → Red (positive)
   │  └─ Save as PNG buffer
   │
   ├─ K-Means Cluster Plot (matplotlib PCA)
   │  ├─ 2D projection of clusters
   │  ├─ 35 province points colored by cluster
   │  └─ Save as PNG buffer
   │
   ├─ Linear Regression Plots (5 individual)
   │  ├─ For each target: Actual vs Predicted scatter
   │  ├─ Add trend line
   │  ├─ Include R² score
   │  └─ Save as PNG buffer
   │
   └─ Random Forest Plots (5 individual)
       ├─ For each target: Actual vs Predicted scatter
       ├─ Feature importance bar chart
       └─ Save as PNG buffer

3. HTML GENERATION
   ├─ Template sections:
   │  ├─ Title & metadata
   │  ├─ Summary statistics
   │  ├─ Correlation heatmap
   │  ├─ Cluster analysis
   │  ├─ Linear regression results (5 targets)
   │  ├─ Random forest results (5 targets)
   │  ├─ Spearman correlation table
   │  ├─ Data normalization documentation
   │  └─ Footer with timestamp
   │
   ├─ Styling:
   │  ├─ CSS embedded
   │  ├─ Times New Roman font (academic)
   │  ├─ Professional table styling
   │  └─ Responsive layout
   │
   └─ Image Embedding:
       ├─ PNG buffers → Base64 encoding
       ├─ Embedded as data URLs
       ├─ No external image files needed
       └─ Standalone HTML file

OUTPUT: ml_analysis_report_enhanced.html (single file)
└─ All data, styling, images embedded
└─ Can be opened in any browser offline
```

---

## 🔒 Data Quality & Reconciliation

### Validation Strategy

```
LAYER 1: EXTRACTION VALIDATION
├─ Check file exists
├─ Parse CSV without errors
├─ Ensure expected columns present
└─ Type inference correct

LAYER 2: TRANSFORMATION VALIDATION
├─ Province names in canonical list
├─ Numeric values within valid ranges
├─ Dimensions correct (gender splits, education levels)
└─ No unexpected nulls (flagged as suspicious)

LAYER 3: STAGING VALIDATION
├─ Referential integrity in DW
├─ Primary key uniqueness
├─ Foreign key references valid
└─ Check constraints pass

LAYER 4: RECONCILIATION (GATE)
├─ Staging vs. source row counts match
├─ All provinces represented
├─ Year ranges correct
└─ Dimension splits complete

LAYER 5: AGGREGATION VALIDATION
├─ Agg table row counts correct
├─ Aggregation calculations valid (mean, trend)
└─ No data loss in aggregation
```

### Error Handling

```
EXTRACTION ERRORS:
├─ CSV not found → FileNotFoundError (STOP)
├─ Parse error → ValueError (STOP)
└─ Missing column → KeyError (STOP)

TRANSFORMATION ERRORS:
├─ Invalid province → WARNING (flag, continue)
├─ Value out of range → WARNING (flag, continue)
├─ NULL values → WARNING (flag, continue)
└─ Invalid dimension → WARNING (log, continue)

VALIDATION ERRORS:
├─ Type mismatch → ERROR (STOP)
├─ Constraint violation → ERROR (STOP)
├─ Referential integrity → ERROR (STOP)
└─ Missing dimensions → WARNING (log, report)

RECONCILIATION ERRORS:
├─ Row count mismatch → ERROR (GATE CLOSES)
├─ Province missing → ERROR (GATE CLOSES)
├─ Year range wrong → ERROR (GATE CLOSES)
└─ Dimension splits wrong → ERROR (GATE CLOSES)

GATE OVERRIDE:
├─ --force-dw-load flag → PROCEED despite errors
├─ Log warnings about data quality
└─ Proceed at operator's risk
```

---

## 🛠️ Key Implementation Details

### Lagging Implementation

```python
# Pseudocode for lagging logic
for each province:
    for target_year in [2020, 2021, 2022, 2023, 2024]:
        # Poverty data is available from 2021-2025
        # So 2020 targets use 2021 poverty (one year ahead)
        poverty_value = get_value(province, target_year + 1, 'ekonomi_miskin')
        
        # Other indicators: same year
        other_values = get_values(province, target_year, [other_indicators])
        
        # Create row for time series
        ts_row = {
            'provinsi': province,
            'tahun': target_year,
            'ekonomi_miskin': poverty_value,  # LAGGED
            'ekonomi_upah': other_values['ekonomi_upah'],  # NOT lagged
            ...
        }
```

### Batch Insert Performance

```python
# Using SQLAlchemy for batch inserts
records = [
    {'provinsi': 'ACEH', 'tahun': 2020, 'indikator': 'ekonomi_upah', 'nilai': 12.3, ...},
    {'provinsi': 'ACEH', 'tahun': 2021, 'indikator': 'ekonomi_upah', 'nilai': 13.1, ...},
    ...
]

engine.execute(
    staging.indikator_raw.insert(),
    records
)

# Performance: ~1,000 records per batch
# Time: ~2-3 seconds for 1,960 records total
```

### Scaling Strategy

```python
# For clustering: RobustScaler (uses median/IQR)
from sklearn.preprocessing import RobustScaler
scaler = RobustScaler()
X_scaled = scaler.fit_transform(X)  # Handle outliers better

# For regression: StandardScaler (zero mean, unit var)
from sklearn.preprocessing import StandardScaler
scaler = StandardScaler()
X_scaled = scaler.fit_transform(X)
y_scaled = scaler.fit_transform(y.reshape(-1, 1))
```

---

## 📈 Query Patterns

### Common Analytical Queries

```sql
-- Get data for specific province
SELECT * FROM dw.fact_indikator f
JOIN dw.dim_provinsi p ON f.provinsi_id = p.provinsi_id
WHERE p.provinsi_name = 'JAWA BARAT'
ORDER BY f.tahun_id;

-- Aggregate by year
SELECT tahun, AVG(nilai) as avg_value
FROM dw.fact_indikator f
JOIN dw.dim_tahun t ON f.tahun_id = t.tahun_id
GROUP BY tahun
ORDER BY tahun;

-- Find provinces with specific indicator
SELECT DISTINCT p.provinsi_name
FROM dw.fact_indikator f
JOIN dw.dim_provinsi p ON f.provinsi_id = p.provinsi_id
WHERE f.indikator_dimensi_id = (SELECT indikator_dimensi_id FROM dw.dim_indikator_dimensi WHERE indikator = 'ekonomi_miskin')
AND f.nilai > 15;
```

---

**Last Updated**: 2026-04-28  
**Architecture Version**: 1.0  
**Database**: PostgreSQL 12+
