"""Validator module - generates quality reports using inline SQL queries (no .sql files)"""
import os
from datetime import datetime
from sqlalchemy import create_engine, text
from config.db_config import PSQL_CONNECTION_STRING, REPORTS_FOLDER
from utils.logger import get_logger
from utils.helpers import query_database

logger = get_logger(__name__)

# ── Inline SQL queries (previously in sql/verification/*.sql) ────────────────

RECONCILIATION_COUNTS_SQL = """
SELECT 
    COUNT(*) as total_rows,
    COUNT(DISTINCT provinsi) as unique_provinces,
    COUNT(DISTINCT tahun) as unique_years,
    COUNT(DISTINCT indikator) as unique_indicators,
    COUNT(DISTINCT kategori) as unique_categories,
    COUNT(DISTINCT dimensi) as unique_dimensions
FROM staging.indikator_raw;
"""

DATA_QUALITY_SUMMARY_SQL = """
SELECT 
    data_kualitas_flag,
    COUNT(*) as row_count,
    ROUND(COUNT(*) * 100.0 / NULLIF(SUM(COUNT(*)) OVER(), 0), 2) as percentage
FROM staging.indikator_raw
GROUP BY data_kualitas_flag
ORDER BY row_count DESC;
"""

FACT_INTEGRITY_SQL = """
SELECT 
    'fact_indikator' as table_name,
    COUNT(*) as total_rows,
    COUNT(DISTINCT f.tahun_id) as unique_years,
    COUNT(DISTINCT f.provinsi_id) as unique_provinces,
    COUNT(DISTINCT d.indikator_id) as unique_indicators,
    COUNT(CASE WHEN f.nilai IS NULL THEN 1 END) as null_values
FROM dw.fact_indikator f
JOIN dw.dim_indikator_dimensi d ON f.indikator_dimensi_id = d.indikator_dimensi_id;
"""

STAGING_NULL_CHECK_SQL = """
SELECT
    'provinsi' as column_name, COUNT(CASE WHEN provinsi IS NULL THEN 1 END) as null_count
FROM staging.indikator_raw
UNION ALL
SELECT
    'tahun', COUNT(CASE WHEN tahun IS NULL THEN 1 END)
FROM staging.indikator_raw
UNION ALL
SELECT
    'indikator', COUNT(CASE WHEN indikator IS NULL THEN 1 END)
FROM staging.indikator_raw
UNION ALL
SELECT
    'nilai', COUNT(CASE WHEN nilai IS NULL THEN 1 END)
FROM staging.indikator_raw;
"""


def generate_quality_report(db_config, output_file='reports/validation_report.txt'):
    """
    Generate comprehensive data quality report using inline SQL queries.
    
    Args:
        db_config (dict): Database configuration (unused, uses PSQL_CONNECTION_STRING)
        output_file (str): Output file path for report
        
    Returns:
        str: Path to output report file
    """
    logger.info("Generating quality report...")
    
    try:
        engine = create_engine(PSQL_CONNECTION_STRING)
        os.makedirs(REPORTS_FOLDER, exist_ok=True)
        
        report_lines = []
        report_lines.append("=" * 80)
        report_lines.append("DATA QUALITY VALIDATION REPORT")
        report_lines.append("=" * 80)
        report_lines.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        report_lines.append("")
        
        # Section 1: Reconciliation Counts
        report_lines.append("SECTION 1: RECONCILIATION COUNTS")
        report_lines.append("-" * 80)
        
        result = query_database(engine, RECONCILIATION_COUNTS_SQL)
        if result is not None and not result.empty:
            report_lines.append(result.to_string(index=False))
        else:
            report_lines.append("  No data found in staging table.")
        report_lines.append("")
        
        # Section 2: Data Quality Summary
        report_lines.append("SECTION 2: DATA QUALITY SUMMARY")
        report_lines.append("-" * 80)
        
        result = query_database(engine, DATA_QUALITY_SUMMARY_SQL)
        if result is not None and not result.empty:
            report_lines.append(result.to_string(index=False))
        else:
            report_lines.append("  No quality flag data found.")
        report_lines.append("")
        
        # Section 3: Null Value Check
        report_lines.append("SECTION 3: NULL VALUE CHECK (STAGING)")
        report_lines.append("-" * 80)
        
        result = query_database(engine, STAGING_NULL_CHECK_SQL)
        if result is not None and not result.empty:
            report_lines.append(result.to_string(index=False))
        else:
            report_lines.append("  Could not check null values.")
        report_lines.append("")
        
        # Section 4: Fact Table Integrity (only if DW exists)
        report_lines.append("SECTION 4: FACT TABLE INTEGRITY CHECKS")
        report_lines.append("-" * 80)
        
        try:
            result = query_database(engine, FACT_INTEGRITY_SQL)
            if result is not None and not result.empty:
                report_lines.append(result.to_string(index=False))
            else:
                report_lines.append("  No data in fact table.")
        except Exception:
            report_lines.append("  Fact table not yet created (DW load not run).")
        report_lines.append("")
        
        report_lines.append("=" * 80)
        report_lines.append("END OF REPORT")
        report_lines.append("=" * 80)
        
        # Write report to file
        report_path = os.path.join(REPORTS_FOLDER, os.path.basename(output_file))
        with open(report_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(report_lines))
        
        logger.info(f"[OK] Quality report generated: {report_path}")
        engine.dispose()
        return report_path
        
    except Exception as e:
        logger.error(f"[FAIL] Error generating quality report: {str(e)}")
        return None
