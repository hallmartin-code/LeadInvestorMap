# Lead Investor Map — Document Structure Template

The canonical structure of every Lead Investor Map the application produces. It defines
the page geometry, the sections and their order, every field slot, the fixed vocabulary
each slot may draw from, and the rules that govern what may and may not appear.

No company, investor, round or figure from any analysis appears here. Slots are written
as `[FIELD NAME]`.

**The rendered counterpart of this document** is produced by the application itself:

```bash
python app.py --template                      # writes lead_investor_map_TEMPLATE.pdf
python app.py --template my_template.pdf --out docs/
```

It is built by [`src/reporting/template.py`](../src/reporting/template.py) and rendered
through the ordinary renderer, so the template can never describe a layout the
application does not actually emit. When the layout changes, the template changes with it.

---

## 1. Page

| Property | Value |
| --- | --- |
| Page size | US Letter landscape (792 × 612 pt); A4 landscape when `PAGE_SIZE=a4` |
| Page count | Exactly 1, always — enforced by the fitting ladder and asserted in tests |
| Margin | 26 pt all round |
| Content width | 740 pt (Letter) |
| Background | White; no images, no charts, no decorative elements |
| Colour role | Emphasis only — every status is also carried by a word, so the page reads in greyscale |

### Type scale

| Element | Size | Weight |
| --- | --- | --- |
| Company name (header) | 16 pt | Bold |
| Product name, date | 9 pt | Regular |
| Section labels | 8.5 pt | Bold, upper case, navy, hairline rule beneath |
| Body / table cells | 8.0 pt (floor 7.5 pt) | Regular |
| Table headers | 6.6 pt | Bold, muted |
| Tile labels | 6.2 pt | Bold, muted, upper case |
| Tile values | 10 pt (auto-shrinks to fit, floor 6.5 pt) | Bold |
| Micro text, footnotes | 6.4–6.6 pt | Regular, muted |

Body text is never reduced below **7.5 pt**. If content will not fit at that size, content
is dropped — the type floor is not negotiable.

---

## 2. Section order

