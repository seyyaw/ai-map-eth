/* AI-MAP Ethiopia: schema-driven survey renderer.
   Vanilla JS, no build step, no external requests. Works offline: responses queue
   in localStorage and are flushed when connectivity returns. */

const CFG = {
  endpoint: (localStorage.getItem('aimap_endpoint') || '') || '/api/submit',
  // What this device last submitted, so a returning respondent is offered a
  // review instead of silently starting a second response and being counted
  // twice. An id and a date only: no answers are kept here.
  doneKey: 'aimap_completed',
  progressEndpoint: '/api/progress',
  referralEndpoint: '/api/referral',
  schemaDir: './schema/',
  qKey: 'aimap_queue',
  draftKey: 'aimap_draft'
};

let COMMON = null, INSTR = null;

// The study is fielded in English only. Recorded on every response so that a
// later multilingual wave remains distinguishable in the same dataset.
const LANG = 'en';
let state = {
  code: null, answers: {}, page: 0, qidx: 0, pages: [], startedAt: null, respId: null,
  // Design variables, not answers. They come from the recruitment link and travel
  // with the response, because without them the dual-frame design in
  // docs/study-design-decisions.md §1 cannot be analysed after the fact.
  form: 'full',          // 'full' | 'short': the same instrument, non-core items routed out
  arm: 'open',           // list | referral | booster | open
  referrer: null,        // invitation code, for the respondent-driven arm
  enumerator: null,      // set on enumerator devices via ?enum=
  review: false,         // revising a response already submitted from this device
  revision: 0
};

/* Recruitment context from the link the respondent followed. A list-frame
   invitation carries ?arm=list; a referral carries ?ref=ABC123. Read once, at
   load, so a respondent who navigates within the form cannot lose their arm. */
function readRecruitment() {
  try {
    const q = new URLSearchParams(location.search);
    const arm = q.get('arm');
    if (['list', 'referral', 'booster', 'open'].includes(arm)) state.arm = arm;
    const ref = (q.get('ref') || '').trim().toUpperCase();
    if (ref) { state.referrer = ref; state.arm = 'referral'; }
    const en = (q.get('enum') || '').trim();
    if (en) { state.enumerator = en.slice(0, 32); }
    if (q.get('form') === 'short') state.form = 'short';
  } catch (e) {}
}

/*  (: -) appearance: theme, background, text size (: -) Light is the default. The inline script in index.html applies the stored
   choice before first paint; this module keeps it in sync afterwards. */

const BACKGROUNDS = [
  { id: 'paper',    label: 'Paper',    light: '#fbfaf8', dark: '#16171a' },
  { id: 'warm',     label: 'Warm',     light: '#faf5ec', dark: '#1b1815' },
  { id: 'sand',     label: 'Sand',     light: '#f4efe4', dark: '#1d1a15' },
  { id: 'sage',     label: 'Sage',     light: '#f1f5f1', dark: '#141a16' },
  { id: 'mist',     label: 'Mist',     light: '#f0f4f7', dark: '#14181c' },
  // Pure white / pure black: a solid swatch would be invisible against the
  // dialog, so it is shown split to read as "high contrast" at a glance.
  { id: 'contrast', label: 'Contrast', light: '#ffffff', dark: '#000000',
    swatch: 'linear-gradient(135deg,#ffffff 0 50%,#000000 50% 100%)' }
];
const THEME_DEFAULT = 'light', BG_DEFAULT = 'paper', SIZE_DEFAULT = '16';

const prefersDark = () => window.matchMedia('(prefers-color-scheme: dark)').matches;
const getTheme = () => localStorage.getItem('aimap_theme') || THEME_DEFAULT;
const getBg    = () => localStorage.getItem('aimap_bg')    || BG_DEFAULT;
const getSize  = () => localStorage.getItem('aimap_size')  || SIZE_DEFAULT;

function applyAppearance() {
  const theme = getTheme();
  const dark = theme === 'dark' || (theme === 'system' && prefersDark());
  const r = document.documentElement;
  r.setAttribute('data-appearance', dark ? 'dark' : 'light');
  r.setAttribute('data-bg', getBg());
  document.body.style.fontSize = getSize() + 'px';
  syncSettingsUI();
}

function syncSettingsUI() {
  const theme = getTheme(), bg = getBg(), size = getSize();
  document.querySelectorAll('#themeseg button').forEach(b =>
    b.setAttribute('aria-pressed', String(b.dataset.theme === theme)));
  document.querySelectorAll('#textseg button').forEach(b =>
    b.setAttribute('aria-pressed', String(b.dataset.size === size)));
  document.querySelectorAll('#bgsw').forEach(box => {
    box.querySelectorAll('button').forEach(b =>
      b.setAttribute('aria-pressed', String(b.dataset.bg === bg)));
  });
}

function buildSettings() {
  const box = $('#bgsw');
  const dark = document.documentElement.getAttribute('data-appearance') === 'dark';
  box.innerHTML = '';
  BACKGROUNDS.forEach(b => {
    const btn = el('button', 'sw'); btn.type = 'button'; btn.dataset.bg = b.id;
    const sw = el('i');
    sw.style.background = b.swatch || (dark ? b.dark : b.light);
    btn.appendChild(sw); btn.appendChild(el('span', null, b.label));
    btn.addEventListener('click', () => {
      localStorage.setItem('aimap_bg', b.id); applyAppearance(); buildSettings();
      announce(b.label + ' background');
    });
    box.appendChild(btn);
  });
  syncSettingsUI();
}

/*  (: -) utilities (: -) */
const $ = s => document.querySelector(s);
const el = (t, c, txt) => { const n = document.createElement(t); if (c) n.className = c; if (txt != null) n.textContent = txt; return n; };
const uid = () => (crypto.randomUUID ? crypto.randomUUID() : 'r' + Date.now() + Math.random().toString(16).slice(2));

// Screen-reader announcement. Cleared first so repeated identical text re-fires.
let announceTimer = null;
function announce(msg) {
  const n = $('#live'); if (!n) return;
  n.textContent = '';
  clearTimeout(announceTimer);
  announceTimer = setTimeout(() => { n.textContent = msg; }, 60);
}

// Briefly flag that the draft was written to local storage.
let savedTimer = null;
function flashSaved() {
  const n = $('#netstat'); if (!n || n.classList.contains('off')) return;
  n.classList.add('saved'); n.textContent = 'saved';
  clearTimeout(savedTimer);
  savedTimer = setTimeout(() => { n.classList.remove('saved'); updateNet(); }, 1200);
}

// Schema strings are plain English. The object form is still tolerated so that a
// partially-migrated or future multilingual schema does not break the renderer.
function t(bag) {
  if (bag == null) return '';
  if (typeof bag === 'string') return bag;
  return bag.en || Object.values(bag)[0] || '';
}

async function loadJSON(p) { const r = await fetch(CFG.schemaDir + p); if (!r.ok) throw new Error('cannot load ' + p); return r.json(); }

/*  (: -) option references (: -) Questions may reuse another question's option list via options_ref. The
   schema used to be split into one file per instrument, so a reference could
   name an instrument too ("ORG:A1"); now it is a single merged document with
   globally unique question ids, so the id alone is enough to find it. */
const refCache = {};
function findQuestion(qid) {
  for (const s of INSTR.sections) for (const q of s.questions) if (q.id === qid) return q;
  return null;
}
function resolveOptions(q) {
  if (q.options) return q.options;
  if (q.options_ref) {
    // The "INSTRUMENT:" prefix from the old per-instrument files still parses
    // if it shows up anywhere, but it is never needed to find the question.
    const qid = q.options_ref.includes(':') ? q.options_ref.split(':')[1] : q.options_ref;
    const src = findQuestion(qid);
    if (src) {
      let opts = resolveOptions(src) || [];
      if (src.row_options) opts = src.row_options;   // matrix rows reused as a flat option list
      return opts.concat(q.extra_options || []);
    }
  }
  if (q.rows) return q.rows;
  return [];
}

/*  (: -) conditional routing (: -) */
function showIf(cond) {
  if (!cond) return true;
  const v = state.answers[cond.q];
  const has = v !== undefined && v !== null && v !== '' && !(Array.isArray(v) && !v.length);
  switch (cond.op) {
    case 'answered':   return has;
    case 'eq':         return String(v) === String(cond.value);
    case 'not_eq':     return String(v) !== String(cond.value);
    case 'in':         return Array.isArray(v)
      ? v.some(x => cond.value.map(String).includes(String(x)))
      : cond.value.map(String).includes(String(v));
    case 'not_in':     return has && (Array.isArray(v)
      ? !v.some(x => cond.value.map(String).includes(String(x)))
      : !cond.value.map(String).includes(String(v)));
    case 'gte':        return has && parseFloat(v) >= parseFloat(cond.value);
    case 'lte':        return has && parseFloat(v) <= parseFloat(cond.value);
    case 'includes':   return Array.isArray(v) && v.includes(cond.value);
    case 'includes_any': return Array.isArray(v) && cond.value.some(x => v.includes(x));
    // scale_gte: any row of a likert grid at or above a threshold
    case 'scale_gte':  return v && typeof v === 'object' && Object.values(v).some(x => parseFloat(x) >= parseFloat(cond.value));
    default: return true;
  }
}
/* The short form is the SAME instrument with the non-core items routed out, so
   its answers pool with the long form's item by item. A separate short
   questionnaire would not be comparable with the long one, which is the whole
   reason for having it. Which items are core is a data decision in
   tools/schema/*.json, not a branch here. */
