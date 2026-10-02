/* ===========================================================================
   AI-MAP Ethiopia: surveyor's dashboard.

   One fetch of /admin/dashboard, then eight views over the same payload. The
   single fetch is deliberate: the views cross-reference each other: an alert
   points at a quota cell, a finding rests on a distribution, and assembling
   them from separate requests would let the page show two figures computed
   seconds apart and quietly disagreeing.

   No build step and no chart library, for the same reason the questionnaire has
   none: this has to run from a laptop in a field office with no npm, and
   sometimes with no internet. Charts are inline SVG built here.

   THREE RULES, enforced throughout rather than remembered:

     1. No percentage without its denominator. The server returns {pct, n, of}
        for every share and `fmtShare` refuses to render one without the n.
     2. Colour is never the only encoding. Every chart has a table twin behind
        the Table view switch, every multi-series chart has a legend, and every
        sequential scale has a scale legend.
     3. Below the minimum n, figures are withheld rather than captioned. The
        server blanks them; this file shows the reason in their place.
   =========================================================================== */

'use strict';

const $ = s => document.querySelector(s);
const $$ = s => Array.from(document.querySelectorAll(s));

let DATA = null;

/* ---------------------------------------------------------------- format */

const esc = s => String(s == null ? '' : s)
  .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
  .replace(/"/g, '&quot;');

const num = n => (n == null ? '-' : Number(n).toLocaleString('en-GB'));

function pct(x, digits) {
  if (x == null || Number.isNaN(x)) return '-';
  return Number(x).toFixed(digits == null ? 1 : digits) + '%';
}

/* A share is rendered with its n or not at all. The server hands back
   {pct, n, of}; anything that lost the denominator on the way here is a bug we
   want to see as ": ", not as a confident-looking percentage. */
function fmtShare(s, opts) {
  if (!s || s.pct == null || !s.of) return '-';
  const o = opts || {};
  return pct(s.pct, o.digits) + (o.bare ? '' : ` <span class="hint">(${s.n}/${s.of})</span>`);
}

const dateShort = iso => (iso || '').slice(5, 10);

/* ---------------------------------------------------------------- tooltip */

const tip = $('#tip');

function bindTips(root) {
  root.querySelectorAll('[data-tip]').forEach(el => {
    const show = e => {
      tip.innerHTML = el.getAttribute('data-tip');
      tip.classList.add('on');
      const r = (e.target.getBoundingClientRect ? e.target : el).getBoundingClientRect();
      const x = (e.clientX != null ? e.clientX : r.left + r.width / 2);
      const y = (e.clientY != null ? e.clientY : r.top);
      const w = tip.offsetWidth, h = tip.offsetHeight;
      tip.style.left = Math.min(Math.max(8, x - w / 2), innerWidth - w - 8) + 'px';
      tip.style.top = (y - h - 12 < 8 ? y + 18 : y - h - 12) + 'px';
    };
    el.addEventListener('mouseenter', show);
    el.addEventListener('mousemove', show);
    el.addEventListener('focus', show);
    el.addEventListener('mouseleave', () => tip.classList.remove('on'));
    el.addEventListener('blur', () => tip.classList.remove('on'));
  });
}

/* ------------------------------------------------------------ chart parts */

const SERIES = { ORG: 'var(--s1)', IND: 'var(--s2)', CIT: 'var(--s3)' };
const SEQ = ['var(--q1)', 'var(--q2)', 'var(--q3)', 'var(--q4)', 'var(--q5)'];

function legend(items) {
  return `<p class="legend">${items.map(i =>
    `<span><i style="background:${i.color}"></i>${esc(i.label)}</span>`).join('')}</p>`;
}

function scaleLegend(labels, colors, caption) {
  return `<div class="scalelegend"><span>${esc(labels[0])}</span>
    <span class="swatches">${colors.map(c => `<i style="background:${c}"></i>`).join('')}</span>
    <span>${esc(labels[1])}</span>${caption ? `<span> · ${esc(caption)}</span>` : ''}</div>`;
}

/* Stacked columns over time. Stacked rather than grouped because the useful
   reading is total daily throughput with its composition, and 2px surface gaps
   separate the segments: a stroked border around each would read as chrome. */
function chartColumns(days, keys, opts) {
  const o = opts || {};
  // Pixel viewBox with uniform scaling. A stretched viewBox (preserveAspectRatio
  // "none") would distort the tick labels along with the bars, which is the usual
  // way a hand-rolled SVG chart ends up with squashed text on a wide screen.
  const W = 900, H = o.height || 200, pad = { l: 40, r: 8, t: 10, b: 26 };
  const max = Math.max(1, ...days.map(d => keys.reduce((a, k) => a + (d[k] || 0), 0)));
  const bw = (W - pad.l - pad.r) / days.length;
  const y = v => pad.t + (H - pad.t - pad.b) * (1 - v / max);

  let marks = '';
  days.forEach((d, i) => {
    let acc = 0;
    const x = pad.l + i * bw;
    keys.forEach(k => {
      const v = d[k] || 0;
      if (!v) return;
      // 2px surface gap between stacked segments -- a stroked border round each
      // would read as chrome rather than as separation.
      const h = Math.max(1.5, y(acc) - y(acc + v) - 2);
      marks += `<rect class="mark" x="${(x + bw * 0.14).toFixed(1)}" y="${y(acc + v).toFixed(1)}"
        width="${Math.max(1.5, bw * 0.72).toFixed(1)}" height="${h.toFixed(1)}" rx="1.5" fill="${SERIES[k]}"/>`;
      acc += v;
    });
    const total = keys.reduce((a, k) => a + (d[k] || 0), 0);
    marks += `<rect class="hit" x="${x.toFixed(1)}" y="${pad.t}" width="${bw.toFixed(1)}"
      height="${(H - pad.t - pad.b).toFixed(1)}" tabindex="0" data-tip="${esc(`<div class="t">${d.date}</div>` +
        keys.map(k => `<div class="r">${k}: ${d[k] || 0}</div>`).join('') +
        `<div class="r">total: ${total}</div>`)}"/>`;
  });

  // Solid hairline gridlines one shade off the surface. Never dashed.
  let grid = '';
  for (let i = 0; i <= 2; i++) {
    const v = (max / 2) * i, yy = y(v);
    grid += `<line class="gridline" x1="${pad.l}" x2="${W - pad.r}" y1="${yy.toFixed(1)}" y2="${yy.toFixed(1)}"/>
      <text class="val" x="${pad.l - 7}" y="${(yy + 4).toFixed(1)}" text-anchor="end">${Math.round(v)}</text>`;
  }
  // Selective x labels: a date under every column at this width is unreadable.
  let xlab = '';
  const every = Math.max(1, Math.ceil(days.length / 9));
  days.forEach((d, i) => {
    if (i % every) return;
    xlab += `<text x="${(pad.l + i * bw + bw / 2).toFixed(1)}" y="${H - 8}"
      text-anchor="middle">${dateShort(d.date)}</text>`;
  });

  return `<svg class="chart" viewBox="0 0 ${W} ${H}" role="img"
      aria-label="${esc(o.aria || 'Daily responses by instrument')}"
      style="width:100%;height:auto">
    ${grid}${marks}${xlab}
    <line class="axis" x1="${pad.l}" x2="${W - pad.r}" y1="${y(0).toFixed(1)}" y2="${y(0).toFixed(1)}"/>
  </svg>`;
}

/* Horizontal bars. One series, one colour, never a value-ramp across nominal
   categories, which would burn the colour channel re-encoding bar length. */
function chartBarsH(items, opts) {
  const o = opts || {};
  const max = Math.max(1, ...items.map(i => Math.abs(i.value)));
  const rowH = o.rowH || 26;
  const labelW = o.labelW || 210;
  return `<div>${items.map(i => {
    const w = Math.max(1, 100 * Math.abs(i.value) / max);
    const color = i.color || 'var(--s1)';
    // minmax(0, Npx), not a bare Npx: a fixed label column holds every row to
    // that exact width regardless of how little space the panel actually has,
    // which is what pushed wide-label charts (labelW up to 290) off the right
    // edge on a phone -- the label itself already truncates with ellipsis, so
    // letting the TRACK shrink below its preferred width when the viewport is
    // narrow costs nothing but a shorter truncation point.
    return `<div style="display:grid;grid-template-columns:minmax(0,${labelW}px) 1fr auto;gap:10px;
        align-items:center;height:${rowH}px" tabindex="0" data-tip="${esc(`<div class="t">${i.label}</div><div class="r">${i.tip || i.display || i.value}</div>`)}">
      <span style="font-size:12.5px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap"
        title="${esc(i.label)}">${esc(i.label)}</span>
      <span style="height:11px;background:var(--surface-2);border-radius:5px;overflow:hidden">
        <i style="display:block;height:100%;width:${w.toFixed(1)}%;background:${color};border-radius:5px"></i>
      </span>
      <span style="font-size:12.5px;font-variant-numeric:tabular-nums;min-width:76px;text-align:right">
        ${i.display != null ? i.display : num(i.value)}</span>
    </div>`;
  }).join('')}</div>`;
}

/* Diverging bars around a neutral zero. Two hues that read as opposite, with a
   grey midpoint so "no gap" reads as nothing rather than as a third category. */
function chartDiverging(items, opts) {
  const o = opts || {};
  const max = Math.max(1, ...items.map(i => i.value));
  return `<div>${items.map(i => {
    const w = 100 * i.value / max;
    const neg = i.key < 0, zero = i.key === 0;
    const color = zero ? 'var(--dmid)' : (neg ? 'var(--dneg)' : 'var(--dpos)');
    const half = w / 2;
    return `<div style="display:grid;grid-template-columns:130px 1fr 60px;gap:10px;align-items:center;height:24px"
        tabindex="0" data-tip="${esc(`<div class="t">${i.label}</div><div class="r">${i.value} responses</div>`)}">
      <span style="font-size:12.5px">${esc(i.label)}</span>
      <span style="position:relative;height:11px;background:var(--surface-2);border-radius:5px">
        <i style="position:absolute;left:${neg ? (50 - half) : 50}%;width:${half.toFixed(1)}%;
           height:100%;background:${color};border-radius:5px"></i>
        <i style="position:absolute;left:50%;top:-2px;width:1px;height:15px;background:var(--axis)"></i>
      </span>
      <span style="font-size:12.5px;font-variant-numeric:tabular-nums;text-align:right">${i.value}</span>
    </div>`;
  }).join('')}
  <p class="hint" style="margin-top:8px">${esc(o.caption || '')}</p></div>`;
}

/* Sequential heatmap. One hue light→dark, always with a scale legend: a heatmap
   without one cannot be read, and the table twin carries the exact values. */
function chartHeat(rows, cols, get, opts) {
  const o = opts || {};
  return `<div class="scrollx"><table class="dt" style="min-width:${140 + cols.length * 74}px">
    <thead><tr><th>${esc(o.rowHeader || '')}</th>
      ${cols.map(c => `<th class="num">${esc(c.label)}</th>`).join('')}</tr></thead>
    <tbody>${rows.map(r => `<tr>
      <td style="max-width:290px">${esc(r.label)}</td>
      ${cols.map(c => {
        const cell = get(r, c) || {};
        // A cell outside the scale (no target, no data) is painted as surface, not
        // as the lightest ramp step: "not applicable" must not read as "zero".
        const bin = cell.bin == null ? 0 : cell.bin;
        const bg = cell.na ? 'var(--surface-2)' : SEQ[bin];
        const ink = (cell.na || bin <= 2) ? 'var(--ink)' : '#ffffff';
        return `<td class="num" tabindex="0" data-tip="${esc(cell.tip || '')}"
          style="background:${bg};color:${ink};
                 border-bottom:2px solid var(--surface)">${cell.text == null ? '' : esc(cell.text)}</td>`;
      }).join('')}</tr>`).join('')}</tbody></table>
    ${scaleLegend(o.scaleLabels || ['low', 'high'], SEQ, o.scaleCaption)}</div>`;
}

/* Dumbbell: one local value against one comparator, per row. Two entities, so a
   legend is always present, and both ends are direct-labelled. */
function chartDumbbell(items, opts) {
  const o = opts || {};
  return `${legend([{ label: o.aLabel || 'Ethiopia', color: 'var(--s1)' },
                    { label: o.bLabel || 'Global', color: 'var(--s2)' }])}
  <div>${items.map(i => {
    const a = i.a == null ? null : i.a * 100, b = i.b == null ? null : i.b * 100;
    const lo = Math.min(a == null ? b : a, b), hi = Math.max(a == null ? b : a, b);
    return `<div style="display:grid;grid-template-columns:1fr;gap:2px;padding:9px 0;
        border-bottom:1px solid var(--line)">
      <span style="font-size:12.5px">${esc(i.label)}
        ${i.suppressed ? `<span class="hint">: ${esc(i.suppressed)}</span>` : ''}</span>
      <span style="display:grid;grid-template-columns:1fr 92px;gap:10px;align-items:center">
      <span style="position:relative;height:20px" tabindex="0" data-tip="${esc(`<div class="t">${i.label}</div>` +
        `<div class="r">${o.aLabel || 'Ethiopia'}: ${a == null ? 'no data' : a.toFixed(0) + '%'} (n=${i.n || 0})</div>` +
        `<div class="r">${o.bLabel || 'Global'}: ${b.toFixed(0)}%</div>` +
        `<div class="r">${i.source || ''}</div>`)}">
        <i style="position:absolute;left:0;right:0;top:9px;height:1px;background:var(--grid)"></i>
        ${a == null ? '' : `<i style="position:absolute;left:${lo}%;width:${(hi - lo)}%;top:9px;
           height:2px;background:var(--axis)"></i>`}
        ${a == null ? '' : `<i style="position:absolute;left:calc(${a}% - 5px);top:5px;width:10px;height:10px;
           border-radius:50%;background:var(--s1);box-shadow:0 0 0 2px var(--surface)"></i>`}
        <i style="position:absolute;left:calc(${b}% - 5px);top:5px;width:10px;height:10px;
           border-radius:50%;background:var(--s2);box-shadow:0 0 0 2px var(--surface)"></i>
      </span>
      <span style="font-size:12px;font-variant-numeric:tabular-nums;text-align:right;color:var(--muted)"
        >${a == null ? '-' : a.toFixed(0) + '%'} vs ${b.toFixed(0)}%</span>
      </span>
    </div>`;
  }).join('')}</div>`;
}

