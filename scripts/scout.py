#!/usr/bin/env python3
"""Scout tracker CLI. Applications are markdown files with a small front matter,
filed by status under applications/<status>/. Standard library only.

  python3 scripts/scout.py check <url> [--company NAME]
  printf 'url | company\n4468710729\n' | python3 scripts/scout.py check-many   (bare numbers = LinkedIn IDs)
  python3 scripts/scout.py add --company X --role Y --status applied --url U [...]
  python3 scripts/scout.py move <file|url> <status> [--note TEXT]
  python3 scripts/scout.py list [--status S] [--since YYYY-MM-DD]
  python3 scripts/scout.py index
  python3 scripts/scout.py normalize [--dry-run]
  python3 scripts/scout.py stats [--since YYYY-MM-DD]
"""
import argparse, datetime as dt, json, os, re, sys, unicodedata
from pathlib import Path
from urllib.parse import urlparse, parse_qs

ROOT = Path(__file__).resolve().parent.parent
APPS = ROOT / "applications"
STATUSES = ["pending", "applied", "interviewing", "offer", "rejected", "closed", "skipped"]
FIELDS = ["company", "role", "status", "url", "source", "ats", "apply_type", "location_fit",
          "remote_scope", "fit", "posted", "applied", "updated", "job_key"]
TODAY = dt.date.today().isoformat()

UUID = r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"


# ---------- job identity ----------
def job_key(url: str) -> str:
    """Stable identity for a posting, so the same job reached through different URLs matches."""
    if not url:
        return ""
    u = url.strip()
    p = urlparse(u if "://" in u else "https://" + u)
    host = p.netloc.lower().removeprefix("www.")
    q = parse_qs(p.query)
    path = p.path
    m = re.search(r"/jobs/view/(\d+)", path)
    if "linkedin.com" in host and m:
        return f"linkedin:{m.group(1)}"
    if "linkedin.com" in host and "currentJobId" in q:
        return f"linkedin:{q['currentJobId'][0]}"
    for k in ("gh_jid", "token"):
        if k in q and q[k][0].isdigit():
            return f"greenhouse:{q[k][0]}"
    if "ats_id" in q:
        return f"ats:{q['ats_id'][0].lower()}"
    m = re.search(UUID, path, re.I)
    if m:
        return f"uuid:{m.group(0).lower()}"
    if "greenhouse" in host:
        m = re.search(r"/jobs/(\d+)", path)
        if m:
            return f"greenhouse:{m.group(1)}"
    m = re.search(r"/(\d{7,})(?:[-/]|$)", path)
    if m:
        return f"{host}:{m.group(1)}"
    path = re.sub(r"/(application|apply|apply/)?$", "", path.rstrip("/"))
    return f"{host}{path}".lower()


ATS_HOSTS = [
    ("ashbyhq.com", "ashby"), ("greenhouse.io", "greenhouse"), ("lever.co", "lever"),
    ("myworkdayjobs.com", "workday"), ("workable.com", "workable"), ("recruitee.com", "recruitee"),
    ("personio.", "personio"), ("teamtailor.com", "teamtailor"), ("smartrecruiters.com", "smartrecruiters"),
    ("bamboohr.com", "bamboohr"), ("pinpointhq.com", "pinpoint"), ("breezy.hr", "breezy"),
    ("rippling.com", "rippling"), ("icims.com", "icims"), ("taleo.net", "taleo"), ("join.com", "join"),
    ("homerun.co", "homerun"), ("hire.trakstar.com", "trakstar"), ("jobylon.com", "jobylon"),
    ("hr-on.com", "hr-on"), ("dayforcehcm.com", "dayforce"), ("successfactors", "successfactors"),
    ("docs.google.com/forms", "google-forms"), ("forms.gle", "google-forms"),
    ("linkedin.com", "linkedin"), ("djinni.co", "djinni"),
]
# Values that are an application system, not a place the posting was found.
ATS_NAMES = {v for _, v in ATS_HOSTS} - {"linkedin", "djinni"}


def ats_from_url(url: str) -> str:
    u = (url or "").lower()
    for host, name in ATS_HOSTS:
        if host in u:
            return name
    return ""


def norm(v: str) -> str:
    """'Company site' -> 'company-site', 'Other board' -> 'other-board'."""
    return re.sub(r"[^a-z0-9]+", "-", (v or "").strip().lower()).strip("-")


def slug(s: str, n: int = 40) -> str:
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode()
    s = re.sub(r"[^a-zA-Z0-9]+", "-", s).strip("-").lower()
    return s[:n].rstrip("-") or "x"


