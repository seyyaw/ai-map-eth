# AI-MAP Ethiopia — Research Design & Data Collection Methodology (v0.1)

How each section of the white paper gets filled, by whom, with what instrument, and by when.

---

## 1. Design overview

A **convergent parallel mixed-methods design** with five instruments running concurrently and triangulating on the same research questions.

| # | Strand | Instrument | Target n | Primary sections filled |
|---|---|---|---|---|
| 1 | Desk & document review | Structured extraction protocol | ~120 documents | §3, §4.1, §6.2, §7 |
| 2 | **Organisational survey** | ORG questionnaire (web + enumerator + PDF) | **400 organisations** | §4.3, §4.4, §4.7–4.9 |
| 3 | **Individual/practitioner survey** | IND questionnaire (web + **Telegram bot**) | **1,500 individuals** | §4.5, §4.8, §4.10 |
| 4 | **Citizen pulse survey** | Short CIT questionnaire (**Telegram bot** + IVR + intercept) | **3,000 citizens** | §4.10, §5, §7.3 |
| 5 | Key-informant interviews | Semi-structured KII guide | **45 interviews** | §4.1, §4.2, §4.9, §8, §9 |
| 6 | Bibliometric & ecosystem scan | OpenAlex/Scopus + registry scraping | full corpus | §4.5, §4.6 |
| 7 | Validation workshops | Structured deliberation | 3 workshops | §5, §9 |

**Why five instruments rather than one:** the questions differ in kind. Adoption *depth* is an organisational fact and must be asked of organisations with evidence prompts. Skills and emigration are individual facts. Trust and access are population facts requiring probability-ish sampling and cheap reach. Governance judgements about EAII will not be given honestly in a form with a logo on it — they need confidential interviews.

---

## 2. Strand 1 — Desk and document review

**Corpus (~120 docs), four tiers:**
1. **Ethiopian primary:** National AI Policy (2024, bilingual — *use the Amharic text as authoritative where translations diverge*), Digital Ethiopia 2030, PDPP 1321/2024, Computer Crime Proclamation, sector strategies (Digital Health Blueprint, Digital Education Strategy, e-Gov, e-Commerce), EAII annual reports, **federal budget proclamations FY2022/23–FY2026/27** (extract AI-tagged line items), Council of Ministers regulations, university strategic plans.
2. **East African / continental:** AU Continental AI Strategy; Kenya NAIS 2025–30 + Implementation Roadmap; Rwanda AI Policy; Nigeria NAIS; Ghana; Smart Africa; OECD *AI Governance in Africa* (2026).
3. **Global / Global South:** World Bank *WDR 2026*; UNESCO Recommendation on AI Ethics + RAM; UNESCO *Sociotechnical Landscape of AI in Ethiopia* (2026); UNCTAD Technology & Innovation Report; ITU; GSMA; Microsoft AI Diffusion reports; Oxford Insights GAIRI.
4. **Academic:** Ethiopian AI/NLP literature (EthioNLP corpus), the AI-in-K-12 education literature, the maths teacher-PD study, sectoral AI studies in comparable LICs.

**Extraction protocol:** every document coded in a shared spreadsheet against a fixed schema — *jurisdiction · date · issuing body · binding status · quantified targets (Y/N + values) · budget attached (Y/N + amount) · named owner · M&E provision · sector coverage · data-governance provision · language provision · surveillance provision · gap noted*. Two coders, 20% double-coded, Cohen's κ reported.

**Deliverables:** a comparative policy matrix (§3.4), a gap analysis (§4.1.4), a budget-tracking table (§4.9).

---

## 3. Strand 2 — Organisational survey (the centrepiece)

### 3.1 Sampling frame
Construct explicitly rather than by convenience — this is a core differentiator from prior work.

| Stratum | Frame source | Target n |
|---|---|---|
| Federal ministries, agencies, authorities | Government directory | 60 |
| Regional bureaus (all 12 regions + 2 city admins) | Regional directories | 55 |
| Banks, insurers, MFIs, fintechs | NBE licensee list | 50 |
| Telecom & ICT | ECA licensee list | 25 |
| Health facilities & health agencies | MoH facility registry (stratified: referral/general/primary) | 45 |
| Universities, TVETs, research institutes | MoE + ETA registry | 50 |
| Schools (K–12) | MoE EMIS, stratified urban/rural | 40 |
| Manufacturing, agri-business, logistics | Investment Commission / chambers | 40 |
| Startups & software firms | EAII startup registry, ICT association, hubs | 35 |