function tiles(items) {
  return `<div class="tiles">${items.map(i => `<div class="tile">
    <div class="k">${esc(i.k)}</div>
    <div class="v" ${i.color ? `style="color:${i.color}"` : ''}>${i.v}</div>
    <div class="d">${i.d || ''}</div></div>`).join('')}</div>`;
}

function table(cols, rows, opts) {
  const o = opts || {};
  if (!rows.length) return `<p class="empty">${esc(o.empty || 'Nothing to show yet.')}</p>`;
  return `<div class="scrollx ${o.tall ? 'scrolly' : ''}"><table class="dt">
    <thead><tr>${cols.map(c => `<th class="${c.num ? 'num' : ''}">${esc(c.label)}</th>`).join('')}</tr></thead>
    <tbody>${rows.map(r => `<tr class="${r._suppressed ? 'suppressed' : ''}">
      ${cols.map(c => `<td class="${c.num ? 'num' : ''}">${r[c.key] == null ? '-' : r[c.key]}</td>`).join('')}
    </tr>`).join('')}</tbody></table></div>`;
}

function panel(title, sub, body, foot) {
  return `<section class="panel">
    <h3>${esc(title)}</h3>${sub ? `<p class="sub">${sub}</p>` : ''}
    ${body}${foot ? `<p class="foot">${foot}</p>` : ''}</section>`;
}

/* A chart and its table twin, rendered together; the Table view switch shows
   one or the other. Both are always in the DOM, so the table is available to a
   screen reader and to anyone who cannot use the colour encoding. */
function twin(chartHTML, tableHTML) {
  return `<div class="chartcard">${chartHTML}</div><div class="tablecard">${tableHTML}</div>`;
}

/* A progress bar inside a table cell needs an explicit width: the cell sizes to
   its content, and a block element with no intrinsic width collapses to a sliver. */
const bar = (p, cls) =>
  `<span class="pbar ${cls || ''}" style="width:92px"><i style="width:${Math.min(100, p || 0)}%"></i></span>`;

/* ============================================================== views ==== */

const VIEWS = [
  ['overview', 'Overview', viewOverview],
  ['coverage', 'Coverage & quotas', viewCoverage],
  ['quality', 'Data quality', viewQuality],
  ['completion', 'Completion & drop-off', viewCompletion],
  ['org', 'Organisations', viewOrg],
  ['ind', 'Practitioners', viewInd],
  ['cit', 'Citizens', viewCit],
  ['report', 'Findings & report', viewReport],
  ['editor', 'Editor', viewEditor],
];

/* ---------------------------------------------------------------- overview */

function viewOverview(d) {
  const fw = d.fieldwork, p = fw.projection;
  const acts = d.alerts.filter(a => a.severity === 'act');
  const totalTarget = Object.values(fw.by_instrument).reduce((a, v) => a + v.target, 0);

  const stat = tiles([
    { k: 'Responses collected', v: num(fw.total),
      d: `${pct(100 * fw.total / totalTarget)} of ${num(totalTarget)} targeted` },
    { k: 'Collection rate', v: p.responses_per_day,
      d: `per day over the last ${p.window_days} days` },
    { k: 'Projected completion', v: p.projected_date || '-',
      d: p.projected_date ? `${num(p.remaining)} responses remain` : 'rate too low to project' },
    { k: 'Issues needing action', v: acts.length,
      color: acts.length ? 'var(--crit)' : 'var(--ok)',
      d: acts.length ? 'see the alerts below' : 'no trigger crossed' },
  ]);

  const targetRows = Object.entries(fw.by_instrument).map(([code, v]) => ({
    Instrument: `<span style="display:inline-flex;align-items:center;gap:7px">
        <i style="width:10px;height:10px;border-radius:2px;background:${SERIES[code]}"></i>${code}</span>`,
    Collected: num(v.total), Target: num(v.target), '%': pct(v.pct),
    Progress: bar(v.pct, v.pct >= 100 ? 'done' : ''),
    Channels: Object.entries(v.by_mode).map(([m, n]) => `${m} ${n}`).join(', ') || '-',
    Form: Object.entries(v.by_form).map(([f, n]) => `${f} ${n}`).join(', ') || '-',
  }));

  const trendTable = table([{ key: 'date', label: 'Date' }, { key: 'ORG', label: 'ORG', num: true },
     { key: 'IND', label: 'IND', num: true }, { key: 'CIT', label: 'CIT', num: true },
     { key: 'total', label: 'Total', num: true }],
    fw.daily.filter(x => x.total).slice().reverse(), { tall: true, empty: 'No responses yet.' });

  return `
    ${stat}
    <div class="grid wide" style="margin-top:14px">
      ${panel('Alerts: the daily review, computed',
        `The triggers in <code>sampling.json</code>, evaluated against today's data.
         A check that cannot yet be evaluated is absent rather than shown as passing.`,
        d.alerts.length
          ? d.alerts.map(a => `<div class="alert ${a.severity}">
              <span class="ico" aria-hidden="true">${a.severity === 'act' ? '▲' : '●'}</span>
              <span class="msg"><span class="tag">${a.severity === 'act' ? 'Act' : 'Watch'} ·
                ${esc(a.area)}${a.instrument ? ' · ' + esc(a.instrument) : ''}:</span>
                ${esc(a.message)}<span class="act-text">${esc(a.action)}</span></span></div>`).join('')
          : `<p class="empty">No trigger crossed. This is not the same as "no problems": several checks need more data before they can be evaluated.</p>`)}

      ${panel('Progress against target',
        'Targets come from <code>common.json</code>; the sampling matrix behind them is in the Coverage tab.',
        table([{ key: 'Instrument', label: 'Instrument' }, { key: 'Collected', label: 'Collected', num: true },
               { key: 'Target', label: 'Target', num: true }, { key: '%', label: '%', num: true },
               { key: 'Progress', label: '' }, { key: 'Channels', label: 'Channels' },
               { key: 'Form', label: 'Form' }], targetRows))}
    </div>

    <div class="grid" style="margin-top:14px">
      <section class="panel span2">
        <h3>Daily collection</h3>
        <p class="sub">Stacked by instrument over the last 60 days, zero-filled: a sparse
          series drawn as a line joins across the days nobody collected anything, which is
          exactly the pattern worth seeing.</p>
        ${legend(Object.keys(SERIES).map(k => ({ label: k, color: SERIES[k] })))}
        ${twin(chartColumns(fw.daily, ['ORG', 'IND', 'CIT'],
                            { aria: 'Daily responses by instrument, stacked' }), trendTable)}
      </section>
    </div>

    <div class="grid" style="margin-top:14px">
      <section class="panel danger-zone">
        <h3>Danger zone</h3>
        <p class="sub">Permanently deletes every response, in-progress session, contact and
          referral chain currently in the database (<strong>${num(fw.total)}</strong> response(s)
          right now) -- for clearing out test submissions before real fieldwork begins. The
          questionnaire itself (its questions, and whether it is published) is untouched.
          There is no undo.</p>
        <button type="button" class="btn danger" id="resetData">Reset all response data&hellip;</button>
      </section>
    </div>`;
}

function wireOverview(d) {
  const btn = $('#resetData');
  if (!btn) return;
  btn.addEventListener('click', async () => {
    const total = d.fieldwork.total;
    const typed = prompt(
      `This permanently deletes all ${total} response(s), every in-progress session, contact ` +
      `and referral chain. The questionnaire itself is not affected. This cannot be undone.\n\n` +
      `Type ${JSON.stringify(RESET_PHRASE)} to confirm:`);
    if (typed === null) return;
    if (typed !== RESET_PHRASE) { alert('Not confirmed -- typed text did not match. Nothing was deleted.'); return; }
    btn.disabled = true;
    btn.textContent = 'Deleting…';
    try {
      const res = await apiSend('/admin/reset-data', 'POST', { confirm: RESET_PHRASE });
      const summary = Object.entries(res.deleted).map(([t, n]) => `${t}: ${n}`).join(', ');
      alert('Deleted. ' + summary);
      await load();
    } catch (e) {
      alert('Could not reset: ' + e.message);
      btn.disabled = false;
      btn.textContent = 'Reset all response data…';
    }
  });
}

const RESET_PHRASE = 'RESET ALL DATA';

/* ---------------------------------------------------------------- coverage */

