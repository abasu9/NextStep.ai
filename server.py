"""NextStep.ai web server."""
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import logic

ROOT = Path(__file__).resolve().parent
WEB = ROOT / "web"

app = FastAPI(title="NextStep.ai", version="1.0.0")
app.mount("/static", StaticFiles(directory=WEB), name="static")


class AskBody(BaseModel):
    patient_id: int
    question: str
    fr_calc: str | None = None


class FrCheckBody(BaseModel):
    patient_id: int
    calc: str


@app.get("/")
def index():
    return FileResponse(WEB / "index.html")


@app.get("/api/health")
def health():
    return {
        "ok": True,
        "ollama": logic.ollama_available(),
        "patients": logic.list_patient_ids(),
    }


@app.get("/api/patients")
def patients():
    return {"ids": logic.list_patient_ids()}


@app.get("/api/patients/{pid}")
def patient(pid: int):
    p = logic.load_patient(pid)
    if p is None:
        raise HTTPException(404, f"Patient {pid} not found")
    return {
        "id": pid,
        "index_date": p["index_date"],
        "fr_present": p["fr_present"],
        "vt_present": p["vt_present"],
        "age": p.get("age"),
        "record_html": logic.render_record_html(p),
        "graph_dot": logic.render_graph_dot(p, pid),
    }


@app.get("/api/chats")
def chats():
    return {"saved": logic.saved_patient_ids()}


@app.get("/api/chats/{pid}")
def get_chat(pid: int):
    return {"patient_id": pid, "messages": logic.load_chat(pid)}


@app.delete("/api/chats/{pid}")
def remove_chat(pid: int):
    logic.delete_chat(pid)
    return {"ok": True}


@app.post("/api/fr-check")
def fr_check(body: FrCheckBody):
    p = logic.load_patient(body.patient_id)
    if p is None:
        raise HTTPException(404, "Patient not found")
    if body.calc not in logic.FR_CALCS:
        raise HTTPException(400, "Unknown instrument")
    missing, spec = logic.fr_check(body.calc, p)
    return {
        "calc": body.calc,
        "missing": missing,
        "source": spec["source"],
        "type": spec["type"],
        "proceed": len(missing) == 0,
    }


@app.get("/api/fr-calcs")
def fr_calcs(fr_type: str | None = None):
    out = []
    for name, spec in logic.FR_CALCS.items():
        if fr_type is None or spec["type"] == fr_type:
            out.append({"name": name, **spec})
    return {"instruments": out}


@app.post("/api/ask")
def ask(body: AskBody):
    q = (body.question or "").strip()
    if not q and not body.fr_calc:
        raise HTTPException(400, "Question required")
    result = logic.process_question(body.patient_id, q or "", fr_calc=body.fr_calc)
    if "error" in result:
        raise HTTPException(404, result["error"])
    return result


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("server:app", host="0.0.0.0", port=8080, reload=True)
