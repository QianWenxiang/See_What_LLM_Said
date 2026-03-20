#!/usr/bin/env python3
"""
see_what_llm_said.py  —  Universal LLM Interaction Visualizer & Proxy
======================================================================
A developer tool that acts as a transparent proxy between your AI Agent
and any OpenAI-compatible LLM API. It captures every request/response
and displays them in a beautiful real-time web dashboard.

Two usage modes:
  1. Standalone Proxy Server  (python see_what_llm_said.py)
  2. Python Library           (import SeeWhatLLMSaid; spy.call_llm(...))

GitHub: https://github.com/your-org/See_What_LLM_Said
"""

import json
import os
import queue
import re
import threading
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

import requests

# ── optional deps ─────────────────────────────────────────────────────────────
try:
    from dotenv import load_dotenv
    load_dotenv()
    _DOTENV_OK = True
except ImportError:
    _DOTENV_OK = False

try:
    from flask import Flask, Response, jsonify, request as flask_request
    _FLASK_OK = True
except ImportError:
    _FLASK_OK = False


# ─────────────────────────────────────────────────────────────────────────────
#  Config from .env / environment
# ─────────────────────────────────────────────────────────────────────────────
def _env(key: str, default: str = "") -> str:
    return os.environ.get(key, default)

DEFAULT_LLM_URL   = _env("LLM_API_URL",  "https://llm.amlogic.com/8d1b5b4c")
DEFAULT_LLM_KEY   = _env("LLM_API_KEY",  "")
DEFAULT_MODEL     = _env("LLM_MODEL",    "")
DEFAULT_SPY_PORT  = int(_env("SPY_PORT", "7654"))
DEFAULT_PROXY_PORT= int(_env("PROXY_PORT","7655"))


# ─────────────────────────────────────────────────────────────────────────────
#  Helpers
# ─────────────────────────────────────────────────────────────────────────────
def _est_tokens(text: str) -> int:
    if not text:
        return 0
    cjk   = len(re.findall(r'[\u4e00-\u9fff\u3400-\u4dbf]', text))
    other = len(text) - cjk
    return int(cjk * 1.5 + other / 4)