function inForm(q) {
  if (state.form !== 'short') return true;
  if (!shortFormAllowed(state.code)) return true;
  return !!q.core;
}

function shortFormAllowed(code) {
  const sf = (COMMON && COMMON.short_form) || null;
  return !!(sf && (sf.enabled_for || []).includes(code));
}

const visible = q => !q.hidden_from_ui && showIf(q.show_if) && inForm(q);

/*  (: -) completion progress (: -) Counted over the questions currently IN SCOPE, not over the whole instrument:
   routing means the real length of the questionnaire depends on the answers
   given, so a fixed denominator would show a bar that jumps backwards when a
   branch opens. Grids are weighted by their row count, since a nine-row grid is
   not one question's worth of work. */

function isCounted(q) {
  return q.type !== 'info' && !(q.flags && q.flags.includes('honeypot'));
}

function questionWeight(q) {
  if (q.type === 'likert_grid') return (q.rows || []).length || 1;
  if (q.type === 'matrix') return (q.row_options || []).length || 1;
  return 1;
}

function answeredWeight(q) {
  const v = state.answers[q.id];
  if (q.type === 'likert_grid' || q.type === 'matrix') {
    if (!v || typeof v !== 'object') return 0;
    return Object.values(v).filter(x => x !== undefined && x !== '').length;
  }
  if (v === undefined || v === null || v === '' || v === false) return 0;
  if (Array.isArray(v)) {
    if (!v.length) return 0;
    if (q.type === 'repeatable') return v.some(r => Object.values(r).some(x => x)) ? 1 : 0;
  }
  return 1;
}

/*  (: -) cross-field consistency (: -) Per-question validation cannot catch an answer that is only wrong in the light
   of another: 400 IT staff in a 50-person organisation, more pilots reaching
   production than were started, a founding year in the future. Each passes every
   check its own field can make.

   The rules live in the schema, so adding one is a data change. This is the twin
   of tools/aimap_constraints.py -- the two channels cannot share a runtime, so
   the model is implemented twice and the parity test asserts they agree. */

function bandMax(qid, value) {
  const q = findQuestion(qid);
  if (!q) return null;
  const o = (q.options || []).find(x => String(x.value) === String(value));
  // An open-ended top band ("5,000 or more") has no maximum by design, so
  // nothing can exceed it and the rule correctly does not fire.
  return o && o.max != null ? o.max : null;
}

/* Read an answer, addressing one row of a grid as "Q.row". A contradiction often
   lives between a question and a single grid row -- "rates themselves expert at
   machine learning" is C1.ml, not C1 -- and without this those rules cannot be
   expressed at all. Twin of resolve() in tools/aimap_constraints.py. */
function resolveRef(answers, ref) {
  if (ref && ref.indexOf('.') !== -1) {
    const [qid, row] = [ref.slice(0, ref.indexOf('.')), ref.slice(ref.indexOf('.') + 1)];
    const cell = answers[qid];
    return (cell && typeof cell === 'object' && !Array.isArray(cell)) ? cell[row] : undefined;
  }
  return answers[ref];
}

function refBase(ref) { return ref ? ref.split('.')[0] : ref; }

function asNumber(v) {
  if (v === null || v === undefined || v === '') return null;   // blank is not zero
  const n = Number(v);
  return Number.isNaN(n) ? null : n;
}

function violates(c, answers) {
  const v = resolveRef(answers, c.field);
  switch (c.type) {
    case 'lte_band': {
      const n = asNumber(v);
      if (n === null) return false;
      const cap = bandMax(c.band_field, answers[c.band_field]);
      return cap != null && n > cap;
    }
    case 'lte_field': {
      const a = asNumber(v), b = asNumber(resolveRef(answers, c.other));
      return a !== null && b !== null && a > b;
    }
    case 'both_at_least': {
      // Two answers that cannot comfortably both be high: the reverse-keyed
      // pairs inside an attitude grid, where agreeing with a statement and its
      // opposite is the signal rather than an error.
      const vals = c.fields.map(r => asNumber(resolveRef(answers, r)));
      if (vals.some(x => x === null)) return false;
      return vals.every(x => x >= c.min);
    }
    case 'year_range': {
      const n = asNumber(v);
      if (n === null) return false;
      // Computed now, never stored: a hard-coded upper year starts rejecting
      // valid answers on the first of January.
      const hi = c.max === 'this_year' ? new Date().getFullYear() : c.max;
      if (c.min != null && n < c.min) return true;
      return hi != null && n > hi;
    }
    case 'includes_field': {
      const other = resolveRef(answers, c.other);
      if (!Array.isArray(v) || !v.length || other == null || other === '') return false;
      return !v.map(String).includes(String(other));
    }
    case 'matrix_any': {
      const grid = answers[c.field];
      if (!grid || typeof grid !== 'object') return false;
      const bad = c.bad_values.map(String);
      const hit = Object.values(grid).some(v => bad.includes(String(v)));
      if (!hit) return false;
      const other = resolveRef(answers, c.other);
      return other != null && c.other_values.map(String).includes(String(other));
    }
    case 'incompatible_pair': {
      const wanted = (c.values || [c.value]).map(String);
      if (!wanted.includes(String(v))) return false;
      const other = resolveRef(answers, c.other);
      return other != null && c.other_values.map(String).includes(String(other));
    }
    default: return false;
  }
}

/* Violations whose blocking field is the question on screen. A respondent must
   be stopped by the question they are looking at, never by one three screens
   back that they can no longer see. */
function constraintViolations(qid) {
  const rules = (INSTR && INSTR.constraints) || [];
  return rules.filter(c => refBase(c.field) === qid && violates(c, state.answers));
}

/* Format rules come from the schema (common.json -> validators) so the web form
   and the Telegram bot accept exactly the same answers. A contact address that
   one channel takes and the other refuses is a respondent the study cannot
   follow up, discovered months later. */
function validatorFor(q) {
  const rules = (COMMON && COMMON.validators) || {};
  return q.validate ? rules[q.validate] : null;
}

function formatOk(q, value) {
  const rule = validatorFor(q);
  if (!rule) return true;
  const v = String(value == null ? '' : value).trim();
  if (!v) return true;                    // emptiness is mustAnswer()'s business
  return new RegExp(rule.pattern).test(v);
}

function showFormatError(q, inp, err) {
  const rule = validatorFor(q);
  if (!rule) return true;
  const ok = formatOk(q, inp.value);
  err.textContent = ok ? '' : rule.message;
  err.hidden = ok;
  inp.classList.toggle('bad', !ok);
  return ok;
}

/* Every question must be answered before the respondent can move on. The only
   exceptions are display-only items and questions the schema explicitly marks
   `optional` -- so which questions may be skipped is a data decision, editable
   in tools/schema/*.json without touching this file. */
function mustAnswer(q) {
  return isCounted(q) && q.type !== 'consent' && !q.optional;
}

/* Fully answered, not merely started: a grid needs every row, a repeatable
   block needs at least one row with something in it. */
function isComplete(q) {
  if (q.type === 'consent') return state.answers[q.id] === true;
  return answeredWeight(q) >= questionWeight(q);
}

function progressStats() {
  let total = 0, done = 0, secTotal = 0, secDone = 0;
  const cur = state.pages[state.page];
  for (const sec of INSTR.sections) {
    if (!showIf(sec.show_if)) continue;
    for (const q of sec.questions) {
      if (!isCounted(q) || !showIf(q.show_if) || !inForm(q)) continue;
      const w = questionWeight(q), a = Math.min(answeredWeight(q), w);
      total += w; done += a;
      if (cur && sec.id === cur.section.id) { secTotal += w; secDone += a; }
    }
  }
  return {
    total, done,
    pct: total ? Math.round(100 * done / total) : 0,
    secTotal, secDone,
    secComplete: secTotal > 0 && secDone >= secTotal
  };
}

/* Is every section before `i` fully answered? Drives the step ticks. */
function sectionComplete(page) {
  let t = 0, d = 0;
  for (const q of page.section.questions) {
    if (!isCounted(q) || !showIf(q.show_if) || !inForm(q)) continue;
    const w = questionWeight(q);
    t += w; d += Math.min(answeredWeight(q), w);
  }
  return t > 0 && d >= t;
}

/* Minutes left, from the schema's own estimate scaled by the work remaining.
   A percentage answers "how far am I"; it does not answer "should I start this
   now", which is the question that decides whether someone begins at all.
   Deliberately coarse and rounded up: a confident "4 minutes" that turns out to
   be seven costs more trust than an honest "about 5". */
