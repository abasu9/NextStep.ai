"""Extract patient sample from UIC Falls dataset (requires local data mount)."""
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent
SD = "/media/data/caidf_data/UIC/Falls/arpa_h_falls_structured_deid/arpa_h_falls_structured_deid"
NOTES = "/media/data/caidf_data/UIC/Falls/260305_UIC_Deliverable/260305_UIC_Deliverable/delivery_20260305-082155.csv"
DEMO = SD + "/00369_ARPA_H_Falls_Demo_Deid.csv"
OUT = ROOT / "docs" / "data" / "sample_patients.json"
WINDOW = 30
N = 100

TABLES = {
    "dx": (SD + "/00369_ARPA_H_Falls_Diagnosis_Deid.csv", ["PATIENT_ID", "START_DATE", "ICD_DESCRIPTION"]),
    "meds": (SD + "/00369_ARPA_H_Falls_Meds_Deid.csv", ["PATIENT_ID", "START_DATE", "GENERIC_NAME"]),
    "labs": (SD + "/00369_ARPA_H_Falls_Labs_Deid.csv", ["PATIENT_ID", "RESULT_DATE", "LABTEST_NAME", "VALUE", "UNIT"]),
    "vitals": (SD + "/00369_ARPA_H_Falls_Vitals_Deid.csv", ["PATIENT_ID", "VITAL_DATE", "VITAL_NAME", "VALUE", "UNIT"]),
    "fr": (SD + "/00369_ARPA_H_Falls_Fall_Risk_Scale_Deid.csv", ["PATIENT_ID", "MEASUREMENT_DATE", "FALL_MEASURE_NAME", "VALUE"]),
}


def meds_with_dates(mdf):
    if mdf is None or mdf.empty:
        return []
    out = []
    g = mdf.dropna(subset=["GENERIC_NAME"]).copy()
    g["d"] = pd.to_datetime(g["START_DATE"], errors="coerce")
    for name, sub in g.groupby("GENERIC_NAME"):
        dates = sorted(set(d.date().isoformat() for d in sub["d"].dropna()))
        if not dates:
            out.append(str(name))
        elif len(dates) == 1:
            out.append("%s (started %s)" % (name, dates[0]))
        else:
            out.append("%s (%d fills: %s)" % (name, len(dates), ", ".join(dates)))
    return out


def main():
    print("Loading demo, taking first %d patients..." % N)
    demo = pd.read_csv(DEMO, low_memory=False)
    demo = demo[demo["INDEX_DATE"].notna()].head(N)
    patients = [int(x) for x in demo["PATIENT_ID"].tolist()]
    pset = set(patients)
    print("  patients:", patients[:10], "...")

    collected = {pid: {} for pid in patients}
    for key, (path, cols) in TABLES.items():
        print("Scanning %s ..." % key)
        parts = {pid: [] for pid in patients}
        for ch in pd.read_csv(path, usecols=cols, chunksize=500000, low_memory=False):
            sub = ch[ch["PATIENT_ID"].isin(pset)]
            if sub.empty:
                continue
            for pid, r in sub.groupby("PATIENT_ID"):
                parts[int(pid)].append(r)
        for pid in patients:
            collected[pid][key] = (
                pd.concat(parts[pid], ignore_index=True) if parts[pid] else pd.DataFrame(columns=cols)
            )

    print("Scanning notes ...")
    ndf = pd.read_csv(NOTES, engine="python", on_bad_lines="skip")
    ncol = "note_text" if "note_text" in ndf.columns else ndf.columns[-1]
    pcol = "patient_id" if "patient_id" in ndf.columns else "PATIENT_ID"
    acol = "author_type" if "author_type" in ndf.columns else None

    def notes_for(pid):
        sub = ndf[ndf[pcol] == pid]
        sub = sub[sub[ncol].notna()]
        return [
            {
                "author": (str(r[acol]) if acol and pd.notna(r[acol]) else "Unknown"),
                "text": str(r[ncol]),
            }
            for _, r in sub.iterrows()
        ]

    notes_by_pid = {pid: notes_for(pid) for pid in patients}
    out = {}
    for pid in patients:
        drow = demo[demo["PATIENT_ID"] == pid].iloc[0]
        idx = pd.to_datetime(drow["INDEX_DATE"])
        c = collected[pid]

        def win(df, col):
            if df.empty:
                return False
            dts = pd.to_datetime(df[col], errors="coerce")
            return bool(((dts - idx).abs().dt.days <= WINDOW).any())

        notes = notes_by_pid[pid]
        out[str(pid)] = {
            "index_date": str(idx.date()),
            "age": int(drow["AGE_AT_FALL"]) if pd.notna(drow.get("AGE_AT_FALL")) else None,
            "dx": c["dx"].tail(15)["ICD_DESCRIPTION"].dropna().tolist(),
            "meds": meds_with_dates(c["meds"]),
            "labs": (
                c["labs"]
                .tail(10)
                .apply(lambda r: "%s %s %s" % (r["LABTEST_NAME"], r["VALUE"], r.get("UNIT", "")), axis=1)
                .tolist()
                if not c["labs"].empty
                else []
            ),
            "vitals": (
                c["vitals"]
                .tail(10)
                .apply(lambda r: "%s %s %s" % (r["VITAL_NAME"], r["VALUE"], r.get("UNIT", "")), axis=1)
                .tolist()
                if not c["vitals"].empty
                else []
            ),
            "fall_risk": (
                c["fr"]
                .tail(8)
                .apply(lambda r: "%s: %s" % (r["FALL_MEASURE_NAME"], r["VALUE"]), axis=1)
                .tolist()
                if not c["fr"].empty
                else []
            ),
            "notes": [{"author": n["author"], "text": n["text"][:600]} for n in notes[-3:]],
            "fr_present": win(c["fr"], "MEASUREMENT_DATE"),
            "vt_present": win(c["vitals"], "VITAL_DATE"),
        }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT, "w") as f:
        json.dump(out, f)
    gather = [pid for pid in patients if not out[str(pid)]["fr_present"]]
    print("Wrote %s with %d patients." % (OUT, len(out)))
    print("Patients that will trigger GATHER on a fall-risk question:", gather[:15])


if __name__ == "__main__":
    main()