function viewCoverage(d) {
  const q = d.quotas;

  const orgRows = q.ORG.cells.map(c => ({
    Stratum: esc(c.label) + (c.census ? ' <span class="hint">· census</span>' : ''),
    n: c.n, Target: c.target, '%': pct(c.pct, 0),
    Progress: bar(c.pct, c.pct >= 100 ? 'done' : (c.pct < 50 ? 'gap' : '')),
    Gap: c.gap,
  }));
  const orgChart = chartBarsH(q.ORG.cells.map(c => ({
    label: c.label + (c.census ? ' (census)' : ''),
    value: c.pct || 0, display: `${c.n}/${c.target}`,
    color: (c.pct || 0) >= 100 ? 'var(--ok)' : ((c.pct || 0) < 50 ? 'var(--warn-c)' : 'var(--s1)'),
    tip: `${c.n} of ${c.target}: ${pct(c.pct, 0)}${c.census ? '<br>Census stratum: the risk here is response rate, not sampling error.' : ''}`,
  })), { labelW: 250 });

  const bg = q.CIT.booster_quota.grid;
  const settlements = [{ value: 'urban', label: 'Town / city' },
                       { value: 'periurban', label: 'Small town' },
                       { value: 'rural', label: 'Rural' }];
  const heat = chartHeat(bg.map(r => ({ label: `${r.label} (${r.n}/${r.target})`, _row: r })),
    settlements,
    (r, c) => {
      const cell = r._row.cells.find(x => x.settlement === c.value) || {};
      if (!cell.target) return { na: true, text: '-', tip: 'No target set for this cell.' };
      const fill = cell.pct || 0;
      return {
        bin: fill >= 100 ? 4 : fill >= 75 ? 3 : fill >= 50 ? 2 : fill >= 25 ? 1 : 0,
        text: `${cell.n}/${cell.target}`,
        tip: `<div class="t">${r._row.label} · ${c.label}</div>
              <div class="r">${cell.n} of ${cell.target}: ${pct(cell.pct, 0)}</div>
              <div class="r">still needed: ${cell.gap}</div>`,
      };
    },
    { rowHeader: 'Region', scaleLabels: ['0% filled', 'complete'],
      scaleCaption: 'share of the cell target collected' });

  const boosterTable = table([{ key: 'Region', label: 'Region' }, { key: 'Settlement', label: 'Settlement' },
     { key: 'n', label: 'n', num: true }, { key: 'Target', label: 'Target', num: true },
     { key: '%', label: '%', num: true }, { key: 'Gap', label: 'Still needed', num: true }],
    bg.flatMap(r => r.cells.filter(c => c.target).map(c => ({
      Region: r.label, Settlement: c.settlement, n: c.n, Target: c.target,
      '%': pct(c.pct, 0), Gap: c.gap }))));

  return `
    <div class="grid wide">
      ${panel('ORG: strata', esc(q.ORG.note),
        `<p class="legend"><span><i style="background:var(--warn-c)"></i>under half filled</span>
          <span><i style="background:var(--s1)"></i>in progress</span>
          <span><i style="background:var(--ok)"></i>target met</span></p>` +
        twin(orgChart, table([{ key: 'Stratum', label: 'Stratum' }, { key: 'n', label: 'n', num: true },
          { key: 'Target', label: 'Target', num: true }, { key: '%', label: '%', num: true },
          { key: 'Progress', label: '' }, { key: 'Gap', label: 'Still needed', num: true }], orgRows)),
        'A census stratum is one small enough to enumerate completely. What can go wrong there is response rate, not sampling error.')}

      ${panel('IND: recruitment arms', esc(q.IND.note),
        table([{ key: 'Arm', label: 'Arm' }, { key: 'n', label: 'n', num: true },
               { key: 'Target', label: 'Target', num: true }, { key: '%', label: '%', num: true },
               { key: 'Progress', label: '' }],
          q.IND.cells.map(c => ({
            Arm: esc(c.label) + (c.weightable === false ? ' <span class="hint">· not weightable alone</span>' : ''),
            n: c.n, Target: c.target, '%': pct(c.pct, 0),
            Progress: bar(c.pct, c.pct >= 100 ? 'done' : (c.pct < 50 ? 'gap' : '')),
          }))) +
        `<p class="foot"><strong>Composition watch.</strong> ${esc(q.IND.watch_note)}</p>` +
        table([{ key: 'Group', label: 'Group' }, { key: 'Share', label: 'Share', num: true },
               { key: 'Ceiling', label: 'Watch level', num: true }, { key: 'State', label: 'State' }],
          q.IND.watch.map(w => ({
            Group: esc(w.label), Share: `${pct(100 * w.share, 0)} <span class="hint">(${w.n}/${w.of})</span>`,
            Ceiling: pct(100 * w.max_share, 0),
            State: w.breached ? '<span style="color:var(--warn-c)">● over</span>' : '<span style="color:var(--ok)">● within</span>',
          }))))}
    </div>

    <div class="grid wide" style="margin-top:14px">
      ${panel('CIT: panel and booster', esc(q.CIT.note),
        table([{ key: 'Arm', label: 'Arm' }, { key: 'n', label: 'n', num: true },
               { key: 'Target', label: 'Target', num: true }, { key: '%', label: '%', num: true },
               { key: 'Progress', label: '' }],
          q.CIT.arms.filter(a => a.target).map(a => ({
            Arm: esc(a.label) + (a.weightable === false ? ' <span class="hint">· not weightable alone</span>' : ''),
            n: a.n, Target: a.target, '%': pct(a.pct, 0),
            Progress: bar(a.pct, a.pct >= 100 ? 'done' : (a.pct < 50 ? 'gap' : '')),
          }))),
        esc(q.CIT.calibration.note))}

      ${panel('Booster quota: region × settlement', esc(q.CIT.booster_quota.note),
        twin(heat, boosterTable),
        'A region can be on target in total while every response in it came from the regional capital. That is why this is a grid and not a list.')}
    </div>`;
}

/* ----------------------------------------------------------------- quality */

function viewQuality(d) {
  const q = d.quality, thr = q._threshold;
  const rows = Object.entries(q).filter(([k, v]) => !k.startsWith('_') && typeof v === 'object')
    .map(([code, v]) => ({
      Instrument: code, n: v.n,
      'Flag rate': `${pct(100 * v.flag_rate, 1)} ${v.over_threshold
        ? '<span style="color:var(--crit)">▲ over</span>' : '<span style="color:var(--ok)">● within</span>'}`,
      Planted: v.planted, 'Definition gate': v.definition, Attention: v.attention,
      Honeypot: v.honeypot, Speeders: v.speeder,
      Inconsistent: v.inconsistent
        ? `<span style="color:var(--crit)" title="${esc(Object.entries(v.inconsistent_rules || {})
             .map(([k, n]) => k + ' ×' + n).join(', '))}">${v.inconsistent}</span>` : 0,
      'Client divergence': v.client_divergence
        ? `<span style="color:var(--crit)">${v.client_divergence}</span>` : 0,
      'Scoring errors': v.scoring_errors
        ? `<span style="color:var(--crit)">${v.scoring_errors}</span>` : 0,
      'Mean maturity gap': v.mean_maturity_gap == null ? '-' : v.mean_maturity_gap,
    }));

  const e = d.enumerators;
  const enumRows = (e.enumerators || []).map(x => ({
    Enumerator: x.enumerator, n: x.n,
    'Median min': x.median_minutes == null ? '-' : x.median_minutes,
    'vs team': x.ratio_to_team == null ? '-' :
      `${x.ratio_to_team}× ${x.too_fast ? '<span style="color:var(--crit)">▲ too fast</span>' : ''}`,
    'Flag rate': pct(100 * x.flag_rate, 1),
    Instruments: Object.entries(x.instruments).map(([k, n]) => `${k} ${n}`).join(', '),
    Last: (x.last_submission || '').slice(0, 10),
  }));
  const enumChart = (e.enumerators || []).length ? chartBarsH((e.enumerators || []).map(x => ({
    label: x.enumerator,
    value: x.ratio_to_team || 0,
    display: x.ratio_to_team == null ? '-' : x.ratio_to_team + '×',
    color: x.too_fast ? 'var(--crit)' : 'var(--s1)',
    tip: `${x.n} interviews · median ${x.median_minutes} min · team median ${e.team_median_minutes} min
          · flag rate ${pct(100 * x.flag_rate, 1)}`,
  })), { labelW: 120 }) : '';

  const dur = d.durations;
  const durRows = ['ORG', 'IND', 'CIT'].flatMap(code => {
    const o = dur[code] && dur[code].overall;
    const rows = o ? [{ Instrument: code, Group: 'all', n: o.n, Min: o.min,
                        P25: o.p25 == null ? '-' : o.p25, Median: o.median,
                        P75: o.p75 == null ? '-' : o.p75, Max: o.max }] : [];
    Object.entries((dur[code] || {}).by_form || {}).forEach(([f, v]) => {
      if (v) rows.push({ Instrument: code, Group: `form: ${f}`, n: v.n, Min: v.min,
                         P25: v.p25 == null ? '-' : v.p25, Median: v.median,
                         P75: v.p75 == null ? '-' : v.p75, Max: v.max });
    });
    return rows;
  });

  const gate = dur.cit_gate;
  return `
    ${tiles([
      { k: 'Flag-rate trigger', v: pct(100 * thr, 0), d: 'pauses a channel when crossed' },
      { k: 'CIT median length', v: gate.median_minutes == null ? '-' : gate.median_minutes + ' min',
        color: gate.median_minutes == null ? null : (gate.passes ? 'var(--ok)' : 'var(--crit)'),
        d: `Phase 2 gate: ≤ ${gate.max} min` },
      { k: 'Enumerators active', v: (e.enumerators || []).length,
        d: e.team_median_minutes ? `team median ${e.team_median_minutes} min` : 'no enumerator ids yet' },
      { k: 'Referral chains', v: num(d.referral_chains), d: 'recorded recruitment edges' },
    ])}

    <div class="grid wide" style="margin-top:14px">
      ${panel('Flags by instrument',
        `Flagged responses are analysed in <em>and</em> out, and both are reported, never silently dropped. <strong>Inconsistent</strong> counts responses that contradict
         themselves across fields; both channels block those before submission, so any number
         here arrived another way. Client divergence and scoring errors are integrity
         problems rather than quality ones: any non-zero count is investigated the same day.`,
        table([{ key: 'Instrument', label: 'Instrument' }, { key: 'n', label: 'n', num: true },
               { key: 'Flag rate', label: 'Flag rate', num: true },
               { key: 'Planted', label: 'Planted', num: true },
               { key: 'Definition gate', label: 'Definition', num: true },
               { key: 'Attention', label: 'Attention', num: true },
               { key: 'Honeypot', label: 'Honeypot', num: true },
               { key: 'Speeders', label: 'Speeders', num: true },
               { key: 'Inconsistent', label: 'Inconsistent', num: true },
               { key: 'Client divergence', label: 'Divergence', num: true },
               { key: 'Scoring errors', label: 'Scoring errors', num: true },
               { key: 'Mean maturity gap', label: 'Mean gap', num: true }], rows))}

      ${panel('Enumerator monitoring',
        `Interviewer effects are the largest uncontrolled source of error in
         enumerator-assisted collection, and the only time anything can be done about
         them is during fielding. Speed is shown relative to the team median, because
         the absolute figure depends on the instrument and says nothing alone.`,
        enumRows.length
          ? twin(enumChart, table([{ key: 'Enumerator', label: 'Enumerator' }, { key: 'n', label: 'n', num: true },
              { key: 'Median min', label: 'Median min', num: true }, { key: 'vs team', label: 'vs team', num: true },
              { key: 'Flag rate', label: 'Flag rate', num: true },
              { key: 'Instruments', label: 'Instruments' }, { key: 'Last', label: 'Last' }], enumRows))
          : `<p class="empty">${esc(e.note || 'No enumerator ids recorded yet.')}</p>`,
        `Anyone below ${e.min_ratio || 0.6}× the team median is re-briefed and a sample of their respondents re-contacted.`)}
    </div>

    <div class="grid" style="margin-top:14px">
      ${panel('Completion time', 'Minutes, from the first question to submission. The short form is shown separately because its whole purpose is to be shorter.',
        table([{ key: 'Instrument', label: 'Instrument' }, { key: 'Group', label: 'Group' },
               { key: 'n', label: 'n', num: true }, { key: 'Min', label: 'Min', num: true },
               { key: 'P25', label: 'P25', num: true }, { key: 'Median', label: 'Median', num: true },
               { key: 'P75', label: 'P75', num: true }, { key: 'Max', label: 'Max', num: true }], durRows))}
    </div>`;
}

