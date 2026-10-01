# docs/

## Live documents

**[study-design-decisions.md](study-design-decisions.md)**: the four questions raised in the
project group, the answer taken for each, and what changed in the instruments and tools as a
result: one sampling strategy or several, which domains get a sector module, how the study stands
in relation to the Ethiopian AI Institute, and how the study is actually conducted. This is the
working document; the versions that go into the paper are Annex A and §4.3.

## The white paper

The white paper now lives in [`../paper/`](../paper/) as LaTeX. Build it with `../paper/build.sh`.

| LaTeX source | Was |
|---|---|
| `paper/chapters/00-abstract.tex`, `01-introduction.tex` | `04-abstract-and-introduction.md` |
| `paper/chapters/01`–`10` | `01-whitepaper-outline.md` |
| `paper/annexes/a-methodology.tex` | `02-research-methodology.md` |
| `paper/annexes/d-evidence-base.tex` | `03-evidence-base.md` |
| `paper/annexes/b-instrument.tex`, `c-maturity-ladder.tex` | generated from `tools/schema/*.json` |

The original Markdown drafts are kept in `superseded-markdown/` for reference only.
They are **not** the source of truth and are not maintained: edit the LaTeX.
