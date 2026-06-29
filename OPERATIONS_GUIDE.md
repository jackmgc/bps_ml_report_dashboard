# Operations & Quick Start Guide

## 🚀 Quick Start (5 Minutes)

### Minimal Setup
```bash
# 1. Install dependencies (one time)
pip install -r requirements.txt

# 2. Create .env with database credentials
# Create file: .env
PSQL_HOST=localhost
PSQL_PORT=5432
PSQL_USER=postgres
PSQL_PASSWORD=your_password
PSQL_DBNAME=skripsi

# 3. Verify PostgreSQL is running and database exists
psql -U postgres -d skripsi -c "SELECT version();"

# 4. Run the pipeline
python main.py --phase all

# 5. Check report
# Open: reports/ml_analysis_report_enhanced.html
```

---

## 📋 Common Tasks

### Task 1: Run Complete Pipeline (Full ETL + ML + Report)
```bash
python main.py --phase all
```
**What happens**:
- Extracts and cleans all CSV files
- Transforms data to canonical format
- Loads to staging schema
- Validates data quality
- Reconciles with source CSVs
- Creates data warehouse
- Creates data mart aggregations
- Runs ML models (clustering, regression)
- Generates HTML report with visualizations

**Expected output**:
```
reports/ml_analysis_report_enhanced.html
reports/ml_results.json
reports/etl.log
reports/validation_report.txt
reports/reconciliation_report.txt
```

---

### Task 2: Run ETL Only (No ML)
```bash
python main.py --phase validate
```
**What happens**:
- Extracts and cleans CSVs
- Transforms to canonical format
- Loads to staging
- Validates quality
- Reconciles with source

**Use case**: Verify data integrity before running ML

---

### Task 3: Run ML Pipeline Only
```bash
python main.py --phase ml-pipeline
```
**What happens**:
- Reads aggregated data from data mart
- Runs K-Means and HDBSCAN clustering
- Calculates Spearman correlations
- Fits Linear Regression models
- Trains Random Forest ensemble
- Saves results to ml_results.json

**Use case**: Re-run ML with different parameters (modify ml_config.json first)

---

### Task 4: Generate Report Only
```bash
python main.py --phase ml-report
```
**What happens**:
- Reads ml_results.json
- Creates visualizations (heatmaps, plots, clusters)
- Generates enhanced HTML report
- Embeds all images in HTML

**Use case**: Regenerate report with different styling or if report was deleted

---

### Task 5: Force DW Load Despite Reconciliation Failures
```bash
python main.py --phase all --force-dw-load
```
**What happens**:
- Same as normal pipeline, BUT
- Skips reconciliation failure gate
- Forces Data Warehouse load even if reconciliation has issues

**Use case**: Development/testing when you know reconciliation will fail
**⚠️ Warning**: Only use if you understand the data quality implications

---

### Task 6: Run Up to Aggregation Only
```bash
python main.py --phase aggregation
```
**What happens**:
- Extracts and cleans CSVs
- Transforms to canonical format
- Loads to staging
- Validates quality
- Reconciles with source
- Creates DW
- Creates data mart aggregations (STOPS HERE)

**Use case**: Prepare aggregated tables without running ML

---

### Task 7: Export Aggregated Data to CSV
```bash
python export_aggregations.py
```
**What happens**:
- Exports province-level aggregated data
- Exports province-year time series data

**Output files**:
```
data/ml_clustering_aggregated.csv        # 35 provinces × ~50 columns
data/ml_timeseries_province_year.csv     # 175 rows × 23 columns
```

**Use case**: 
- External analysis in Excel, R, or other tools
- Manual data verification
- Sharing cleaned data with colleagues

---

### Task 8: View Pipeline Logs
```bash
# View logs in terminal (last 50 lines)
tail -50 reports/etl.log

# View all logs
type reports/etl.log  # Windows
cat reports/etl.log   # macOS/Linux

# Search logs for errors
find reports/etl.log -type f -exec grep -l ERROR {} \;
```

---

