import re
import json, urllib.request
import numpy as np
import pandas as pd
import streamlit as st
from sklearn.metrics.pairwise import cosine_distances

BASE = "/media/data/caidf_data/UIC/Falls"
NOTES_PATH = BASE + "/260305_UIC_Deliverable/260305_UIC_Deliverable/delivery_20260305-082155.csv"
SD = BASE + "/arpa_h_falls_structured_deid/arpa_h_falls_structured_deid"
DEMO = SD + "/00369_ARPA_H_Falls_Demo_Deid.csv"
DIAG = SD + "/00369_ARPA_H_Falls_Diagnosis_Deid.csv"
MEDS = SD + "/00369_ARPA_H_Falls_Meds_Deid.csv"
LABS = SD + "/00369_ARPA_H_Falls_Labs_Deid.csv"
VITALS = SD + "/00369_ARPA_H_Falls_Vitals_Deid.csv"
FALL_RISK = SD + "/00369_ARPA_H_Falls_Fall_Risk_Scale_Deid.csv"
EMBED_URL = "http://localhost:11434/api/embed"
CHAT_URL = "http://localhost:11434/api/chat"
EMBED_MODEL = "mxbai-embed-large"
CHAT_MODEL = "llama3.1:8b"
WINDOW_DAYS = 30
MARGIN = 1.5
SEEDS = ["hip fracture", "fall risk assessment", "gait instability", "general deconditioning"]

def embed_one(text, retries=3):
    text = (str(text) if text is not None else "").strip() or "empty"
    payload = json.dumps({"model": EMBED_MODEL, "input": text[:400]}).encode("utf-8")
    last = None
    for _ in range(retries):
        try:
            req = urllib.request.Request(EMBED_URL, data=payload, headers={"Content-Type":"application/json"})
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.loads(r.read())["embeddings"][0]
        except Exception as e:
            last = e
            import time; time.sleep(1.0)
    raise last

def chat(messages, retries=2):
    payload = json.dumps({"model": CHAT_MODEL, "messages": messages, "stream": False}).encode("utf-8")
    last = None
    for _ in range(retries):
        try:
            req = urllib.request.Request(CHAT_URL, data=payload, headers={"Content-Type":"application/json"})
            with urllib.request.urlopen(req, timeout=120) as r:
                return json.loads(r.read())["message"]["content"]
        except Exception as e:
            last = e
            import time; time.sleep(1.0)
    return "Model error: %s" % last

def calibrate_band(vectors, k=3.0, floor=0.02):
    centroid = np.asarray(vectors.mean(axis=0)).ravel()
    d = cosine_distances(vectors, centroid.reshape(1, -1)).ravel()
    return centroid, max(float(d.mean() + k * d.std()), floor)

@st.cache_resource(show_spinner="Building concept bands (one-time)...")
def build_bands(n_notes=800):
    import os, pickle
    cache = "/home/abasu9/AchievabilityAgent/bands_cache.pkl"
    if os.path.exists(cache):
        with open(cache, "rb") as f:
            return pickle.load(f)
    df = pd.read_csv(NOTES_PATH, engine="python", on_bad_lines="skip", nrows=n_notes)
    col = next((c for c in ("note_text","NOTE","DEID_NOTE_RELEASE","TEXT","note") if c in df.columns), df.columns[-1])
    notes = df[df[col].notna()][col].tolist()
    X = []
    for t in notes:
        try: X.append(embed_one(t))
        except Exception: continue
    X = np.asarray(X, dtype=float)
    bands = {}
    for s_ in SEEDS:
        sv = np.asarray(embed_one(s_)).reshape(1, -1)
        d = cosine_distances(X, sv).ravel()
        bands[s_] = calibrate_band(X[d.argsort()[:200]])
    with open(cache, "wb") as f:
        pickle.dump(bands, f)
    return bands

def patient_rows(path, pid, usecols, chunksize=500000):
    keep = []
    for ch in pd.read_csv(path, usecols=usecols, chunksize=chunksize, low_memory=False):
        keep.append(ch[ch["PATIENT_ID"] == pid])
    return pd.concat(keep, ignore_index=True) if keep else pd.DataFrame()

@st.cache_resource(show_spinner=False)
def load_sample():
    import json
    with open("/home/abasu9/AchievabilityAgent/sample_100.json") as f:
        return json.load(f)

