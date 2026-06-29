"""
Complete Enhanced Report Generator with:
1. Correlation heatmap (displayed in HTML via base64)
2. Yearly correlation tables (5 targets × 9 predictors, with mean)
3. K-Means and HDBSCAN individual graphs (5 graphs each - one per target)
4. Linear Regression individual graphs (5 graphs - one per target)
5. Simple clean table styling (Academic/LaTeX style)
6. Clear data normalization documentation
7. All images embedded in HTML (no local server needed)
"""

import json
import pandas as pd
import numpy as np
from datetime import datetime
from html import escape
import logging

try:
    from sqlalchemy import create_engine
except Exception:
    create_engine = None
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import seaborn as sns

# Use a bundled serif font in containers to avoid noisy missing-font warnings.
plt.rcParams['font.family'] = 'serif'
plt.rcParams['font.serif'] = ['DejaVu Serif', 'Times New Roman', 'Times']
plt.rcParams['axes.unicode_minus'] = False
from sklearn.preprocessing import StandardScaler, RobustScaler
from sklearn.cluster import KMeans
from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_absolute_error, r2_score
from scipy.stats import spearmanr
import base64
from io import BytesIO

try:
    from config.db_config import PSQL_CONNECTION_STRING
except Exception:
    PSQL_CONNECTION_STRING = None

try:
    from utils.logger import get_logger
    logger = get_logger(__name__)
except Exception:
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    logger = logging.getLogger(__name__)