def _now_ts() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# ─────────────────────────────────────────────────────────────────────────────
#  HTML Template
# ─────────────────────────────────────────────────────────────────────────────
_HTML = r"""<!DOCTYPE html>
<html lang="zh-CN" data-theme="dark">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>See What LLM Said 🔍</title>
<style>
/* ... existing styles ... */
:root[data-theme="dark"]{
  --bg:#0f1117;--surface:#1a1d2e;--surface2:#242741;--border:#2e3150;
  --accent:#7c6af7;--accent2:#4ecdc4;--success:#43d98e;--error:#ff6b6b;
  --warn:#ffd93d;--text:#e2e8f0;--text-dim:#8892a4;--text-bright:#fff;
  --code-bg:#12151f;--card-shadow:0 4px 20px rgba(0,0,0,.4);
}
:root[data-theme="light"]{
  --bg:#f0f2f8;--surface:#fff;--surface2:#eef0f8;--border:#d0d5e8;
  --accent:#5b4de0;--accent2:#27b0a8;--success:#1eb87a;--error:#e04040;
  --warn:#d4a017;--text:#1a1d2e;--text-dim:#6672a0;--text-bright:#000;
  --code-bg:#f8f9fc;--card-shadow:0 4px 20px rgba(0,0,0,.08);
}
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:'Segoe UI',system-ui,sans-serif;background:var(--bg);color:var(--text);min-height:100vh;transition:background .3s,color .3s}
/* ── Header ── */
header{background:var(--surface);border-bottom:1px solid var(--border);padding:12px 20px;position:sticky;top:0;z-index:100;display:flex;align-items:center;gap:12px;flex-wrap:wrap}
.logo{font-size:18px;font-weight:800;color:var(--text-bright);display:flex;align-items:center;gap:8px;white-space:nowrap}
.pulse{width:9px;height:9px;border-radius:50%;background:var(--success);animation:pulse 2s infinite}
.pulse.off{background:var(--error);animation:none}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.2}}
.stats{display:flex;gap:10px;flex-wrap:wrap}
.stat{background:var(--surface2);border:1px solid var(--border);border-radius:8px;padding:5px 12px;font-size:12px;color:var(--text-dim);white-space:nowrap}
.stat b{color:var(--text-bright);font-weight:700}
.htools{display:flex;gap:8px;margin-left:auto;flex-wrap:wrap;align-items:center}
.btn{background:transparent;border:1px solid var(--border);color:var(--text-dim);border-radius:8px;padding:5px 12px;font-size:12px;cursor:pointer;transition:all .2s;white-space:nowrap}
.btn:hover{border-color:var(--accent);color:var(--accent)}
.btn.danger:hover{border-color:var(--error);color:var(--error)}
.btn.active{background:var(--accent);border-color:var(--accent);color:#fff}
/* ── Search bar ── */
.search-bar{display:flex;gap:8px;padding:10px 20px;background:var(--surface);border-bottom:1px solid var(--border);align-items:center}
.search-bar input{flex:1;background:var(--surface2);border:1px solid var(--border);border-radius:8px;padding:7px 12px;color:var(--text);font-size:13px;outline:none}
.search-bar input:focus{border-color:var(--accent)}
.search-bar select{background:var(--surface2);border:1px solid var(--border);border-radius:8px;padding:7px 10px;color:var(--text);font-size:12px;cursor:pointer}
/* ── Main ── */
main{max-width:1200px;margin:0 auto;padding:20px 16px}
.empty{text-align:center;padding:80px 20px;color:var(--text-dim)}
.empty .icon{font-size:56px;margin-bottom:12px}
/* ── Card ── */
.card{background:var(--surface);border:1px solid var(--border);border-radius:12px;margin-bottom:14px;overflow:hidden;transition:border-color .2s;animation:slideIn .3s ease;box-shadow:var(--card-shadow)}
@keyframes slideIn{from{opacity:0;transform:translateY(-6px)}to{opacity:1;transform:translateY(0)}}
.card:hover{border-color:var(--accent)}
.card.err{border-left:3px solid var(--error)}
.card.ok{border-left:3px solid var(--success)}
.card-hdr{display:flex;align-items:center;gap:10px;padding:12px 16px;cursor:pointer;user-select:none;flex-wrap:wrap}
.card-hdr:hover{background:var(--surface2)}
.badge{border-radius:6px;padding:3px 9px;font-size:11px;font-weight:600;white-space:nowrap}
.badge.model{background:var(--surface2);border:1px solid var(--border);color:var(--accent)}
.badge.step{background:rgba(124,106,247,.15);border:1px solid rgba(124,106,247,.3);color:var(--accent)}
.badge.ok{background:rgba(67,217,142,.12);color:var(--success)}
.badge.err{background:rgba(255,107,107,.12);color:var(--error)}
.badge.proxy{background:rgba(78,205,196,.12);border:1px solid rgba(78,205,196,.3);color:var(--accent2)}
.ex-id{font-size:11px;color:var(--text-dim);font-family:monospace;min-width:28px}
.ex-time{font-size:11px;color:var(--text-dim);font-family:monospace}
.dur{font-size:12px;color:var(--text-dim);margin-left:auto}
.dur.slow{color:var(--warn)}
.arrow{color:var(--text-dim);font-size:13px;margin-left:4px}
/* ── Card body ── */
.card-body{padding:0 16px 16px;display:none}
.card-body.open{display:block}
.sec-label{font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.08em;color:var(--text-dim);margin:12px 0 5px;display:flex;align-items:center;gap:8px}
.sec-label::after{content:'';flex:1;height:1px;background:var(--border)}
.collapsible .sec-content{display:none}
.collapsible .sec-content.open{display:block}
.tog{background:none;border:1px solid var(--border);color:var(--text-dim);border-radius:6px;padding:2px 7px;font-size:11px;cursor:pointer;transition:all .2s}
.tog:hover{border-color:var(--accent);color:var(--accent)}
pre{background:var(--code-bg);border:1px solid var(--border);border-radius:8px;padding:10px 12px;font-family:'Fira Code',Consolas,monospace;font-size:12px;line-height:1.6;overflow:auto;max-height:380px;white-space:pre-wrap;word-break:break-word;color:#c9d1d9}
.resp-box{background:linear-gradient(135deg,#0d1f0e,#0a1929);border:1px solid #2d4a2d;border-radius:8px;padding:12px;font-size:13px;line-height:1.7;white-space:pre-wrap;word-break:break-word;max-height:480px;overflow:auto;color:#b5f5b5}
:root[data-theme="light"] .resp-box{background:linear-gradient(135deg,#f0fff4,#e8f4fd);border:1px solid #87c9b0;color:#1a5c3a}
.err-box{background:rgba(255,107,107,.08);border:1px solid rgba(255,107,107,.3);border-radius:8px;padding:10px 12px;color:var(--error);font-size:12px;font-family:monospace;white-space:pre-wrap}
/* json highlight */
.jk{color:#79b8ff}.js{color:#9ecbff}.jn{color:#f8a169}.jb{color:#ff7b72}.jnu{color:#aaa}
/* ── Messages timeline ── */
.msg-list{display:flex;flex-direction:column;gap:8px}
.msg{border-radius:8px;padding:10px 12px;font-size:12.5px;line-height:1.6;white-space:pre-wrap;word-break:break-word}
.msg.system{background:rgba(255,211,61,.07);border:1px solid rgba(255,211,61,.2);color:var(--warn)}
.msg.user{background:var(--surface2);border:1px solid var(--border);color:var(--text)}
.msg.assistant{background:linear-gradient(135deg,rgba(67,217,142,.06),rgba(78,205,196,.06));border:1px solid rgba(67,217,142,.2);color:var(--success)}
.msg-role{font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.1em;margin-bottom:4px;opacity:.7}
/* ── Stats chart ── */
#chart-wrap{background:var(--surface);border:1px solid var(--border);border-radius:12px;padding:16px;margin-bottom:18px;display:none}
#chart-wrap h3{font-size:13px;color:var(--text-dim);margin-bottom:12px}
#chart-bars{display:flex;align-items:flex-end;gap:6px;height:80px;overflow-x:auto;padding-bottom:4px}
.bar-col{display:flex;flex-direction:column;align-items:center;gap:3px;min-width:36px}
.bar{width:28px;background:var(--accent);border-radius:4px 4px 0 0;transition:height .4s;cursor:pointer;position:relative}
.bar:hover::after{content:attr(title);position:absolute;bottom:100%;left:50%;transform:translateX(-50%);background:var(--surface2);border:1px solid var(--border);border-radius:6px;padding:3px 7px;font-size:11px;white-space:nowrap;z-index:10}
.bar.error-bar{background:var(--error)}
.bar-lbl{font-size:9px;color:var(--text-dim);text-align:center}
/* ── Scrollbar ── */
::-webkit-scrollbar{width:5px;height:5px}
::-webkit-scrollbar-track{background:transparent}
::-webkit-scrollbar-thumb{background:var(--border);border-radius:3px}
::-webkit-scrollbar-thumb:hover{background:var(--accent)}
/* ── Toast ── */
#toast{position:fixed;bottom:20px;right:20px;background:var(--surface2);border:1px solid var(--accent);color:var(--text);border-radius:10px;padding:10px 18px;font-size:13px;transform:translateY(16px);opacity:0;transition:all .3s;pointer-events:none;z-index:999}
#toast.show{transform:translateY(0);opacity:1}
/* ── copy btn ── */
.copy-btn{background:none;border:1px solid var(--border);color:var(--text-dim);border-radius:5px;padding:1px 7px;font-size:10px;cursor:pointer;float:right;margin-left:8px;transition:all .2s}
.copy-btn:hover{border-color:var(--accent);color:var(--accent)}
</style>
</head>
<body>
<header>
  <div class="logo"><div class="pulse" id="dot"></div>🔍 See What LLM Said</div>
  <div class="stats">
    <div class="stat"><span class="t" data-t="statCalls">总调用</span> <b id="s-total">0</b></div>
    <div class="stat"><span class="t" data-t="statSuccess">成功</span> <b id="s-ok">0</b></div>
    <div class="stat"><span class="t" data-t="statError">错误</span> <b id="s-err">0</b></div>
    <div class="stat"><span class="t" data-t="statAvg">平均耗时</span> <b id="s-avg">—</b></div>
    <div class="stat"><span class="t" data-t="statTokens">总 Token(估)</span> <b id="s-tok">0</b></div>
  </div>
  <div class="htools">
    <button class="btn" onclick="manualRefresh()">🔄 <span class="t" data-t="btnRefresh">刷新</span></button>
    <button class="btn" onclick="toggleChart()" id="chart-btn">📊 <span class="t" data-t="btnChart">图表</span></button>
    <button class="btn" onclick="toggleScroll()" id="scroll-btn">📌 <span class="t" data-t="btnScrollOn">自动滚动:开</span></button>
    <button class="btn" onclick="expandAll()"><span class="t" data-t="btnExpandAll">展开全部</span></button>
    <button class="btn" onclick="collapseAll()"><span class="t" data-t="btnCollapseAll">折叠全部</span></button>
    <button class="btn" onclick="exportJSON()">⬇ <span class="t" data-t="btnExport">导出 JSON</span></button>
    <button class="btn" onclick="toggleTheme()" id="theme-btn">🌙 <span class="t" data-t="btnDark">深色</span></button>
    <button class="btn" onclick="toggleLang()" id="lang-btn">🌐 EN</button>
    <button class="btn danger" onclick="clearAll()">🗑 <span class="t" data-t="btnClear">清空</span></button>
  </div>
</header>

<div class="search-bar">
  <input type="text" id="search" placeholder="🔍 搜索模型、内容、状态..." data-t-ph="searchPh" oninput="filterCards()">
  <select id="filter-status" onchange="filterCards()">
    <option value="" class="t" data-t="optAllStatus">全部状态</option>
    <option value="success" class="t" data-t="optSuccess">✅ 成功</option>
    <option value="error" class="t" data-t="optError">❌ 错误</option>
  </select>
  <select id="filter-model" onchange="filterCards()">
    <option value="" class="t" data-t="optAllModels">全部模型</option>
  </select>
</div>

<main>
  <div id="chart-wrap">
    <h3>⏱ <span class="t" data-t="chartTitle">最近调用耗时（ms）</span></h3>
    <div id="chart-bars"></div>
  </div>
  <div id="empty" class="empty">
    <div class="icon">👀</div>
    <div><b class="t" data-t="emptyL1">等待 LLM 交互...</b></div>
    <p style="margin-top:8px;font-size:13px" class="t" data-t="emptyL2">当 Agent 调用 LLM 时，交互内容会实时显示在这里</p>
  </div>
  <div id="list"></div>
</main>
<div id="toast"></div>

<script>
// ── i18n ──────────────────────────────────────────────────────────────────────
const i18n = {
  zh: {
    statCalls:"总调用", statSuccess:"成功", statError:"错误", statAvg:"平均耗时", statTokens:"总 Token(估)",
    btnChart:"图表", btnScrollOn:"自动滚动:开", btnScrollOff:"自动滚动:关", btnExpandAll:"展开全部", btnCollapseAll:"折叠全部",
    btnExport:"导出 JSON", btnRefresh:"刷新", btnDark:"深色", btnLight:"浅色", btnClear:"清空",
    searchPh:"🔍 搜索模型、内容、状态...", optAllStatus:"全部状态", optSuccess:"✅ 成功", optError:"❌ 错误", optAllModels:"全部模型",
    chartTitle:"最近调用耗时（ms）", emptyL1:"等待 LLM 交互...", emptyL2:"当 Agent 调用 LLM 时，交互内容会实时显示在这里",
    msgTitle:"💬 消息", msgTokens:"条 · ~", expand:"展开", collapse:"折叠", errTitle:"❌ 错误", copy:"复制",
    respTitle:"🤖 LLM 回复", chars:"字符", metaTitle:"ℹ️ 元信息", noData:"暂无数据",
    toastScrollOn:"自动滚动已开启", toastScrollOff:"自动滚动已关闭", confirmClear:"确认清空所有交互记录？",
    toastClear:"记录已清空", toastExport:"已导出 JSON", toastCopy:"已复制到剪贴板", toastRefresh:"已刷新数据",
  },
  en: {
    statCalls:"Total", statSuccess:"Success", statError:"Error", statAvg:"Avg Time", statTokens:"Total Tokens(~)",
    btnChart:"Chart", btnScrollOn:"AutoScroll: ON", btnScrollOff:"AutoScroll: OFF", btnExpandAll:"Expand All", btnCollapseAll:"Collapse All",
    btnExport:"Export JSON", btnRefresh:"Refresh", btnDark:"Dark", btnLight:"Light", btnClear:"Clear",
    searchPh:"🔍 Search model, content, status...", optAllStatus:"All Status", optSuccess:"✅ Success", optError:"❌ Error", optAllModels:"All Models",
    chartTitle:"Recent Latency (ms)", emptyL1:"Waiting for LLM...", emptyL2:"When your agent calls an LLM, interactions will appear here instantly.",
    msgTitle:"💬 Messages", msgTokens:"msgs · ~", expand:"Expand", collapse:"Collapse", errTitle:"❌ Error", copy:"Copy",
    respTitle:"🤖 LLM Response", chars:"chars", metaTitle:"ℹ️ Meta", noData:"No data",
    toastScrollOn:"Auto scroll ON", toastScrollOff:"Auto scroll OFF", confirmClear:"Clear all records?",
    toastClear:"Records cleared", toastExport:"Exported JSON", toastCopy:"Copied to clipboard", toastRefresh:"Data refreshed"
  }
};
let lang = 'zh';

function t(key){ return i18n[lang][key] || key; }
function updateI18n(){
  document.querySelectorAll('.t').forEach(el=>{
    const k = el.getAttribute('data-t');
    if(k && i18n[lang][k]) el.textContent = i18n[lang][k];
  });
  document.querySelectorAll('input[data-t-ph]').forEach(el=>{
    const k = el.getAttribute('data-t-ph');
    if(k && i18n[lang][k]) el.placeholder = i18n[lang][k];
  });
  document.getElementById('lang-btn').textContent = lang==='zh'?'🌐 EN':'🌐 中文';
  
  // Re-render UI dynamically
  const sBtn = document.getElementById('scroll-btn');
  if(sBtn.innerHTML.includes('📌')) sBtn.innerHTML = `📌 ${t(autoScroll?'btnScrollOn':'btnScrollOff')}`;
  
  const thBtn = document.getElementById('theme-btn');
  const isDark = document.documentElement.dataset.theme==='dark';
  if(thBtn.innerHTML.includes('🌙') || thBtn.innerHTML.includes('☀️')){
    thBtn.innerHTML = isDark?`🌙 ${t('btnDark')}`:`☀️ ${t('btnLight')}`;
  }
}
function toggleLang(){
  lang = lang === 'zh' ? 'en' : 'zh';
  updateI18n();
  // Force re-render of dynamic elements inside cards
  list.childNodes.forEach(card => {
    // Find expand/collapse buttons inside this card
    card.querySelectorAll('.tog').forEach(btn => {
      const c = btn.closest('.collapsible').querySelector('.sec-content');
      btn.textContent = c.classList.contains('open') ? t('collapse') : t('expand');
    });
    card.querySelectorAll('.copy-btn').forEach(btn => btn.textContent = t('copy'));
    
    // We update headers by finding spans but the dynamic counts (chars, tokens) are mixed with string literals in the code.
    // Full re-render of components would be required to fully localize existing cards' inner text,
    // For simplicity, new cards will be fully localized, existing ones mainly have buttons translated.
  });
}

const list = document.getElementById('list');
const empty = document.getElementById('empty');
let exchanges = [], autoScroll = true, chartVisible = false;
const models = new Set();


// ── SSE ──────────────────────────────────────────────────────────────────────
function connectSSE(){
  const es = new EventSource('/stream');
  const dot = document.getElementById('dot');
  es.onopen = ()=> dot.classList.remove('off');
  es.onerror = ()=> dot.classList.add('off');
  es.addEventListener('exchange', e => {
    const d = JSON.parse(e.data);
    addCard(d); updateStats(); updateChart();
    if(autoScroll) setTimeout(()=>window.scrollTo({top:0,behavior:'smooth'}),60);
  });
  es.addEventListener('clear', ()=>{
    exchanges=[]; list.innerHTML=''; empty.style.display='';
    updateStats(); updateChart(); resetModelFilter();
  });
}

async function loadHistory(){
  try{
    const r = await fetch('/api/exchanges');
    const data = await r.json();
    data.forEach(addCard);
    updateStats(); updateChart();
    if(data.length) empty.style.display='none';
  }catch(e){console.warn('history load failed',e)}
}

// ── Render Card ───────────────────────────────────────────────────────────────
function addCard(ex){
  exchanges.push(ex);
  empty.style.display='none';
  updateModelFilter(ex.model);

  const dur = ex.duration_ms;
  const durStr = dur>=1000?`${(dur/1000).toFixed(2)}s`:`${dur}ms`;
  const durCls = dur>10000?'slow':'';
  const stepBadge = ex.step_num!=null?`<span class="badge step">Step ${ex.step_num}</span>`:'';
  const proxyBadge = ex.via_proxy?`<span class="badge proxy">PROXY</span>`:'';
  const statusBadge = ex.status==='success'
    ?`<span class="badge ok">OK</span>`
    :`<span class="badge err">ERR</span>`;

  const div = document.createElement('div');
  div.className = `card ${ex.status==='success'?'ok':'err'}`;
  div.id = `card-${ex.id}`;
  div.dataset.status = ex.status;
  div.dataset.model = (ex.model||'').toLowerCase();
  div.dataset.content = JSON.stringify(ex).toLowerCase();

  div.innerHTML = `
    <div class="card-hdr" onclick="toggleCard(${ex.id})">
      <span class="ex-id">#${ex.id}</span>
      <span class="ex-time">${ex.timestamp}</span>
      <span class="badge model" title="${esc(ex.model)}">${esc(ex.model||'unknown')}</span>
      ${stepBadge}${proxyBadge}${statusBadge}
      <span class="dur ${durCls}" style="margin-left:auto">⏱ ${durStr}</span>
      <span class="arrow" id="arrow-${ex.id}">▼</span>
    </div>
    <div class="card-body" id="body-${ex.id}">
      ${renderMessages(ex)}
      ${renderResponse(ex)}
      ${renderMeta(ex)}
    </div>`;
  list.prepend(div);
}

function renderMessages(ex){
  // Support both single-turn (system_prompt+user_content) and multi-turn (messages[])
  const msgs = ex.messages || [];
  if(msgs.length === 0){
    if(ex.system_prompt || ex.user_content){
      if(ex.system_prompt) msgs.push({role:'system',content:ex.system_prompt});
      if(ex.user_content)  msgs.push({role:'user',  content:ex.user_content});
    }
  }
  if(!msgs.length) return '';

  const items = [...msgs].reverse().map(m=>{
    const preview = (m.content||'').slice(0,80).replace(/\n/g,' ');
    const chars = (m.content||'').length;
    const tok = estTokens(m.content||'');
    return `<div class="msg ${m.role}">
      <div class="msg-role">${m.role} · ${chars} ${t('chars')} · ~${tok} tokens
        <button class="copy-btn" onclick="copyText(decodeURIComponent(this.getAttribute('data-content')))" data-content="${encodeURIComponent(m.content||'')}">${t('copy')}</button>
      </div>
      ${esc(m.content||'')}
    </div>`;
  }).join('');

  const totalTok = msgs.reduce((a,m)=>a+estTokens(m.content||''),0);
  return `<div class="collapsible">
    <div class="sec-label">${t('msgTitle')} (${msgs.length} ${t('msgTokens')}${totalTok} tokens)
      <button class="tog" onclick="toggleSec(this)">${t('expand')}</button>
    </div>
    <div class="sec-content"><div class="msg-list">${items}</div></div>
  </div>`;
}

function renderResponse(ex){
  if(ex.status==='error'){
    return `<div class="sec-label">${t('errTitle')}</div>
    <div class="err-box">${esc(ex.error||ex.response||'')}</div>`;
  }
  const resp = ex.response||'';
  if(!resp) return '';
  const respTok = estTokens(resp);
  let rendered='';
  try{
    const obj=JSON.parse(resp);
    rendered=`<button class="copy-btn" onclick="copyText(decodeURIComponent(this.getAttribute('data-content')))" data-content="${encodeURIComponent(resp)}">${t('copy')}</button>
      <pre>${highlightJson(JSON.stringify(obj,null,2))}</pre>`;
  }catch{
    rendered=`<button class="copy-btn" onclick="copyText(decodeURIComponent(this.getAttribute('data-content')))" data-content="${encodeURIComponent(resp)}">${t('copy')}</button>
      <div class="resp-box">${esc(resp)}</div>`;
  }
  return `<div class="sec-label">${t('respTitle')} (${resp.length} ${t('chars')} · ~${respTok} tokens)</div>${rendered}`;
}

function renderMeta(ex){
  const fields=[
    ['API URL', ex.api_url||'—'],
    ['Model',   ex.model||'—'],
    ['Duration',ex.duration_ms+'ms'],
  ];
  const rows = fields.map(([k,v])=>`<tr><td style="color:var(--text-dim);padding:2px 10px 2px 0;font-size:12px">${k}</td><td style="font-size:12px">${esc(String(v))}</td></tr>`).join('');
  return `<div class="collapsible">
    <div class="sec-label">${t('metaTitle')} <button class="tog" onclick="toggleSec(this)">${t('expand')}</button></div>
    <div class="sec-content"><table style="border-collapse:collapse">${rows}</table></div>
  </div>`;
}

// ── Helpers ───────────────────────────────────────────────────────────────────
function esc(s){ return String(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;') }
function estTokens(t){ const cjk=(t.match(/[\u4e00-\u9fff]/g)||[]).length; return Math.round(cjk*1.5+(t.length-cjk)/4) }
function highlightJson(s){
  return esc(s)
    .replace(/"((?:[^"\\]|\\.)*)"\s*:/g,'<span class="jk">"$1"</span>:')
    .replace(/:\s*"((?:[^"\\]|\\.)*)"/g,': <span class="js">"$1"</span>')
    .replace(/:\s*(-?\d+\.?\d*)/g,': <span class="jn">$1</span>')
    .replace(/:\s*(true|false)/g,': <span class="jb">$1</span>')
    .replace(/:\s*(null)/g,': <span class="jnu">$1</span>')
}

function toggleCard(id){
  const body=document.getElementById(`body-${id}`);
  const arrow=document.getElementById(`arrow-${id}`);
  body.classList.toggle('open');
  arrow.textContent=body.classList.contains('open')?'▲':'▼';
}
function toggleSec(btn){
  const c=btn.closest('.collapsible').querySelector('.sec-content');
  c.classList.toggle('open');
  btn.textContent=c.classList.contains('open')?t('collapse'):t('expand');
}
function expandAll(){
  document.querySelectorAll('.card-body').forEach(b=>b.classList.add('open'));
  document.querySelectorAll('.arrow').forEach(a=>a.textContent='▲');
}
function collapseAll(){
  document.querySelectorAll('.card-body').forEach(b=>b.classList.remove('open'));
  document.querySelectorAll('.arrow').forEach(a=>a.textContent='▼');
}

// ── Stats ─────────────────────────────────────────────────────────────────────
function updateStats(){
  const ok=exchanges.filter(e=>e.status==='success');
  const err=exchanges.filter(e=>e.status==='error');
  const durs=ok.map(e=>e.duration_ms);
  const avg=durs.length?Math.round(durs.reduce((a,b)=>a+b,0)/durs.length):0;
  const totalTok=exchanges.reduce((a,e)=>a+(e.token_est||0),0);
  document.getElementById('s-total').textContent=exchanges.length;
  document.getElementById('s-ok').textContent=ok.length;
  document.getElementById('s-err').textContent=err.length;
  document.getElementById('s-avg').textContent=avg?(avg>=1000?`${(avg/1000).toFixed(1)}s`:`${avg}ms`):'—';
  document.getElementById('s-tok').textContent=totalTok.toLocaleString();
}

// ── Chart ─────────────────────────────────────────────────────────────────────
function toggleChart(){
  chartVisible=!chartVisible;
  document.getElementById('chart-wrap').style.display=chartVisible?'block':'none';
  document.getElementById('chart-btn').classList.toggle('active',chartVisible);
  if(chartVisible) updateChart();
}
function updateChart(){
  if(!chartVisible) return;
  const bars=document.getElementById('chart-bars');
  const recent=exchanges.slice(-30);
  if(!recent.length){bars.innerHTML=`<span style="color:var(--text-dim);font-size:12px">${t('noData')}</span>`;return}
  const maxDur=Math.max(...recent.map(e=>e.duration_ms),1);
  bars.innerHTML=recent.map(e=>{
    const h=Math.max(4,Math.round((e.duration_ms/maxDur)*72));
    const isErr=e.status==='error';
    const dur=e.duration_ms>=1000?`${(e.duration_ms/1000).toFixed(1)}s`:`${e.duration_ms}ms`;
    return `<div class="bar-col">
      <div class="bar ${isErr?'error-bar':''}" style="height:${h}px" title="#${e.id} ${dur}"></div>
      <div class="bar-lbl">#${e.id}</div>
    </div>`;
  }).join('');
}

// ── Filter ────────────────────────────────────────────────────────────────────
function updateModelFilter(model){
  if(!model||models.has(model)) return;
  models.add(model);
  const sel=document.getElementById('filter-model');
  const opt=document.createElement('option');
  opt.value=model.toLowerCase(); opt.textContent=model;
  sel.appendChild(opt);
}
function resetModelFilter(){
  models.clear();
  document.getElementById('filter-model').innerHTML=`<option value="" class="t" data-t="optAllModels">${t('optAllModels')}</option>`;
}
function filterCards(){
  const q=(document.getElementById('search').value||'').toLowerCase();
  const st=document.getElementById('filter-status').value;
  const mo=document.getElementById('filter-model').value;
  document.querySelectorAll('.card').forEach(c=>{
    const matchQ=!q||c.dataset.content.includes(q);
    const matchS=!st||c.dataset.status===st;
    const matchM=!mo||c.dataset.model.includes(mo);
    c.style.display=(matchQ&&matchS&&matchM)?'':'none';
  });
}

// ── Actions ───────────────────────────────────────────────────────────────────
function toggleScroll(){
  autoScroll=!autoScroll;
  document.getElementById('scroll-btn').innerHTML=`📌 ${t(autoScroll?'btnScrollOn':'btnScrollOff')}`;
  toast(autoScroll?t('toastScrollOn'):t('toastScrollOff'));
}
async function clearAll(){
  if(!confirm(t('confirmClear'))) return;
  await fetch('/api/clear',{method:'POST'});
  await manualRefresh();
}
function exportJSON(){
  const blob=new Blob([JSON.stringify(exchanges,null,2)],{type:'application/json'});
  const a=document.createElement('a');
  a.href=URL.createObjectURL(blob);
  a.download=`llm_exchanges_${Date.now()}.json`;
  a.click();
  toast(t('toastExport'));
}
async function manualRefresh(){
  exchanges=[]; list.innerHTML=''; empty.style.display='';
  resetModelFilter();
  await loadHistory();
  updateI18n();
  toast(t('toastRefresh'));
}
function toggleTheme(){
  const html=document.documentElement;
  const isDark=html.dataset.theme==='dark';
  html.dataset.theme=isDark?'light':'dark';
  document.getElementById('theme-btn').innerHTML=isDark?`🌙 ${t('btnDark')}`:`☀️ ${t('btnLight')}`;
}
function copyText(text){
  navigator.clipboard.writeText(text).then(()=>toast(t('toastCopy')));
}
function toast(msg){
  const tDiv=document.getElementById('toast');
  tDiv.textContent=msg; tDiv.classList.add('show');
  setTimeout(()=>tDiv.classList.remove('show'),2500);
}

// ── Init ──────────────────────────────────────────────────────────────────────
updateI18n();
loadHistory().then(connectSSE);
</script>
</body>
</html>"""