def load_patient(pid):
    return load_sample().get(str(pid))

def _clean(t):
    t = str(t).replace("\\r\\n", " ").replace("\r\n", " ").replace("\n", " ")
    t = t.replace("[REDACTED]", "").replace("  ", " ")
    return re.sub(r"\s+", " ", t).strip()

import re as _re2

def _med_compact(entry):
    m = _re2.match(r"\s*(.+?)\s*\((\d+) fills:\s*(.+)\)\s*$", str(entry))
    if m:
        name, n, dates = m.group(1), m.group(2), m.group(3)
        parts = [d.strip() for d in dates.split(",") if d.strip()]
        rng = ("%s to %s" % (parts[0], parts[-1])) if parts else ""
        return "%s: %s fills, %s" % (name, n, rng)
    m2 = _re2.match(r"\s*(.+?)\s*\(started\s*(.+?)\)\s*$", str(entry))
    if m2:
        return "%s: 1 fill, %s" % (m2.group(1), m2.group(2))
    return str(entry)

def _sections(p):
    return [
        ("Demographics", ["Fall index date: %s" % p["index_date"], "Age at fall: %s" % p.get("age","n/a")]),
        ("Diagnoses", p["dx"] or ["none on file"]),
        ("Medications", [_med_compact(m) for m in p["meds"]] or ["none on file"]),
        ("Recent labs", p["labs"] or ["none on file"]),
        ("Recent vitals", p["vitals"] or ["none on file"]),
        ("Fall-risk assessment", p["fall_risk"] or ["none on file"]),
        ("Recent note excerpts", ["[%s] %s" % (n.get("author","?"), _clean(n.get("text",""))) for n in p["notes"]] or ["none on file"]),
    ]

def build_context(p):
    out = []
    for title, items in _sections(p):
        out.append(title + ": " + "; ".join(items))
    return "\n".join(out)

def render_record(p):
    html = "<div style='background:#fff;border:1px solid #e2e8f0;border-radius:12px;padding:1rem 1.25rem'>"
    for title, items in _sections(p):
        html += "<p style='font-size:12px;font-weight:600;color:#0f766e;text-transform:uppercase;letter-spacing:.04em;margin:.8rem 0 .3rem'>%s</p>" % title
        if title == "Recent note excerpts":
            for it in items:
                html += "<p style='font-size:13px;color:#475569;line-height:1.5;margin:0 0 .5rem'>%s</p>" % it[:400]
        else:
            for it in items:
                html += "<p style='font-size:14px;color:#1a2733;line-height:1.5;margin:0 0 .2rem'>%s</p>" % it
    html += "</div>"
    return html

def render_mermaid(p, pid):
    def esc(t):
        return str(t).replace('"', "").replace("\n", " ").replace("(", " ").replace(")", " ")[:36]
    L = ["flowchart LR"]
    c = "P%d" % pid
    L.append('  %s(["Patient %d<br/>fall %s"])' % (c, pid, p["index_date"]))
    groups = [
        ("dx", "Diagnoses", p["dx"]),
        ("med", "Medications", p["meds"]),
        ("lab", "Labs", p["labs"]),
        ("vit", "Vitals", p["vitals"]),
        ("fr", "Fall-risk", p["fall_risk"]),
    ]
    for gid, gname, items in groups:
        hub = "%s_hub" % gid
        label = gname if items else gname + " <br/>(none on file)"
        L.append('  %s["%s"]' % (hub, label))
        L.append('  %s --> %s' % (c, hub))
        for i, it in enumerate(items[:3]):
            nid = "%s%d" % (gid, i)
            L.append('  %s["%s"]' % (nid, esc(it)))
            L.append('  %s --> %s' % (hub, nid))
    L.append('  classDef dx fill:#fee2e2,stroke:#991b1b,color:#991b1b;')
    L.append('  classDef med fill:#dbeafe,stroke:#1e40af,color:#1e40af;')
    L.append('  classDef lab fill:#d1fae5,stroke:#065f46,color:#065f46;')
    L.append('  classDef vit fill:#fef3c7,stroke:#92400e,color:#92400e;')
    L.append('  classDef fr fill:#ede9fe,stroke:#5b21b6,color:#5b21b6;')
    for gid, _, items in groups:
        members = ["%s_hub" % gid] + ["%s%d" % (gid, i) for i in range(min(len(items),6))]
        L.append('  class %s %s;' % (",".join(members), gid))
    return "\n".join(L)

