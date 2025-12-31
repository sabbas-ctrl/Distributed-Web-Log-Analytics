import argparse
import json
import time
import threading
from pathlib import Path
from typing import Optional, List, Generator
from datetime import datetime

from flask import Flask, jsonify, send_file, abort, request, Response, stream_with_context
from flask import render_template_string

from analysis_core import parse_log_line, ip_to_region, new_stats, update_stats, summarize_stats, merge_stats


# ---------------------------------------------------------------------------
# HTML Template - Complete Redesign: Light theme + dark toggle, sidebar nav,
# per-chart filters, advanced charts, real-time updates
# ---------------------------------------------------------------------------

HTML_TEMPLATE = """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <title>Log Analytics Platform</title>
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.4/dist/chart.umd.min.js"></script>
  <script src="https://cdn.jsdelivr.net/npm/chartjs-plugin-datalabels@2.2.0/dist/chartjs-plugin-datalabels.min.js"></script>
  <style>
    :root {
      --bg: #f8fafc;
      --bg2: #ffffff;
      --text: #1e293b;
      --muted: #64748b;
      --border: #e2e8f0;
      --accent: #3b82f6;
      --accent2: #ef4444;
      --success: #22c55e;
      --warning: #f59e0b;
      --sidebar-bg: #1e293b;
      --sidebar-text: #f1f5f9;
      --shadow: 0 4px 6px -1px rgba(0,0,0,0.1), 0 2px 4px -2px rgba(0,0,0,0.1);
    }
    .dark {
      --bg: #0f172a;
      --bg2: #1e293b;
      --text: #f1f5f9;
      --muted: #94a3b8;
      --border: #334155;
      --sidebar-bg: #020617;
      --shadow: 0 4px 6px -1px rgba(0,0,0,0.4);
    }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body { font-family: 'Inter', 'Segoe UI', sans-serif; background: var(--bg); color: var(--text); display: flex; min-height: 100vh; transition: background 0.3s, color 0.3s; }
    
    /* Sidebar */
    .sidebar { width: 260px; background: var(--sidebar-bg); color: var(--sidebar-text); padding: 24px 16px; display: flex; flex-direction: column; gap: 8px; position: fixed; height: 100vh; overflow-y: auto; }
    .sidebar h1 { font-size: 18px; font-weight: 700; margin-bottom: 24px; display: flex; align-items: center; gap: 10px; }
    .sidebar h1 svg { width: 28px; height: 28px; }
    .nav-item { display: flex; align-items: center; gap: 12px; padding: 12px 16px; border-radius: 10px; cursor: pointer; transition: background 0.2s; font-size: 14px; font-weight: 500; }
    .nav-item:hover { background: rgba(255,255,255,0.1); }
    .nav-item.active { background: var(--accent); color: #fff; }
    .nav-item svg { width: 20px; height: 20px; opacity: 0.8; }
    .sidebar-footer { margin-top: auto; padding-top: 16px; border-top: 1px solid rgba(255,255,255,0.1); }
    .theme-toggle { display: flex; align-items: center; gap: 10px; padding: 12px 16px; border-radius: 10px; cursor: pointer; font-size: 14px; }
    .theme-toggle:hover { background: rgba(255,255,255,0.1); }
    
    /* Main content */
    .main { margin-left: 260px; flex: 1; padding: 24px 32px; }
    .header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 24px; flex-wrap: wrap; gap: 16px; }
    .header h2 { font-size: 24px; font-weight: 700; }
    .header-controls { display: flex; gap: 12px; flex-wrap: wrap; align-items: center; }
    
    /* Cards & Sections */
    .card { background: var(--bg2); border: 1px solid var(--border); border-radius: 16px; padding: 20px; box-shadow: var(--shadow); }
    .card-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; flex-wrap: wrap; gap: 12px; }
    .card-header h3 { font-size: 16px; font-weight: 600; }
    .card-filters { display: flex; gap: 8px; flex-wrap: wrap; }
    .grid { display: grid; gap: 20px; grid-template-columns: repeat(auto-fit, minmax(380px, 1fr)); }
    .grid-2 { grid-template-columns: repeat(2, 1fr); }
    .grid-3 { grid-template-columns: repeat(3, 1fr); }
    .grid-4 { grid-template-columns: repeat(4, 1fr); }
    @media (max-width: 1200px) { .grid-2, .grid-3, .grid-4 { grid-template-columns: 1fr; } }
    
    /* Form controls */
    select, input, button { font-family: inherit; font-size: 13px; }
    select, input { background: var(--bg); color: var(--text); border: 1px solid var(--border); border-radius: 8px; padding: 8px 12px; min-width: 140px; }
    select:focus, input:focus { outline: none; border-color: var(--accent); }
    .btn { background: var(--accent); color: #fff; border: none; border-radius: 8px; padding: 8px 16px; cursor: pointer; font-weight: 500; transition: background 0.2s; }
    .btn:hover { background: #2563eb; }
    .btn-secondary { background: var(--bg); color: var(--text); border: 1px solid var(--border); }
    .btn-secondary:hover { background: var(--border); }
    
    /* Stats */
    .stats-grid { display: grid; gap: 16px; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); margin-bottom: 24px; }
    .stat-card { background: var(--bg2); border: 1px solid var(--border); border-radius: 12px; padding: 16px; box-shadow: var(--shadow); }
    .stat-card .label { font-size: 12px; color: var(--muted); margin-bottom: 4px; text-transform: uppercase; letter-spacing: 0.5px; }
    .stat-card .value { font-size: 28px; font-weight: 700; }
    .stat-card .change { font-size: 12px; margin-top: 4px; }
    .stat-card .change.up { color: var(--success); }
    .stat-card .change.down { color: var(--accent2); }
    
    /* Charts */
    .chart-container { position: relative; height: 300px; }
    .chart-container.tall { height: 400px; }
    canvas { max-width: 100%; }
    
    /* Tables */
    .table-container { overflow-x: auto; }
    table { width: 100%; border-collapse: collapse; font-size: 13px; }
    th, td { padding: 12px 16px; text-align: left; border-bottom: 1px solid var(--border); }
    th { font-weight: 600; color: var(--muted); text-transform: uppercase; font-size: 11px; letter-spacing: 0.5px; }
    tr:hover { background: var(--bg); }
    
    /* Pills & badges */
    .pill { display: inline-block; padding: 4px 10px; border-radius: 20px; font-size: 12px; font-weight: 500; }
    .pill.success { background: rgba(34,197,94,0.15); color: var(--success); }
    .pill.error { background: rgba(239,68,68,0.15); color: var(--accent2); }
    .pill.warning { background: rgba(245,158,11,0.15); color: var(--warning); }
    .pill.info { background: rgba(59,130,246,0.15); color: var(--accent); }
    
    /* Views */
    .view { display: none; }
    .view.active { display: block; }
    
    /* Live indicator */
    .live-indicator { display: flex; align-items: center; gap: 6px; font-size: 12px; color: var(--success); }
    .live-dot { width: 8px; height: 8px; background: var(--success); border-radius: 50%; animation: pulse 2s infinite; }
    @keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.5; } }
    
    /* Loading */
    .loading { display: flex; justify-content: center; align-items: center; padding: 40px; color: var(--muted); }
    
    /* Subtle text */
    .subtle { color: var(--muted); font-size: 12px; }
  </style>
</head>
<body>
  <aside class="sidebar">
    <h1>
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 20V10M18 20V4M6 20v-4"/></svg>
      Log Analytics
    </h1>
    <div class="nav-item active" data-view="overview">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/></svg>
      Overview
    </div>
    <div class="nav-item" data-view="servers">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="2" y="2" width="20" height="8" rx="2"/><rect x="2" y="14" width="20" height="8" rx="2"/><circle cx="6" cy="6" r="1"/><circle cx="6" cy="18" r="1"/></svg>
      Servers
    </div>
    <div class="nav-item" data-view="traffic">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="22,12 18,12 15,21 9,3 6,12 2,12"/></svg>
      Traffic Analysis
    </div>
    <div class="nav-item" data-view="geography">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="2" y1="12" x2="22" y2="12"/><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/></svg>
      Geography
    </div>
    <div class="nav-item" data-view="errors">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
      Errors & Status
    </div>
    <div class="nav-item" data-view="paths">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14,2 14,8 20,8"/></svg>
      Paths & URLs
    </div>
    <div class="nav-item" data-view="logs">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="8" y1="6" x2="21" y2="6"/><line x1="8" y1="12" x2="21" y2="12"/><line x1="8" y1="18" x2="21" y2="18"/><line x1="3" y1="6" x2="3.01" y2="6"/><line x1="3" y1="12" x2="3.01" y2="12"/><line x1="3" y1="18" x2="3.01" y2="18"/></svg>
      Raw Logs
    </div>
    <div class="sidebar-footer">
      <div class="theme-toggle" id="themeToggle">
        <svg id="themeIcon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="width:20px;height:20px"><circle cx="12" cy="12" r="5"/><path d="M12 1v2M12 21v2M4.22 4.22l1.42 1.42M18.36 18.36l1.42 1.42M1 12h2M21 12h2M4.22 19.78l1.42-1.42M18.36 5.64l1.42-1.42"/></svg>
        <span id="themeLabel">Dark Mode</span>
      </div>
    </div>
  </aside>

  <main class="main">
    <!-- OVERVIEW -->
    <div id="view-overview" class="view active">
      <div class="header">
        <h2>Overview Dashboard</h2>
        <div class="header-controls">
          <select id="globalRegion">
            <option value="All">All Regions</option>
          </select>
          <select id="globalServer">
            <option value="All">All Servers</option>
          </select>
          <div class="live-indicator" id="liveIndicator" style="display:none">
            <span class="live-dot"></span> Live
          </div>
        </div>
      </div>
      
      <div class="stats-grid" id="statsGrid"></div>
      
      <div class="grid">
        <div class="card">
          <div class="card-header">
            <h3>Requests per Server</h3>
            <div class="card-filters">
              <select id="reqChartType"><option value="bar">Bar</option><option value="doughnut">Doughnut</option><option value="polarArea">Polar</option></select>
            </div>
          </div>
          <div class="chart-container"><canvas id="requestsChart"></canvas></div>
        </div>
        <div class="card">
          <div class="card-header">
            <h3>Error Rate by Server</h3>
            <div class="card-filters">
              <select id="errChartType"><option value="bar">Bar</option><option value="line">Line</option></select>
            </div>
          </div>
          <div class="chart-container"><canvas id="errorsChart"></canvas></div>
        </div>
        <div class="card">
          <div class="card-header">
            <h3>Hourly Traffic Distribution</h3>
            <div class="card-filters">
              <select id="hourlyChartType"><option value="line">Line</option><option value="bar">Bar</option></select>
              <select id="hourlyStack"><option value="global">Global</option><option value="stacked">Stacked by Server</option></select>
            </div>
          </div>
          <div class="chart-container tall"><canvas id="hourlyChart"></canvas></div>
        </div>
        <div class="card">
          <div class="card-header">
            <h3>HTTP Methods Distribution</h3>
          </div>
          <div class="chart-container"><canvas id="methodsChart"></canvas></div>
        </div>
      </div>
    </div>

    <!-- SERVERS -->
    <div id="view-servers" class="view">
      <div class="header">
        <h2>Server Analysis</h2>
        <div class="header-controls">
          <select id="serverPicker"></select>
        </div>
      </div>
      <div class="stats-grid" id="serverStats"></div>
      <div class="grid">
        <div class="card">
          <div class="card-header"><h3>Status Codes</h3></div>
          <div class="chart-container"><canvas id="serverStatusChart"></canvas></div>
        </div>
        <div class="card">
          <div class="card-header"><h3>Methods</h3></div>
          <div class="chart-container"><canvas id="serverMethodChart"></canvas></div>
        </div>
        <div class="card">
          <div class="card-header"><h3>Region Distribution</h3></div>
          <div class="chart-container"><canvas id="serverRegionChart"></canvas></div>
        </div>
        <div class="card">
          <div class="card-header"><h3>Hourly Traffic</h3></div>
          <div class="chart-container"><canvas id="serverHoursChart"></canvas></div>
        </div>
        <div class="card" style="grid-column: span 2;">
          <div class="card-header"><h3>Top Paths</h3></div>
          <div class="table-container">
            <table id="serverPathsTable">
              <thead><tr><th>Path</th><th>Count</th><th>Share</th></tr></thead>
              <tbody></tbody>
            </table>
          </div>
        </div>
      </div>
    </div>

    <!-- TRAFFIC -->
    <div id="view-traffic" class="view">
      <div class="header">
        <h2>Traffic Analysis</h2>
        <div class="header-controls">
          <select id="trafficServerFilter" multiple style="min-width:200px"></select>
        </div>
      </div>
      <div class="grid">
        <div class="card" style="grid-column: span 2;">
          <div class="card-header">
            <h3>Hourly Requests by Server</h3>
            <div class="card-filters">
              <select id="trafficChartType"><option value="line">Line</option><option value="bar">Stacked Bar</option></select>
            </div>
          </div>
          <div class="chart-container tall"><canvas id="trafficChart"></canvas></div>
        </div>
        <div class="card">
          <div class="card-header"><h3>Request Volume Comparison</h3></div>
          <div class="chart-container"><canvas id="volumeChart"></canvas></div>
        </div>
        <div class="card">
          <div class="card-header"><h3>Bytes Transferred</h3></div>
          <div class="chart-container"><canvas id="bytesChart"></canvas></div>
        </div>
      </div>
    </div>

    <!-- GEOGRAPHY -->
    <div id="view-geography" class="view">
      <div class="header">
        <h2>Geographic Distribution</h2>
      </div>
      <div class="grid">
        <div class="card">
          <div class="card-header"><h3>Global Region Distribution</h3></div>
          <div class="chart-container tall"><canvas id="geoGlobalChart"></canvas></div>
        </div>
        <div class="card">
          <div class="card-header"><h3>Region by Server</h3></div>
          <div class="chart-container tall"><canvas id="geoServerChart"></canvas></div>
        </div>
        <div class="card" style="grid-column: span 2;">
          <div class="card-header"><h3>Region Breakdown</h3></div>
          <div class="table-container">
            <table id="geoTable">
              <thead><tr><th>Region</th><th>Requests</th><th>Share</th><th>Trend</th></tr></thead>
              <tbody></tbody>
            </table>
          </div>
        </div>
      </div>
    </div>

    <!-- ERRORS -->
    <div id="view-errors" class="view">
      <div class="header">
        <h2>Errors & Status Codes</h2>
        <div class="header-controls">
          <select id="errorServerFilter"><option value="All">All Servers</option></select>
        </div>
      </div>
      <div class="grid">
        <div class="card">
          <div class="card-header"><h3>Status Code Distribution</h3></div>
          <div class="chart-container"><canvas id="statusChart"></canvas></div>
        </div>
        <div class="card">
          <div class="card-header"><h3>Error Rate by Server</h3></div>
          <div class="chart-container"><canvas id="errorRateChart"></canvas></div>
        </div>
        <div class="card" style="grid-column: span 2;">
          <div class="card-header"><h3>Status Code Breakdown</h3></div>
          <div class="table-container">
            <table id="statusTable">
              <thead><tr><th>Status</th><th>Count</th><th>Share</th><th>Category</th></tr></thead>
              <tbody></tbody>
            </table>
          </div>
        </div>
      </div>
    </div>

    <!-- PATHS -->
    <div id="view-paths" class="view">
      <div class="header">
        <h2>Paths & URL Analysis</h2>
        <div class="header-controls">
          <select id="pathServerFilter"><option value="">All Servers</option></select>
          <input id="pathSearch" placeholder="Search paths..." style="min-width:200px" />
        </div>
      </div>
      <div class="grid">
        <div class="card">
          <div class="card-header"><h3>Top Paths</h3></div>
          <div class="chart-container tall"><canvas id="pathsChart"></canvas></div>
        </div>
        <div class="card" style="grid-column: span 1;">
          <div class="card-header"><h3>Path Details</h3></div>
          <div class="table-container">
            <table id="pathsTable">
              <thead><tr><th>Path</th><th>Count</th><th>Share</th></tr></thead>
              <tbody></tbody>
            </table>
          </div>
        </div>
      </div>
    </div>

    <!-- RAW LOGS -->
    <div id="view-logs" class="view">
      <div class="header">
        <h2>Raw Logs</h2>
      </div>
      <div class="card">
        <div class="card-header">
          <h3>Log Entries</h3>
          <div class="card-filters">
            <select id="logServer"></select>
            <select id="logStatus"><option value="">All Status</option><option value="2">2xx</option><option value="3">3xx</option><option value="4">4xx</option><option value="5">5xx</option></select>
            <select id="logMethod"><option value="">All Methods</option><option>GET</option><option>POST</option><option>PUT</option><option>DELETE</option></select>
            <select id="logRegion"><option value="">All Regions</option></select>
            <input id="logPath" placeholder="Path contains..." />
            <button class="btn" id="logReload">Reload</button>
          </div>
        </div>
        <div class="table-container">
          <table id="logTable">
            <thead><tr><th>Time</th><th>IP</th><th>Region</th><th>Method</th><th>Path</th><th>Status</th><th>Bytes</th></tr></thead>
            <tbody></tbody>
          </table>
        </div>
        <div class="subtle" style="margin-top:12px">Showing up to 200 entries. Use filters to narrow results.</div>
      </div>
    </div>
  </main>

<script>
// State
let summaryData = null;
let metaData = null;
let charts = {};
let darkMode = localStorage.getItem('darkMode') === 'true';

// Theme
function applyTheme() {
  document.body.classList.toggle('dark', darkMode);
  document.getElementById('themeLabel').textContent = darkMode ? 'Light Mode' : 'Dark Mode';
  // Update chart colors if needed
  Object.values(charts).forEach(c => c && c.update && c.update());
}

// API
async function fetchJSON(url) {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`Failed: ${url}`);
  return res.json();
}

async function loadSummary() { return fetchJSON('/api/summary'); }
async function loadMeta() { return fetchJSON('/api/meta'); }
async function loadTimeseries(servers) {
  const params = servers && servers.length ? `?servers=${servers.join(',')}` : '';
  return fetchJSON(`/api/timeseries${params}`);
}
async function loadRaw(opts) {
  const url = new URL('/api/raw', location.origin);
  if (opts.server) url.searchParams.set('server', opts.server);
  if (opts.status_class) url.searchParams.set('status_class', opts.status_class);
  if (opts.method) url.searchParams.set('method', opts.method);
  if (opts.region) url.searchParams.set('region', opts.region);
  if (opts.path_sub) url.searchParams.set('path_sub', opts.path_sub);
  url.searchParams.set('limit', '200');
  return fetchJSON(url);
}

// Utilities
function toSorted(obj) { return Object.entries(obj || {}).sort((a,b) => a[0].localeCompare(b[0])); }
function destroy(id) { if (charts[id]) { charts[id].destroy(); delete charts[id]; } }
const palette = ['#3b82f6','#ef4444','#22c55e','#f59e0b','#8b5cf6','#06b6d4','#ec4899','#84cc16'];

function getChartColors(isDark) {
  return {
    gridColor: isDark ? 'rgba(255,255,255,0.1)' : 'rgba(0,0,0,0.1)',
    textColor: isDark ? '#94a3b8' : '#64748b',
  };
}

function chartDefaults() {
  const colors = getChartColors(darkMode);
  return {
    responsive: true,
    maintainAspectRatio: false,
    plugins: { legend: { labels: { color: colors.textColor } } },
    scales: {
      x: { grid: { color: colors.gridColor }, ticks: { color: colors.textColor } },
      y: { grid: { color: colors.gridColor }, ticks: { color: colors.textColor }, beginAtZero: true },
    }
  };
}

// Build filters
function buildFilters() {
  const regions = ['All', ...(metaData?.regions || [])];
  const servers = metaData?.servers || Object.keys(summaryData.servers || {});
  
  // Global filters
  const globalRegion = document.getElementById('globalRegion');
  const globalServer = document.getElementById('globalServer');
  globalRegion.innerHTML = regions.map(r => `<option value="${r}">${r === 'All' ? 'All Regions' : r}</option>`).join('');
  globalServer.innerHTML = ['All', ...servers].map(s => `<option value="${s}">${s === 'All' ? 'All Servers' : s}</option>`).join('');
  
  // Server picker
  const serverPicker = document.getElementById('serverPicker');
  serverPicker.innerHTML = servers.map(s => `<option value="${s}">${s}</option>`).join('');
  
  // Traffic filter (multi-select visual)
  const trafficFilter = document.getElementById('trafficServerFilter');
  trafficFilter.innerHTML = servers.map(s => `<option value="${s}" selected>${s}</option>`).join('');
  
  // Error filter
  const errorFilter = document.getElementById('errorServerFilter');
  errorFilter.innerHTML = ['All', ...servers].map(s => `<option value="${s}">${s === 'All' ? 'All Servers' : s}</option>`).join('');
  
  // Path filter
  const pathFilter = document.getElementById('pathServerFilter');
  pathFilter.innerHTML = ['', ...servers].map(s => `<option value="${s}">${s || 'All Servers'}</option>`).join('');
  
  // Log filters
  const logServer = document.getElementById('logServer');
  logServer.innerHTML = servers.map(s => `<option value="${s}">${s}</option>`).join('');
  const logRegion = document.getElementById('logRegion');
  logRegion.innerHTML = ['', ...regions.filter(r => r !== 'All')].map(r => `<option value="${r}">${r || 'All Regions'}</option>`).join('');
}

// Stats Grid
function renderStatsGrid() {
  const g = summaryData.global || {};
  const rankings = summaryData.rankings || {};
  const html = `
    <div class="stat-card"><div class="label">Total Requests</div><div class="value">${(g.total_requests || 0).toLocaleString()}</div></div>
    <div class="stat-card"><div class="label">Total Bytes</div><div class="value">${((g.total_bytes || 0) / (1024*1024)).toFixed(2)} MB</div></div>
    <div class="stat-card"><div class="label">Error Rate</div><div class="value">${((g.error_rate || 0) * 100).toFixed(2)}%</div></div>
    <div class="stat-card"><div class="label">Peak Hour</div><div class="value">${g.peak_hour ?? '-'}:00</div></div>
    <div class="stat-card"><div class="label">Busiest Server</div><div class="value">${rankings.busiest_server || '-'}</div></div>
    <div class="stat-card"><div class="label">Most Errors</div><div class="value">${rankings.highest_error_server || '-'}</div></div>
  `;
  document.getElementById('statsGrid').innerHTML = html;
}

// Overview Charts
function renderOverviewCharts() {
  const region = document.getElementById('globalRegion').value;
  const serverFilter = document.getElementById('globalServer').value;
  const servers = summaryData.servers || {};
  let names = Object.keys(servers);
  if (serverFilter !== 'All') names = names.filter(n => n === serverFilter);
  
  const reqs = names.map(n => region === 'All' ? (servers[n].total_requests || 0) : ((servers[n].region_distribution || {})[region] || 0));
  const errs = names.map(n => (servers[n].error_rate || 0) * 100);
  
  // Requests chart
  const reqType = document.getElementById('reqChartType').value;
  destroy('requests');
  charts.requests = new Chart(document.getElementById('requestsChart'), {
    type: reqType,
    data: { labels: names, datasets: [{ label: 'Requests', data: reqs, backgroundColor: palette.slice(0, names.length), borderColor: palette.slice(0, names.length), borderWidth: 1 }] },
    options: { ...chartDefaults(), plugins: { legend: { display: reqType !== 'bar' } } }
  });
  
  // Errors chart
  const errType = document.getElementById('errChartType').value;
  destroy('errors');
  charts.errors = new Chart(document.getElementById('errorsChart'), {
    type: errType,
    data: { labels: names, datasets: [{ label: 'Error %', data: errs, backgroundColor: '#ef4444', borderColor: '#ef4444', borderWidth: 2, fill: false, tension: 0.3 }] },
    options: { ...chartDefaults(), plugins: { legend: { display: false } } }
  });
  
  // Hourly chart
  renderHourlyChart();
  
  // Methods chart
  const methods = toSorted(summaryData.global?.method_breakdown || {});
  destroy('methods');
  charts.methods = new Chart(document.getElementById('methodsChart'), {
    type: 'doughnut',
    data: { labels: methods.map(([k]) => k), datasets: [{ data: methods.map(([,v]) => v), backgroundColor: palette }] },
    options: { ...chartDefaults(), scales: {} }
  });
}

function renderHourlyChart() {
  const type = document.getElementById('hourlyChartType').value;
  const stack = document.getElementById('hourlyStack').value;
  const hours = Array.from({length:24}, (_,i) => i);
  
  if (stack === 'global') {
    const counts = hours.map(h => (summaryData.global?.hour_histogram || {})[h] || 0);
    destroy('hourly');
    charts.hourly = new Chart(document.getElementById('hourlyChart'), {
      type,
      data: { labels: hours.map(h => `${h}:00`), datasets: [{ label: 'Requests', data: counts, backgroundColor: '#3b82f6', borderColor: '#3b82f6', tension: 0.3, fill: type === 'line' }] },
      options: chartDefaults()
    });
  } else {
    const servers = summaryData.servers || {};
    const datasets = Object.entries(servers).map(([name, data], idx) => ({
      label: name,
      data: hours.map(h => (data.hour_histogram || {})[h] || 0),
      backgroundColor: palette[idx % palette.length],
      borderColor: palette[idx % palette.length],
      tension: 0.3,
      fill: type === 'line',
      stack: 'stack1',
    }));
    destroy('hourly');
    charts.hourly = new Chart(document.getElementById('hourlyChart'), {
      type,
      data: { labels: hours.map(h => `${h}:00`), datasets },
      options: { ...chartDefaults(), plugins: { legend: { display: true } }, scales: { ...chartDefaults().scales, x: { ...chartDefaults().scales.x, stacked: type === 'bar' }, y: { ...chartDefaults().scales.y, stacked: type === 'bar' } } }
    });
  }
}

// Server view
function renderServerView() {
  const name = document.getElementById('serverPicker').value;
  const data = summaryData.servers?.[name];
  if (!data) return;
  
  // Stats
  const html = `
    <div class="stat-card"><div class="label">Requests</div><div class="value">${(data.total_requests || 0).toLocaleString()}</div></div>
    <div class="stat-card"><div class="label">Bytes</div><div class="value">${((data.total_bytes || 0) / (1024*1024)).toFixed(2)} MB</div></div>
    <div class="stat-card"><div class="label">Error Rate</div><div class="value">${((data.error_rate || 0) * 100).toFixed(2)}%</div></div>
    <div class="stat-card"><div class="label">Peak Hour</div><div class="value">${data.peak_hour ?? '-'}:00</div></div>
  `;
  document.getElementById('serverStats').innerHTML = html;
  
  // Charts
  const status = toSorted(data.status_breakdown || {});
  destroy('serverStatus');
  charts.serverStatus = new Chart(document.getElementById('serverStatusChart'), {
    type: 'bar',
    data: { labels: status.map(([k]) => k), datasets: [{ label: 'Count', data: status.map(([,v]) => v), backgroundColor: palette }] },
    options: chartDefaults()
  });
  
  const methods = toSorted(data.method_breakdown || {});
  destroy('serverMethod');
  charts.serverMethod = new Chart(document.getElementById('serverMethodChart'), {
    type: 'doughnut',
    data: { labels: methods.map(([k]) => k), datasets: [{ data: methods.map(([,v]) => v), backgroundColor: palette }] },
    options: { ...chartDefaults(), scales: {} }
  });
  
  const regions = toSorted(data.region_distribution || {});
  destroy('serverRegion');
  charts.serverRegion = new Chart(document.getElementById('serverRegionChart'), {
    type: 'polarArea',
    data: { labels: regions.map(([k]) => k), datasets: [{ data: regions.map(([,v]) => v), backgroundColor: palette }] },
    options: { ...chartDefaults(), scales: {} }
  });
  
  const hours = Array.from({length:24}, (_,i) => i);
  const hourCounts = hours.map(h => (data.hour_histogram || {})[h] || 0);
  destroy('serverHours');
  charts.serverHours = new Chart(document.getElementById('serverHoursChart'), {
    type: 'line',
    data: { labels: hours.map(h => `${h}:00`), datasets: [{ label: 'Requests', data: hourCounts, borderColor: '#3b82f6', tension: 0.3, fill: true, backgroundColor: 'rgba(59,130,246,0.1)' }] },
    options: chartDefaults()
  });
  
  // Paths table
  const total = data.total_requests || 1;
  const tbody = document.querySelector('#serverPathsTable tbody');
  tbody.innerHTML = (data.top_paths || []).map(p => `
    <tr><td>${p.path}</td><td>${p.count.toLocaleString()}</td><td>${((p.count / total) * 100).toFixed(1)}%</td></tr>
  `).join('');
}

// Traffic view
async function renderTrafficView() {
  const selected = Array.from(document.getElementById('trafficServerFilter').selectedOptions).map(o => o.value);
  const ts = await loadTimeseries(selected.length ? selected : undefined);
  const hours = ts.hours.map(h => `${h}:00`);
  const type = document.getElementById('trafficChartType').value;
  
  const datasets = Object.entries(ts.per_server || {}).map(([name, series], idx) => ({
    label: name,
    data: series,
    backgroundColor: palette[idx % palette.length],
    borderColor: palette[idx % palette.length],
    tension: 0.3,
    fill: false,
    stack: type === 'bar' ? 'stack1' : undefined,
  }));
  
  destroy('traffic');
  charts.traffic = new Chart(document.getElementById('trafficChart'), {
    type,
    data: { labels: hours, datasets },
    options: { ...chartDefaults(), scales: { x: { ...chartDefaults().scales.x, stacked: type === 'bar' }, y: { ...chartDefaults().scales.y, stacked: type === 'bar' } } }
  });
  
  // Volume comparison
  const servers = summaryData.servers || {};
  const names = Object.keys(servers);
  destroy('volume');
  charts.volume = new Chart(document.getElementById('volumeChart'), {
    type: 'bar',
    data: { labels: names, datasets: [{ label: 'Requests', data: names.map(n => servers[n].total_requests || 0), backgroundColor: palette }] },
    options: chartDefaults()
  });
  
  // Bytes
  destroy('bytes');
  charts.bytes = new Chart(document.getElementById('bytesChart'), {
    type: 'bar',
    data: { labels: names, datasets: [{ label: 'Bytes (MB)', data: names.map(n => (servers[n].total_bytes || 0) / (1024*1024)), backgroundColor: palette.slice().reverse() }] },
    options: chartDefaults()
  });
}

// Geography view
function renderGeographyView() {
  const regions = toSorted(summaryData.global?.region_distribution || {});
  const total = regions.reduce((a, [,v]) => a + v, 0) || 1;
  
  destroy('geoGlobal');
  charts.geoGlobal = new Chart(document.getElementById('geoGlobalChart'), {
    type: 'doughnut',
    data: { labels: regions.map(([k]) => k), datasets: [{ data: regions.map(([,v]) => v), backgroundColor: palette }] },
    options: { ...chartDefaults(), scales: {} }
  });
  
  // Stacked bar by server
  const servers = summaryData.servers || {};
  const regionNames = regions.map(([k]) => k);
  const datasets = Object.entries(servers).map(([name, data], idx) => ({
    label: name,
    data: regionNames.map(r => (data.region_distribution || {})[r] || 0),
    backgroundColor: palette[idx % palette.length],
  }));
  
  destroy('geoServer');
  charts.geoServer = new Chart(document.getElementById('geoServerChart'), {
    type: 'bar',
    data: { labels: regionNames, datasets },
    options: { ...chartDefaults(), scales: { x: { ...chartDefaults().scales.x, stacked: true }, y: { ...chartDefaults().scales.y, stacked: true } } }
  });
  
  // Table
  const tbody = document.querySelector('#geoTable tbody');
  tbody.innerHTML = regions.map(([region, count]) => `
    <tr><td>${region}</td><td>${count.toLocaleString()}</td><td>${((count / total) * 100).toFixed(1)}%</td><td><span class="pill info">Active</span></td></tr>
  `).join('');
}

// Errors view
function renderErrorsView() {
  const serverFilter = document.getElementById('errorServerFilter').value;
  let statusData, total;
  
  if (serverFilter === 'All') {
    statusData = toSorted(summaryData.global?.status_breakdown || {});
    total = summaryData.global?.total_requests || 1;
  } else {
    const s = summaryData.servers?.[serverFilter] || {};
    statusData = toSorted(s.status_breakdown || {});
    total = s.total_requests || 1;
  }
  
  destroy('status');
  charts.status = new Chart(document.getElementById('statusChart'), {
    type: 'doughnut',
    data: { labels: statusData.map(([k]) => k), datasets: [{ data: statusData.map(([,v]) => v), backgroundColor: palette }] },
    options: { ...chartDefaults(), scales: {} }
  });
  
  // Error rate by server
  const servers = summaryData.servers || {};
  const names = Object.keys(servers);
  destroy('errorRate');
  charts.errorRate = new Chart(document.getElementById('errorRateChart'), {
    type: 'bar',
    data: { labels: names, datasets: [{ label: 'Error %', data: names.map(n => (servers[n].error_rate || 0) * 100), backgroundColor: '#ef4444' }] },
    options: chartDefaults()
  });
  
  // Table
  const tbody = document.querySelector('#statusTable tbody');
  tbody.innerHTML = statusData.map(([status, count]) => {
    const cat = status < 300 ? 'success' : status < 400 ? 'info' : status < 500 ? 'warning' : 'error';
    const catLabel = status < 300 ? 'Success' : status < 400 ? 'Redirect' : status < 500 ? 'Client Error' : 'Server Error';
    return `<tr><td>${status}</td><td>${count.toLocaleString()}</td><td>${((count / total) * 100).toFixed(1)}%</td><td><span class="pill ${cat}">${catLabel}</span></td></tr>`;
  }).join('');
}

// Paths view
async function renderPathsView() {
  const server = document.getElementById('pathServerFilter').value;
  const search = document.getElementById('pathSearch').value.toLowerCase();
  
  let paths = [];
  if (server) {
    paths = (summaryData.servers?.[server]?.top_paths || []).slice();
  } else {
    const counter = {};
    Object.values(summaryData.servers || {}).forEach(s => {
      (s.top_paths || []).forEach(p => { counter[p.path] = (counter[p.path] || 0) + p.count; });
    });
    paths = Object.entries(counter).map(([path, count]) => ({ path, count })).sort((a,b) => b.count - a.count).slice(0, 20);
  }
  
  if (search) paths = paths.filter(p => p.path.toLowerCase().includes(search));
  const total = paths.reduce((a, p) => a + p.count, 0) || 1;
  
  destroy('paths');
  charts.paths = new Chart(document.getElementById('pathsChart'), {
    type: 'bar',
    data: { labels: paths.slice(0,15).map(p => p.path), datasets: [{ label: 'Hits', data: paths.slice(0,15).map(p => p.count), backgroundColor: palette }] },
    options: { ...chartDefaults(), indexAxis: 'y' }
  });
  
  const tbody = document.querySelector('#pathsTable tbody');
  tbody.innerHTML = paths.map(p => `
    <tr><td>${p.path}</td><td>${p.count.toLocaleString()}</td><td>${((p.count / total) * 100).toFixed(1)}%</td></tr>
  `).join('');
}

// Logs view
async function renderLogsView() {
  const server = document.getElementById('logServer').value;
  if (!server) return;
  
  try {
    const data = await loadRaw({
      server,
      status_class: document.getElementById('logStatus').value,
      method: document.getElementById('logMethod').value,
      region: document.getElementById('logRegion').value,
      path_sub: document.getElementById('logPath').value,
    });
    
    const tbody = document.querySelector('#logTable tbody');
    tbody.innerHTML = data.items.map(item => {
      const statusClass = item.status < 300 ? 'success' : item.status < 400 ? 'info' : item.status < 500 ? 'warning' : 'error';
      return `<tr><td>${item.time}</td><td>${item.ip}</td><td>${item.region}</td><td>${item.method}</td><td>${item.path}</td><td><span class="pill ${statusClass}">${item.status}</span></td><td>${item.bytes}</td></tr>`;
    }).join('');
  } catch (err) {
    console.error(err);
    document.querySelector('#logTable tbody').innerHTML = '<tr><td colspan="7" style="text-align:center;color:var(--muted)">Failed to load logs. Make sure --logs-dir is provided.</td></tr>';
  }
}

// Navigation
function wireNav() {
  document.querySelectorAll('.nav-item').forEach(item => {
    item.addEventListener('click', () => {
      document.querySelectorAll('.nav-item').forEach(i => i.classList.remove('active'));
      document.querySelectorAll('.view').forEach(v => v.classList.remove('active'));
      item.classList.add('active');
      const view = item.dataset.view;
      document.getElementById(`view-${view}`).classList.add('active');
      
      // Render view
      if (view === 'servers') renderServerView();
      if (view === 'traffic') renderTrafficView();
      if (view === 'geography') renderGeographyView();
      if (view === 'errors') renderErrorsView();
      if (view === 'paths') renderPathsView();
      if (view === 'logs') renderLogsView();
    });
  });
}

// Wire filter events
function wireFilters() {
  document.getElementById('globalRegion').addEventListener('change', renderOverviewCharts);
  document.getElementById('globalServer').addEventListener('change', renderOverviewCharts);
  document.getElementById('reqChartType').addEventListener('change', renderOverviewCharts);
  document.getElementById('errChartType').addEventListener('change', renderOverviewCharts);
  document.getElementById('hourlyChartType').addEventListener('change', renderHourlyChart);
  document.getElementById('hourlyStack').addEventListener('change', renderHourlyChart);
  document.getElementById('serverPicker').addEventListener('change', renderServerView);
  document.getElementById('trafficServerFilter').addEventListener('change', renderTrafficView);
  document.getElementById('trafficChartType').addEventListener('change', renderTrafficView);
  document.getElementById('errorServerFilter').addEventListener('change', renderErrorsView);
  document.getElementById('pathServerFilter').addEventListener('change', renderPathsView);
  document.getElementById('pathSearch').addEventListener('input', renderPathsView);
  document.getElementById('logReload').addEventListener('click', renderLogsView);
  
  document.getElementById('themeToggle').addEventListener('click', () => {
    darkMode = !darkMode;
    localStorage.setItem('darkMode', darkMode);
    applyTheme();
    // Re-render charts with new colors
    renderOverviewCharts();
    const activeView = document.querySelector('.nav-item.active')?.dataset.view;
    if (activeView === 'servers') renderServerView();
    if (activeView === 'traffic') renderTrafficView();
    if (activeView === 'geography') renderGeographyView();
    if (activeView === 'errors') renderErrorsView();
    if (activeView === 'paths') renderPathsView();
  });
}

// Real-time updates via SSE
function setupRealtime() {
  if (typeof(EventSource) === 'undefined') return;
  
  try {
    const es = new EventSource('/api/stream');
    es.onmessage = (e) => {
      try {
        const data = JSON.parse(e.data);
        if (data.type === 'summary') {
          summaryData = data.payload;
          renderStatsGrid();
          renderOverviewCharts();
          document.getElementById('liveIndicator').style.display = 'flex';
        }
      } catch (err) {
        console.error('SSE parse error', err);
      }
    };
    es.onerror = () => {
      document.getElementById('liveIndicator').style.display = 'none';
    };
  } catch (err) {
    console.log('SSE not available');
  }
}

// Init
(async () => {
  applyTheme();
  try {
    [summaryData, metaData] = await Promise.all([loadSummary(), loadMeta().catch(() => null)]);
    buildFilters();
    renderStatsGrid();
    renderOverviewCharts();
    wireNav();
    wireFilters();
    setupRealtime();
  } catch (err) {
    console.error(err);
    document.getElementById('statsGrid').innerHTML = '<div class="stat-card"><div class="label">Error</div><div class="value">Failed to load data</div></div>';
  }
})();
</script>
</body>
</html>
"""