function minutesLeft(st) {
  const meta = (COMMON.instruments || []).find(i => i.code === state.code);
  if (!meta || !st.total) return null;
  let budget = meta.est_minutes;
  const sf = COMMON.short_form;
  if (state.form === 'short' && sf && sf.est_minutes && sf.est_minutes[state.code]) {
    budget = sf.est_minutes[state.code];
  }
  const left = budget * (1 - st.done / st.total);
  if (left < 0.75) return 'less than a minute';
  return 'about ' + Math.ceil(left) + ' min';
}

/* Position heartbeat: response_id, how far, and which question, never an answer.
   Without it an abandoned questionnaire leaves nothing behind and drop-off reads
   as zero rather than as unknown, which is the failure that matters. Fired on a
   timer rather than on every keystroke, and silently dropped when offline: this
   is monitoring, and it must never delay or block a respondent. */
let beatTimer = null, lastBeat = '';
function heartbeat(st) {
  // The server records a heartbeat against one of the three instruments and
  // rejects anything else; before R1 is answered state.code is still null, so
  // there is nothing valid to report yet. Section R is two questions, over
  // before the respondent has really started, so skipping it costs nothing.
  if (!state.respId || !state.code || !navigator.onLine) return;
  const page = state.pages[state.page];
  const q = page && page.questions[state.qidx];
  const payload = {
    response_id: state.respId, instrument: state.code, mode: 'web',
    form: state.form, recruit_arm: state.arm,
    last_qid: q ? q.id : null, section_id: page ? page.section.id : null,
    answered: st.done, total: st.total, pct: st.pct,
    started_at: state.startedAt ? new Date(state.startedAt).toISOString() : null
  };
  const key = payload.last_qid + ':' + payload.pct;
  if (key === lastBeat) return;
  lastBeat = key;
  clearTimeout(beatTimer);
  beatTimer = setTimeout(() => {
    fetch(CFG.progressEndpoint, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload), keepalive: true
    }).catch(() => {});
  }, 400);
}

function renderProgress() {
  const st = progressStats();
  $('#progwrap').hidden = false;
  const left = minutesLeft(st);
  const lt = $('#progleft');
  if (lt) lt.textContent = left ? left + ' left' : '';
  heartbeat(st);
  // Overall progress is shown as a bar and a percentage only. The raw
  // "25 of 59 answered" was discouraging out of proportion to what it told the
  // respondent, and the section counter below already says where they are.
  $('#progfill').style.width = st.pct + '%';
  $('#progpct').textContent = st.pct + '%';
  const sec = state.pages[state.page];
  $('#progsec').innerHTML = '';
  $('#progsec').appendChild(el('strong', null, t(sec.section.title)));
  $('#progsec').appendChild(document.createTextNode(`  ·  section ${state.page + 1} of ${state.pages.length}`));

  const track = $('#progtrack');
  track.setAttribute('aria-valuenow', String(st.pct));
  track.setAttribute('aria-valuetext', `${st.pct} percent complete`);

  const steps = $('#progsteps'); steps.innerHTML = '';
  state.pages.forEach((pg, i) => {
    const tick = el('i');
    if (i === state.page) tick.className = 'current';
    else if (sectionComplete(pg)) tick.className = 'done';
    steps.appendChild(tick);
  });

  // Within-section position: one dot per question in this section.
  const dots = $('#subdots'); dots.innerHTML = '';
  sec.questions.forEach((q, i) => {
    const d = el('i');
    if (i === state.qidx) d.className = 'current';
    else if (!isCounted(q) || answeredWeight(q) > 0) d.className = 'done';
    dots.appendChild(d);
  });
  $('#subcount').textContent = `Question ${state.qidx + 1} of ${sec.questions.length}`;

  return st;
}

/*  (: -) pagination: one section per page, sections may be skipped wholesale (: -) */
function buildPages() {
  state.pages = INSTR.sections
    .filter(s => showIf(s.show_if))
    .map(s => ({ section: s, questions: s.questions.filter(visible) }))
    .filter(p => p.questions.length);
}

/*  (: -) rendering (: -) */
function renderOptionList(q, opts, multi) {
  const box = el('div', 'opts');
  const cur = state.answers[q.id];
  // Number keys are only offered where they are unambiguous: a short list.
  const keyable = opts.length <= 9;
  opts.forEach((o, oi) => {
    const lab = el('label', 'opt');
    const inp = document.createElement('input');
    inp.type = multi ? 'checkbox' : 'radio';
    inp.name = q.id; inp.value = o.value;
    if (multi) inp.checked = Array.isArray(cur) && cur.includes(o.value);
    else inp.checked = String(cur) === String(o.value);
    if (inp.checked) lab.classList.add('sel');
    inp.addEventListener('change', () => {
      if (multi) {
        let arr = Array.isArray(state.answers[q.id]) ? state.answers[q.id].slice() : [];
        if (inp.checked) {
          // "exclusive" options (e.g. "None of these") clear everything else, and vice versa
          if (o.exclusive) arr = [o.value];
          else { arr = arr.filter(v => !(opts.find(x => x.value === v) || {}).exclusive); arr.push(o.value); }
          if (q.max_select && arr.length > q.max_select) { arr.shift(); }
        } else arr = arr.filter(v => v !== o.value);
        state.answers[q.id] = arr;
      } else {
        state.answers[q.id] = o.value;
        // R1 is the routing question: it decides which of the three branches
        // the rest of the questionnaire follows. The schema keeps every branch
        // section hidden (show_if) until R1 is answered, so state.code is safe
        // to leave unset until this exact moment. state.pages is rebuilt right
        // away, not left for the next render: isLastQuestion() below reads it,
        // and until it is rebuilt it still reflects the old routing, where R1
        // (nothing yet visible past it) looks like the final question.
        if (q.id === 'R1') {
          state.code = { organization: 'ORG', practitioner: 'IND', citizen: 'CIT' }[o.value] || null;
          buildPages();
        }
      }
      saveDraft();
      // A single-choice answer advances by itself, as tapping an option does in
      // the Telegram bot. Multi-select and everything else wait for Next, since
      // there is no way to know the respondent has finished choosing.
      // The pause lets the selection register visually before the screen changes.
      if (!multi && !o.allow_text && !isLastQuestion()) {
        lab.classList.add('sel');
        // The length choice used to be asked up front, next to the now-removed
        // instrument picker. It still belongs right after the respondent says
        // which branch applies, so it is offered here, before stepping into
        // that branch's own first question, instead of on an advance timer.
        if (q.id === 'R1' && shortFormAllowed(state.code)) scheduleLengthScreen();
        else scheduleAdvance(q.id);
      } else {
        renderPage();               // re-render: routing may have changed
      }
    });
    lab.appendChild(inp);
    lab.appendChild(el('span', null, t(o.label)));
    if (keyable) lab.appendChild(el('kbd', null, String(oi + 1)));
    box.appendChild(lab);

    if (o.allow_text && ((multi && Array.isArray(cur) && cur.includes(o.value)) || (!multi && String(cur) === String(o.value)))) {
      /* "Other" with nowhere to say what records that the option list was wrong
         without recording what was missing. Labelled rather than placeholder-only:
         a placeholder disappears the moment someone types, taking the question
         with it, and screen readers do not announce it as a label. */
      const wrap = el('div', 'otherbox');
      const id = 'other-' + q.id;
      const lab = el('label', 'otherlab', `Please tell us what: “${t(o.label)}”`);
      lab.htmlFor = id;
      const ti = document.createElement('input');
      ti.type = 'text'; ti.id = id; ti.placeholder = 'Type it here';
      ti.value = state.answers[q.id + '_text'] || '';
      ti.addEventListener('input', () => { state.answers[q.id + '_text'] = ti.value; saveDraft(); });
      wrap.appendChild(lab); wrap.appendChild(ti);
      box.appendChild(wrap);
      // Focus it, but never steal focus from someone mid-keyboard-navigation.
      if (!ti.value && document.activeElement === inp) setTimeout(() => ti.focus(), 300);
    }
  });
  if (q.max_select) box.appendChild(el('p', 'fine', `Choose up to ${q.max_select}.`));
  return box;
}

function renderScale(q) {
  const wrap = el('div');
  const row = el('div', 'scale');
  for (let i = q.scale.min; i <= q.scale.max; i++) {
    const b = el('button', String(state.answers[q.id]) === String(i) ? 'sel' : '', String(i));
    b.type = 'button';
    b.addEventListener('click', () => { state.answers[q.id] = String(i); saveDraft(); renderPage(); });
    row.appendChild(b);
  }
  wrap.appendChild(row);
  const ends = el('div', 'scale-ends');
  ends.appendChild(el('span', null, t(q.scale.min_label)));
  ends.appendChild(el('span', null, t(q.scale.max_label)));
  wrap.appendChild(ends);
  return wrap;
}

