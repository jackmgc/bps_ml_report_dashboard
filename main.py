"""
ETL + ML Pipeline Orchestrator

This script orchestrates the complete ETL and ML process:

ETL PHASES:
- Extract: Read source CSV files
- Transform: Normalize and validate data
- Load: Insert to PostgreSQL staging and DW schemas
- Reconcile: Validate staging vs. source CSVs (GATE before DW load)
- Aggregate: Create data mart tables for ML
- Validate: Generate quality reports

ML PHASES:
- ML Pipeline: Run clustering (K-Means, HDBSCAN) and prediction models (Linear Regression, Random Forest)
- ML Report: Generate HTML report with visualizations

Usage:
    python main.py --phase all                    # Run complete ETL + ML pipeline
    python main.py --phase validate               # Run up to validation (ETL only)
    python main.py --phase aggregation            # Run up to aggregation
    python main.py --phase ml-pipeline            # Run ML pipeline only
    python main.py --phase ml-report              # Generate ML report
    python main.py --phase all --force-dw-load    # Force DW load despite reconciliation failure
"""

import argparse
import sys
import logging
from pathlib import Path

from config.db_config import DB_CONFIG, LOG_LEVEL, REPORTS_FOLDER
from etl.extractor import extract_all_csvs
from etl.transformer import transform_to_canonical
from etl.loader_python import load_to_staging, create_dw_schema, load_to_dw
from etl.aggregator import setup_aggregation_schema, refresh_data_mart, validate_aggregations
from etl.validator import generate_quality_report
from etl.reconciler import reconcile_staging_to_source, ReconciliationError
from etl.ml_pipeline import MLPipeline
from report_generator import EnhancedReportGenerator
from dashboard_generator import DashboardGenerator
from utils.logger import get_logger
from utils.helpers import ensure_directory

# Get logger
logger = get_logger("main")

# Global state for passing data between phases
_EXTRACTED_DATA = None
_TRANSFORMED_DATA = None


def setup_environment():
    """Set up environment (directories, etc.)"""
    ensure_directory(REPORTS_FOLDER)
    logger.info("Environment setup complete")


def validate_config():
    """Validate configuration"""
    logger.info("Validating configuration...")
    
    if not DB_CONFIG.get('user'):
        logger.error("Database user not configured")
        return False
    
    if not DB_CONFIG.get('password'):
        logger.error("Database password not configured in .env")
        return False
    
    if not DB_CONFIG.get('host'):
        logger.error("Database host not configured")
        return False
    
    logger.info(f"[OK] Configuration valid: {DB_CONFIG['user']}@{DB_CONFIG['host']}:{DB_CONFIG['port']}")
    return True


def phase_extract(args):
    """Execute extraction phase"""
    global _EXTRACTED_DATA
    
    logger.info("")
    logger.info("=" * 100)
    logger.info("PHASE 1: EXTRACTION")
    logger.info("=" * 100)
    
    try:
        _EXTRACTED_DATA = extract_all_csvs()
        logger.info(f"[OK] Extracted {len(_EXTRACTED_DATA)} CSV files")
        return True
    except Exception as e:
        logger.error(f"[FAIL] Extraction failed: {str(e)}")
        return False


def phase_transform(args):
    """Execute transformation phase"""
    global _EXTRACTED_DATA, _TRANSFORMED_DATA
    
    logger.info("")
    logger.info("=" * 100)
    logger.info("PHASE 2: TRANSFORMATION")
    logger.info("=" * 100)
    
    try:
        # If extract phase not run, load from extraction
        if _EXTRACTED_DATA is None:
            logger.info("Extracted data not in memory, re-extracting...")
            _EXTRACTED_DATA = extract_all_csvs()
        
        _TRANSFORMED_DATA = transform_to_canonical(
            _EXTRACTED_DATA, 
            skip_validation=args.skip_validation
        )
        logger.info(f"[OK] Transformed to {len(_TRANSFORMED_DATA)} rows")
        return True
    except Exception as e:
        logger.error(f"[FAIL] Transformation failed: {str(e)}")
        return False


