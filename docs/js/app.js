import {
  FR_CALCS,
  escapeHtml,
  isFallRiskQuestion,
  frCheck,
  processQuestion,
  renderMermaid,
  renderRecordHtml,
} from './engine.js';

const STORAGE_PREFIX = 'nextstep_v2_';
const $ = (sel) => document.querySelector(sel);

let cohort = {};
let currentPid = 1;
let frFlow = null;
let mermaidReady = false;

function assetUrl(path) {
  const base = import.meta.url.replace(/\/js\/app\.js.*$/, '/');
  return new URL(`../${path}`, base).href;
}

async function loadCohort() {
  const res = await fetch(assetUrl('data/sample_patients.json'));
  if (!res.ok) throw new Error('Could not load patient data');
  cohort = await res.json();
  const ids = Object.keys(cohort).map(Number).sort((a, b) => a - b);
  const max = ids[ids.length - 1];
  $('#patient-id').max = max;
  $('#cohort-size').textContent = `${ids.length}-patient demo cohort`;
  $('#patient-meta').textContent = `IDs 1–${max} · synthetic demo data`;
  const dl = $('#patient-ids');
  dl.innerHTML = ids.map((id) => `<option value="${id}">`).join('');
  return ids;
}

function chatKey(pid) {
  return `${STORAGE_PREFIX}chat_${pid}`;
}

function loadChat(pid) {
  try {
    return JSON.parse(localStorage.getItem(chatKey(pid)) || '[]');
  } catch {
    return [];
  }
}

function saveChat(pid, messages) {
  localStorage.setItem(chatKey(pid), JSON.stringify(messages));
  if (messages.length) {
    const saved = new Set(listSavedPids());
    saved.add(pid);
    localStorage.setItem(`${STORAGE_PREFIX}saved`, JSON.stringify([...saved].sort((a, b) => a - b)));
  }
}

function listSavedPids() {
  try {
    return JSON.parse(localStorage.getItem(`${STORAGE_PREFIX}saved`) || '[]');
  } catch {
    return [];
  }
}

function deleteChat(pid) {
  localStorage.removeItem(chatKey(pid));
  const saved = listSavedPids().filter((id) => id !== pid);
  localStorage.setItem(`${STORAGE_PREFIX}saved`, JSON.stringify(saved));
}

function formatAnswer(text) {
  let html = escapeHtml(text);
  html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
  html = html.replace(/\n\* /g, '<br>• ');
  html = html.replace(/\n- /g, '<br>• ');
  html = html.replace(/\n/g, '<br>');
  return html;
}

function renderMessage(m) {
  if (m.role === 'user') {
    return `<div class="umsg">${escapeHtml(m.content)}</div>`;
  }
  const verdict = `<span class="verdict" style="background:${m.bg};color:${m.fg}">${escapeHtml(m.decision)}</span>`;
  const why = `<div class="gline">${escapeHtml(m.why || '')}</div>`;
  const body = `<div class="ans">${formatAnswer(m.content)}</div>`;
  return `<div class="assistant-msg">${verdict}${why}${body}</div>`;
}

function renderChat(messages) {
  const el = $('#chat-messages');
  el.innerHTML = messages.map(renderMessage).join('');
  el.scrollTop = el.scrollHeight;
}

function loadSaved() {
  const saved = listSavedPids();
  const list = $('#saved-list');
  if (!saved.length) {
    list.innerHTML = '<p class="hint" style="margin:0">No saved chats yet.</p>';
    return;
  }
  list.innerHTML = saved
    .map(
      (id) => `
    <div class="saved-item">
      <button type="button" data-pid="${id}">Patient ${id}</button>
      <button type="button" class="del" data-del="${id}" aria-label="Delete">✕</button>
    </div>`
    )
    .join('');
  list.querySelectorAll('[data-pid]').forEach((btn) => {
    btn.addEventListener('click', () => {
      $('#patient-id').value = btn.dataset.pid;
      loadPatient();
    });
  });
  list.querySelectorAll('[data-del]').forEach((btn) => {
    btn.addEventListener('click', () => {
      const pid = Number(btn.dataset.del);
      deleteChat(pid);
      if (currentPid === pid) renderChat([]);
      loadSaved();
    });
  });
}

