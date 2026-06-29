"""
Interactive Dashboard Generator.

Produces reports/dashboard.html - a single-file, offline, interactive
dashboard summarizing the ML pipeline results (per-target clustering,
regression, Spearman correlation) with a sidebar, KPI cards, and
vanilla-JS/SVG charts. No external JS/CSS assets; the file works offline.

Data sources:
  - reports/ml_results.json  (pre-computed by the ML pipeline; always required)
  - data/*.csv               (raw CSVs; used only for the per-province values
                              that feed the scatter plot and Data Explorer)

Self-contained: depends only on pandas + numpy (no seaborn/matplotlib/
sklearn/sqlalchemy), so it runs in a minimal environment. The ML results
are consumed from JSON; only light province-level aggregation is rebuilt
from CSV so the dashboard stays interactive without a database.

Usage:
    python dashboard_generator.py
    python main.py --phase dashboard
"""

import json
import logging
from datetime import datetime

import numpy as np
import pandas as pd

try:
    from utils.logger import get_logger
    logger = get_logger(__name__)
except Exception:
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)

# Regression / Spearman predictor keys (raw, 8 predictors in time-series).
PREDICTORS = [
    {"key": "ekonomi_miskin",             "name": "Persentase Penduduk Miskin",      "unit": "%",         "category": "Ekonomi"},
    {"key": "ekonomi_upah_rata_rata",     "name": "Upah Rata-rata",                  "unit": "Rupiah/Jam","category": "Ekonomi"},
    {"key": "kesehatan_ahh_perempuan",    "name": "Angka Harapan Hidup (Perempuan)", "unit": "tahun",     "category": "Kesehatan"},
    {"key": "kesehatan_unmet_layanan",    "name": "Unmet Need Layanan Kesehatan",    "unit": "%",         "category": "Kesehatan"},
    {"key": "ketenagakerjaan_formal",     "name": "Pekerja Formal",                  "unit": "%",         "category": "Ketenagakerjaan"},
    {"key": "ketenagakerjaan_informal",   "name": "Pekerja Informal",                "unit": "%",         "category": "Ketenagakerjaan"},
    {"key": "teknologi_telepon_seluler",  "name": "Memiliki Telepon Seluler",        "unit": "%",         "category": "Teknologi"},
    {"key": "teknologi_internet",         "name": "Mengakses Internet",              "unit": "%",         "category": "Teknologi"},
]

# Map regression predictor key -> clustering "_mean" key (differs for some).
CLUSTER_MEAN_KEY = {
    "ekonomi_miskin":            "ekonomi_miskin_mean",
    "ekonomi_upah_rata_rata":    "ekonomi_upah_mean",
    "kesehatan_ahh_perempuan":   "kesehatan_ahh_perempuan_mean",
    "kesehatan_unmet_layanan":   "kesehatan_unmet_mean",
    "ketenagakerjaan_formal":    "ketenagakerjaan_formal_mean",
    "ketenagakerjaan_informal":  "ketenagakerjaan_informal_mean",
    "teknologi_telepon_seluler": "teknologi_telepon_mean",
    "teknologi_internet":        "teknologi_internet_mean",
}

TARGETS = [
    {"key": "apm_sd",                   "name": "APM SD",  "long": "Angka Partisipasi Murni SD",          "unit": "%"},
    {"key": "apm_smp",                  "name": "APM SMP", "long": "Angka Partisipasi Murni SMP",         "unit": "%"},
    {"key": "apm_sm",                   "name": "APM SM",  "long": "Angka Partisipasi Murni SM",          "unit": "%"},
    {"key": "apk_pt",                   "name": "APK PT",  "long": "Angka Partisipasi Kasar Perguruan Tinggi", "unit": "%"},
    {"key": "rata_rata_lama_sekolah",   "name": "RLS",     "long": "Rata-rata Lama Sekolah",              "unit": "tahun"},
]

CLUSTER_COLORS = ['#4f46e5', '#d97706', '#0d9488', '#be123c', '#6d28d9',
                  '#15803d', '#b45309', '#1e40af', '#9333ea', '#64748b']

_CANONICAL_PROVINCES = [
    "ACEH", "SUMATERA UTARA", "SUMATERA BARAT", "RIAU", "JAMBI",
    "SUMATERA SELATAN", "BENGKULU", "LAMPUNG", "KEP. BANGKA BELITUNG",
    "KEP. RIAU", "DKI JAKARTA", "JAWA BARAT", "JAWA TENGAH",
    "DI YOGYAKARTA", "JAWA TIMUR", "BANTEN", "BALI",
    "NUSA TENGGARA BARAT", "NUSA TENGGARA TIMUR", "KALIMANTAN BARAT",
    "KALIMANTAN TENGAH", "KALIMANTAN SELATAN", "KALIMANTAN TIMUR",
    "KALIMANTAN UTARA", "SULAWESI UTARA", "SULAWESI TENGAH",
    "SULAWESI SELATAN", "SULAWESI TENGGARA", "GORONTALO",
    "SULAWESI BARAT", "MALUKU", "MALUKU UTARA", "PAPUA BARAT", "PAPUA",
]


def _fmt(v, dec=2):
    if v is None: return None
    try:
        return round(float(v), dec)
    except (TypeError, ValueError):
        return None


def _choose_plot_axes(target_results):
    """Pick top-2 features by abs correlation for the scatter axes."""
    correlations = target_results.get('feature_correlations', {})
    selected = target_results.get('selected_features', [])
    ranked = sorted(selected, key=lambda c: abs(correlations.get(c, 0)), reverse=True)
    for col, _ in sorted(correlations.items(), key=lambda it: abs(it[1]), reverse=True):
        if col not in ranked:
            ranked.append(col)
    return ranked[:2] if len(ranked) >= 2 else ranked


# --- Lightweight pandas-only province aggregator (mirrors dm.agg_province_ml).-
def _read_province_year_values(filepath, years, data_start_idx, col_start=1):
    raw = pd.read_csv(filepath, header=None)
    provs = raw.iloc[data_start_idx:, 0].astype(str).str.strip()
    vals = raw.iloc[data_start_idx:, col_start:col_start + len(years)].copy()
    vals.columns = years
    vals['provinsi'] = provs.values
    vals = vals[vals['provinsi'].isin(_CANONICAL_PROVINCES)]
    long_df = vals.melt(id_vars='provinsi', var_name='tahun', value_name='nilai')
    long_df['nilai'] = pd.to_numeric(long_df['nilai'], errors='coerce')
    return long_df.dropna(subset=['nilai'])


def _read_simple_csv(filename):
    raw = pd.read_csv(f'data/{filename}', header=None)
    year_row = data_start = None
    for idx in (1, 2):
        cand = raw.iloc[idx, 1:].fillna('').astype(str)
        if cand.str.isnumeric().sum() >= 4:
            year_row, data_start = idx, idx + 1
            break
    if year_row is None:
        raise ValueError(f'Cannot detect year row in {filename}')
    years = [int(y) for y in raw.iloc[year_row, 1:6].tolist()]
    return _read_province_year_values(f'data/{filename}', years, data_start)


