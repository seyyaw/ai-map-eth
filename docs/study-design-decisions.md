# Study design decisions

Four questions were raised in the project group. This file records the answer taken for
each, the reasoning, and what changed in the instruments and tools as a result. It is the
working document; the version that goes into the white paper is Annex A (methodology), and
the new §4.3 on institutional positioning.

Decided 2026-09-11. Supersedes nothing; nothing here was previously decided in writing.

---

## 1. Should we use one sampling strategy for the whole survey, or different ones?

**Decision: three different strategies, one per instrument, and say so loudly.**

A single strategy was never available. The three target populations differ in the one
property that determines sampling design: whether an enumerable frame exists:

| Instrument | Frame exists? | Strategy |
|---|---|---|
| **ORG** | Yes | Stratified probability sample, census in the small strata |
| **IND** | No | Dual-frame: list-based arm + respondent-driven (referral) arm |
| **CIT** | No | Self-selected online panel **calibrated to** a probability-sampled booster |

Pretending otherwise would produce a single headline national number with a single
confidence interval, and that number would be wrong in a direction we could not estimate.

### ORG: stratified probability, census where the stratum is small

Several strata are small enough to enumerate completely rather than sample: licensed
financial institutions (NBE register), public universities (MoE/HERQA), federal ministries
and agencies, tier-1 hospitals. Take all of them. Sample within the large strata
(manufacturing, agricultural cooperatives, private service firms) proportional to size with
oversampling of the sectors the analysis compares.

The consequence to accept: for the census strata, "response rate" replaces "sampling
error" as the thing that can go wrong, so non-response follow-up is not optional. Budget
three contact attempts and an enumerator visit for non-responders in the census strata.

### IND: dual-frame, because the single-frame versions both fail

There is no register of Ethiopian AI practitioners. Two partial approaches exist and each
is biased in a known direction:

- **List-based arm.** University CS/IT/engineering staff and student registries, ICT
  association membership, employees of named technology firms, EAII and MInT staff.
  Enumerable, weightable, and systematically missing the self-taught and the informally
  employed, who are a large part of the actual practitioner population.
- **Referral arm (respondent-driven sampling).** Seeds chosen for diversity across region,
  gender, sector and employment type; each respondent can invite others; recruitment chains
  are recorded so RDS estimators and network-size weights can be applied. Reaches the
  self-taught; over-represents the well-connected, and is vulnerable to fraud where an
  incentive is attached.

Running both and keeping them distinguishable is what makes either interpretable: the
difference between the arms is itself a finding about who list-based research in Ethiopia
misses. This needs the recruitment arm and the referral chain stored on every response,
which the tools did not previously do: see *What changed* below.

### CIT: a self-selected panel is not a national estimate, and must not be reported as one

Telegram recruitment in Ethiopia yields an urban, younger, more educated, more male,
more Addis-based sample. The instrument is English-only, which compounds every one of
those. Left alone the resulting "national AI awareness" figure would be inflated by an
unknown multiple.

The design is therefore:

1. **Probability-sampled booster**, enumerator-administered, n ≈ 800, drawn from CSA
   enumeration areas across at least four regions with a deliberate rural majority.
   This is the anchor. It is the expensive part and it is not optional.
2. **Telegram/web panel**, n ≈ 1,500, unweighted on its own.
3. **Calibration**: rake the panel to census marginals (region, urban/rural, sex, age band,
   education), and estimate a propensity adjustment against the booster.
4. **Report three numbers, always together**: raw panel, calibrated panel, booster. The
   spread between them is reported as a finding about online measurement in Ethiopia,
   not hidden in a weights appendix.

**Recommended target revision:** CIT 3,000 → 1,500 panel + 800 booster. A calibrated 2,300
beats an uncalibrated 3,000 on every inferential question, and costs less. This is a
recommendation to the group, not yet applied to `tools/schema/common.json`.

---

## 2. Which domains should be covered?

**Decision: six sector modules (the existing five plus government) selected against
stated criteria rather than by intuition.**

Selection criteria, applied in order:

1. **Named in national policy.** The FDRE National AI Policy (2024), and Digital Ethiopia
   name the sector as a priority.
2. **Enumerable.** A sampling frame of organisations exists, so the sector's results can
   carry a confidence interval rather than an anecdote.
3. **Measurable diffusion.** There is plausibly something deployed to find. A sector where
   the honest answer is "nothing yet" belongs in the common core, not in a module.
4. **Evidence base.** Comparable measurement exists elsewhere, so Ethiopian results can be
   placed against something.
5. **Rights salience.** The sector makes decisions about people that AI would change.

