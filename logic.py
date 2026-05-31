"""Core achievability agent logic (shared by API and legacy Streamlit app)."""
from __future__ import annotations

import glob
import json
import os
import pickle
import re
import time
import urllib.error
import urllib.request
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics.pairwise import cosine_distances

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "docs" / "data"
SAMPLE_PATH = DATA_DIR / "sample_patients.json"
CHAT_DIR = DATA_DIR / "chats"
BANDS_CACHE = DATA_DIR / "bands_cache.pkl"

EMBED_URL = os.environ.get("OLLAMA_EMBED_URL", "http://localhost:11434/api/embed")
CHAT_URL = os.environ.get("OLLAMA_CHAT_URL", "http://localhost:11434/api/chat")
EMBED_MODEL = os.environ.get("EMBED_MODEL", "mxbai-embed-large")
CHAT_MODEL = os.environ.get("CHAT_MODEL", "llama3.1:8b")
WINDOW_DAYS = 30
MARGIN = 1.5
SEEDS = ["hip fracture", "fall risk assessment", "gait instability", "general deconditioning"]

FR_CALCS = {
    "Morse Fall Scale": {
        "type": "survey",
        "needs": ["fall history", "secondary diagnosis", "ambulatory aid", "gait", "mental status"],
        "source": "a patient-facing Morse survey plus chart review",
    },
    "Hendrich II": {
        "type": "survey",
        "needs": ["confusion", "depression", "altered elimination", "dizziness", "gait"],
        "source": "a patient-facing Hendrich II survey plus chart review",
    },
    "Timed Up and Go (TUG)": {
        "type": "performance",
        "needs": ["timed mobility test"],
        "source": "a performance test administered by PT or the care provider",
    },
}

PALETTE = {
    "PROCEED": ("#d1fae5", "#0f766e"),
    "GATHER": ("#dbeafe", "#1d4ed8"),
    "ABSTAIN": ("#fef3c7", "#b45309"),
}

_bands: dict | None = None
_ollama_ok: bool | None = None


def ollama_available() -> bool:
    """True only when Ollama responds and the configured embed model works."""
    global _ollama_ok
    if _ollama_ok is not None:
        return _ollama_ok
    try:
        req = urllib.request.Request(
            EMBED_URL.replace("/api/embed", "/api/tags"),
            method="GET",
        )
        with urllib.request.urlopen(req, timeout=3):
            pass
        embed_one("ping", retries=1)
        _ollama_ok = True
    except Exception:
        _ollama_ok = False
    return _ollama_ok


