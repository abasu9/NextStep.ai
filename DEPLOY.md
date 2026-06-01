# Deploy NextStep.ai

Static site lives in **`docs/`** — not Hugo, Jekyll, or a Node app.

## GitHub Pages (recommended)

Push to `main`. Workflow [`.github/workflows/pages.yml`](.github/workflows/pages.yml) publishes `docs/` to:

**https://abasu9.github.io/NextStep.ai/**

### Fix: wrong site on GitHub Pages

If you see the black **“AI Modernisation / executive coaching”** page, GitHub is still redirecting to **nextstep.ai** (OVH — not this repo).

1. **https://github.com/abasu9/NextStep.ai/settings/pages**
2. **Custom domain** → **Remove** (empty). Save.
3. **Build and deployment → Source** → **GitHub Actions**.
4. **Actions** → **Deploy to GitHub Pages** → **Run workflow**.

Use **https://abasu9.github.io/NextStep.ai/** until DNS for `nextstep.ai` points at GitHub.

## Netlify

Netlify was failing with `hugo: command not found` because the UI was set for Hugo (`publish: public`).

**Use [`netlify.toml`](netlify.toml)** in the repo, or set in Netlify → **Build & deploy**:

| Setting | Value |
|--------|--------|
| Build command | `python3 scripts/generate_samples.py` (or empty) |
| Publish directory | `docs` |

Do **not** use `hugo` or `public`.

## Local preview

```bash
./run.sh
# http://localhost:8080
```
