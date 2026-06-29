/* Pipeline Dashboard — Alpine component + Chart.js rendering.
   Reuses the build_payload() blob from dashboard_generator (served at /api/results). */

function dashboard() {
  return {
    // ---- state ----
    sidebarOpen: true,
    view: 'overview',
    health: null,
    status: null,
    results: null,
    config: null,
    configDraft: null,
    toasts: [],
    run: { phase: 'all', forceDw: false, skipVal: false, running: false, exitCode: null, lines: [], evt: null },
    cl: { target: null, method: 'kmeans' },
    rg: { target: null, model: 'linear' },
    cr: { target: null },
    ex: { prov: null, sortKey: 'pv', sortDir: 1 },
    charts: {},
    defaultTargets: [
      { key: 'apm_sd' }, { key: 'apm_smp' }, { key: 'apm_sm' }, { key: 'apk_pt' }, { key: 'rata_rata_lama_sekolah' }
    ],
    phaseSteps: ['Extract', 'Transform', 'Reconcile', 'Load Staging', 'Create DW', 'Load DW', 'Aggregation', 'Validate', 'ML Pipeline', 'ML Report', 'Dashboard'],
    phases: [
      { id: 'all', desc: 'Seluruh pipeline (11 phase)' },
      { id: 'extract', desc: 'Baca & bersihkan CSV' },
      { id: 'transform', desc: 'Normalisasi & validasi' },
      { id: 'load-staging', desc: 'Load ke staging schema' },
      { id: 'reconcile', desc: 'Gate rekonsiliasi' },
      { id: 'create-dw', desc: 'Buat schema data warehouse' },
      { id: 'load-dw', desc: 'Load fact table DW' },
      { id: 'aggregation', desc: 'Buat data mart' },
      { id: 'validate', desc: 'Laporan kualitas' },
      { id: 'ml-pipeline', desc: 'Clustering & regresi' },
      { id: 'ml-report', desc: 'Laporan HTML ML' },
      { id: 'dashboard', desc: 'Dashboard statis' },
    ],
    nav: [
      { id: 'overview', label: 'Overview', sub: 'Ringkasan hasil pipeline ETL + ML', icon: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/></svg>' },
      { id: 'run', label: 'Run Control', sub: 'Jalankan & pantau pipeline secara real-time', icon: '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M8 5v14l11-7z"/></svg>' },
      { id: 'clustering', label: 'Clustering', sub: 'Pengelompokan provinsi per target pendidikan', icon: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="7" cy="7" r="3"/><circle cx="17" cy="7" r="3"/><circle cx="7" cy="17" r="3"/><circle cx="17" cy="17" r="3"/></svg>' },
      { id: 'regression', label: 'Regresi & Prediksi', sub: 'Linear Regression & Random Forest per target', icon: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 17l6-6 4 4 8-8"/><path d="M14 7h7v7"/></svg>' },
      { id: 'correlation', label: 'Korelasi Spearman', sub: 'Hubungan prediktor ↔ target pendidikan', icon: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 12h4l3-8 4 16 3-8h4"/></svg>' },
      { id: 'explorer', label: 'Data Explorer', sub: 'Nilai indikator per provinsi', icon: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="7"/><path d="M21 21l-4-4"/></svg>' },
      { id: 'config', label: 'ML Config', sub: 'Edit config/ml_config.json', icon: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg>' },
      { id: 'reports', label: 'Reports', sub: 'Unduh laporan & artifacts', icon: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><path d="M7 10l5 5 5-5"/><path d="M12 15V3"/></svg>' },
    ],

    // ---- lifecycle ----
    async init() {
      window.__exSort = (k) => { this.ex.sortDir = (this.ex.sortKey === k) ? -this.ex.sortDir : 1; this.ex.sortKey = k; this.renderExTable(); };
      window.__pickCorr = (t, p) => { this.cr.target = t; this.renderCorrBars(); };
      await this.refresh();
      this.pollStatus();
    },
    async refresh() {
      await Promise.all([this.loadHealth(), this.loadStatus(), this.loadResults(), this.loadConfig()]);
    },
    async loadHealth() { try { this.health = await (await fetch('/api/health')).json(); } catch (e) { this.health = { env_present: false, db: { reachable: false } }; } },
    async loadStatus() { try { this.status = await (await fetch('/api/status')).json(); } catch (e) { this.status = { artifacts: [], has_results: false }; } },
    async loadResults() {
      try { const r = await (await fetch('/api/results')).json(); this.results = r; this.initSelections(); }
      catch (e) { this.results = { error: String(e) }; }
    },
    async loadConfig() {
      try { this.config = await (await fetch('/api/config')).json(); this.configDraft = JSON.parse(JSON.stringify(this.config)); }
      catch (e) { this.config = null; }
    },
    initSelections() {
      const R = this.results;
      if (!R || R.error || !R.targets) return;
      const tk = R.targets.map(t => t.key);
      if (!this.cl.target || !tk.includes(this.cl.target)) this.cl.target = tk[0];
      if (!this.rg.target || !tk.includes(this.rg.target)) this.rg.target = tk[0];
      if (!this.cr.target || !tk.includes(this.cr.target)) this.cr.target = tk[0];
      if (!this.ex.prov && R.provinces?.length) this.ex.prov = R.provinces[0];
    },

    // ---- view switching + render hooks ----
    switchView(v) {
      this.view = v;
      this.$nextTick(() => {
        if (v === 'clustering') this.renderClustering();
        else if (v === 'regression') this.renderRegression();
        else if (v === 'correlation') this.renderCorrelation();
        else if (v === 'explorer') this.renderExplorer();
      });
    },
    watchView(_v) { /* x-init no-op; rendering driven by switchView */ },
    currentNav() { return this.nav.find(n => n.id === this.view) || this.nav[0]; },

    // ---- run control ----
    async runPipeline() {
      if (this.run.running) return;
      this.run.lines = [];
      this.run.exitCode = null;
      this.run.running = true;
      try {
        const r = await fetch('/api/run', { method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ phase: this.run.phase, force_dw_load: this.run.forceDw, skip_validation: this.run.skipVal }) });
        if (r.status === 409) { this.pushToast('Pipeline sedang berjalan', 'error'); this.run.running = false; return; }
        if (!r.ok) { const e = await r.json(); this.pushToast('Gagal memulai: ' + (e.detail || r.status), 'error'); this.run.running = false; return; }
        const data = await r.json();
        this.startSSE(data.run_id);
        this.pushToast('Pipeline berjalan: --phase ' + this.run.phase, 'info');
      } catch (e) { this.pushToast('Kesalahan jaringan: ' + e, 'error'); this.run.running = false; }
    },
    async quickRunAll() { this.run.phase = 'all'; this.run.forceDw = false; this.run.skipVal = false; await this.runPipeline(); },
    startSSE(runId) {
      if (this.run.evt) this.run.evt.close();
      const evt = new EventSource('/api/logs/' + runId);
      this.run.evt = evt;
      evt.onmessage = (m) => {
        const d = JSON.parse(m.data);
        this.run.lines.push(d.line);
        this.$nextTick(() => { const b = this.$refs.logbox; if (b) b.scrollTop = b.scrollHeight; });
      };
      evt.addEventListener('done', (m) => {
        const d = JSON.parse(m.data);
        this.run.exitCode = d.exit_code;
        this.run.running = false;
        evt.close(); this.run.evt = null;
        if (d.exit_code === 0) { this.pushToast('Pipeline selesai ✓', 'success'); }
        else { this.pushToast('Pipeline gagal (exit ' + d.exit_code + ')', 'error'); }
        this.loadStatus();
        this.loadResults();
      });
      evt.onerror = () => { /* SSE reconnects; ignore transient errors */ };
    },
    async stopRun() {
      try { await fetch('/api/stop', { method: 'POST' }); this.pushToast('Stop dikirim', 'info'); }
      catch (e) { this.pushToast('Gagal stop: ' + e, 'error'); }
    },
    pollStatus() { setInterval(() => { this.loadStatus(); }, 8000); },

    // ---- config ----
    setOverride(key, field, val) {
      if (!this.configDraft.overrides[key]) this.configDraft.overrides[key] = {};
      this.configDraft.overrides[key][field] = (val === '' || Number.isNaN(val)) ? null : val;
    },
    async saveConfig() {
      try {
        const r = await fetch('/api/config', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(this.configDraft) });
        if (!r.ok) { const e = await r.json(); this.pushToast('Gagal simpan: ' + (e.detail || r.status), 'error'); return; }
        this.config = JSON.parse(JSON.stringify(this.configDraft));
        this.pushToast('Config tersimpan. Jalankan ulang ml-pipeline.', 'success');
      } catch (e) { this.pushToast('Kesalahan: ' + e, 'error'); }
    },

    // ---- toasts ----
    pushToast(msg, type = 'info') { const id = Math.random().toString(36).slice(2); this.toasts.push({ id, msg, type }); setTimeout(() => { this.toasts = this.toasts.filter(t => t.id !== id); }, 4200); },

    // ---- helpers ----
    fmt(v, d = 2) { if (v === null || v === undefined || Number.isNaN(v)) return '–'; return Number(v).toLocaleString('id-ID', { minimumFractionDigits: d, maximumFractionDigits: d }); },
    fmtBytes(n) { if (!n) return '0 B'; const u = ['B', 'KB', 'MB', 'GB']; const i = Math.floor(Math.log(n) / Math.log(1024)); return (n / Math.pow(1024, i)).toFixed(i ? 1 : 0) + ' ' + u[i]; },
    clr(v) { if (v === null || v === undefined || Number.isNaN(v)) return '#e2e8f0'; const x = Math.max(-1, Math.min(1, v)); const t = Math.abs(x); return x >= 0 ? `rgba(13,148,136,${0.18 + 0.62 * t})` : `rgba(190,18,60,${0.18 + 0.62 * t})`; },
    predByKey(k) { return this.results?.predictors?.find(p => p.key === k); },
    tgtByKey(k) { return this.results?.targets?.find(t => t.key === k); },
    shortName(key) { if (!key) return key; let base = key; for (const s of ['_mean', '_trend_pct']) if (base.endsWith(s)) base = base.slice(0, -s.length); base = { 'ekonomi_upah': 'ekonomi_upah_rata_rata', 'kesehatan_unmet': 'kesehatan_unmet_layanan', 'teknologi_telepon': 'teknologi_telepon_seluler' }[base] || base; return this.predByKey(base)?.name || key; },
    resultsError() { return this.results?.error; },
    resultsLoading() { return this.results === null; },
    emptyHtml() { return `<div class="font-semibold mb-1">Hasil ML belum tersedia</div><div class="text-[13px]">${this.resultsError() || 'Jalankan pipeline terlebih dahulu.'}</div><button onclick="document.querySelector('[x-data]').__x.$data.switchView('run')" class="mt-3 bg-amber-600 hover:bg-amber-700 text-white text-[13px] px-3 py-1.5 rounded">Buka Run Control →</button>`; },
    dbReachable() { return !!this.health?.db?.reachable; },
    dbStatusText() {
      return this.dbReachable() ? 'PostgreSQL siap' : 'PostgreSQL belum siap';
    },
    openReport(a) { if (a.kind === 'json') window.open('/api/reports/' + a.name, '_blank'); else window.open('/api/reports/' + a.name, '_blank'); },

    // ---- run pill ----
    runPillText() { if (this.run.running) return 'Running'; if (this.run.exitCode === 0) return 'Done'; if (this.run.exitCode && this.run.exitCode !== 0) return 'Failed'; return 'Idle'; },
    runPillClass() { if (this.run.running) return 'bg-amber-100 text-amber-700 border-amber-200'; if (this.run.exitCode === 0) return 'bg-emerald-100 text-emerald-700 border-emerald-200'; if (this.run.exitCode) return 'bg-rose-100 text-rose-700 border-rose-200'; return 'bg-slate-100 text-slate-500 border-slate-200'; },

    // ---- progress tracker ----
    computeSteps() {
      const states = Array(this.phaseSteps.length).fill('pending');
      const byName = { extract: 0, transform: 1, reconcile: 2, 'load staging': 3, 'create dw': 4, 'load dw': 5, aggregation: 6, validate: 7, 'ml pipeline': 8, 'ml report': 9, dashboard: 10 };
      for (const line of this.run.lines) {
        const m = line.match(/PHASE\s+(\d+):/); if (m) { const idx = +m[1] - 1; if (idx >= 0 && idx < states.length && states[idx] === 'pending') states[idx] = 'running'; }
        const m2 = line.match(/\[OK\]\s+(.+?)\s+phase complete/i); if (m2) { const idx = byName[m2[1].toLowerCase()]; if (idx !== undefined) { states[idx] = 'done'; for (let j = 0; j < idx; j++) if (states[j] === 'running') states[j] = 'done'; } }
        if (/\[FAIL\]/.test(line)) { const ri = states.indexOf('running'); if (ri >= 0) states[ri] = 'failed'; }
      }
      if (!this.run.running && this.run.exitCode !== null) { if (this.run.exitCode === 0) states.forEach((s, i) => { if (s === 'running' || s === 'pending') states[i] = 'done'; }); else { const ri = states.indexOf('running'); if (ri >= 0) states[ri] = 'failed'; } }
      return states;
    },
    stepState(i) { const s = this.computeSteps()[i]; return s === 'done' ? 'bg-emerald-500 text-white' : s === 'running' ? 'bg-accent text-white animate-pulse' : s === 'failed' ? 'bg-rose-500 text-white' : 'bg-slate-200 text-slate-500'; },
    stepTextClass(i) { const s = this.computeSteps()[i]; return s === 'done' ? 'text-emerald-700 font-medium' : s === 'running' ? 'text-accent font-medium' : s === 'failed' ? 'text-rose-600 font-medium' : 'text-slate-500'; },

    logLineClass(l) {
      if (/\[OK\]/.test(l)) return 'text-emerald-400';
      if (/\[FAIL\]|ERROR|Traceback/.test(l)) return 'text-rose-400';
      if (/\[WARNING\]|WARNING/.test(l)) return 'text-amber-400';
      if (/PHASE\s+\d+/.test(l)) return 'text-indigo-300 font-semibold';
      if (/====+/.test(l)) return 'text-slate-600';
      return 'text-slate-300';
    },

    // ---- overview ----
    overviewKpis() {
      const R = this.results; if (!R || R.error) return [];
      const C = R.clustering || {}, Reg = R.regression || {};
      let bSil = -2, bSilT = '', bR2 = -2, bR2T = '';
      (R.targets || []).forEach(t => {
        const km = C[t.key]?.kmeans?.silhouette, hd = C[t.key]?.hdbscan?.silhouette;
        const s = Math.max(km ?? -2, hd ?? -2); if (s > bSil) { bSil = s; bSilT = t.name; }
        const lr = Reg[t.key]?.linear?.adj_r2, rf = Reg[t.key]?.rf?.adj_r2;
        const r = Math.max(lr ?? -2, rf ?? -2); if (r > bR2) { bR2 = r; bR2T = t.name; }
      });
      return [
        { k: 'Provinsi', v: (R.provinces || []).length, h: 'terklustering' },
        { k: 'Prediktor', v: (R.predictors || []).length, h: 'indikator sosial' },
        { k: 'Target', v: (R.targets || []).length, h: 'pendidikan' },
        { k: 'Silhouette terbaik', v: this.fmt(bSil, 3), h: bSilT || '–' },
        { k: 'R² Adj. terbaik', v: this.fmt(bR2, 3), h: bR2T || '–' },
      ];
    },
    perfRows() {
      const R = this.results; if (!R || R.error) return [];
      return (R.targets || []).map(t => {
        const C = (R.clustering || {})[t.key] || {}, Reg = (R.regression || {})[t.key] || {};
        const km = C.kmeans || {}, hd = C.hdbscan || {}, lr = Reg.linear || {}, rf = Reg.rf || {};
        return { key: t.key, name: t.name, long: t.long, kKm: km.n_clusters ?? '–', silKm: km.silhouette, kHdb: hd.n_clusters ?? '–', noise: hd.noise_ratio, silHdb: hd.silhouette, r2lr: lr.adj_r2, r2rf: rf.adj_r2, mae: Math.min(lr.mae ?? 9e9, rf.mae ?? 9e9) };
      });
    },

    // ---- clustering ----
    clObj() { return this.results?.clustering?.[this.cl.target] || null; },
    clMethodObj() { const c = this.clObj(); return c ? c[this.cl.method] : null; },
    clMetrics() {
      const M = this.clMethodObj(), t = this.tgtByKey(this.cl.target);
      if (!M) return [];
      const arr = [{ k: 'Metode', v: this.cl.method.toUpperCase() }, { k: 'Kluster', v: M.n_clusters ?? '–' }];
      arr.push(this.cl.method === 'hdbscan' ? { k: 'Rasio Noise', v: this.fmt(M.noise_ratio, 3) } : { k: 'Inersia', v: this.fmt(M.inertia, 1) });
      arr.push({ k: 'Silhouette', v: this.fmt(M.silhouette, 3) }, { k: 'Target', v: t?.name || '–' });
      return arr;
    },
    clPlotDesc() { const c = this.clObj(); return c?.plot?.x_key ? `Sumbu X: ${this.shortName(c.plot.x_key)} · Sumbu Y: ${this.shortName(c.plot.y_key)}. Titik = provinsi.` : 'Plot tidak tersedia.'; },
    clLegend() {
      const M = this.clMethodObj(); if (!M) return [];
      const labels = M.labels || [];
      const order = [...new Set(labels)].sort((a, b) => a - b);
      const colors = this.results.colors || [];
      return order.map(l => { const col = l === -1 ? '#64748b' : colors[l % colors.length]; return { label: (l === -1 ? 'Noise' : 'Kluster ' + l) + ` (${labels.filter(x => x === l).length})`, color: col }; });
    },
    clMembers() {
      const M = this.clMethodObj(), t = this.tgtByKey(this.cl.target); if (!M) return [];
      const colors = this.results.colors || [], total = (M.labels || []).length || 1;
      return (M.clusters || []).map(c => {
        const col = c.label === -1 ? '#64748b' : colors[c.label % colors.length];
        return { label: c.label, name: c.name, n: c.n_members, pct: (c.n_members / total * 100).toFixed(1), tm: c.target_mean, members: (c.members || []).join(', ') || '–', tagStyle: `background:${col}22;color:${col}` };
      });
    },
    renderClustering() {
      if (this.resultsError()) return;
      this.initSelections();
      this.renderClHeatmap();
      this.$nextTick(() => this.renderClChart());
    },
    renderClChart() {
      const c = this.clObj(); const M = this.clMethodObj();
      const canvas = document.getElementById('clChart'); if (!canvas) return;
      if (this.charts.cl) { this.charts.cl.destroy(); this.charts.cl = null; }
      const pts = c?.points || []; const labels = M?.labels || []; const colors = this.results.colors || [];
      if (!pts.length || !c?.plot?.x_key) { this.charts.cl = new Chart(canvas, { type: 'scatter', data: { datasets: [] }, options: this.clChartOpts(c, []) }); return; }
      const order = [...new Set(labels)].sort((a, b) => a - b);
      const datasets = order.map(l => ({
        label: l === -1 ? 'Noise' : 'Kluster ' + l,
        data: pts.filter((_, i) => labels[i] === l).map(p => ({ x: p.x, y: p.y, province: p.province, tv: p.target_value })),
        backgroundColor: l === -1 ? '#64748b' : colors[l % colors.length],
        pointRadius: 6, pointHoverRadius: 8,
      }));
      this.charts.cl = new Chart(canvas, { type: 'scatter', data: { datasets }, options: this.clChartOpts(c, order) });
    },
    clChartOpts(c, order) {
      const t = this.tgtByKey(this.cl.target);
      return {
        responsive: true, maintainAspectRatio: false,
        plugins: {
          legend: { display: false },
          tooltip: { callbacks: { label: (ctx) => { const p = ctx.raw; return `${p.province} · ${t?.name}: ${this.fmt(p.tv, 2)} · ${this.shortName(c.plot.x_name)}: ${this.fmt(p.x, 2)} · ${this.shortName(c.plot.y_name)}: ${this.fmt(p.y, 2)}`; } } },
        },
        scales: {
          x: { title: { display: true, text: this.shortName(c?.plot?.x_name) || 'X' }, grid: { color: '#eef2f7' } },
          y: { title: { display: true, text: this.shortName(c?.plot?.y_name) || 'Y' }, grid: { color: '#eef2f7' } },
        },
      };
    },
    renderClHeatmap() {
      const el = document.getElementById('clHeatmap'); if (!el) return;
      const M = this.clMethodObj(), t = this.tgtByKey(this.cl.target); if (!M) { el.innerHTML = ''; return; }
      const preds = this.results.predictors || [];
      const cols = (M.clusters || []).filter(c => c.label !== -1).sort((a, b) => a.label - b.label);
      const noise = (M.clusters || []).find(c => c.label === -1);
      const all = noise ? [...cols, noise] : cols;
      let head = `<thead><tr><th class="text-left px-3 py-2 bg-slate-50">Prediktor</th>${all.map(c => `<th class="px-2 py-2 text-center num bg-slate-50">${c.name}</th>`).join('')}</tr></thead><tbody>`;
      let body = '';
      preds.forEach(p => {
        const vals = all.map(c => c.predictor_means[p.key]).filter(v => v != null);
        const mn = Math.min(...vals), mx = Math.max(...vals);
        body += `<tr><td class="px-3 py-1.5 font-semibold whitespace-nowrap">${p.name}<div class="text-[10px] text-slate-400 font-normal">${p.unit}</div></td>`;
        all.forEach(c => { const v = c.predictor_means[p.key]; let bg = '#e2e8f0'; if (v != null && mx > mn) { const tt = (v - mn) / (mx - mn); bg = `rgba(79,70,229,${0.12 + 0.55 * tt})`; } const col = (v != null && mx > mn && ((v - mn) / (mx - mn)) > 0.55) ? '#fff' : '#0f172a'; body += `<td class="px-2 py-1.5 text-center num" style="background:${bg};color:${col}">${this.fmt(v, 1)}</td>`; });
        body += '</tr>';
      });
      const tvals = all.map(c => c.target_mean).filter(v => v != null); const tmn = Math.min(...tvals), tmx = Math.max(...tvals);
      body += `<tr class="border-t-2 border-slate-200"><td class="px-3 py-1.5 font-bold bg-slate-50">${t?.name || 'Target'}</td>`;
      all.forEach(c => { const v = c.target_mean; let bg = '#eef2ff'; if (v != null && tmx > tmn) { const tt = (v - tmn) / (tmx - tmn); bg = `rgba(13,148,136,${0.18 + 0.55 * tt})`; } body += `<td class="px-2 py-1.5 text-center num font-semibold" style="background:${bg}">${this.fmt(v, 2)}</td>`; });
      body += '</tr></tbody>';
      el.innerHTML = head + body;
    },

    // ---- regression ----
    rgObj() { return this.results?.regression?.[this.rg.target]?.[this.rg.model]; },
    rgMetrics() {
      const R = this.rgObj(); if (!R) return [];
      const arr = [{ k: 'R²', v: this.fmt(R.r2, 3) }, { k: 'R² Adj.', v: this.fmt(R.adj_r2, 3) }, { k: 'MAE', v: this.fmt(R.mae, 3) }, { k: 'RMSE', v: this.fmt(R.rmse, 3) }];
      arr.push(this.rg.model === 'linear' ? { k: 'Intercept', v: this.fmt(R.intercept, 3) } : { k: 'Train/Test', v: (R.n_train ?? '–') + '/' + (R.n_test ?? '–') });
      return arr;
    },
    rgBarTitle() { return this.rg.model === 'linear' ? 'Koefisien Regresi Linear (* signifikan p<0.05)' : 'Pentingnya Fitur (Random Forest)'; },
    rgBarDesc() { return this.rg.model === 'linear' ? 'Tanda (+/−) menunjukkan arah hubungan.' : 'Skor importance relatif; panjang batang = kontribusi.'; },
    renderRegression() {
      if (this.resultsError()) return;
      this.initSelections();
      this.$nextTick(() => this.renderRgChart());
    },
    renderRgChart() {
      const canvas = document.getElementById('rgChart'); if (!canvas) return;
      const R = this.rgObj(); if (!R) return;
      if (this.charts.rg) { this.charts.rg.destroy(); this.charts.rg = null; }
      const preds = this.results.predictors || [];
      let items, labels, data, colors;
      if (this.rg.model === 'linear') {
        items = preds.map(p => ({ name: p.name, val: R.coefficients[p.key], p: R.p_values[p.key] }));
        items.sort((a, b) => (b.val ?? 0) - (a.val ?? 0));
        labels = items.map(i => i.name + (i.p < 0.05 ? ' *' : ''));
        data = items.map(i => i.val ?? 0);
        colors = items.map(i => i.p < 0.05 ? '#0d9488' : '#94a3b8');
      } else {
        items = preds.map(p => ({ name: p.name, val: R.feature_importance[p.key] }));
        items.sort((a, b) => (b.val ?? 0) - (a.val ?? 0));
        labels = items.map(i => i.name); data = items.map(i => i.val ?? 0); colors = items.map(() => '#4f46e5');
      }
      this.charts.rg = new Chart(canvas, {
        type: 'bar',
        data: { labels, datasets: [{ data, backgroundColor: colors, borderRadius: 4, barThickness: 18 }] },
        options: {
          indexAxis: 'y', responsive: true, maintainAspectRatio: false,
          plugins: { legend: { display: false }, tooltip: { callbacks: { label: (ctx) => this.fmt(ctx.raw, 4) } } },
          scales: { x: { grid: { color: '#eef2f7' }, title: { display: true, text: this.rg.model === 'linear' ? 'Koefisien' : 'Importance' } }, y: { grid: { display: false } } },
        },
      });
    },

    // ---- correlation ----
    renderCorrelation() {
      if (this.resultsError()) return;
      this.initSelections();
      this.renderCorrMatrix();
      this.$nextTick(() => this.renderCorrBars());
    },
    renderCorrMatrix() {
      const el = document.getElementById('corrMatrix'); if (!el) return;
      const R = this.results; if (!R || R.error) { el.innerHTML = ''; return; }
      const m = R.spearman.matrix || [], preds = R.predictors || [], tgts = R.targets || [];
      let head = `<thead><tr><th class="text-left px-3 py-2 bg-slate-50">Prediktor</th>${tgts.map(t => `<th class="px-2 py-2 text-center bg-slate-50">${t.name}</th>`).join('')}</tr></thead><tbody>`;
      let body = '';
      preds.forEach(p => {
        body += `<tr><td class="px-3 py-1.5 font-semibold whitespace-nowrap">${p.name}</td>`;
        tgts.forEach(t => {
          const row = m.find(r => r.target === t.key); const cell = row?.cells.find(c => c.predictor === p.key);
          const v = cell?.value; const c = R.spearman.correlations?.[t.key]?.[p.key];
          const star = c?.significant ? '*' : '';
          const tip = `ρ=${this.fmt(v, 3)} · p=${this.fmt(c?.p_value, 4)}`;
          body += `<td class="cell px-2 py-1.5 text-center num" style="background:${this.clr(v)};color:${Math.abs(v ?? 0) > 0.55 ? '#fff' : '#0f172a'}" title="${tip}" onclick="window.__pickCorr('${t.key}','${p.key}')">${this.fmt(v, 2)}${star}</td>`;
        });
        body += '</tr>';
      });
      el.innerHTML = head + body + '</tbody>';
    },
    renderCorrBars() {
      const canvas = document.getElementById('crChart'); if (!canvas) return;
      if (this.charts.cr) { this.charts.cr.destroy(); this.charts.cr = null; }
      const R = this.results; if (!R || R.error) return;
      const corr = R.spearman.correlations?.[this.cr.target] || {};
      const preds = R.predictors || [];
      const items = preds.map(p => ({ name: p.name, val: corr[p.key]?.coefficient, p: corr[p.key]?.p_value, sig: corr[p.key]?.significant }));
      items.sort((a, b) => (b.val ?? 0) - (a.val ?? 0));
      this.charts.cr = new Chart(canvas, {
        type: 'bar',
        data: { labels: items.map(i => i.name + (i.sig ? ' *' : '')), datasets: [{ data: items.map(i => i.val ?? 0), backgroundColor: items.map(i => i.sig ? '#0d9488' : '#94a3b8'), borderRadius: 4, barThickness: 18 }] },
        options: {
          indexAxis: 'y', responsive: true, maintainAspectRatio: false,
          plugins: { legend: { display: false }, tooltip: { callbacks: { label: (ctx) => `${this.fmt(ctx.raw, 3)} (p=${this.fmt(items[ctx.dataIndex].p, 3)})` } } },
          scales: { x: { grid: { color: '#eef2f7' }, title: { display: true, text: 'ρ (Spearman)' } }, y: { grid: { display: false } } },
        },
      });
    },

    // ---- explorer ----
    exData() { return this.results?.province_data?.[this.ex.prov]; },
    renderExplorer() {
      if (this.resultsError()) return;
      this.initSelections();
      this.renderExTable();
    },
    renderExTable() {
      const el = document.getElementById('exTable'); if (!el) return;
      const R = this.results; if (!R || R.error) { el.innerHTML = ''; return; }
      const preds = R.predictors || [], tgts = R.targets || [];
      const rows = R.provinces.map(pv => { const d = R.province_data[pv]; return { pv, ...Object.fromEntries(preds.map(p => [p.key, d?.predictors?.[p.key]])), ...Object.fromEntries(tgts.map(t => [t.key, d?.targets?.[t.key]])) }; });
      const cols = [{ k: 'pv', label: 'Provinsi' }, ...preds.map(p => ({ k: p.key, label: p.name })), ...tgts.map(t => ({ k: t.key, label: t.name }))];
      const sk = this.ex.sortKey;
      rows.sort((a, b) => { const av = a[sk], bv = b[sk]; if (typeof av === 'string' || typeof bv === 'string') return String(av).localeCompare(String(bv)) * this.ex.sortDir; return ((av ?? 0) - (bv ?? 0)) * this.ex.sortDir; });
      const head = `<thead class="bg-slate-50 text-slate-600 sticky top-0"><tr>${cols.map(c => `<th class="cursor-pointer px-3 py-2 ${c.k === 'pv' ? 'text-left' : 'text-right num'}" onclick="window.__exSort('${c.k}')">${c.label}${this.ex.sortKey === c.k ? (this.ex.sortDir > 0 ? ' ▲' : ' ▼') : ''}</th>`).join('')}</tr></thead>`;
      const body = '<tbody>' + rows.map(r => '<tr class="border-t border-slate-100 hover:bg-slate-50">' + cols.map(c => c.k === 'pv' ? `<td class="px-3 py-2 font-semibold">${r.pv}</td>` : `<td class="px-3 py-2 text-right num">${this.fmt(r[c.k], 2)}</td>`).join('') + '</tr>').join('') + '</tbody>';
      el.innerHTML = head + body;
    },
  };
}