def embed_one(text: str, retries: int = 3) -> list[float]:
    text = (str(text) if text is not None else "").strip() or "empty"
    payload = json.dumps({"model": EMBED_MODEL, "input": text[:400]}).encode("utf-8")
    last: Exception | None = None
    for _ in range(retries):
        try:
            req = urllib.request.Request(
                EMBED_URL, data=payload, headers={"Content-Type": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.loads(r.read())["embeddings"][0]
        except Exception as e:
            last = e
            time.sleep(1.0)
    raise last or RuntimeError("embed failed")


def chat(messages: list[dict], retries: int = 2) -> str:
    payload = json.dumps(
        {"model": CHAT_MODEL, "messages": messages, "stream": False}
    ).encode("utf-8")
    last: Exception | None = None
    for _ in range(retries):
        try:
            req = urllib.request.Request(
                CHAT_URL, data=payload, headers={"Content-Type": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=120) as r:
                return json.loads(r.read())["message"]["content"]
        except Exception as e:
            last = e
            time.sleep(1.0)
    return f"Model error: {last}"


def calibrate_band(vectors: np.ndarray, k: float = 3.0, floor: float = 0.02):
    centroid = np.asarray(vectors.mean(axis=0)).ravel()
    d = cosine_distances(vectors, centroid.reshape(1, -1)).ravel()
    return centroid, max(float(d.mean() + k * d.std()), floor)


def _demo_bands() -> dict:
    rng = np.random.default_rng(42)
    bands = {}
    for s in SEEDS:
        cen = rng.standard_normal(384)
        cen /= np.linalg.norm(cen) + 1e-9
        bands[s] = (cen, 0.35)
    return bands


def build_bands(n_notes: int = 200) -> dict:
    global _bands
    if _bands is not None:
        return _bands
    if BANDS_CACHE.exists():
        with open(BANDS_CACHE, "rb") as f:
            _bands = pickle.load(f)
            return _bands
    if not ollama_available():
        _bands = _demo_bands()
        return _bands
    notes_path = os.environ.get("NOTES_PATH", "")
    if not notes_path or not os.path.exists(notes_path):
        _bands = _demo_bands()
        return _bands
    df = pd.read_csv(notes_path, engine="python", on_bad_lines="skip", nrows=n_notes)
    col = next(
        (c for c in ("note_text", "NOTE", "DEID_NOTE_RELEASE", "TEXT", "note") if c in df.columns),
        df.columns[-1],
    )
    notes = df[df[col].notna()][col].tolist()
    X = []
    for t in notes:
        try:
            X.append(embed_one(t))
        except Exception:
            continue
    if len(X) < 10:
        _bands = _demo_bands()
        return _bands
    X = np.asarray(X, dtype=float)
    bands = {}
    for s in SEEDS:
        sv = np.asarray(embed_one(s)).reshape(1, -1)
        d = cosine_distances(X, sv).ravel()
        bands[s] = calibrate_band(X[d.argsort()[: min(200, len(X))]])
    BANDS_CACHE.parent.mkdir(parents=True, exist_ok=True)
    with open(BANDS_CACHE, "wb") as f:
        pickle.dump(bands, f)
    _bands = bands
    return _bands


def load_sample() -> dict:
    with open(SAMPLE_PATH) as f:
        return json.load(f)


def list_patient_ids() -> list[int]:
    return sorted(int(k) for k in load_sample().keys())


def load_patient(pid: int) -> dict | None:
    return load_sample().get(str(pid))


def _clean(t: str) -> str:
    t = str(t).replace("\\r\\n", " ").replace("\r\n", " ").replace("\n", " ")
    t = t.replace("[REDACTED]", "").replace("  ", " ")
    return re.sub(r"\s+", " ", t).strip()


def _med_compact(entry: str) -> str:
    m = re.match(r"\s*(.+?)\s*\((\d+) fills:\s*(.+)\)\s*$", str(entry))
    if m:
        name, n, dates = m.group(1), m.group(2), m.group(3)
        parts = [d.strip() for d in dates.split(",") if d.strip()]
        rng = f"{parts[0]} to {parts[-1]}" if parts else ""
        return f"{name}: {n} fills, {rng}"
    m2 = re.match(r"\s*(.+?)\s*\(started\s*(.+?)\)\s*$", str(entry))
    if m2:
        return f"{m2.group(1)}: 1 fill, {m2.group(2)}"
    return str(entry)


def _sections(p: dict) -> list[tuple[str, list[str]]]:
    return [
        ("Demographics", [f"Fall index date: {p['index_date']}", f"Age at fall: {p.get('age', 'n/a')}"]),
        ("Diagnoses", p["dx"] or ["none on file"]),
        ("Medications", [_med_compact(m) for m in p["meds"]] or ["none on file"]),
        ("Recent labs", p["labs"] or ["none on file"]),
        ("Recent vitals", p["vitals"] or ["none on file"]),
        ("Fall-risk assessment", p["fall_risk"] or ["none on file"]),
        (
            "Recent note excerpts",
            [f"[{n.get('author', '?')}] {_clean(n.get('text', ''))}" for n in p["notes"]]
            or ["none on file"],
        ),
    ]


def build_context(p: dict) -> str:
    out = []
    for title, items in _sections(p):
        out.append(f"{title}: {'; '.join(items)}")
    return "\n".join(out)


def render_record_html(p: dict) -> str:
    html = "<div class='record-panel'>"
    for title, items in _sections(p):
        html += f"<h4>{title}</h4>"
        if title == "Recent note excerpts":
            for it in items:
                html += f"<p class='note-excerpt'>{it[:400]}</p>"
        else:
            for it in items:
                html += f"<p>{it}</p>"
    html += "</div>"
    return html


def render_graph_dot(p: dict, pid: int) -> str:
    def esc(t):
        return str(t).replace('"', "'").replace("\n", " ").replace("\r", "")[:50]

    dot = ["digraph G {", '  graph [rankdir=LR, nodesep=0.4, ranksep=1.5, pad=0.3];', '  bgcolor="transparent";']
    dot.append('  node [style=filled fontname="Helvetica" fontsize=10 shape=box];')
    center = f"Patient {pid} (fall {p['index_date']})"
    dot.append(
        f'  "{center}" [shape=doubleoctagon fillcolor="#1a2733" fontcolor="white" fontsize=13];'
    )
    groups = [
        ("Diagnoses", p.get("dx", []), "#fee2e2", "#991b1b"),
        ("Medications", p.get("meds", []), "#dbeafe", "#1e40af"),
        ("Labs", p.get("labs", []), "#d1fae5", "#065f46"),
        ("Vitals", p.get("vitals", []), "#fef3c7", "#92400e"),
        ("Fall-Risk", p.get("fall_risk", []), "#ede9fe", "#5b21b6"),
    ]
    for gname, items, fill, font in groups:
        hub = f"{gname.replace('-', '')}_hub"
        label = gname if items else f"{gname} (none on file)"
        dot.append(
            f'  "{hub}" [label="{label}" fillcolor="{fill}" fontcolor="{font}" fontsize=11 shape=folder];'
        )
        dot.append(f'  "{center}" -> "{hub}";')
        for i, it in enumerate(items):
            nid = f"{gname.replace('-', '')}_{i}"
            dot.append(f'  "{nid}" [label="{esc(it)}" fillcolor="{fill}" fontcolor="{font}"];')
            dot.append(f'  "{hub}" -> "{nid}";')
    notes = p.get("notes", [])
    nhub = "Notes_hub"
    nlabel = f"Notes ({len(notes)})" if notes else "Notes (none)"
    dot.append(
        f'  "{nhub}" [label="{nlabel}" fillcolor="#e0f2fe" fontcolor="#075985" fontsize=11 shape=folder];'
    )
    dot.append(f'  "{center}" -> "{nhub}";')
    for i, n in enumerate(notes):
        nid = f"note_{i}"
        auth = esc(n.get("author", "?"))
        txt = esc(n.get("text", ""))
        dot.append(
            f'  "{nid}" [label="[{auth}] {txt}" fillcolor="#e0f2fe" fontcolor="#075985"];'
        )
        dot.append(f'  "{nhub}" -> "{nid}";')
    dot.append("}")
    return "\n".join(dot)


def chat_path(pid: int) -> Path:
    return CHAT_DIR / f"patient_{int(pid)}.json"


def load_chat(pid: int) -> list[dict]:
    fp = chat_path(pid)
    if fp.exists():
        try:
            with open(fp) as f:
                return json.load(f)
        except Exception:
            return []
    return []


def save_chat(pid: int, history: list[dict]) -> None:
    CHAT_DIR.mkdir(parents=True, exist_ok=True)
    with open(chat_path(pid), "w") as f:
        json.dump(history, f)


def delete_chat(pid: int) -> None:
    fp = chat_path(pid)
    if fp.exists():
        fp.unlink()


def saved_patient_ids() -> list[int]:
    ids = []
    for fp in sorted(glob.glob(str(CHAT_DIR / "patient_*.json"))):
        try:
            ids.append(int(os.path.basename(fp).replace("patient_", "").replace(".json", "")))
        except Exception:
            pass
    return ids


def fr_field_present(field: str, p: dict) -> bool:
    txt = " ".join(p.get("fall_risk", []) + p.get("dx", []) + p.get("vitals", [])).lower()
    key = {
        "fall history": ["fall"],
        "ambulatory aid": ["ambulat", "walker", "cane", "aid"],
        "gait": ["gait", "mobility"],
        "mental status": ["mental", "loc", "awareness", "confus"],
        "confusion": ["confus", "mental"],
        "depression": ["depress"],
        "altered elimination": ["elimination", "toileting", "continence"],
        "dizziness": ["dizz", "vertigo"],
        "timed mobility test": ["timed up", "tug", "gait speed"],
    }
    if field == "secondary diagnosis":
        return len(p.get("dx", [])) > 1
    return any(k in txt for k in key.get(field, []))


def fr_check(calc: str, p: dict) -> tuple[list[str], dict]:
    spec = FR_CALCS[calc]
    missing = [f for f in spec["needs"] if not fr_field_present(f, p)]
    return missing, spec


def _demo_embed(text: str) -> np.ndarray:
    rng = np.random.default_rng(hash(text) % (2**32))
    v = rng.standard_normal(384)
    v /= np.linalg.norm(v) + 1e-9
    return v


def gate(bands: dict, qvec: np.ndarray, evidence_present: bool, missing: list, index_date: str):
    best_c, best = None, 1e9
    for name, (cen, rad) in bands.items():
        dist = float(cosine_distances(qvec.reshape(1, -1), cen.reshape(1, -1))[0, 0])
        if dist < best:
            best_c, best = name, dist
    rad = bands[best_c][1]
    ceil = rad * MARGIN
    if best > ceil:
        return (
            "ABSTAIN",
            best_c,
            best,
            rad,
            ceil,
            "Off-distribution: not close to any learned concept. No data fixes this; hand to clinician.",
        )
    if not evidence_present:
        return (
            "GATHER",
            best_c,
            best,
            rad,
            ceil,
            f"In-distribution but required evidence missing within {WINDOW_DAYS}d of fall ({index_date}): {', '.join(missing)}.",
        )
    return "PROCEED", best_c, best, rad, ceil, "In-band and evidence present. Reasoning is justified."


def demo_gate(q: str, p: dict) -> tuple[str, str]:
    ql = q.lower()
    ood = ["insurance", "billing", "weather", "stock", "recipe", "legal advice"]
    if any(x in ql for x in ood):
        return "ABSTAIN", "Question is outside clinical chart scope."
    if "fall risk" in ql and (not p["fr_present"] or not p["vt_present"]):
        missing = []
        if not p["fr_present"]:
            missing.append("fall-risk assessment")
        if not p["vt_present"]:
            missing.append("vitals")
        return "GATHER", f"Missing within {WINDOW_DAYS}d of fall: {', '.join(missing)}."
    return "PROCEED", "Demo mode: record appears sufficient for a grounded answer."


def is_fallrisk_question(text: str) -> bool:
    t = (text or "").lower().strip()
    excludes = [
        "medication",
        "med ",
        "meds",
        "drug",
        "cause",
        "lead to",
        "leads to",
        "leading",
        "contribute",
        "factor",
        "why",
        "which",
        "reduce",
        "prevent",
        "list",
        "name",
        "what are",
    ]
    if any(x in t for x in excludes):
        return False
    triggers = [
        "fall risk score",
        "fall-risk score",
        "fall risk assessment",
        "calculate fall risk",
        "assess fall risk",
        "what is the fall risk",
        "what's the fall risk",
        "fall score",
        "compute fall risk",
        "fall risk scale",
    ]
    return any(tr in t for tr in triggers)


def _demo_answer(decision: str, q: str, p: dict) -> str:
    ctx = build_context(p)
    if decision == "ABSTAIN":
        return (
            "This question cannot be answered reliably from the available patient record. "
            "The chart does not contain the specific data required, or the question falls outside "
            "what a de-identified fall cohort record can support. Please narrow the question or review with a clinician."
        )
    if decision == "GATHER":
        return (
            "**What is ambiguous**\n"
            "The question is in scope, but required evidence is missing or incomplete near the fall index date.\n\n"
            "* Confirm whether a validated fall-risk instrument was completed within 30 days of the index fall.\n"
            "* Obtain vitals and gait or balance assessment if not documented.\n"
            "* Route a Morse or Hendrich II survey to the patient or PT as appropriate."
        )
    lines = ["**Summary (demo mode — connect Ollama for live LLM answers)**\n"]
    for title, items in _sections(p):
        if title == "Demographics":
            continue
        lines.append(f"**{title}**")
        for it in items[:8]:
            lines.append(f"* {it}")
    lines.append("\n**Current Status**")
    lines.append(f"* Fall index date: {p['index_date']}")
    lines.append(f"* Fall-risk data within 30d: {'yes' if p['fr_present'] else 'no'}")
    lines.append(f"* Vitals within 30d: {'yes' if p['vt_present'] else 'no'}")
    return "\n".join(lines)


def generate_answer(decision: str, q: str, p: dict, ctx: str) -> str:
    if not ollama_available():
        return _demo_answer(decision, q, p)

    if decision == "ABSTAIN":
        abstain_sys = (
            "You are a gate that has determined a clinical question CANNOT be reliably "
            "answered from the available patient record. Your ONLY job is to explain, in 2 to 3 "
            "sentences, WHY this specific question cannot be answered reliably given what is and "
            "is not in the record. You MUST NOT provide any clinical answer. Only explain why."
        )
        abstain_user = (
            f"PATIENT RECORD (for context only):\n{ctx}\n\nQUESTION: {q}\n\nExplain why."
        )
        return chat(
            [{"role": "system", "content": abstain_sys}, {"role": "user", "content": abstain_user}]
        ).strip()

    if decision == "GATHER":
        gather_sys = (
            "You are a clinical assistant. Do NOT give a final clinical answer. "
            "In 2 to 4 short bullet points, write clarifying questions for the clinician."
        )
        gather_user = f"PATIENT RECORD:\n{ctx}\n\nQUESTION: {q}\n\nWhat needs clarification?"
        ans = chat(
            [{"role": "system", "content": gather_sys}, {"role": "user", "content": gather_user}]
        )
        return ans.replace("* ", "\n* ").replace("- ", "\n- ").strip()

    sys = (
        "You are a clinical assistant answering ONLY from the patient record provided. "
        "If something is not in the record, say 'not documented in the available record'. "
        "Use labeled sections with bullet points. Include specific values from the record."
    )
    user = f"PATIENT RECORD:\n{ctx}\n\nQUESTION: {q}"
    ans = chat([{"role": "system", "content": sys}, {"role": "user", "content": user}])
    return ans.replace("* ", "\n* ").replace("- ", "\n- ").strip()


def suggest_followups(ctx: str, ans: str) -> list[str]:
    if not ollama_available():
        return ["Review fall-risk components", "Check medication interactions"]
    fu_sys = (
        "Given a patient record and the last answer, suggest exactly 2 short follow-up "
        "questions. Reply ONLY as 2 lines, no numbering, each under 10 words."
    )
    fu_user = f"PATIENT RECORD:\n{ctx}\n\nLAST ANSWER: {ans}"
    try:
        fu_raw = chat([{"role": "system", "content": fu_sys}, {"role": "user", "content": fu_user}])
        return [l.strip("-* ").strip() for l in fu_raw.split("\n") if l.strip()][:2]
    except Exception:
        return []


def process_question(pid: int, q: str, fr_calc: str | None = None) -> dict:
    p = load_patient(pid)
    if p is None:
        return {"error": f"Patient {pid} not found"}

    if fr_calc:
        missing, spec = fr_check(fr_calc, p)
        if missing:
            bg, fg = PALETTE["GATHER"]
            content = (
                f"I do not have all the data to complete the **{fr_calc}**. "
                f"Missing inputs: **{', '.join(missing)}**. "
                f"Collect via {spec['source']}."
            )
            return {
                "decision": "GATHER",
                "why": f"Instrument inputs incomplete for {fr_calc}.",
                "content": content,
                "bg": bg,
                "fg": fg,
                "followups": [],
            }
        q = f"Using the {fr_calc}, assess this patient's fall risk based only on the record."

    needs = "fall risk" in q.lower()
    if needs:
        present = p["fr_present"] and p["vt_present"]
        missing = [
            x
            for x, ok in [("fall-risk assessment", p["fr_present"]), ("vitals", p["vt_present"])]
            if not ok
        ]
    else:
        present, missing = True, []

    bands = build_bands()
    use_llm = ollama_available()
    if use_llm:
        try:
            qv = np.asarray(embed_one(q))
        except Exception:
            use_llm = False
            qv = _demo_embed(q)
    else:
        qv = _demo_embed(q)

    if use_llm:
        decision, concept, dist, rad, ceil, why = gate(
            bands, qv, present, missing, p["index_date"]
        )
    else:
        decision, why = demo_gate(q, p)
        if needs and not present:
            decision = "GATHER"

    ctx = build_context(p)
    if not needs and decision != "ABSTAIN" and use_llm:
        try:
            chk = chat(
                [
                    {
                        "role": "system",
                        "content": "Answer ONLY YES or NO. Is the data needed to answer present in the record?",
                    },
                    {"role": "user", "content": f"PATIENT RECORD:\n{ctx}\n\nQUESTION: {q}"},
                ]
            ).strip().upper()
            if chk.startswith("NO"):
                decision = "ABSTAIN"
                why = "The record does not contain the data needed to answer this question reliably."
        except Exception:
            pass

    bg, fg = PALETTE[decision]
    content = generate_answer(decision, q, p, ctx)
    followups = suggest_followups(ctx, content)

    msg_user = {"role": "user", "content": q}
    msg_asst = {
        "role": "assistant",
        "content": content,
        "decision": decision,
        "why": why,
        "bg": bg,
        "fg": fg,
    }
    history = load_chat(pid)
    history.extend([msg_user, msg_asst])
    save_chat(pid, history)

    return {
        "decision": decision,
        "why": why,
        "content": content,
        "bg": bg,
        "fg": fg,
        "followups": followups,
        "history": history,
    }