class EnhancedReportGenerator:
    """Generate comprehensive enhanced HTML report with all visualizations"""
    
    def __init__(self, ml_results_path='reports/ml_results.json'):
        self.ml_results_path = ml_results_path
        
        try:
            with open(ml_results_path, 'r') as f:
                self.results = json.load(f)
            logger.info(f"Loaded ML results from {ml_results_path}")
        except Exception as e:
            logger.warning(f"Could not load ML results: {e}")
            self.results = {}
        
        # Load ML config for scaling settings
        try:
            with open('config/ml_config.json', 'r') as f:
                self.ml_config = json.load(f)
        except:
            self.ml_config = {}
        
        # Connect to database when available. The cluster section can still be
        # generated from ml_results.json without a database connection.
        self.engine = create_engine(PSQL_CONNECTION_STRING) if create_engine and PSQL_CONNECTION_STRING else None
        self.df_timeseries = None
        self.df_clustering = None
        self.load_data()
        
        # Column mappings
        self.target_cols = ['apm_sd', 'apm_smp', 'apm_sm', 'apk_pt', 'rata_rata_lama_sekolah']
        self.predictor_cols = [
            'ekonomi_miskin', 'ekonomi_upah_rata_rata',
            'kesehatan_ahh_perempuan', 'kesehatan_unmet_layanan',
            'ketenagakerjaan_formal', 'ketenagakerjaan_informal',
            'teknologi_telepon_seluler', 'teknologi_internet'
        ]
        
        self.target_names = {
            'apm_sd': 'APMSD',
            'apm_smp': 'APMSMP',
            'apm_sm': 'APMSM',
            'apk_pt': 'APKPT',
            'rata_rata_lama_sekolah': 'RLS'
        }
        
        self.predictor_short_names = {
            'ekonomi_miskin': 'PPM (%)',
            'ekonomi_upah_rata_rata': 'URPJ',
            'kesehatan_ahh_perempuan': 'AHH',
            'kesehatan_unmet_layanan': 'PUPK (%)',
            'ketenagakerjaan_formal': 'PTKF (%)',
            'ketenagakerjaan_informal': 'PTKIN (%)',
            'teknologi_telepon_seluler': 'PMTS (%)',
            'teknologi_internet': 'PAIN (%)',
            # Add mean versions for clustering tables
            'ekonomi_miskin_mean': 'PPM (%) Mean',
            'ekonomi_miskin_trend_pct': 'PPM Trend (%)',
            'ekonomi_upah_mean': 'URPJ Mean',
            'ekonomi_upah_trend_pct': 'URPJ Trend (%)',
            'kesehatan_ahh_perempuan_mean': 'AHH Mean',
            'kesehatan_ahh_perempuan_trend_pct': 'AHH Trend (%)',
            'kesehatan_unmet_mean': 'PUPK (%) Mean',
            'kesehatan_unmet_trend_pct': 'PUPK Trend (%)',
            'ketenagakerjaan_formal_mean': 'PTKF (%) Mean',
            'ketenagakerjaan_formal_trend_pct': 'PTKF Trend (%)',
            'ketenagakerjaan_informal_mean': 'PTKIN (%) Mean',
            'ketenagakerjaan_informal_trend_pct': 'PTKIN Trend (%)',
            'teknologi_telepon_mean': 'PMTS (%) Mean',
            'teknologi_telepon_trend_pct': 'PMTS Trend (%)',
            'teknologi_internet_mean': 'PAIN (%) Mean',
            'teknologi_internet_trend_pct': 'PAIN Trend (%)'
        }
        
        # Clustering columns
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
    
    def load_data(self):
        """Load both timeseries and clustering data"""
        if self.engine is None:
            logger.warning("Database connection unavailable; trying to build clustering data from local CSV files")
            self.df_clustering = self.load_clustering_data_from_csv()
            return

        try:
            # Time series data for correlations and prediction
            query_ts = "SELECT * FROM dm.timeseries_province_year_ml WHERE provinsi != 'INDONESIA' ORDER BY provinsi, tahun"
            self.df_timeseries = pd.read_sql(query_ts, self.engine)
            
            # Clustering data for visualizations
            query_cl = "SELECT * FROM dm.agg_province_ml WHERE provinsi != 'INDONESIA' ORDER BY provinsi"
            self.df_clustering = pd.read_sql(query_cl, self.engine)
            
            logger.info(f"Loaded data: TS={self.df_timeseries.shape}, CL={self.df_clustering.shape}")
        except Exception as e:
            logger.error(f"Failed to load data: {e}")
            logger.warning("Trying to build clustering data from local CSV files")
            self.df_clustering = self.load_clustering_data_from_csv()

    def _canonical_provinces(self):
        return [
            "ACEH", "SUMATERA UTARA", "SUMATERA BARAT", "RIAU", "JAMBI",
            "SUMATERA SELATAN", "BENGKULU", "LAMPUNG", "KEP. BANGKA BELITUNG",
            "KEP. RIAU", "DKI JAKARTA", "JAWA BARAT", "JAWA TENGAH",
            "DI YOGYAKARTA", "JAWA TIMUR", "BANTEN", "BALI",
            "NUSA TENGGARA BARAT", "NUSA TENGGARA TIMUR", "KALIMANTAN BARAT",
            "KALIMANTAN TENGAH", "KALIMANTAN SELATAN", "KALIMANTAN TIMUR",
            "KALIMANTAN UTARA", "SULAWESI UTARA", "SULAWESI TENGAH",
            "SULAWESI SELATAN", "SULAWESI TENGGARA", "GORONTALO",
            "SULAWESI BARAT", "MALUKU", "MALUKU UTARA", "PAPUA BARAT",
            "PAPUA",
        ]

    def _read_province_year_values(self, filepath, years, data_start_idx, col_start=1):
        raw_df = pd.read_csv(filepath, header=None)
        provinces = raw_df.iloc[data_start_idx:, 0].astype(str).str.strip()
        values = raw_df.iloc[data_start_idx:, col_start:col_start + len(years)].copy()
        values.columns = years
        values['provinsi'] = provinces.values
        values = values[values['provinsi'].isin(self._canonical_provinces())]
        long_df = values.melt(id_vars='provinsi', var_name='tahun', value_name='nilai')
        long_df['nilai'] = pd.to_numeric(long_df['nilai'], errors='coerce')
        return long_df.dropna(subset=['nilai'])

    def _read_simple_csv(self, filename):
        filepath = f'data/{filename}'
        raw_df = pd.read_csv(filepath, header=None)
        year_row_idx, data_start_idx = None, None
        for idx in [1, 2]:
            candidates = raw_df.iloc[idx, 1:].fillna('').astype(str)
            if candidates.str.isnumeric().sum() >= 4:
                year_row_idx = idx
                data_start_idx = idx + 1
                break
        if year_row_idx is None:
            raise ValueError(f'Cannot detect year row in {filename}')

        years = [int(y) for y in raw_df.iloc[year_row_idx, 1:6].tolist()]
        return self._read_province_year_values(filepath, years, data_start_idx)

    def _read_poverty_csv(self):
        filepath = 'data/Ekonomi_persentase_penduduk_miskin.csv'
        raw_df = pd.read_csv(filepath, header=None)
        years = [int(y) for y in raw_df.iloc[2, 1:6].tolist()]
        return self._read_province_year_values(filepath, years, data_start_idx=4)

    def _read_apm_csv(self, col_start):
        filepath = 'data/Pendidikan_APM_provinsi.csv'
        raw_df = pd.read_csv(filepath, header=None)
        years = [int(y) for y in raw_df.iloc[2, col_start:col_start + 5].tolist()]
        return self._read_province_year_values(filepath, years, data_start_idx=3, col_start=col_start)

    def _read_ahh_csv(self, col_start):
        filepath = 'data/Kesehatan_angka_harapan_hidup.csv'
        raw_df = pd.read_csv(filepath, header=None)
        years = [int(y) for y in raw_df.iloc[2, col_start:col_start + 5].tolist()]
        return self._read_province_year_values(filepath, years, data_start_idx=3, col_start=col_start)

    def _mean_and_trend(self, df, years):
        scoped = df[df['tahun'].isin(years)]
        mean_series = scoped.groupby('provinsi')['nilai'].mean()
        first_year, last_year = years[0], years[-1]
        first = scoped[scoped['tahun'] == first_year].set_index('provinsi')['nilai']
        last = scoped[scoped['tahun'] == last_year].set_index('provinsi')['nilai']
        trend = ((last - first) / first * 100).replace([np.inf, -np.inf], np.nan)
        return mean_series, trend

    def _assign_mean_trend(self, out, prefix, df, years):
        mean_series, trend = self._mean_and_trend(df, years)
        out[f'{prefix}_mean'] = out['provinsi'].map(mean_series)
        out[f'{prefix}_trend_pct'] = out['provinsi'].map(trend)

    def _assign_mean(self, out, col, df, years):
        scoped = df[df['tahun'].isin(years)]
        mean_series = scoped.groupby('provinsi')['nilai'].mean()
        out[col] = out['provinsi'].map(mean_series)

    def load_clustering_data_from_csv(self):
        """Build dm.agg_province_ml equivalent from local CSV files."""
        try:
            out = pd.DataFrame({'provinsi': sorted(self._canonical_provinces())})

            self._assign_mean_trend(out, 'ekonomi_miskin', self._read_poverty_csv(), [2021, 2022, 2023, 2024, 2025])
            self._assign_mean_trend(out, 'ekonomi_upah', self._read_simple_csv('Ekonomi_upah_rata-rata.csv'), [2020, 2021, 2022, 2023, 2024])
            self._assign_mean_trend(out, 'kesehatan_ahh_perempuan', self._read_ahh_csv(6), [2020, 2021, 2022, 2023, 2024])
            self._assign_mean_trend(out, 'kesehatan_unmet', self._read_simple_csv('Kesehatan_unmet_layanan_kesehatan.csv'), [2020, 2021, 2022, 2023, 2024])
            self._assign_mean_trend(out, 'ketenagakerjaan_formal', self._read_simple_csv('Ketenagakerjaan_formal.csv'), [2020, 2021, 2022, 2023, 2024])
            self._assign_mean_trend(out, 'ketenagakerjaan_informal', self._read_simple_csv('Ketenagakerjaan_informal.csv'), [2020, 2021, 2022, 2023, 2024])
            self._assign_mean_trend(out, 'teknologi_telepon', self._read_simple_csv('Teknologi_memiliki_telepon_seluler.csv'), [2020, 2021, 2022, 2023, 2024])
            self._assign_mean_trend(out, 'teknologi_internet', self._read_simple_csv('Teknologi_mengakses_internet.csv'), [2020, 2021, 2022, 2023, 2024])

            self._assign_mean(out, 'apm_sd_mean', self._read_apm_csv(1), [2020, 2021, 2022, 2023, 2024])
            self._assign_mean(out, 'apm_smp_mean', self._read_apm_csv(6), [2020, 2021, 2022, 2023, 2024])
            self._assign_mean(out, 'apm_sm_mean', self._read_apm_csv(11), [2020, 2021, 2022, 2023, 2024])
            self._assign_mean(out, 'apk_pt_mean', self._read_simple_csv('Pendidikan_APK_PT_provinsi.csv'), [2020, 2021, 2022, 2023, 2024])
            self._assign_mean(out, 'rata_rata_lama_sekolah_mean', self._read_simple_csv('Pendidikan_Rata-rata_lama_sekolah.csv'), [2020, 2021, 2022, 2023, 2024])

            logger.info(f"Built clustering data from CSV: {out.shape}")
            return out
        except Exception as e:
            logger.error(f"Failed to build clustering data from CSV: {e}")
            return None

    def fig_to_base64(self, fig):
        """Convert matplotlib figure to base64-encoded PNG"""
        buffer = BytesIO()
        fig.savefig(buffer, format='png', dpi=100, bbox_inches='tight')
        buffer.seek(0)
        image_base64 = base64.b64encode(buffer.read()).decode('utf-8')
        plt.close(fig)
        return image_base64
    
    def generate_correlation_heatmap(self):
        """Generate Spearman correlation heatmap"""
        logger.info("Generating correlation heatmap...")
        if self.df_timeseries is None: return None
        try:
            data = self.df_timeseries[self.predictor_cols + self.target_cols].dropna()
            if len(data) == 0: return None
            scaler = StandardScaler()
            data_normalized = pd.DataFrame(scaler.fit_transform(data), columns=data.columns, index=data.index)
            corr_matrix = data_normalized.corr(method='spearman')
            fig, ax = plt.subplots(figsize=(14, 10))
            sns.heatmap(corr_matrix, annot=True, fmt='.3f', cmap='RdBu_r', center=0, vmin=-1, vmax=1, ax=ax, square=True)
            ax.set_title('Matriks Korelasi Spearman', fontsize=13, fontweight='bold', pad=20)
            plt.tight_layout()
            return self.fig_to_base64(fig)
        except Exception as e:
            logger.error(f"Error generating correlation heatmap: {e}")
            return None
    
    def generate_yearly_correlation_tables(self):
        """Generate correlation tables by year"""
        if self.df_timeseries is None: return {}
        tables_html = {}
        try:
            years = sorted(self.df_timeseries['tahun'].unique())
            for target in self.target_cols:
                rows = []
                for pred in self.predictor_cols:
                    row_data = {'Variable': self.predictor_short_names[pred]}
                    corrs = []
                    for year in years:
                        y_data = self.df_timeseries[self.df_timeseries['tahun'] == year][[pred, target]].dropna()
                        if len(y_data) > 2:
                            c, _ = spearmanr(y_data[pred], y_data[target])
                            row_data[str(year)] = round(c, 3); corrs.append(c)
                        else: row_data[str(year)] = 'N/A'
                    row_data['mean'] = round(np.mean(corrs), 3) if corrs else 'N/A'
                    rows.append(row_data)
                # Sort rows by mean correlation (highest to lowest)
                rows.sort(key=lambda x: x['mean'] if isinstance(x['mean'], (int, float)) else -999, reverse=True)
                
                df_corr = pd.DataFrame(rows)
                html = '<table><thead><tr><th>Variabel</th>'
                for y in years: html += f'<th>{y}</th>'
                html += '<th>mean</th></tr></thead><tbody>'
                for _, row in df_corr.iterrows():
                    html += '<tr>'
                    for col in df_corr.columns:
                        val = row[col]
                        html += f'<td>{val:.3f}</td>' if isinstance(val, float) else f'<td>{val}</td>'
                    html += '</tr>'
                html += '</tbody></table>'
                tables_html[target] = html
            return tables_html
        except Exception as e: return {}
    
    def generate_trend_correlation_table(self):
        """Generate correlation table specifically for trend features"""
        if self.df_clustering is None: return ""
        try:
            # Predictor trend columns
            trend_preds = [c for c in self.predictor_cols_clustering if '_trend_pct' in c]
            
            rows = []
            for pred in trend_preds:
                row_data = {'Variable': self.predictor_short_names.get(pred, pred)}
                for target_col in self.target_cols_clustering:
                    target_name = self.target_names.get(target_col.replace('_mean', ''), target_col)
                    y_data = self.df_clustering[[pred, target_col]].dropna()
                    if len(y_data) > 2:
                        c, _ = spearmanr(y_data[pred], y_data[target_col])
                        row_data[target_name] = round(c, 3)
                    else: row_data[target_name] = 'N/A'
                rows.append(row_data)
            
            # Sort by absolute max correlation if possible
            df_corr = pd.DataFrame(rows)
            
            html = '<table><thead><tr><th>Variabel Trend</th>'
            for target_col in self.target_cols_clustering:
                target_name = self.target_names.get(target_col.replace('_mean', ''), target_col)
                html += f'<th>{target_name}</th>'
            html += '</tr></thead><tbody>'
            
            for _, row in df_corr.iterrows():
                html += '<tr>'
                for col in df_corr.columns:
                    val = row[col]
                    html += f'<td>{val:.3f}</td>' if isinstance(val, float) else f'<td>{val}</td>'
                html += '</tr>'
            html += '</tbody></table>'
            return html
        except Exception as e: 
            logger.error(f"Error generating trend correlation table: {e}")
            return ""

    def generate_hdbscan_metrics_table(self, target=None):
        """Simple metrics table"""
        if target: h = self.results.get('per_target_clustering', {}).get(target, {}).get('hdbscan', {})
        else: h = self.results.get('hdbscan', {})
        if not h: return "<p>Data tidak tersedia.</p>"
        html = '<table><thead><tr><th>Metrik</th><th>Nilai</th></tr></thead><tbody>'
        html += f'<tr><td>Jumlah Kluster</td><td>{h.get("n_clusters", "N/A")}</td></tr>'
        html += f'<tr><td>Rasio Noise</td><td>{h.get("noise_ratio", 0):.4f}</td></tr>'
        html += f'<tr><td>Silhouette Score</td><td>{h.get("silhouette", h.get("silhouette_score", 0)):.4f}</td></tr>'
        html += '</tbody></table>'
        return html

    def generate_kmeans_metrics_table(self, target=None):
        """Simple metrics table with Inertia and Silhouette"""
        if target: k = self.results.get('per_target_clustering', {}).get(target, {}).get('kmeans', {})
        else: k = self.results.get('kmeans', {})
        if not k: return "<p>Data tidak tersedia.</p>"
        
        opt_k = k.get("optimal_k", k.get("n_clusters", "N/A"))
        inertia = k.get("inertia")
        if inertia is None and "inertias" in k and "k_range" in k:
            try:
                idx = k["k_range"].index(opt_k)
                inertia = k["inertias"][idx]
            except: inertia = "N/A"
            
        html = '<table><thead><tr><th>Metrik</th><th>Nilai</th></tr></thead><tbody>'
        html += f'<tr><td>Nilai K</td><td>{opt_k}</td></tr>'
        html += f'<tr><td>Inersia</td><td>{f"{inertia:.2f}" if isinstance(inertia, (int, float)) else inertia}</td></tr>'
        html += f'<tr><td>Silhouette Score</td><td>{k.get("final_silhouette", k.get("silhouette", 0)):.4f}</td></tr>'
        html += '</tbody></table>'
        return html

    def generate_cluster_statistics_table(self, method='kmeans', target=None):
        """Comprehensive cluster statistics table"""
        if target: stats = self.results.get('per_target_clustering', {}).get(target, {}).get(method, {}).get('stats', {})
        else: stats = self.results.get(method, {}).get('cluster_statistics', {})
        if not stats: return f'<p>Data tidak tersedia.</p>'
        
        keys = sorted([k for k in stats.keys() if k.startswith('cluster_')], key=lambda x: int(x.split('_')[1]))
        if 'noise' in stats: keys.append('noise')
            
        html = '<table><thead><tr><th>Indikator</th>'
        for k in keys:
            header = 'Noise' if k == 'noise' else self._cluster_display_name(int(k.split('_')[1]))
            html += f'<th>{header}</th>'
        html += '</tr></thead><tbody>'
        html += '<tr><td>Jumlah Anggota</td>'
        for k in keys: html += f'<td>{stats[k]["n_members"]}</td>'
        html += '</tr>'
        # Get selected features for this target to highlight
        selected_features = self.results.get('per_target_clustering', {}).get(target, {}).get('selected_features', [])
        
        for p in self.predictor_cols_clustering:
            display_name = self.predictor_short_names.get(p, p)
            if p in selected_features:
                display_name = f'<span style="color: green;">{display_name}</span>'
                
            html += f'<tr><td>{display_name}</td>'
            for k in keys: html += f'<td>{stats[k]["means"].get(p, 0):.2f}</td>'
            html += '</tr>'
        
        # Target Pendidikan section
        html += '<tr><td><strong>Target Pendidikan</strong></td>' + ('<td></td>' * len(keys)) + '</tr>'
        for t_col in self.target_cols_clustering:
            t_name_clean = t_col.replace('_mean', '')
            # If per-target analysis, ONLY show the current target indicator
            if target and t_name_clean != target: continue
            
            html += f'<tr><td>{self.target_names.get(t_name_clean, t_name_clean)}</td>'
            for k in keys: html += f'<td>{stats[k]["means"].get(t_col, 0):.2f}</td>'
            html += '</tr>'
            
        html += '</tbody></table>'
        return html

    def _cluster_display_name(self, label):
        if label == -1:
            return 'Noise'
        return f'Kluster {label}'

    def _get_cluster_order_from_labels(self, labels):
        unique_labels = sorted(set(int(l) for l in labels if int(l) != -1))
        if -1 in set(int(l) for l in labels):
            unique_labels.append(-1)
        return unique_labels

    def generate_cluster_overview_table(self, method='kmeans', target=None):
        """Compact member and target-statistics table for each cluster."""
        target_results = self.results.get('per_target_clustering', {}).get(target, {})
        method_results = target_results.get(method, {})
        labels = [int(l) for l in method_results.get('labels', [])]
        provinces = target_results.get('provinces', [])
        stats = method_results.get('stats', {})

        if not labels or not provinces or len(labels) != len(provinces):
            return '<p>Data anggota kluster tidak tersedia.</p>'

        total = len(labels)
        target_col = f'{target}_mean'
        rows = []
        for label in self._get_cluster_order_from_labels(labels):
            key = 'noise' if label == -1 else f'cluster_{label}'
            members = sorted([provinces[i] for i, l in enumerate(labels) if l == label])
            n_members = len(members)
            target_mean = stats.get(key, {}).get('means', {}).get(target_col)
            rows.append({
                'label': label,
                'name': self._cluster_display_name(label),
                'n_members': n_members,
                'pct': n_members / total * 100 if total else 0,
                'target_mean': target_mean,
                'members': members
            })

        html = '<table class="cluster-overview-table"><thead><tr>'
        html += '<th>Kluster</th><th>Jumlah</th><th>% Sampel</th>'
        html += f'<th>Rata-rata {self.target_names.get(target, target)}</th><th>Provinsi</th>'
        html += '</tr></thead><tbody>'
        for row in rows:
            members = ', '.join(escape(str(m)) for m in row['members'])
            target_mean = f'{row["target_mean"]:.2f}' if isinstance(row['target_mean'], (int, float)) else 'N/A'
            html += '<tr>'
            html += f'<td>{row["name"]}</td>'
            html += f'<td>{row["n_members"]}</td>'
            html += f'<td>{row["pct"]:.1f}%</td>'
            html += f'<td>{target_mean}</td>'
            html += f'<td class="members-cell">{members}</td>'
            html += '</tr>'
        html += '</tbody></table>'
        return html

    def generate_rf_feature_importance_tables(self):
        tables = {}
        for target in self.target_cols:
            rf = self.results.get('random_forest', {}).get(target, {})
            if not rf: continue
            fi = sorted(rf.get('feature_importance', {}).items(), key=lambda x: x[1], reverse=True)
            html = '<table><thead><tr><th>Indikator Sosial</th><th>FI</th></tr></thead><tbody>'
            for f, v in fi: html += f'<tr><td>{self.predictor_short_names.get(f, f)}</td><td>{v:.4f}</td></tr>'
            html += f'<tr><td><strong>R² Disesuaikan</strong></td><td>{rf.get("adj_r2", 0):.4f}</td></tr>'
            html += f'<tr><td><strong>MAE</strong></td><td>{rf.get("mae", 0):.4f}</td></tr></tbody></table>'
            tables[target] = html
        return tables

    def generate_lr_slope_table(self):
        tables = {}
        for target in self.target_cols:
            lr = self.results.get('linear_regression', {}).get(target, {})
            if not lr: continue
            p_vals = lr.get('p_values', {})
            # Prepare data with significance flag for sorting
            data_to_sort = []
            for f, c in lr.get('coefficients', {}).items():
                p = p_vals.get(f, 1.0)
                data_to_sort.append({
                    'f': f,
                    'c': c,
                    'p': p,
                    'sig_val': 1 if p < 0.05 else 0
                })
            
            # Sort: Significance (1 first), then coefficient value (descending)
            sorted_items = sorted(data_to_sort, key=lambda x: (x['sig_val'], x['c']), reverse=True)
            
            html = '<table><thead><tr><th>Indikator Sosial</th><th>Koefisien</th><th>P-Value</th><th>Sig*</th></tr></thead><tbody>'
            for item in sorted_items:
                f, c, p = item['f'], item['c'], item['p']
                sig = 'Ya' if p < 0.05 else 'Tidak'
                html += f'<tr><td>{self.predictor_short_names.get(f, f)}</td><td>{c:.6f}</td><td>{p:.6f}</td><td>{sig}</td></tr>'
            html += f'<tr><td colspan="4"><strong>R² Disesuaikan: {lr.get("adj_r2", 0):.4f} | MAE: {lr.get("mae", 0):.4f}</strong></td></tr></tbody></table>'
            tables[target] = html
        return tables

    def _choose_plot_axes(self, target_results, available_columns):
        selected = [c for c in target_results.get('selected_features', []) if c in available_columns]
        correlations = target_results.get('feature_correlations', {})

        if selected:
            ranked = sorted(selected, key=lambda c: abs(correlations.get(c, 0)), reverse=True)
        else:
            ranked = []

        for col, _corr in sorted(correlations.items(), key=lambda item: abs(item[1]), reverse=True):
            if col in available_columns and col not in ranked:
                ranked.append(col)

        for col in self.predictor_cols_clustering:
            if col in available_columns and col not in ranked:
                ranked.append(col)

        return ranked[:2]

    def generate_clustering_visualizations(self, method='kmeans'):
        """Generate interactive 2D cluster graphs using real feature axes."""
        graphs = {}
        results = self.results.get('per_target_clustering', {})
        if self.df_clustering is None:
            return {}
        
        for target in self.target_cols:
            target_results = results.get(target, {})
            t_data = target_results.get(method, {})
            if not t_data: continue
            
            t_col = f"{target}_mean"
            df_cols = list(dict.fromkeys(['provinsi'] + self.predictor_cols_clustering + [t_col]))
            df = self.df_clustering[df_cols].dropna()
            labels = np.array(t_data.get('labels', []), dtype=int)

            result_provinces = target_results.get('provinces', [])
            if result_provinces:
                df = df.set_index('provinsi').reindex(result_provinces).reset_index()
                valid_rows = ~df[self.predictor_cols_clustering + [t_col]].isna().any(axis=1)
                df = df[valid_rows].reset_index(drop=True)
                labels = labels[valid_rows.to_numpy()]
            
            if len(df) != len(labels):
                logger.warning(f"Length mismatch for {target} ({method}): df={len(df)}, labels={len(labels)}")
                continue

            plot_cols = self._choose_plot_axes(target_results, df.columns)
            if len(plot_cols) < 2:
                logger.warning(f"Not enough plot columns for {target} ({method})")
                continue

            x_col, y_col = plot_cols
            x_values = df[x_col].astype(float).to_numpy()
            y_values = df[y_col].astype(float).to_numpy()
            x_min, x_max = np.nanmin(x_values), np.nanmax(x_values)
            y_min, y_max = np.nanmin(y_values), np.nanmax(y_values)
            x_span = x_max - x_min if x_max != x_min else 1
            y_span = y_max - y_min if y_max != y_min else 1
            colors = ['#2f6fb0', '#d95f02', '#1b9e77', '#7570b3', '#e7298a',
                      '#66a61e', '#e6ab02', '#a6761d', '#1f9fd0', '#666666']

            points_html = []
            centroid_html = []
            cluster_labels = self._get_cluster_order_from_labels(labels)

            for idx, row in df.reset_index(drop=True).iterrows():
                label = int(labels[idx])
                x_val = float(row[x_col])
                y_val = float(row[y_col])
                x_pct = 7 + ((x_val - x_min) / x_span * 86)
                y_pct = 93 - ((y_val - y_min) / y_span * 86)
                jitter = ((idx % 5) - 2) * 0.35
                x_pct = min(96, max(4, x_pct + jitter))
                y_pct = min(96, max(4, y_pct - jitter))
                color = '#777777' if label == -1 else colors[label % len(colors)]
                cluster_name = self._cluster_display_name(label)
                tooltip = (
                    f"{row['provinsi']} | {cluster_name} | "
                    f"{self.target_names.get(target, target)}: {row[t_col]:.2f} | "
                    f"{self.predictor_short_names.get(x_col, x_col)}: {x_val:.2f} | "
                    f"{self.predictor_short_names.get(y_col, y_col)}: {y_val:.2f}"
                )
                points_html.append(
                    '<span class="cluster-point" '
                    f'style="left:{x_pct:.2f}%; top:{y_pct:.2f}%; background:{color};" '
                    f'data-tooltip="{escape(tooltip, quote=True)}" '
                    f'aria-label="{escape(tooltip, quote=True)}"></span>'
                )

            if method == 'kmeans':
                for label in cluster_labels:
                    if label == -1:
                        continue
                    mask = labels == label
                    x_mean = x_values[mask].mean()
                    y_mean = y_values[mask].mean()
                    x_pct = 7 + ((x_mean - x_min) / x_span * 86)
                    y_pct = 93 - ((y_mean - y_min) / y_span * 86)
                    centroid_html.append(
                        '<span class="cluster-centroid" '
                        f'style="left:{x_pct:.2f}%; top:{y_pct:.2f}%;" '
                        f'data-tooltip="Rata-rata {self._cluster_display_name(label)} pada dua sumbu tampilan"></span>'
                    )

            legend_items = []
            for label in cluster_labels:
                color = '#777777' if label == -1 else colors[label % len(colors)]
                count = int((labels == label).sum())
                legend_items.append(
                    '<span class="legend-item">'
                    f'<span class="legend-swatch" style="background:{color};"></span>'
                    f'{self._cluster_display_name(label)} ({count})</span>'
                )
            if method == 'kmeans':
                legend_items.append('<span class="legend-item"><span class="centroid-legend">X</span>Rata-rata kluster</span>')

            x_name = self.predictor_short_names.get(x_col, x_col)
            y_name = self.predictor_short_names.get(y_col, y_col)
            selected_feature_names = ', '.join(
                self.predictor_short_names.get(c, c)
                for c in target_results.get('selected_features', [])
            )
            graphs[target] = f'''
            <div class="cluster-viz" role="img" aria-label="Visualisasi {method.upper()} {self.target_names[target]}">
                <div class="cluster-viz-head">
                    <span>X: {escape(x_name)}</span>
                    <span>Y: {escape(y_name)}</span>
                </div>
                <div class="cluster-plot">
                    <span class="axis-label axis-x">{escape(x_name)}</span>
                    <span class="axis-label axis-y">{escape(y_name)}</span>
                    {''.join(points_html)}
                    {''.join(centroid_html)}
                </div>
                <div class="cluster-legend">{''.join(legend_items)}</div>
                <div class="cluster-features">
                    Sumbu X = {escape(x_name)}. Sumbu Y = {escape(y_name)}.<br>
                    Kedua sumbu dipilih dari fitur terpilih dengan korelasi terkuat terhadap target. Label kluster tetap berasal dari model {method.upper()} yang berjalan pada seluruh fitur terpilih.<br>
                    Fitur model: {escape(selected_feature_names or '-')}
                </div>
            </div>
            '''
        return graphs

    def generate_linear_regression_graphs(self):
        graphs = {}
        if self.df_timeseries is None:
            return graphs

        for target in self.target_cols:
            df = self.df_timeseries[self.predictor_cols + [target]].dropna()
            if len(df) < 5: continue
            
            X = df[self.predictor_cols]
            y = df[target].values
            
            # Use same scaling as ML pipeline if configured
            pred_cfg = self.ml_config.get('prediction', {})
            if pred_cfg.get('use_scaling', False):
                scaler_type = pred_cfg.get('scaler_type', 'robust')
                scaler = RobustScaler() if scaler_type == 'robust' else StandardScaler()
                X = scaler.fit_transform(X)
            
            lr = LinearRegression().fit(X, y); y_p = lr.predict(X)
            fig, ax = plt.subplots(figsize=(10, 8))
            ax.scatter(y, y_p, alpha=0.6, s=80, color='blue')
            ax.plot([y.min(), y.max()], [y.min(), y.max()], 'r--', lw=1)
            ax.set_title(f'Regresi Linear: {self.target_names[target]}')
            ax.set_xlabel('Aktual'); ax.set_ylabel('Prediksi')
            graphs[target] = self.fig_to_base64(fig)
        return graphs

    def generate_kmeans_summary_table(self):
        """K-Means summary table (Indikator, jumlah K, inertia, silhouette)"""
        html = '<table><thead><tr><th>Indikator</th><th>Jumlah K</th><th>Inertia</th><th>Silhouette</th></tr></thead><tbody>'
        for t in self.target_cols:
            k = self.results.get('per_target_clustering', {}).get(t, {}).get('kmeans', {})
            if not k: continue
            
            opt_k = k.get("optimal_k", k.get("n_clusters", "N/A"))
            inertia = k.get("inertia")
            if inertia is None and "inertias" in k and "k_range" in k:
                try:
                    idx = k["k_range"].index(opt_k)
                    inertia = k["inertias"][idx]
                except: inertia = "N/A"
            
            sil = k.get("final_silhouette", k.get("silhouette", 0))
            
            html += f'<tr><td>{self.target_names.get(t, t)}</td>'
            html += f'<td>{opt_k}</td>'
            html += f'<td>{f"{inertia:.2f}" if isinstance(inertia, (int, float)) else inertia}</td>'
            html += f'<td>{sil:.4f}</td></tr>'
        html += '</tbody></table>'
        return html

    def generate_hdbscan_summary_table(self):
        """HDBSCAN summary table (indikator, jumlah kluster, noise, silhouette)"""
        html = '<table><thead><tr><th>Indikator</th><th>Jumlah Kluster</th><th>Noise</th><th>Silhouette</th></tr></thead><tbody>'
        for t in self.target_cols:
            h = self.results.get('per_target_clustering', {}).get(t, {}).get('hdbscan', {})
            if not h: continue
            
            n_clusters = h.get("n_clusters", "N/A")
            noise = h.get("noise_ratio", 0)
            sil = h.get("silhouette", h.get("silhouette_score", 0))
            
            html += f'<tr><td>{self.target_names.get(t, t)}</td>'
            html += f'<td>{n_clusters}</td>'
            html += f'<td>{noise:.4f}</td>'
            html += f'<td>{sil:.4f}</td></tr>'
        html += '</tbody></table>'
        return html

    def generate_rf_summary_table(self):
        """Random Forest summary table (indikator, R^2 disesuaikan, MAE, 3 fitur penting)"""
        html = '<table><thead><tr><th>Indikator</th><th>R² Disesuaikan</th><th>MAE</th><th>3 Fitur Paling Penting</th></tr></thead><tbody>'
        for t in self.target_cols:
            rf = self.results.get('random_forest', {}).get(t, {})
            if not rf: continue
            
            adj_r2 = rf.get("adj_r2", 0)
            mae = rf.get("mae", 0)
            fi = sorted(rf.get('feature_importance', {}).items(), key=lambda x: x[1], reverse=True)
            top_3 = [self.predictor_short_names.get(f, f) for f, v in fi[:3]]
            top_3_str = ", ".join(top_3)
            
            html += f'<tr><td>{self.target_names.get(t, t)}</td>'
            html += f'<td>{adj_r2:.4f}</td>'
            html += f'<td>{mae:.4f}</td>'
            html += f'<td>{top_3_str}</td></tr>'
        html += '</tbody></table>'
        return html

    def generate_lr_summary_table(self):
        """Linear Regression summary table (indikator, R^2 disesuaikan, MAE, 3 fitur signifikan)"""
        html = '<table><thead><tr><th>Indikator</th><th>R² Disesuaikan</th><th>MAE</th><th>3 Fitur Signifikan</th></tr></thead><tbody>'
        for t in self.target_cols:
            lr = self.results.get('linear_regression', {}).get(t, {})
            if not lr: continue
            
            adj_r2 = lr.get("adj_r2", 0)
            mae = lr.get("mae", 0)
            p_vals = lr.get('p_values', {})
            coeffs = lr.get('coefficients', {})
            
            # Filter significant features (p < 0.05)
            sig_features = []
            for f, p in p_vals.items():
                if p < 0.05:
                    sig_features.append(f)
            
            # Sort by absolute coefficient value
            sig_features_sorted = sorted(sig_features, key=lambda f: abs(coeffs.get(f, 0)), reverse=True)
            
            top_3 = []
            for f in sig_features_sorted[:3]:
                c = coeffs.get(f, 0)
                sign = "(+)" if c > 0 else "(-)"
                name = self.predictor_short_names.get(f, f)
                top_3.append(f"{name} {sign}")
            
            top_3_str = ", ".join(top_3) if top_3 else "-"
            
            html += f'<tr><td>{self.target_names.get(t, t)}</td>'
            html += f'<td>{adj_r2:.4f}</td>'
            html += f'<td>{mae:.4f}</td>'
            html += f'<td>{top_3_str}</td></tr>'
        html += '</tbody></table>'
        return html

    def generate_html(self, output_file='reports/ml_analysis_report_enhanced.html'):
        """Generate final HTML with booktabs style"""
        logger.info("Building HTML report with booktabs style...")
        
        heatmap = self.generate_correlation_heatmap()
        yearly_corr = self.generate_yearly_correlation_tables()
        km_graphs = self.generate_clustering_visualizations('kmeans')
        hdb_graphs = self.generate_clustering_visualizations('hdbscan')
        lr_graphs = self.generate_linear_regression_graphs()
        lr_tables = self.generate_lr_slope_table()
        rf_tables = self.generate_rf_feature_importance_tables()
        
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        heatmap_html = (
            f'<img src="data:image/png;base64,{heatmap}">'
            if heatmap else '<p>Data heatmap tidak tersedia tanpa koneksi database.</p>'
        )
        
        html = f"""<!DOCTYPE html>
<html lang="id">
<head>
    <meta charset="UTF-8">
    <title>Laporan Analisis ML</title>
    <style>
        body {{ font-family: "Times New Roman", Times, serif; max-width: 1000px; margin: 40px auto; color: black; line-height: 1.4; background: white; }}
        h1 {{ text-align: center; text-transform: uppercase; margin-bottom: 30px; padding-bottom: 10px; border-bottom: 2px solid black; }}
        h2 {{ margin-top: 40px; border-bottom: 1px solid black; padding-bottom: 5px; }}
        h3 {{ margin-top: 25px; }}
        .section {{ margin-bottom: 40px; }}
        table {{ width: 100%; border-collapse: collapse; margin: 10px 0; border-top: 2px solid black; border-bottom: 2px solid black; font-size: 13px; }}
        th, td {{ padding: 6px 4px; text-align: center; border: none; }}
        thead {{ border-bottom: 1px solid black; }}
        th {{ font-weight: bold; }}
        .graph-container {{ text-align: center; margin: 15px 0; }}
        .graph-container img {{ max-width: 85%; height: auto; }}
        .tables-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }}
        .cluster-viz {{ margin: 10px 0 18px; text-align: left; }}
        .cluster-viz-head {{ display: flex; justify-content: space-between; font-size: 12px; margin-bottom: 4px; }}
        .cluster-plot {{ position: relative; width: 100%; aspect-ratio: 4 / 3; border: 1px solid #444; background: linear-gradient(#f3f3f3 1px, transparent 1px), linear-gradient(90deg, #f3f3f3 1px, transparent 1px); background-size: 20% 20%; overflow: visible; }}
        .cluster-membership-plot {{ background: linear-gradient(90deg, #f7f7f7 1px, transparent 1px); background-size: 20% 100%; }}
        .cluster-point {{ position: absolute; width: 12px; height: 12px; border: 1px solid #111; border-radius: 50%; transform: translate(-50%, -50%); cursor: pointer; z-index: 2; }}
        .cluster-point:hover {{ width: 18px; height: 18px; z-index: 20; }}
        .cluster-point:hover::after, .cluster-centroid:hover::after {{ content: attr(data-tooltip); position: absolute; left: 14px; top: -8px; min-width: 190px; max-width: 260px; padding: 7px 9px; background: #111; color: #fff; font-family: Arial, sans-serif; font-size: 12px; line-height: 1.3; border-radius: 3px; white-space: normal; box-shadow: 0 2px 8px rgba(0,0,0,0.25); pointer-events: none; }}
        .cluster-centroid {{ position: absolute; color: #b00000; font-family: Arial, sans-serif; font-size: 20px; font-weight: bold; line-height: 1; transform: translate(-50%, -50%); cursor: pointer; z-index: 3; }}
        .cluster-centroid::before {{ content: "X"; }}
        .cluster-legend {{ display: flex; flex-wrap: wrap; gap: 8px 14px; margin-top: 8px; font-family: Arial, sans-serif; font-size: 12px; }}
        .legend-item {{ display: inline-flex; align-items: center; gap: 5px; }}
        .legend-swatch {{ display: inline-block; width: 10px; height: 10px; border: 1px solid #111; border-radius: 50%; }}
        .centroid-legend {{ color: #b00000; font-weight: bold; font-family: Arial, sans-serif; }}
        .cluster-features {{ margin-top: 6px; font-size: 11px; color: #333; text-align: left; }}
        .axis-label {{ position: absolute; font-size: 11px; color: #333; background: rgba(255,255,255,0.85); padding: 1px 3px; }}
        .axis-x {{ left: 50%; bottom: 4px; transform: translateX(-50%); }}
        .axis-y {{ left: 4px; top: 50%; transform: translateY(-50%) rotate(-90deg); transform-origin: left center; }}
        .cluster-column-label {{ position: absolute; top: 4px; text-align: center; font-family: Arial, sans-serif; font-size: 11px; color: #333; }}
        .cluster-overview-table .members-cell {{ text-align: left; line-height: 1.35; }}
        .timestamp {{ margin-top: 50px; font-size: 11px; text-align: right; font-style: italic; border-top: 1px solid #ccc; padding-top: 10px; }}
        .note {{ border: 1px solid black; padding: 12px; background: #fff; margin: 15px 0; font-size: 14px; }}
        @media (max-width: 800px) {{
            body {{ margin: 20px 12px; }}
            .tables-grid {{ grid-template-columns: 1fr; }}
            .cluster-point:hover::after, .cluster-centroid:hover::after {{ left: -95px; top: 18px; }}
        }}
    </style>
</head>
<body>
    <h1>Laporan Analisis Machine Learning</h1>

    <div class="note"><strong>Metodologi:</strong> Klustering dilakukan independen per indikator pendidikan menggunakan fitur terpilih berbasis korelasi dan penskalaan RobustScaler. Fitur terpilih ditandai dengan <span style="color: green;">teks hijau</span> pada tabel statistik kluster; bila tidak ada fitur yang melewati ambang korelasi, pipeline memakai fitur dengan korelasi terkuat sebagai fallback.</div>

    <h2>1. Heatmap Korelasi Spearman</h2>
    <div class="section"><div class="graph-container">{heatmap_html}</div></div>

    <h2>2. Korelasi Tahunan (Tingkat Level)</h2>
    <div class="section">
        <div class="tables-grid">
        {''.join([f'<div><h3>Target: {self.target_names[t]}</h3>{yearly_corr[t]}</div>' for t in self.target_cols if t in yearly_corr])}
        </div>
    </div>

    <h2>3. Korelasi Fitur Trend (Laju Perubahan)</h2>
    <div class="section">
        {self.generate_trend_correlation_table()}
    </div>

    <h2>4. Klustering Independen per Target Pendidikan</h2>
    <div class="section">
        {''.join([f'''
        <div style="border-top: 1px solid black; margin-top: 30px; padding-top: 15px;">
            <h3>Target Indikator: {self.target_names[t]}</h3>
            <div class="tables-grid">
                <div><h4>K-Means Metrics</h4>{self.generate_kmeans_metrics_table(t)}</div>
                <div><h4>HDBSCAN Metrics</h4>{self.generate_hdbscan_metrics_table(t)}</div>
            </div>
            <div class="tables-grid">
                <div class="graph-container"><h4>Visualisasi K-Means</h4>{km_graphs.get(t, '')}</div>
                <div class="graph-container"><h4>Visualisasi HDBSCAN</h4>{hdb_graphs.get(t, '')}</div>
            </div>
            <h4>Ringkasan Anggota K-Means ({self.target_names[t]})</h4>{self.generate_cluster_overview_table('kmeans', t)}
            <h4>Ringkasan Anggota HDBSCAN ({self.target_names[t]})</h4>{self.generate_cluster_overview_table('hdbscan', t)}
            <h4>Statistik K-Means ({self.target_names[t]})</h4>{self.generate_cluster_statistics_table('kmeans', t)}
            <h4>Statistik HDBSCAN ({self.target_names[t]})</h4>{self.generate_cluster_statistics_table('hdbscan', t)}
        </div>
        ''' for t in self.target_cols])}
    </div>

    <h2>5. Analisis Prediksi dan Regresi</h2>
    <div class="section">
        {''.join([f'''
        <div style="margin-top: 25px;">
            <h3>Target: {self.target_names[t]}</h3>
            <div class="tables-grid">
                <div><h4>Random Forest Importance</h4>{rf_tables.get(t, '')}</div>
                <div><h4>Regresi Linear Coefficients</h4>{lr_tables.get(t, '')}</div>
            </div>
            <div class="graph-container"><h4>Plot Prediksi Regresi Linear</h4><img src="data:image/png;base64,{lr_graphs.get(t, '')}"></div>
        </div>
        ''' for t in self.target_cols])}
    </div>

    <h2>6. Ringkasan Performa Model</h2>
    <div class="section">
        <h3>Ringkasan Klustering K-Means</h3>
        {self.generate_kmeans_summary_table()}
        
        <h3>Ringkasan Klustering HDBSCAN</h3>
        {self.generate_hdbscan_summary_table()}
        
        <h3>Ringkasan Random Forest</h3>
        {self.generate_rf_summary_table()}
        
        <h3>Ringkasan Regresi Linear</h3>
        {self.generate_lr_summary_table()}
    </div>

    <div class="timestamp">Laporan Dibuat: {timestamp}</div>
</body>
</html>
"""
        with open(output_file, 'w', encoding='utf-8') as f: f.write(html)
        return output_file

if __name__ == "__main__":
    EnhancedReportGenerator().generate_html()