/* -------------------------------------------------------------- completion */

function viewCompletion(d) {
  const f = d.funnel;
  if (!f.measurable) {
    return panel('Drop-off', '',
      `<p class="empty">No progress heartbeats have been recorded, so drop-off cannot be
       measured. It is <strong>not zero</strong>; it is unmeasured. Both channels post a
       position heartbeat as the respondent moves; if this stays empty while responses
       arrive, the heartbeat is failing and should be fixed before the pilot.</p>`);
  }

  const rows = Object.entries(f.by_instrument).map(([code, v]) => ({
    Instrument: code, Starts: v.starts, Completed: v.completions, Abandoned: v.abandoned,
    'Completion rate': fmtShare(v.completion_rate),
    Bar: bar(v.completion_rate.pct, v.completion_rate.pct >= 65 ? 'done' : 'gap'),
    'Median % when abandoning': v.median_pct_at_abandonment == null
      ? '-' : v.median_pct_at_abandonment + '%',
  }));

  const modeRows = Object.entries(f.by_instrument).flatMap(([code, v]) =>
    Object.entries(v.by_mode).map(([mode, m]) => ({
      Instrument: code, Channel: mode, Starts: m.starts,
      'Completion rate': fmtShare(m.completion_rate),
    })));

  const worst = Object.entries(f.worst_questions).map(([code, items]) => panel(`${code}: where respondents stop`,
    `Share of all ${code} starts that end on this question. Anything over
     ${pct(100 * f.threshold, 0)} is a wording problem, not a respondent problem.`,
    twin(chartBarsH(items.slice(0, 10).map(i => ({
        label: `${i.qid}: ${String(i.text).slice(0, 46)}`,
        value: 100 * i.share_of_starts,
        display: `${i.n} · ${pct(100 * i.share_of_starts, 1)}`,
        color: i.over_threshold ? 'var(--crit)' : 'var(--s1)',
        tip: `<div class="t">${esc(i.qid)} (section ${esc(i.section)})</div>
              <div class="r">${esc(i.text)}</div>
              <div class="r">${i.n} starts ended here: ${pct(100 * i.share_of_starts, 1)}</div>`,
      })), { labelW: 290 }),
      table([{ key: 'Question', label: 'Question' }, { key: 'Section', label: 'Section' },
             { key: 'Text', label: 'Text' }, { key: 'n', label: 'Stopped here', num: true },
             { key: 'Share', label: 'Share of starts', num: true }],
        items.map(i => ({ Question: i.qid, Section: i.section, Text: esc(String(i.text).slice(0, 110)),
                          n: i.n, Share: pct(100 * i.share_of_starts, 1) })))))).join('');

  return `
    <div class="grid wide">
      ${panel('Starts, completions and abandonment',
        `Measured from position heartbeats, which carry no answer content: only how far
         a respondent got. Without them an abandoned questionnaire leaves nothing behind
         and drop-off reads as zero.`,
        table([{ key: 'Instrument', label: 'Instrument' }, { key: 'Starts', label: 'Starts', num: true },
               { key: 'Completed', label: 'Completed', num: true },
               { key: 'Abandoned', label: 'Abandoned', num: true },
               { key: 'Completion rate', label: 'Completion rate', num: true },
               { key: 'Bar', label: '' },
               { key: 'Median % when abandoning', label: 'Median % reached', num: true }], rows),
        `Phase 2 gate: drop-off below ${pct(100 * d.thresholds.dropoff_rate_max, 0)}.`)}

      ${panel('Completion by channel',
        'A channel difference here is a design finding, not noise: it says which surface the instrument actually works on.',
        table([{ key: 'Instrument', label: 'Instrument' }, { key: 'Channel', label: 'Channel' },
               { key: 'Starts', label: 'Starts', num: true },
               { key: 'Completion rate', label: 'Completion rate', num: true }], modeRows))}
    </div>
    <div class="grid wide" style="margin-top:14px">${worst}</div>`;
}

/* ------------------------------------------------------------ organisations */

function viewOrg(d) {
  const o = d.org, oc = o.overclaiming, b = d.benchmarks;
  if (!o.n) return `<p class="empty">No organisational responses yet.</p>`;

  const matChart = chartBarsH(o.maturity.map(m => ({
    label: `${m.level} · ${m.name}`, value: m.n, display: `${m.n} (${pct(m.pct, 0)})`,
    tip: `${m.n} organisations: ${pct(m.pct, 1)} of ${o.n}`,
  })), { labelW: 230 });

  const techChart = chartBarsH(o.technical.map(m => ({
    label: `${m.level} · ${m.name}`, value: m.n, display: `${m.n} (${pct(m.pct, 0)})`,
    color: 'var(--s2)',
    tip: `${m.n} organisations: ${pct(m.pct, 1)} of ${o.n}`,
  })), { labelW: 230 });

  const gapItems = Object.entries(oc.distribution).map(([k, v]) => ({
    key: Number(k), value: v,
    label: Number(k) === 0 ? 'accurate' :
           (Number(k) > 0 ? `over by ${k}` : `under by ${Math.abs(Number(k))}`),
  })).sort((a, b2) => a.key - b2.key);

  const sectorRows = d.sectors.map(s => s.suppressed
    ? { Sector: esc(s.label), n: s.n, _suppressed: true, Readiness: esc(s.suppressed) }
    : {
        Sector: esc(s.label), n: s.n,
        Readiness: s.readiness_overall, Geometric: s.readiness_geometric,
        'Compensability gap': s.compensability_gap, Band: s.band,
        Maturity: s.maturity_mean, 'Technical depth': s.technical_mean,
        Infrastructure: s.infrastructure, Data: s.data, Expertise: s.expertise,
        Economic: s.economic, Governance: s.governance,
      });

  const ranked = d.sectors.filter(s => !s.suppressed);
  const dims = [{ value: 'infrastructure', label: 'Infra' }, { value: 'data', label: 'Data' },
                { value: 'expertise', label: 'Expertise' }, { value: 'economic', label: 'Economic' },
                { value: 'governance', label: 'Governance' }];
  const sectorHeat = ranked.length ? chartHeat(ranked.map(s => ({ label: `${s.label} (n=${s.n})`, _s: s })),
    dims,
    (r, c) => {
      const v = r._s[c.value];
      if (v == null) return { bin: 0, text: '-', tip: 'Not enough answered items to score.' };
      return { bin: v >= 80 ? 4 : v >= 60 ? 3 : v >= 40 ? 2 : v >= 20 ? 1 : 0,
               text: v.toFixed(0),
               tip: `<div class="t">${r._s.label} · ${c.label}</div>
                     <div class="r">${v} of 100 (n=${r._s.n})</div>` };
    },
    { rowHeader: 'Sector', scaleLabels: ['0', '100'], scaleCaption: 'readiness score by dimension' }) : '';

  const benchItems = b.rows.filter(r => !r.unit).map(r => ({
    label: r.label, a: r.local, b: r.global, n: r.n, source: r.source,
    suppressed: r.sufficient ? null : `n=${r.n}, below the minimum of ${b.min_n}`,
  }));
  const delay = b.rows.find(r => r.unit === 'months');

  const useCases = Object.entries(d.use_cases).filter(([k]) => k !== 'YI').map(([sec, blk]) => {
    const cols = [{ value: '2', label: 'Exploring' }, { value: '3', label: 'Piloting' },
                  { value: '4', label: 'In production' }];
    return panel(`Use cases: ${sec} module`,
      `${blk.n_responses} responding organisations. Status is self-reported on the
       five-point scale shared by every sector module, which is what makes the
       modules comparable.` +
      (blk.sufficient ? '' : ` <strong>Below n=${d.min_n}: read as indicative only.</strong>`),
      twin(chartHeat(blk.cases.map(c => ({ label: c.label, _c: c })), cols,
          (r, c) => {
            const n = r._c.counts[c.value] || 0;
            const share = r._c.n ? 100 * n / r._c.n : 0;
            return { bin: share >= 40 ? 4 : share >= 25 ? 3 : share >= 12 ? 2 : share > 0 ? 1 : 0,
                     text: n ? `${share.toFixed(0)}%` : '',
                     tip: `<div class="t">${esc(r._c.label)}</div>
                           <div class="r">${c.label}: ${n} of ${r._c.n} (${share.toFixed(0)}%)</div>` };
          },
          { rowHeader: 'Use case', scaleLabels: ['none', 'most'],
            scaleCaption: 'share of responding organisations at this status' }),
        table([{ key: 'Use case', label: 'Use case' }, { key: 'n', label: 'n', num: true },
               { key: 'In production', label: 'In production', num: true },
               { key: 'Piloting or better', label: 'Piloting or better', num: true }],
          blk.cases.map(c => ({ 'Use case': esc(c.label), n: c.n,
            'In production': fmtShare(c.production), 'Piloting or better': fmtShare(c.piloting_or_better) })))));
  }).join('');

  const yi = d.use_cases.YI;
  const industry = yi ? panel('Industry: technology sophistication',
    `A different scale on purpose: 1 = manual, 5 = machine learning, matching the
     Firm-level Adoption of Technology survey so movement against that baseline is
     measurable. It is <strong>not</strong> pooled into the heatmaps above.`,
    chartBarsH(yi.functions.map(fn => ({
      label: fn.label, value: fn.mean_sophistication,
      display: fn.mean_sophistication.toFixed(2), color: 'var(--s2)',
      tip: `mean ${fn.mean_sophistication} of 5 (n=${fn.n}) · using AI: ${fmtShare(fn.using_ai, { bare: true })}`,
    })), { labelW: 200 }),
    esc(yi.baseline)) : '';

  const barr = d.barriers.ORG;

  return `
    ${tiles([
      { k: 'Organisations', v: num(o.n), d: 'responses received' },
      { k: 'Mean over-claim', v: oc.mean_gap == null ? '-' : `+${oc.mean_gap}`,
        d: `levels above what the checklist supports (n=${oc.n})` },
      { k: 'Over-claim by ≥1 level', v: oc.over.pct == null ? '-' : pct(oc.over.pct, 0),
        d: oc.over.of ? `${oc.over.n} of ${oc.over.of}` : '' },
      { k: 'In production (level 3+)',
        v: pct(o.maturity.slice(3).reduce((a, m) => a + (m.pct || 0), 0), 0),
        d: `${o.maturity.slice(3).reduce((a, m) => a + m.n, 0)} of ${o.n}` },
    ])}

    <div class="grid wide" style="margin-top:14px">
      ${panel('Adoption maturity: computed, not self-rated',
        'Derived from the D5 behavioural checklist under gated rules. Level 3 requires a system in production today; level 4 requires two departments or a budget line plus production monitoring.',
        twin(matChart, table([{ key: 'Level', label: 'Level' }, { key: 'n', label: 'n', num: true },
          { key: '%', label: '%', num: true }],
          o.maturity.map(m => ({ Level: `${m.level} · ${esc(m.name)}`, n: m.n, '%': pct(m.pct, 1) })))))}

      ${panel('Technical depth: could they build any of it?',
        'Orthogonal to maturity. A bank running vendor credit scoring nationwide is maturity 4, depth 1; a lab that trained a model nothing uses is maturity 2, depth 4. Reporting either alone gives a national picture that is wrong in a predictable direction.',
        twin(techChart, table([{ key: 'Level', label: 'Level' }, { key: 'n', label: 'n', num: true },
          { key: '%', label: '%', num: true }],
          o.technical.map(m => ({ Level: `${m.level} · ${esc(m.name)}`, n: m.n, '%': pct(m.pct, 1) })))))}
    </div>

    <div class="grid wide" style="margin-top:14px">
      ${panel('Self-assessment against the behavioural checklist',
        'Both figures come from the same respondent minutes apart, so the gap is internal inconsistency, not two sources disagreeing.',
        twin(chartDiverging(gapItems,
              { caption: 'Left of centre: understated. Right: over-claimed. Grey: accurate.' }),
             table([{ key: 'Gap', label: 'Gap' }, { key: 'n', label: 'Responses', num: true }],
               gapItems.map(g => ({ Gap: esc(g.label), n: g.value })))),
        `Under-claiming: ${fmtShare(oc.under)} · over by two or more levels: ${fmtShare(oc.over_by_two_or_more)}`)}

      ${panel('Against the global benchmark',
        `Items worded to match the comparator instrument on purpose, so an Ethiopian
         figure lands on a global distribution rather than standing alone.`,
        benchItems.length ? chartDumbbell(benchItems, { aLabel: 'Ethiopia (this study)', bLabel: 'Global' })
          : '<p class="empty">No benchmark items answered yet.</p>',
        (delay && delay.local != null
          ? `Mean deployment delay: <strong>${delay.local} months</strong> here against
             ${delay.global} globally (n=${delay.n}). ` : '') +
        `Blind spots: counted separately from a "no", because not knowing is a different state
         from having checked: ` +
        b.blind_spots.map(x => `${esc(x.label)} ${fmtShare(x)}`).join(' · '))}
    </div>

    <div class="grid" style="margin-top:14px">
      ${panel('Readiness by sector and dimension',
        `Sectors below n=${d.min_n} are withheld rather than shown with a caveat.
         The compensability gap is the distance between the arithmetic and geometric
         means: a large gap means one dimension is near zero and is being masked by
         strength elsewhere.`,
        ranked.length
          ? twin(sectorHeat, table([{ key: 'Sector', label: 'Sector' }, { key: 'n', label: 'n', num: true },
              { key: 'Readiness', label: 'Readiness', num: true },
              { key: 'Geometric', label: 'Geometric', num: true },
              { key: 'Compensability gap', label: 'Comp. gap', num: true },
              { key: 'Band', label: 'Band' }, { key: 'Maturity', label: 'Maturity', num: true },
              { key: 'Technical depth', label: 'Depth', num: true },
              { key: 'Infrastructure', label: 'Infra', num: true }, { key: 'Data', label: 'Data', num: true },
              { key: 'Expertise', label: 'Expertise', num: true },
              { key: 'Economic', label: 'Economic', num: true },
              { key: 'Governance', label: 'Governance', num: true }], sectorRows))
          : `<p class="empty">No sector yet has n ≥ ${d.min_n}, the minimum for a ranking.
             ${d.sectors.length} sector(s) have responses; their counts are listed in the table view.</p>`,
        'The geometric mean is the figure to quote where the gap is large: an arithmetic mean lets strong infrastructure mask absent governance.')}
    </div>

    <div class="grid wide" style="margin-top:14px">${useCases}${industry}</div>

    ${barr ? `<div class="grid" style="margin-top:14px">${panel('Reported barriers', esc(barr.text) +
      ` Multi-select, so shares are over the ${barr.n_respondents} respondents who answered, not over selections; they do not sum to 100%.`,
      twin(chartBarsH(barr.items.slice(0, 12).map(i => ({
        label: i.label, value: i.pct, display: pct(i.pct, 0),
        tip: `${i.n} of ${barr.n_respondents} organisations` })), { labelW: 250 }),
        table([{ key: 'Barrier', label: 'Barrier' }, { key: 'n', label: 'n', num: true },
               { key: '%', label: '%', num: true }],
          barr.items.map(i => ({ Barrier: esc(i.label), n: i.n, '%': pct(i.pct, 1) })))))}</div>` : ''}`;
}