function renderGrid(q, rows, cols) {
  const wrap = el('div', 'gridwrap');
  const noun = q.row_noun || 'item';
  const cap = el('p', 'gridcap');
  cap.appendChild(el('span', 'gridcap-n', `${rows.length} ${noun}${rows.length === 1 ? '' : 's'}`));
  cap.appendChild(document.createTextNode('\u00a0: answer every row'));
  const tally = el('span', 'gridtally');
  cap.appendChild(tally);
  wrap.appendChild(cap);
  wrap.dataset.qid = q.id;
  const tbl = el('table', 'grid');
  const thead = el('thead'); const hr = el('tr');
  hr.appendChild(el('th'));
  cols.forEach(c => hr.appendChild(el('th', null, t(c.label))));
  thead.appendChild(hr); tbl.appendChild(thead);
  const tb = el('tbody');
  const cur = state.answers[q.id] || {};
  rows.forEach((r, ri) => {
    const tr = el('tr');
    const done = cur[r.value] !== undefined && cur[r.value] !== '';
    if (done) tr.className = 'answered';
    /* Each row is a question in its own right -- a ten-row grid asks ten of them
       off one stem -- so it is numbered and marked like one. Without that the
       rows read as a wall and the respondent cannot see which they have left. */
    const label = el('td');
    // The digit is wrapped so the answered state can swap it for a tick; a bare
    // text node cannot be hidden by a CSS child selector.
    const num = el('span', 'rownum');
    num.appendChild(el('i', null, String(ri + 1)));
    label.appendChild(num);
    label.appendChild(el('span', 'rowlabel', t(r.label)));
    tr.appendChild(label);
    cols.forEach(c => {
      const td = el('td');
      const inp = document.createElement('input');
      inp.type = 'radio'; inp.name = q.id + '__' + r.value; inp.value = c.value;
      inp.checked = String(cur[r.value]) === String(c.value);
      inp.addEventListener('change', () => {
        const o = Object.assign({}, state.answers[q.id] || {});
        o[r.value] = c.value; state.answers[q.id] = o; saveDraft();
        tr.className = 'answered';
        const got = Object.values(o).filter(x => x !== undefined && x !== '').length;
        tally.textContent = `\u00a0\u00a0·\u00a0${got} of ${rows.length} done`;
        tally.classList.toggle('complete', got >= rows.length);
        renderProgress();          // grids fill row by row; keep the bar live
      });
      td.appendChild(inp); tr.appendChild(td);
    });
    tb.appendChild(tr);
  });
  tbl.appendChild(tb); wrap.appendChild(tbl);
  const got = Object.values(cur).filter(x => x !== undefined && x !== '').length;
  if (got) {
    tally.textContent = `\u00a0\u00a0·\u00a0${got} of ${rows.length} done`;
    tally.classList.toggle('complete', got >= rows.length);
  }
  return wrap;
}

function renderRepeatable(q) {
  const wrap = el('div');
  const rows = state.answers[q.id] || [{}];
  rows.forEach((row, i) => {
    const box = el('div', 'rep');
    box.appendChild(el('h4', null, `#${i + 1}`));
    q.fields.forEach(f => {
      const fld = el('div', 'fld');
      fld.appendChild(el('label', null, t(f.label)));
      if (f.type === 'single' || f.type === 'multi') {
        const opts = f.options || resolveOptions(f);
        if (f.type === 'single') {
          const sel = document.createElement('select');
          sel.appendChild(new Option('-', ''));
          opts.forEach(o => sel.appendChild(new Option(t(o.label), o.value)));
          sel.value = row[f.id] || '';
          sel.addEventListener('change', () => { row[f.id] = sel.value; state.answers[q.id] = rows; saveDraft(); });
          fld.appendChild(sel);
        } else {
          const inner = el('div', 'opts');
          opts.forEach(o => {
            const lab = el('label', 'opt');
            const inp = document.createElement('input'); inp.type = 'checkbox';
            inp.checked = (row[f.id] || []).includes(o.value);
            inp.addEventListener('change', () => {
              let a = row[f.id] || [];
              a = inp.checked ? a.concat([o.value]) : a.filter(x => x !== o.value);
              row[f.id] = a; state.answers[q.id] = rows; saveDraft();
            });
            lab.appendChild(inp); lab.appendChild(el('span', null, t(o.label))); inner.appendChild(lab);
          });
          fld.appendChild(inner);
        }
      } else if (f.type === 'month_year') {
        const inp = document.createElement('input'); inp.type = 'month';
        inp.value = row[f.id] || '';
        inp.addEventListener('input', () => { row[f.id] = inp.value; state.answers[q.id] = rows; saveDraft(); });
        fld.appendChild(inp);
      } else {
        const inp = document.createElement('input');
        inp.type = f.type === 'number' ? 'number' : 'text';
        inp.value = row[f.id] || '';
        inp.addEventListener('input', () => { row[f.id] = inp.value; state.answers[q.id] = rows; saveDraft(); });
        fld.appendChild(inp);
      }
      box.appendChild(fld);
    });
    wrap.appendChild(box);
  });
  if (rows.length < (q.max_items || 5)) {
    const add = el('button', 'btn ghost', '+ Add another');
    add.type = 'button';
    add.addEventListener('click', () => { rows.push({}); state.answers[q.id] = rows; saveDraft(); renderPage(); });
    wrap.appendChild(add);
  }
  return wrap;
}

/* Shared with the Telegram bot, deliberately: the same glyph and the same words
   for the same kind of question, so a respondent who switches channels is not
   relearning the interface. */
const TYPE_BADGE = {
  consent:     ['📋', 'Please read and confirm'],
  single:      ['🔘', 'Choose one'],
  multi:       ['☑️', 'Choose any that apply'],
  checklist:   ['☑️', 'Tick everything that is true'],
  likert_grid: ['📊', 'Rate each one'],
  matrix:      ['📊', 'Rate each one'],
  scale:       ['🎚', 'Pick a number'],
  text:        ['✍️', 'Type your answer'],
  longtext:    ['✍️', 'Type your answer'],
  number:      ['🔢', 'Type a number'],
  email:       ['✉️', 'Type your email address'],
  phone:       ['📞', 'Type your phone number'],
  repeatable:  ['➕', 'Add one row per item'],
};

function renderQuestion(q) {
  const card = el('div', 'q' + (q.required ? ' req' : ''));
  card.dataset.qid = q.id;

  if (q.type === 'consent') {
    card.appendChild(el('p', 'qtext', t(COMMON.consent.text)));
    // Wrapped in .opts so keyboard selection reaches it like any other choice.
    const box = el('div', 'opts');
    const lab = el('label', 'opt');
    const inp = document.createElement('input'); inp.type = 'checkbox';
    inp.checked = state.answers[q.id] === true;
    if (inp.checked) lab.classList.add('sel');
    inp.addEventListener('change', () => {
      state.answers[q.id] = inp.checked;
      lab.classList.toggle('sel', inp.checked);
      saveDraft(); renderProgress();
    });
    lab.appendChild(inp);
    lab.appendChild(el('span', null, t(COMMON.consent.affirm)));
    lab.appendChild(el('kbd', null, '1'));
    box.appendChild(lab);
    card.appendChild(box);
    card.appendChild(el('p', 'fine', COMMON.consent.controller));
    return card;
  }

  /* A badge naming the kind of answer wanted. The web can do what Telegram
     cannot -- a distinct colour per type -- so the two channels carry the same
     glyph and wording, and the web adds colour on top rather than instead. */
  const badge = TYPE_BADGE[q.type];
  if (badge && q.type !== 'info') {
    const b = el('p', 'qbadge t-' + q.type);
    b.appendChild(el('span', 'qbadge-ico', badge[0]));
    b.appendChild(document.createTextNode(badge[1]));
    if (q.max_select) b.appendChild(el('span', 'qbadge-max', `up to ${q.max_select}`));
    card.appendChild(b);
  }

  const head = el('div', 'qhead');
  head.appendChild(el('span', 'qnum', q.id));
  const stem = el('p', 'qtext', t(q.text));
  if (q.required) { const r = el('span', 'req-star', ' *'); r.title = 'Required'; stem.appendChild(r); }
  head.appendChild(stem);
  card.appendChild(head);
  if (q.help) card.appendChild(el('p', 'qhelp', t(q.help)));
  if (q.type === 'info') return card;

  if (q.flags && q.flags.includes('honeypot')) {
    card.className = 'hp';
    const inp = document.createElement('input'); inp.type = 'text'; inp.tabIndex = -1; inp.autocomplete = 'off';
    inp.addEventListener('input', () => { state.answers.__hp = inp.value; });
    card.appendChild(inp);
    return card;
  }

  switch (q.type) {
    case 'single':    card.appendChild(renderOptionList(q, resolveOptions(q), false)); break;
    case 'multi':
    case 'checklist': card.appendChild(renderOptionList(q, resolveOptions(q), true)); break;
    case 'scale':     card.appendChild(renderScale(q)); break;
    case 'likert_grid': card.appendChild(renderGrid(q, q.rows, q.scale)); break;
    case 'matrix':    card.appendChild(renderGrid(q, q.row_options, q.col_options)); break;
    case 'repeatable':card.appendChild(renderRepeatable(q)); break;
    case 'longtext': {
      const ta = document.createElement('textarea');
      ta.value = state.answers[q.id] || '';
      ta.addEventListener('input', () => { state.answers[q.id] = ta.value; saveDraft(); renderProgress(); });
      card.appendChild(ta); break;
    }
    default: {
      const inp = document.createElement('input');
      inp.type = q.type === 'email' ? 'email'
               : q.type === 'phone' ? 'tel'
               : q.type === 'number' ? 'number' : 'text';
      const rule = validatorFor(q);
      if (rule) {
        inp.placeholder = rule.placeholder || '';
        if (rule.inputmode) inp.inputMode = rule.inputmode;
        inp.setAttribute('aria-describedby', 'fmt-' + q.id);
      }
      if (q.validation) { if (q.validation.min != null) inp.min = q.validation.min; if (q.validation.max != null) inp.max = q.validation.max; }
      inp.value = state.answers[q.id] || '';
      const err = el('p', 'fielderr'); err.id = 'fmt-' + q.id; err.hidden = true;
      inp.addEventListener('input', () => {
        state.answers[q.id] = inp.value; saveDraft(); renderProgress();
        // Clear the complaint as soon as they start fixing it; re-checked on Next.
        err.hidden = true; inp.classList.remove('bad');
      });
      inp.addEventListener('blur', () => showFormatError(q, inp, err));
      card.appendChild(inp);
      card.appendChild(err);
    }
  }
  return card;
}

