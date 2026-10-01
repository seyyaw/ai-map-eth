# Mapping AI in Ethiopia (AI-MAP)
## White Paper — Annotated Section Outline (v0.1 draft)

**Working title:** *From Policy to Practice: Mapping Artificial Intelligence Adoption in Ethiopia and a Prescriptive Agenda for AI Value Creation in Low-Resource Economies*

**Document class:** Evidence-based policy white paper with primary-data annex
**Target length:** 60–80 pages main text + annexes
**Intended audiences:** EAII, MInT, MoE, MoH, MoA, NBE, ECA, regional bureaus; universities and research institutes; private sector (banking, telecom, insurance, logistics); development partners (World Bank, UNESCO, UNDP, GIZ, Gates, Mastercard Foundation); the Ethiopian AI research diaspora.

---

## 0. Front matter

| Item | Note |
|---|---|
| Title page, suggested citation, DOI | Deposit on Zenodo for a citable DOI; CC BY 4.0 |
| Author & contributor list | Distinguish authors / survey enumerators / advisory panel |
| Acknowledgements & funding disclosure | State funder and independence explicitly — the paper comments on a state institute |
| Abbreviations | EAII, MInT, DE2030, RAM, TOE, LLM, NLP, HPC, PDPP |
| Executive summary (4 pages) | 10 findings, 12 recommendations, 1 infographic, 1 costed roadmap table |
| Reader's guide | Which chapter answers which policy question |

---

## 1. Introduction

### 1.1 Why this study, why now
Three things changed between 2024 and 2026 and none of them has been measured empirically:
Ethiopia adopted a **National AI Policy** (June 2024), the **Council of Ministers approved the Medemer AI University** (2 March 2026), and the **EAII budget rose 42% to ETB 1.13 bn**. Meanwhile Microsoft's *Global AI Diffusion Q1 2026* places Ethiopian generative-AI use **below 8%** of the working-age population, and the World Bank's *WDR 2026* classifies Ethiopia as underperforming on **both** AI-readiness dimensions. Ambition and diffusion are moving in opposite directions. **Nobody has measured the gap with Ethiopian primary data.**

### 1.2 Research questions
- **RQ1 (State).** What is the actual level, depth and distribution of AI adoption across Ethiopian sectors, organisation types and regions — as opposed to announced intent?
- **RQ2 (Determinants).** Which technological, organisational and environmental factors explain variation in adoption?
- **RQ3 (Value).** Where does AI create the most defensible value given Ethiopia's factor endowments (labour-abundant, data-poor, compute-poor, energy-rich, linguistically plural)?
- **RQ4 (Foundations).** What foundational data assets and cost-effective infrastructure are required, and what do they cost?
- **RQ5 (Governance).** Is the current institutional configuration — a single institute that writes policy, coordinates implementation, licenses developers, certifies products and evaluates itself — fit for purpose?

### 1.3 Scope and boundaries
Federal + regional; public, private, academic, civil society; excludes defence-classified deployments; covers 2019 → Q3 2026.

### 1.4 **How this study differs from existing work** *(critical — reviewers will look here first)*

| Existing body of work | Example | What it does | What it cannot tell you |
|---|---|---|---|
| National policy documents | National AI Policy (2024), Digital Ethiopia 2030 | Normative intent, institutional mandate | Zero measurement; self-authored by the implementing body |
| Global readiness indices | Oxford Insights GAIRI, ITU, Microsoft AI Diffusion | Cross-country comparability | Built from secondary macro proxies; **n≈0 Ethiopian respondents**; sector- and language-blind |
| Multilateral landscape studies | UNESCO RAM / *Sociotechnical Landscape of AI in Ethiopia* (2026) | Institutional and legal mapping, desk-based | Elite/institutional lens; no organisation-level adoption measurement; no firm-level microdata |
| Single-sector academic studies | AI-generated assessment in maths teacher PD; agri-tech pilots | Depth in one domain | Not generalisable; no cross-sector comparison |
| Continental analyses | AU Continental AI Strategy; *Mapping the AI Divide in Africa* | Regional framing | Ethiopia appears as one row, if at all |
| NLP/language-tech research | EthioNLP, EthioLLM, EthioMT, Ethiopian-Language-Survey | Real resource inventory for Ethiopian languages | Technical, not policy-facing; not linked to adoption outcomes |