async function ensureMermaid() {
  if (mermaidReady) return;
  if (!window.mermaid) {
    await new Promise((resolve, reject) => {
      const s = document.createElement('script');
      s.src = 'https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.min.js';
      s.onload = resolve;
      s.onerror = reject;
      document.head.appendChild(s);
    });
  }
  mermaid.initialize({ startOnLoad: false, theme: 'neutral', securityLevel: 'loose' });
  mermaidReady = true;
}

async function renderGraph(p, pid) {
  const el = $('#graph-mermaid');
  el.textContent = renderMermaid(p, pid);
  await ensureMermaid();
  try {
    const { svg } = await mermaid.render(`graph-${pid}-${Date.now()}`, el.textContent);
    el.outerHTML = `<div class="mermaid-rendered">${svg}</div>`;
  } catch {
    el.textContent = 'Graph preview unavailable.';
  }
}

function loadPatient() {
  const pid = parseInt($('#patient-id').value, 10);
  currentPid = pid;
  $('#patient-error').classList.add('hidden');
  const p = cohort[String(pid)];
  if (!p) {
    $('#patient-error').textContent = `Patient ${pid} not found (1–${Object.keys(cohort).length}).`;
    $('#patient-error').classList.remove('hidden');
    $('#ev-index').textContent = '—';
    $('#ev-fr').textContent = '—';
    $('#ev-vt').textContent = '—';
    $('#record-panel').innerHTML = '';
    renderChat([]);
    return;
  }

  $('#ev-index').textContent = p.index_date;
  $('#ev-fr').textContent = p.fr_present ? 'yes' : 'no';
  $('#ev-vt').textContent = p.vt_present ? 'yes' : 'no';
  $('#record-panel').innerHTML = renderRecordHtml(p);

  const graphPanel = $('#graph-panel');
  const graphBody = graphPanel.querySelector('.graph-wrap');
  graphBody.innerHTML = '<pre class="mermaid" id="graph-mermaid"></pre>';
  graphPanel.ontoggle = async () => {
    if (graphPanel.open) await renderGraph(p, pid);
  };

  renderChat(loadChat(pid));
  loadSaved();
}

function setLoading(on) {
  $('#loading').classList.toggle('hidden', !on);
  $('#ask-form button').disabled = on;
}

function showFollowups(list) {
  const wrap = $('#followups-wrap');
  const row = $('#followups');
  if (!list?.length) {
    wrap.classList.add('hidden');
    return;
  }
  wrap.classList.remove('hidden');
  row.innerHTML = list
    .map((q) => `<button type="button" class="btn followup-btn">${escapeHtml(q)}</button>`)
    .join('');
  row.querySelectorAll('.followup-btn').forEach((btn) => {
    btn.addEventListener('click', () => submitQuestion(btn.textContent));
  });
}

const frModal = $('#fr-modal');
const frModalContent = $('#fr-modal-content');