**Design:** stratified purposive with a **census of the small strata** (there are only ~30 banks — survey all of them) and stratified random sampling within large strata. Non-response is tracked and reported by stratum; a **non-response bias check** compares respondents to frame characteristics.

### 3.2 Respondent rule
One response per organisation, from the **most senior person who can name the systems** — typically CIO/IT head/director of digital. A second "technical validator" respondent is invited for organisations reporting maturity ≥3.

### 3.3 Anti-inflation design *(the methodological core of this study)*
Self-reported AI adoption is systematically overstated everywhere; in a context where AI is politically favoured, it will be overstated badly. Four countermeasures, all built into the instrument:

1. **Evidence prompts.** Any claim of "deployed" (maturity ≥3) triggers mandatory follow-ups: *name the system · vendor or in-house · go-live month/year · number of users · is there a budget line · is it running today*. Unnameable systems are down-scored.
2. **A behavioural checklist instead of a self-rating.** Respondents tick concrete practices actually performed ("we have a written data-sharing agreement", "we monitor a deployed model's accuracy in production"). The maturity score is **computed** from these, not self-assigned. The self-rating is *also* collected — the **gap between self-rated and computed maturity is itself a reported finding**.
3. **A definitional gate.** Early in the instrument, a short set of items distinguishes AI from ordinary automation/BI/dashboards, with examples. Respondents who classify a rules-based dashboard as AI are flagged for adjusted analysis.
4. **A planted-item validity check.** One item names a plausible-sounding but non-existent AI capability. Respondents who claim to use it are flagged for over-claiming; the flagged proportion is reported as a data-quality statistic.

### 3.4 Modes
Web (primary) · enumerator-assisted CATI/CAPI for low-response strata (especially regional bureaus and rural facilities) · offline PDF/Word for organisations that require a formal letter · Telegram for follow-up reminders. **Offline-capable web form** — saves to local storage and submits when connectivity returns.

### 3.5 Access strategy
Formal request letters from the host institution + a partner ministry; ICT-association and chamber endorsement; NBE and ECA channels for regulated sectors; a named liaison per stratum; **a guaranteed benchmarking report back to each participating organisation** — the single most effective incentive for institutional response, and cost-free.

---

## 4. Strand 3 — Individual / practitioner survey

**Population:** ICT and data professionals, researchers, academics, students in relevant fields, public-sector technical staff, educators.
**Target n = 1,500**, quota-managed by region, gender and sector.

**Recruitment channels:** university mailing lists and department heads; EthioNLP, Ethiopian ICT/software associations, developer meetups and hubs; LinkedIn and X; **Telegram channels and groups — the dominant Ethiopian professional channel**; snowball with a capped referral chain; diaspora networks.

**Key measurement targets:** actual tool use and frequency; self-assessed and tested AI competence; training received and wanted; **which language they work and prompt in, and where language failure blocks them**; salary and employment status; **intention to emigrate (validated 3-item scale)** — this converts "brain drain" from an assertion into a measured quantity with covariates.

**Quality controls:** honeypot field, minimum completion time, duplicate detection on hashed contact, attention-check item, IP/device heuristics for the web mode, and Telegram user-ID uniqueness for the bot mode.

---

## 5. Strand 4 — Citizen pulse survey (**where the Telegram bot does the heavy lifting**)

**Why Telegram:** it is the default social and information platform in Ethiopia, works acceptably on low bandwidth, needs no app install beyond one people already have, supports Amharic and other Ethiopic-script input natively, and costs nothing per response. **A web survey alone will produce an Addis-based, English-reading, university-educated sample and a badly wrong national picture.** Telegram plus IVR plus in-person intercepts is how the sample gets corrected.

**Design:** 18–22 items, ≤7 minutes, one question per message, buttons rather than typing wherever possible, full Amharic / Afaan Oromo / Tigrinya / Somali / English switching, resumable, no personal identifiers required.