/*  (: -) length choice (: -) A pseudo-step, not a schema question: it decides state.form, which in turn
   decides which questions inForm() lets through, rather than being an answer
   itself. Shown once, right after R1 is answered, for whichever branch the
   schema's short_form.enabled_for actually covers; skipped entirely otherwise. */
let lengthPending = false;

function syncLength() {
  const code = state.code;
  const sf = COMMON.short_form;
  if (!code || !shortFormAllowed(code)) { $('#lenfs').hidden = true; return; }
  const meta = COMMON.instruments.find(i => i.code === code);
  const shortMin = (sf.est_minutes || {})[code];
  $('#lenseg').querySelectorAll('button').forEach(b => {
    b.setAttribute('aria-pressed', String(b.dataset.form === state.form));
    b.textContent = b.dataset.form === 'short'
      ? `${sf.label} · about ${shortMin} min`
      : `${sf.long_label} · about ${meta.est_minutes} min`;
  });
  $('#lenhint').textContent = state.form === 'short'
    ? 'The quick version asks the essential questions only. Every answer still counts.'
    : 'The full version adds the detail that makes sector comparisons possible.';
}

function renderLengthScreen() {
  lengthPending = true;
  $('#qform').innerHTML = '';
  $('#secmeta').textContent = 'Before you begin';
  syncLength();
  $('#lenfs').hidden = false;
  $('#counter').textContent = '';
  $('#back').disabled = false;
  $('#next').textContent = 'Continue →';
  $('#next').classList.remove('done');
  $('#hint').textContent = 'Choose quick or full, then continue.';
  $('#skip').hidden = true;
  const rv = $('#reviewbar'); if (rv) rv.hidden = true;
  announce('How much time do you have? Choose quick or full version.');
  window.scrollTo({ top: 0, behavior: 'smooth' });
}

/* One question per screen. Long sections were previously rendered as a single
   scrolling list, which buried the navigation and made the respondent's position
   impossible to judge; it also diverged from the Telegram bot, which has always
   asked one question per message. Both channels now step identically. */
function renderPage() {
  lengthPending = false;
  $('#lenfs').hidden = true;   // normal question render: the length pseudo-step is over
  buildPages();
  if (state.page >= state.pages.length) state.page = state.pages.length - 1;
  if (state.page < 0) state.page = 0;
  const p = state.pages[state.page];
  if (state.qidx >= p.questions.length) state.qidx = p.questions.length - 1;
  if (state.qidx < 0) state.qidx = 0;

  const form = $('#qform'); form.innerHTML = '';
  $('#secmeta').textContent = t(p.section.title);
  if (state.qidx === 0 && p.section.help) {
    const h = el('p', 'qhelp', t(p.section.help));
    h.style.marginBottom = '14px';
    form.appendChild(h);
  }
  form.appendChild(renderQuestion(p.questions[state.qidx]));
  const st = renderProgress();
  const lastQ = isLastQuestion();
  $('#counter').textContent = `Question ${state.qidx + 1} of ${p.questions.length} in this section`;
  $('#back').disabled = state.page === 0 && state.qidx === 0;
  /* On a multi-select nothing tells the form that the respondent has finished
     choosing, so Next IS the Done button and says so, with a running count that
     doubles as confirmation a tick registered. Single-choice questions advance
     by themselves and keep the plain label.

     Set HERE rather than in renderProgress(): this line runs last and would
     otherwise overwrite it, which is exactly what it did on the first attempt. */
  const curr = p.questions[state.qidx];
  const multi = curr && (curr.type === 'multi' || curr.type === 'checklist');
  const picked = multi && Array.isArray(state.answers[curr.id])
    ? state.answers[curr.id].length : 0;
  $('#next').textContent = lastQ ? 'Submit ✓'
    : multi ? (picked ? `✓ Done · ${picked} selected` : 'Done when ready →')
    : 'Next →';
  $('#next').classList.toggle('done', !!multi && picked > 0);

  /* During a review both controls matter. Without Keep, changing one answer near
     the end means clicking through everything before it; without Finish, the only
     way out is to reach the last question, which is exactly what someone who came
     back to fix one thing will not do. */
  const rv = $('#reviewbar');
  if (rv) rv.hidden = !state.review;
  $('#hint').textContent = lastQ
    ? 'This is the last question. Submitting sends your response.'
    : 'Press 1-9 to choose, Enter to continue, Alt+← to go back.';
  // Skip is offered only where the schema says the question is optional.
  const curQ = p.questions[state.qidx];
  $('#skip').hidden = !(curQ && curQ.optional && !isComplete(curQ));
  announce(`${t(p.section.title)}, section ${state.page + 1} of ${state.pages.length}. `
         + `Question ${state.qidx + 1} of ${p.questions.length}. ${st.pct} percent complete.`);
  window.scrollTo({ top: 0, behavior: 'smooth' });
}

const isLastQuestion = () =>
  state.page === state.pages.length - 1 &&
  state.qidx === state.pages[state.page].questions.length - 1;

/* Step one question forward/back, crossing section boundaries. Returns false at
   the very start or the very end. */
/*  (: -) auto-advance, guarded (: -) A single-choice answer advances on a short delay so the selection is visible
   before the screen changes. That delay is a window in which the old options are
   still on screen and still live, and anything that fires a second change event
   inside it -- a double tap, an impatient second choice, a synthetic click from a
   test driver -- used to queue a SECOND advance. The result was a question
   stepped past without ever being answered, which is precisely the guarantee the
   questionnaire is supposed to make.

   Three rules close it: only one advance can ever be pending; the pending
   advance belongs to a named question and does nothing if the screen has since
   moved; and it re-checks that the question is actually complete before
   stepping. Manual navigation cancels it outright -- otherwise tapping an option
   and immediately pressing Back lands the respondent a question further on than
   they asked for. */

let advanceTimer = null;

function currentQuestion() {
  const p = state.pages[state.page];
  return p && p.questions[state.qidx];
}

function cancelAdvance() {
  if (advanceTimer !== null) { clearTimeout(advanceTimer); advanceTimer = null; }
}

function scheduleAdvance(qid) {
  cancelAdvance();
  advanceTimer = setTimeout(() => {
    advanceTimer = null;
    const q = currentQuestion();
    if (!q || q.id !== qid) return;     // the screen already moved on
    if (mustAnswer(q) && !isComplete(q)) return;   // never step past an unanswered question
    if (step(+1)) { saveDraft(); renderPage(); }
  }, 260);
}

// Same pause and the same guard against a stale timer, but the destination is
// the length-choice pseudo-step rather than the next real question. Only ever
// scheduled from answering R1, so there is no qid to re-check: if the screen
// has moved on by the time this fires, renderPage()/renderLengthScreen() calls
// elsewhere will already have taken care of what is on screen.
function scheduleLengthScreen() {
  cancelAdvance();
  advanceTimer = setTimeout(() => {
    advanceTimer = null;
    renderLengthScreen();
  }, 260);
}

function step(dir) {
  cancelAdvance();
  // Rebuild first: the answer just given may have opened or closed a branch, and
  // navigating on a stale page list would skip questions it has revealed (or
  // land on ones it has just hidden).
  buildPages();
  if (state.page >= state.pages.length) state.page = state.pages.length - 1;
  const p = state.pages[state.page];
  if (state.qidx > p.questions.length - 1) state.qidx = p.questions.length - 1;
  if (dir > 0) {
    if (state.qidx < p.questions.length - 1) { state.qidx++; return true; }
    if (state.page < state.pages.length - 1) { state.page++; state.qidx = 0; return true; }
    return false;
  }
  if (state.qidx > 0) { state.qidx--; return true; }
  if (state.page > 0) {
    state.page--;
    buildPages();
    state.qidx = Math.max(0, state.pages[state.page].questions.length - 1);
    return true;
  }
  return false;
}

