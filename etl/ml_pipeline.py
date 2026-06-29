"""ML Pipeline: Clustering (K-Means, HDBSCAN) and Prediction (Linear Regression, Random Forest)"""

import pandas as pd
import numpy as np
from sqlalchemy import create_engine
from config.db_config import PSQL_CONNECTION_STRING
from utils.logger import get_logger
from sklearn.preprocessing import RobustScaler, StandardScaler
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score, calinski_harabasz_score, davies_bouldin_score
import hdbscan
from sklearn.linear_model import LinearRegression
from sklearn.ensemble import RandomForestRegressor
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_absolute_error, r2_score, mean_squared_error
from scipy.stats import spearmanr, t
import json
import warnings
warnings.filterwarnings('ignore')

logger = get_logger(__name__)

class MLPipeline:
    """Comprehensive ML pipeline for clustering and prediction"""
    
    def __init__(self):
        self.engine = create_engine(PSQL_CONNECTION_STRING)
        self.clustering_df = None
        self.timeseries_df = None
        self.results = {}
        
        # Load ML Configuration for fine-tuning
        self.config_path = 'config/ml_config.json'
        self.ml_config = self._load_config()
        
        # For clustering table (aggregated by province)
        self.predictor_cols_clustering = [
            'ekonomi_miskin_mean', 'ekonomi_miskin_trend_pct',
            'ekonomi_upah_mean', 'ekonomi_upah_trend_pct',
            'kesehatan_ahh_perempuan_mean', 'kesehatan_ahh_perempuan_trend_pct',
            'kesehatan_unmet_mean', 'kesehatan_unmet_trend_pct',
            'ketenagakerjaan_formal_mean', 'ketenagakerjaan_formal_trend_pct',
            'ketenagakerjaan_informal_mean', 'ketenagakerjaan_informal_trend_pct',
            'teknologi_telepon_mean', 'teknologi_telepon_trend_pct',
            'teknologi_internet_mean', 'teknologi_internet_trend_pct'
        ]
        
        self.target_cols_clustering = [
            'apm_sd_mean', 'apm_smp_mean', 'apm_sm_mean', 'apk_pt_mean', 'rata_rata_lama_sekolah_mean'
        ]
        
        # For timeseries table (raw values)
        self.predictor_cols_ts = [
            'ekonomi_miskin', 'ekonomi_upah_rata_rata',
            'kesehatan_ahh_perempuan', 'kesehatan_unmet_layanan',
            'ketenagakerjaan_formal', 'ketenagakerjaan_informal',
            'teknologi_telepon_seluler', 'teknologi_internet'
        ]
        
        self.target_cols_ts = [
            'apm_sd', 'apm_smp', 'apm_sm', 'apk_pt', 'rata_rata_lama_sekolah'
        ]
        
    def _load_config(self):
        """Load ML configuration from JSON file"""
        try:
            with open(self.config_path, 'r') as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"Could not load {self.config_path}, using defaults: {e}")
            return {
                "feature_selection": {
                    "correlation_threshold": 0.4,
                    "method": "correlation"
                },
                "clustering": {
                    "kmeans": {"max_k": 8, "random_state": 42, "elbow_method": True},
                    "hdbscan": {"min_cluster_size": 2, "min_samples": 1}
                },
                "overrides": {}
            }
    
    def _select_features_by_correlation(self, X, target_col, threshold=0.4):
        """Select features based on spearman correlation with target column (abs value >= threshold)"""
        correlations = {}
        selected_features = []
        
        for col in X.columns:
            if col != target_col:
                corr = X[col].corr(X[target_col], method='spearman')
                correlations[col] = float(corr)
                if abs(corr) >= threshold:
                    selected_features.append(col)
        
        return selected_features, correlations
    
    def _find_elbow_k(self, inertias, k_range):
        """Find elbow point using curvature method"""
        inertias = np.array(inertias)
        k_range = np.array(list(k_range))
        
        # Calculate differences
        d1 = np.diff(inertias)
        d2 = np.diff(d1)
        
        # Find the point with maximum curvature (largest second difference)
        # This indicates the elbow where diminishing returns start
        elbow_idx = np.argmax(d2) + 1
        
        # Ensure we pick a valid k (at least 2)
        optimal_k = max(2, k_range[elbow_idx])
        
        logger.info(f"  Elbow method detected optimal K: {optimal_k}")
        logger.info(f"  Inertias by K: {dict(zip(k_range, [f'{x:.2f}' for x in inertias]))}")
        
        return optimal_k
        
    def load_data(self):
        """Load clustering and timeseries data, excluding INDONESIA (national level)"""
        logger.info("Loading ML data...")
        
        query_clustering = "SELECT * FROM dm.agg_province_ml WHERE provinsi != 'INDONESIA' ORDER BY provinsi"
        query_timeseries = "SELECT * FROM dm.timeseries_province_year_ml WHERE provinsi != 'INDONESIA' ORDER BY provinsi, tahun"
        
        self.clustering_df = pd.read_sql(query_clustering, self.engine)
        self.timeseries_df = pd.read_sql(query_timeseries, self.engine)
        
        logger.info(f"  Clustering: {self.clustering_df.shape}")
        logger.info(f"  Time series: {self.timeseries_df.shape}")
        
        return self.clustering_df, self.timeseries_df
    
    def kmeans_clustering(self, max_k=None):
        """Global K-Means with elbow method and feature selection based on correlation"""
        logger.info("\n" + "="*80)
        logger.info("GLOBAL K-MEANS CLUSTERING (with Elbow Method & Correlation-based Feature Selection)")
        logger.info("="*80)
        
        # Get correlation threshold from config
        corr_threshold = self.ml_config.get('feature_selection', {}).get('correlation_threshold', 0.4)
        if max_k is None:
            max_k = self.ml_config.get('clustering', {}).get('kmeans', {}).get('max_k', 8)
        
        # Prepare data
        all_cols = self.predictor_cols_clustering + self.target_cols_clustering
        X = self.clustering_df[all_cols].copy()
        X = X.dropna()
        
        # Select features based on correlation with targets
        logger.info(f"Selecting features with correlation threshold: ±{corr_threshold}")
        selected_features = set()
        correlation_details = {}
        
        for target_col in self.target_cols_clustering:
            features, corrs = self._select_features_by_correlation(X, target_col, corr_threshold)
            selected_features.update(features)
            correlation_details[target_col] = corrs
            logger.info(f"  {target_col}: selected {len(features)} features - {features}")
        
        # If no features selected, use all predictors as fallback
        if not selected_features:
            selected_features = self.predictor_cols_clustering
            logger.warning("  No features met correlation threshold, using all predictors")
        
        selected_features = list(selected_features)
        logger.info(f"Total selected features: {selected_features}")
        
        X_selected = X[selected_features].copy()
        scaler = StandardScaler()
        X_scaled = scaler.fit_transform(X_selected)
        
        # Use elbow method to find optimal k
        inertias = []
        silhouette_scores = []
        davies_bouldin_scores = []
        K_range = range(2, max_k + 1)
        
        logger.info("Running K-Means for different K values...")
        for k in K_range:
            kmeans = KMeans(n_clusters=k, random_state=42, n_init=10)
            kmeans.fit(X_scaled)
            inertias.append(kmeans.inertia_)
            silhouette_scores.append(silhouette_score(X_scaled, kmeans.labels_))
            davies_bouldin_scores.append(davies_bouldin_score(X_scaled, kmeans.labels_))
        
        # Determine optimal k using elbow method
        optimal_k = self._find_elbow_k(inertias, K_range)
        
        # Fit final model with optimal k
        kmeans_final = KMeans(n_clusters=optimal_k, random_state=42, n_init=10)
        labels = kmeans_final.fit_predict(X_scaled)
        final_silhouette = silhouette_score(X_scaled, labels)
        
        self.results['kmeans'] = {
            'optimal_k': int(optimal_k),
            'selected_features': selected_features,
            'correlation_threshold': corr_threshold,
            'feature_correlations': correlation_details,
            'inertias': [float(x) for x in inertias],
            'silhouette_scores': [float(x) for x in silhouette_scores],
            'davies_bouldin_scores': [float(x) for x in davies_bouldin_scores],
            'final_silhouette': float(final_silhouette),
            'labels': labels.tolist(),
            'n_samples': len(X),
            'n_features': len(selected_features),
            'k_range': list(K_range),
            'provinces': self.clustering_df.iloc[X.index]['provinsi'].tolist() if 'provinsi' in self.clustering_df.columns else None
        }
        
        logger.info(f"Optimal K: {optimal_k}, Final silhouette: {final_silhouette:.4f}")
        return self.results['kmeans']
    
    def hdbscan_clustering(self, min_cluster_size=2):
        """Global HDBSCAN clustering with feature selection based on correlation"""
        logger.info("\n" + "="*80)
        logger.info("GLOBAL HDBSCAN CLUSTERING (with Correlation-based Feature Selection)")
        logger.info("="*80)
        
        # Get correlation threshold from config
        corr_threshold = self.ml_config.get('feature_selection', {}).get('correlation_threshold', 0.5)
        
        # Prepare data
        all_cols = self.predictor_cols_clustering + self.target_cols_clustering
        X = self.clustering_df[all_cols].copy()
        X = X.dropna()
        
        # Select features based on correlation with targets
        logger.info(f"Selecting features with correlation threshold: ±{corr_threshold}")
        selected_features = set()
        correlation_details = {}
        
        for target_col in self.target_cols_clustering:
            features, corrs = self._select_features_by_correlation(X, target_col, corr_threshold)
            selected_features.update(features)
            correlation_details[target_col] = corrs
            logger.info(f"  {target_col}: selected {len(features)} features - {features}")
        
        # If no features selected, use all predictors as fallback
        if not selected_features:
            selected_features = self.predictor_cols_clustering
            logger.warning("  No features met correlation threshold, using all predictors")
        
        selected_features = list(selected_features)
        logger.info(f"Total selected features: {selected_features}")
        
        X_selected = X[selected_features].copy()
        scaler = StandardScaler()
        X_scaled = scaler.fit_transform(X_selected)
        
        clusterer = hdbscan.HDBSCAN(min_cluster_size=min_cluster_size, min_samples=1)
        labels = clusterer.fit_predict(X_scaled)
        
        n_clusters = len(set(labels)) - (1 if -1 in labels else 0)
        n_noise = list(labels).count(-1)
        noise_ratio = n_noise / len(labels)
        
        if n_clusters > 1:
            mask = labels != -1
            if mask.sum() > 1:
                silhouette = silhouette_score(X_scaled[mask], labels[mask])
            else:
                silhouette = -1.0
        else:
            silhouette = -1.0
        
        self.results['hdbscan'] = {
            'n_clusters': int(n_clusters),
            'n_noise': int(n_noise),
            'noise_ratio': float(noise_ratio),
            'silhouette_score': float(silhouette),
            'selected_features': selected_features,
            'correlation_threshold': corr_threshold,
            'feature_correlations': correlation_details,
            'labels': labels.tolist(),
            'n_samples': len(X),
            'n_features': len(selected_features),
            'provinces': self.clustering_df.iloc[X.index]['provinsi'].tolist() if 'provinsi' in self.clustering_df.columns else None
        }
        
        logger.info(f"Clusters: {n_clusters}, Noise: {n_noise} ({noise_ratio*100:.2f}%)")
        logger.info(f"Silhouette: {silhouette:.4f}")
        
        return self.results['hdbscan']

    def _calculate_cluster_stats(self, df, labels, n_clusters, include_noise=False):
        """Helper to calculate mean values for each cluster"""
        df_with_labels = df.copy()
        df_with_labels['cluster'] = labels
        
        stats = {}
        cluster_range = range(-1, n_clusters) if include_noise else range(n_clusters)
        
        for cluster_id in cluster_range:
            if cluster_id == -1 and (labels == -1).sum() == 0:
                continue
                
            cluster_data = df_with_labels[df_with_labels['cluster'] == cluster_id]
            if len(cluster_data) == 0:
                continue
                
            cluster_name = f"cluster_{cluster_id}" if cluster_id != -1 else "noise"
            
            stats[cluster_name] = {
                'n_members': int(len(cluster_data)),
                'means': {col: float(cluster_data[col].mean()) for col in df.columns}
            }
            
        return stats

    def run_per_target_clustering(self):
        """Run K-Means and HDBSCAN for each target indicator independently using elbow method and feature selection"""
        logger.info("\n" + "="*80)
        logger.info("INDEPENDENT PER-TARGET CLUSTERING ANALYSIS (Elbow Method & Correlation-based Feature Selection)")
        logger.info("="*80)
        
        self.results['per_target_clustering'] = {}
        
        # Global defaults from config
        cl_cfg = self.ml_config.get('clustering', {})
        km_cfg = cl_cfg.get('kmeans', {"max_k": 8, "random_state": 42})
        hdb_cfg = cl_cfg.get('hdbscan', {"min_cluster_size": 2, "min_samples": 1})
        tw_cfg = cl_cfg.get('target_weighting', {"enabled": True, "weight": 1.5})
        fs_cfg = self.ml_config.get('feature_selection', {})
        corr_threshold = fs_cfg.get('correlation_threshold', 0.4)
        
        for target_mean_col in self.target_cols_clustering:
            target_name = target_mean_col.replace('_mean', '')
            logger.info(f"\n--- Processing Target: {target_name} ---")
            
            # Check for overrides
            overrides = self.ml_config.get('overrides', {}).get(target_name, {})
            
            # Prepare data
            cols = self.predictor_cols_clustering + [target_mean_col]
            X = self.clustering_df[cols].copy().dropna()
            
            # Select features based on correlation threshold
            logger.info(f"Selecting features with correlation threshold: ±{corr_threshold}")
            selected_features, correlations = self._select_features_by_correlation(X, target_mean_col, corr_threshold)
            
            if not selected_features:
                # Fallback: Pick top 3 strongest correlations if none meet threshold
                sorted_preds = sorted(correlations.items(), key=lambda x: abs(x[1]), reverse=True)
                selected_features = [p[0] for p in sorted_preds[:3]]
                logger.info(f"  No features met threshold ({corr_threshold}), using top 3 strongest: {selected_features}")
            else:
                logger.info(f"  Selected features meeting ±{corr_threshold}: {selected_features}")
            
            X_selected = X[selected_features].copy()
            # RobustScaler handles outliers (like DKI Jakarta) much better than StandardScaler
            scaler = RobustScaler()
            X_scaled = scaler.fit_transform(X_selected)
            
            # Target weighting logic
            if tw_cfg.get('enabled', True):
                # Include target and apply weight
                X_combined = X[selected_features + [target_mean_col]].copy()
                X_combined_scaled = scaler.fit_transform(X_combined)
                
                weight = tw_cfg.get('weight', 1.5)
                X_combined_scaled[:, -1] = X_combined_scaled[:, -1] * weight
                X_for_clustering = X_combined_scaled
                logger.info(f"  Target weighting ENABLED: {weight}x (Target included in features)")
            else:
                # Exclude target from clustering features entirely for a pure baseline
                X_for_clustering = scaler.fit_transform(X[selected_features])
                logger.info("  Target weighting DISABLED: Clustering on predictors ONLY")
            
            # K-Means with elbow method
            manual_k = overrides.get('kmeans_k')
            if manual_k:
                best_k = manual_k
                km_final = KMeans(n_clusters=best_k, random_state=km_cfg.get('random_state', 42), n_init=10)
                km_labels = km_final.fit_predict(X_scaled)
                best_inertia = km_final.inertia_
                best_silhouette = silhouette_score(X_scaled, km_labels)
                logger.info(f"  K-Means (Manual Override): k={best_k}")
            else:
                max_k = km_cfg.get('max_k', 8)
                k_range = range(2, max_k + 1)
                inertias, silhouettes = [], []
                for k in k_range:
                    km = KMeans(n_clusters=k, random_state=km_cfg.get('random_state', 42), n_init=10)
                    labels = km.fit_predict(X_for_clustering)
                    inertias.append(km.inertia_)
                    silhouettes.append(silhouette_score(X_for_clustering, labels))
                
                # Use elbow method to find optimal k
                best_k = self._find_elbow_k(inertias, k_range)
                km_final = KMeans(n_clusters=best_k, random_state=km_cfg.get('random_state', 42), n_init=10)
                km_labels = km_final.fit_predict(X_for_clustering)
                best_inertia = km_final.inertia_
                best_silhouette = silhouette_score(X_for_clustering, km_labels)
                logger.info(f"  K-Means (Elbow Method): k={best_k}")
            
            # HDBSCAN: Use override or defaults, with feature selection
            min_c_size = overrides.get('hdbscan_min_cluster_size') or hdb_cfg.get('min_cluster_size', 2)
            clusterer = hdbscan.HDBSCAN(
                min_cluster_size=min_c_size, 
                min_samples=hdb_cfg.get('min_samples', 1),
                cluster_selection_epsilon=hdb_cfg.get('cluster_selection_epsilon', 0.0)
            )
            hdb_labels = clusterer.fit_predict(X_for_clustering)
            
            hdb_n_clusters = len(set(hdb_labels)) - (1 if -1 in hdb_labels else 0)
            hdb_n_noise = list(hdb_labels).count(-1)
            hdb_noise_ratio = hdb_n_noise / len(hdb_labels)
            hdb_silhouette = silhouette_score(X_for_clustering[hdb_labels != -1], hdb_labels[hdb_labels != -1]) if hdb_n_clusters > 1 else -1.0
            
            # Store results
            target_results = {
                'selected_features': selected_features,
                'n_selected_features': len(selected_features),
                'correlation_threshold': corr_threshold,
                'feature_correlations': correlations,
                'kmeans': {
                    'n_clusters': int(best_k),
                    'inertia': float(best_inertia),
                    'silhouette': float(best_silhouette),
                    'labels': km_labels.tolist(),
                    'stats': self._calculate_cluster_stats(X[self.predictor_cols_clustering + [target_mean_col]], km_labels, best_k)
                },
                'hdbscan': {
                    'n_clusters': int(hdb_n_clusters),
                    'n_noise': int(hdb_n_noise),
                    'noise_ratio': float(hdb_noise_ratio),
                    'silhouette': float(hdb_silhouette),
                    'labels': hdb_labels.tolist(),
                    'stats': self._calculate_cluster_stats(X[self.predictor_cols_clustering + [target_mean_col]], hdb_labels, hdb_n_clusters, include_noise=True)
                },
                'n_samples': len(X),
                'provinces': self.clustering_df.iloc[X.index]['provinsi'].tolist()
            }
            
            self.results['per_target_clustering'][target_name] = target_results
            logger.info(f"  K-Means Optimal K={best_k}: Inertia={best_inertia:.2f}, Silhouette={best_silhouette:.4f}")
            logger.info(f"  HDBSCAN: Clusters={hdb_n_clusters}, Noise Ratio={hdb_noise_ratio:.4f}, Silhouette={hdb_silhouette:.4f}")

    
    def kmeans_cluster_statistics(self):
        """Global K-Means cluster statistics"""
        logger.info("\n" + "="*80)
        logger.info("GLOBAL K-MEANS CLUSTER STATISTICS")
        logger.info("="*80)
        
        X = self.clustering_df[self.predictor_cols_clustering + self.target_cols_clustering].copy()
        X = X.dropna()
        optimal_k = self.results['kmeans']['optimal_k']
        labels = np.array(self.results['kmeans']['labels'])
        
        self.results['kmeans']['cluster_statistics'] = self._calculate_cluster_stats(X, labels, optimal_k)
        logger.info(f"Global K-Means cluster statistics calculated for {optimal_k} clusters")
        return self.results['kmeans']['cluster_statistics']
    
    def hdbscan_cluster_statistics(self):
        """Global HDBSCAN cluster statistics"""
        logger.info("\n" + "="*80)
        logger.info("GLOBAL HDBSCAN CLUSTER STATISTICS")
        logger.info("="*80)
        
        X = self.clustering_df[self.predictor_cols_clustering + self.target_cols_clustering].copy()
        X = X.dropna()
        n_clusters = self.results['hdbscan']['n_clusters']
        labels = np.array(self.results['hdbscan']['labels'])
        
        self.results['hdbscan']['cluster_statistics'] = self._calculate_cluster_stats(X, labels, n_clusters, include_noise=True)
        logger.info(f"Global HDBSCAN cluster statistics calculated for {n_clusters} clusters")
        return self.results['hdbscan']['cluster_statistics']

    def spearman_correlation(self):
        """Spearman correlation matrix"""
        logger.info("\n" + "="*80)
        logger.info("SPEARMAN CORRELATION ANALYSIS")
        logger.info("="*80)
        
        df = self.timeseries_df.dropna(subset=self.predictor_cols_ts + self.target_cols_ts)
        
        correlations = {}
        correlation_matrix = []
        
        for target in self.target_cols_ts:
            correlations[target] = {}
            row = {'target': target}
            for predictor in self.predictor_cols_ts:
                corr, pval = spearmanr(df[predictor], df[target])
                correlations[target][predictor] = {
                    'coefficient': float(corr),
                    'p_value': float(pval),
                    'significant': bool(pval < 0.05)
                }
                row[predictor] = float(corr)
            correlation_matrix.append(row)
        
        self.results['spearman'] = {
            'correlations': correlations,
            'correlation_matrix': correlation_matrix
        }
        
        logger.info(f"Calculated {len(self.target_cols_ts)*len(self.predictor_cols_ts)} correlations")
        return correlations
    
    def linear_regression(self):
        """Linear Regression with coefficients and p-values"""
        logger.info("\n" + "="*80)
        logger.info("LINEAR REGRESSION")
        logger.info("="*80)
        
        df = self.timeseries_df.dropna(subset=self.predictor_cols_ts + self.target_cols_ts)
        X = df[self.predictor_cols_ts]
        regression_results = {}
        
        for target in self.target_cols_ts:
            y = df[target]
            X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
            
            # Optional scaling
            pred_cfg = self.ml_config.get('prediction', {})
            if pred_cfg.get('use_scaling', False):
                scaler_type = pred_cfg.get('scaler_type', 'robust')
                scaler = RobustScaler() if scaler_type == 'robust' else StandardScaler()
                X_train = scaler.fit_transform(X_train)
                X_test = scaler.transform(X_test)
                # Re-convert to array if needed for p-value calculation
                X_train = np.array(X_train)
                X_test = np.array(X_test)
            
            model = LinearRegression()
            model.fit(X_train, y_train)
            y_pred = model.predict(X_test)
            
            mae = mean_absolute_error(y_test, y_pred)
            r2 = r2_score(y_test, y_pred)
            rmse = np.sqrt(mean_squared_error(y_test, y_pred))
            
            # Calculate Adjusted R-squared
            n = len(y_test)
            p = len(self.predictor_cols_ts)
            adj_r2 = 1 - (1 - r2) * (n - 1) / (n - p - 1)
            
            # Calculate p-values
            y_pred_train = model.predict(X_train)
            residuals = y_train - y_pred_train
            mse = np.sum(residuals**2) / (len(y_train) - p - 1)
            X_with_intercept = np.column_stack([np.ones(len(X_train)), X_train])
            var_covar_matrix = mse * np.linalg.inv(X_with_intercept.T @ X_with_intercept)
            std_errors = np.sqrt(np.diag(var_covar_matrix))[1:]
            t_stats = model.coef_ / std_errors
            p_values = 2 * (1 - t.cdf(np.abs(t_stats), len(y_train) - p - 1))
            
            regression_results[target] = {
                'coefficients': {k: float(v) for k, v in zip(self.predictor_cols_ts, model.coef_)},
                'p_values': {k: float(pv) for k, pv in zip(self.predictor_cols_ts, p_values)},
                'intercept': float(model.intercept_),
                'mae': float(mae),
                'r2': float(r2),
                'adj_r2': float(adj_r2),
                'rmse': float(rmse),
                'n_train': len(X_train),
                'n_test': len(X_test)
            }
            logger.info(f"  {target}: MAE={mae:.4f}, R2={r2:.4f}, AdjR2={adj_r2:.4f}")
        
        self.results['linear_regression'] = regression_results
        return regression_results
    
    def random_forest(self):
        """Random Forest with feature importance"""
        logger.info("\n" + "="*80)
        logger.info("RANDOM FOREST")
        logger.info("="*80)
        
        df = self.timeseries_df.dropna(subset=self.predictor_cols_ts + self.target_cols_ts)
        X = df[self.predictor_cols_ts]
        rf_results = {}
        
        for target in self.target_cols_ts:
            y = df[target]
            X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
            
            # Optional scaling
            pred_cfg = self.ml_config.get('prediction', {})
            if pred_cfg.get('use_scaling', False):
                scaler_type = pred_cfg.get('scaler_type', 'robust')
                scaler = RobustScaler() if scaler_type == 'robust' else StandardScaler()
                X_train = scaler.fit_transform(X_train)
                X_test = scaler.transform(X_test)
            
            model = RandomForestRegressor(n_estimators=100, random_state=42, n_jobs=-1)
            model.fit(X_train, y_train)
            y_pred = model.predict(X_test)
            
            mae = mean_absolute_error(y_test, y_pred)
            r2 = r2_score(y_test, y_pred)
            rmse = np.sqrt(mean_squared_error(y_test, y_pred))
            
            n = len(y_test)
            p = len(self.predictor_cols_ts)
            adj_r2 = 1 - (1 - r2) * (n - 1) / (n - p - 1)
            
            rf_results[target] = {
                'feature_importance': {k: float(v) for k, v in zip(self.predictor_cols_ts, model.feature_importances_)},
                'mae': float(mae),
                'r2': float(r2),
                'adj_r2': float(adj_r2),
                'rmse': float(rmse),
                'n_train': len(X_train),
                'n_test': len(X_test)
            }
            logger.info(f"  {target}: MAE={mae:.4f}, R2={r2:.4f}, AdjR2={adj_r2:.4f}")
        
        self.results['random_forest'] = rf_results
        return rf_results
    
    def run_all(self):
        """Execute full pipeline"""
        self.load_data()
        self.kmeans_clustering()
        self.kmeans_cluster_statistics()
        self.hdbscan_clustering()
        self.hdbscan_cluster_statistics()
        self.run_per_target_clustering()
        self.spearman_correlation()
        self.linear_regression()
        self.random_forest()
        
        logger.info("\n" + "="*80)
        logger.info("ML PIPELINE COMPLETE")
        logger.info("="*80)
        return self.results
    
    def save_results(self, filepath='reports/ml_results.json'):
        """Save results as JSON"""
        with open(filepath, 'w') as f:
            json.dump(self.results, f, indent=2)
        logger.info(f"Results saved to {filepath}")

if __name__ == "__main__":
    pipeline = MLPipeline()
    results = pipeline.run_all()
    pipeline.save_results()