def _read_poverty_csv():
    raw = pd.read_csv('data/Ekonomi_persentase_penduduk_miskin.csv', header=None)
    years = [int(y) for y in raw.iloc[2, 1:6].tolist()]
    return _read_province_year_values('data/Ekonomi_persentase_penduduk_miskin.csv', years, 4)


def _read_apm_csv(col_start):
    raw = pd.read_csv('data/Pendidikan_APM_provinsi.csv', header=None)
    years = [int(y) for y in raw.iloc[2, col_start:col_start + 5].tolist()]
    return _read_province_year_values('data/Pendidikan_APM_provinsi.csv', years, 3, col_start)


def _read_ahh_csv(col_start):
    raw = pd.read_csv('data/Kesehatan_angka_harapan_hidup.csv', header=None)
    years = [int(y) for y in raw.iloc[2, col_start:col_start + 5].tolist()]
    return _read_province_year_values('data/Kesehatan_angka_harapan_hidup.csv', years, 3, col_start)


def _mean_and_trend(df, years):
    scoped = df[df['tahun'].isin(years)]
    mean_s = scoped.groupby('provinsi')['nilai'].mean()
    first, last = years[0], years[-1]
    f = scoped[scoped['tahun'] == first].set_index('provinsi')['nilai']
    l = scoped[scoped['tahun'] == last].set_index('provinsi')['nilai']
    trend = ((l - f) / f * 100).replace([np.inf, -np.inf], np.nan)
    return mean_s, trend


def _assign_mt(out, prefix, df, years):
    mean_s, trend = _mean_and_trend(df, years)
    out[f'{prefix}_mean'] = out['provinsi'].map(mean_s)
    out[f'{prefix}_trend_pct'] = out['provinsi'].map(trend)


def _assign_mean(out, col, df, years):
    scoped = df[df['tahun'].isin(years)]
    out[col] = out['provinsi'].map(scoped.groupby('provinsi')['nilai'].mean())


def build_clustering_df():
    """Rebuild dm.agg_province_ml equivalent from raw CSVs (pandas-only)."""
    out = pd.DataFrame({'provinsi': sorted(_CANONICAL_PROVINCES)})
    yrs = [2020, 2021, 2022, 2023, 2024]
    _assign_mt(out, 'ekonomi_miskin', _read_poverty_csv(), [2021, 2022, 2023, 2024, 2025])
    _assign_mt(out, 'ekonomi_upah', _read_simple_csv('Ekonomi_upah_rata-rata.csv'), yrs)
    _assign_mt(out, 'kesehatan_ahh_perempuan', _read_ahh_csv(6), yrs)
    _assign_mt(out, 'kesehatan_unmet', _read_simple_csv('Kesehatan_unmet_layanan_kesehatan.csv'), yrs)
    _assign_mt(out, 'ketenagakerjaan_formal', _read_simple_csv('Ketenagakerjaan_formal.csv'), yrs)
    _assign_mt(out, 'ketenagakerjaan_informal', _read_simple_csv('Ketenagakerjaan_informal.csv'), yrs)
    _assign_mt(out, 'teknologi_telepon', _read_simple_csv('Teknologi_memiliki_telepon_seluler.csv'), yrs)
    _assign_mt(out, 'teknologi_internet', _read_simple_csv('Teknologi_mengakses_internet.csv'), yrs)
    _assign_mean(out, 'apm_sd_mean', _read_apm_csv(1), yrs)
    _assign_mean(out, 'apm_smp_mean', _read_apm_csv(6), yrs)
    _assign_mean(out, 'apm_sm_mean', _read_apm_csv(11), yrs)
    _assign_mean(out, 'apk_pt_mean', _read_simple_csv('Pendidikan_APK_PT_provinsi.csv'), yrs)
    _assign_mean(out, 'rata_rata_lama_sekolah_mean', _read_simple_csv('Pendidikan_Rata-rata_lama_sekolah.csv'), yrs)
    return out