# ─────────────────────────────────────────────────────────────────────────────
#  SeeWhatLLMSaid  — Core Class
# ─────────────────────────────────────────────────────────────────────────────

class SeeWhatLLMSaid:
    """
    Universal LLM Interaction Visualizer & Proxy.

    Usage as a library::

        spy = SeeWhatLLMSaid(port=7654)
        spy.start()
        result = spy.call_llm(messages, model="gpt-4o", api_url=..., api_key=...)

    Usage as a transparent proxy server::

        python see_what_llm_said.py --proxy
        # Then point your agent's API_URL to http://localhost:7655
    """

    def __init__(
        self,
        host: str = "0.0.0.0",
        port: int = DEFAULT_SPY_PORT,
        auto_open: bool = True,
    ):
        if not _FLASK_OK:
            raise RuntimeError("Please install flask: pip install flask requests python-dotenv")
        self.host = host
        self.port = port
        self.auto_open = auto_open
        self._exchanges: List[Dict] = []
        self._exchange_id = 0
        self._lock = threading.Lock()
        self._sse_queues: List[queue.Queue] = []
        self._app = self._build_app()
        self._server_thread: Optional[threading.Thread] = None

    # ── Public API ────────────────────────────────────────────────────────────

    def start(self) -> str:
        """Start background web server. Returns URL."""
        if self._server_thread and self._server_thread.is_alive():
            return self.get_url()
        t = threading.Thread(target=self._run_flask, daemon=True, name="spy-flask")
        t.start()
        self._server_thread = t
        time.sleep(0.6)
        url = self.get_url()
        print(f"\n{'='*60}")
        print(f"  🔍  See What LLM Said  — dashboard ready")
        print(f"  ➜   {url}")
        print(f"{'='*60}\n")
        if self.auto_open:
            try:
                import webbrowser; webbrowser.open(url)
            except Exception:
                pass
        return url

    def get_url(self) -> str:
        h = "localhost" if self.host == "0.0.0.0" else self.host
        return f"http://{h}:{self.port}"

    def call_llm(
        self,
        messages: Optional[List[Dict]] = None,
        model: str = DEFAULT_MODEL,
        api_url: str = DEFAULT_LLM_URL,
        api_key: str = DEFAULT_LLM_KEY,
        step_num: Optional[int] = None,
        temperature: float = 0.1,
        max_retries: int = 3,
        logger=None,
        # Legacy single-turn compat
        system_prompt: str = "",
        user_content: str = "",
        **kwargs,
    ) -> str:
        """
        Call LLM, record interaction, return response text.

        Supports both multi-turn messages list and legacy single-turn args.
        """
        # Build messages list
        if messages is None:
            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            if user_content:
                messages.append({"role": "user", "content": user_content})

        # Normalize URL
        url_full = api_url.rstrip("/")
        if not url_full.endswith("/chat/completions"):
            url_full += "/chat/completions"

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        }
        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
        }

        t0 = time.time()
        status, response, error = "error", "", ""
        raw_response: Dict = {}

        for attempt in range(max_retries):
            try:
                resp = requests.post(url_full, headers=headers, json=payload, timeout=120)
                resp.raise_for_status()
                raw_response = resp.json()
                response = raw_response["choices"][0]["message"]["content"]
                status = "success"
                break
            except Exception as e:
                error = str(e)
                if logger:
                    logger.log(f"[SeeWhatLLMSaid] retry {attempt+1}: {e}")
                if attempt < max_retries - 1:
                    time.sleep(2 ** attempt)

        duration_ms = int((time.time() - t0) * 1000)
        token_est = sum(_est_tokens(m.get("content", "")) for m in messages)
        usage = raw_response.get("usage", {})

        record = {
            "id": self._next_id(),
            "timestamp": _now_ts(),
            "model": model,
            "api_url": url_full,
            "messages": messages,
            # Legacy compat fields
            "system_prompt": next((m["content"] for m in messages if m["role"] == "system"), ""),
            "user_content": next((m["content"] for m in messages if m["role"] == "user"), ""),
            "response": response,
            "duration_ms": duration_ms,
            "token_est": token_est,
            "prompt_tokens": usage.get("prompt_tokens", token_est),
            "completion_tokens": usage.get("completion_tokens", _est_tokens(response)),
            "status": status,
            "error": error,
            "step_num": step_num,
            "has_image": False,
            "via_proxy": False,
        }
        self._push(record)

        if status == "error":
            raise RuntimeError(f"LLM call failed after {max_retries} retries: {error}")
        return response

    def record_raw(self, record: Dict[str, Any]):
        """Manually push a pre-built record into the dashboard."""
        defaults = {
            "id": self._next_id(),
            "timestamp": _now_ts(),
            "api_url": "", "messages": [], "system_prompt": "",
            "user_content": "", "response": "", "duration_ms": 0,
            "token_est": 0, "prompt_tokens": 0, "completion_tokens": 0,
            "error": "", "step_num": None, "has_image": False, "via_proxy": False,
        }
        defaults.update(record)
        self._push(defaults)

    # ── Internal ──────────────────────────────────────────────────────────────

    def _next_id(self) -> int:
        with self._lock:
            self._exchange_id += 1
            return self._exchange_id

    def _push(self, record: Dict):
        with self._lock:
            self._exchanges.append(record)
        msg = f"event: exchange\ndata: {json.dumps(record, ensure_ascii=False)}\n\n"
        dead = []
        for q in self._sse_queues:
            try:
                q.put_nowait(msg)
            except queue.Full:
                dead.append(q)
            try:
                spy._sse_queues.remove(q)
            except ValueError:
                pass

    def _build_app(self) -> "Flask":
        app = Flask(__name__)
        import logging
        logging.getLogger("werkzeug").setLevel(logging.ERROR)
        spy = self

        @app.route("/")
        def index():
            return _HTML

        @app.route("/api/exchanges")
        def api_exchanges():
            with spy._lock:
                return jsonify(list(spy._exchanges))

        @app.route("/api/clear", methods=["POST"])
        def api_clear():
            with spy._lock:
                spy._exchanges.clear()
                spy._exchange_id = 0
            clr = "event: clear\ndata: {}\n\n"
            for q in spy._sse_queues:
                try: 
                    q.put_nowait(clr)
                except queue.Full: 
                    pass
            return jsonify({"ok": True})

        @app.route("/api/stats")
        def api_stats():
            with spy._lock:
                exs = list(spy._exchanges)
            ok = [e for e in exs if e["status"] == "success"]
            err= [e for e in exs if e["status"] == "error"]
            durs= [e["duration_ms"] for e in ok]
            return jsonify({
                "total": len(exs),
                "success": len(ok),
                "error": len(err),
                "avg_ms": int(sum(durs)/len(durs)) if durs else 0,
                "total_tokens": sum(e.get("token_est",0) for e in exs),
            })

        @app.route("/v1/models", methods=["GET"])
        @app.route("/models", methods=["GET"])
        @app.route("/<path:sub_path>", methods=["GET"])
        def mock_get(sub_path=""):
            """Mock GET requests for models so plugins don't crash."""
            if "models" in sub_path or sub_path in ["", "v1/models", "models"]:
                return jsonify({
                    "object": "list",
                    "data": [{"id": DEFAULT_MODEL or "gpt-4o", "object": "model", "owned_by": "system"}]
                })
            return jsonify({"error": "not found"}), 404

        @app.route("/v1/chat/completions", methods=["POST"])
        @app.route("/chat/completions", methods=["POST"])
        @app.route("/<path:sub_path>", methods=["POST"])
        def proxy_api(sub_path=""):
            """Handle API calls on the same port as the dashboard."""
            # Give precedence to actual frontend api routes just in case
            if sub_path == "api/clear":
                return api_clear()

            body = flask_request.get_json(silent=True) or {}
            
            stream_requested = False
            if isinstance(body, dict) and body.get("stream"):
                stream_requested = True
                
            messages = body.get("messages", [])
            model = body.get("model", DEFAULT_MODEL)
            
            # Forward manually using our internal logic (records it automatically)
            try:
                # Always use the real key if it's set properly in .env, ignore fake plugin keys
                key = DEFAULT_LLM_KEY
                
                # Normalize target URL
                url = DEFAULT_LLM_URL.rstrip("/")
                if not url.endswith("/chat/completions"):
                    url += "/chat/completions"

                t0 = time.time()
                headers = {"Content-Type": "application/json", "Authorization": f"Bearer {key}"}
                r = requests.post(url, headers=headers, json=body, timeout=120, stream=stream_requested)
                
                if not r.ok:
                    status = "error"
                    response_text = f"HTTP {r.status_code}: {r.text}"
                    duration_ms = int((time.time() - t0) * 1000)
                    rec = {
                        "id": spy._next_id(),
                        "timestamp": _now_ts(),
                        "model": model,
                        "api_url": url,
                        "messages": messages,
                        "response": response_text,
                        "duration_ms": duration_ms,
                        "token_est": sum(_est_tokens(m.get("content","")) for m in messages),
                        "status": status,
                        "error": response_text,
                        "via_proxy": True,
                    }
                    spy._push(rec)
                    return jsonify({"error": {"message": response_text}}), r.status_code

                if not stream_requested:
                    resp_json = r.json()() if callable(r.json) else r.json()
                    choices = resp_json.get("choices", [])
                    response_text = choices[0].get("message", {}).get("content", "") if choices else ""
                    duration_ms = int((time.time() - t0) * 1000)
                    rec = {
                        "id": spy._next_id(),
                        "timestamp": _now_ts(),
                        "model": model,
                        "api_url": url,
                        "messages": messages,
                        "response": response_text,
                        "duration_ms": duration_ms,
                        "token_est": sum(_est_tokens(m.get("content","")) for m in messages),
                        "status": "success",
                        "error": "",
                        "via_proxy": True,
                    }
                    spy._push(rec)
                    return jsonify(resp_json), 200

                # Streaming behavior
                def stream_generator():
                    full_content = ""
                    try:
                        for line in r.iter_lines():
                            if line:
                                yield line + b"\n\n"
                                line_str = line.decode('utf-8')
                                if line_str.startswith("data: ") and line_str != "data: [DONE]":
                                    try:
                                        chunk = json.loads(line_str[6:])
                                        delta = chunk.get("choices", [{}])[0].get("delta", {})
                                        if "content" in delta:
                                            full_content += delta["content"]
                                    except Exception:
                                        pass
                    finally:
                        duration_ms = int((time.time() - t0) * 1000)
                        rec = {
                            "id": spy._next_id(),
                            "timestamp": _now_ts(),
                            "model": model,
                            "api_url": url,
                            "messages": messages,
                            "response": full_content,
                            "duration_ms": duration_ms,
                            "token_est": sum(_est_tokens(m.get("content","")) for m in messages),
                            "status": "success",
                            "error": "",
                            "via_proxy": True,
                        }
                        spy._push(rec)

                from flask import Response, stream_with_context
                return Response(stream_with_context(stream_generator()), mimetype='text/event-stream')
            except Exception as e:
                return jsonify({"error": {"message": str(e)}}), 500

        @app.route("/stream")
        def stream():
            q = queue.Queue(maxsize=200)
            spy._sse_queues.append(q)
            def gen():
                yield ": heartbeat\n\n"
                try:
                    while True:
                        try:
                            yield q.get(timeout=20)
                        except queue.Empty:
                            yield ": heartbeat\n\n"
                except GeneratorExit:
                    pass
                finally:
                    try: 
                        spy._sse_queues.remove(q)
                    except ValueError: 
                        pass
            return Response(gen(), mimetype="text/event-stream",
                headers={"Cache-Control":"no-cache","X-Accel-Buffering":"no","Connection":"keep-alive"})

        return app

    def _run_flask(self):
        self._app.run(host=self.host, port=self.port, threaded=True, use_reloader=False)