function openFrModal(step, data = {}) {
  frModal.classList.remove('hidden');
  if (step === 'pick_type') {
    frModalContent.innerHTML = `
      <h3>Fall risk is broad. Which kind of validated assessment?</h3>
      <div class="btn-row">
        <button type="button" class="btn" data-type="survey">Patient-facing survey</button>
        <button type="button" class="btn accent" data-type="performance">Provider performance test</button>
      </div>`;
    frModalContent.querySelectorAll('[data-type]').forEach((btn) => {
      btn.addEventListener('click', () => {
        frFlow = { type: btn.dataset.type };
        openFrModal('pick_calc');
      });
    });
    return;
  }
  if (step === 'pick_calc') {
    const opts = Object.entries(FR_CALCS).filter(([, v]) => v.type === frFlow.type);
    frModalContent.innerHTML = `
      <h3>Which validated instrument?</h3>
      <div class="btn-row">
        ${opts.map(([name]) => `<button type="button" class="btn" data-calc="${escapeHtml(name)}">${escapeHtml(name)}</button>`).join('')}
      </div>`;
    frModalContent.querySelectorAll('[data-calc]').forEach((btn) => {
      btn.addEventListener('click', () => runFrCheck(btn.dataset.calc));
    });
    return;
  }
  if (step === 'gather') {
    frModalContent.innerHTML = `
      <h3><span class="verdict" style="background:#ffedd5;color:#c2410c">GATHER</span></h3>
      <div class="ans">${data.html}</div>
      <div class="btn-row" style="margin-top:1rem">
        <button type="button" class="btn">${escapeHtml(data.routeLabel)}</button>
        <button type="button" class="btn ghost" id="fr-reset">Start over</button>
      </div>`;
    frModalContent.querySelector('#fr-reset')?.addEventListener('click', () => {
      frFlow = null;
      frModal.classList.add('hidden');
    });
    frModalContent.querySelector('.btn:not(.ghost)')?.addEventListener('click', () => {
      alert(`Request queued: ${data.source}`);
    });
  }
}

function runFrCheck(calc) {
  const p = cohort[String(currentPid)];
  frModal.classList.add('hidden');
  const { missing, spec } = frCheck(calc, p);
  if (!missing.length) {
    submitQuestion(
      `Using the ${calc}, assess this patient's fall risk based only on the record.`,
      calc
    );
    return;
  }
  frModal.classList.remove('hidden');
  const routeLabel = spec.type === 'survey' ? 'Send survey to patient' : 'Request test from PT';
  openFrModal('gather', {
    html: `I do not have all the data to complete the <strong>${escapeHtml(calc)}</strong>. Missing: <strong>${escapeHtml(missing.join(', '))}</strong>. Collect via ${escapeHtml(spec.source)}.`,
    routeLabel,
    source: spec.source,
  });
  frFlow = null;
}

function submitQuestion(q, frCalc = null) {
  if (!q?.trim()) return;
  const p = cohort[String(currentPid)];
  if (!p) return;

  if (!frCalc && isFallRiskQuestion(q)) {
    frFlow = {};
    openFrModal('pick_type');
    return;
  }

  setLoading(true);
  $('#followups-wrap').classList.add('hidden');

  const history = loadChat(currentPid);
  history.push({ role: 'user', content: q });
  renderChat(history);

  requestAnimationFrame(() => {
    const res = processQuestion(q, p, frCalc);
    history.push({
      role: 'assistant',
      content: res.content,
      decision: res.decision,
      why: res.why,
      bg: res.bg,
      fg: res.fg,
    });
    saveChat(currentPid, history);
    renderChat(history);
    showFollowups(res.followups);
    setLoading(false);
    $('#question').value = '';
    loadSaved();
  });
}

$('#ask-form').addEventListener('submit', (e) => {
  e.preventDefault();
  submitQuestion($('#question').value);
});

$('#patient-id').addEventListener('change', loadPatient);

$('#quick-actions').addEventListener('click', (e) => {
  const btn = e.target.closest('button');
  if (!btn) return;
  if (btn.dataset.fr) {
    frFlow = {};
    openFrModal('pick_type');
    return;
  }
  if (btn.dataset.q) submitQuestion(btn.dataset.q);
});

frModal.addEventListener('click', (e) => {
  if (e.target === frModal) {
    frModal.classList.add('hidden');
    frFlow = null;
  }
});

loadCohort()
  .then(() => loadPatient())
  .catch((err) => {
    $('#patient-error').textContent = err.message;
    $('#patient-error').classList.remove('hidden');
  });