/*  (: -) validation (: -) */
function validatePage() {
  document.querySelectorAll('.err').forEach(n => n.remove());
  document.querySelectorAll('.q.invalid').forEach(n => n.classList.remove('invalid'));
  const p = state.pages[state.page];
  let ok = true, missing = 0;
  // Only the question currently on screen is validated -- the rest of the
  // section has not been shown yet.
  for (const q of [p.questions[state.qidx]]) {
    if (!q) continue;
    if (q.type === 'consent') {
      if (state.answers[q.id] !== true) {
        ok = false; missing++;
        const card = document.querySelector(`[data-qid="${q.id}"]`);
        if (card) {
          card.classList.add('invalid');
          card.appendChild(el('p', 'err', 'Please confirm consent to continue.'));
        }
      }
      continue;
    }
    // Consistency with OTHER answers, checked before emptiness so the more
    // specific complaint wins: "that is more IT staff than you have employees"
    // is more use than "please answer this question".
    for (const c of constraintViolations(q.id)) {
      if (c.severity !== 'block') continue;
      ok = false; missing++;
      const card = document.querySelector(`[data-qid="${q.id}"]`);
      if (card) {
        card.classList.add('invalid');
        const inp = card.querySelector('input');
        if (inp) inp.classList.add('bad');
        card.appendChild(el('p', 'err', t(c.message)));
      }
      break;
    }
    if (!ok) continue;

    // A well-formed answer is a separate test from a present one: an address
    // typed as "user@" passes isComplete(), and is useless for follow-up.
    if (!formatOk(q, state.answers[q.id])) {
      ok = false; missing++;
      const card = document.querySelector(`[data-qid="${q.id}"]`);
      if (card) {
        card.classList.add('invalid');
        const inp = card.querySelector('input');
        if (inp) inp.classList.add('bad');
        card.appendChild(el('p', 'err', validatorFor(q).message));
      }
      continue;
    }
    if (!mustAnswer(q)) continue;
    const empty = !isComplete(q);
    if (empty) {
      ok = false; missing++;
      const card = document.querySelector(`[data-qid="${q.id}"]`);
      if (card) {
        card.classList.add('invalid');
        const partial = answeredWeight(q) > 0;
        card.appendChild(el('p', 'err',
          (q.type === 'likert_grid' || q.type === 'matrix')
            ? (partial ? 'Please answer every row before continuing.'
                       : 'Please answer each row before continuing.')
          : q.type === 'repeatable' ? 'Please complete at least one entry before continuing.'
          : 'Please answer this question before continuing.'));
      }
    }
  }
  if (!ok) {
    const first = document.querySelector('.q.invalid');
    if (first) { first.scrollIntoView({ behavior: 'smooth', block: 'center' });
                 const f = first.querySelector('input,textarea,select,button');
                 if (f) f.focus({ preventScroll: true }); }
    announce('Please answer this question before continuing.');
  }
  return ok;
}

/*  (: -) scoring (computed at submit; mirrors the analysis plan) (: -) */
function computeScores() {
  const s = {};
  const a = state.answers;
  if (state.code === 'ORG') {
    const chk = Array.isArray(a.D5) ? a.D5 : [];
    const q = findQuestion('D5');
    const pts = (q ? q.options : []).filter(o => chk.includes(o.value)).reduce((n, o) => n + (o.points || 0), 0);
    s.maturity_points = pts;                      // continuous index, kept for regression
    // Gated ladder: a level is awarded only when its structural evidence is present.
    // An additive threshold would let training + planning alone reach "deployed", which is
    // precisely the over-claiming this instrument exists to detect. See common.json
    // maturity_ladder.computed_rule: the bot and analysis scripts apply the same gates.
    const has = k => chk.includes(k);
    const real = chk.filter(v => v !== 'none' && v !== 'e14');
    let lvl = 0;
    if (real.length) lvl = 1;
    if (has('e3')) lvl = 2;
    if (has('e4')) lvl = 3;
    if (has('e4') && (has('e9') || (has('e6') && has('e7')))) lvl = 4;
    if (lvl === 4 && has('e13') && (has('e7') || has('e11'))) lvl = 5;
    s.maturity_computed = lvl;
    s.maturity_self = a.D4 != null ? parseInt(a.D4) : null;
    s.maturity_gap = (s.maturity_self != null) ? s.maturity_self - s.maturity_computed : null;
    s.flag_planted = chk.includes('e14');
    const dq = findQuestion('C2');
    if (dq && Array.isArray(a.C2)) {
      const correct = dq.options.filter(o => o.correct).map(o => o.value);
      const wrong = dq.options.filter(o => o.correct === false).map(o => o.value);
      const hit = correct.filter(v => a.C2.includes(v)).length;
      const fp = wrong.filter(v => a.C2.includes(v)).length;
      s.definition_accuracy = (hit - fp) / correct.length;
      s.flag_definition = fp >= 2;
    }
    s.digital_baseline_index = Array.isArray(a.B1) ? a.B1.filter(v => v !== 'none').length : 0;
    s.data_governance_index = Array.isArray(a.F3) ? a.F3.filter(v => v !== 'none').length : 0;

    // Technical depth: are we building AI, or only adopting it? Gated exactly as
    // in tools/scripts/scoring.py. Level 4 additionally requires level-3
    // evidence, because "trained from scratch" with no fine-tuning capability
    // beneath it is far more likely to be a misread question.
    const t = Array.isArray(a.T2) ? a.T2 : [];
    const tHas = k => t.includes(k);
    let tl = 0;
    if (tHas('t1')) tl = 1;
    if (tHas('t2') || tHas('t3')) tl = 2;
    if (tHas('t4') || tHas('t5')) tl = 3;
    if (tHas('t6') && (tHas('t4') || tHas('t5'))) tl = 4;
    s.technical_computed = tl;
    s.technical_self = a.T1 != null ? parseInt(a.T1) : null;
    s.technical_gap = s.technical_self != null ? s.technical_self - tl : null;
    s.trains_on_ethiopian_data = tHas('t5');
    s.flag_scratch_unsupported = tHas('t6') && !['t2','t3','t4','t5'].some(tHas);
    // Vendor-hosted inference with no in-house diagnosis is a purchased service,
    // not a capability.
    s.capability_not_procurement = ['2','3'].includes(String(a.T5)) && a.T4 !== 'vendor';
    s.sector = a.S3 || null;
  }

  // These are advisory only: the collection server recomputes every score from
  // the reference implementation on ingest and keeps this copy separately, so a
  // stale cached build here cannot move a published figure.
  s.scored_by = 'client';
  if (state.code === 'IND') {
    const aq = findQuestion('G5');
    if (aq && a.G5 != null) s.flag_attention = String(a.G5) !== String(aq.expected);
    if (a.F3 && typeof a.F3 === 'object') {
      const items = ['intent1', 'intent2', 'intent3'].map(k => parseFloat(a.F3[k])).filter(x => !isNaN(x));
      if (items.length) s.emigration_intention = items.reduce((x, y) => x + y, 0) / items.length;
    }
  }
  s.flag_honeypot = !!a.__hp;
  s.duration_seconds = state.startedAt ? Math.round((Date.now() - state.startedAt) / 1000) : null;
  s.flag_speeder = s.duration_seconds != null && s.duration_seconds < 90;
  return s;
}

/*  (: -) persistence (: -) */
function saveDraft() {
  try { localStorage.setItem(CFG.draftKey, JSON.stringify(state)); flashSaved(); } catch (e) {}
}
function clearDraft() { try { localStorage.removeItem(CFG.draftKey); } catch (e) {} }
function queueGet() { try { return JSON.parse(localStorage.getItem(CFG.qKey) || '[]'); } catch (e) { return []; } }
function queueSet(q) { try { localStorage.setItem(CFG.qKey, JSON.stringify(q)); } catch (e) {} }

function rememberCompletion(rec) {
  try {
    localStorage.setItem(CFG.doneKey, JSON.stringify({
      response_id: rec.response_id, instrument: rec.instrument,
      submitted_at: rec.submitted_at, revision: rec.revision || 0
    }));
  } catch (e) {}
}

function lastCompletion() {
  try { return JSON.parse(localStorage.getItem(CFG.doneKey) || 'null'); }
  catch (e) { return null; }
}

function buildRecord() {
  const a = Object.assign({}, state.answers);
  delete a.__hp;
  return {
    response_id: state.respId,
    instrument: state.code,
    instrument_version: COMMON.version,
    language: LANG,
    started_at: new Date(state.startedAt).toISOString(),
    submitted_at: new Date().toISOString(),
    mode: state.enumerator ? 'enumerator' : 'web',
    form: state.form,
    revision: state.revision || 0,
    recruit_arm: state.arm,
    referrer: state.referrer,
    enumerator: state.enumerator,
    answers: a,
    scores: computeScores()
  };
}