def show_mermaid(code):
    import streamlit.components.v1 as components
    html = """
    <div class="mermaid">%s</div>
    <script src="https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.min.js"></script>
    <script>mermaid.initialize({startOnLoad:true, theme:'neutral'});</script>
    """ % code
    components.html(html, height=520, scrolling=True)

def render_graph(p, pid):
    def esc(t):
        return str(t).replace('"', "'").replace("\n", " ").replace("\r", "")[:50]
    dot = []
    dot.append("digraph G {")
    dot.append("  graph [rankdir=LR, nodesep=0.4, ranksep=1.5, pad=0.3];")
    dot.append('  bgcolor="transparent";')
    dot.append('  node [style=filled fontname="Helvetica" fontsize=10 shape=box];')
    center = "Patient %d (fall %s)" % (pid, p["index_date"])
    dot.append('  "%s" [shape=doubleoctagon fillcolor="#1a2733" fontcolor="white" fontsize=13];' % center)
    groups = [
        ("Diagnoses", p.get("dx",[]), "#fee2e2", "#991b1b"),
        ("Medications", p.get("meds",[]), "#dbeafe", "#1e40af"),
        ("Labs", p.get("labs",[]), "#d1fae5", "#065f46"),
        ("Vitals", p.get("vitals",[]), "#fef3c7", "#92400e"),
        ("Fall-Risk", p.get("fall_risk",[]), "#ede9fe", "#5b21b6"),
    ]
    for gname, items, fill, font in groups:
        hub = "%s_hub" % gname.replace("-","")
        label = gname if items else gname + " (none on file)"
        dot.append('  "%s" [label="%s" fillcolor="%s" fontcolor="%s" fontsize=11 shape=folder];' % (hub, label, fill, font))
        dot.append('  "%s" -> "%s";' % (center, hub))
        for i, it in enumerate(items):
            nid = "%s_%d" % (gname.replace("-",""), i)
            dot.append('  "%s" [label="%s" fillcolor="%s" fontcolor="%s"];' % (nid, esc(it), fill, font))
            dot.append('  "%s" -> "%s";' % (hub, nid))
    notes = p.get("notes", [])
    nhub = "Notes_hub"
    nlabel = "Notes (%d)" % len(notes) if notes else "Notes (none)"
    dot.append('  "%s" [label="%s" fillcolor="#e0f2fe" fontcolor="#075985" fontsize=11 shape=folder];' % (nhub, nlabel))
    dot.append('  "%s" -> "%s";' % (center, nhub))
    for i, n in enumerate(notes):
        nid = "note_%d" % i
        if isinstance(n, dict):
            auth = esc(n.get("author", "?"))
            txt = esc(n.get("text", ""))
            label = "[%s] %s" % (auth, txt)
        else:
            label = esc(str(n))
        dot.append('  "%s" [label="%s" fillcolor="#e0f2fe" fontcolor="#075985"];' % (nid, label))
        dot.append('  "%s" -> "%s";' % (nhub, nid))
    dot.append("}")
    return "\n".join(dot)

import os, glob
CHAT_DIR = "/home/abasu9/AchievabilityAgent/chats"

def chat_path(pid):
    return os.path.join(CHAT_DIR, "patient_%d.json" % int(pid))

def load_chat(pid):
    fp = chat_path(pid)
    if os.path.exists(fp):
        try:
            with open(fp) as f:
                return json.load(f)
        except Exception:
            return []
    return []

def save_chat(pid, history):
    os.makedirs(CHAT_DIR, exist_ok=True)
    with open(chat_path(pid), "w") as f:
        json.dump(history, f)

def saved_patient_ids():
    ids = []
    for fp in sorted(glob.glob(os.path.join(CHAT_DIR, "patient_*.json"))):
        try:
            ids.append(int(os.path.basename(fp).replace("patient_","").replace(".json","")))
        except Exception:
            pass
    return ids

