# NextStep.ai — The Achievability Agent

A clinical AI gate that decides whether a question *can* be answered before it answers.

- **PROCEED** — the record contains the evidence needed; answer grounded in the record.
- **GATHER** — in scope but evidence is missing or ambiguous; name what's needed.
- **ABSTAIN** — out of scope or absent data; explain why instead of guessing.

This repo is built **100% free**: static HTML/CSS/JS, no API keys, no paid hosting required. Patient data is **synthetic** (200 demo charts). Chats are stored in **localStorage** in the browser.

## Live site (GitHub Pages)

**URL:** https://abasu9.github.io/NextStep.ai/

If you see the wrong (black coaching) site, follow **[DEPLOY.md](DEPLOY.md)** — remove the **custom domain** under repo Settings → Pages (we do not use `nextstep.ai` for this demo).

1. **Settings → Pages** → remove any custom domain → **Save**
2. **Source** → **GitHub Actions**
3. **Actions** → run **Deploy to GitHub Pages**

### Sample data in this repo

**`docs/data/sample_patients.json` is committed to git** (~200 synthetic patients). It is **not real clinical data** — safe for public GitHub and Pages. See [docs/data/README.md](docs/data/README.md).

Or run locally:

```bash
cd docs
python3 -m http.server 8080
# open http://localhost:8080
```

## Regenerate sample data

```bash
python3 scripts/generate_samples.py
```

Writes `docs/data/sample_patients.json` (200 patients by default). Edit `COUNT` in the script to change size.

## Project layout

| Path | Purpose |
|------|---------|
| `docs/` | Static site deployed to GitHub Pages |
| `docs/js/engine.js` | Achievability gate + grounded answers (browser) |
| `docs/data/sample_patients.json` | 200 synthetic patients |
| `scripts/generate_samples.py` | Cohort generator |
| `.github/workflows/pages.yml` | Deploy workflow |
| `app.py`, `server.py`, `logic.py`, `build_sample.py` | Optional local/Python tooling (not used on Pages) |

## Optional local Python stack

For development with Streamlit or FastAPI + Ollama (not required for the public site):

```bash
pip install -r requirements.txt
./run.sh   # FastAPI on :8080
streamlit run app.py
```

## Real UIC cohort

The UIC Falls data is not redistributed. To use your own cohort locally, run `build_sample.py` against your mounted dataset and replace `docs/data/sample_patients.json`.

