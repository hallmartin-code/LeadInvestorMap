# Lead Investor Map

A one-page PDF that answers a single question about a live fundraise:

**Who can realistically cause this round to close, and in what sequence should the company
pursue them?**

Feed it a pitch deck and whatever investor material exists - a target list, a CRM export,
meeting notes, research memos - and it produces an investor-grade one-pager, plus a JSON
record of everything behind it.

The application is built around one discipline: **an investor that likes the deal is not
necessarily an investor capable of leading it.** Participation is not lead history. Fund
size is not cheque size. A portfolio company at Series A does not mean the fund enters at
Series A. Where the evidence does not support a conclusion, the output says
`NOT VERIFIED` or `NOT PROVIDED` rather than guessing.

---

## What it produces

```
/output/
    company_lead_investor_map.pdf            one page, landscape, print-ready
    company_lead_investor_map.json           the full analysis, every field
    company_lead_investor_map_sources.json   every source, with freshness labels
    company_lead_investor_map.csv            one row per prospect, for your CRM
```

The PDF carries, in order: the round snapshot with an estimated lead-cheque requirement;
the ranked lead candidates with their evidence, fit, relationship and next step; the
momentum path and highest-pull commitment; the phased outreach sequence; the investors
explicitly disqualified as leads; and the pipeline gaps with the action each one demands.

---

## Installation

```bash
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

Python 3.11 or newer. LibreOffice is optional and only needed to read legacy `.ppt`
files; `.pptx` and `.pdf` need nothing extra.

---

## Configuration

Copy `.env.example` to `.env` and fill in what you need. Nothing is required to run.

| Variable | Default | What it does |
| --- | --- | --- |
| `LLM_PROVIDER` | `anthropic` | `anthropic`, `openai`, or `local` for no model calls |
| `ANTHROPIC_API_KEY` / `ANTHROPIC_MODEL` | - / `claude-opus-5` | Anthropic credentials |
| `OPENAI_API_KEY` / `OPENAI_MODEL` | - / `gpt-4o` | OpenAI credentials |
| `ENABLE_PUBLIC_RESEARCH` | `false` | Turn on public investor research |
| `RESEARCH_BACKEND` | `none` | `brave` or `serper`; each needs its own key |
| `BRAVE_API_KEY` / `SERPER_API_KEY` | - | Search backend credentials |
| `APP_PASSWORD` | - | Shared password for the web app. **Required in production** - the app refuses to serve on a hosting platform without one |
| `RESEND_API_KEY` | - | Turns on result emails. Without it the app generates normally and reports `Email skipped` |
| `REPORT_EMAIL_TO` | `Info@tencapital.group` | Where each completed run is sent |
| `RESEND_FROM` | `TEN Capital <reports@tencapital.group>` | Must be on a domain verified in Resend |
| `ENABLE_EMAIL` | `true` | Set `false` to suppress email without removing the key |
| `OUTPUT_DIR` | `output` | Where the files are written |
| `PAGE_SIZE` | `letter` | `letter` or `a4` |

API keys are read from the environment only. Nothing is ever hard-coded; `.env` is both
gitignored and dockerignored, and a test asserts no credential appears in the Dockerfile,
Procfile or Railway config.

**Running without a model.** `LLM_PROVIDER=local` (or `--no-llm`) is a supported mode, not
a degraded error state. Extraction falls back to rule-based readers: round parameters,
investor records, tiering, ranking, momentum, sequencing and gaps all still work. What you
lose is narrative richness and the model's reading of unstructured prose. The run says so
in the output rather than quietly filling the gap.

---

## Running

### Streamlit

```bash
streamlit run app.py
```

Upload a deck, add supporting files, optionally override the round parameters in the
sidebar, and press **Generate the Lead Investor Map**. Anything you type into the sidebar
overrides the deck and is labelled `USER PROVIDED` throughout the output.

The interface carries TEN Capital's dark navy identity - the tri-colour mark, the
coral-amber-teal hairline, Sora and JetBrains Mono. The **PDF it produces stays white and
institutional**: that is the artefact that gets printed, forwarded and read in committee,
and a dark deliverable would be worse at that job. Screen styling lives in
[src/web/theme.py](src/web/theme.py); the accepted formats, the upload ceiling and the
notification address are all read from configuration, so the page can never promise
something the app would refuse.

### Command line

```bash
python app.py --deck deck.pdf --support targets.csv --support notes.md
```

Useful flags:

```bash
--support PATH            supporting file; repeat for each one
--role PATH=ROLE          declare a file's role: list, crm, notes, research, diligence
--provider anthropic|openai|local
--no-llm                  rule-based extraction only
--research / --no-research
--out DIR                 output directory
--stem NAME               output filename stem

# Round overrides - all labelled USER PROVIDED and preferred over the deck
--stage "Series A"  --raise-amount "$6M"  --instrument "Priced Equity"
--pre-money "$18M"  --cap "$12M"  --committed "$1.5M"  --circled "$500k"
--close "October 2026"