def phase_load_staging(args):
    """Execute staging load phase"""
    global _TRANSFORMED_DATA
    
    logger.info("")
    logger.info("=" * 100)
    logger.info("PHASE 4: LOAD TO STAGING")
    logger.info("=" * 100)
    
    try:
        # If transform phase not run, run it
        if _TRANSFORMED_DATA is None:
            logger.info("Transformed data not in memory, running transformation...")
            if not phase_transform(args):
                return False
        
        success = load_to_staging(_TRANSFORMED_DATA)
        
        if success:
            logger.info("[OK] Staging load complete")
        else:
            logger.error("[FAIL] Staging load failed")
        
        return success
    except Exception as e:
        logger.error(f"[FAIL] Staging load error: {str(e)}")
        return False


def phase_reconcile(args):
    """Execute reconciliation gate phase"""
    global _TRANSFORMED_DATA
    
    logger.info("")
    logger.info("=" * 100)
    logger.info("PHASE 3: RECONCILIATION VALIDATION GATE")
    logger.info("=" * 100)
    logger.info("This gate validates that transformed data matches source CSVs")
    logger.info("DW load will be BLOCKED if reconciliation fails")
    logger.info("")
    
    try:
        # Ensure we have transformed data to reconcile
        if _TRANSFORMED_DATA is None:
            logger.info("Transformed data not in memory, re-extracting and transforming...")
            if not phase_extract(args) or not phase_transform(args):
                return False
        
        result = reconcile_staging_to_source(
            _TRANSFORMED_DATA,
            output_file='reports/reconciliation_report.txt'
        )
        logger.info("[OK] Reconciliation PASSED - DW load approved")
        return True
    except ReconciliationError as e:
        logger.error(f"[FAIL] Reconciliation FAILED: {str(e)}")
        
        if args.force_dw_load:
            logger.warning("[WARNING] Forcing DW load despite reconciliation failure (--force-dw-load flag)")
            return True  # Return True to allow proceeding
        else:
            logger.error("DW load BLOCKED. To override, use: python main.py --force-dw-load")
            return False
    except Exception as e:
        logger.error(f"[FAIL] Reconciliation error: {str(e)}")
        return False


def phase_create_dw(args):
    """Execute DW schema creation phase"""
    logger.info("")
    logger.info("=" * 100)
    logger.info("PHASE 5: CREATE DATA WAREHOUSE SCHEMA")
    logger.info("=" * 100)
    
    try:
        success = create_dw_schema()
        
        if success:
            logger.info("[OK] DW schema creation complete")
        else:
            logger.error("[FAIL] DW schema creation failed")
        
        return success
    except Exception as e:
        logger.error(f"[FAIL] DW schema creation error: {str(e)}")
        return False


def phase_load_dw(args):
    """Execute DW fact table load phase"""
    global _TRANSFORMED_DATA
    
    logger.info("")
    logger.info("=" * 100)
    logger.info("PHASE 6: LOAD DATA WAREHOUSE FACT TABLE")
    logger.info("=" * 100)
    
    try:
        # If transform phase not run, re-transform
        if _TRANSFORMED_DATA is None:
            logger.info("Transformed data not in memory, re-extracting and transforming...")
            _EXTRACTED_DATA = extract_all_csvs()
            _TRANSFORMED_DATA = transform_to_canonical(_EXTRACTED_DATA, skip_validation=args.skip_validation)
        
        # Load to fact table
        success = load_to_dw(_TRANSFORMED_DATA)
        
        if success:
            logger.info("[OK] DW fact table load complete")
        else:
            logger.error("[FAIL] DW fact table load failed")
        
        return success
    except Exception as e:
        logger.error(f"[FAIL] DW load error: {str(e)}")
        return False


def phase_aggregation(args):
    """Execute data mart aggregation phase"""
    logger.info("")
    logger.info("=" * 100)
    logger.info("PHASE 7: DATA MART AGGREGATION")
    logger.info("=" * 100)
    
    try:
        # Setup aggregation schema and tables
        setup_aggregation_schema()
        
        # Refresh aggregation tables
        rows1, rows2 = refresh_data_mart()
        
        # Validate aggregations
        validate_aggregations()
        
        logger.info("[OK] Data mart aggregation complete")
        return True
    except Exception as e:
        logger.error(f"[FAIL] Data mart aggregation error: {str(e)}")
        return False