**Distribution:** paid and organic placement in large Ethiopian Telegram channels (news, jobs, university, regional); QR codes at universities, kebele service centres, health facilities and banks; partner-organisation broadcast; radio mentions for the IVR line.

**Representativeness — stated honestly.** A Telegram sample is **not** a probability sample of Ethiopia. Three corrections: **(a)** post-stratification weights to census/ESS marginals (region, sex, age, urban/rural, education); **(b)** an **enumerator-administered booster sample of n≈600** in rural and low-connectivity woredas, drawn with proper probability sampling, used both as a stand-alone estimate and to calibrate the online sample; **(c)** an **IVR/USSD channel** for non-smartphone respondents. Report unweighted and weighted estimates side by side, and state the design effect and the limits of inference. Do not claim national representativeness without the booster.

---

## 6. Strand 5 — Key-informant interviews (n≈45)

**Frame:** EAII leadership and technical staff (4–5); MInT, MoE, MoH, MoA, ECA, INSA, ESS, National ID (10); NBE and 3–4 bank CTOs (5); Ethio Telecom / Safaricom (3); university deans and AI centre heads (7); startup founders (6); development partners — World Bank, UNESCO, UNDP, GIZ (5); civil society, digital-rights and journalist voices (4); diaspora researchers (4).

**Guide themes:** the intent-vs-implementation gap; where budgets actually go; coordination and duplication; **the EAII mandate question, asked non-leadingly** ("who decides X?", "what happens if two institutions disagree?", "walk me through getting a licence") rather than "is EAII too powerful?"; procurement reality; data-sharing blockages; talent; what they would do with a marginal USD 10m.

**Ethics and safety:** interviews on the governance and surveillance themes are **confidential and non-attributed by default**; institutional attribution only with written consent; no recording where the interviewee prefers notes; a **do-no-harm review** before any quote involving a named public body is published. This matters in this context and should be stated in the paper.

**Analysis:** thematic analysis, two coders, framework matrix by TOE + governance themes, disconfirming-case search.

---

## 7. Strand 6 — Bibliometric and ecosystem scan

- **Publications:** OpenAlex + Scopus + Semantic Scholar API, 2015–2026, Ethiopian affiliation strings (with variant handling — a real problem for Ethiopian institution names), AI/ML/NLP concept filters. Outputs: volume trend, venue tier, **international vs domestic vs diaspora co-authorship share**, topic map, citation impact.
- **Datasets and models:** HuggingFace, GitHub, Zenodo scan for Ethiopian-language resources — the practical inventory for §6 and the evidence base for the language argument in §5.5.
- **Startups and firms:** registry triangulation (EAII startup registry, Crunchbase, Neural Catalog, hub portfolios), funding amounts, founding years, survival.
- **Job market:** scrape and code Ethiopian job postings for AI/data roles over 24 months → demand-side skills evidence for §4.8.
- **Compute inventory:** direct enquiry to universities and institutes (a dedicated ORG module) — this produces the **first national GPU/HPC inventory**.

---

## 8. Instrument development and quality assurance

1. **Item sourcing.** Adapt validated items wherever possible — OECD/Eurostat ICT-usage AI module, UNESCO RAM, TOE and UTAUT2 scales, World Bank Enterprise Survey digital module — so results are internationally comparable. Only write new items for what is genuinely Ethiopia-specific (language, Telegram, FX, Ethiopic/calendar standards, EAII).
2. **Translation protocol.** Forward translation → back translation by an independent translator → reconciliation panel → cognitive interviewing in each language. Amharic, Afaan Oromo, Tigrinya, Somali. **Budget for this properly; bad translation is the most common failure mode in Ethiopian multilingual surveys.**
3. **Cognitive interviews:** 8–10 per instrument per language, think-aloud protocol.
4. **Pilot:** 30 organisations, 100 individuals, 200 citizens. Report Cronbach's α / McDonald's ω for multi-item scales; revise or drop items with poor discrimination.
5. **Pre-registration:** register RQs, hypotheses, primary outcomes and the analysis plan (OSF) **before** the main field wave. This is unusual in this literature and strengthens the paper's independence claim considerably.

---

## 9. Ethics, data protection and governance