/* ------------------------------------------------------------ practitioners */

function viewInd(d) {
  const i = d.ind;
  if (!i.n) return `<p class="empty">No practitioner responses yet.</p>`;

  const order = ['performance_expectancy', 'effort_expectancy', 'social_influence',
                 'facilitating_conditions', 'algorithmic_aversion'];
  const pretty = k => k.replace(/_/g, ' ').replace(/^./, c => c.toUpperCase());

  const constructChart = chartBarsH(order.filter(k => i.constructs[k]).map(k => {
    const c = i.constructs[k];
    return {
      label: pretty(k) + (k === 'algorithmic_aversion' ? ' (high = more averse)' : ''),
      value: c.mean == null ? 0 : (c.mean - 1) / (i.scale_points - 1) * 100,
      display: c.mean == null ? '-' : c.mean.toFixed(2),
      color: 'var(--s1)',
      tip: c.sufficient
        ? `mean ${c.mean} on a 1-${i.scale_points} scale (n=${c.n})`
        : `n=${c.n}: below the minimum of ${d.min_n}, read as indicative only`,
    };
  }), { labelW: 265 });

  const armCols = Object.keys(i.by_arm);
  const armHeat = armCols.length ? chartHeat(order.filter(k => i.constructs[k]).map(k => ({ label: pretty(k), _k: k })),
    armCols.map(a => ({ value: a, label: `${a} (n=${i.by_arm[a].n})` })),
    (r, c) => {
      const v = i.by_arm[c.value].constructs[r._k];
      if (!v || v.mean == null) return { bin: 0, text: '-', tip: 'No responses in this cell.' };
      const norm = (v.mean - 1) / (i.scale_points - 1);
      return { bin: Math.min(4, Math.floor(norm * 5)), text: v.mean.toFixed(2),
               tip: `<div class="t">${pretty(r._k)} · ${c.label}</div>
                     <div class="r">mean ${v.mean} of ${i.scale_points} (n=${v.n})</div>
                     ${v.sufficient ? '' : `<div class="r">below n=${d.min_n}: indicative only</div>`}` };
    },
    { rowHeader: 'Construct', scaleLabels: [`1 (disagree)`, `${i.scale_points} (agree)`],
      scaleCaption: 'construct mean by recruitment arm' }) : '';

  const freqLabels = i.use_frequency_labels || {};
  const freqRows = Object.entries(i.use_frequency).map(([k, n]) => ({
    Frequency: esc(freqLabels[k] || k), n,
    '%': pct(100 * n / Math.max(1, i.n), 1),
  })).reverse();

  const barr = d.barriers.IND;

  return `
    ${tiles([
      { k: 'Practitioners', v: num(i.n), d: 'responses received' },
      { k: 'Intend more than they do', v: fmtShare(i.intention_behaviour_gap.wants_more_than_does, { bare: true }),
        d: `n=${i.intention_behaviour_gap.n}: points at access, not attitude` },
      { k: 'Blocked by payment', v: fmtShare(i.blocked_by_payment, { bare: true }),
        d: 'would pay, cannot pay from Ethiopia' },
      { k: 'Language penalty', v: fmtShare(i.language_penalty, { bare: true }),
        d: 'working in English has limited their work' },
    ])}

    <div class="grid wide" style="margin-top:14px">
      ${panel('UTAUT constructs',
        `Venkatesh et al. (2003), extended with algorithmic aversion after Ayeni et al.
         (MWAIS 2024) who field the same constructs in Nigeria, Cameroon and Uganda.
         Bars show the construct mean on the 1-${i.scale_points} response scale.`,
        twin(constructChart, table([{ key: 'Construct', label: 'Construct' },
            { key: 'Mean', label: `Mean (1-${i.scale_points})`, num: true },
            { key: 'n', label: 'n', num: true }, { key: 'Note', label: '' }],
          order.filter(k => i.constructs[k]).map(k => ({
            Construct: pretty(k), Mean: i.constructs[k].mean == null ? '-' : i.constructs[k].mean,
            n: i.constructs[k].n,
            Note: i.constructs[k].sufficient ? '' : `below n=${d.min_n}` })))),
        `<strong>Read the sign carefully.</strong> ${esc(i.aversion_note)}`)}

      ${panel('Constructs by recruitment arm',
        `The difference between the list-based and referral arms is an estimate of who
         list-based research in Ethiopia misses. It is a finding, not an inconsistency
         to be averaged away.`,
        armCols.length ? twin(armHeat, table([{ key: 'Arm', label: 'Arm' }, { key: 'n', label: 'n', num: true }].concat(order.map(k => ({ key: k, label: pretty(k), num: true }))),
          armCols.map(a => Object.assign({ Arm: a, n: i.by_arm[a].n },
            Object.fromEntries(order.map(k => [k,
              (i.by_arm[a].constructs[k] || {}).mean == null ? '-' : i.by_arm[a].constructs[k].mean]))))))
          : '<p class="empty">No arm data yet.</p>')}
    </div>

    <div class="grid wide" style="margin-top:14px">
      ${panel('How often practitioners use AI tools', 'Current behaviour, kept separate from intention so the two can diverge, which is where facilitating conditions become visible.',
        twin(chartBarsH(freqRows.map(r => ({
          label: r.Frequency, value: r.n, display: `${r.n} (${r['%']})`,
          tip: `${r.n} of ${i.n}` })), { labelW: 200 }),
          table([{ key: 'Frequency', label: 'Frequency' }, { key: 'n', label: 'n', num: true },
                 { key: '%', label: '%', num: true }], freqRows)))}

      ${barr ? panel('What practitioners say would help', esc(barr.text) +
        ` Multi-select over ${barr.n_respondents} respondents.`,
        twin(chartBarsH(barr.items.slice(0, 10).map(x => ({
          label: x.label, value: x.pct, display: pct(x.pct, 0), color: 'var(--s2)',
          tip: `${x.n} of ${barr.n_respondents}` })), { labelW: 250 }),
          table([{ key: 'Item', label: 'Item' }, { key: 'n', label: 'n', num: true },
                 { key: '%', label: '%', num: true }],
            barr.items.map(x => ({ Item: esc(x.label), n: x.n, '%': pct(x.pct, 1) }))))) : ''}
    </div>

    <div class="grid" style="margin-top:14px">
      ${panel('Emigration intention and skill index',
        'The emigration scale is the substantive measure in section F; the skill index is the mean of the ten self-rated ability areas, on 0-100.',
        table([{ key: 'Measure', label: 'Measure' }, { key: 'n', label: 'n', num: true },
               { key: 'Min', label: 'Min', num: true }, { key: 'P25', label: 'P25', num: true },
               { key: 'Median', label: 'Median', num: true }, { key: 'P75', label: 'P75', num: true },
               { key: 'Max', label: 'Max', num: true }],
          [['Emigration intention (1-5)', i.emigration_intention],
           ['Skill index (0-100)', i.skill_index]]
            .filter(([, v]) => v)
            .map(([label, v]) => ({ Measure: label, n: v.n, Min: v.min,
              P25: v.p25 == null ? '-' : v.p25, Median: v.median,
              P75: v.p75 == null ? '-' : v.p75, Max: v.max }))))}
    </div>`;
}