**This study's five distinctive contributions:**
1. **First multi-sector primary-data survey** of AI adoption in Ethiopia — organisation-level and individual-level, with an explicit, published sampling frame rather than convenience sampling.
2. **Measures diffusion, not intent.** Adoption is scored on an 6-level maturity ladder with *evidence prompts* (named system, go-live date, users, budget line) so "we are working on AI" cannot be scored as deployment.
3. **Language-inclusive instrumentation.** Fielded in Amharic, Afaan Oromo, Tigrinya and Somali as well as English, and it *treats the language gap as a measured variable* — connecting the EthioNLP resource inventory to observed adoption barriers. No prior Ethiopian AI study does this.
4. **Reach through the channel Ethiopians actually use.** A Telegram-based instrument alongside web and enumerator-assisted modes, which is how you reach respondents outside the Addis policy elite on 2G budgets.
5. **Open, reproducible, and contestable.** Anonymised microdata, instrument, codebook and analysis scripts released publicly, so the baseline can be re-run in 2028 and the trend claimed by anyone — including critics of this paper.

### 1.5 Positioning statement on independence
This paper assesses an institution that also funds much of the sector. State the funding source, the non-interference agreement, and the pre-registration of hypotheses before data collection.

---

## 2. Conceptual framework and definitions

### 2.1 Defining "AI adoption" for a low-resource economy
Distinguish four things routinely conflated in Ethiopian discourse:
**AI *use*** (an employee uses ChatGPT) → **AI *adoption*** (an organisation runs an AI system in production) → **AI *adaptation*** (a system is fine-tuned/localised to Ethiopian data and languages) → **AI *production*** (models trained domestically). The World Bank's *adopt → adapt → produce* sequencing is the spine of this paper's argument.

### 2.2 The AI-MAP Adoption Maturity Ladder (0–5)
`0 Unaware · 1 Aware/exploring · 2 Piloting · 3 Deployed in one function · 4 Scaled across the organisation · 5 Core to the operating model`
Each level carries objective evidence criteria (Annex C).

### 2.3 Analytical lenses
- **TOE (Technology–Organisation–Environment)** for organisational determinants.
- **UTAUT2** for individual-level acceptance.
- **UNESCO RAM dimensions** for cross-comparability with the 2026 landscape study.
- **Factor-endowment lens** — Ethiopia's actual comparative advantages: cheap renewable power, a very large young labour force, extreme linguistic diversity, thin capital, thin data.

### 2.4 The "value creation" test
A candidate AI use case qualifies only if it passes five gates: **(1)** addresses a top-20 national constraint; **(2)** the required data exists or can be created for <USD 1m; **(3)** works at ≤3G bandwidth and with intermittent power; **(4)** unit economics beat the non-AI alternative; **(5)** does not require scarce PhD-level talent to *operate*.

---

## 3. Global and comparative context *(short — sets the frame, avoids padding)*

- **3.1 Global.** Compute concentration, the diffusion gap (Global North 27.5% vs Global South 15.4%, Q1 2026), the shift from model-building to model-adoption as the development-relevant frontier.
- **3.2 Global South.** UNCTAD/UNDP framing; data colonialism and the terms-of-trade question for African language data; sovereignty vs pragmatism in compute.
- **3.3 Africa.** AU Continental AI Strategy (2024): five focus areas, 15 member-state recommendations. Continental constraints: ~38% internet penetration, <1% of global data centres.
- **3.4 East Africa & peer benchmarking.** Kenya (National AI Strategy 2025–30 **with a costed implementation roadmap**), Rwanda (2023, earliest mover), Nigeria (NAIS, 150+ stakeholder co-creation), Ghana. **Table: peer comparison across 12 dimensions** — strategy, roadmap, budget transparency, regulator independence, compute, data authority, language programmes.
- **3.5 What Ethiopia can and cannot copy.** Kenya's roadmap discipline: copy. Rwanda's small-state agility: partially. Gulf-style capital-intensive compute: no.

---

## 4. The current state of AI in Ethiopia — evidence base *(the empirical core)*