async function flushQueue() {
  const q = queueGet(); if (!q.length) return { sent: 0, left: 0 };
  const left = []; let sent = 0;
  for (const rec of q) {
    try {
      const r = await fetch(CFG.endpoint, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(rec) });
      if (r.ok) sent++; else left.push(rec);
    } catch (e) { left.push(rec); }
  }
  queueSet(left);
  return { sent, left: left.length };
}

async function submit() {
  const rec = buildRecord();
  rememberCompletion(rec);
  const q = queueGet(); q.push(rec); queueSet(q);
  clearDraft();
  const res = await flushQueue();
  $('#survey').hidden = true; $('#done').hidden = false; $('#progwrap').hidden = true;
  // The offline case is not a failure and must not read like one: the response
  // is safe on the device and will go by itself.
  if (state.review) $('.done-title').textContent = 'Saved';
  $('#donemsg').textContent = res.left === 0
    ? (state.review ? `Your answers have been updated (revision ${state.revision}).`
                    : 'Your answers have been recorded.')
    : `Your answers are saved on this device (${res.left} waiting to send) and will go automatically when there is a connection. You can close this page safely.`;
  $('#dl').onclick = () => downloadJSON([rec], `aimap-${rec.instrument}-${rec.response_id.slice(0, 8)}.json`);
  offerInvite(rec);
  updateNet();
}

/* An invitation link for the respondent-driven arm. Shown only for the
   instruments that use that arm, and only once the response is in -- inviting
   before finishing would seed the chain from someone who never answered. */
function offerInvite(rec) {
  const box = $('#invitebox');
  if (!box) return;
  const arms = ((COMMON.recruitment || {}).arms || [])
    .find(a => a.code === 'referral');
  if (!arms || !(arms.applies_to || []).includes(rec.instrument)) { box.hidden = true; return; }
  box.hidden = false;
  $('#inviteout').hidden = true;
  $('#makeinvite').onclick = async () => {
    $('#makeinvite').disabled = true;
    try {
      const r = await fetch(CFG.referralEndpoint, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ response_id: rec.response_id, instrument: rec.instrument })
      });
      const j = await r.json();
      if (!j.ok) throw new Error('no code');
      const url = location.origin + location.pathname + '?ref=' + j.code;
      $('#invitelink').textContent = url;
      $('#inviteout').hidden = false;
      $('#copyinvite').onclick = async () => {
        try { await navigator.clipboard.writeText(url); $('#copyinvite').textContent = 'Copied'; }
        catch (e) { $('#copyinvite').textContent = 'Select the link above to copy it'; }
      };
      announce('Invitation link created');
    } catch (e) {
      $('#makeinvite').textContent = 'Could not create a link; you may be offline';
    } finally {
      $('#makeinvite').disabled = false;
    }
  };
}

function downloadJSON(obj, name) {
  const b = new Blob([JSON.stringify(obj, null, 2)], { type: 'application/json' });
  const u = URL.createObjectURL(b); const a = document.createElement('a');
  a.href = u; a.download = name; a.click(); URL.revokeObjectURL(u);
}
function downloadCSV(records, name) {
  const keys = new Set(['response_id', 'instrument', 'language', 'started_at', 'submitted_at', 'mode']);
  records.forEach(r => { Object.keys(r.answers || {}).forEach(k => keys.add('a_' + k)); Object.keys(r.scores || {}).forEach(k => keys.add('s_' + k)); });
  const cols = [...keys];
  const cell = v => v == null ? '' : `"${(typeof v === 'object' ? JSON.stringify(v) : String(v)).replace(/"/g, '""')}"`;
  const lines = [cols.join(',')];
  records.forEach(r => lines.push(cols.map(c =>
    c.startsWith('a_') ? cell((r.answers || {})[c.slice(2)]) :
    c.startsWith('s_') ? cell((r.scores || {})[c.slice(2)]) : cell(r[c])).join(',')));
  const b = new Blob(['﻿' + lines.join('\n')], { type: 'text/csv;charset=utf-8' });
  const u = URL.createObjectURL(b); const a = document.createElement('a');
  a.href = u; a.download = name; a.click(); URL.revokeObjectURL(u);
}

/*  (: -) keyboard navigation (: -) Number keys pick an option, Enter advances. Scoped to the question the user
   is actually in: whichever .q contains focus, else the first unanswered choice
   question on the page -- so a stray keypress cannot silently answer something
   further down that the respondent has not read. */

function activeChoiceCard() {
  const inFocus = document.activeElement && document.activeElement.closest('.q');
  if (inFocus && inFocus.querySelector('.opts')) return inFocus;
  const cards = [...document.querySelectorAll('.q')].filter(c => c.querySelector('.opts'));
  return cards.find(c => !c.querySelector('.opt.sel')) || cards[0] || null;
}

function onKey(e) {
  // Intro screen: Enter starts the questionnaire.
  if (!$('#picker').hidden) {
    if (e.metaKey || e.ctrlKey) return;
    if (e.key === 'Enter') { e.preventDefault(); $('#pnext').click(); }
    return;
  }
  if ($('#survey').hidden) return;
  const tag = (e.target.tagName || '').toLowerCase();
  const typing = tag === 'textarea' || tag === 'select' ||
    (tag === 'input' && !['radio', 'checkbox'].includes(e.target.type));
  if (e.metaKey || e.ctrlKey) return;

  // Enter advances, except while typing in a textarea.
  if (e.key === 'Enter' && !(tag === 'textarea')) { e.preventDefault(); $('#next').click(); return; }
  if (e.altKey && e.key === 'ArrowRight') { e.preventDefault(); $('#next').click(); return; }
  if (e.altKey && e.key === 'ArrowLeft')  { e.preventDefault(); $('#back').click(); return; }
  if (typing) return;

  if (/^[1-9]$/.test(e.key)) {
    const card = activeChoiceCard(); if (!card) return;
    const opts = [...card.querySelectorAll('.opt')];
    const pick = opts[parseInt(e.key, 10) - 1];
    if (!pick) return;
    e.preventDefault();
    const input = pick.querySelector('input');
    input.checked = input.type === 'checkbox' ? !input.checked : true;
    input.dispatchEvent(new Event('change', { bubbles: true }));
    announce(pick.querySelector('span').textContent);
  }
}

/*  (: -) boot (: -) */
function updateNet() {
  const n = $('#netstat'); const pend = queueGet().length;
  if (!navigator.onLine) { n.textContent = pend ? `offline · ${pend} queued` : 'offline'; n.classList.add('off'); }
  else { n.textContent = pend ? `${pend} queued` : 'online'; n.classList.remove('off'); }
  const qc = $('#qcount'); if (qc) qc.textContent = pend;
}

/* Begins the one questionnaire. INSTR is already loaded (init() loads the
   merged schema once, up front, since every instrument code resolves to the
   same file now); which branch the respondent is in is not yet known, so
   state.code stays null until R1 is answered. */
function startQuestionnaire() {
  state = Object.assign({}, state, {
    code: null, answers: {}, page: 0, qidx: 0, pages: [], startedAt: Date.now(), respId: uid()
  });
  $('#picker').hidden = true; $('#done').hidden = true; $('#survey').hidden = false;
  $('#progwrap').hidden = false;
  renderPage();
}

/* Reload a submitted response and walk it from the start, with every answer
   already in place. The same response_id is kept, so this REVISES the response
   rather than adding a second one; `revision` counts how many times. */
async function startReview(prior) {
  let stored = null;
  try {
    const r = await fetch('/api/response/' + encodeURIComponent(prior.response_id));
    if (r.ok) stored = await r.json();
  } catch (e) { /* offline: fall through to the local copy below */ }

  // Offline, or the server has no record: the draft on this device is the only
  // copy, and it is better to review that than to refuse.
  const answers = stored ? stored.answers : (JSON.parse(localStorage.getItem(CFG.draftKey) || '{}').answers || null);
  if (!answers) {
    alert('Those answers could not be loaded. You can start a new response instead.');
    return;
  }
  const code = (stored && stored.instrument) || prior.instrument;
  INSTR = refCache[code] || await loadJSON(COMMON.instruments.find(i => i.code === code).file);
  refCache[code] = INSTR;

  state = Object.assign({}, state, {
    code, answers: Object.assign({}, answers),
    form: (stored && stored.form) || 'full',
    arm: (stored && stored.recruit_arm) || state.arm,
    referrer: (stored && stored.referrer) || state.referrer,
    respId: prior.response_id,
    revision: ((stored && stored.revision) || prior.revision || 0) + 1,
    review: true,
    page: 0, qidx: 0, pages: [], startedAt: Date.now()
  });
  $('#picker').hidden = true; $('#done').hidden = true; $('#survey').hidden = false;
  $('#progwrap').hidden = false;
  document.body.classList.add('reviewing');
  renderPage();
}