class DashboardGenerator:
    def __init__(self, ml_results_path='reports/ml_results.json'):
        try:
            with open(ml_results_path, 'r') as f:
                self.results = json.load(f)
            logger.info(f"Loaded ML results from {ml_results_path}")
        except Exception as e:
            logger.error(f"Could not load ML results from {ml_results_path}: {e}")
            self.results = {}
        try:
            self.df = build_clustering_df()
            logger.info(f"Built province aggregation from CSV: {self.df.shape}")
        except Exception as e:
            logger.warning(f"Could not build province data from CSV ({e}); "
                           "scatter/explorer will be limited")
            self.df = None
        self.target_keys = [t['key'] for t in TARGETS]
        self.pred_keys = [p['key'] for p in PREDICTORS]
        self._current_target = self.target_keys[0] if self.target_keys else None

    def _short(self, key):
        # Human label for any predictor key variant (raw or _mean/_trend_pct).
        base = key
        for suf in ('_mean', '_trend_pct'):
            if base.endswith(suf):
                base = base[:-len(suf)]
        base = {'ekonomi_upah': 'ekonomi_upah_rata_rata',
                'kesehatan_unmet': 'kesehatan_unmet_layanan',
                'teknologi_telepon': 'teknologi_telepon_seluler'}.get(base, base)
        for p in PREDICTORS:
            if p['key'] == base:
                return p['name']
        return key

    def _method_block(self, m, tk):
        stats = m.get('stats', {})
        cluster_rows = []
        for sk in sorted([k for k in stats if k.startswith('cluster_')],
                         key=lambda x: int(x.split('_')[1])):
            s = stats[sk]
            label = int(sk.split('_')[1])
            means = s.get('means', {})
            cluster_rows.append({
                "label": label,
                "name": f"Kluster {label}",
                "n_members": s.get('n_members', 0),
                "target_mean": _fmt(means.get(f"{tk}_mean")),
                "predictor_means": {
                    pk: _fmt(means.get(CLUSTER_MEAN_KEY[pk])) for pk in self.pred_keys
                },
                "members": self._members(m, label),
            })
        if 'noise' in stats:
            s = stats['noise']
            means = s.get('means', {})
            cluster_rows.append({
                "label": -1, "name": "Noise",
                "n_members": s.get('n_members', 0),
                "target_mean": _fmt(means.get(f"{tk}_mean")),
                "predictor_means": {
                    pk: _fmt(means.get(CLUSTER_MEAN_KEY[pk])) for pk in self.pred_keys
                },
                "members": self._members(m, -1),
            })
        return {
            "n_clusters": m.get('n_clusters'),
            "n_noise": m.get('n_noise'),
            "noise_ratio": _fmt(m.get('noise_ratio'), 4),
            "inertia": _fmt(m.get('inertia'), 2),
            "silhouette": _fmt(m.get('silhouette', m.get('silhouette_score')), 4),
            "labels": [int(x) for x in m.get('labels', [])],
            "clusters": cluster_rows,
        }

    def _members(self, method_block, label):
        labels = method_block.get('labels', [])
        provinces = self.results.get('per_target_clustering', {}).get(
            self._current_target, {}).get('provinces', [])
        return [provinces[i] for i, l in enumerate(labels) if int(l) == label]

    def build_regression(self):
        out = {}
        lr = self.results.get('linear_regression', {})
        rf = self.results.get('random_forest', {})
        for t in TARGETS:
            tk = t['key']
            l = lr.get(tk, {})
            r = rf.get(tk, {})
            out[tk] = {
                "target_name": t['name'],
                "linear": {
                    "r2": _fmt(l.get('r2'), 4), "adj_r2": _fmt(l.get('adj_r2'), 4),
                    "mae": _fmt(l.get('mae'), 4), "rmse": _fmt(l.get('rmse'), 4),
                    "intercept": _fmt(l.get('intercept'), 4),
                    "n_train": l.get('n_train'), "n_test": l.get('n_test'),
                    "coefficients": {k: _fmt(v, 4) for k, v in l.get('coefficients', {}).items()},
                    "p_values": {k: _fmt(v, 5) for k, v in l.get('p_values', {}).items()},
                },
                "rf": {
                    "r2": _fmt(r.get('r2'), 4), "adj_r2": _fmt(r.get('adj_r2'), 4),
                    "mae": _fmt(r.get('mae'), 4), "rmse": _fmt(r.get('rmse'), 4),
                    "n_train": r.get('n_train'), "n_test": r.get('n_test'),
                    "feature_importance": {k: _fmt(v, 4) for k, v in r.get('feature_importance', {}).items()},
                },
            }
        return out

    def build_spearman(self):
        sp = self.results.get('spearman', {})
        matrix = []
        for row in sp.get('correlation_matrix', []):
            target = row.get('target')
            cells = [{"predictor": pk, "value": _fmt(row.get(pk), 3)} for pk in self.pred_keys]
            matrix.append({"target": target, "cells": cells})
        corr = {}
        for tk, preds in sp.get('correlations', {}).items():
            corr[tk] = {
                pk: {"coefficient": _fmt(v.get('coefficient'), 3),
                     "p_value": _fmt(v.get('p_value'), 5),
                     "significant": bool(v.get('significant'))}
                for pk, v in preds.items()
            }
        return {"matrix": matrix, "correlations": corr}

    def build_province_data(self):
        """Per-province predictor means + target means for the Data Explorer."""
        if self.df is None:
            return {}
        out = {}
        df = self.df.set_index('provinsi') if 'provinsi' in self.df.columns else self.df
        for prov in df.index:
            row = df.loc[prov]
            out[prov] = {
                "predictors": {pk: _fmt(row.get(CLUSTER_MEAN_KEY[pk])) for pk in self.pred_keys},
                "targets": {tk: _fmt(row.get(f"{tk}_mean")) for tk in self.target_keys},
            }
        return out

    def build_payload(self):
        # _current_target hack so _members can find provinces; set per target below.
        ptc = self.results.get('per_target_clustering', {})
        clusters = {}
        for t in TARGETS:
            self._current_target = t['key']
            ptc_t = ptc.get(t['key'], {})
            axes = _choose_plot_axes(ptc_t)
            x_col, y_col = (axes + [None, None])[:2]
            provinces = ptc_t.get('provinces', [])
            points = []
            if self.df is not None and x_col and y_col and len(provinces) == len(ptc_t.get('kmeans', {}).get('labels', [])):
                df = self.df.set_index('provinsi') if 'provinsi' in self.df.columns else self.df
                for prov in provinces:
                    if prov in df.index:
                        row = df.loc[prov]
                        points.append({
                            "province": prov,
                            "x": _fmt(row.get(x_col)),
                            "y": _fmt(row.get(y_col)),
                            "target_value": _fmt(row.get(f"{t['key']}_mean")),
                        })
            clusters[t['key']] = {
                "target_name": t['name'],
                "target_long": t['long'],
                "selected_features": ptc_t.get('selected_features', []),
                "feature_correlations": {k: _fmt(v, 3) for k, v in ptc_t.get('feature_correlations', {}).items()},
                "plot": {
                    "x_key": x_col, "y_key": y_col,
                    "x_name": self._short(x_col) if x_col else None,
                    "y_name": self._short(y_col) if y_col else None,
                },
                "points": points,
                "kmeans": self._method_block(ptc_t.get('kmeans', {}), t['key']),
                "hdbscan": self._method_block(ptc_t.get('hdbscan', {}), t['key']),
            }
        return {
            "generated_at": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            "targets": TARGETS,
            "predictors": PREDICTORS,
            "provinces": sorted(self.build_province_data().keys()),
            "clustering": clusters,
            "regression": self.build_regression(),
            "spearman": self.build_spearman(),
            "province_data": self.build_province_data(),
            "colors": CLUSTER_COLORS,
        }

    def generate_html(self, output_file='reports/dashboard.html'):
        payload = self.build_payload()
        # Self-check: payload must carry the sections the dashboard renders.
        assert payload['clustering'], "clustering payload empty"
        assert payload['regression'], "regression payload empty"
        assert payload['spearman']['matrix'], "spearman matrix empty"

        json_blob = json.dumps(payload, ensure_ascii=False, allow_nan=False)
        html = _HTML_TEMPLATE.replace('__DATA__', json_blob)
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(html)
        logger.info(f"[OK] Dashboard generated: {output_file}")
        logger.info(f"     Targets: {len(payload['targets'])} | "
                    f"Provinces: {len(payload['provinces'])} | "
                    f"Clusters: {len(payload['clustering'])}")
        return output_file