# ---------------------------------------------------------------------------
# Flask Application
# ---------------------------------------------------------------------------

def load_summary(summary_path: Path):
    if not summary_path.exists():
        abort(404, "Summary JSON not found; run parallel_analyzer first")
    with open(summary_path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def available_regions(summary: dict) -> List[str]:
    regions = set()
    if summary.get("global", {}).get("region_distribution"):
        regions.update(summary["global"]["region_distribution"].keys())
    for server in summary.get("servers", {}).values():
        regions.update((server.get("region_distribution") or {}).keys())
    return sorted(regions)


def create_app(summary_path: Path, plot_path: Optional[Path] = None, logs_dir: Optional[Path] = None):
    app = Flask(__name__)
    
    # Shared state for real-time updates
    summary_cache = {"data": None, "mtime": 0}
    
    def get_summary():
        """Load summary with caching based on mtime."""
        if summary_path.exists():
            mtime = summary_path.stat().st_mtime
            if summary_cache["data"] is None or mtime > summary_cache["mtime"]:
                summary_cache["data"] = load_summary(summary_path)
                summary_cache["mtime"] = mtime
        return summary_cache["data"]

    @app.get("/")
    def index():
        return render_template_string(HTML_TEMPLATE, summary_path=summary_path)

    @app.get("/api/summary")
    def summary():
        return jsonify(get_summary())

    @app.get("/api/meta")
    def meta():
        summary = get_summary()
        servers = sorted(summary.get("servers", {}).keys())
        regions = available_regions(summary)
        return jsonify({"servers": servers, "regions": regions})

    @app.get("/api/servers")
    def servers():
        summary = get_summary()
        return jsonify(summary.get("servers", {}))

    @app.get("/api/server/<name>")
    def server_detail(name: str):
        summary = get_summary()
        server = summary.get("servers", {}).get(name)
        if not server:
            abort(404, f"Server {name} not found")
        return jsonify(server)

    @app.get("/api/top-paths")
    def top_paths():
        summary = get_summary()
        server = request.args.get("server")
        top_k = int(request.args.get("k", 10))
        if server:
            data = summary.get("servers", {}).get(server)
            if not data:
                abort(404, f"Server {server} not found")
            return jsonify(data.get("top_paths", [])[:top_k])
        counter = {}
        for data in summary.get("servers", {}).values():
            for entry in data.get("top_paths", []):
                counter[entry["path"]] = counter.get(entry["path"], 0) + entry["count"]
        merged = sorted(counter.items(), key=lambda x: x[1], reverse=True)[:top_k]
        return jsonify([{"path": p, "count": c} for p, c in merged])

    @app.get("/api/timeseries")
    def timeseries():
        summary = get_summary()
        servers_param = request.args.get("servers")
        selected = set(servers_param.split(",")) if servers_param else None
        hours = list(range(24))
        per_server = {}
        for name, data in summary.get("servers", {}).items():
            if selected and name not in selected:
                continue
            hist = data.get("hour_histogram", {}) or {}
            per_server[name] = [hist.get(str(h), hist.get(h, 0)) for h in hours]
        global_hist = summary.get("global", {}).get("hour_histogram", {}) or {}
        global_series = [global_hist.get(str(h), global_hist.get(h, 0)) for h in hours]
        return jsonify({"hours": hours, "per_server": per_server, "global": global_series})

    @app.get("/api/raw")
    def raw_logs():
        if logs_dir is None:
            abort(400, "Raw log browsing disabled; provide --logs-dir")
        server = request.args.get("server")
        if not server:
            abort(400, "server query param required")
        log_path = logs_dir / f"{server}.log"
        if not log_path.exists():
            abort(404, f"Log file not found for server {server}")

        offset = int(request.args.get("offset", 0))
        limit = min(int(request.args.get("limit", 200)), 2000)
        status_class = request.args.get("status_class")
        method_filter = request.args.get("method")
        region_filter = request.args.get("region")
        path_sub = request.args.get("path_sub")

        results = []
        with open(log_path, "r", encoding="utf-8") as handle:
            skipped = 0
            for line in handle:
                record = parse_log_line(line)
                if not record:
                    continue
                region = ip_to_region(record["ip"])
                if status_class and not str(record["status"]).startswith(status_class):
                    continue
                if method_filter and record["method"] != method_filter:
                    continue
                if region_filter and region_filter != region:
                    continue
                if path_sub and path_sub not in record["path"]:
                    continue
                if skipped < offset:
                    skipped += 1
                    continue
                results.append({
                    "ip": record["ip"],
                    "time": record["dt"].isoformat(),
                    "method": record["method"],
                    "path": record["path"],
                    "status": record["status"],
                    "bytes": record["size"],
                    "region": region,
                })
                if len(results) >= limit:
                    break
        return jsonify({"items": results, "count": len(results), "offset": offset, "limit": limit})

    @app.get("/api/stream")
    def stream():
        """Server-Sent Events for real-time updates."""
        def generate() -> Generator[str, None, None]:
            last_mtime = 0
            while True:
                if summary_path.exists():
                    mtime = summary_path.stat().st_mtime
                    if mtime > last_mtime:
                        last_mtime = mtime
                        data = get_summary()
                        yield f"data: {json.dumps({'type': 'summary', 'payload': data})}\\n\\n"
                time.sleep(2)
        return Response(stream_with_context(generate()), mimetype="text/event-stream")

    if plot_path:
        @app.get("/plot")
        def plot():
            if not plot_path.exists():
                abort(404, "Plot not found")
            return send_file(plot_path)

    return app


def parse_args():
    parser = argparse.ArgumentParser(description="Advanced log analytics dashboard")
    parser.add_argument("--summary", default="reports/parallel_summary.json", help="Path to summary JSON")
    parser.add_argument("--plot", default=None, help="Optional path to plot image")
    parser.add_argument("--logs-dir", default=None, help="Directory containing raw server logs")
    parser.add_argument("--host", default="127.0.0.1", help="Host to bind")
    parser.add_argument("--port", type=int, default=8000, help="Port to bind")
    return parser.parse_args()


def main():
    args = parse_args()
    summary_path = Path(args.summary)
    plot_path = Path(args.plot) if args.plot else None
    logs_dir = Path(args.logs_dir) if args.logs_dir else None
    app = create_app(summary_path, plot_path, logs_dir)
    app.run(host=args.host, port=args.port, debug=False, threaded=True)


if __name__ == "__main__":
    main()