def phase_validate(args):
    """Execute validation and reporting phase"""
    logger.info("")
    logger.info("=" * 100)
    logger.info("PHASE 8: VALIDATION & REPORTING")
    logger.info("=" * 100)
    
    try:
        report_path = generate_quality_report(
            DB_CONFIG,
            output_file='reports/validation_report.txt'
        )
        
        if report_path:
            logger.info(f"[OK] Quality report generated: {report_path}")
            return True
        else:
            logger.error("[FAIL] Failed to generate quality report")
            return False
    except Exception as e:
        logger.error(f"[FAIL] Validation error: {str(e)}")
        return False


def phase_ml_pipeline(args):
    """Execute ML clustering and prediction pipeline"""
    logger.info("")
    logger.info("=" * 100)
    logger.info("PHASE 9: ML PIPELINE - CLUSTERING & PREDICTION")
    logger.info("=" * 100)
    
    try:
        logger.info("Starting ML pipeline...")
        pipeline = MLPipeline()
        
        # Load data
        logger.info("Loading aggregated data...")
        pipeline.load_data()
        
        # Run independent per-target analysis
        logger.info("Running per-target independent clustering analysis...")
        pipeline.run_per_target_clustering()
        
        # Run correlation analysis
        logger.info("Running Spearman correlation analysis...")
        pipeline.spearman_correlation()
        
        # Run prediction models
        logger.info("Running Linear Regression models...")
        pipeline.linear_regression()
        
        logger.info("Running Random Forest models...")
        pipeline.random_forest()
        
        # Save results
        results_file = 'reports/ml_results.json'
        pipeline.save_results(results_file)
        logger.info(f"[OK] ML results saved to {results_file}")
        
        logger.info("[OK] ML pipeline complete")
        return True
        
    except Exception as e:
        logger.error(f"[FAIL] ML pipeline error: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


def phase_ml_report(args):
    """Generate enhanced ML analysis HTML report with visualizations"""
    logger.info("")
    logger.info("=" * 100)
    logger.info("PHASE 10: ENHANCED ML REPORT GENERATION")
    logger.info("=" * 100)
    
    try:
        logger.info("Generating enhanced ML analysis HTML report...")
        logger.info("  - Spearman correlation heatmap")
        logger.info("  - Yearly correlation tables by target")
        logger.info("  - K-Means clustering visualizations (5 graphs)")
        logger.info("  - Linear Regression prediction plots (5 graphs)")
        
        generator = EnhancedReportGenerator()
        report_file = generator.generate_html('reports/ml_analysis_report_enhanced.html')
        
        if report_file:
            logger.info(f"[OK] Enhanced ML report generated: {report_file}")
            logger.info("     Open the HTML file in a web browser to view all visualizations")
            return True
        else:
            logger.error("[FAIL] Failed to generate ML report")
            return False
            
    except Exception as e:
        logger.error(f"[FAIL] ML report generation error: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


def phase_dashboard(args):
    """Generate interactive dashboard HTML (reports/dashboard.html)"""
    logger.info("")
    logger.info("=" * 100)
    logger.info("PHASE 11: INTERACTIVE DASHBOARD GENERATION")
    logger.info("=" * 100)
    
    try:
        logger.info("Generating interactive dashboard (single-file, offline)...")
        report_file = DashboardGenerator().generate_html('reports/dashboard.html')
        if report_file:
            logger.info(f"[OK] Dashboard generated: {report_file}")
            logger.info("     Open reports/dashboard.html in a web browser")
            return True
        logger.error("[FAIL] Failed to generate dashboard")
        return False
    except Exception as e:
        logger.error(f"[FAIL] Dashboard generation error: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


def run_all_phases(args):
    """Run all ETL and ML phases in sequence"""
    logger.info("Starting full ETL + ML pipeline (--phase all)")
    logger.info("=" * 100)
    
    phases = [
        ("Extract", phase_extract),
        ("Transform", phase_transform),
        ("Reconcile", phase_reconcile),
        ("Load Staging", phase_load_staging),
        ("Create DW", phase_create_dw),
        ("Load DW", phase_load_dw),
        ("Aggregation", phase_aggregation),
        ("Validate", phase_validate),
        ("ML Pipeline", phase_ml_pipeline),
        ("ML Report", phase_ml_report),
        ("Dashboard", phase_dashboard),
    ]
    
    results = {}
    
    for phase_name, phase_func in phases:
        try:
            success = phase_func(args)
            results[phase_name] = success
            
            if not success:
                logger.error(f"[FAIL] {phase_name} phase failed")
                logger.error("Stopping pipeline")
                break
            else:
                logger.info(f"[OK] {phase_name} phase complete")
        except Exception as e:
            logger.error(f"[FAIL] {phase_name} phase error: {str(e)}")
            results[phase_name] = False
            break
    
    # Summary
    logger.info("")
    logger.info("=" * 100)
    logger.info("COMPLETE PIPELINE SUMMARY")
    logger.info("=" * 100)
    
    for phase_name, success in results.items():
        status = "[PASS]" if success else "[FAIL]"
        logger.info(f"{status}: {phase_name}")
    
    all_passed = all(results.values())
    logger.info("")
    
    if all_passed:
        logger.info("[OK] FULL PIPELINE COMPLETE - ALL PHASES SUCCESSFUL")
        logger.info("Data warehouse and ML analysis models are ready")
    else:
        logger.info("[FAIL] PIPELINE INCOMPLETE - SEE ERRORS ABOVE")
    
    logger.info("=" * 100)
    
    return all_passed


def main():
    """Main entry point"""
    # Parse arguments
    parser = argparse.ArgumentParser(
        description="ETL + ML Pipeline for Indonesian Statistics Data",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run complete ETL + ML pipeline
  python main.py --phase all
  
  # Run individual ETL phases
  python main.py --phase extract
  python main.py --phase transform
  python main.py --phase load-staging
  python main.py --phase reconcile
  python main.py --phase load-dw
  python main.py --phase aggregation
  python main.py --phase validate
  
   # Run only ML pipeline (after ETL is complete)
   python main.py --phase ml-pipeline
   python main.py --phase ml-report

   # Generate the interactive dashboard (reports/dashboard.html)
   python main.py --phase dashboard
  
  # Run both ML phases together
  python main.py --phase ml-pipeline
  python main.py --phase ml-report
  
  # Skip validation for quick test
  python main.py --phase transform --skip-validation
  
  # Force DW load despite reconciliation failure
  python main.py --phase all --force-dw-load
        """
    )
    
    parser.add_argument(
        "--phase",
        choices=[
            "extract", "transform", "load-staging", "reconcile", 
            "create-dw", "load-dw", "aggregation", "validate", 
            "ml-pipeline", "ml-report", "dashboard",
            "all"
        ],
        default="all",
        help="Which pipeline phase to run (default: all)"
    )
    
    parser.add_argument(
        "--skip-validation",
        action="store_true",
        help="Skip data quality validation checks"
    )
    
    parser.add_argument(
        "--force-dw-load",
        action="store_true",
        help="Force DW load even if reconciliation fails (use with caution)"
    )
    
    args = parser.parse_args()
    
    # Setup
    setup_environment()
    
    logger.info("")
    logger.info("=" * 100)
    logger.info("ETL + ML PIPELINE FOR INDONESIAN STATISTICS DATA".center(100))
    logger.info("=" * 100)
    logger.info("")
    
    # Validate config
    if not validate_config():
        logger.error("Configuration validation failed")
        return 1
    
    # Route to appropriate phase
    try:
        if args.phase == "all":
            success = run_all_phases(args)
        elif args.phase == "extract":
            success = phase_extract(args)
        elif args.phase == "transform":
            success = phase_transform(args)
        elif args.phase == "load-staging":
            success = phase_load_staging(args)
        elif args.phase == "reconcile":
            success = phase_reconcile(args)
        elif args.phase == "create-dw":
            success = phase_create_dw(args)
        elif args.phase == "load-dw":
            success = phase_load_dw(args)
        elif args.phase == "aggregation":
            success = phase_aggregation(args)
        elif args.phase == "validate":
            success = phase_validate(args)
        elif args.phase == "ml-pipeline":
            success = phase_ml_pipeline(args)
        elif args.phase == "ml-report":
            success = phase_ml_report(args)
        elif args.phase == "dashboard":
            success = phase_dashboard(args)
        else:
            logger.error(f"Unknown phase: {args.phase}")
            return 1
        
        return 0 if success else 1
    
    except KeyboardInterrupt:
        logger.warning("\n[FAIL] Pipeline interrupted by user")
        return 130
    except Exception as e:
        logger.error(f"[FAIL] Unexpected error: {str(e)}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())