### 4.1 The policy and institutional environment
- **4.1.1** National AI Policy (June 2024): vision — *"centre of AI development excellence in Africa by 2035"*; 8 policy areas (human resources, infrastructure, data management, R&D, support & incentives, cooperation, ethics/inclusion, risks & remedies); 5 key results; 4 implementation programmes.
  - **Critical reading — findings to state plainly:** the policy contains **no quantified targets, no budget envelope, no timeline** beyond a 3-year evaluation cycle; it still references *"the digital Ethiopia strategy by 2025"*; and §4.2.1 makes **"Enriching AI Surveillance Infrastructure"** — road and security surveillance — the *first* named infrastructure priority, ahead of data centres and compute. That ordering is a policy signal worth naming.
- **4.1.2** Digital Ethiopia 2030 (adopted Dec 2025): four Pathways-for-Prosperity priority sectors (agriculture, manufacturing, IT-enabled services, tourism); three pillars (access, equal opportunity, trust); proposed **National Data Governance Framework and National Data Authority**; 1m IT jobs ambition; 0–3 / 3–5 year sequencing.
- **4.1.3** Legal instruments: **Personal Data Protection Proclamation 1321/2024** (in force 24 July 2024; ECA as supervisory authority; 72-hour breach notification); Computer Crime Proclamation; Hate Speech & Disinformation Proclamation; Access to Information Proclamation.
- **4.1.4** **The gaps.** No binding rules on **public procurement of AI**, **algorithmic transparency**, or **liability for AI-induced harm**. No AI-specific proclamation yet, though the policy anticipates one. No sector regulator has issued AI guidance except partial NBE activity.
- **4.1.5** Sector strategies: Digital Health Blueprint, Digital Education Strategy, National Digital ID (Fayda), e-Government and e-Commerce strategies 2025–2030.

### 4.2 Institutional landscape and the EAII question *(a chapter, not a paragraph)*
- **4.2.1** Map of actors: EAII, MInT, ECA, INSA, National ID Program, Ethiopian Statistical Service, EIAR, Biotechnology Institute, regional bureaus, universities, private firms, diaspora networks.
- **4.2.2** **EAII: mandate concentration.** Under the policy, EAII simultaneously (i) drafts and owns the policy, (ii) coordinates implementation, (iii) **issues licences to private AI developers**, (iv) **certifies AI products and services, domestic and imported**, (v) operates the M&E framework that judges the policy, and (vi) is itself a major R&D producer competing with universities and startups for talent and funding.
- **4.2.3** **Positive contributions — state them fairly and with evidence.** Convening power; getting AI onto the Council of Ministers agenda at all; national-language NLP work under "AI for Social Good"; concrete pilots (EIAR poultry/dairy/enset disease surveillance); startup registration channel; a budget line that survived a tight fiscal year.
- **4.2.4** **Risks of concentration — the honest analysis.**
  - *Player–referee conflict:* an R&D producer that also licenses its competitors.
  - *Crowding-out:* when one institute holds the budget, universities and startups become subcontractors rather than independent centres of gravity.
  - *Licensing as a barrier to entry:* developer licensing plus product certification is, in a thin market, a chokepoint — measure the actual administrative burden.
  - *Self-evaluation:* no external audit of policy implementation is provided for.
  - *Monoculture risk:* one institution's technical bets become the country's technical bets.
  - *Surveillance mandate adjacency:* an institution that builds surveillance infrastructure and also sets AI ethics rules.
