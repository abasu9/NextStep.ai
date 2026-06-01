# Fix: wrong site opening on GitHub Pages

If you see the black **“AI Modernisation / executive coaching”** page, GitHub is still redirecting to **nextstep.ai** (hosted on OVH — not this repo).

## One-time fix in GitHub (required)

1. Open **https://github.com/abasu9/NextStep.ai/settings/pages**
2. Under **Custom domain**, click **Remove** (leave the field empty). Save.
3. Under **Build and deployment → Source**, choose **GitHub Actions**.
4. Open **https://github.com/abasu9/NextStep.ai/actions** → **Deploy to GitHub Pages** → **Run workflow** → Run.

Wait 2–3 minutes.

## Correct URL (no custom domain)

**https://abasu9.github.io/NextStep.ai/**

You should see the dark teal **Achievability Agent** page (hero: “Restraint prevents liability”) and a **Live demo** section with Patient ID 1–200.

Do **not** use `nextstep.ai` until you point that domain’s DNS at GitHub; it will keep showing the old OVH site.

## Local preview

```bash
./run.sh
# http://localhost:8080
```