# --------------------------------------------------------------------------- #
# HTML template: single-file, offline, vanilla JS + SVG. No external assets.
# --------------------------------------------------------------------------- #
_HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="id">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Dashboard Analisis ML - Indikator Regional Indonesia</title>
<style>
  :root{
    --bg:#f1f5f9; --panel:#ffffff; --ink:#0f172a; --muted:#64748b; --line:#e2e8f0;
    --accent:#4f46e5; --accent-soft:#eef2ff; --good:#0d9488; --bad:#be123c; --warn:#b45309;
    --sidebar:#0f172a; --sidebar-soft:#1e293b; --sidebar-ink:#cbd5e1;
    --radius:10px; --shadow:0 1px 3px rgba(15,23,42,.08),0 1px 2px rgba(15,23,42,.06);
  }
  *{box-sizing:border-box}
  html,body{margin:0;padding:0}
  body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
       background:var(--bg);color:var(--ink);line-height:1.5;font-size:14px}
  a{color:inherit;text-decoration:none}

  .layout{display:flex;min-height:100vh}
  .sidebar{width:248px;flex:0 0 248px;background:var(--sidebar);color:var(--sidebar-ink);
           position:sticky;top:0;height:100vh;overflow-y:auto;padding:18px 14px}
  .brand{color:#fff;font-weight:700;font-size:15px;line-height:1.25;padding:6px 8px 14px;
         border-bottom:1px solid var(--sidebar-soft);margin-bottom:12px}
  .brand small{display:block;color:var(--muted);font-weight:400;font-size:11px;margin-top:3px}
  .nav-btn{display:flex;align-items:center;gap:10px;width:100%;text-align:left;
           background:transparent;border:0;color:var(--sidebar-ink);padding:9px 10px;
           border-radius:7px;cursor:pointer;font-size:13.5px;margin-bottom:2px}
  .nav-btn:hover{background:var(--sidebar-soft);color:#fff}
  .nav-btn.active{background:var(--accent);color:#fff}
  .nav-ico{width:18px;height:18px;flex:0 0 18px;opacity:.9}
  .nav-hint{margin-top:auto;padding:12px 8px 4px;color:var(--muted);font-size:11px;line-height:1.45}

  .main{flex:1;min-width:0;padding:26px 32px 60px}
  .topbar{display:flex;align-items:center;justify-content:space-between;margin-bottom:20px;flex-wrap:wrap;gap:10px}
  .topbar h1{font-size:20px;margin:0;font-weight:700}
  .topbar .sub{color:var(--muted);font-size:12.5px}
  .pill{background:var(--panel);border:1px solid var(--line);border-radius:999px;
        padding:4px 11px;font-size:11.5px;color:var(--muted)}

  .section{display:none}
  .section.active{display:block}
  .section-title{font-size:16px;font-weight:700;margin:0 0 4px}
  .section-desc{color:var(--muted);font-size:13px;margin:0 0 18px}

  .cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:14px;margin-bottom:22px}
  .card{background:var(--panel);border:1px solid var(--line);border-radius:var(--radius);
        padding:15px 16px;box-shadow:var(--shadow)}
  .card .k{font-size:11px;color:var(--muted);text-transform:uppercase;letter-spacing:.04em}
  .card .v{font-size:24px;font-weight:700;margin-top:3px}
  .card .h{font-size:11.5px;color:var(--muted);margin-top:3px}

  .panel{background:var(--panel);border:1px solid var(--line);border-radius:var(--radius);
         padding:18px 18px 22px;box-shadow:var(--shadow);margin-bottom:18px}
  .panel h2{font-size:14.5px;margin:0 0 4px}
  .panel .pmeta{color:var(--muted);font-size:12px;margin:0 0 14px}

  .controls{display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin-bottom:14px}
  .seg{display:inline-flex;background:#eef2f7;border:1px solid var(--line);border-radius:8px;padding:3px}
  .seg button{border:0;background:transparent;padding:6px 12px;font-size:12.5px;border-radius:6px;cursor:pointer;color:var(--muted)}
  .seg button.active{background:var(--panel);color:var(--ink);box-shadow:var(--shadow);font-weight:600}
  .label{font-size:12px;color:var(--muted);margin-right:2px}

  table{width:100%;border-collapse:collapse;font-size:12.5px}
  thead th{background:#f8fafc;text-align:left;padding:8px 10px;font-weight:600;color:#334155;
           border-bottom:1px solid var(--line);position:sticky;top:0}
  tbody td{padding:7px 10px;border-bottom:1px solid var(--line);vertical-align:top}
  tbody tr:hover{background:#f8fafc}
  .num{text-align:right;font-variant-numeric:tabular-nums}
  .tag{display:inline-block;padding:2px 8px;border-radius:999px;font-size:11px;font-weight:600}
  .tag-good{background:#ccfbf1;color:#0f766e} .tag-bad{background:#ffe4e6;color:#be123c}
  .tag-warn{background:#fef3c7;color:#92400e} .tag-mut{background:#e2e8f0;color:#475569}
  .scroll{overflow-x:auto;max-height:340px;overflow-y:auto}

  .heatmap td.cell{width:54px;min-width:54px;text-align:center;font-size:11px;font-variant-numeric:tabular-nums}
  .matrix td.cell{width:74px;min-width:74px;text-align:center;font-size:11.5px;font-variant-numeric:tabular-nums;cursor:pointer}
  .matrix td.cell:hover{outline:2px solid var(--accent);outline-offset:-2px}
  .row-label{font-weight:600;white-space:nowrap}
  .members{font-size:11.5px;color:var(--muted);line-height:1.45}

  .chart{width:100%;display:block}
  .scatter-wrap{position:relative;background:#fafbfd;border:1px solid var(--line);border-radius:8px;overflow:hidden}
  .legend{display:flex;flex-wrap:wrap;gap:8px 16px;margin-top:10px;font-size:12px}
  .legend .it{display:inline-flex;align-items:center;gap:6px}
  .legend .sw{width:11px;height:11px;border-radius:50%}

  .bar-row{display:flex;align-items:center;gap:8px;margin-bottom:7px}
  .bar-name{width:200px;flex:0 0 200px;font-size:12px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
  .bar-track{flex:1;height:18px;background:#f1f5f9;border-radius:5px;position:relative;overflow:hidden}
  .bar-fill{height:100%;border-radius:5px;position:absolute;top:0;opacity:.92}
  .bar-val{width:78px;flex:0 0 78px;text-align:right;font-size:11.5px;font-variant-numeric:tabular-nums;color:#334155}
  .axis-mid{position:absolute;left:50%;top:0;bottom:0;border-left:1px dashed #cbd5e1}

  .explorer-grid{display:grid;grid-template-columns:1fr 1fr;gap:18px}
  select{font:inherit;padding:6px 10px;border:1px solid var(--line);border-radius:7px;background:#fff}
  .kpi-mini{display:grid;grid-template-columns:repeat(auto-fill,minmax(140px,1fr));gap:10px}
  .kpi-mini .m{background:#f8fafc;border:1px solid var(--line);border-radius:8px;padding:10px 11px}
  .kpi-mini .m .k{font-size:11px;color:var(--muted)} .kpi-mini .m .v{font-size:18px;font-weight:700}
  .help{background:var(--accent-soft);border:1px solid #c7d2fe;border-radius:8px;padding:12px 14px;font-size:12.5px;color:#3730a3;margin-bottom:18px}
  .help b{color:#312e81}
  .footer{margin-top:30px;color:var(--muted);font-size:11.5px;text-align:center}
  @media(max-width:900px){.sidebar{position:fixed;left:-260px;z-index:30;transition:left .2s}.sidebar.open{left:0}.explorer-grid{grid-template-columns:1fr}.bar-name{width:130px;flex:0 0 130px}}
  .burger{display:none}@media(max-width:900px){.burger{display:inline-block;margin-right:10px;background:var(--panel);border:1px solid var(--line);border-radius:7px;padding:5px 9px;cursor:pointer}}
</style>
</head>
<body>
<div class="layout">
  <aside class="sidebar" id="sidebar">
    <div class="brand">Dashboard Analisis ML<small>Indikator Regional Indonesia</small></div>
    <button class="nav-btn active" data-section="overview"><svg class="nav-ico" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/></svg>Overview</button>
    <button class="nav-btn" data-section="clustering"><svg class="nav-ico" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="7" cy="7" r="3"/><circle cx="17" cy="7" r="3"/><circle cx="7" cy="17" r="3"/><circle cx="17" cy="17" r="3"/></svg>Clustering</button>
    <button class="nav-btn" data-section="regression"><svg class="nav-ico" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 17l6-6 4 4 8-8"/><path d="M14 7h7v7"/></svg>Regresi & Prediksi</button>
    <button class="nav-btn" data-section="correlation"><svg class="nav-ico" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 12h4l3-8 4 16 3-8h4"/></svg>Korelasi Spearman</button>
    <button class="nav-btn" data-section="explorer"><svg class="nav-ico" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="7"/><path d="M21 21l-4-4"/></svg>Data Explorer</button>
    <div class="nav-hint">Sumber: <code>ml_results.json</code> + data mart agregat provinsi. File mandiri offline.</div>
  </aside>

  <main class="main">
    <div class="topbar">
      <div>
        <button class="burger" onclick="document.getElementById('sidebar').classList.toggle('open')">&#9776;</button>
        <h1 id="view-title">Overview</h1>
        <div class="sub" id="view-sub">Ringkasan hasil pipeline ETL + ML</div>
      </div>
      <span class="pill" id="gen-ts">Dibuat: ...</span>
    </div>

    <!-- OVERVIEW -->
    <section class="section active" id="sec-overview">
      <div class="help"><b>Cara pakai:</b> pilih bagian lewat sidebar kiri. Pada <b>Clustering</b> & <b>Regresi</b>, ganti target pendidikan dan metode dengan tombol di atas panel. Hover titik/graf untuk detail. Semua interaksi berjalan offline di browser.</div>
      <div class="cards" id="kpi-cards"></div>
      <div class="panel">
        <h2>Performa Model per Target Pendidikan</h2>
        <p class="pmeta">Bandingkan kualitas klustering (silhouette) & regresi (R² disesuaikan) lintas 5 target.</p>
        <div class="scroll"><table id="perf-table"></table></div>
      </div>
    </section>

    <!-- CLUSTERING -->
    <section class="section" id="sec-clustering">
      <div class="controls">
        <span class="label">Target:</span><div class="seg" id="cl-target"></div>
        <span class="label" style="margin-left:10px">Metode:</span><div class="seg" id="cl-method">
          <button data-v="kmeans" class="active">K-Means</button><button data-v="hdbscan">HDBSCAN</button>
        </div>
      </div>
      <div class="cards" id="cl-metrics"></div>
      <div class="panel"><h2>Visualisasi Kluster</h2><p class="pmeta" id="cl-plot-desc"></p>
        <div class="scatter-wrap" id="cl-scatter"></div>
        <div class="legend" id="cl-legend"></div>
      </div>
      <div class="panel"><h2>Anggota Kluster</h2><p class="pmeta">Provinsi dalam tiap kluster beserta rata-rata target.</p>
        <div class="scroll"><table id="cl-members"></table></div>
      </div>
      <div class="panel"><h2>Rata-rata Prediktor per Kluster</h2><p class="pmeta">Pola indikator sosial-ekonomi tiap kluster (heatmap).</p>
        <div class="scroll"><table class="heatmap" id="cl-heatmap"></table></div>
      </div>
    </section>

    <!-- REGRESSION -->
    <section class="section" id="sec-regression">
      <div class="controls">
        <span class="label">Target:</span><div class="seg" id="rg-target"></div>
        <span class="label" style="margin-left:10px">Model:</span><div class="seg" id="rg-model">
          <button data-v="linear" class="active">Linear Regression</button><button data-v="rf">Random Forest</button>
        </div>
      </div>
      <div class="cards" id="rg-metrics"></div>
      <div class="panel"><h2 id="rg-bar-title">Koefisien / Pentingnya Fitur</h2><p class="pmeta" id="rg-bar-desc"></p>
        <div id="rg-bars"></div>
      </div>
    </section>

    <!-- CORRELATION -->
    <section class="section" id="sec-correlation">
      <div class="help">Matriks korelasi Spearman antara 8 prediktor (baris) dan 5 target pendidikan (kolom). Warna merah = korelasi negatif, hijau = positif. Klik sel untuk detail p-value.</div>
      <div class="panel"><h2>Matriks Korelasi Spearman</h2><p class="pmeta">ρ per pasangan prediktor–target. * = signifikan (p&lt;0.05).</p>
        <div class="scroll"><table class="matrix" id="corr-matrix"></table></div>
      </div>
      <div class="panel"><h2>Detail Target Terpilih</h2><p class="pmeta">Korelasi & signifikansi tiap prediktor terhadap target.</p>
        <div class="controls"><span class="label">Target:</span><div class="seg" id="cr-target"></div></div>
        <div id="corr-bars"></div>
      </div>
    </section>

    <!-- EXPLORER -->
    <section class="section" id="sec-explorer">
      <div class="controls"><span class="label">Provinsi:</span><select id="ex-prov"></select></div>
      <div class="explorer-grid">
        <div class="panel"><h2>Indikator Sosial-Ekonomi (rata-rata)</h2><p class="pmeta">8 prediktor untuk provinsi terpilih.</p><div class="kpi-mini" id="ex-pred"></div></div>
        <div class="panel"><h2>Target Pendidikan (rata-rata)</h2><p class="pmeta">5 indikator pendidikan untuk provinsi terpilih.</p><div class="kpi-mini" id="ex-tgt"></div></div>
      </div>
      <div class="panel"><h2>Semua Provinsi</h2><p class="pmeta">Tabel interaktif; klik header untuk sortir.</p>
        <div class="scroll"><table id="ex-table"></table></div>
      </div>
    </section>

    <div class="footer">Dashboard ML · Indikator Regional Indonesia · dibuat <span id="gen-ts2"></span></div>
  </main>
</div>

<script>
const DATA = __DATA__;
const PRED_BY_KEY = Object.fromEntries(DATA.predictors.map(p=>[p.key,p]));
const TGT_BY_KEY  = Object.fromEntries(DATA.targets.map(t=>[t.key,t]));
const COLORS = DATA.colors;
const state = {section:'overview', ctarget:DATA.targets[0].key, cmethod:'kmeans',
               rgtarget:DATA.targets[0].key, rgmodel:'linear',
               crtarget:DATA.targets[0].key, prov:DATA.provinces[0]};

const fmt = (v,d=2)=> (v===null||v===undefined||isNaN(v)) ? '–' : Number(v).toLocaleString('id-ID',{minimumFractionDigits:d,maximumFractionDigits:d});
const sig = p => p<0.05;
const clr = v => { // green(+) .. red(-)
  const x = Math.max(-1,Math.min(1,v));
  if(v===null||isNaN(v)) return '#e2e8f0';
  if(x>=0){const t=x; return `rgba(13,148,136,${0.18+0.62*t})`;}
  const t=-x; return `rgba(190,18,60,${0.18+0.62*t})`;
};
const el = id => document.getElementById(id);
function seg(container, opts, get, set){
  container.innerHTML='';
  opts.forEach(o=>{
    const b=document.createElement('button');
    b.textContent=o.label; b.dataset.v=o.value;
    if(o.value===get()) b.classList.add('active');
    b.onclick=()=>{set(o.value); [...container.children].forEach(c=>c.classList.remove('active')); b.classList.add('active');};
    container.appendChild(b);
  });
}

/* ---------- OVERVIEW ---------- */
function renderOverview(){
  el('gen-ts').textContent='Dibuat: '+DATA.generated_at;
  el('gen-ts2').textContent=DATA.generated_at;
  const C=DATA.clustering, R=DATA.regression;
  const tgs=DATA.targets, preds=DATA.predictors;
  let bestSil=-2,bestSilTgt='',bestR2=-2,bestR2Tgt='';
  tgs.forEach(t=>{
    const km=C[t.key]?.kmeans?.silhouette, hd=C[t.key]?.hdbscan?.silhouette;
    const s=Math.max(km??-2,hd??-2); if(s>bestSil){bestSil=s;bestSilTgt=t.name;}
    const lr=R[t.key]?.linear?.adj_r2, rf=R[t.key]?.rf?.adj_r2;
    const r=Math.max(lr??-2,rf??-2); if(r>bestR2){bestR2=r;bestR2Tgt=t.name;}
  });
  const cards=[
    {k:'Provinsi',v:DATA.provinces.length,h:'terklustering'},
    {k:'Indikator Sosial',v:preds.length,h:'prediktor (8)'},
    {k:'Target Pendidikan',v:tgs.length,h:'APM/APK/RLS'},
    {k:'Silhouette Terbaik',v:fmt(bestSil,3),h:bestSilTgt||'–'},
    {k:'R² Adj. Terbaik',v:fmt(bestR2,3),h:bestR2Tgt||'–'},
  ];
  el('kpi-cards').innerHTML=cards.map(c=>`<div class="card"><div class="k">${c.k}</div><div class="v">${c.v}</div><div class="h">${c.h}</div></div>`).join('');
  // perf table
  const rows=tgs.map(t=>{
    const Cc=C[t.key]||{}, Rr=R[t.key]||{};
    const km=Cc.kmeans||{}, hd=Cc.hdbscan||{}, lr=Rr.linear||{}, rf=Rr.rf||{};
    return `<tr><td class="row-label">${t.name}<div style="font-size:10.5px;color:var(--muted)">${t.long}</div></td>
      <td class="num">${km.n_clusters??'–'}</td><td class="num">${fmt(km.silhouette,3)}</td>
      <td class="num">${hd.n_clusters??'–'}</td><td class="num">${fmt(hd.noise_ratio,3)}</td><td class="num">${fmt(hd.silhouette,3)}</td>
      <td class="num">${fmt(lr.adj_r2,3)}</td><td class="num">${fmt(rf.adj_r2,3)}</td>
      <td class="num">${fmt(Math.min(lr.mae??9,rf.mae??9),3)}</td></tr>`;
  }).join('');
  el('perf-table').innerHTML=`<thead><tr><th>Target</th><th>K</th><th>Sil. KM</th><th>Cluster HDB</th><th>Noise</th><th>Sil. HDB</th><th>R²Adj LR</th><th>R²Adj RF</th><th>MAE</th></tr></thead><tbody>${rows}</tbody>`;
}

/* ---------- CLUSTERING ---------- */
function renderClustering(){
  const tgtOpts=DATA.targets.map(t=>({label:t.name,value:t.key}));
  seg(el('cl-target'),tgtOpts,()=>state.ctarget,v=>{state.ctarget=v;drawClustering();});
  seg(el('cl-method'),[{label:'K-Means',value:'kmeans'},{label:'HDBSCAN',value:'hdbscan'}],()=>state.cmethod,v=>{state.cmethod=v;drawClustering();});
  drawClustering();
}
function drawClustering(){
  const C=DATA.clustering[state.ctarget], M=C[state.cmethod], t=TGT_BY_KEY[state.ctarget];
  el('cl-metrics').innerHTML=[
    {k:'Metode',v:state.cmethod.toUpperCase()},
    {k:'Jumlah Kluster',v:M.n_clusters??'–'},
    state.cmethod==='hdbscan'?{k:'Rasio Noise',v:fmt(M.noise_ratio,3)}:{k:'Inersia',v:fmt(M.inertia,1)},
    {k:'Silhouette',v:fmt(M.silhouette,3)},
    {k:'Target',v:t.name},
  ].map(c=>`<div class="card"><div class="k">${c.k}</div><div class="v">${c.v}</div></div>`).join('');
  drawScatter(C,M); drawMembers(M,t); drawHeatmap(M,t);
}
function drawScatter(C,M){
  const wrap=el('cl-scatter'); const pts=C.points||[];
  if(!pts.length||!C.plot.x_key){wrap.innerHTML='<p style="padding:18px;color:var(--muted)">Data scatter tidak tersedia.</p>';el('cl-legend').innerHTML='';return;}
  const W=560,H=400,padL=54,padR=18,padT=18,padB=46;
  const xs=pts.map(p=>p.x), ys=pts.map(p=>p.y);
  let xmin=Math.min(...xs),xmax=Math.max(...xs),ymin=Math.min(...ys),ymax=Math.max(...ys);
  if(xmin===xmax){xmin-=1;xmax+=1;} if(ymin===ymax){ymin-=1;ymax+=1;}
  const sx=x=>padL+(x-xmin)/(xmax-xmin)*(W-padL-padR);
  const sy=y=>H-padB-(y-ymin)/(ymax-ymin)*(H-padT-padB);
  const labels=M.labels||[];
  const ptsSvg=pts.map((p,i)=>{
    const lab=labels[i]??-1; const col=lab===-1?'#64748b':COLORS[lab%COLORS.length];
    const tip=`${p.province} | ${lab===-1?'Noise':'Kluster '+lab} | ${TGT_BY_KEY[state.ctarget].name}: ${fmt(p.target_value,2)} | ${C.plot.x_name}: ${fmt(p.x,2)} | ${C.plot.y_name}: ${fmt(p.y,2)}`;
    return `<circle cx="${sx(p.x)}" cy="${sy(p.y)}" r="6" fill="${col}" stroke="#0f172a" stroke-width=".8" opacity=".88"><title>${tip}</title></circle>`;
  }).join('');
  // gridlines
  let grid='';
  for(let i=0;i<=4;i++){const gy=padT+(H-padT-padB)*i/4; grid+=`<line x1="${padL}" y1="${gy}" x2="${W-padR}" y2="${gy}" stroke="#eef2f7"/>`;
    const val=ymin+(ymax-ymin)*(1-i/4); grid+=`<text x="${padL-6}" y="${gy+3}" text-anchor="end" font-size="10" fill="#94a3b8">${fmt(val,1)}</text>`;}
  for(let i=0;i<=4;i++){const gx=padL+(W-padL-padR)*i/4; grid+=`<line x1="${gx}" y1="${padT}" x2="${gx}" y2="${H-padB}" stroke="#eef2f7"/>`;
    const val=xmin+(xmax-xmin)*i/4; grid+=`<text x="${gx}" y="${H-padB+14}" text-anchor="middle" font-size="10" fill="#94a3b8">${fmt(val,1)}</text>`;}
  const svg=`<svg class="chart" viewBox="0 0 ${W} ${H}" preserveAspectRatio="xMidYMid meet">
    ${grid}
    <text x="${(W+padL)/2}" y="${H-6}" text-anchor="middle" font-size="11" fill="#475569" font-weight="600">${C.plot.x_name||'X'}</text>
    <text x="14" y="${H/2}" text-anchor="middle" font-size="11" fill="#475569" font-weight="600" transform="rotate(-90 14 ${H/2})">${C.plot.y_name||'Y'}</text>
    ${ptsSvg}</svg>`;
  wrap.innerHTML=svg;
  el('cl-plot-desc').textContent=`Sumbu X: ${C.plot.x_name} · Sumbu Y: ${C.plot.y_name}. Titik = provinsi (hover untuk detail). Warna mengikuti label ${state.cmethod.toUpperCase()}.`;
  // legend
  const order=[...new Set(labels)].sort((a,b)=>a-b);
  el('cl-legend').innerHTML=order.map(l=>{
    const col=l===-1?'#64748b':COLORS[l%COLORS.length]; const n=labels.filter(x=>x===l).length;
    return `<span class="it"><span class="sw" style="background:${col}"></span>${l===-1?'Noise':'Kluster '+l} (${n})</span>`;
  }).join('');
}
function drawMembers(M,t){
  const rows=(M.clusters||[]).map(c=>{
    const pct=(c.n_members/(M.labels?.length||1)*100).toFixed(1);
    return `<tr><td><span class="tag" style="background:${c.label===-1?'#e2e8f0':'#eef2ff'};color:${c.label===-1?'#475569':'#3730a3'}">${c.name}</span></td>
      <td class="num">${c.n_members}</td><td class="num">${pct}%</td>
      <td class="num">${fmt(c.target_mean,2)}</td><td class="members">${c.members.join(', ')||'–'}</td></tr>`;
  }).join('');
  el('cl-members').innerHTML=`<thead><tr><th>Kluster</th><th>Jumlah</th><th>%</th><th>Rata-rata ${t.name}</th><th>Provinsi</th></tr></thead><tbody>${rows}</tbody>`;
}
function drawHeatmap(M,t){
  const preds=DATA.predictors;
  const cols=(M.clusters||[]).filter(c=>c.label!==-1).sort((a,b)=>a.label-b.label);
  const noise=(M.clusters||[]).find(c=>c.label===-1);
  const all=noise?[...cols,noise]:cols;
  // header
  let head=`<thead><tr><th>Prediktor</th>${all.map(c=>`<th class="cell">${c.name}</th>`).join('')}</tr></thead>`;
  // compute global min/max per predictor for coloring
  let body='<tbody>';
  preds.forEach(p=>{
    const vals=all.map(c=>c.predictor_means[p.key]).filter(v=>v!=null);
    const mn=Math.min(...vals),mx=Math.max(...vals);
    body+=`<tr><td class="row-label">${p.name}<div style="font-size:10px;color:var(--muted)">${p.unit}</div></td>`;
    all.forEach(c=>{const v=c.predictor_means[p.key]; let bg='#e2e8f0';
      if(v!=null&&mx>mn){const t=(v-mn)/(mx-mn); bg=`rgba(79,70,229,${0.12+0.55*t})`;}
      const col = (v!=null&&mx>mn&&((v-mn)/(mx-mn))>0.55)?'#fff':'#0f172a';
      body+=`<td class="cell" style="background:${bg};color:${col}">${fmt(v,1)}</td>`;});
    body+='</tr>';
  });
  // target row
  const tvals=all.map(c=>c.target_mean).filter(v=>v!=null);
  const tmn=Math.min(...tvals),tmx=Math.max(...tvals);
  body+=`<tr><td class="row-label" style="background:#f8fafc"><strong>${t.name}</strong></td>`;
  all.forEach(c=>{const v=c.target_mean;let bg='#eef2ff';
    if(v!=null&&tmx>tmn){const tt=(v-tmn)/(tmx-tmn); bg=`rgba(13,148,136,${0.18+0.55*tt})`;}
    body+=`<td class="cell" style="background:${bg};font-weight:600">${fmt(v,2)}</td>`;});
  body+='</tr></tbody>';
  el('cl-heatmap').innerHTML=head+body;
}

/* ---------- REGRESSION ---------- */
function renderRegression(){
  seg(el('rg-target'),DATA.targets.map(t=>({label:t.name,value:t.key})),()=>state.rgtarget,v=>{state.rgtarget=v;drawRegression();});
  seg(el('rg-model'),[{label:'Linear Regression',value:'linear'},{label:'Random Forest',value:'rf'}],()=>state.rgmodel,v=>{state.rgmodel=v;drawRegression();});
  drawRegression();
}
function drawRegression(){
  const R=DATA.regression[state.rgtarget][state.rgmodel], t=TGT_BY_KEY[state.rgtarget];
  const cards=state.rgmodel==='linear'?[
    {k:'R²',v:fmt(R.r2,3)},{k:'R² Disesuaikan',v:fmt(R.adj_r2,3)},
    {k:'MAE',v:fmt(R.mae,3)},{k:'RMSE',v:fmt(R.rmse,3)},{k:'Intercept',v:fmt(R.intercept,3)},
  ]:[
    {k:'R²',v:fmt(R.r2,3)},{k:'R² Disesuaikan',v:fmt(R.adj_r2,3)},
    {k:'MAE',v:fmt(R.mae,3)},{k:'RMSE',v:fmt(R.rmse,3)},{k:'Train/Test',v:(R.n_train??'–')+'/'+(R.n_test??'–')},
  ];
  el('rg-metrics').innerHTML=cards.map(c=>`<div class="card"><div class="k">${c.k}</div><div class="v">${c.v}</div></div>`).join('');
  // bars
  let items;
  if(state.rgmodel==='linear'){
    items=DATA.predictors.map(p=>({name:p.name,key:p.key,val:R.coefficients[p.key],p:R.p_values[p.key]}));
    el('rg-bar-title').textContent='Koefisien Regresi Linear (berurutan, * signifikan)';
    el('rg-bar-desc').textContent='Tanda (+/−) menunjukkan arah hubungan; warna hijau = signifikan (p<0.05).';
  }else{
    items=DATA.predictors.map(p=>({name:p.name,key:p.key,val:R.feature_importance[p.key]}));
    items.sort((a,b)=>(b.val??0)-(a.val??0));
    el('rg-bar-title').textContent='Pentingnya Fitur (Random Forest)';
    el('rg-bar-desc').textContent='Skor importance relatif; panjang batang = kontribusi ke model.';
  }
  if(state.rgmodel==='linear') items.sort((a,b)=>(b.val??0)-(a.val??0));
  const maxAbs=Math.max(0.0001,...items.map(i=>Math.abs(i.val??0)));
  el('rg-bars').innerHTML=items.map(i=>{
    const v=i.val??0; const pct=Math.abs(v)/maxAbs*50;
    const left=v>=0?50:50-pct; const w=pct;
    const sign=v>=0?'+':'−';
    const col=state.rgmodel==='linear'?(sig(i.p)?'#0d9488':'#94a3b8'):'#4f46e5';
    const star=state.rgmodel==='linear'&&sig(i.p)?' *':'';
    return `<div class="bar-row"><div class="bar-name" title="${i.name}">${i.name}${star}</div>
      <div class="bar-track"><span class="axis-mid"></span><div class="bar-fill" style="left:${left}%;width:${w}%;background:${col}"></div></div>
      <div class="bar-val">${sign}${fmt(Math.abs(v),4)}</div></div>`;
  }).join('');
}

/* ---------- CORRELATION ---------- */
function renderCorrelation(){
  const m=DATA.spearman.matrix;
  const preds=DATA.predictors;
  let head='<thead><tr><th>Prediktor</th>'+DATA.targets.map(t=>`<th class="cell">${t.name}</th>`).join('')+'</tr></thead><tbody>';
  let body='';
  preds.forEach(p=>{
    body+=`<tr><td class="row-label">${p.name}</td>`;
    DATA.targets.forEach(t=>{
      const row=m.find(r=>r.target===t.key); const cell=row?.cells.find(c=>c.predictor===p.key);
      const v=cell?.value; const c=DATA.spearman.correlations[t.key]?.[p.key];
      const star=c?.significant?'*':'';
      const tip=`ρ=${fmt(v,3)} · p=${fmt(c?.p_value,4)} ${c?.significant?'(signifikan)':''}`;
      body+=`<td class="cell" style="background:${clr(v)};color:${Math.abs(v??0)>0.55?'#fff':'#0f172a'}" title="${tip}">${fmt(v,2)}${star}</td>`;
    });
    body+='</tr>';
  });
  el('corr-matrix').innerHTML=head+body+'</tbody>';
  seg(el('cr-target'),DATA.targets.map(t=>({label:t.name,value:t.key})),()=>state.crtarget,v=>{state.crtarget=v;drawCorrBars();});
  drawCorrBars();
}
function drawCorrBars(){
  const t=state.crtarget, corr=DATA.spearman.correlations[t]||{};
  const items=DATA.predictors.map(p=>({name:p.name,val:corr[p.key]?.coefficient,p:corr[p.key]?.p_value,sig:corr[p.key]?.significant}));
  items.sort((a,b)=>(b.val??0)-(a.val??0));
  const maxAbs=Math.max(0.0001,...items.map(i=>Math.abs(i.val??0)));
  el('corr-bars').innerHTML=items.map(i=>{
    const v=i.val??0; const pct=Math.abs(v)/maxAbs*50; const left=v>=0?50:50-pct;
    const col=i.sig?'#0d9488':'#94a3b8';
    return `<div class="bar-row"><div class="bar-name" title="${i.name}">${i.name}${i.sig?' *':''}</div>
      <div class="bar-track"><span class="axis-mid"></span><div class="bar-fill" style="left:${left}%;width:${pct}%;background:${col}"></div></div>
      <div class="bar-val">${fmt(v,3)} (p=${fmt(i.p,3)})</div></div>`;
  }).join('');
}

/* ---------- EXPLORER ---------- */
function renderExplorer(){
  const sel=el('ex-prov');
  sel.innerHTML=DATA.provinces.map(p=>`<option value="${p}">${p}</option>`).join('');
  sel.value=state.prov; sel.onchange=e=>{state.prov=e.target.value;drawExplorer();};
  drawExplorer(); drawExTable();
}
function drawExplorer(){
  const d=DATA.province_data[state.prov]; if(!d) return;
  el('ex-pred').innerHTML=DATA.predictors.map(p=>`<div class="m"><div class="k">${p.name}</div><div class="v">${fmt(d.predictors[p.key],2)}</div></div>`).join('');
  el('ex-tgt').innerHTML=DATA.targets.map(t=>`<div class="m"><div class="k">${t.name}</div><div class="v">${fmt(d.targets[t.key],2)}</div></div>`).join('');
}
let _exSort={k:null,dir:1};
function drawExTable(){
  const preds=DATA.predictors,tgts=DATA.targets;
  const rows=DATA.provinces.map(pv=>{const d=DATA.province_data[pv];
    return {pv,...Object.fromEntries(preds.map(p=>[p.key,d?.predictors[p.key]])),...Object.fromEntries(tgts.map(t=>[t.key,d?.targets[t.key]]))};});
  const cols=[{k:'pv',label:'Provinsi'},...preds.map(p=>({k:p.key,label:p.name})),...tgts.map(t=>({k:t.key,label:t.name}))];
  const sortKey=_exSort.k||'pv';
  rows.sort((a,b)=>{const av=a[sortKey],bv=b[sortKey];
    if(typeof av==='string'||typeof bv==='string') return String(av).localeCompare(String(bv))*_exSort.dir;
    return ((av??0)-(bv??0))*_exSort.dir;});
  const head='<thead><tr>'+cols.map(c=>`<th style="cursor:pointer" onclick="exSort('${c.k}')">${c.label}${_exSort.k===c.k?(_exSort.dir>0?' ▲':' ▼'):''}</th>`).join('')+'</tr></thead>';
  const body='<tbody>'+rows.map(r=>'<tr>'+cols.map(c=>c.k==='pv'?`<td class="row-label">${r.pv}</td>`:`<td class="num">${fmt(r[c.k],2)}</td>`).join('')+'</tr>').join('')+'</tbody>';
  el('ex-table').innerHTML=head+body;
}
window.exSort=k=>{_exSort.dir=(_exSort.k===k)?-_exSort.dir:1;_exSort.k=k;drawExTable();};

/* ---------- NAV ---------- */
const TITLES={overview:['Overview','Ringkasan hasil pipeline ETL + ML'],
  clustering:['Clustering','Pengelompokan provinsi per target pendidikan'],
  regression:['Regresi & Prediksi','Linear Regression & Random Forest per target'],
  correlation:['Korelasi Spearman','Hubungan prediktor ↔ target pendidikan'],
  explorer:['Data Explorer','Nilai indikator per provinsi']};
document.querySelectorAll('.nav-btn').forEach(b=>b.onclick=()=>{
  document.querySelectorAll('.nav-btn').forEach(x=>x.classList.remove('active'));
  b.classList.add('active');
  state.section=b.dataset.section;
  document.querySelectorAll('.section').forEach(s=>s.classList.remove('active'));
  el('sec-'+state.section).classList.add('active');
  const [ti,su]=TITLES[state.section]; el('view-title').textContent=ti; el('view-sub').textContent=su;
  document.getElementById('sidebar').classList.remove('open');
  if(state.section==='overview')renderOverview();
  if(state.section==='clustering')renderClustering();
  if(state.section==='regression')renderRegression();
  if(state.section==='correlation')renderCorrelation();
  if(state.section==='explorer')renderExplorer();
});

renderOverview();
</script>
</body>
</html>
"""


if __name__ == "__main__":
    DashboardGenerator().generate_html()
