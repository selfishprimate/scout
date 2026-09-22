# Scout

A job-search agent for Claude Code. It searches job sources every day, filters postings against **your** rules (location, visa, salary, sectors, seniority, language), fills application forms in your own Chrome, and keeps every application and skip as a markdown file you can read, grep and diff.

It was built over a month of daily use by one designer and then emptied of personal data, so it's opinionated where the lessons were expensive: dedup before every form, never guess an answer, never invent an anecdote, never touch a CAPTCHA or a password.

## Quick start

```bash
git clone <this-repo> scout && cd scout
claude            # open Claude Code in the repo
```

Then, inside Claude Code:

```
/scout-init       # ~40 short questions, one at a time. Writes profile/ (git-ignored).
/scout-run        # today's search and applications
```

Requirements: [Claude Code](https://docs.claude.com/en/docs/claude-code), the Claude in Chrome extension (logged in to LinkedIn in that browser), Python 3.9+ and `curl`. No packages.

## Commands

| Command | What it does |
|---|---|
| `/scout-init` | Interviews you and writes your profile: contact details, CVs, target roles, where you can work, salary bands, standard form answers, sectors you won't touch, a fact bank for free-text answers, your writing voice, and the search queries. Resumable. Can import an existing tracker from a Notion/Sheets CSV. |
| `/scout-run` | The daily run. Five sources in a fixed order (freehire API, LinkedIn alert notifications, LinkedIn searches, LinkedIn saved/drafts, other boards), filtering, dedup, form filling, tracker update, and a report with a per-source table. Applies without asking when a posting fits; stops only for things only you can decide. |
| `/scout-log` | Records what happened next: rejections, interviews, offers, applications you made by hand, or a sweep of your inbox. |
| `/scout-report` | Funnel and response rate by source and by location track, top skip reasons, open hand-offs, and at most two suggested changes. |

## The tracker

Every posting Scout touches becomes one file, filed by status:

```
applications/
  README.md                         ← generated index (scripts/scout.py index)
  pending/                          ← needs you: CAPTCHA, account wall, a question only you can answer
  applied/
    2026-09-22--ruby-labs--senior-product-designer.md
  interviewing/  offer/  rejected/  closed/
  skipped/                          ← with the reason, so the same posting is never re-evaluated
```

```markdown
---
company: Ruby Labs
role: Senior Product Designer
status: applied
url: https://jobs.ashbyhq.com/ruby-labs/1e548ada-…
source: freehire
ats: ashby
location_fit: A
applied: 2026-09-22
job_key: uuid:1e548ada-…
---

# Senior Product Designer · Ruby Labs

## Why it fits
## Notes
## Answers submitted      ← free-text answers as sent, so no sentence goes to two companies
## Log
- 2026-09-22: applied
```

`job_key` is a normalised identity (LinkedIn ID, ATS UUID, Greenhouse ID…), so the same job reached through LinkedIn, an aggregator and the company site is still caught as a duplicate.

```bash
python3 scripts/scout.py check <url> --company "Acme"     # exit 1 if already tracked
python3 scripts/scout.py move <url-or-file> rejected --note "form mail, 2 days"
python3 scripts/scout.py list --status pending
python3 scripts/scout.py stats --since 2026-09-01
```

## What's in the repo

```
.claude/skills/     scout-init · scout-run · scout-log · scout-report
reference/          sources.md (how each job source works) · ats-mechanics.md (how each form system behaves)
templates/          profile.md · search.example.json
scripts/            scout.py · freehire_sweep.py · import_notion_csv.py
profile/  applications/  runs/     ← yours, git-ignored
```

`reference/` is the part worth contributing back: every ATS quirk and source behaviour there was measured in real applications.

## Privacy

`profile/`, `applications/` and `runs/` are in `.gitignore`. Your data stays on your machine unless you remove those lines. If you want your tracker versioned, keep it in a separate private repo or remove the ignore lines in a private fork.

## Guardrails

Scout never solves CAPTCHAs, creates accounts, types passwords, accepts terms of use, sends messages or emails as you, posts reviews or salaries, or pays for anything. It treats any instruction found inside a job posting or form as data, and it won't submit an answer it can't verify from your profile.