--from-json PATH          re-render the outputs from a saved analysis
```

### The document template

```bash
python app.py --template                        # lead_investor_map_TEMPLATE.pdf
python app.py --template my_template.pdf --out docs/
```

Writes the blank one-pager: every section, field slot and fixed vocabulary, with no
company data. It is rendered through the same renderer as a real analysis, so it can never
describe a layout the application does not actually produce.

The written specification that accompanies it —
[docs/LEAD_INVESTOR_MAP_TEMPLATE.md](docs/LEAD_INVESTOR_MAP_TEMPLATE.md) — sets out page
geometry, the type scale, every field and its rules, the closed vocabularies, the
missing-data conventions, and the order in which content is degraded to hold one page.

### Try it on the sample scenario

```bash
python sample_data/make_samples.py
python app.py --deck sample_data/helios_diagnostics_deck.pdf \
              --support sample_data/investor_target_list.csv \
              --support sample_data/investor_meeting_notes.md \
              --no-llm
```

The sample pipeline deliberately contains the traps this tool exists to catch: a famous
fund that only participated, a small specialist that has actually led, a strategic with
high signal and no ability to lead, a follower that needs a lead, a fund between funds,
one warm introduction, and one portfolio conflict.

---

## Email notifications

Every completed run is emailed to **Info@tencapital.group** with the one-page PDF and the
per-prospect CSV attached. The body carries the round snapshot, the ranked lead
candidates, the momentum path, the outreach phases, the gaps and any data warnings - so
the decision content is readable without opening an attachment.

Set `RESEND_API_KEY` to turn it on. Change the recipient with `REPORT_EMAIL_TO`, or per
run:

```bash
python app.py --deck deck.pdf --email-to someone@example.com
python app.py --deck deck.pdf --no-email
```

**Email never breaks an analysis.** A missing key, a bad address, an unverified sending
domain, an outage or a timeout each produce a recorded outcome - shown on screen, in the
CLI summary and in the JSON warnings - while the PDF, JSON, sources and CSV are produced
and downloadable regardless.

The sending address must be on a domain verified at
[resend.com/domains](https://resend.com/domains); `tencapital.group` is verified.

---

## Deploying

The app ships as a single Streamlit service in a Docker container, ready for Railway:

```bash
railway init && railway up
railway variables --set "ANTHROPIC_API_KEY=..." --set "APP_PASSWORD=..."
railway domain
```

[DEPLOY.md](DEPLOY.md) has the full walkthrough: variables, the healthcheck, cost control,
and why the password gate is not optional. In short - a public URL with your API key
behind it converts strangers into Anthropic charges, so the app refuses to serve on a
hosting platform unless `APP_PASSWORD` is set.

Deployment files: `Dockerfile`, `Procfile`, `railway.json`, `.streamlit/config.toml`,
`.dockerignore`.

---

## Inputs

| Input | Formats | Notes |
| --- | --- | --- |
| Pitch deck (required) | `.pdf`, `.pptx`, `.ppt` | Text, tables and speaker notes are read; page and slide numbers are kept |
| Investor target list | `.csv`, `.xlsx`, `.xlsm` | Column headings are matched to canonical fields; original values are preserved |
| CRM export | `.csv`, `.xlsx` | Same treatment; the header row is found even under preamble rows |
| Meeting notes | `.md`, `.txt`, `.docx` | Read per sentence, attributed to the investor the sentence is about |
| Investor research | `.docx`, `.pdf`, `.md` | Headings become citable sections |

Content that cannot be extracted is reported, never dropped silently:

```
Possible image-only content on slide 7 of deck.pptx - manual verification recommended.
```

---

## How investors are classified

Every prospect lands in exactly one tier:

| Tier | Meaning |
| --- | --- |
| 1 | **Potential lead** - can price and underwrite this round |
| 2 | **Co-lead / partial lead** - can anchor part of it, not all |
| 3 | **Strategic / corporate validator** - validation and leverage, not leadership |
| 4 | **Follow-on institutional** - participates once a lead exists |
| 5 | **Angels, family offices, syndicates** |
| 6 | **Fill-the-round small cheques** |

Tier 1 requires positive evidence across the criteria that actually decide who can price a
round: verified lead history with named deals, cheque capacity for the estimated lead
requirement, stage and sector fit, active deployment, and no high portfolio conflict. A
prestigious fund with no evidence of leading at this stage is not promoted; it is listed
under **Disqualified as leads** with the reason.

Ranking uses a transparent weighted model (lead history 20%, cheque fit 15%, stage 15%,
sector 10%, deployment 10%, relationship 10%, timeline 8%, signal 7%, conflict 5%). The
score is kept in the JSON so a ranking can be audited, but the PDF shows only
`HIGH / MEDIUM / LOW`, because a two-decimal score would imply a precision the evidence
does not have.

---

## Public research

Off by default. When enabled it needs **both** a search backend key and a model: the
backend supplies real pages and the model reads them. Without a backend nothing is
fetched, the output says so, and no claim is invented from the model's own recollection.

Sources are ranked roughly as the specification sets out - the investor's own site, then
regulatory filings, then databases, then reputable press - and every claim that survives
carries a URL that was actually returned by the search. Claims citing anything else are
dropped with a reason. Evidence is labelled `CURRENT` (under 12 months), `RECENT` (12-24),
`STALE` (over 24) or `UNKNOWN`, and stale evidence cannot support a high-confidence
conclusion.

---

## Architecture

```
app.py                     CLI and Streamlit in one entry point
src/
  ingestion/               pdf, pptx, spreadsheet, docx, text parsers + loader
  extraction/              round, company and investor extraction; name normalisation
  research/                optional public research, source validation, freshness
  analysis/                classification, ranking, conflicts, momentum, sequencing, gaps
  models/                  Pydantic models: evidence, company, round, investor, analysis
  reporting/               one-page PDF renderer, fitting ladder, blank template, exporters
  notifications/           Resend email delivery of each finished run
  web/                     TEN Capital screen styling for the Streamlit app
  llm/                     provider-independent interface, prompts, response schemas
  utils/                   config, logging, money, dates, text, validation