/* ----------------------------------------------------------------- citizens */

function viewCit(d) {
  const c = d.cit;
  if (!c.n) return `<p class="empty">No citizen responses yet.</p>`;
  const s = c.panel_booster_spread;

  const armRows = Object.entries(c.by_arm).map(([arm, v]) => ({
    Arm: arm, n: v.n,
    'Aware of AI': fmtShare(v.aware), 'Uses AI': fmtShare(v.uses),
    Smartphone: fmtShare(v.smartphone), Rural: fmtShare(v.rural),
    'Knows how to complain': fmtShare(v.knows_how_to_complain),
    'Trust (0-100)': v.institutional_trust ? v.institutional_trust.median : '-',
    _suppressed: !v.sufficient,
  }));

  // The panel and the booster are never pooled into one national figure. The
  // comparison IS the finding, so it is drawn as two labelled marks, not averaged.
  const compare = s ? `
    ${legend([{ label: 'Online panel', color: 'var(--s3)' }, { label: 'Enumerator booster', color: 'var(--s1)' }])}
    ${chartBarsH([
      { label: 'Online panel (self-selected)', value: s.panel_pct, display: pct(s.panel_pct, 1),
        color: 'var(--s3)', tip: `${c.panel.uses.n} of ${c.panel.uses.of} panel respondents` },
      { label: 'Enumerator booster (probability)', value: s.booster_pct, display: pct(s.booster_pct, 1),
        color: 'var(--s1)', tip: `${c.booster.uses.n} of ${c.booster.uses.of} booster respondents` },
    ], { labelW: 250 })
    }<p class="foot"><strong>The panel reports ${s.ratio}× the booster's rate</strong>
      (${s.difference > 0 ? '+' : ''}${s.difference} percentage points). ${esc(s.note)}</p>`
    : `<p class="empty">The booster has too few responses to compare against the panel yet.
       Until it does, no national citizen figure should be quoted from this study.</p>`;

  const diff = c.diffusion_comparators;
  const diffRows = Object.entries(diff.values).map(([k, v]) => ({
    Country: k, 'Generative AI use': pct(100 * v, 1),
  }));
  const diffChart = chartBarsH(Object.entries(diff.values).map(([k, v]) => ({
    label: k, value: 100 * v, display: pct(100 * v, 1),
    color: k.startsWith('Ethiopia') ? 'var(--s2)' : 'var(--s1)',
    tip: `${pct(100 * v, 1)} of people aged 15-64`,
  })), { labelW: 190 });

  const regionLabels = c.region_labels || {};
  const regionRows = Object.entries(c.region).sort((a, b) => b[1] - a[1])
    .map(([k, n]) => ({ Region: esc(regionLabels[k] || k), n,
                        '%': pct(100 * n / c.n, 1) }));

  const barr = d.barriers.CIT;

  return `
    ${tiles([
      { k: 'Citizen responses', v: num(c.n), d: `${c.panel.n} panel · ${c.booster.n} booster` },
      { k: 'Booster: uses AI', v: fmtShare(c.booster.uses, { bare: true }),
        d: c.booster.sufficient ? `n=${c.booster.n}` : `n=${c.booster.n}: below n=${d.min_n}` },
      { k: 'Booster: aware of AI', v: fmtShare(c.booster.aware, { bare: true }),
        d: 'probability-sampled arm only' },
      { k: 'Panel ÷ booster', v: s ? s.ratio + '×' : '-',
        color: s && s.ratio > 1.3 ? 'var(--crit)' : null,
        d: 'how much the online panel overstates use' },
    ])}

    <div class="grid wide" style="margin-top:14px">
      ${panel('Online panel against the probability booster',
        `These two are never pooled into a single national figure. A combined
         "national AI awareness" number computed over a self-selected Telegram panel
         plus a probability booster is the single most misleading figure this study
         could produce, so it is not computed.`, compare)}

      ${panel('By recruitment arm',
        'Every citizen figure is reported by arm. Rows below the minimum n are shown in grey and should not be quoted.',
        table([{ key: 'Arm', label: 'Arm' }, { key: 'n', label: 'n', num: true },
               { key: 'Aware of AI', label: 'Aware', num: true },
               { key: 'Uses AI', label: 'Uses', num: true },
               { key: 'Smartphone', label: 'Smartphone', num: true },
               { key: 'Rural', label: 'Rural', num: true },
               { key: 'Knows how to complain', label: 'Knows redress', num: true },
               { key: 'Trust (0-100)', label: 'Trust (median)', num: true }], armRows))}
    </div>

    <div class="grid wide" style="margin-top:14px">
      ${panel('Against the international diffusion estimates',
        esc(diff.note) + ' Ethiopia is highlighted.',
        twin(diffChart, table([{ key: 'Country', label: 'Country / group' },
          { key: 'Generative AI use', label: 'Generative AI use', num: true }], diffRows)),
        esc(diff.source) + '. Telemetry counts devices and self-report counts people; they will not agree exactly and are not expected to.')}

      ${panel('Where responses come from',
        'Geographic composition of the citizen sample. Compare against the booster quota grid in the Coverage tab.',
        twin(chartBarsH(regionRows.slice(0, 12).map(r => ({
          label: r.Region, value: r.n, display: `${r.n} (${r['%']})`, color: 'var(--s3)',
          tip: `${r.n} of ${c.n}` })), { labelW: 190 }),
          table([{ key: 'Region', label: 'Region' }, { key: 'n', label: 'n', num: true },
                 { key: '%', label: '%', num: true }], regionRows)))}
    </div>

    ${barr ? `<div class="grid" style="margin-top:14px">${panel('What citizens are worried about', esc(barr.text) +
      ` Multi-select over ${barr.n_respondents} respondents.`,
      twin(chartBarsH(barr.items.slice(0, 10).map(x => ({
        label: x.label, value: x.pct, display: pct(x.pct, 0), color: 'var(--s3)',
        tip: `${x.n} of ${barr.n_respondents}` })), { labelW: 250 }),
        table([{ key: 'Worry', label: 'Worry' }, { key: 'n', label: 'n', num: true },
               { key: '%', label: '%', num: true }],
          barr.items.map(x => ({ Worry: esc(x.label), n: x.n, '%': pct(x.pct, 1) })))))}</div>` : ''}`;
}

/* ------------------------------------------------------------------ report */

function viewReport(d) {
  const findings = d.insights.map(i => `<article class="finding">
    <h4>${esc(i.heading)}</h4>
    <p>${esc(i.finding)}</p>
    <p class="meta">n = ${i.n}. ${esc(i.caveat)}</p>
    <span class="where">${esc(i.section)}</span></article>`).join('');

  return `
    <div class="grid wide">
      <section class="panel">
        <h3>Findings ready to report</h3>
        <p class="sub">Each is written to be pasted into the paper <em>with its caveat</em>.
          The caveat is not decoration: the fastest way for this study to be misquoted is
          for a sentence to travel without its qualification. Findings below n = ${d.min_n}
          are not produced at all.</p>
        ${findings || `<p class="empty">Nothing yet meets the minimum n required to report a
          figure. This fills in as collection continues.</p>`}
      </section>

      <section class="panel">
        <h3>Findings draft</h3>
        <p class="sub">The same content as Markdown, ready for the paper or an email.
          Edit it here before copying; this is a draft, not an output.</p>
        <div class="row" style="margin-bottom:10px">
          <button type="button" class="btn" id="copyreport">Copy to clipboard</button>
          <button type="button" class="btn ghost" id="dlreport">Download .md</button>
          <button type="button" class="btn ghost" id="dljson">Download raw data (JSON)</button>
        </div>
        <textarea id="reportbox" spellcheck="false" aria-label="Findings draft"></textarea>
      </section>
    </div>`;
}

/* ============================================================ app shell === */

let current = 'overview';

function renderTabs() {
  $('#tabs').innerHTML = VIEWS.map(([id, label]) =>
    `<button role="tab" data-view="${id}" aria-selected="${id === current}">${esc(label)}</button>`).join('');
  $$('#tabs button').forEach(b => b.addEventListener('click', () => {
    current = b.dataset.view;
    location.hash = current;
    renderTabs();
    renderView();
  }));
}

function renderView() {
  const entry = VIEWS.find(v => v[0] === current) || VIEWS[0];
  const view = $('#view');
  // Hold the previous render rather than flashing a skeleton: no layout jump.
  view.style.opacity = '0.55';
  try {
    view.innerHTML = entry[2](DATA);
  } catch (e) {
    view.innerHTML = `<p class="empty">This view could not be rendered: ${esc(e.message)}.
      The raw payload is still downloadable from the Findings &amp; report tab.</p>`;
    console.error(e);
  }
  view.style.opacity = '1';
  bindTips(view);
  if (current === 'overview') wireOverview(DATA);
  if (current === 'report') wireReport();
  if (current === 'editor') wireEditor();
}

function wireReport() {
  const box = $('#reportbox');
  box.value = 'Building the draft…';
  api('/admin/report.md', true).then(text => { box.value = text; })
    .catch(e => { box.value = 'Could not load the draft: ' + e.message; });

  $('#copyreport').addEventListener('click', async () => {
    try {
      await navigator.clipboard.writeText(box.value);
      $('#copyreport').textContent = 'Copied';
      setTimeout(() => { $('#copyreport').textContent = 'Copy to clipboard'; }, 1600);
    } catch (e) {
      box.select();                        // clipboard API needs a secure context
      $('#copyreport').textContent = 'Selected: press ⌘/Ctrl+C';
    }
  });
  $('#dlreport').addEventListener('click', () =>
    download(box.value, 'aimap-findings-draft.md', 'text/markdown'));
  $('#dljson').addEventListener('click', () =>
    download(JSON.stringify(DATA, null, 2), 'aimap-dashboard.json', 'application/json'));
}