- IRB/ethics approval from the host university; local approval where required for health-facility and school access.
- **PDPP 1321/2024 compliance by design:** explicit informed consent, stated purpose and retention, no collection of personal identifiers in the citizen instrument, opt-in only for follow-up contact, a named data controller and DPO, breach procedure.
- **Data minimisation:** contact details stored separately from responses, linked by a random token; direct identifiers destroyed after the follow-up window.
- **Storage:** encrypted at rest; primary storage under the host institution's control; documented processor arrangements for any third-party service.
- **Open science with protection:** anonymised microdata released under CC BY 4.0 with disclosure control (k-anonymity ≥5 on the quasi-identifier set, suppression of small cells, aggregation of small strata); a restricted-access tier for the organisational file, which is re-identifiable by construction.
- **Reciprocity:** every participating organisation receives a benchmark report; every citizen respondent can opt into a plain-language summary in their language.

---

## 10. Analysis plan

- **Descriptive:** adoption rates and maturity distributions by sector, size, region, ownership — weighted and unweighted, with confidence intervals.
- **The headline number:** the **self-rated vs evidence-computed maturity gap** — this is the finding that distinguishes this study from every index that has scored Ethiopia from a desk.
- **Inferential:** ordered logit / multilevel models of maturity on TOE predictors; test the §4.4 hypothesis that FX access, foreign partnership and an internal champion outperform sector as predictors.
- **Segmentation:** latent class analysis of the adopter typology.
- **Gap analysis:** required-vs-available for data assets, compute, skills.
- **Qualitative integration:** joint-display tables placing survey estimates alongside KII explanations — the mechanism behind each number.
- **Costing:** bottom-up unit costs for each §7.7 scenario, sourced from vendor quotes and comparator-country procurement.
- **Sensitivity:** results reported with and without over-claim-flagged respondents; weighted and unweighted.

---

## 11. Timeline (26 weeks from go)

| Weeks | Activity |
|---|---|
| 1–3 | Finalise instruments; ethics submission; sampling frame construction; partner MoUs |
| 3–5 | Translation + cognitive interviews; tool build and load test; enumerator recruitment |
| 5–7 | Pilot (30/100/200); revise; pre-register |
| 6–8 | Desk review and bibliometrics run in parallel |
| 7–15 | **Main field wave** — all four surveys concurrently; weekly response monitoring by stratum with targeted follow-up |
| 10–17 | KIIs |
| 15–18 | Rural booster and IVR wave |
| 16–20 | Data cleaning, weighting, analysis |
| 20–22 | Draft white paper; use-case cards; costing |
| 22–24 | Three validation workshops (Addis, one regional, one online/diaspora) |
| 24–26 | Revision, layout, DOI deposit, launch, microdata release |

---

## 12. Team and budget shape

**Roles:** PI; co-investigator (policy); survey methodologist; 4 sector leads (gov/health/education/finance-telecom); data engineer (tools); 2 translators + 4 language reviewers; 12 enumerators + 2 supervisors; qualitative researcher; data analyst; communications/design.

**Indicative budget bands (USD):** instruments & translation 12–18k · enumerator field work incl. rural booster 45–70k · tooling & hosting 6–10k · Telegram/IVR distribution 8–15k · KII travel 10–15k · analysis & writing 40–60k · workshops 15–25k · design, publication, DOI 8–12k. **Total ≈ USD 145–225k** for the full design; a credible reduced-scope version (no rural booster, no IVR, n=200 orgs) runs ≈ USD 60–80k — **but say plainly in the paper which version was funded, because it determines what can be claimed.**

---

## 13. Risks to the research itself

| Risk | Mitigation |
|---|---|
| Low institutional response, especially government | Ministerial endorsement letter; named liaisons; benchmark-report incentive; enumerator follow-up; report response rates honestly |
| Political sensitivity of EAII findings | Pre-registration; confidential KIIs; findings framed as institutional design, not personal criticism; right-of-reply offered to named institutions before publication |
| Telegram sample skew | Rural booster + IVR + weighting; explicit limitations statement |
| Network shutdowns / conflict-affected areas | Offline-capable instruments; flexible field scheduling; transparent reporting of excluded areas rather than silent omission |
| Translation quality | Back-translation + cognitive interviews + native-speaker reviewers per language |
| Over-claiming | The four anti-inflation mechanisms in §3.3 |
| Funder influence | Written independence clause; disclosure in the paper |
