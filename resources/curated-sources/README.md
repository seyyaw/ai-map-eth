# Primary sources retrieved during scoping

Everything cited from outside the repository is archived here, so the paper can be
re-checked without a live network. HTML-only sources are captured as PDF
(`web-snapshots/`, rendered headless at retrieval date), because news and blog pages
carrying the numbers we quote are edited in place without notice.

## Ethiopian policy and landscape

| File | Document | Status |
|---|---|---|
| `ethiopia-national-ai-policy.pdf` / `.txt` | FDRE *National Artificial Intelligence Policy*, June 2024: bilingual Amharic/English | ✅ complete |
| `ethiopia-ai-policy-EN.txt` | English section only, pp. 34–68 | ✅ |
| `asric-ai-landscape-ethiopia.pdf` / `.txt` | Jima, Tarekegn & Debele, *The Landscape of Artificial Intelligence Implementation in Ethiopia*, ASRIC Journal on Natural Sciences 3(2) 2023, 188–197 | ✅ |

`asric-ai-landscape-ethiopia.pdf` matters out of proportion to its length: all three
authors are **Ethiopian Artificial Intelligence Institute staff**, so it is the closest
thing to an EAII position on what has and has not been measured. It is an interview and
physical-inspection study of 32 organisations (10 government bodies, 18 universities,
4 private data-centre operators), fielded 1–30 January 2023. It establishes the
infrastructure and institutional baseline; it does not measure diffusion, individuals,
citizens, or over-claiming, which is precisely the gap AI-MAP fills. See
`paper/chapters/04-current-state.tex` §4.3 for the positioning that follows from this.

## Comparative and continental evidence

| File | Document | Status |
|---|---|---|
| `ai-divide-africa.pdf` / `.txt` | Agbeyangi & Lukose, *Mapping the AI Divide in Africa*, arXiv | ✅ |
| `mwais2024-genai-subsaharan-africa.pdf` / `.txt` | Ayeni, Ngufor, Gani & Mbarika, *Adoption of Generative AI (Gen-AI) in Sub-Saharan Africa: Extension of the UTAUT Model*, MWAIS 2024 Proceedings 31 | ✅ |
| `mardiani-iswahyudi-ai-survey.pdf` / `.txt` | Mardiani & Iswahyudi, *Mapping the Landscape of Artificial Intelligence Research: A Bibliometric Approach*, West Science Interdisciplinary Studies 1(8) 2023, 606–618 | ✅ |
| `avepoint-ai-report-2026.pdf` / `.txt` | AvePoint, *The State of AI 2026: Scaling Trust, Control and Readiness in the Agentic Era*: global survey, n=750 | ✅ |
| `preprints-ai-agriculture-review.pdf` / `.txt` | *Artificial Intelligence in Agriculture: A Review of Transformative Applications and Future Directions*, Preprints 202503.0335 v1 | ✅ |

What each contributes to AI-MAP:

- **MWAIS/UTAUT**: the theoretical spine for the IND instrument. It extends UTAUT with
  *algorithmic aversion* as a mediator and fields it in Nigeria, Cameroon and Uganda.
  Its own N is 54 and its results are preliminary, which is the opening: AI-MAP can field
  the same constructs at n≈1,500 with a documented sampling frame and publish the
  microdata. Constructs adopted: performance expectancy, effort expectancy, social
  influence, facilitating conditions, algorithmic aversion, behavioural intention.
- **AvePoint 2026**: the global comparator. 750 respondents with direct responsibility
  for information management, data security or AI programmes. It supplies the benchmark
  figures the ORG instrument is now aligned to, so Ethiopian organisations can be placed
  against a global distribution rather than described in isolation.
- **Mardiani & Iswahyudi**: a worked precedent for "mapping" as a research genre, and a
  caution: a bibliometric map describes what is *published*, not what is *deployed*.
  AI-MAP's contribution is the second of those, and §1.3 now says so explicitly.
- **AI in agriculture review**: the domain evidence base for the agriculture module,
  which the domain-selection decision (docs/study-design-decisions.md) makes load-bearing.

## Web snapshots (`web-snapshots/`)

Captured 2026-09-11. Each is the rendered page at that date.

| File | Source | Used for |
|---|---|---|
| `microsoft-ai-diffusion-q1-2026-africa.pdf` / `.txt` | Ecofin Agency on Microsoft, *Global AI Diffusion: Q1 2026* | Adoption rates: global 17.8%, developed 27.5%, developing 15.4%, South Africa 23.1%, Kenya 8.7%, Nigeria 10.1%, Ethiopia <8% |
| `techcentral-sa-leads-africa-ai-adoption.pdf` | TechCentral on the same Microsoft report | Corroboration |
| `hrrc-critical-gaps-ai-east-horn-africa.pdf` / `.txt` | Human Rights Research Center, Dec 2025 | East and Horn of Africa governance gaps; which neighbours have AI strategies |
| `ai-readiness-index-2026-rankings.pdf` | index.dev | Cross-country readiness rankings |
| `african-ai-adoption-trends-2025.pdf` | Neuravox Journal | Continental adoption trend commentary |
| `ai-regulation-africa-2026.pdf` | Tech In Africa | Regulatory movement across African states in 2026 |
| `nigeria-genai-working-age-10pct.pdf` | Technext | Nigeria working-age diffusion |
| `togo-mid-tier-ai-adopters.pdf` | Togo First | Mid-tier African adopter comparison |
| `ethiopia-first-ai-research-centre.pdf` | Ethiopian Business Review | EAII / AI UniPod institutional development |

Snapshots are **secondary reporting**, tagged `S` in Annex D. Where a snapshot is the only
support for a figure, the figure is reported as reported: attributed to the outlet and to
the underlying report, never as an AI-MAP finding.

## Still to obtain

- **Digital Ethiopia 2030**: `pmo.gov.et` serves a JavaScript application shell rather than
  the file. Retrieve through a browser session or request from the PMO/MInT. Needed for
  outline §4.1.2; the scoping summary currently rests on secondary reporting.
- **UNESCO, *Sociotechnical Landscape of AI in Ethiopia* (2026)**, unesdoc `pf0000398524`: the UNESCO observatory page returns *Access denied* to automated retrieval and to a
  headless browser. Request from UNESCO or retrieve from an institutional network.
- **Microsoft, *Global AI Diffusion (Q1 2026***) the primary report behind the adoption
  figures above. We currently hold two independent secondary reports of it, which agree.
- **Shitaye et al., *Artificial Intelligence in East African Agriculture*, The Scientific
  World Journal 2026**, doi `10.1155/tswj/5128133`: open access, but Wiley and PMC both
  refuse automated retrieval. Obtain through an institutional session.
- **K-12 AI education article**, *Computers and Education: AI* `S2666557325000102`: publisher returns 403; obtain through institutional access.

## Reproducing the retrieval

`scripts/fetch_sources.py` re-runs every automated retrieval in this register. Two of the
publishers (AIS eLibrary, Preprints.org) refuse plain HTTP clients and need a real browser
engine; the script uses Playwright and says which engine each source needs, because the
answer is not guessable and cost an hour to find once.