| Sector | Policy | Frame | Diffusion | Evidence | Rights | Verdict |
|---|---|---|---|---|---|---|
| Agriculture | ✅ | ✅ coops, MoA | Moderate | Strong (East African smallholder literature) | ✅ | **Core** |
| Health | ✅ | ✅ MoH facility list | Moderate | Strong | ✅✅ | **Core** |
| Finance | ✅ | ✅ NBE register | Highest | Strong | ✅✅ | **Core** |
| Academia / research | ✅ | ✅ MoE/HERQA | Moderate | Strong | ⚪ | **Core** |
| Government / public service | ✅ | ✅ federal + regional bodies | Unknown (the point | Weak for Ethiopia | ✅✅ | **Core) added** |
| Industry / manufacturing | ✅ | ✅ EIC, industrial parks | Low | Moderate | ⚪ | **Core: retained** |
| Telecom / ICT services | ⚪ | ✅ small, enumerable | High | Moderate | ✅ | Covered inside Industry; split in wave 2 if n allows |
| Education (K–12) | ✅ | ✅ MoE | Low | Growing | ✅ | Common core only |
| Justice / security | ⚪ | ✗ access | Unknown | (| ✅✅✅ | **Excluded**) access and safety |

**Government was the significant omission.** The state is simultaneously the largest
prospective deployer of AI in Ethiopia, the author of the AI policy, and the actor whose
AI use has the most direct consequences for rights. Measuring every sector's readiness
*except* the one writing the rules produced a map with a hole in the middle. A `YG` module
now covers service-delivery use cases, procurement route, the legal basis for automated
decisions, citizen redress, and the Amharic/Ethiopic-language service gate.

**Justice and security are deliberately excluded**, and the exclusion is stated in
Limitations rather than left as a silence. Fielding questions about algorithmic policing
or surveillance to Ethiopian security bodies would neither be answered honestly nor be
safe to ask, and an unanswerable module is worse than an acknowledged gap.

Cross-cutting domains (language technology, data infrastructure, skills) stay in the
common core for every sector, because their whole analytical value is that they are
comparable across sectors.

---

## 3. How will the Ethiopian AI Institute see this: support, or compete?

**Decision: assume overlap is real, approach EAII as a complement with something to
offer, and protect independence by making the study publishable without their consent.**

### What EAII has already done

Jima, Tarekegn and Debele (*ASRIC Journal on Natural Sciences* 3(2), 2023): all three EAII
staff: surveyed 32 organisations (10 government bodies, 18 universities, 4 private
data-centre operators) in January 2023 by semi-structured interview and physical
inspection of infrastructure. This is the closest thing to an official Ethiopian AI
landscape study, and it is in `sources/asric-ai-landscape-ethiopia.pdf`.

Treating it as unknown would have been a research failure and, once discovered, a
diplomatic one. It is now cited in §1.3 and §4.3.

### Where we overlap, and where we do not

| | EAII 2023 | AI-MAP |
|---|---|---|
| Unit | Organisations (32) | Organisations (440) + practitioners (1,500) + citizens (2,300) |
| Method | Interview + inspection | Probability sampling + calibrated panels + KII |
| Focus | Infrastructure, policy readiness, skills supply | Diffusion, maturity, over-claiming, sector comparison |
| Verification | Self-report | Evidence prompts, definitional gate, planted item |
| Output | Policy recommendations | Recommendations + published microdata + reusable instrument |
| Standing | Official | Independent |

The overlap is one panel of the grid: the organisational infrastructure baseline. Four
things we produce, EAII has not: measured diffusion rather than capability, the individual
and citizen layers, a quantified gap between claimed and demonstrable adoption, and open
microdata anyone can re-analyse.

### The realistic risks

1. **Mandate.** Regulation 510/2022 gives EAII statutory authority over national AI policy
   and coordination. An independent national measurement can be read as encroachment.
2. **Contradiction.** AI-MAP is built to detect over-claiming. It is likely to produce a
   lower adoption figure than official statements imply, and the first institution asked to
   explain that will be EAII.
3. **Access.** Government organisations in the ORG frame will ask whether the study is
   sanctioned. A cold "no" is a response-rate problem in the largest stratum.

### The approach

- **Lead with their work.** Cite the 2023 landscape study in the introduction as the
  starting point AI-MAP extends. Update, do not correct.
- **Offer the layers they cannot field.** Citizen and practitioner data, emigration
  intention among AI-skilled workers, and an instrument they can re-run as wave 2 under
  their own name. These are worth more to EAII than a share of the organisational chapter.
- **Publish the instrument before fielding.** Pre-registration plus an open instrument
  means no institution is surprised by a question, and the design cannot later be accused
  of having been fitted to its findings.
