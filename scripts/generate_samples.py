#!/usr/bin/env python3
"""Generate synthetic demo cohort for static NextStep site (default: 200 patients)."""
from __future__ import annotations

import json
import random
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "data" / "sample_patients.json"
COUNT = 200
SEED = 42

DX_POOL = [
    "Essential hypertension",
    "Type 2 diabetes mellitus",
    "Atrial fibrillation",
    "Chronic obstructive pulmonary disease",
    "Osteoarthritis of knee",
    "History of falling",
    "Muscle weakness (generalized)",
    "Gait instability",
    "Major depressive disorder",
    "Vitamin D deficiency",
    "Hip fracture, closed",
    "Osteoporosis",
    "Benign prostatic hyperplasia",
    "Heart failure",
    "Chronic kidney disease, stage 3",
    "Dementia, unspecified",
    "Peripheral neuropathy",
    "Anemia, unspecified",
]

MEDS_POOL = [
    "Lisinopril",
    "Metformin",
    "Amlodipine",
    "Apixaban",
    "Sertraline",
    "Tamsulosin",
    "Alendronate",
    "Acetaminophen",
    "Furosemide",
    "Atorvastatin",
    "Omeprazole",
    "Gabapentin",
    "Tiotropium",
    "Albuterol",
    "Carvedilol",
]

LABS_POOL = [
    ("Hemoglobin A1c", "7.2", "%"),
    ("Creatinine", "1.1", "mg/dL"),
    ("Sodium", "139", "mmol/L"),
    ("Potassium", "4.2", "mmol/L"),
    ("INR", "2.1", ""),
    ("BNP", "180", "pg/mL"),
    ("Hemoglobin", "11.8", "g/dL"),
    ("Calcium", "9.1", "mg/dL"),
    ("Vitamin D", "22", "ng/mL"),
]

VITALS_POOL = [
    ("Blood pressure", "132/78", "mmHg"),
    ("Heart rate", "72", "bpm"),
    ("Weight", "168", "lb"),
    ("Temperature", "98.2", "F"),
    ("Oxygen saturation", "94", "%"),
    ("Respiratory rate", "18", "/min"),
    ("Pain score", "3", "/10"),
]

MORSE_COMPONENTS = [
    ("Morse Fall Scale - History of falling", "25"),
    ("Morse Fall Scale - Secondary diagnosis", "15"),
    ("Morse Fall Scale - Ambulatory aid", "15"),
    ("Morse Fall Scale - Gait", "20"),
    ("Morse Fall Scale - Mental status", "0"),
    ("Morse Fall Scale - Total", "75"),
]

HENDRICH = [
    ("Hendrich II - Confusion", "1"),
    ("Hendrich II - Depression", "1"),
    ("Hendrich II - Dizziness", "0"),
    ("Hendrich II - Total", "4"),
]

NOTE_SNIPPETS = [
    ("RN", "Patient ambulates with rolling walker. Fall precautions in place."),
    ("MD", "Follow-up after index fall. Gait unsteady on exam. Continue PT referral."),
    ("PT", "Balance deficits noted during ambulation training."),
    ("Orthopedics", "Post-operative status. Weight-bearing as tolerated with walker."),
]


def rand_date(rng: random.Random, start: date, end: date) -> date:
    delta = (end - start).days
    return start + timedelta(days=rng.randint(0, max(delta, 1)))


def med_entry(rng: random.Random, name: str, idx: date) -> str:
    n = rng.randint(1, 4)
    if n == 1:
        return f"{name} (started {idx.isoformat()})"
    dates = sorted(
        {(idx + timedelta(days=rng.randint(-60, 30))).isoformat() for _ in range(n)}
    )
    return f"{name} ({n} fills: {', '.join(dates)})"


def build_patient(pid: int, rng: random.Random) -> dict:
    idx = rand_date(rng, date(2023, 6, 1), date(2024, 11, 30))
    age = rng.randint(65, 92)
    fr_present = rng.random() < 0.72
    vt_present = rng.random() < 0.85

    dx = rng.sample(DX_POOL, k=rng.randint(2, 6))
    meds = [med_entry(rng, m, idx) for m in rng.sample(MEDS_POOL, k=rng.randint(2, 6))]
    labs = [
        f"{a} {b} {c}".strip()
        for a, b, c in rng.sample(LABS_POOL, k=rng.randint(2, 5))
    ]
    vitals = (
        [f"{a} {b} {c}".strip() for a, b, c in rng.sample(VITALS_POOL, k=rng.randint(2, 5))]
        if vt_present
        else []
    )

    if fr_present:
        fall_risk = (
            [f"{a}: {b}" for a, b in MORSE_COMPONENTS]
            if rng.random() < 0.6
            else [f"{a}: {b}" for a, b in HENDRICH]
        )
    else:
        fall_risk = []

    notes = [
        {"author": a, "text": t + f" Patient ID {pid}."}
        for a, t in rng.sample(NOTE_SNIPPETS, k=rng.randint(1, 3))
    ]

    return {
        "index_date": idx.isoformat(),
        "age": age,
        "dx": dx,
        "meds": meds,
        "labs": labs,
        "vitals": vitals,
        "fall_risk": fall_risk,
        "notes": notes,
        "fr_present": fr_present,
        "vt_present": vt_present,
    }


def main() -> None:
    rng = random.Random(SEED)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    cohort = {str(i): build_patient(i, rng) for i in range(1, COUNT + 1)}
    with open(OUT, "w") as f:
        json.dump(cohort, f, separators=(",", ":"))
    gather = sum(1 for p in cohort.values() if not p["fr_present"])
    print(f"Wrote {len(cohort)} patients to {OUT} ({OUT.stat().st_size // 1024} KB)")
    print(f"Patients missing fall-risk (GATHER on fall-risk Q): ~{gather}")


if __name__ == "__main__":
    main()
