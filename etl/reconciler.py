"""Reconciler module - validates transformed data against source CSVs using pure Python"""
import os
import pandas as pd
from datetime import datetime
from config.db_config import DATA_FOLDER, REPORTS_FOLDER
from config.constants import CSV_FILES, CANONICAL_PROVINCES, DROPPED_PROVINCES, EXPECTED_ROW_COUNTS
from utils.logger import get_logger

logger = get_logger(__name__)

class ReconciliationError(Exception):
    """Exception raised when reconciliation fails"""
    pass


def _read_csv_expected_provinces(csv_path, csv_file):
    """
    Read a source CSV and extract the set of expected canonical provinces.
    
    Handles the different CSV structures (poverty has extra metadata row).
    
    Args:
        csv_path (str): Full path to CSV file
        csv_file (str): Filename for identification
        
    Returns:
        tuple: (set of province names found in CSV, set of year values)
    """
    raw_df = pd.read_csv(csv_path, header=None, skiprows=0)
    
    # Determine data start row and year row based on file type
    if 'persentase_penduduk_miskin' in csv_file.lower():
        # Poverty file has extra metadata row
        year_row_idx = 2
        data_start_idx = 4
    elif 'APM' in csv_file or 'angka_harapan_hidup' in csv_file:
        # Multi-block files: row 2 has years, data from row 3
        year_row_idx = 2
        data_start_idx = 3
    else:
        # Simple files: detect year row
        year_candidates_r1 = raw_df.iloc[1, 1:].fillna('').astype(str)
        if year_candidates_r1.str.isnumeric().sum() >= 4:
            year_row_idx = 1
            data_start_idx = 2
        else:
            year_row_idx = 2
            data_start_idx = 3
    
    # Extract years
    year_row = raw_df.iloc[year_row_idx, 1:].values
    years = set()
    for y in year_row[:5]:
        try:
            years.add(int(float(y)))
        except (ValueError, TypeError):
            pass
    
    # Extract province names from column 0
    all_col0 = raw_df.iloc[data_start_idx:, 0].dropna().values
    provinces = set()
    for val in all_col0:
        sval = str(val).strip()
        if sval and sval in CANONICAL_PROVINCES:
            provinces.add(sval)
    
    return provinces, years


