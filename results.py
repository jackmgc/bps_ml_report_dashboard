"""Main script to run ML pipeline and generate report"""

import sys
from etl.ml_pipeline import MLPipeline
from report_generator import ReportGenerator
from utils.logger import get_logger

logger = get_logger("results")

def main():
    logger.info("="*80)
    logger.info("Starting ML Analysis Pipeline")
    logger.info("="*80)
    
    # Run ML pipeline
    logger.info("\nStep 1: Running ML pipeline...")
    pipeline = MLPipeline()
    pipeline.load_data()
    pipeline.kmeans_clustering()
    pipeline.hdbscan_clustering()
    pipeline.spearman_correlation()
    pipeline.linear_regression()
    pipeline.random_forest()
    pipeline.save_results('ml_results.json')
    
    # Generate HTML report
    logger.info("\nStep 2: Generating HTML report...")
    generator = ReportGenerator()
    report_file = generator.generate_html('reports/ml_analysis_report.html')
    
    logger.info("\n" + "="*80)
    logger.info("ML Analysis Complete!")
    logger.info(f"Report saved to: {report_file}")
    logger.info("="*80)

if __name__ == "__main__":
    main()