FR_CALCS = {
    "Morse Fall Scale": {"type":"survey",
        "needs":["fall history","secondary diagnosis","ambulatory aid","gait","mental status"],
        "source":"a patient-facing Morse survey plus chart review"},
    "Hendrich II": {"type":"survey",
        "needs":["confusion","depression","altered elimination","dizziness","gait"],
        "source":"a patient-facing Hendrich II survey plus chart review"},
    "Timed Up and Go (TUG)": {"type":"performance",
        "needs":["timed mobility test"],
        "source":"a performance test administered by PT or the care provider"},
}

def fr_field_present(field, p):
    txt = " ".join(p.get("fall_risk",[]) + p.get("dx",[]) + p.get("vitals",[])).lower()
    KEY = {
        "fall history":["fall"], "ambulatory aid":["ambulat","walker","cane","aid"],
        "gait":["gait","mobility"], "mental status":["mental","loc","awareness","confus"],
        "confusion":["confus","mental"], "depression":["depress"],
        "altered elimination":["elimination","toileting","continence"],
        "dizziness":["dizz","vertigo"], "timed mobility test":["timed up","tug","gait speed"],
    }
    if field == "secondary diagnosis":
        return len(p.get("dx",[])) > 1
    return any(k in txt for k in KEY.get(field, []))

def fr_check(calc, p):
    spec = FR_CALCS[calc]
    missing = [f for f in spec["needs"] if not fr_field_present(f, p)]
    return missing, spec

def gate(bands, qvec, evidence_present, missing, index_date):
    best_c, best = None, 1e9
    for name,(cen,rad) in bands.items():
        dist = float(cosine_distances(qvec.reshape(1,-1), cen.reshape(1,-1))[0,0])
        if dist < best: best_c, best = name, dist
    rad = bands[best_c][1]; ceil = rad * MARGIN
    if best > ceil:
        return "ABSTAIN", best_c, best, rad, ceil, "Off-distribution: not close to any learned concept. No data fixes this; hand to clinician."
    if not evidence_present:
        return "GATHER", best_c, best, rad, ceil, "In-distribution but required evidence missing within %dd of fall (%s): %s." % (WINDOW_DAYS, index_date, ", ".join(missing))
    return "PROCEED", best_c, best, rad, ceil, "In-band and evidence present. Reasoning is justified."

def classify_intent(q, ctx):
    csys = ("You are a clinical question router. Given a patient record and a question, "
            "classify into exactly one word: PROCEED, GATHER, or ABSTAIN.\n"
            "PROCEED: the record directly contains what is needed to answer factually.\n"
            "GATHER: the data is present but AMBIGUOUS, incomplete, or needs clinical "
            "clarification to answer safely. Example: medications repeated across different "
            "dates that could be refills, dose changes, or true duplicates and require "
            "clinician confirmation. Any case where the honest move is to ask a clarifying "
            "question rather than guess.\n"
            "ABSTAIN: the question is genuinely outside what any patient chart could support, "
            "or unanswerable in principle.\n"
            "Respond with ONLY the one word on the first line. If GATHER, add a second line "
            "with one sentence naming exactly what needs clarifying.")
    cuser = "PATIENT RECORD:\n%s\n\nQUESTION: %s" % (ctx, q)
    try:
        raw = chat([{"role":"system","content":csys},{"role":"user","content":cuser}]).strip()
    except Exception:
        return "PROCEED", ""
    lines = [l.strip() for l in raw.split("\n") if l.strip()]
    label = lines[0].upper().split()[0] if lines else "PROCEED"
    if label not in ("PROCEED","GATHER","ABSTAIN"):
        label = "PROCEED"
    clarify = lines[1] if len(lines) > 1 else ""
    return label, clarify

st.set_page_config(page_title="Achievability Agent", layout="centered")
try:
    with open("/home/abasu9/AchievabilityAgent/style.css") as _f:
        st.markdown("<style>" + _f.read() + "</style>", unsafe_allow_html=True)
except Exception:
    pass