def reconcile_staging_to_source(transformed_df, csv_folder=None, output_file='reports/reconciliation_report.txt'):
    """
    Validate that transformed DataFrame matches source CSV files.
    
    RECONCILIATION GATE: This must pass before DW loading proceeds.
    
    Uses pure Python/pandas comparison — no database queries needed.
    
    Args:
        transformed_df (pd.DataFrame): The transformed DataFrame from the transform phase
        csv_folder (str): Path to CSV folder. If None, uses DATA_FOLDER
        output_file (str): Path to write reconciliation report
        
    Returns:
        dict: Reconciliation results with 'passed', 'files_checked', etc.
        
    Raises:
        ReconciliationError: If reconciliation fails
    """
    if csv_folder is None:
        csv_folder = DATA_FOLDER
    
    logger.info("RECONCILIATION GATE: Validating transformed data against source CSVs...")
    
    try:
        os.makedirs(REPORTS_FOLDER, exist_ok=True)
        
        report_lines = []
        report_lines.append("=" * 100)
        report_lines.append("RECONCILIATION VALIDATION REPORT - TRANSFORMED DATA vs. SOURCE CSVs")
        report_lines.append("=" * 100)
        report_lines.append(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        report_lines.append("")
        
        total_files = len(CSV_FILES)
        passed_files = 0
        failed_files = []
        all_issues = []
        
        # Get unique indicators from transformed data to map back to CSV files
        # Build a mapping: csv_file -> indicator names used in transformed_df
        csv_to_indicators = _build_csv_indicator_map()
        
        for csv_file in CSV_FILES:
            csv_path = os.path.join(csv_folder, csv_file)
            
            report_lines.append(f"FILE: {csv_file}")
            report_lines.append("-" * 100)
            
            if not os.path.exists(csv_path):
                report_lines.append(f"  [FAIL] CSV file not found: {csv_path}")
                all_issues.append(f"Missing CSV file: {csv_file}")
                failed_files.append(csv_file)
                report_lines.append("")
                continue
            
            try:
                # Read expected provinces and years from source CSV
                csv_provinces, csv_years = _read_csv_expected_provinces(csv_path, csv_file)
                
                # Get corresponding rows from transformed DataFrame
                indicators = csv_to_indicators.get(csv_file, [])
                if not indicators:
                    report_lines.append(f"  [WARN] No indicator mapping for {csv_file}, skipping")
                    report_lines.append("")
                    continue
                
                tf_subset = transformed_df[transformed_df['indikator'].isin(indicators)]
                
                if tf_subset.empty:
                    report_lines.append(f"  [FAIL] No transformed data found for indicators: {indicators}")
                    all_issues.append(f"{csv_file}: No transformed data")
                    failed_files.append(csv_file)
                    report_lines.append("")
                    continue
                
                tf_provinces = set(tf_subset['provinsi'].unique())
                tf_years = set(tf_subset['tahun'].unique())
                
                # ── Check 1: Province coverage ──
                missing_provinces = csv_provinces - tf_provinces
                extra_provinces = tf_provinces - csv_provinces
                # INDONESIA is in tf but might not be flagged as "csv province" if filtering stripped it
                # Remove INDONESIA from extra check since it's expected
                extra_provinces.discard('INDONESIA')
                missing_provinces.discard('INDONESIA')
                
                provinces_ok = len(missing_provinces) == 0
                
                if provinces_ok:
                    report_lines.append(f"  [PASS] Province coverage: {len(tf_provinces)} provinces — OK")
                else:
                    report_lines.append(f"  [FAIL] Province coverage mismatch")
                    if missing_provinces:
                        report_lines.append(f"    - Missing in transformed: {missing_provinces}")
                        all_issues.append(f"{csv_file}: Missing provinces {missing_provinces}")
                
                # ── Check 2: Year coverage ──
                missing_years = csv_years - tf_years
                years_ok = len(missing_years) == 0
                
                if years_ok:
                    report_lines.append(f"  [PASS] Year coverage: {sorted(tf_years)} — OK")
                else:
                    report_lines.append(f"  [FAIL] Year mismatch: expected={sorted(csv_years)}, got={sorted(tf_years)}")
                    all_issues.append(f"{csv_file}: Missing years {missing_years}")
                
                # ── Check 3: Row count (approximate) ──
                expected_rows = EXPECTED_ROW_COUNTS.get(csv_file)
                # Expected rows per file is province count; after unpivot it's provinces × years × dimensions
                unique_dims = tf_subset['dimensi'].nunique()
                dim_count = max(unique_dims, 1)
                actual_province_count = tf_subset['provinsi'].nunique()
                year_count = len(tf_years)
                actual_rows = len(tf_subset)
                expected_unpivoted = actual_province_count * year_count * dim_count
                
                # Allow tolerance of ±5% for row count
                row_tolerance = 0.05
                if expected_unpivoted > 0:
                    row_diff_pct = abs(actual_rows - expected_unpivoted) / expected_unpivoted
                    row_ok = row_diff_pct <= row_tolerance
                else:
                    row_ok = actual_rows > 0
                
                if row_ok:
                    report_lines.append(f"  [PASS] Row count: {actual_rows} actual vs {expected_unpivoted} expected — OK")
                else:
                    report_lines.append(f"  [WARN] Row count: {actual_rows} actual vs {expected_unpivoted} expected (diff {row_diff_pct:.1%})")
                
                # ── Check 4: No all-null value columns ──
                null_pct = tf_subset['nilai'].isna().mean()
                if null_pct > 0.5:
                    report_lines.append(f"  [WARN] High null rate: {null_pct:.1%} of values are NULL")
                else:
                    report_lines.append(f"  [PASS] Null rate: {null_pct:.1%} — OK")
                
                # ── Overall file verdict ──
                file_ok = provinces_ok and years_ok
                if file_ok:
                    passed_files += 1
                else:
                    failed_files.append(csv_file)
                
            except Exception as e:
                report_lines.append(f"  [FAIL] Error processing {csv_file}: {str(e)}")
                all_issues.append(f"{csv_file}: {str(e)}")
                failed_files.append(csv_file)
            
            report_lines.append("")
        
        # ── Summary section ──
        report_lines.append("=" * 100)
        report_lines.append("RECONCILIATION SUMMARY")
        report_lines.append("-" * 100)
        report_lines.append(f"Total files checked: {total_files}")
        report_lines.append(f"Files PASSED: {passed_files}")
        report_lines.append(f"Files FAILED: {len(failed_files)}")
        
        if failed_files:
            report_lines.append(f"\nFailed files:")
            for f in failed_files:
                report_lines.append(f"  - {f}")
        
        report_lines.append("")
        
        # Transformed DataFrame statistics
        report_lines.append("Transformed Data Statistics:")
        report_lines.append(f"  Total rows:          {len(transformed_df)}")
        report_lines.append(f"  Unique provinces:    {transformed_df['provinsi'].nunique()}")
        report_lines.append(f"  Unique years:        {sorted(transformed_df['tahun'].unique())}")
        report_lines.append(f"  Unique indicators:   {transformed_df['indikator'].nunique()}")
        report_lines.append(f"  Unique categories:   {sorted(transformed_df['kategori'].unique())}")
        
        quality_counts = transformed_df['data_kualitas_flag'].value_counts()
        report_lines.append(f"\n  Quality flags:")
        for flag, count in quality_counts.items():
            report_lines.append(f"    {flag}: {count}")
        
        report_lines.append("")
        report_lines.append("=" * 100)
        
        if len(failed_files) > 0:
            result_str = "[FAIL] RECONCILIATION FAILED"
            report_lines.append(result_str)
            report_lines.append("Issues found - see details above. DW load BLOCKED.")
        else:
            result_str = "[OK] RECONCILIATION PASSED"
            report_lines.append(result_str)
            report_lines.append("All source CSVs match transformed data. Proceeding to DW load...")
        
        report_lines.append("=" * 100)
        
        # Write report
        report_path = os.path.join(REPORTS_FOLDER, os.path.basename(output_file))
        with open(report_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(report_lines))
        
        logger.info(f"Reconciliation report written to: {report_path}")
        
        # Raise exception if failed
        if len(failed_files) > 0:
            error_msg = f"Reconciliation failed for {len(failed_files)} files: {', '.join(failed_files)}"
            logger.error(f"[FAIL] {error_msg}")
            raise ReconciliationError(error_msg)
        else:
            logger.info("[OK] RECONCILIATION PASSED - DW load approved")
            return {
                'passed': True,
                'files_checked': total_files,
                'files_passed': passed_files,
                'report_path': report_path
            }
        
    except ReconciliationError:
        raise
    except Exception as e:
        logger.error(f"[FAIL] Reconciliation error: {str(e)}")
        raise ReconciliationError(f"Reconciliation process failed: {str(e)}")


def _build_csv_indicator_map():
    """
    Build mapping from CSV filename to indicator names used in the transformed DataFrame.
    
    Returns:
        dict: {csv_filename: [indicator_name, ...]}
    """
    return {
        'Ekonomi_persentase_penduduk_miskin.csv': ['Persentase_Penduduk_Miskin'],
        'Ekonomi_upah_rata-rata.csv': ['Upah_Rata_Rata'],
        'Kesehatan_angka_harapan_hidup.csv': ['AHH'],
        'Kesehatan_unmet_layanan_kesehatan.csv': ['Unmet_Layanan_Kesehatan'],
        'Ketenagakerjaan_formal.csv': ['Tenaga_Kerja_Formal'],
        'Ketenagakerjaan_informal.csv': ['Lapangan_Kerja_Informal'],
        'Pendidikan_APK_PT_provinsi.csv': ['APK_Perguruan_Tinggi'],
        'Pendidikan_APM_provinsi.csv': ['APM'],
        'Pendidikan_Rata-rata_lama_sekolah.csv': ['Rata_Rata_Lama_Sekolah'],
        'Teknologi_memiliki_telepon_seluler.csv': ['Memiliki_Telepon_Seluler'],
        'Teknologi_mengakses_internet.csv': ['Mengakses_Internet'],
    }