### Task 9: Modify ML Model Parameters
```bash
# 1. Edit config/ml_config.json
notepad config/ml_config.json  # Windows
nano config/ml_config.json     # macOS/Linux

# Example: Change K-Means clusters from 4 to 5
{
  "kmeans": {
    "n_clusters": 5,  # <-- Change this
    "random_state": 42,
    "n_init": 10
  }
}

# 2. Re-run ML pipeline
python main.py --phase ml-pipeline

# 3. Regenerate report
python main.py --phase ml-report
```

---

### Task 10: Run Standalone ML (Legacy Mode)
```bash
python results.py
```
**What happens**:
- Loads aggregated data from database
- Runs ML pipeline
- Generates HTML report

**Note**: This is older approach - use `main.py --phase ml-pipeline` instead for new work

---

## 🔍 Debugging & Troubleshooting

### Problem: "PSQL_USER not configured in .env file"

**Solution 1: Create .env file**
```bash
# Windows: Create text file
notepad .env

# Add these lines:
PSQL_HOST=localhost
PSQL_PORT=5432
PSQL_USER=postgres
PSQL_PASSWORD=mypassword
PSQL_DBNAME=skripsi
DATA_FOLDER=./data
REPORTS_FOLDER=./reports
LOG_LEVEL=INFO
RECONCILIATION_TOLERANCE=0.0001
```

**Solution 2: Verify .env location**
```bash
# .env must be in project root, same directory as main.py
# Verify it exists:
ls -la .env  # macOS/Linux
dir .env    # Windows
```

---

### Problem: "Connection refused" to PostgreSQL

**Check 1: Is PostgreSQL running?**
```bash
# Windows
# Check Services or use:
psql --version

# macOS
# Check if server running:
pg_isready -h localhost -p 5432

# Linux
systemctl status postgresql
```

**Check 2: Correct host/port?**
```bash
# Verify connection manually
psql -h localhost -U postgres -d skripsi -c "SELECT 1"

# If this works, update .env with correct values
```

**Check 3: Password correct?**
```bash
# If password has special characters, URL-encode it
# Example: password is "p@ss%word"
# In .env use: PSQL_PASSWORD=p%40ss%25word
```

---

### Problem: "CSV file not found"

**Check 1: Files exist in data/ folder?**
```bash
# List CSV files
dir data\*.csv         # Windows
ls -la data/*.csv      # macOS/Linux
```

**Check 2: Exact filenames match?**
```
Expected:
- Ekonomi_persentase_penduduk_miskin.csv
- Ekonomi_upah_rata-rata.csv
- Kesehatan_angka_harapan_hidup.csv
- Kesehatan_unmet_layanan_kesehatan.csv
- Ketenagakerjaan_formal.csv
- Ketenagakerjaan_informal.csv
- Pendidikan_APK_PT_provinsi.csv
- Pendidikan_APM_provinsi.csv
- Pendidikan_Rata-rata_lama_sekolah.csv
- Teknologi_memiliki_telepon_seluler.csv
- Teknologi_mengakses_internet.csv
```

**Check 3: Update DATA_FOLDER if needed**
```bash
# In .env, verify data folder path
DATA_FOLDER=./data
# or absolute path:
DATA_FOLDER=f:\BINUS\SEMS 8\code-program\data
```

---

### Problem: "Reconciliation failed - staging vs source row counts"

**Cause**: Missing provinces or data in CSVs

**Solution 1: Check reconciliation report**
```bash
type reports/reconciliation_report.txt  # Windows
cat reports/reconciliation_report.txt   # macOS/Linux

# This shows which provinces/years have mismatches
```

**Solution 2: Force load (if acceptable)**
```bash
python main.py --phase all --force-dw-load
```

**Solution 3: Fix source CSV**
- Open CSV file and verify completeness
- Check for missing provinces or years
- Ensure no extra header/footer rows

---

### Problem: "OutOfMemory" error

**For small datasets, this shouldn't happen. If it does:**