/* Build vs conduct. Checked once, silently, before anything else: a
   respondent must never wait on this or see it fail loudly if the endpoint is
   briefly unreachable, so a network error is treated as "published" -- the
   normal, safe default -- rather than stalling the page on a gate nobody
   asked for. Only an EXPLICIT published:false response shows the chooser. */
async function checkModeGate() {
  let published = true;
  try {
    const r = await fetch('/api/schema/state');
    if (r.ok) {
      const j = await r.json();
      published = j.published !== false;
    }
  } catch (e) { /* offline or no such endpoint (older server): proceed as published */ }

  if (published) { $('#picker').hidden = false; return; }

  $('#modegate').hidden = false;
  return new Promise(resolve => {
    $('#gateBuild').addEventListener('click', () => {
      location.href = 'dashboard.html#editor';
    });
    $('#gateConduct').addEventListener('click', () => {
      $('#modegate').hidden = true;
      $('#picker').hidden = false;
      resolve();
    }, { once: true });
  });
}

async function init() {
  applyAppearance();
  localStorage.removeItem('aimap_lang');   // left over from the multilingual build
  await checkModeGate();
  COMMON = await loadJSON('common.json');
  readRecruitment();

  // The footer used to hard-code the instrument version, which meant it kept
  // claiming v0.1 after the schema moved on. Read it from the schema instead.
  const foot = document.querySelector('footer');
  if (foot) foot.innerHTML = foot.innerHTML.replace(/instrument v[\w.\-]+/,
    'instrument v' + COMMON.version);

  // A referral code is checked before the respondent starts, so a mistyped code
  // becomes an 'open' response rather than a dangling edge in the referral graph.
  if (state.referrer) {
    try {
      const r = await fetch(CFG.referralEndpoint + '/' + encodeURIComponent(state.referrer));
      const j = await r.json();
      if (!j.ok) { state.referrer = null; state.arm = 'open'; }
    } catch (e) { /* offline: keep the code and let the server decide on submit */ }
  }
  // The three instruments are one schema file now (questionnaire.json), so it
  // is loaded once, up front, rather than per branch; which code applies is
  // not decided by a picker screen any more, it is decided by the respondent's
  // own answer to R1, the first real question. "ORG" here is just which of
  // the three equivalent entries in common.json's instrument list is read to
  // find that file -- any of the three would resolve to the same place.
  INSTR = await loadJSON(COMMON.instruments.find(i => i.code === 'ORG').file);

  $('#lenseg').addEventListener('click', e => {
    const b = e.target.closest('button'); if (!b) return;
    state.form = b.dataset.form;
    syncLength();
    saveDraft();
    announce(b.textContent);
  });

  $('#pnext').addEventListener('click', startQuestionnaire);

  $('#next').addEventListener('click', async () => {
    if (lengthPending) {
      step(+1);               // into the chosen branch's first real question
      saveDraft(); renderPage();
      return;
    }
    if (!validatePage()) return;
    if (isLastQuestion()) await submit();
    else if (step(+1)) { saveDraft(); renderPage(); }
  });
  $('#back').addEventListener('click', () => {
    // Going back from the length choice lands on R1 again: state.page/qidx never
    // moved while it was showing, since it sits between R1 and the next
    // section rather than occupying a page slot of its own.
    if (lengthPending) { renderPage(); return; }
    if (step(-1)) { saveDraft(); renderPage(); }
  });
  $('#skip').addEventListener('click', async () => {
    if (isLastQuestion()) await submit();
    else if (step(+1)) { saveDraft(); renderPage(); }
  });
  $('#restart').addEventListener('click', () => location.reload());  // clean picker state

  $('#keepbtn').addEventListener('click', () => {
    if (isLastQuestion()) return submit();
    if (step(+1)) { saveDraft(); renderPage(); }
  });
  $('#endreview').addEventListener('click', () => submit());

  // Appearance settings
  const sdlg = $('#setdlg');
  buildSettings();
  $('#settings').addEventListener('click', () => { buildSettings(); sdlg.showModal(); });
  $('#setclose').addEventListener('click', () => sdlg.close());
  $('#setreset').addEventListener('click', () => {
    ['aimap_theme', 'aimap_bg', 'aimap_size'].forEach(k => localStorage.removeItem(k));
    applyAppearance(); buildSettings(); announce('Appearance reset to default');
  });
  $('#themeseg').addEventListener('click', e => {
    const b = e.target.closest('button'); if (!b) return;
    localStorage.setItem('aimap_theme', b.dataset.theme);
    applyAppearance(); buildSettings(); announce(b.textContent + ' theme');
  });
  $('#textseg').addEventListener('click', e => {
    const b = e.target.closest('button'); if (!b) return;
    localStorage.setItem('aimap_size', b.dataset.size);
    applyAppearance(); announce(b.textContent + ' text');
  });
  // Follow the OS only while the user has actually chosen "System".
  window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', () => {
    if (getTheme() === 'system') { applyAppearance(); buildSettings(); }
  });
  document.addEventListener('keydown', onKey);

  const dlg = $('#admindlg');
  $('#admin').addEventListener('click', e => { e.preventDefault(); updateNet(); dlg.showModal(); });
  $('#closedlg').addEventListener('click', () => dlg.close());
  $('#flush').addEventListener('click', async () => { const r = await flushQueue(); updateNet(); alert(`Sent ${r.sent}. ${r.left} still queued.`); });
  $('#exportall').addEventListener('click', () => downloadJSON(queueGet(), 'aimap-responses.json'));
  $('#exportcsv').addEventListener('click', () => downloadCSV(queueGet(), 'aimap-responses.csv'));

  window.addEventListener('online', async () => { await flushQueue(); updateNet(); });
  window.addEventListener('offline', updateNet);
  updateNet();
  setInterval(async () => { if (navigator.onLine && queueGet().length) { await flushQueue(); updateNet(); } }, 60000);

  /* Already submitted from this device? Offer a review before the picker. A
     returning respondent is far likelier to be coming back to their own answers
     than to be a different person on the same machine, and quietly recording a
     second response would count one person twice. */
  const prior = lastCompletion();
  if (prior && prior.response_id) {
    const when = (prior.submitted_at || '').slice(0, 10);
    const box = el('div', 'priorbox');
    box.appendChild(el('h3', null, 'You have already completed this questionnaire'));
    box.appendChild(el('p', 'fine',
      `Submitted on ${when}${prior.revision ? `, revised ${prior.revision} time(s)` : ''}. ` +
      'You can look back through your answers and change anything. Nothing changes ' +
      'unless you choose a different answer.'));
    const rowel = el('div', 'row');
    const rev = el('button', 'btn', 'Review my answers');
    rev.type = 'button';
    rev.addEventListener('click', () => startReview(prior));
    const fresh = el('button', 'btn ghost', 'Start a new, separate response');
    fresh.type = 'button';
    fresh.addEventListener('click', () => { box.remove(); });
    rowel.appendChild(rev); rowel.appendChild(fresh);
    box.appendChild(rowel);
    $('#picker').insertBefore(box, $('#picker').firstChild.nextSibling);
  }

  // Offer to resume an interrupted session.
  try {
    const d = JSON.parse(localStorage.getItem(CFG.draftKey) || 'null');
    if (d && d.code && Object.keys(d.answers || {}).length > 2) {
      if (confirm('You have an unfinished questionnaire on this device. Continue where you left off?')) {
        INSTR = refCache[d.code] || await loadJSON(COMMON.instruments.find(i => i.code === d.code).file);
        refCache[d.code] = INSTR;
        state = d;
        $('#picker').hidden = true; $('#survey').hidden = false;
        $('#progwrap').hidden = false; renderPage();
      } else clearDraft();
    }
  } catch (e) {}

  // A deliberate, always-findable way to wipe all locally-saved state -- not
  // just the draft above, but the "already completed" marker and any queued
  // offline submission too. Repeat testing otherwise keeps tripping over
  // yesterday's answers; shown only when there is something to actually clear.
  const hasLocalState = () => {
    try {
      return !!(localStorage.getItem(CFG.draftKey) ||
                JSON.parse(localStorage.getItem(CFG.qKey) || '[]').length ||
                localStorage.getItem(CFG.doneKey));
    } catch (e) { return false; }
  };
  const startoverBtn = $('#startover');
  if (startoverBtn) {
    startoverBtn.hidden = !hasLocalState();
    startoverBtn.addEventListener('click', () => {
      if (!confirm('Clear all saved answers on this device and start over? Anything already ' +
                    'submitted stays submitted -- this only clears what is saved locally.')) return;
      clearDraft();
      queueSet([]);
      try { localStorage.removeItem(CFG.doneKey); } catch (e) {}
      location.reload();
    });
  }
}
init().catch(e => { document.body.innerHTML = '<div class="wrap card"><h2>Could not load the survey</h2><p class="fine">' + e.message + '</p></div>'; });