# ---------- file io ----------
def read(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    meta, body = {}, text
    if text.startswith("---\n"):
        end = text.find("\n---", 4)
        if end != -1:
            for line in text[4:end].splitlines():
                if ":" in line:
                    k, v = line.split(":", 1)
                    meta[k.strip()] = v.strip()
            body = text[end + 4:].lstrip("\n")
    meta["_path"] = path
    meta["_body"] = body
    return meta


def write(path: Path, meta: dict, body: str) -> None:
    lines = ["---"]
    for k in FIELDS:
        if meta.get(k) not in (None, ""):
            lines.append(f"{k}: {str(meta[k]).replace(chr(10), ' ')}")
    for k, v in meta.items():
        if k not in FIELDS and not k.startswith("_") and v not in (None, ""):
            lines.append(f"{k}: {str(v).replace(chr(10), ' ')}")
    lines.append("---")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n\n" + body.rstrip() + "\n", encoding="utf-8")


def all_apps():
    for st in STATUSES:
        d = APPS / st
        if d.is_dir():
            for f in sorted(d.glob("*.md")):
                yield read(f)


def find(target: str):
    p = Path(target)
    if p.exists():
        return read(p)
    key = job_key(target)
    for a in all_apps():
        if a.get("job_key") == key or job_key(a.get("url", "")) == key:
            return a
    return None


# ---------- commands ----------
def cmd_check(a):
    key = job_key(a.url)
    same, company = [], []
    for r in all_apps():
        if key and (r.get("job_key") == key or job_key(r.get("url", "")) == key):
            same.append(r)
        elif a.company and slug(a.company) in slug(r.get("company", ""), 80):
            company.append(r)
    if same:
        print("DUPLICATE: this posting is already tracked")
        for r in same:
            print(f"  {r.get('status')} | {r.get('company')} | {r.get('role')} | {r['_path'].relative_to(ROOT)}")
        sys.exit(1)
    print(f"NEW  key={key}")
    for r in company:
        print(f"  same company, other role: {r.get('status')} | {r.get('role')} | {r.get('applied') or r.get('updated')}")


def cmd_check_many(a):
    """stdin: one posting per line, 'url' or 'url | company'. Prints NEW / DUP / SAMECO per line."""
    apps = list(all_apps())
    keys = {r.get("job_key") or job_key(r.get("url", "")): r for r in apps}
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        url, _, co = (x.strip() for x in line.partition("|"))
        if url.isdigit():
            url = f"https://www.linkedin.com/jobs/view/{url}/"
        r = keys.get(job_key(url))
        if r:
            print(f"DUP    {line} -> {r.get('status')} {r['_path'].name}")
            continue
        same = [x for x in apps if co and slug(co) in slug(x.get("company", ""), 80)]
        print(("SAMECO " if same else "NEW    ") + line + (f" -> {len(same)} earlier: " + ", ".join(f"{x.get('status')}:{x.get('role')}" for x in same[:3]) if same else ""))


def cmd_add(a):
    if a.status not in STATUSES:
        sys.exit(f"status must be one of {STATUSES}")
    key = job_key(a.url or "")
    if key and not a.force:
        for r in all_apps():
            if r.get("job_key") == key:
                sys.exit(f"DUPLICATE: {r['_path'].relative_to(ROOT)} (use --force to add anyway)")
    date = a.applied or a.date or TODAY
    name = f"{date}--{slug(a.company, 30)}--{slug(a.role, 40)}.md"
    path = APPS / a.status / name
    i = 2
    while path.exists():
        path = APPS / a.status / name.replace(".md", f"-{i}.md")
        i += 1
    meta = dict(company=a.company, role=a.role, status=a.status, url=a.url, source=norm(a.source),
                ats=norm(a.ats) or ats_from_url(a.url), apply_type=norm(a.apply_type), location_fit=a.location_fit,
                remote_scope=a.remote_scope, fit=a.fit, posted=a.posted,
                applied=a.applied or (TODAY if a.status == "applied" else ""),
                updated=a.date or TODAY, job_key=key)
    body = f"# {a.role} · {a.company}\n\n"
    body += "## Why it fits\n\n" + (a.why or "") + "\n\n"
    body += "## Notes\n\n" + (a.notes or "") + "\n\n"
    body += "## Answers submitted\n\n" + (a.answers or "") + "\n\n"
    body += "## Log\n\n" + f"- {a.date or TODAY}: {a.status}" + (f". {a.log}" if a.log else "") + "\n"
    write(path, meta, body)
    print(path.relative_to(ROOT))


def cmd_move(a):
    if a.status not in STATUSES:
        sys.exit(f"status must be one of {STATUSES}")
    r = find(a.target)
    if not r:
        sys.exit("not found")
    old = r["_path"]
    body = r.pop("_body")
    r.pop("_path")
    r["status"] = a.status
    r["updated"] = TODAY
    if a.status == "applied" and not r.get("applied"):
        r["applied"] = TODAY
    if "## Log" not in body:
        body += "\n## Log\n"
    body = body.rstrip() + f"\n- {TODAY}: {a.status}" + (f". {a.note}" if a.note else "") + "\n"
    new = APPS / a.status / old.name
    write(new, r, body)
    if new != old:
        old.unlink()
    print(new.relative_to(ROOT))


def rows(since=None, status=None):
    out = []
    for r in all_apps():
        d = r.get("applied") or r.get("updated") or ""
        if since and d < since:
            continue
        if status and r.get("status") != status:
            continue
        out.append(r)
    out.sort(key=lambda r: (r.get("applied") or r.get("updated") or ""), reverse=True)
    return out


def cmd_list(a):
    for r in rows(a.since, a.status):
        print(f"{r.get('applied') or r.get('updated')} | {r.get('status'):<12} | {r.get('company')} | {r.get('role')} | {r.get('url','')}")


def cmd_stats(a):
    rs = rows(a.since)
    c = {s: 0 for s in STATUSES}
    for r in rs:
        c[r.get("status", "pending")] = c.get(r.get("status", "pending"), 0) + 1
    sent = sum(c[s] for s in ("applied", "interviewing", "offer", "rejected", "closed"))
    print(json.dumps({"total": len(rs), "sent": sent, **c,
                      "response_rate": round((c["interviewing"] + c["offer"] + c["rejected"]) / sent, 3) if sent else None},
                     indent=1))


def fix_meta(r: dict) -> dict:
    """Normalise one record: lowercase-hyphen enums, ATS derived from the URL,
    and an ATS name misfiled as `source` moved to `ats`."""
    before = {k: r.get(k, "") for k in ("source", "ats", "apply_type", "job_key")}
    src, ats = norm(r.get("source")), norm(r.get("ats"))
    if src == "other-board":
        src = "board"
    if src in ATS_NAMES:
        ats = ats or src
        src = "board"  # the tracker only knew the form system, not where the posting was found
    r["source"] = src
    r["ats"] = ats or ats_from_url(r.get("url", ""))
    r["apply_type"] = norm(r.get("apply_type"))
    if r.get("url") and not r.get("job_key"):
        r["job_key"] = job_key(r["url"])
    return {k: (before[k], r.get(k, "")) for k in before if before[k] != r.get(k, "")}


def cmd_normalize(a):
    changed = 0
    for r in all_apps():
        path, body = r.pop("_path"), r.pop("_body")
        diff = fix_meta(r)
        if diff:
            changed += 1
            if not a.dry_run:
                write(path, r, body)
    print(f"{changed} files {'would change' if a.dry_run else 'normalised'}")


def cmd_index(a):
    rs = rows()
    c = {s: sum(1 for r in rs if r.get("status") == s) for s in STATUSES}
    lines = ["# Applications", "", f"Generated by `scripts/scout.py index` on {TODAY}. Don't edit by hand.", "",
             " · ".join(f"**{s}** {c[s]}" for s in STATUSES), ""]
    for s in STATUSES:
        sub = [r for r in rs if r.get("status") == s]
        if not sub:
            continue
        lines += [f"## {s.capitalize()} ({len(sub)})", "", "| Date | Company | Role | Fit | Link |", "|---|---|---|---|---|"]
        for r in sub:
            rel = r["_path"].relative_to(APPS).as_posix()
            lines.append(f"| {r.get('applied') or r.get('updated','')} | {r.get('company','')} | "
                         f"[{r.get('role','')}]({rel}) | {r.get('location_fit','')} | "
                         f"{'[posting](' + r['url'] + ')' if r.get('url') else ''} |")
        lines.append("")
    (APPS / "README.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"applications/README.md ({len(rs)} rows)")


def main():
    ap = argparse.ArgumentParser(description="Scout tracker")
    sp = ap.add_subparsers(dest="cmd", required=True)
    c = sp.add_parser("check"); c.add_argument("url"); c.add_argument("--company")
    c.set_defaults(fn=cmd_check)
    cm = sp.add_parser("check-many"); cm.set_defaults(fn=cmd_check_many)
    ad = sp.add_parser("add")
    for f in ("company", "role", "url"):
        ad.add_argument("--" + f, required=f != "url", default="")
    ad.add_argument("--status", default="applied")
    for f in ("source", "ats", "apply-type", "location-fit", "remote-scope", "fit", "posted", "applied",
              "date", "why", "notes", "answers", "log"):
        ad.add_argument("--" + f, default="")
    ad.add_argument("--force", action="store_true")
    ad.set_defaults(fn=cmd_add)
    mv = sp.add_parser("move"); mv.add_argument("target"); mv.add_argument("status"); mv.add_argument("--note", default="")
    mv.set_defaults(fn=cmd_move)
    ls = sp.add_parser("list"); ls.add_argument("--status"); ls.add_argument("--since"); ls.set_defaults(fn=cmd_list)
    ix = sp.add_parser("index"); ix.set_defaults(fn=cmd_index)
    nm = sp.add_parser("normalize", help="lowercase enums, derive ats from url, fix ats-in-source")
    nm.add_argument("--dry-run", action="store_true"); nm.set_defaults(fn=cmd_normalize)
    st = sp.add_parser("stats"); st.add_argument("--since"); st.set_defaults(fn=cmd_stats)
    a = ap.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