**Solution 1: Process in chunks**
```bash
# Edit etl/loader_python.py
# Reduce batch size:
BATCH_SIZE = 500  # was 1000

# Then re-run:
python main.py --phase all --force-dw-load
```

**Solution 2: Check for infinite loops**
```bash
# View logs for what's consuming memory
tail -100 reports/etl.log | grep -i "memory\|warning"
```

---

### Problem: "No module named 'xxx'"

**Solution: Install missing package**
```bash
# Verify venv is activated
# Windows: venv\Scripts\activate
# macOS/Linux: source venv/bin/activate

# Re-install dependencies
pip install -r requirements.txt

# Or install specific package
pip install pandas scikit-learn
```

---

### Problem: Duplicate data after re-running

**Cause**: Staging/DW tables not cleared

**Solution**: Pipeline auto-clears with DROP SCHEMA IF EXISTS
- First time: Slow (creates everything)
- Subsequent runs: Clears and reloads (normal)

**Manual clear if needed**:
```bash
# In PostgreSQL:
DROP SCHEMA staging CASCADE;
DROP SCHEMA dw CASCADE;
DROP SCHEMA dm CASCADE;

# Then re-run pipeline
python main.py --phase all
```

---

## 📊 Interpreting Results

### Reading ml_analysis_report_enhanced.html

**1. Correlation Heatmap**
- Shows relationships between predictors and targets
- Red = positive correlation, Blue = negative
- Darker = stronger relationship

**2. K-Means Clusters**
- Groups provinces into clusters
- Each province assigned a cluster ID
- Similar provinces grouped together

**3. Linear Regression Results**
- Coefficients show strength of relationship (positive/negative)
- R² shows model fit (closer to 1 = better)
- MAE shows average prediction error

**4. Random Forest Results**
- Feature importance shows which predictors matter most
- R² shows non-linear model fit
- Captures complex relationships

**5. Data Quality Summary**
- Shows how data was normalized and scaled
- Lists any data issues found
- Validates year ranges and province coverage

---

### Reading ml_results.json

**Structure**:
```json
{
  "kmeans": {
    "cluster_assignments": {...},
    "silhouette_score": 0.45,
    "inertia": 123.45
  },
  "hdbscan": {
    "cluster_assignments": {...},
    "n_clusters": 3
  },
  "linear_regression": {
    "target_1": {
      "coefficients": [...],
      "r2_score": 0.78,
      "mae": 5.23
    }
  },
  "random_forest": {...},
  "spearman_correlation": {...}
}
```

---

## 📈 Performance & Optimization

### Execution Times (Typical)
```
Extract & Clean:        1-2 seconds
Transform:              1-2 seconds
Load to Staging:        2-3 seconds
Validate:               1-2 seconds
Reconcile:              1-2 seconds
Create DW:              1-2 seconds
Create Data Mart:       1-2 seconds
ML Pipeline:            3-5 seconds
Report Generation:      2-3 seconds
────────────────────────────────
TOTAL:                  15-25 seconds
```

### Optimization Tips

1. **First Run**: Slower (creates schema, indexes)
2. **Subsequent Runs**: Faster (reuses schema)
3. **Database Performance**: Ensure sufficient RAM for PostgreSQL
4. **Batch Processing**: Currently processes all data in memory (OK for this size)

---

## 🔄 Workflow Examples

### Example 1: Daily Refresh
```bash
# Morning: Run full pipeline with latest data
python main.py --phase all

# Check output
type reports/ml_analysis_report_enhanced.html

# Export for sharing
python export_aggregations.py

# Archive results
# Copy reports folder to backup location
```

### Example 2: ML Experimentation
```bash
# 1. Try different cluster counts
# Edit config/ml_config.json:
# "n_clusters": 3 (try 3, 4, 5, 6)

# 2. Re-run ML and check report
python main.py --phase ml-pipeline
python main.py --phase ml-report

# 3. Compare results in HTML report
# Open in browser: reports/ml_analysis_report_enhanced.html

# 4. Keep best result, move to production
```