```
┌──────────────────────────────────────────────────────────────────────────────┐
│ 1  HEADER                    company · product · date · evidence summary     │
├──────────────────────────────────────────────────────────────────────────────┤
│ 2  ROUND SNAPSHOT            8 tiles, full width                             │
├──────────────────────────────────────────────────────────────────────────────┤
│ 3  LEAD CANDIDATES           ranked table, full width + case-for line        │
├──────────────────────────────────────────────────────────────────────────────┤
│ 4  MOMENTUM PATH │ OUTREACH SEQUENCE │ DISQUALIFIED AS LEADS   (3 columns)   │
├──────────────────────────────────────────────────────────────────────────────┤
│ 5  GAPS / RISKS AND REQUIRED ACTION  (+ FALLBACK STRUCTURES when relevant)   │
├──────────────────────────────────────────────────────────────────────────────┤
│ 6  FOOTER                    sourcing statement · inputs · warnings          │
└──────────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Header

| Slot | Content | Rule |
| --- | --- | --- |
| `[COMPANY NAME]` | Upper case, bold, 16 pt | Truncated to 50% of content width. `COMPANY NOT IDENTIFIED` when the deck yields no name |
| `LEAD INVESTOR MAP` | Fixed product name, accent colour | Never changes |
| `[YYYY-MM-DD]` | Generation date, right-aligned | Always the run date; never hard-coded |
| `[ONE-LINE DESCRIPTION OF THE BUSINESS]` | Max ~140 characters | Falls back to `Company summary NOT PROVIDED in the supplied materials` |
| Evidence summary | `N prospects │ N lead-qualified │ documents only` | Right-aligned. Last term is `public research ON` when research ran |

A 1 pt navy rule closes the header.

---

## 4. Round snapshot

Eight equal tiles, left to right. Each carries a label, a value, and a provenance note.

| # | Tile | Value slot | Provenance note |
| --- | --- | --- | --- |
| 1 | STAGE | `[STAGE]` | `deck p./sl. N`, or the status term |
| 2 | RAISE | `[$ RAISE]` | `deck p./sl. N` |
| 3 | INSTRUMENT | `[INSTRUMENT]` | `deck p./sl. N` |
| 4 | VALUATION | `Pre [$…]` / `Cap [$…]` / `Post [$…]` | `deck p./sl. N` |
| 5 | COMMITTED | `[$ COMMITTED]` | `deck p./sl. N` |
| 6 | REMAINING | `[$ REMAINING]` | `derived` — always, it is computed |
| 7 | TARGET CLOSE | `[TARGET CLOSE]` | `deck p./sl. N` |
| 8 | **LEAD CHECK REQUIRED** | `[$ MIN-$ MAX]` | `ESTIMATED` — tinted, the only emphasised tile |

**Rules**

- A value that was not established reads `NOT PROVIDED`. Tiles are never left blank.
- The provenance note carries the evidence status when the value is not `VERIFIED`:
  `user provided`, `inferred`, `unverified`, `conflicting`.
- Tile 6 is derived (raise − committed) and always says so.
- Tile 8 is an estimate (40–70% of the remaining allocation) and always says so. It reads
  `insufficient data` when the round size was never established.

---

## 5. Lead candidates

The ranked shortlist: **5–8 rows when that many clear the bar, and fewer when they do
not.** The list is never padded.

| Column | Width | Slot | Vocabulary / rule |
| --- | --- | --- | --- |
| # | 2.2% | `1`–`8` | Rank order |
| INVESTOR | 13% | `[INVESTOR NAME]` | Bold |
| TIER | 6.8% | `T1 LEAD` / `T2 CO-LEAD` | Only tiers 1 and 2 appear here |
| LEAD CONF | 5.6% | `HIGH` / `MEDIUM` / `LOW` | Band only — the numeric score is never printed |
| CHECK | 8.2% | `[$ MIN-$ MAX]` | `NOT VERIFIED` when no cheque size was established |
| LEAD EVIDENCE | 16.8% | `[CO. - ROUND - ROLE - YEAR]` | `NOT VERIFIED`, or `Says it leads; NOT VERIFIED` |
| FIT STAGE/SECTOR | 9% | `Strong` / `Partial` / `Weak` / `Mismatch` / `Unknown`, paired | Assessed separately, printed together |
| RELATIONSHIP | 7.6% | See the relationship vocabulary below | Short form |
| KEY DEPENDENCY | 14% | `[DEPENDENCY]` | Falls back to the condition for commitment |
| NEXT STEP (OWNER) | 16.8% | `[ACTION] ([OWNER])` | Exactly one action per investor |

Beneath the table, one italic line carries the case for the top candidate:

```
#1 [INVESTOR]: [WHY THEY CAN LEAD] [WHY THEY FIT] Obstacle: [KEY OBSTACLE]
```

**When the shortlist is empty**, the table is replaced by a single statement that no
prospect meets the lead standard — naming the five criteria — and pointing to the fallback
structures below. The section is never simply blank.

---

## 6. Momentum path (column 1 of 3)

```
Highest pull: [INVESTOR] ([HIGH | MEDIUM | LOW | INSUFFICIENT EVIDENCE] confidence)
[WHY THIS COMMITMENT MOVES THE ROUND]

[INVESTOR] commits as lead
> [INVESTOR] enters diligence
> [INVESTOR] validates the sector
> [INVESTOR, INVESTOR] fill remaining allocation

