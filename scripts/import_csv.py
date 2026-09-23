#!/usr/bin/env python3
"""Import an existing tracker (Notion, Airtable, Google Sheets, any CSV) into
applications/<YYYY-MM>/.

  python3 scripts/import_csv.py path/to/export.csv [--dry-run]

Column names are matched loosely (Position/Role/Title, Company, Status, Job URL/URL,
Applied on/Date, Source, Apply type, Location fit, Remote scope, Fit score, Posted,
Why it fits, Notes). Rows that point at the same posting are merged into one file:
the most advanced status wins and the other rows' notes are appended.
"""
import argparse, csv, datetime as dt, re, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import seekter  # noqa: E402

STATUS_MAP = {
    "shortlisted": "pending", "pending": "pending", "to apply": "pending", "draft": "pending",
    "applied": "applied", "submitted": "applied",
    "screening": "interviewing", "interview": "interviewing", "interviewing": "interviewing",
    "offer": "offer", "rejected": "rejected", "declined": "rejected",
    "no response": "closed", "ghosted": "closed", "withdrawn": "closed", "closed": "closed",
    "skipped": "skipped", "skip": "skipped",
}
RANK = {"offer": 7, "interviewing": 6, "rejected": 5, "applied": 4, "closed": 3, "pending": 2, "skipped": 1}
ALIASES = {
    "role": ["position", "role", "title", "job title", "name"],
    "company": ["company", "employer"],
    "status": ["status", "stage"],
    "url": ["job url", "url", "link", "posting"],
    "applied": ["applied on", "applied", "date applied", "date"],
    "updated": ["last update", "updated"],
    "posted": ["posted", "posted on"],
    "source": ["source"],
    "apply_type": ["apply type", "method"],
    "location_fit": ["location fit", "location"],
    "remote_scope": ["remote scope", "remote"],
    "fit": ["fit score", "fit"],
    "why": ["why it fits", "why"],
    "notes": ["notes", "comments"],
}


def pick(row, field):
    low = {k.strip().lower().lstrip("﻿"): v for k, v in row.items() if k}
    for name in ALIASES[field]:
        if name in low and low[name] not in (None, ""):
            return low[name].strip()
    return ""


def date(s):
    s = (s or "").strip()
    if not s:
        return ""
    s = re.split(r"\s*(→|->)\s*", s)[0]
    s = re.sub(r"\s+\d{1,2}:\d{2}.*$", "", s)
    for f in ("%Y-%m-%d", "%B %d, %Y", "%b %d, %Y", "%d/%m/%Y", "%m/%d/%Y", "%d.%m.%Y", "%Y/%m/%d"):
        try:
            return dt.datetime.strptime(s, f).date().isoformat()
        except ValueError:
            pass
    m = re.search(r"\d{4}-\d{2}-\d{2}", s)
    return m.group(0) if m else ""


def fit_code(s):
    m = re.match(r"\s*([ABCX])\b", s or "")
    return m.group(1) if m else (s or "")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("csv")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    with open(a.csv, newline="", encoding="utf-8-sig") as fh:
        raw = list(csv.DictReader(fh))
    groups = {}
    for row in raw:
        r = {f: pick(row, f) for f in ALIASES}
        if not (r["company"] or r["role"]):
            continue
        r["status"] = STATUS_MAP.get(r["status"].lower(), "pending")
        for f in ("applied", "updated", "posted"):
            r[f] = date(r[f])
        r["location_fit"] = fit_code(r["location_fit"])
        key = seekter.job_key(r["url"]) or f"{seekter.slug(r['company'])}|{seekter.slug(r['role'])}|{r['applied']}"
        groups.setdefault(key, []).append(r)

    made = 0
    for key, rs in groups.items():
        rs.sort(key=lambda r: RANK[r["status"]], reverse=True)
        top = rs[0]
        notes = [top["notes"]] + [f"(merged row, status {o['status']}) {o['notes']}" for o in rs[1:] if o["notes"]]
        when = top["applied"] or top["updated"] or max((o["applied"] or o["updated"] for o in rs), default="") or seekter.TODAY
        if a.dry_run:
            print(f"{top['status']:<12} {when} {top['company']} | {top['role']}" + (f"  (+{len(rs)-1} merged)" if len(rs) > 1 else ""))
            made += 1
            continue
        meta = dict(company=top["company"], role=top["role"] or "(untitled)", status=top["status"], url=top["url"],
                    source=top["source"], apply_type=top["apply_type"], location_fit=top["location_fit"],
                    remote_scope=top["remote_scope"], fit=top["fit"], posted=top["posted"],
                    applied=top["applied"] if top["status"] not in ("pending", "skipped") else "",
                    updated=top["updated"] or when, job_key=seekter.job_key(top["url"]))
        notes_txt = "\n\n".join(x for x in notes if x)
        if meta["status"] == "skipped":
            meta["notes"] = notes_txt or top["why"]
            seekter.save(meta)
        else:
            seekter.save(meta, seekter.body_for(meta["role"], meta["company"], top["why"], notes_txt,
                                            log=f"- {when}: {top['status']} (imported)"))
        made += 1
    print(f"{len(raw)} rows → {made} files" + (" (dry run)" if a.dry_run else ""))
    if not a.dry_run:
        seekter.cmd_index(None)


if __name__ == "__main__":
    main()