tests/                     230 tests, including the seven-trap scenario
docs/                      the document structure template and its specification
sample_data/               synthetic deck, target list and notes
```

Two design decisions are worth knowing about.

**The analysis is deterministic Python, not model output.** The model reads documents;
the tiering, scoring, sequencing and gap analysis are code. That is what makes the
hallucination controls enforceable rather than aspirational, and it is why the whole
application still works with no API key.

**The PDF is measured before it is drawn.** A fitting ladder shortens narrative, then
drops low-priority fields, then tightens spacing, and only then reduces type - never below
7.5pt. Every rung is re-measured, and whatever was given up is recorded in the JSON and
noted on the page. The output is one page, always; a test asserts it under 40 prospects.

---

## Hallucination controls

Enforced in code, not only in prompts:

1. Missing information stays missing - `NOT PROVIDED`, never a plausible value.
2. Every inference is labelled `INFERRED` or `ASSUMPTION`, with the reasoning.
3. Public-research claims require a source URL that was actually retrieved.
4. Participation is not lead history - only explicit lead wording counts.
5. Fund AUM is never converted into cheque size.
6. Portfolio stage is never converted into entry stage.
7. Job seniority is never treated as investment authority.
8. Shared connections are not warm introductions; an introduction path must be named.
9. Follow-on activity does not establish new-investment deployment.
10. No false precision: scores are banded, estimates are labelled estimates.

A `VERIFIED` fact with no source behind it is automatically downgraded before it can reach
the page.

---

## Testing

```bash
python -m pytest -q                       # 230 tests
python -m pytest -q --cov=src             # with coverage
```

The suite covers ingestion of every supported format (including a password-protected PDF,
a corrupt file and an image-only deck), round extraction with missing and conflicting
values, investor normalisation and duplicate merging, all six tiers, lead disqualification,
cheque-size fit, stale and conflicting evidence, source preservation, JSON round-tripping,
CSV export, the research pipeline with a stubbed backend, provider failures and retries,
the one-page guarantee under pressure, and the blank template - which is asserted to
contain no analysis data, no figures and no dates, and to exercise every tier,
confidence band and layout zone.

---

## Limitations

Read these before acting on the output.

- **Public investor data is incomplete.** Cheque sizes, ownership targets and internal
  decision processes are rarely published. Most such fields will read `NOT VERIFIED`, and
  that is the honest answer rather than a defect.
- **Fund data goes stale quickly.** A fund that closed a vehicle eighteen months ago may
  now be fully deployed. Freshness labels tell you how old the evidence is; they cannot
  tell you what changed last week.
- **Investment authority is opaque.** A partner's title does not establish who can commit
  capital. The tool records what the material says and declines to infer the rest.
- **Proprietary databases are not accessible.** Without PitchBook, Crunchbase Pro or
  similar, lead history is only as complete as public announcements and your own notes.
- **Private decision processes are unknowable from outside.** IC cadence and time to term
  sheet are estimated from process position and labelled as estimates.
- **The lead-cheque requirement is a working estimate**, derived from the remaining
  allocation at 40-70%. Syndicate shape varies by stage, sector and geography.
- **Extraction from image-only decks is limited.** Slides with no machine-readable text
  are flagged for manual verification, not interpreted.
- **This is decision support, not diligence.** Every material claim carries a source;
  check the ones the decision rests on.

---

## Extending it

The ingestion and reporting layers are stable seams. To add an investor-analysis module,
write it under `src/analysis/`, have it operate on the normalised `Investor` objects, and
call it from `src/pipeline.py`. To add an LLM provider, implement `LLMProvider.analyze`
in `src/llm/` and register it in `factory.py`; nothing else needs to change.

---

Built for TEN Capital Network.