Downstream (state they need a lead): [INVESTOR], [INVESTOR]
```

**Rules**

- Every name must be a prospect from the supplied materials.
- The anchor's event term matches its tier: `commits as lead` (T1), `commits as co-lead`
  (T2), `commits as strategic anchor` (T3). A strategic is never described as leading.
- Downstream names appear only where that investor's *own* material states a dependency on
  a lead. Influence is never asserted from reputation.
- With no evidence-supported chain, the section says so in one sentence.

---

## 7. Outreach sequence (column 2 of 3)

Five phases, always in this order, always all five present:

| Label | Phase | Objective |
| --- | --- | --- |
| `NOW` | Phase 1 — calibration | Test the narrative on conversations the round can afford to lose |
| `NEXT` | Phase 2 — lead conversion | Partner meetings and a competitive process for the lead |
| `ON MOMENTUM` | Phase 3 — signal leverage | Strategics and followers, once lead momentum exists |
| `COMPLETION` | Phase 4 — round completion | Angels, family offices, syndicates, small cheques |
| `HOLD BACK` | — | Prospects where contact now is counterproductive |

Each line lists up to 5 names, then `(+N)`. An empty phase reads `none identified`.

---

## 8. Disqualified as leads (column 3 of 3)

```
[INVESTOR NAME] - [REASON], [REASON]
+N further prospect(s) - see companion JSON.
```

Up to 7 entries, ordered by how likely the reader is to over-rate them (institutions
first). Tier 1 and Tier 2 investors never appear here — they are in the candidate table
with their obstacle stated there.

**Reason vocabulary** (at most two shown per investor):

`NO VERIFIED LEAD HISTORY` · `CHECK TOO SMALL` · `REQUIRES EXISTING LEAD` · `WRONG STAGE` ·
`WRONG SECTOR` · `PORTFOLIO CONFLICT` · `INACTIVE FUND` · `BETWEEN FUNDS` ·
`FOLLOW-ON ONLY` · `TIMELINE TOO LONG` · `RELATIONSHIP TOO COLD` · `STRATEGIC ONLY` ·
`PASSED ON THE ROUND`

---

## 9. Gaps, risks and required action

Four columns: **GAP / RISK · CONSEQUENCE · REQUIRED ACTION · SEV**.

| Row type | Content | SEV |
| --- | --- | --- |
| Pipeline gap | `[GAP]` · `[CONSEQUENCE]` · `[CATEGORY TO ADD, OR ACTION]` | `HIGH` / `MED` / `LOW` |
| Fallback structure | `Fallback: [STRUCTURE] ([VIABILITY])` · `Risk: [PRIMARY RISK]` · `Needs [$ CAPITAL]. [MILESTONE]` | `ALT` |
| Company objection | `Likely objection: [OBJECTION]` · `[EVIDENCE]` · `Prepare a direct answer before phase 2 outreach.` | Objection severity |

**Rules**

- Every gap states its consequence. An observation without a consequence is not a gap.
- Fallback rows appear **only when no credible lead was identified**, and the section
  heading then extends to `… | FALLBACK STRUCTURES IF NO LEAD EMERGES`.
- The objection row is company-specific and evidence-backed. An objection with no evidence
  is dropped rather than printed.

---

## 10. Footer

```
Sources: company-provided materials and cited public information.        Generated [YYYY-MM-DD] by TEN Capital Network
Unverified or inferred information is explicitly labelled.
Inputs: [FILENAME], [FILENAME], [FILENAME] (+N)                          [N data warning(s) - see companion JSON | No data warnings]
```

`| content trimmed to fit one page` is appended to the right-hand note when the fitting
ladder could not fit everything.

---

## 11. Fixed vocabularies

Slots that draw from a closed list. An analysis may print one of these terms and nothing
else.

**Tier** — `T1 LEAD` · `T2 CO-LEAD` · `T3 STRATEGIC` · `T4 FOLLOW` · `T5 ANGEL/FO` ·
`T6 FILL`

**Lead confidence** — `HIGH` · `MEDIUM` · `LOW` · `NOT A LEAD`

**Relationship** (0–9, short form on the page) — `COLD` · `WEAK` · `INTRO AVAIL` ·
`INTRO MADE` · `MEETING` · `PARTNER` · `DD` · `VERBAL INT` · `VERBAL` · `COMMITTED`

**Diligence stage** — `COLD` · `INTRO AVAILABLE` · `INTRO MADE` · `FIRST MEETING` ·
`FOLLOW-UP` · `PARTNER MEETING` · `DILIGENCE` · `TERM DISCUSSION` · `VERBAL` ·
`COMMITTED` · `PASS`

**Fit** — `STRONG` · `PARTIAL` · `WEAK` · `MISMATCH` · `UNKNOWN`

**Fund status** — `ACTIVE` · `LIKELY ACTIVE` · `SLOW DEPLOYMENT` · `BETWEEN FUNDS` ·
`FOLLOW-ON ONLY` · `INACTIVE` · `UNKNOWN`

**Conflict level** — `NONE IDENTIFIED` · `LOW` · `MODERATE` · `HIGH` · `UNKNOWN`

**Signal value** — `VERY HIGH` · `HIGH` · `MEDIUM` · `LOW` · `UNKNOWN`

**Evidence status** — `VERIFIED` · `USER PROVIDED` · `INFERRED` · `UNVERIFIED` ·
`NOT PROVIDED` · `CONFLICTING`

**Confidence** — `HIGH` · `MEDIUM` · `LOW` · `INSUFFICIENT EVIDENCE`

**Freshness** — `CURRENT` (<12 months) · `RECENT` (12–24) · `STALE` (>24) · `UNKNOWN`

**Objection categories** — insufficient revenue · unclear product-market fit · valuation ·
customer concentration · regulatory risk · reimbursement risk · clinical risk · technical
validation · commercialisation · long sales cycles · competition · weak defensibility ·
unclear unit economics · high burn · short runway · team gaps · cap-table complexity ·
insufficient lead commitment

---

## 12. Missing-data conventions

The page never leaves a slot blank and never fills one with a guess.

| Situation | What is printed |
| --- | --- |
| Value not found in any source | `NOT PROVIDED` |
| Lead history not evidenced | `NOT VERIFIED` |
| Investor states it leads, no named deal | `Says it leads; NOT VERIFIED` |
| Value supplied by the user | value + `USER PROVIDED` in the provenance note |
| Value read between the lines | value + `inferred`, with `ASSUMPTION — …` in the JSON |
| Two sources disagree | value + `conflicting`; both readings kept in the JSON |
| Cheque size unknown | `NOT VERIFIED` in the CHECK column |
| No lead candidates | Full-width statement + fallback structures |
| No prospects at all | Gap row: no pipeline to sequence |

---

## 13. Companion files

The PDF carries what a decision needs. Everything else is preserved alongside it.

| File | Contents |
| --- | --- |
| `[stem]_lead_investor_map.pdf` | The one page |
| `[stem]_lead_investor_map.json` | Full analysis: every field, the ten-point lead test per investor, the nine-dimension score breakdown, all warnings |
| `[stem]_lead_investor_map_sources.json` | Every distinct source with citation, page/slide, URL, dates and freshness label |
| `[stem]_lead_investor_map.csv` | One row per prospect, 37 columns, for CRM import |

Fields captured but deliberately **not** on the page: full portfolio evidence, complete
source citations, governance and ownership expectations, the full conflict list, research
notes, and the decision-process detail.

---

## 14. Fitting ladder

When content exceeds one page, it is degraded in this fixed order — cosmetic loss before
content loss, content loss before readability loss — and every rung is re-measured:

1. Shorten candidate narrative (150 → 70 characters)
2. Trim gaps (5 → 2) and fallback structures (2 → 1)
3. Trim the disqualification list (7 → 3)
4. Trim outreach phase names (5 → 3 each)
5. Drop the company objection row
6. Tighten section spacing (100% → 78%)
7. Reduce body type (8.0 → 7.7 → 7.5 pt, **floor**)
8. Trim lead candidates (8 → 5) and momentum steps (4 → 3)
9. Move the next-step column out of the candidate table

Whatever was given up is recorded as a warning in the JSON and noted in the footer.