# ─────────────────────────────────────────────────────────────────────────────
#  Proxy Server  —  transparent OpenAI-compatible reverse proxy
# ─────────────────────────────────────────────────────────────────────────────

class ProxyServer:
    """
    Standalone transparent proxy.

    Your agent sends requests to http://localhost:PROXY_PORT
    The proxy forwards them to the real LLM_API_URL and records everything.
    Dashboard available at http://localhost:SPY_PORT
    """

    def __init__(
        self,
        spy: SeeWhatLLMSaid,
        target_url: str = DEFAULT_LLM_URL,
        target_key: str = DEFAULT_LLM_KEY,
        proxy_port: int = DEFAULT_PROXY_PORT,
    ):
        self.spy = spy
        self.target_url = target_url.rstrip("/")
        self.target_key = target_key
        self.proxy_port = proxy_port
        self._app = self._build_proxy_app()

    def start(self):
        t = threading.Thread(target=self._run, daemon=True, name="spy-proxy")
        t.start()
        time.sleep(0.5)
        print(f"  🔀  Proxy listening  ➜  http://localhost:{self.proxy_port}")
        print(f"      Forwarding to   ➜  {self.target_url}")
        print(f"      Set your agent's LLM_API_URL=http://localhost:{self.proxy_port}\n")

    def _build_proxy_app(self) -> "Flask":
        app = Flask("proxy")
        import logging
        logging.getLogger("werkzeug").setLevel(logging.ERROR)
        spy = self.spy
        target_url = self.target_url
        target_key = self.target_key

        @app.route("/v1/chat/completions", methods=["POST"])
        @app.route("/chat/completions", methods=["POST"])
        @app.route("/<path:sub_path>", methods=["POST", "GET"])
        def proxy(sub_path=""):
            body = flask_request.get_json(silent=True) or {}
            messages = body.get("messages", [])
            model = body.get("model", DEFAULT_MODEL)
            auth = flask_request.headers.get("Authorization", f"Bearer {target_key}")
            key = auth.replace("Bearer ", "").strip() or target_key

            # Forward to real LLM
            real_url = f"{target_url}/{sub_path}".rstrip("/")
            if not real_url.endswith("completions"):
                real_url = f"{target_url}/chat/completions"

            fwd_headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {key}",
            }
            t0 = time.time()
            status, response_text, error = "error", "", ""
            raw_resp: Dict = {}
            status_code = 200

            try:
                r = requests.post(real_url, headers=fwd_headers, json=body, timeout=120)
                status_code = r.status_code
                raw_resp = r.json()
                if r.ok:
                    choices = raw_resp.get("choices", [])
                    if choices:
                        response_text = choices[0].get("message", {}).get("content", "")
                    status = "success"
                else:
                    error = f"HTTP {r.status_code}: {r.text}"
            except Exception as e:
                error = str(e)
                status_code = 502

            duration_ms = int((time.time() - t0) * 1000)
            token_est = sum(_est_tokens(m.get("content", "")) for m in messages)
            usage = raw_resp.get("usage", {})

            record = {
                "id": spy._next_id(),
                "timestamp": _now_ts(),
                "model": model,
                "api_url": real_url,
                "messages": messages,
                "system_prompt": next((m["content"] for m in messages if m["role"] == "system"), ""),
                "user_content": next((m["content"] for m in messages if m["role"] == "user"), ""),
                "response": response_text,
                "duration_ms": duration_ms,
                "token_est": token_est,
                "prompt_tokens": usage.get("prompt_tokens", token_est),
                "completion_tokens": usage.get("completion_tokens", _est_tokens(response_text)),
                "status": status,
                "error": error,
                "step_num": None,
                "has_image": False,
                "via_proxy": True,
            }
            spy._push(record)

            if status == "success":
                return jsonify(raw_resp), status_code
            else:
                return jsonify({"error": error}), status_code

        return app

    def _run(self):
        self._app.run(host="0.0.0.0", port=self.proxy_port, threaded=True, use_reloader=False)