### Example 3: Data Quality Issue
```bash
# 1. Identify issue
python main.py --phase validate
type reports/validation_report.txt

# 2. Fix in source CSV
# Edit data/XXX.csv (fix missing values, etc.)

# 3. Re-run ETL
python main.py --phase all

# 4. Verify results
python export_aggregations.py
```

### Example 4: Share Aggregated Data
```bash
# 1. Ensure data is aggregated
python main.py --phase aggregation

# 2. Export to CSV
python export_aggregations.py

# 3. Share files
# Send these files to colleagues:
# - data/ml_clustering_aggregated.csv
# - data/ml_timeseries_province_year.csv

# They can open in Excel, R, Python for analysis
```

---

## 🎯 Phase Details & Decisions

### When to use `--phase validate` (ETL only)?
- ✓ Testing data extraction
- ✓ Verifying data quality
- ✓ Debugging CSV issues
- ✓ Not ready for ML yet

### When to use `--phase ml-pipeline` (ML only)?
- ✓ Tuning model parameters
- ✓ Re-running with different configs
- ✓ Data unchanged, only ML changed
- ✓ Fast experimentation

### When to use `--phase all` (Full pipeline)?
- ✓ New data ingestion
- ✓ Production refresh
- ✓ Everything from scratch
- ✓ Ensure consistency

### When to use `--force-dw-load`?
- ✓ Development/testing only
- ⚠️ When reconciliation fails but you accept the risk
- ⚠️ Not for production without investigation

---

## 🚨 Important Notes

### Data Freshness
- Pipeline can be re-run anytime
- Each run clears and reloads all data
- Old data not retained (no historical versions stored)

### Database Size
- Current data: ~10-50 MB (small)
- Schemas: staging, dw, dm (~5-10 MB each)
- Easy to backup/restore

### PostgreSQL Requirements
- UTF-8 encoding (required)
- Public schema readable
- No connection pooling needed for this size

### Reproducibility
- All ML models use random_state for reproducibility
- Same input data → same output always
- Config file controls randomness

---

## 📚 Additional Resources

### View Database Directly
```bash
# Connect to database
psql -h localhost -U postgres -d skripsi

# Explore schema
\dt staging.*        # Staging tables
\dt dw.*             # Data warehouse tables
\dt dm.*             # Data mart tables

# Count records
SELECT COUNT(*) FROM staging.indikator_raw;
SELECT COUNT(*) FROM dw.fact_indikator;

# Sample data
SELECT * FROM dm.agg_province_ml LIMIT 5;
```

### Python Console Access
```bash
# Start Python interpreter
python

# Import and explore
from etl.ml_pipeline import MLPipeline
pipe = MLPipeline()
pipe.load_data()
print(pipe.clustering_df.shape)
print(pipe.clustering_df.head())
```

---

## 🆘 Getting Help

### Check Logs First
```bash
# Full execution log
type reports/etl.log

# Filter for errors
type reports/etl.log | find "ERROR"

# Recent entries only
tail -50 reports/etl.log
```

### Verify Setup
```bash
# 1. Check environment
python --version
pip list | grep -E "pandas|scikit-learn|psycopg2"

# 2. Check database
psql -U postgres -d skripsi -c "SELECT COUNT(*) FROM staging.indikator_raw;"

# 3. Check files
dir data\*.csv
dir reports\
```

### Common Error Messages

| Error | Cause | Solution |
|-------|-------|----------|
| `ModuleNotFoundError: No module named 'X'` | Missing package | `pip install -r requirements.txt` |
| `psycopg2.OperationalError: connection refused` | PostgreSQL not running | Start PostgreSQL server |
| `FileNotFoundError: CSV file not found` | Wrong path or filename | Check `data/` folder, verify names |
| `ValueError: PSQL_USER not configured` | Missing `.env` file | Create `.env` with credentials |
| `IntegrityError: duplicate key value` | Duplicate data after re-run | Normal - pipeline clears data first |

---

**Last Updated**: 2026-04-28  
**Project**: Indonesian Regional Indicators ETL+ML Pipeline