st.markdown('''<style>
.stApp { background:#f7fafc; }
.block-container { padding-top:2rem; max-width:840px; }
.hdr { display:flex; align-items:center; justify-content:space-between; border-bottom:1px solid #e2e8f0; padding-bottom:1rem; margin-bottom:1.25rem; }
.hdr h1 { font-size:26px; font-weight:600; color:#1a2733; margin:0; }
.hdr .sub { font-size:14px; color:#64748b; margin-top:2px; }
.live { display:flex; align-items:center; gap:7px; font-size:13px; color:#0f766e; font-weight:500; }
.dot { width:9px; height:9px; border-radius:50%; background:#10b981; display:inline-block; }
.evrow { display:flex; gap:12px; margin:.25rem 0 .75rem; }
.evcard { flex:1; background:#fff; border:1px solid #e2e8f0; border-radius:12px; padding:.75rem 1rem; }
.evcard .lab { font-size:12px; color:#64748b; margin:0 0 3px; }
.evcard .val { font-size:18px; font-weight:600; color:#1a2733; margin:0; }
.verdict { display:inline-block; padding:5px 14px; border-radius:20px; font-weight:600; font-size:13px; }
.ans { background:#fff; border:1px solid #e2e8f0; border-radius:14px; padding:1.1rem 1.3rem; margin-top:.75rem; line-height:1.65; color:#1a2733; box-shadow:0 1px 2px rgba(16,24,40,.04); }
.umsg { background:#eef2ff; border-radius:12px; padding:.7rem 1rem; margin-top:.75rem; color:#1e293b; font-weight:500; }
.gline { font-size:13px; color:#475569; margin:.5rem 0 0; }
</style>''', unsafe_allow_html=True)

st.markdown('''<div style="background:linear-gradient(135deg,#0f0c29 0%,#1e1b4b 50%,#3b0764 100%);border-radius:20px;padding:2.8rem 3rem;margin:0 0 1.5rem;box-shadow:0 14px 40px rgba(15,12,41,.35);position:relative;overflow:hidden;">
<div style="position:absolute;right:-40px;top:-40px;width:200px;height:200px;border-radius:50%;background:rgba(124,58,237,.25);"></div>
<div style="position:absolute;right:60px;bottom:-60px;width:260px;height:260px;border-radius:50%;background:rgba(124,58,237,.15);"></div>
<div style="font-size:48px;font-weight:800;color:#ffffff;margin-bottom:1.2rem;position:relative;">NextStep<span style="background:linear-gradient(100deg,#2dd4bf,#60a5fa);-webkit-background-clip:text;background-clip:text;-webkit-text-fill-color:transparent;">.ai</span></div>
<div style="font-size:38px;font-weight:800;line-height:1.1;background:linear-gradient(100deg,#2dd4bf,#60a5fa,#a78bfa);-webkit-background-clip:text;background-clip:text;-webkit-text-fill-color:transparent;margin-bottom:1.2rem;position:relative;">Restraint prevents liability.</div>
<div style="font-size:16px;color:#94a3b8;line-height:1.6;max-width:580px;margin-bottom:1.2rem;position:relative;">An agent that knows when not to answer and becomes how the All-Care Team coordinates around one trusted record.</div>
<div style="font-size:17px;font-weight:700;color:#ffffff;margin-bottom:1rem;position:relative;">Safer care. &nbsp; Cleaner claims. &nbsp; One source of truth.</div>
<div style="font-size:14px;color:#5eead4;font-weight:600;position:relative;">Gated &nbsp;&middot;&nbsp; Grounded &nbsp;&middot;&nbsp; Auditable &nbsp;&middot;&nbsp; Human-in-the-Loop</div>
</div>''', unsafe_allow_html=True)

bands = build_bands()
if "chat" not in st.session_state: st.session_state.chat = []
if "cur_pid" not in st.session_state: st.session_state.cur_pid = None

with st.sidebar:
    st.markdown("### Saved conversations")
    saved = saved_patient_ids()
    if saved:
        for sid in saved:
            _sc, _sd = st.columns([4,1])
            if _sc.button("Patient %d" % sid, key="side_%d" % sid):
                st.session_state.pick_pid = sid
                st.rerun()
            if _sd.button("\u2715", key="del_%d" % sid):
                fp = chat_path(sid)
                if os.path.exists(fp): os.remove(fp)
                if st.session_state.get("cur_pid") == sid:
                    st.session_state.chat = []
                st.rerun()
    else:
        st.caption("No saved chats yet.")

pid = st.number_input("Patient ID", min_value=1, value=int(st.session_state.pop("pick_pid", None) or st.session_state.get("cur_pid") or 1), step=1)
if pid != st.session_state.cur_pid:
    st.session_state.cur_pid = pid
    st.session_state.chat = load_chat(pid)