function download(text, name, type) {
  const url = URL.createObjectURL(new Blob([text], { type: type + ';charset=utf-8' }));
  const a = document.createElement('a');
  a.href = url; a.download = name; a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

/* ==================================================================== */
/*  EDITOR -- the live, Google-Forms-style question builder.            */
/*                                                                      */
/*  Structural edits (add/remove/reorder question or option, change a   */
/*  type, toggle a checkbox) re-render the whole editor body: infrequent */
/*  enough that a full redraw is cheap and far simpler than patching.   */
/*  TEXT edits (question wording, option labels, ids) do NOT re-render: */
/*  they write straight into the in-memory document via a delegated     */
/*  `input` listener and a dotted path, so the input keeps its cursor   */
/*  and focus -- redrawing a text field on every keystroke is the       */
/*  textbook way a hand-rolled form editor becomes unusable.            */
/* ==================================================================== */

const QUESTION_TYPES = [
  'single', 'multi', 'checklist', 'scale', 'likert_grid', 'matrix',
  'text', 'longtext', 'number', 'email', 'phone', 'consent', 'info',
];

const OPTION_BEARING = new Set(['single', 'multi', 'checklist']);

/* The questionnaire used to be three separate instruments (ORG/IND/CIT), each
   independently draftable through its own editor tab. They have since been
   merged into one file, tools/schema/questionnaire.json -- organization-branch
   sections keep their old ids, practitioner-branch sections and questions are
   prefixed "P", citizen-branch ones "Z", and a first section "R" routes a
   respondent into one branch. There is one document to edit now, so EDITOR no
   longer keys its state by instrument code. */
const EDITOR = {
  doc: null,
  dirty: false,
  published: null,
  publishedAt: null,
  wired: false,
  saving: false,
  errors: null,    // [messages] after a rejected publish
  openSections: new Set(),
  hasDraft: false,   // from the GET's own response
};

function getPath(obj, path) {
  return path.split('.').reduce((o, k) => (o == null ? o : o[k]), obj);
}

function setPath(obj, path, value) {
  const parts = path.split('.');
  let node = obj;
  for (let i = 0; i < parts.length - 1; i++) node = node[parts[i]];
  node[parts[parts.length - 1]] = value;
}

/* A fresh, minimally sane question of a given type -- used both for "add
   question" and for re-shaping a question whose type was just changed, so
   switching from 'single' to 'likert_grid' does not leave stale `options`
   sitting next to a grid with no rows. */
function blankQuestion(type, id) {
  const base = { id: id || 'NEW', type, text: type === 'info' ? '' : 'New question' };
  if (OPTION_BEARING.has(type)) {
    base.options = [{ value: 'a', label: 'Option A' }, { value: 'b', label: 'Option B' }];
  } else if (type === 'scale') {
    base.scale = { min: 1, max: 5, min_label: 'Low', max_label: 'High' };
  } else if (type === 'likert_grid') {
    base.rows = [{ value: 'row1', label: 'First statement' }];
    base.scale = [{ value: '1', label: 'Disagree' }, { value: '5', label: 'Agree' }];
  } else if (type === 'matrix') {
    base.row_options = [{ value: 'row1', label: 'First item' }];
    base.col_options = [{ value: '0', label: 'No' }, { value: '1', label: 'Yes' }];
  } else if (type === 'consent') {
    delete base.text;
  }
  return base;
}

function reshapeForType(q, newType) {
  const fresh = blankQuestion(newType, q.id);
  // Keep what still makes sense across the change; drop what does not.
  const kept = { id: q.id, type: newType, text: q.text, help: q.help,
                required: q.required, optional: q.optional, core: q.core };
  Object.assign(q, fresh, Object.fromEntries(Object.entries(kept).filter(([, v]) => v !== undefined)));
}

function slugify(label, existing) {
  let base = String(label || 'opt').toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_+|_+$/g, '') || 'opt';
  let v = base, n = 1;
  while (existing.includes(v)) v = base + '_' + (n++);
  return v;
}

/* ------------------------------------------------------------- rendering */

function viewEditor() {
  return `
    <div id="editorRoot">
      <div class="editortop">
        <div id="editorStatus" class="editorstatus">loading…</div>
        <div class="row" style="margin:0">
          <button type="button" class="btn ghost" id="edDiscard">Discard changes</button>
          <button type="button" class="btn ghost" id="edSaveOnly">Save draft</button>
          <button type="button" class="btn" id="edPublish">Publish</button>
          <button type="button" class="btn ghost" id="edUnpublish" hidden>Unpublish</button>
        </div>
      </div>
      <div id="edErrors" hidden></div>
      <p class="fine" style="margin:6px 0 16px">
        Editing here is a safety net, not the full pre-fieldwork check. Before real
        fieldwork, also run <code>tools/scripts/validate_schema.py</code> on the command
        line -- it checks routing order and constraint reachability this editor does not.
      </p>
      <div id="editorBody"><p class="empty">Loading…</p></div>
    </div>`;
}

function editorStatusLine() {
  const pub = EDITOR.published;
  const bits = [];
  bits.push(pub
    ? `<span style="color:var(--ok)">● PUBLISHED</span>${EDITOR.publishedAt ? ' since ' + new Date(EDITOR.publishedAt).toLocaleString('en-GB') : ''}`
    : `<span style="color:var(--warn-c)">● DRAFT: not visible to respondents</span>`);
  if (EDITOR.hasDraft) bits.push('<b>there are unsaved changes waiting to be published</b>');
  if (EDITOR.dirty) bits.push('<b>edited just now: click Save draft</b>');
  return bits.join(' · ');
}

async function wireEditor() {
  if (!EDITOR.wired) {
    EDITOR.wired = true;
    // Delegated listeners, bound ONCE to `document`: renderEditorBody() replaces
    // #editorBody's innerHTML on every structural edit, but never detaches this.
    document.addEventListener('input', onEditorInput);
    document.addEventListener('change', onEditorInput);
    document.addEventListener('click', onEditorClick);
  }

  $('#edDiscard').onclick = () => editorAction('discard');
  $('#edSaveOnly').onclick = () => editorAction('save');
  $('#edPublish').onclick = () => editorAction('publish');
  $('#edUnpublish').onclick = () => editorAction('unpublish');

  await loadEditorState();
  await loadEditorDocument();
}

async function loadEditorState() {
  // The published flag has one public source of truth: /api/schema/state,
  // the same endpoint index.html uses; has_draft comes back on the
  // GET /admin/schema response instead of a separate call.
  try {
    const r = await fetch('/api/schema/state'); const j = await r.json();
    EDITOR.published = j.published;
    EDITOR.publishedAt = j.published_at;
  } catch (e) { EDITOR.published = null; }
  $('#edUnpublish').hidden = !EDITOR.published;
}

async function loadEditorDocument() {
  $('#editorBody').innerHTML = '<p class="empty">Loading…</p>';
  try {
    const r = await api('/admin/schema');
    EDITOR.doc = r.content;
    EDITOR.published = r.published;
    EDITOR.hasDraft = r.has_draft;
    $('#edUnpublish').hidden = !EDITOR.published;
    EDITOR.dirty = false;
    // Open the first section only the FIRST time the document is loaded in
    // this session; afterwards, whatever the admin opened or closed persists
    // across every structural re-render (see the toggle listener below) --
    // otherwise adding a question anywhere but section 1 would collapse the
    // very section being edited the instant it changed shape.
    if (EDITOR.openSections.size === 0 && r.content.sections.length) {
      EDITOR.openSections.add(r.content.sections[0].id);
    }
    renderEditorBody();
  } catch (e) {
    $('#editorBody').innerHTML = `<p class="empty">Could not load the questionnaire: ${esc(e.message)}</p>`;
  }
}

/* The merged document holds three respondent branches back to back: section
   "R" routes the respondent, then organization-branch sections (ids
   unchanged from the old org.json), then practitioner-branch sections (ids
   prefixed "P"), then citizen-branch sections (ids prefixed "Z"). A plain id
   gives no visual cue which branch a section belongs to, so a label is
   inserted into the list wherever the branch changes -- cosmetic only, it is
   not written back into the document. */
function sectionBranch(id) {
  if (id === 'R') return 'Routing (shown to every respondent)';
  if (id.startsWith('P')) return 'Practitioner branch';
  if (id.startsWith('Z')) return 'Citizen branch';
  return 'Organization branch';
}

function renderEditorBody() {
  const doc = EDITOR.doc;
  $('#editorStatus').innerHTML = editorStatusLine();
  if (!doc) { $('#editorBody').innerHTML = '<p class="empty">Nothing loaded.</p>'; return; }
  let lastBranch = null;
  const parts = [];
  doc.sections.forEach((sec, si) => {
    const branch = sectionBranch(sec.id);
    if (branch !== lastBranch) {
      parts.push(`<div class="edbranch">${esc(branch)}</div>`);
      lastBranch = branch;
    }
    parts.push(sectionCardHTML(sec, si, doc.sections.length));
  });
  $('#editorBody').innerHTML = parts.join('') + `
    <div class="row" style="margin:18px 0 40px">
      <button type="button" class="btn ghost" data-action="add-section">+ Add section</button>
    </div>`;
  // <details> does not bubble its native `toggle` event, so it cannot be
  // caught by the delegated listeners on document -- each one gets its own,
  // re-attached after every redraw, recording open/closed into EDITOR state so
  // the NEXT redraw (triggered by an edit inside a DIFFERENT section entirely)
  // does not silently close the one the admin is actually looking at.
  $$('#editorBody .edsection').forEach(el => {
    el.addEventListener('toggle', () => {
      const id = el.dataset.secid;
      if (el.open) EDITOR.openSections.add(id);
      else EDITOR.openSections.delete(id);
    });
  });
}

function sectionCardHTML(sec, si, total) {
  const qs = (sec.questions || []).map((q, qi) =>
    questionCardHTML(si, qi, q, sec.questions.length)).join('');
  const isOpen = EDITOR.openSections.has(sec.id);
  return `
    <details class="edsection" data-secid="${esc(sec.id)}" ${isOpen ? 'open' : ''}>
      <summary>
        <input type="text" class="edsecid" data-field data-path="sections.${si}.id"
               value="${esc(sec.id)}" title="Section id" style="width:64px">
        <input type="text" class="edsectitle" data-field data-path="sections.${si}.title"
               value="${esc(sec.title || '')}" placeholder="Section title">
        <span class="edcount">${(sec.questions || []).length} question(s)</span>
        <span class="edmove">
          <button type="button" class="iconbtn" data-action="move-section" data-dir="-1"
                  data-si="${si}" ${si === 0 ? 'disabled' : ''} title="Move up">↑</button>
          <button type="button" class="iconbtn" data-action="move-section" data-dir="1"
                  data-si="${si}" ${si === total - 1 ? 'disabled' : ''} title="Move down">↓</button>
          <button type="button" class="iconbtn danger" data-action="delete-section" data-si="${si}"
                  title="Delete this whole section">✕</button>
        </span>
      </summary>
      <div class="edquestions">${qs}
        <button type="button" class="btn ghost" data-action="add-question" data-si="${si}">
          + Add question to this section</button>
      </div>
    </details>`;
}

function optionRowsHTML(path, opts, noun) {
  opts = opts || [];
  return `<div class="edoptions" data-optpath="${path}">
    ${opts.map((o, oi) => `
      <div class="edoptrow">
        <input type="text" data-field data-path="${path}.${oi}.value" value="${esc(o.value)}"
               class="edoptval" title="value">
        <input type="text" data-field data-path="${path}.${oi}.label" value="${esc(o.label || '')}"
               class="edoptlabel" placeholder="Label" title="label">
        <button type="button" class="iconbtn danger" data-action="delete-option"
                data-path="${path}" data-oi="${oi}" ${opts.length <= 1 ? 'disabled' : ''}
                title="Remove">✕</button>
      </div>`).join('')}
    <button type="button" class="linkbtn" data-action="add-option" data-path="${path}">
      + Add ${esc(noun || 'option')}</button>
  </div>`;
}

