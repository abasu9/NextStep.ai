# Sample patient data (synthetic)

`sample_patients.json` contains **200 fully synthetic** patient charts for demo and GitHub Pages.

- **Not real patient data** — no PHI, no UIC cohort, safe to clone and redistribute.
- **Generated** by `scripts/generate_samples.py` (deterministic seed for reproducibility).
- **Committed to git** on purpose so the live site works without a backend or private mounts.

To regenerate:

```bash
python3 scripts/generate_samples.py
```

Replace your real cohort only in private environments; do not commit regulated data to this public repo.
