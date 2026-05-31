/** Client-side achievability gate (free, no server). */
export const FR_CALCS = {
  'Morse Fall Scale': {
    type: 'survey',
    needs: ['fall history', 'secondary diagnosis', 'ambulatory aid', 'gait', 'mental status'],
    source: 'a patient-facing Morse survey plus chart review',
  },
  'Hendrich II': {
    type: 'survey',
    needs: ['confusion', 'depression', 'altered elimination', 'dizziness', 'gait'],
    source: 'a patient-facing Hendrich II survey plus chart review',
  },
  'Timed Up and Go (TUG)': {
    type: 'performance',
    needs: ['timed mobility test'],
    source: 'a performance test administered by PT or the care provider',
  },
};

export const PALETTE = {
  PROCEED: ['#dcfce7', '#166534'],
  GATHER: ['#ffedd5', '#c2410c'],
  ABSTAIN: ['#fef9c3', '#a16207'],
};

const OOD = ['insurance', 'billing', 'weather', 'stock', 'recipe', 'legal advice', 'crypto', 'sports'];
const SEEDS = ['hip fracture', 'fall risk', 'gait', 'decondition', 'mobility', 'vitals', 'medication'];

function medCompact(entry) {
  const m = String(entry).match(/^\s*(.+?)\s*\((\d+) fills:\s*(.+)\)\s*$/);
  if (m) return `${m[1]}: ${m[2]} fills`;
  const m2 = String(entry).match(/^\s*(.+?)\s*\(started\s*(.+?)\)\s*$/);
  if (m2) return `${m2[1]}: started ${m2[2]}`;
  return String(entry);
}

export function sections(p) {
  return [
    ['Demographics', [`Fall index date: ${p.index_date}`, `Age at fall: ${p.age ?? 'n/a'}`]],
    ['Diagnoses', p.dx?.length ? p.dx : ['none on file']],
    ['Medications', p.meds?.length ? p.meds.map(medCompact) : ['none on file']],
    ['Recent labs', p.labs?.length ? p.labs : ['none on file']],
    ['Recent vitals', p.vitals?.length ? p.vitals : ['none on file']],
    ['Fall-risk assessment', p.fall_risk?.length ? p.fall_risk : ['none on file']],
    [
      'Recent note excerpts',
      p.notes?.length
        ? p.notes.map((n) => `[${n.author || '?'}] ${String(n.text || '').slice(0, 400)}`)
        : ['none on file'],
    ],
  ];
}

export function renderRecordHtml(p) {
  let html = "<div class='record-panel'>";
  for (const [title, items] of sections(p)) {
    html += `<h4>${title}</h4>`;
    if (title === 'Recent note excerpts') {
      for (const it of items) html += `<p class='note-excerpt'>${escapeHtml(it)}</p>`;
    } else {
      for (const it of items) html += `<p>${escapeHtml(it)}</p>`;
    }
  }
  return html + '</div>';
}