p = load_patient(int(pid))
if p is None:
    st.error("Patient %d not found." % pid)
    st.stop()

st.markdown('''<div class="evrow">
<div class="evcard"><p class="lab">Fall index date</p><p class="val">%s</p></div>
<div class="evcard"><p class="lab">Fall-risk within 30d</p><p class="val">%s</p></div>
<div class="evcard"><p class="lab">Vitals within 30d</p><p class="val">%s</p></div>
</div>''' % (p["index_date"], "yes" if p["fr_present"] else "no", "yes" if p["vt_present"] else "no"), unsafe_allow_html=True)

with st.expander("View patient record the model sees"):
    st.markdown(render_record(p), unsafe_allow_html=True)

if st.toggle("Show patient knowledge graph"):
    st.graphviz_chart(render_graph(p, int(pid)))

for m in st.session_state.chat:
    if m["role"] == "user":
        st.markdown('<div class="umsg">%s</div>' % m["content"], unsafe_allow_html=True)
    else:
        st.markdown('<span class="verdict" style="background:%s;color:%s">%s</span><div class="gline">%s</div>'
                    % (m["bg"], m["fg"], m["decision"], m["why"]), unsafe_allow_html=True)
        _c = m["content"].replace(" * ", " \n* ").replace(" - ", " \n- ")
        _c = _c.replace("\n", "<br>")
        st.markdown(_c, unsafe_allow_html=True)


if st.session_state.get("followups"):
    st.markdown("<p style='font-size:13px;color:#64748b;margin:.5rem 0 .3rem'>Suggested follow-ups</p>", unsafe_allow_html=True)
    fcols = st.columns(len(st.session_state.followups))
    for i, fu in enumerate(st.session_state.followups):
        if fcols[i].button(fu, key="fu_%d" % i, width='stretch'):
            st.session_state.pending_q = fu
            st.session_state.followups = []
            st.rerun()

st.markdown("<p style='font-size:13px;color:#64748b;margin:.5rem 0 .3rem'>Quick actions</p>", unsafe_allow_html=True)
PRESETS = {
    "Summarize patient": "Summarize this patient's history and current status.",
    "Fall risk score": "What is the patient's fall risk score?",
    "Medications": "What medications is this patient currently on?",
    "Diagnoses": "What are this patient's main diagnoses?",
}
qa = st.columns(len(PRESETS))
for col, (label, preset) in zip(qa, PRESETS.items()):
    if col.button(label, key="qa_"+label, width='stretch'):
        st.session_state.pending_q = preset
        st.session_state.preset_flag = True

typed = st.chat_input("Ask about this patient...")
q = typed or st.session_state.pop("pending_q", None)

BROAD = ["tell me about", "summarize", "summary", "overview", "what's going on",
         "whats going on", "how is", "status", "anything", "everything"]
def is_broad(text):
    t = text.lower()
    return any(b in t for b in BROAD)

# If the question is broad and not already a clarifying pick, offer options.
if False and q and is_broad(q) and not st.session_state.get("is_pick"):
    ctx0 = build_context(p)
    opt_sys = ("Given a patient record and a broad question, propose exactly 4 short, specific "
               "follow-up questions a clinician might mean. Reply ONLY as 4 lines, no numbering, "
               "each under 10 words.")
    opt_user = "PATIENT RECORD:\n%s\n\nBROAD QUESTION: %s" % (ctx0, q)
    raw = chat([{"role":"system","content":opt_sys},{"role":"user","content":opt_user}])
    opts = [l.strip("-* ").strip() for l in raw.split("\n") if l.strip()][:4]
    st.markdown("<p style='font-size:14px;color:#1a2733;font-weight:600;margin:.5rem 0'>Did you mean:</p>", unsafe_allow_html=True)
    ocols = st.columns(min(len(opts),2))
    for i, opt in enumerate(opts):
        if ocols[i % 2].button(opt, key="opt_%d" % i, width='stretch'):
            st.session_state.pending_q = opt
            st.session_state.is_pick = True
            st.rerun()
    st.stop()

st.session_state.is_pick = False