- **Advisory seat, not a veto.** EAII and MInT are invited as standing observers with the
  right to a published response alongside the findings. No pre-publication approval. The
  independence is the product; a study EAII could edit would be worth less *to EAII*.
- **Timing.** Approach after the pilot, before the main wave: late enough to show
  something, early enough that co-design is genuine.
- **If they decline or oppose.** Field anyway. The ORG frame is built from public
  registers and needs no permission. Drop every implication of official endorsement, note
  the approach and its outcome in Limitations, and expect a lower government-stratum
  response rate which is then reported as a number, not absorbed silently.

**Most likely outcome, stated so it can be checked later:** qualified interest rather than
either support or competition. EAII gets an external evidence base it did not have to
fund; the friction will be over the diffusion headline, not over the study existing.

---

## 4. How do we actually conduct the study?

**Decision: five phases, each with a gate that can stop the study, and a daily dashboard
review during fielding.**

### Phase 0: Authorisation (4 weeks)

Ethics approval; named data controller and DPO; Proclamation 1321/2024 compliance review;
pre-registration of research questions, hypotheses and analysis plan on OSF. Build the
sampling frames from the registers named in Annex A.
**Gate:** no fielding of any channel before ethics approval exists in writing.

### Phase 1: Instrument finalisation (3 weeks)

Cognitive interviews on the English wording, including with lower-education respondents,
since enumerators read the citizen instrument aloud. Agree oral renderings of the technical
terms and publish them, so two enumerators do not define "machine learning" differently.
**Gate:** every technical term has an agreed oral rendering.

### Phase 2: Pilot (4 weeks)

30 organisations, 100 practitioners, 200 citizens. Report scale reliabilities, item
non-response, median completion time per channel, and drop-off point by question. Revise.
**Gate:** CIT median completion under 8 minutes and drop-off below 35%, or the instrument
is cut further before the main wave.

### Phase 3: Main wave (12 weeks, channels in parallel)

- **ORG**: enumerator-assisted, three contact attempts, escalate to a named senior contact.
- **IND**: list arm and referral arm opened together, so arm is not confounded with time.
- **CIT**: Telegram panel throughout; enumerator booster in weeks 3–10 when teams are
  trained and supervisable.

**Daily quality review, off the dashboard**; this is what the new `/dashboard` exists for:

| Check | Trigger for action |
|---|---|
| Flag rate (planted item, definition gate, honeypot, speeding) | >10% in any channel → pause that channel, review |
| Median duration by enumerator | Anyone below 60% of team median → re-brief, re-contact their respondents |
| Quota gaps against the sampling matrix | Any cell below 50% at the halfway point → redirect field effort |
| Drop-off by question | Any question losing >15% → wording problem, fix mid-wave and record the change |
| Client/server score divergence | Any non-zero count → stale build or tampering, investigate the same day |

**Gate:** weekly sign-off. Two consecutive weeks of a channel above its flag threshold
ends that channel rather than accumulating unusable responses.

### Phase 4: Analysis (6 weeks)

Analysis follows the pre-registered plan. Flagged responses are analysed in and out and
both are reported, never silently dropped. Weighting and calibration applied as in §1.
Sector rankings are only published where n ≥ 15, which the dashboard and
`aimap_db.by_sector()` already enforce.

### Phase 5: Publication and handover (4 weeks)

White paper; anonymised microdata under statistical disclosure control for the citizen
file and restricted access for the re-identifiable organisational file; instrument and
code under CC BY 4.0; a wave-2 handover pack so EAII or anyone else can re-field it.

**Total: about 8 months** from authorisation to publication, with fielding occupying 12
weeks of it.

---

## What changed in the tools as a result

| Decision | Change |
|---|---|
| §1 dual-frame IND | `recruit_arm` and `referrer` recorded on every response; `/invite` in the Telegram bot issues referral codes and stores recruitment chains, so RDS weights are computable |
| §1 calibration | `mode` and arm exposed as first-class dashboard filters; raw/calibrated comparison surfaced rather than buried |
| §1 booster | Enumerator quota tracking against the sampling matrix, visible daily |
| §2 government module | `YG` section added to `tools/schema/org.json` in the same common shape as the other five |
| §4 daily review | `tools/web/dashboard.html`: fieldwork, quality, drop-off, enumerator and insight views |
| §4 pilot gate | Drop-off-by-question and duration distributions computed server-side, so the Phase 2 gate is measurable rather than impressionistic |
| Simplicity | Both channels: a short "core" path, honest time estimates, and progress that reflects work remaining rather than questions remaining |