function questionCardHTML(si, qi, q, total) {
  const base = `sections.${si}.questions.${qi}`;
  const t = q.type;
  let body = '';
  if (t !== 'info' && t !== 'consent') {
    body += `<label class="edlbl">Question text
      <textarea data-field data-path="${base}.text" rows="2">${esc(q.text || '')}</textarea></label>`;
  } else if (t === 'consent') {
    body += `<p class="fine">Renders the shared consent text from common.json; nothing to edit here.</p>`;
  } else {
    body += `<label class="edlbl">Information text shown to the respondent
      <textarea data-field data-path="${base}.text" rows="2">${esc(q.text || '')}</textarea></label>`;
  }
  body += `<label class="edlbl">Help text (optional, shown under the question)
    <input type="text" data-field data-path="${base}.help" value="${esc(q.help || '')}"></label>`;

  if (OPTION_BEARING.has(t)) {
    body += optionRowsHTML(base + '.options', q.options, 'option');
  } else if (t === 'likert_grid') {
    body += `<div class="edgridcols"><div><b>Rows (what is being rated)</b>
      ${optionRowsHTML(base + '.rows', q.rows, 'row')}</div>
      <div><b>Scale</b>${optionRowsHTML(base + '.scale', q.scale, 'scale point')}</div></div>`;
  } else if (t === 'matrix') {
    body += `<div class="edgridcols"><div><b>Rows</b>
      ${optionRowsHTML(base + '.row_options', q.row_options, 'row')}</div>
      <div><b>Columns / status options</b>
      ${optionRowsHTML(base + '.col_options', q.col_options, 'column')}</div></div>`;
  } else if (t === 'scale') {
    const sc = q.scale || {};
    body += `<div class="edscalebar">
      <label>Min <input type="number" data-field data-path="${base}.scale.min" value="${sc.min ?? 1}" style="width:64px"></label>
      <label>Max <input type="number" data-field data-path="${base}.scale.max" value="${sc.max ?? 5}" style="width:64px"></label>
      <label>Low label <input type="text" data-field data-path="${base}.scale.min_label" value="${esc(sc.min_label || '')}"></label>
      <label>High label <input type="text" data-field data-path="${base}.scale.max_label" value="${esc(sc.max_label || '')}"></label>
    </div>`;
  }

  return `<div class="edq">
    <div class="edqhead">
      <input type="text" class="edqid" data-field data-path="${base}.id" value="${esc(q.id)}"
             title="Question id: used by scoring and routing, change with care" style="width:70px">
      <select data-field data-action="type-change" data-path="${base}.type" data-si="${si}" data-qi="${qi}">
        ${QUESTION_TYPES.map(x => `<option value="${x}" ${x === t ? 'selected' : ''}>${x}</option>`).join('')}
      </select>
      <label class="edcheck"><input type="checkbox" data-field data-checkbox data-path="${base}.optional" ${q.optional ? 'checked' : ''}> optional</label>
      <label class="edcheck"><input type="checkbox" data-field data-checkbox data-path="${base}.core" ${q.core ? 'checked' : ''}> core (short form)</label>
      <span class="edmove">
        <button type="button" class="iconbtn" data-action="move-question" data-dir="-1" data-si="${si}" data-qi="${qi}" ${qi === 0 ? 'disabled' : ''} title="Move up">↑</button>
        <button type="button" class="iconbtn" data-action="move-question" data-dir="1" data-si="${si}" data-qi="${qi}" ${qi === total - 1 ? 'disabled' : ''} title="Move down">↓</button>
        <button type="button" class="iconbtn" data-action="duplicate-question" data-si="${si}" data-qi="${qi}" title="Duplicate">⧉</button>
        <button type="button" class="iconbtn danger" data-action="delete-question" data-si="${si}" data-qi="${qi}" title="Delete">✕</button>
      </span>
    </div>
    ${body}
  </div>`;
}

/* ---------------------------------------------------------------- events */

function onEditorInput(e) {
  const el = e.target;
  if (!el.matches('[data-field]') || !el.dataset.path) return;
  const doc = EDITOR.doc;
  if (!doc) return;
  if (el.dataset.action === 'type-change') {
    const si = +el.dataset.si, qi = +el.dataset.qi;
    reshapeForType(doc.sections[si].questions[qi], el.value);
    EDITOR.dirty = true;
    renderEditorBody();          // structure changed: a full redraw is right here
    return;
  }
  let value = el.type === 'checkbox' ? (el.checked || undefined) : el.value;
  if (el.tagName === 'SELECT' && el.dataset.path.endsWith('.type')) return; // handled above
  if (el.type === 'number') value = el.value === '' ? undefined : Number(el.value);
  try { setPath(doc, el.dataset.path, value); } catch (err) { return; }
  EDITOR.dirty = true;
  $('#editorStatus').innerHTML = editorStatusLine();
}

function onEditorClick(e) {
  const btn = e.target.closest('[data-action]');
  if (!btn) return;
  const action = btn.dataset.action;
  if (!['add-section', 'delete-section', 'move-section', 'add-question', 'delete-question',
        'move-question', 'duplicate-question', 'add-option', 'delete-option'].includes(action)) return;
  const doc = EDITOR.doc;
  if (!doc) return;

  if (action === 'add-section') {
    const id = prompt('Short id for the new section (letters/digits, e.g. "X1"):', 'NEW');
    if (!id) return;
    doc.sections.push({ id, title: 'New section', questions: [blankQuestion('single', 'Q1')] });
  } else if (action === 'delete-section') {
    const si = +btn.dataset.si;
    if (!confirm(`Delete section "${doc.sections[si].id}" and all ${doc.sections[si].questions.length} question(s) in it?`)) return;
    doc.sections.splice(si, 1);
  } else if (action === 'move-section') {
    const si = +btn.dataset.si, dir = +btn.dataset.dir, target = si + dir;
    if (target < 0 || target >= doc.sections.length) return;
    [doc.sections[si], doc.sections[target]] = [doc.sections[target], doc.sections[si]];
  } else if (action === 'add-question') {
    const si = +btn.dataset.si;
    const existing = doc.sections[si].questions.map(q => q.id);
    doc.sections[si].questions.push(blankQuestion('single', slugify('new', existing).toUpperCase()));
  } else if (action === 'delete-question') {
    const si = +btn.dataset.si, qi = +btn.dataset.qi;
    if (!confirm('Delete this question?')) return;
    doc.sections[si].questions.splice(qi, 1);
  } else if (action === 'duplicate-question') {
    const si = +btn.dataset.si, qi = +btn.dataset.qi;
    const copy = JSON.parse(JSON.stringify(doc.sections[si].questions[qi]));
    const existing = doc.sections[si].questions.map(q => q.id);
    copy.id = slugify(copy.id + '_copy', existing).toUpperCase();
    doc.sections[si].questions.splice(qi + 1, 0, copy);
  } else if (action === 'move-question') {
    const si = +btn.dataset.si, qi = +btn.dataset.qi, dir = +btn.dataset.dir, target = qi + dir;
    const arr = doc.sections[si].questions;
    if (target < 0 || target >= arr.length) return;
    [arr[qi], arr[target]] = [arr[target], arr[qi]];
  } else if (action === 'add-option') {
    const arr = getPath(doc, btn.dataset.path) || [];
    const existing = arr.map(o => o.value);
    arr.push({ value: slugify('opt', existing), label: 'New option' });
    setPath(doc, btn.dataset.path, arr);
  } else if (action === 'delete-option') {
    const arr = getPath(doc, btn.dataset.path);
    const oi = +btn.dataset.oi;
    if (arr.length <= 1) return;
    arr.splice(oi, 1);
  }
  EDITOR.dirty = true;
  renderEditorBody();
}

async function editorAction(kind) {
  const showErrors = (errors) => {
    EDITOR.errors = errors;
    const box = $('#edErrors');
    if (!errors || !errors.length) { box.hidden = true; return; }
    box.hidden = false;
    box.innerHTML = `<div class="alert act"><span class="ico">▲</span><span class="msg">
      <span class="tag">Publish blocked</span>: fix these and try again:
      ${errors.map(m => `<br>${esc(m)}`).join('')}
      </span></div>`;
  };
  try {
    if (kind === 'save') {
      await apiSend('/admin/schema', 'PUT', { content: EDITOR.doc });
      EDITOR.dirty = false;
      EDITOR.hasDraft = true;
      showErrors(null);
    } else if (kind === 'discard') {
      if (!confirm('Discard all unsaved and saved-but-unpublished changes?')) return;
      await apiSend('/admin/schema/discard', 'POST');
      await loadEditorDocument();
      showErrors(null);
      return;
    } else if (kind === 'publish') {
      // Save the current in-memory state before publishing, so an edit made
      // seconds ago is not silently lost.
      await apiSend('/admin/schema', 'PUT', { content: EDITOR.doc });
      await apiSend('/admin/schema/publish', 'POST');
      EDITOR.dirty = false;
      EDITOR.hasDraft = false;  // publish clears the draft
      showErrors(null);
      alert('Published. The questionnaire is now live; opening the survey no longer asks '
           + 'to build or conduct it.');
    } else if (kind === 'unpublish') {
      if (!confirm('Unpublish? The site will show the build/conduct choice again until you '
                  + 'publish again.')) return;
      await apiSend('/admin/schema/unpublish', 'POST');
    }
  } catch (e) {
    if (e.detail && e.detail.errors) { showErrors(e.detail.errors); return; }
    alert('Could not complete that action: ' + e.message);
    return;
  }
  await loadEditorState();
  renderEditorBody();
}


/* ------------------------------------------------------------------- data */

/* The session cookie is HttpOnly, so there is nothing to attach here: the
   browser sends it, and this code cannot read it even if it wanted to. That is
   the point -- a script injected into this page cannot steal the credential. */
async function api(path, asText) {
  const r = await fetch(path, { credentials: 'same-origin' });
  if (r.status === 401 || r.status === 404) {
    location.reload();                 // the session expired: back to the sign-in page
    throw new Error('session expired');
  }
  if (r.status === 429) throw new Error('too many failed attempts: wait and retry');
  if (r.status === 503) throw new Error('AIMAP_ADMIN_TOKEN is not set on the server');
  if (!r.ok) throw new Error('server returned ' + r.status);
  return asText ? r.text() : r.json();
}

/* PUT/POST with a JSON body, for the editor. Same session cookie, same error
   handling as api() -- kept separate because most of the app only ever reads. */
async function apiSend(path, method, body) {
  const r = await fetch(path, {
    method, credentials: 'same-origin',
    headers: body !== undefined ? { 'Content-Type': 'application/json' } : {},
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  if (r.status === 401) { location.reload(); throw new Error('session expired'); }
  if (r.status === 429) throw new Error('too many failed attempts: wait and retry');
  let payload = null;
  try { payload = await r.json(); } catch (e) { /* no body */ }
  if (!r.ok) {
    const detail = payload && payload.detail;
    const err = new Error(typeof detail === 'string' ? detail : (r.status + ' ' + r.statusText));
    err.detail = detail;
    throw err;
  }
  return payload;
}

async function signOut() {
  try { await fetch('/admin/logout', { method: 'POST', credentials: 'same-origin' }); }
  finally { location.reload(); }
}

async function load() {
  $('#netstat').textContent = 'loading…';
  DATA = await api('/admin/dashboard');
  $('#asof').textContent = 'as of ' + new Date(DATA.generated_at).toLocaleString('en-GB') +
    ' · instrument ' + DATA.instrument_version;
  $('#netstat').textContent = DATA.fieldwork.total + ' responses';
  renderTabs();
  renderView();
}

function init() {
  const hash = location.hash.replace('#', '');
  if (VIEWS.some(v => v[0] === hash)) current = hash;

  $('#refresh').addEventListener('click', () => load().catch(e => alert(e.message)));
  $('#signout').addEventListener('click', signOut);
  $('#tablemode').addEventListener('change', e =>
    document.body.classList.toggle('tables', e.target.checked));

  // Reaching this file at all means the session is valid -- the server does not
  // serve it otherwise -- so there is no gate to pass here any more.
  $('#app').hidden = false;
  load().catch(e => {
    $('#view').innerHTML = '<p class="empty">Could not load: ' + esc(e.message) + '</p>';
  });
}

document.addEventListener('DOMContentLoaded', init);