def _is_fallrisk(t):
    t = (t or "").lower().strip()
    excludes = ["medication", "med ", "meds", "drug", "cause", "lead to", "leads to",
                "leading", "contribute", "factor", "why", "which", "reduce", "prevent",
                "list", "name", "what are"]
    if any(x in t for x in excludes):
        return False
    triggers = ["fall risk score", "fall-risk score", "fall risk assessment",
                "calculate fall risk", "assess fall risk", "what is the fall risk",
                "what's the fall risk", "fall score", "compute fall risk", "fall risk scale"]
    return any(tr in t for tr in triggers)

if q and not _is_fallrisk(q):
    st.session_state.fr_step = None



if q and _is_fallrisk(q) and st.session_state.get("fr_step") in (None, "done"):
    st.session_state.fr_step = "pick_type"; q = None

if st.session_state.get("fr_step") == "pick_type":
    st.markdown("<p style='font-weight:600;color:#1e1b4b;margin:.5rem 0'>Fall risk is broad. Which kind of validated assessment?</p>", unsafe_allow_html=True)
    _a, _b = st.columns(2)
    if _a.button("Patient-facing survey", key="frt_s"):
        st.session_state.fr_type="survey"; st.session_state.fr_step="pick_calc"; st.rerun()
    if _b.button("Provider performance test", key="frt_p"):
        st.session_state.fr_type="performance"; st.session_state.fr_step="pick_calc"; st.rerun()
    st.stop()

if st.session_state.get("fr_step") == "pick_calc":
    opts = [k for k,v in FR_CALCS.items() if v["type"]==st.session_state.fr_type]
    st.markdown("<p style='font-weight:600;color:#1e1b4b;margin:.5rem 0'>Which validated instrument?</p>", unsafe_allow_html=True)
    cc = st.columns(len(opts))
    for i,name in enumerate(opts):
        if cc[i].button(name, key="frc_%d"%i):
            st.session_state.fr_calc=name; st.session_state.fr_step="result"; st.rerun()
    st.stop()

if st.session_state.get("fr_step") == "result":
    calc = st.session_state.fr_calc
    missing, spec = fr_check(calc, p)
    if not missing:
        st.markdown('<span style="background:#d1fae5;color:#0f766e;padding:5px 14px;border-radius:20px;font-weight:700;font-size:12px">PROCEED</span>', unsafe_allow_html=True)
        q = "Using the %s, assess this patient's fall risk based only on the record." % calc
        st.session_state.fr_step = "done"
    else:
        st.markdown('<span style="background:#dbeafe;color:#1d4ed8;padding:5px 14px;border-radius:20px;font-weight:700;font-size:12px">GATHER</span>', unsafe_allow_html=True)
        st.markdown("<div class='ans'>I do not have all the data to complete the <b>%s</b>. Missing inputs: <b>%s</b>. I cannot answer yet. To obtain the missing data, collect it via %s.</div>" % (calc, ", ".join(missing), spec["source"]), unsafe_allow_html=True)
        _r1, _r2 = st.columns(2)
        label = "Send survey to patient" if spec["type"]=="survey" else "Request test from PT"
        if _r1.button(label, key="fr_route"):
            st.success("Request queued: %s" % spec["source"])
        if _r2.button("Start over", key="fr_reset"):
            st.session_state.fr_step=None; st.rerun()
        st.session_state.fr_step = "done"
        st.stop()