export function escapeHtml(s) {
  return String(s)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

export function renderMermaid(p, pid) {
  const esc = (t) =>
    String(t)
      .replace(/"/g, "'")
      .replace(/[\[\]()]/g, ' ')
      .slice(0, 40);
  const lines = ['flowchart LR', `  P${pid}(["Patient ${pid}<br/>fall ${p.index_date}"])`];
  const groups = [
    ['dx', 'Diagnoses', p.dx || [], '#ccfbf1', '#0f766e'],
    ['med', 'Meds', p.meds || [], '#e0f2fe', '#0369a1'],
    ['lab', 'Labs', p.labs || [], '#fef3c7', '#b45309'],
    ['vit', 'Vitals', p.vitals || [], '#fce7f3', '#be185d'],
    ['fr', 'Fall-risk', p.fall_risk || [], '#ede9fe', '#6d28d9'],
  ];
  for (const [gid, gname, items] of groups) {
    const hub = `${gid}_hub`;
    const label = items.length ? gname : `${gname} (none)`;
    lines.push(`  ${hub}["${label}"]`);
    lines.push(`  P${pid} --> ${hub}`);
    items.slice(0, 4).forEach((it, i) => {
      lines.push(`  ${gid}${i}["${esc(it)}"]`);
      lines.push(`  ${hub} --> ${gid}${i}`);
    });
  }
  return lines.join('\n');
}

function tokenSet(text) {
  return new Set(
    text
      .toLowerCase()
      .replace(/[^a-z0-9\s]/g, ' ')
      .split(/\s+/)
      .filter(Boolean)
  );
}

function conceptScore(q, seed) {
  const qt = tokenSet(q);
  const st = tokenSet(seed);
  let hit = 0;
  for (const t of st) if (qt.has(t) || [...qt].some((w) => w.includes(t) || t.includes(w))) hit++;
  return hit / Math.max(st.size, 1);
}

export function gateQuestion(q, p) {
  const ql = q.toLowerCase();
  if (OOD.some((x) => ql.includes(x))) {
    return {
      decision: 'ABSTAIN',
      why: 'Question is outside clinical chart scope (off-distribution).',
    };
  }

  const scores = SEEDS.map((s) => ({ s, score: conceptScore(q, s) }));
  scores.sort((a, b) => b.score - a.score);
  const best = scores[0];
  if (best.score < 0.15) {
    return {
      decision: 'ABSTAIN',
      why: 'Not close to any learned clinical concept. Hand to clinician.',
    };
  }

  const needsFr = ql.includes('fall risk') || ql.includes('fall-risk');
  if (needsFr) {
    const missing = [];
    if (!p.fr_present) missing.push('fall-risk assessment');
    if (!p.vt_present) missing.push('vitals');
    if (missing.length) {
      return {
        decision: 'GATHER',
        why: `Required evidence missing within 30d of fall (${p.index_date}): ${missing.join(', ')}.`,
      };
    }
  }

  if (/prognosis|life expectancy|surgery outcome/i.test(q) && !p.notes?.some((n) => /prognos|expect/i.test(n.text))) {
    return {
      decision: 'ABSTAIN',
      why: 'The record does not contain data needed to answer this question reliably.',
    };
  }

  if (/duplicate|refill|dose change|which dose/i.test(q) && (p.meds?.length || 0) > 4) {
    return {
      decision: 'GATHER',
      why: 'Medication timeline may be ambiguous; clinician confirmation needed.',
    };
  }

  return {
    decision: 'PROCEED',
    why: `In-band (${best.s}). Evidence present. Reasoning is justified.`,
  };
}

export function frFieldPresent(field, p) {
  const txt = [...(p.fall_risk || []), ...(p.dx || []), ...(p.vitals || [])].join(' ').toLowerCase();
  const key = {
    'fall history': ['fall'],
    'ambulatory aid': ['ambulat', 'walker', 'cane', 'aid'],
    gait: ['gait', 'mobility'],
    'mental status': ['mental', 'confus'],
    confusion: ['confus', 'mental'],
    depression: ['depress'],
    'altered elimination': ['elimination', 'toileting', 'continence'],
    dizziness: ['dizz', 'vertigo'],
    'timed mobility test': ['timed up', 'tug', 'gait speed'],
  };
  if (field === 'secondary diagnosis') return (p.dx || []).length > 1;
  return (key[field] || []).some((k) => txt.includes(k));
}

export function frCheck(calc, p) {
  const spec = FR_CALCS[calc];
  const missing = spec.needs.filter((f) => !frFieldPresent(f, p));
  return { missing, spec };
}

export function isFallRiskQuestion(text) {
  const t = (text || '').toLowerCase();
  const excludes = [
    'medication',
    'med ',
    'meds',
    'drug',
    'cause',
    'lead to',
    'contribute',
    'prevent',
    'list',
    'name',
    'what are',
  ];
  if (excludes.some((x) => t.includes(x))) return false;
  const triggers = [
    'fall risk score',
    'fall-risk score',
    'fall risk assessment',
    'calculate fall risk',
    'assess fall risk',
    'what is the fall risk',
    "what's the fall risk",
    'fall score',
    'compute fall risk',
    'fall risk scale',
  ];
  return triggers.some((tr) => t.includes(tr));
}

function answerForMeds(p) {
  const lines = ['**Medications** (from record only)\n'];
  for (const m of p.meds || []) lines.push(`* ${medCompact(m)}`);
  if (!p.meds?.length) lines.push('* none on file');
  return lines.join('\n');
}

function answerForDx(p) {
  const lines = ['**Diagnoses**\n'];
  for (const d of p.dx || []) lines.push(`* ${d}`);
  if (!p.dx?.length) lines.push('* none on file');
  return lines.join('\n');
}

function answerSummary(p) {
  const lines = ['**Patient summary** (grounded in record)\n'];
  for (const [title, items] of sections(p)) {
    if (title === 'Demographics') continue;
    lines.push(`**${title}**`);
    for (const it of items.slice(0, 8)) lines.push(`* ${it}`);
  }
  lines.push('\n**Current status**');
  lines.push(`* Fall index: ${p.index_date}`);
  lines.push(`* Fall-risk within 30d: ${p.fr_present ? 'yes' : 'no'}`);
  lines.push(`* Vitals within 30d: ${p.vt_present ? 'yes' : 'no'}`);
  return lines.join('\n');
}

export function generateAnswer(decision, q, p) {
  const ql = q.toLowerCase();
  if (decision === 'ABSTAIN') {
    return (
      'This question cannot be answered reliably from the available patient record. ' +
      'The chart does not contain the specific data required, or the question falls outside what this record can support. ' +
      'Please narrow the question or review with a clinician.'
    );
  }
  if (decision === 'GATHER') {
    return (
      '**What is ambiguous**\n' +
      'The question is in scope, but required evidence is missing or incomplete near the fall index date.\n\n' +
      '* Confirm whether a validated fall-risk instrument was completed within 30 days of the index fall.\n' +
      '* Obtain vitals and gait or balance assessment if not documented.\n' +
      '* Route a Morse or Hendrich II survey to the patient or PT as appropriate.'
    );
  }
  if (ql.includes('medication') || ql.includes('meds') || ql.includes('drug')) return answerForMeds(p);
  if (ql.includes('diagnos')) return answerForDx(p);
  if (/summar|overview|status|history/.test(ql)) return answerSummary(p);
  if (ql.includes('fall risk') && p.fall_risk?.length) {
    const lines = ['**Fall-risk assessment**\n'];
    for (const r of p.fall_risk) lines.push(`* ${r}`);
    return lines.join('\n');
  }
  if (ql.includes('lab')) {
    const lines = ['**Recent labs**\n'];
    for (const l of p.labs || []) lines.push(`* ${l}`);
    return lines.join('\n') || '* none on file';
  }
  if (ql.includes('vital')) {
    const lines = ['**Recent vitals**\n'];
    for (const v of p.vitals || []) lines.push(`* ${v}`);
    return lines.join('\n') || '* none on file';
  }
  return answerSummary(p);
}

export function suggestFollowups(q, decision, p) {
  if (decision === 'GATHER') return ['Request Morse survey', 'Check vitals in last 30d'];
  if (decision === 'ABSTAIN') return ['Ask about medications', 'Ask about diagnoses'];
  const out = [];
  if (!p.fr_present) out.push('Fall risk assessment status');
  if ((p.meds || []).length > 3) out.push('Reconcile medication list');
  if (!out.length) out.push('Summarize patient', 'Review fall-risk scores');
  return out.slice(0, 2);
}

export function processQuestion(q, p, frCalc = null) {
  if (frCalc) {
    const { missing, spec } = frCheck(frCalc, p);
    if (missing.length) {
      const [bg, fg] = PALETTE.GATHER;
      return {
        decision: 'GATHER',
        why: `Instrument inputs incomplete for ${frCalc}.`,
        content: `I do not have all the data to complete the **${frCalc}**. Missing inputs: **${missing.join(', ')}**. Collect via ${spec.source}.`,
        bg,
        fg,
        followups: ['Request survey from patient', 'Start over'],
      };
    }
    q = `Using the ${frCalc}, assess this patient's fall risk based only on the record.`;
  }

  const { decision, why } = gateQuestion(q, p);
  const [bg, fg] = PALETTE[decision];
  const content = generateAnswer(decision, q, p);
  const followups = suggestFollowups(q, decision, p);
  return { decision, why, content, bg, fg, followups };
}