- **4.2.5** **Recommendation preview:** separate the four roles — *policy secretariat* (MInT or PMO-level council), *regulator* (independent, with the ECA data mandate), *funder* (an arm's-length National AI Fund with peer review), *performer* (EAII as one competitive R&D actor among several). This is the single most consequential governance recommendation in the paper.
- **4.2.6** **Medemer AI University** (approved 2 Mar 2026; ~1,000 graduates/year target; 100 pan-African scholarships; opening targeted 2027). Analysis: opportunity vs the risk of a greenfield institution absorbing scarce faculty from existing universities that are already under-resourced. Faculty-pipeline arithmetic required.

### 4.3 AI adoption across industries — **primary survey findings**
Structure each sub-section identically: *adoption rate · maturity distribution · named use cases · data foundations · reported barriers · spend · headcount*.
- **4.3.1 Financial services** — the visible early adopter. NBE fraud/AML analytics; bank branch-service AI; CBE's 3.48bn digital transactions worth >ETB 22tn in 2025/26 (~70% of national digital value) → the largest single transaction dataset in the country. Credit scoring for the thin-file majority.
- **4.3.2 Telecommunications** — Ethio Telecom (chatbot, network optimisation, the Huawei partnership on cloud/AI/IoT/data centres), Safaricom Ethiopia. Telcos as the de-facto national data and compute layer. Mobile-money data as a national asset.
- **4.3.3 Health** — Digital Health Blueprint; AI-assisted breast-cancer detection; the >50,000 health-worker digital training programme; EHR/DHIS2 data readiness; radiology and pathology scarcity as the strongest AI case in the country.
- **4.3.4 Agriculture** — EIAR/EAII/GPS PLC pilots in poultry, dairy and enset disease surveillance; advisory services; yield and pest forecasting; the 8110 hotline and extension-agent channel as the realistic delivery surface.
- **4.3.5 Education** — the maths teacher-PD study using AI-generated assessment (TPACK-framed, MoE 2024 programme); K–12 AI literacy; the national exam failure-rate crisis as the demand driver; EMPA and olympiad pipelines.
- **4.3.6 Public administration & policy management** — e-services, Fayda digital ID, document/translation workloads, revenue and customs analytics, planning and statistics.
- **4.3.7 Manufacturing, logistics, energy, mining, tourism** — thinner, but measure it.
- **4.3.8 Media, civil society and the information environment** — content moderation in Ethiopian languages, election-period integrity, the hate-speech proclamation's interaction with automated moderation.
- **4.3.9 The informal and MSME economy** — where most Ethiopians actually work; AI reaching them via Telegram, IVR and agent networks, if at all.

### 4.4 Who the early adopters are — an adopter typology
Cross-cutting profile from the survey: sector, size, foreign-partnership status, cloud access, whether the CEO or a technical lead drove it, whether it survived pilot stage. **Test the hypothesis that adoption in Ethiopia is predicted less by sector than by (a) access to foreign exchange, (b) a foreign technology partner, and (c) one internal champion.** This is a falsifiable, policy-relevant claim.

### 4.5 Research and innovation capacity
- **4.5.1** University and institute pivots: AASTU AI & Robotics Centre of Excellence, Addis Ababa University, Adama, Bahir Dar, Jimma, Hawassa, Mekelle, Haramaya; new AI/data-science programmes; the Medemer AI University.
- **4.5.2** **Bibliometric analysis** (Scopus/OpenAlex/Semantic Scholar, 2015–2026): Ethiopian-affiliated AI publications, growth rate, venue quality, international vs domestic collaboration share, topic distribution, and **the diaspora co-authorship share** — an under-measured and strategically important number.
- **4.5.3** The Ethiopian NLP ecosystem as the clearest domestic research success: EthioNLP, EthioLLM (Amharic, Ge'ez, Afaan Oromo, Somali, Tigrinya + EthioBenchmark), EthioMT (15 languages), the Ethiopian Language Survey repository, SemEval/ACL-track participation, the ICES22 Hawassa workshop. **Argument: this is the one area where Ethiopia has genuine, internationally-visible comparative advantage — and it is almost entirely donor- and diaspora-funded rather than state-funded.**
- **4.5.4** R&D intensity: **~0.27% of GDP vs the AU 1% target**; ranked ~101st in data-science talent; **only ~6% of tech startups are AI-focused**.
- **4.5.5** Brain drain: measure it directly (intention-to-emigrate items in the individual survey), don't assert it.

### 4.6 The private AI sector and startups
iCog Labs, Gebeya, Hasab AI (Amharic/Afaan Oromo/Tigrinya speech), and the wider directory; **~USD 5m total tracked funding** — a number that should be stated next to any "AI hub of Africa" claim. Business models, revenue sources, FX constraints, the diaspora-founder pattern, the EAII startup registration channel.

### 4.7 Infrastructure and compute — the binding constraint
Internet penetration **~21.7% (29.5m users, Oct 2025)**; mobile coverage **98.8% 3G / 74% 4G**, 5G in 16 cities; **electricity access ~55–63%** but a **~97% renewable installed capacity** grid; **~6 data-centre facilities**; data-centre market ~USD 95m (2022) → ~USD 226m (2028E); rural–urban gap **~33 percentage points**; gender internet gap **~12.1%**. Cloud access constrained by FX and by data-residency ambiguity. **National GPU inventory: to be established by this survey — no credible public figure exists.**

### 4.8 Skills, talent and the labour market
Supply: graduate output by field and institution. Demand: job-posting analysis. The mismatch. Salary benchmarks vs remote-work arbitrage. Teacher and civil-servant AI literacy.

### 4.9 Funding: sources, flows and indicators
- **4.9.1** Public: **EAII ETB 1.13 bn FY2026/27, up 42% from ETB 795 m** — and what fraction is capital vs recurrent; MInT, MoE and university allocations; the announced **"USD 1 bn AI factory"** — *verify, cost, and treat sceptically until an appropriation is shown*.
- **4.9.2** Development partners: World Bank Digital Ethiopia/DECA, UNESCO, UNDP, GIZ/BMZ, EU, Mastercard Foundation, Gates.
- **4.9.3** Private and FDI: Huawei, Safaricom, vendor-led investment; venture capital (thin).
- **4.9.4** Diaspora and philanthropic flows.
- **4.9.5** **A funding-effectiveness indicator set** — because "how much" matters less than "on what": *ETB per AI graduate produced · per peer-reviewed publication · per production system in service · per 1,000 citizens served · share of budget contested through open competition · share reaching institutions outside Addis Ababa · capital-to-recurrent ratio · disbursement rate.*
- **4.9.6** Transparency assessment: can an ordinary citizen find out what the AI budget bought? Score it.

### 4.10 Public awareness, trust and readiness
Citizen-level results: awareness, use, trust, perceived job threat, willingness to share data with government vs banks vs foreign platforms, language of AI use, disaggregated by region, gender, age, education, urban/rural.

---

## 5. Where AI should create value in Ethiopia *(the prescriptive core)*

Opening argument: **Ethiopia's binding constraint is not model capability — it is the missing digital substrate.** Therefore prioritise (a) use cases where the data already exists as a by-product of an existing digital process, and (b) use cases where AI substitutes for a *scarce professional*, not for abundant labour. Sequence: **adopt → adapt → produce.**

Each of the following is presented on a **standard one-page use-case card**: *problem · AI approach · required data · infrastructure floor · owner · cost band · time to value · KPI · risks · precedent*.

### 5.1 Government and public service delivery
Document and correspondence processing; Amharic/multilingual citizen-service assistants over Telegram and IVR; translation across working languages; revenue and customs risk-scoring; procurement anomaly detection; land-registry digitisation; court backlog triage. **Governance guardrail: publish an AI use register for the public sector.**

### 5.2 Policy management and evidence
Nowcasting prices, food security and displacement; satellite-based crop, land-use and infrastructure monitoring; automated coding of citizen feedback and parliamentary records; a national policy-simulation and M&E stack; strengthening the Ethiopian Statistical Service rather than routing around it.

### 5.3 Health
Radiology and pathology triage where specialists are scarcest; cervical and breast cancer screening; TB and malaria diagnostics; maternal-risk stratification; health-worker decision support in local languages on low-end phones; supply-chain forecasting for essential medicines; **AMR surveillance**. Guardrail: clinical validation and post-deployment monitoring requirements before any diagnostic AI is procured.

### 5.4 Education
Adaptive maths and literacy support in mother-tongue languages (K–8) — connect directly to the EMPA/maths-PD evidence; teacher professional development and AI-generated formative assessment; exam integrity and item analysis; special-needs and sign-language support; **an AI-literacy strand in the K–12 curriculum**, framed around the competency model in the K–12 AI-education literature rather than tool-training.

### 5.5 Languages and cultural heritage — **Ethiopia's differentiated bet**
ASR and TTS for Amharic, Afaan Oromo, Tigrinya, Somali, Sidama, Wolaytta and beyond; machine translation across working languages; OCR for Ge'ez and Ethiopic manuscripts; sign language; and a **National Language Data Commons** as public infrastructure. Argue this explicitly: *for a country with ~85 languages, language technology is not a nice-to-have — it is the access layer for every other AI service, and it is the only segment where Ethiopia can plausibly lead rather than follow.*

### 5.6 Private sector and finance
Credit scoring for thin-file borrowers and MSMEs; fraud/AML; insurance for smallholders (index-based, satellite-verified); agricultural advisory and market-price information; logistics and routing; demand forecasting for manufacturers; tourism.

### 5.7 Cross-cutting: what Ethiopia should *not* do now
Frontier model pre-training from scratch; mass biometric surveillance expansion ahead of the legal safeguards; sovereign hyperscale data centres before utilisation of existing capacity is demonstrated; single-vendor national platform lock-in. **State these plainly with reasons.**

### 5.8 Prioritisation matrix
All candidate use cases scored on *impact × feasibility × data readiness × cost × time-to-value*, yielding a ranked national portfolio of ~15 with 3-year sequencing.

---

## 6. Data availability and standardisation *(the foundational layer)*

### 6.1 What foundational data the proposed value actually requires
A **data-asset register** mapped to §5: for every prioritised use case, the specific dataset, its current custodian, its current state (exists digitally / exists on paper / does not exist), quality, licence, and the cost to make it usable.

### 6.2 National data audit findings
Administrative data (health/DHIS2, education/EMIS, agriculture, civil registration, land, tax, customs); statistical data (census, surveys); the Fayda digital-ID data estate; telecom and mobile-money data; geospatial and EO data; language and speech corpora; open government data.

### 6.3 The standardisation agenda
Ethiopic text encoding and normalisation; transliteration standards; **the Ethiopian calendar and date-handling problem** — a real, under-appreciated interoperability defect across national systems; name, address and geo-referencing standards; health terminology (ICD/SNOMED/LOINC) mapping; a national metadata standard and data dictionary; unique identifiers and record linkage via Fayda; API and interoperability standards.

### 6.4 Governance, sharing and rights
Operationalising PDPP 1321/2024; lawful bases for public-interest research; anonymisation and de-identification standards; a **tiered access model** (open / registered / secure enclave); the National Data Authority proposed in DE2030 — design, independence and funding; **community rights over language and cultural data** and fair terms when foreign platforms harvest Ethiopian language data.

### 6.5 Proposal: the Ethiopian Data & Language Commons
A concrete institutional proposal — mandate, hosting, licensing (CC BY / CC BY-SA / restricted tiers), contribution incentives, a curation workforce, sustainability model, and a 3-year budget. Includes the policy's own idea of a **national crowd-sourcing platform**, made specific.

### 6.6 Data quality measurement
Adopt a national AI-data quality standard (the policy calls for one but does not specify it): completeness, timeliness, representativeness, **linguistic and regional coverage**, documentation (datasheets for datasets), bias audit requirements.

---

## 7. Cost-effective infrastructure

### 7.1 Principle: the cheapest compute is the compute you don't buy
Sequence: *optimise existing → aggregate demand → federate national capacity → build only what is proven scarce.*

### 7.2 Compute
A national GPU/HPC inventory (this survey produces the first one); a **federated national research-compute pool** across universities before any new build; a shared inference tier for public-sector services; sovereign-cloud vs public-cloud decision criteria by data class; edge and on-device inference for low-connectivity settings; **quantised and distilled small models as the default deployment pattern**, not frontier APIs.

### 7.3 Connectivity
Prioritise coverage-quality where services will be delivered; **design every public AI service to work on 2G/SMS/USSD/IVR and Telegram**, not just app-and-broadband; affordability (data cost as % of income); the ~33pp rural–urban and ~12pp gender gaps as explicit targets.

### 7.4 Energy
Ethiopia's ~97%-renewable grid as a genuine, marketable comparative advantage for green data centres — *conditional on* transmission reliability and industrial tariff clarity. Reliability, not generation, is the constraint. Cooling and siting economics.

### 7.5 Platform and delivery layer
National interoperability/API gateway; identity via Fayda; payments; a shared government AI service catalogue; open-source-first procurement to avoid lock-in; **Telegram/IVR as recognised public-service delivery channels** given actual usage patterns.

### 7.6 Human infrastructure
The often-missed layer: data curators, annotators, MLOps engineers, clinical and agronomic domain reviewers, translators. **An annotation economy as a deliberate job-creation strategy** — this is where AI creates Ethiopian jobs rather than displacing them, and it is directly aligned with the labour endowment.

### 7.7 Costed options
Three scenarios — *Frugal (USD ~15–25m/3yr) · Balanced (~USD 60–90m) · Ambitious (~USD 250m+)* — each with what it buys, what it does not, and the fiscal and FX implications. Figures to be finalised from survey and vendor data.

---

## 8. Challenges and risks

- **8.1 Structural:** data scarcity, compute scarcity, FX rationing, electricity reliability, connectivity, procurement capacity.
- **8.2 Human capital:** shortage, mismatch, emigration, weak PhD pipeline, faculty dilution risk from new institutions.
- **8.3 Institutional:** mandate concentration, weak M&E, no external audit, coordination failure, duplication (a risk the policy itself names).
- **8.4 Legal and regulatory:** no AI procurement rules, no algorithmic transparency duty, no liability regime, PDPP enforcement capacity at the ECA.
- **8.5 Ethical, rights and political-economy risks:** surveillance-first infrastructure framing; automated moderation interacting with the hate-speech proclamation in a multi-ethnic, conflict-affected polity; bias against non-Amharic speakers and rural populations; the disability access gap; gender gap.
- **8.6 Economic:** vendor lock-in, dependency, unfavourable terms of trade on language data, AI-washing of ordinary IT procurement.
- **8.7 Fragility and conflict:** implementing national digital infrastructure in a context of active conflict recovery, internal displacement, and periodic network shutdowns — **a constraint that most AI strategies for Ethiopia simply omit**.
- **8.8 Risk register** with likelihood × impact × owner × mitigation × leading indicator.

---

## 9. Recommendations

Organised as: **Now (0–12 months) · Next (1–3 years) · Later (3–10 years)**, each with owner, cost band, KPI and the evidence in this paper that supports it.

- **9.1 Governance:** unbundle EAII's four roles; establish an independent AI oversight function; mandate an AI use register for public bodies; require external evaluation of policy implementation; publish the National AI Strategy's implementation roadmap **with costs, owners and dates — the single clearest lesson from Kenya**.
- **9.2 Legal:** AI procurement standard; algorithmic transparency and contestability duty for public-sector decisions; a liability rule; strengthen ECA enforcement capacity; a research exemption for public-interest data use.
- **9.3 Data:** stand up the National Data Authority with real independence; launch the Ethiopian Data & Language Commons; fix Ethiopic/calendar/identifier standards; mandate machine-readable open data for named public datasets.
- **9.4 Infrastructure:** federate university compute before building new; national GPU inventory; low-bandwidth-first service design standard; green-compute investment case.
- **9.5 Skills:** AI literacy in K–12 and in the civil service; scale existing universities alongside (not instead of) Medemer AI University; a national annotation and data-curation workforce programme; a structured diaspora-engagement instrument with real terms.
- **9.6 Sector plays:** the ranked portfolio from §5.8 with named owners.
- **9.7 Financing:** an arm's-length National AI Fund with peer review and published criteria; the funding-effectiveness indicators from §4.9.5 adopted as budget-cycle reporting requirements; blended finance for infrastructure.
- **9.8 Measurement:** a **National AI Observatory** with an annual indicator set — and this survey as its baseline instrument, repeated every two years.
- **9.9 Regional and international:** align with the AU Continental AI Strategy; East African compute and data-sharing arrangements; negotiate collectively on language-data terms.

---

## 10. Conclusion — Ethiopia's realistic AI proposition

The honest version: Ethiopia will not be "the AI hub of Africa" by 2035 on current trajectories, and pursuing that framing misallocates scarce resources. The achievable and more valuable proposition: **the country that made AI work in a low-bandwidth, low-income, multilingual setting — and built the language and data commons the rest of Africa depends on.** That is a defensible, differentiated and affordable national position, and it happens to be where Ethiopia's existing research strength already lies.

---

## Annexes

- **A.** Methodology and sampling design *(see `02-research-methodology.md`)*
- **B.** Survey instruments — organisation, individual, academic, educator, citizen *(see `03-survey-instrument.md` and the generated `.docx`)*
- **C.** Adoption maturity ladder — full scoring rubric and evidence criteria
- **D.** Key-informant interview guide and the interviewee frame
- **E.** Use-case cards (full set)
- **F.** Data-asset register
- **G.** Indicator dictionary for the National AI Observatory
- **H.** Bibliometric method and query strings
- **I.** Costing assumptions and sources
- **J.** Ethics approval, consent forms, data-management plan
- **K.** Full bibliography
- **L.** Open data statement — repository, licence, DOI

---

## Evidence status legend (use throughout the draft)

| Tag | Meaning |
|---|---|
| `[P]` | Primary — this study's survey/interview data |
| `[S]` | Secondary — cited published source |
| `[E]` | Estimate — our calculation, assumptions stated |
| `[V]` | **Unverified — claim circulating publicly, not yet confirmed** (e.g. the "USD 1bn AI factory") |
| `[G]` | Gap — no evidence available; flagged for future work |

Every quantitative claim in the final paper carries one of these tags. This is part of what makes the paper contestable and reusable.