if q:
    needs = "fall risk" in q.lower()
    if needs:
        present = p["fr_present"] and p["vt_present"]
        missing = [x for x,ok in [("fall-risk assessment",p["fr_present"]),("vitals",p["vt_present"])] if not ok]
    else:
        present, missing = True, []
    qv = np.asarray(embed_one(q))
    decision, concept, dist, rad, ceil, why = gate(bands, qv, present, missing, p["index_date"])
    PAL = {"PROCEED":("#d1fae5","#0f766e"),"GATHER":("#dbeafe","#1d4ed8"),"ABSTAIN":("#fef3c7","#b45309")}
    ctx = build_context(p)
    if not needs and decision != "ABSTAIN":
        with st.spinner("Checking answerability..."):
            try:
                _chk = chat([{"role":"system","content":
                    "You answer ONLY with the single word YES or NO. Given a patient record and a question, "
                    "answer YES if the specific data needed to answer is actually present in the record, "
                    "and NO if that data is absent or the question is out of scope for this record."},
                    {"role":"user","content":"PATIENT RECORD:\n%s\n\nQUESTION: %s" % (ctx, q)}]).strip().upper()
            except Exception:
                _chk = "YES"
        if _chk.startswith("NO"):
            decision = "ABSTAIN"
            why = "The record does not contain the data needed to answer this question reliably."
    bg, fg = PAL[decision]
    sys = ("You are a clinical assistant answering ONLY from the patient record provided. "
           "If something is not in the record, say 'not documented in the available record'. "
           "Do not invent values. Always structure your response with clear labeled sections "
           "using headers (e.g. **Diagnoses**, **Medications**, **Labs**, **Vitals**, **Fall-Risk Assessment**, "
           "**Current Status**) and use bullet points for lists. Include specific values and numbers from the record. "
           "For the Current Status section, always use bullet points, never a paragraph. "
           "For the Fall-Risk Assessment section, show each component with its actual numeric score; a score of 0 is a real, valid value meaning no elevated risk on that component, so display it as 0, never as 'Not Available' or 'missing'. "
           "When listing medications you MUST name every single medication individually as its own bullet. "
           "NEVER summarize medications as 'numerous medications', 'various medications', 'multiple medications', or say the list is 'not exhaustive'. "
           "Always enumerate every medication name present in the record. You may omit fill dates for brevity, but every drug name must appear.")
    if decision == "ABSTAIN":
        abstain_sys = ("You are a gate that has determined a clinical question CANNOT be reliably "
                       "answered from the available patient record. Your ONLY job is to explain, in 2 to 3 "
                       "sentences, WHY this specific question cannot be answered reliably given what is and "
                       "is not in the record. You MUST NOT provide any clinical answer, diagnosis, medication "
                       "guidance, score, or medical conclusion of any kind. Do not list patient data. "
                       "Only explain the reason for abstaining and suggest the question be narrowed or reviewed by a clinician.")
        abstain_user = "PATIENT RECORD (for context only, do not answer from it):\n%s\n\nQUESTION THAT CANNOT BE ANSWERED: %s\n\nExplain why this cannot be reliably answered." % (ctx, q)
        with st.spinner("Checking the question..."):
            ans = chat([{"role":"system","content":abstain_sys},{"role":"user","content":abstain_user}])
            ans = ans.strip()
    elif decision == "GATHER":
        gather_sys = ("You are a clinical assistant. A question cannot be answered definitively yet because "
                      "the data is present but ambiguous and needs clinician confirmation. Do NOT give a final "
                      "clinical answer. Instead, in 2 to 4 short bullet points, write the specific clarifying "
                      "questions a clinician should answer to resolve the ambiguity. Reference the actual record "
                      "(for example, medications repeated across dates that may be refills, dose changes, or "
                      "concurrent duplicates). Start with one sentence stating what is ambiguous, then the bullets.")
        gather_user = "PATIENT RECORD:\n%s\n\nQUESTION: %s\n\nWhat does the clinician need to clarify?" % (ctx, q)
        with st.spinner("Identifying what to clarify..."):
            ans = chat([{"role":"system","content":gather_sys},{"role":"user","content":gather_user}])
            ans = ans.replace("* ", "\n* ").replace("- ", "\n- ").strip()
    else:
        note = ""
        user = "PATIENT RECORD:\n%s\n\nQUESTION: %s%s" % (ctx, q, note)
        with st.spinner("Generating response..."):
            ans = chat([{"role":"system","content":sys},{"role":"user","content":user}])
            ans = ans.replace("* ", "\n* ").replace("- ", "\n- ").strip()
    st.session_state.chat.append({"role":"user","content":q})
    st.session_state.chat.append({"role":"assistant","content":ans,"decision":decision,"why":why,"bg":bg,"fg":fg})
    # generate 2 suggested follow-ups based on the answer
    fu_sys = ("Given a patient record and the last answer, suggest exactly 2 short follow-up "
              "questions a clinician might ask next. Reply ONLY as 2 lines, no numbering, each under 10 words.")
    fu_user = "PATIENT RECORD:\n%s\n\nLAST ANSWER: %s" % (ctx, ans)
    try:
        fu_raw = chat([{"role":"system","content":fu_sys},{"role":"user","content":fu_user}])
        fus = [l.strip("-* ").strip() for l in fu_raw.split("\n") if l.strip()][:2]
    except Exception:
        fus = []
    st.session_state.followups = fus
    save_chat(pid, st.session_state.chat)
    st.rerun()