# ─────────────────────────────────────────────────────────────────────────────
#  CLI entry point
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="See What LLM Said — Universal LLM Interaction Visualizer",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Start dashboard only (use as Python library)
  python see_what_llm_said.py

  # Start transparent proxy (intercept any OpenAI-compatible agent)
  python see_what_llm_said.py --proxy

  # Custom ports
  python see_what_llm_said.py --proxy --spy-port 8080 --proxy-port 8081
        """,
    )
    parser.add_argument("--proxy",      action="store_true", help="Also start transparent proxy server")
    parser.add_argument("--spy-port",   type=int, default=DEFAULT_SPY_PORT,   help=f"Dashboard port (default: {DEFAULT_SPY_PORT})")
    parser.add_argument("--proxy-port", type=int, default=DEFAULT_PROXY_PORT, help=f"Proxy port (default: {DEFAULT_PROXY_PORT})")
    parser.add_argument("--target-url", type=str, default=DEFAULT_LLM_URL,    help="Real LLM API base URL")
    parser.add_argument("--target-key", type=str, default=DEFAULT_LLM_KEY,    help="Real LLM API key")
    parser.add_argument("--no-open",    action="store_true", help="Don't auto-open browser")
    args = parser.parse_args()

    def _free_port(p: int):
        import subprocess
        try:
            out = subprocess.check_output(f"lsof -ti:{p}", shell=True, stderr=subprocess.DEVNULL).decode().strip()
            if out:
                for pid in out.split():
                    print(f"  [Warn] Port {p} occupied by PID {pid}. Killing it to free the port...")
                    subprocess.run(f"kill -9 {pid}", shell=True, stderr=subprocess.DEVNULL)
                time.sleep(0.5)
        except Exception:
            pass

    _free_port(args.spy_port)
    spy = SeeWhatLLMSaid(port=args.spy_port, auto_open=not args.no_open)
    spy.start()

    if args.proxy:
        _free_port(args.proxy_port)
        proxy = ProxyServer(
            spy=spy,
            target_url=args.target_url,
            target_key=args.target_key,
            proxy_port=args.proxy_port,
        )
        proxy.start()

    print("Press Ctrl+C to exit\n")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nBye!")
