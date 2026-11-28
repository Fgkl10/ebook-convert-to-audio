// The web page: display only. Every book operation is a call to the JSON API (D-032); nothing here cleans or
// converts. The Android app uses the same API.
const API = '/api/v1';
const $ = (s) => document.querySelector(s);

// Pairing (D-037): a phone opens the QR code's address, …/#token=…. The token is kept in this browser and sent
// with every API call: a header on fetch, ?token= on URLs the browser loads itself (audio, images, downloads).
// The PC's own browser needs no token.
let TOKEN = '';
try { TOKEN = localStorage.getItem('ebookAudioToken') || ''; } catch (e) { /* storage blocked: header-less */ }
if (location.hash.startsWith('#token=')) {
  TOKEN = decodeURIComponent(location.hash.slice('#token='.length));
  try { localStorage.setItem('ebookAudioToken', TOKEN); } catch (e) { /* kept for this visit only */ }
  history.replaceState(null, '', location.pathname + location.search);  // the token leaves the address bar
}
const tok = (url) => TOKEN ? `${url}${url.includes('?') ? '&' : '?'}token=${encodeURIComponent(TOKEN)}` : url;
const plainFetch = window.fetch.bind(window);
window.fetch = (url, opts = {}) => TOKEN && String(url).startsWith(API)
  ? plainFetch(url, { ...opts, headers: { ...(opts.headers || {}), Authorization: `Bearer ${TOKEN}` } })
  : plainFetch(url, opts);
// ---------------- languages (D-040): English, Simplified and Traditional Chinese. The text lives in
// /static/i18n/<lang>.json; t(key, {name: …}) fills {name}. A missing key falls back to English, then to the key.
const LANGS = ['en', 'zh-Hans', 'zh-Hant'];
let LANG = 'en', STRINGS = {}, FALLBACK = {};
function pickLang() {
  try { const saved = localStorage.getItem('ebookAudioLang'); if (LANGS.includes(saved)) return saved; }
  catch (e) { /* storage blocked: follow the browser */ }
  for (const l of navigator.languages || [navigator.language || 'en']) {
    const x = String(l).toLowerCase();
    if (x.startsWith('zh')) return /hant|-tw|-hk|-mo/.test(x) ? 'zh-Hant' : 'zh-Hans';
    if (x.startsWith('en')) return 'en';
  }
  return 'en';
}
const t = (key, vars = {}) => String(STRINGS[key] ?? FALLBACK[key] ?? key)
  .replace(/\{(\w+)\}/g, (m, k) => (k in vars ? vars[k] : m));
async function loadStrings() {
  LANG = pickLang();
  const get = async (l) => { try { return await (await fetch(`/static/i18n/${l}.json`)).json(); } catch (e) { return {}; } };
  FALLBACK = await get('en');
  STRINGS = LANG === 'en' ? FALLBACK : await get(LANG);
  document.documentElement.lang = LANG;
  document.title = t('app.name');
  document.querySelectorAll('[data-i18n]').forEach(el => el.textContent = t(el.dataset.i18n));
  document.querySelectorAll('[data-i18n-html]').forEach(el => el.innerHTML = t(el.dataset.i18nHtml));  // our own files
  document.querySelectorAll('[data-i18n-title]').forEach(el => el.title = t(el.dataset.i18nTitle));
  document.querySelectorAll('[data-i18n-placeholder]').forEach(el => el.placeholder = t(el.dataset.i18nPlaceholder));
  document.querySelectorAll('[data-i18n-aria]').forEach(el => el.setAttribute('aria-label', t(el.dataset.i18nAria)));
  document.querySelectorAll('#langs [data-lang]').forEach(b => {
    b.classList.toggle('on', b.dataset.lang === LANG);
    b.setAttribute('aria-pressed', b.dataset.lang === LANG);
    // the choice is kept in this browser; a reload redraws every list in the new language
    b.onclick = () => { try { localStorage.setItem('ebookAudioLang', b.dataset.lang); } catch (e) { /* this visit */ } location.reload(); };
  });
}

const fmt = (ms) => {
  const s = Math.round(ms/1000), h = Math.floor(s/3600), m = Math.floor(s%3600/60);
  return h ? t('dur.hm', { h, m }) : t('dur.ms', { m, s: s % 60 });
};
const esc = (s) => s.replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));

// Every API error is JSON {"detail": ...}; a 422 (wrong field type) has a list there.
async function errText(r) {
  try { const d = (await r.json()).detail; return Array.isArray(d) ? d.map(e => e.msg).join('; ') : d; }
  catch (e) { return `${r.status} ${r.statusText}`; }
}
const getJSON = async (path) => (await fetch(API + path)).json();

async function loadInfo() {
  const r = await fetch(`${API}/info`);
  if (r.status === 401) {  // another device without (or with an old) token
    $('#url').textContent = t('app.not_paired');
    $('#unpaired').hidden = false;
    return;
  }
  const info = await r.json();
  addrs = info.urls;
  setVoiceLanguages(info.languages);
  // The QR code starts on the default (local) address, or on the one picked last time in this browser.
  let saved = {};
  try { saved = JSON.parse(localStorage.getItem('ebookAudioAddress') || '{}'); } catch (e) { /* none */ }
  if (saved.typed && !await addTyped(saved.typed)) saved = {};
  // match the whole URL: a typed address can share its host with a listed one and differ only in the port
  pickAddress(Math.max(0, addrs.findIndex(a => a.url === saved.url)));
}

// ---------------- voices (D-043): every picker is Language ▸ Voice; the Voice list follows the Language.
// The last voice picked for each language is kept in this browser, else the server's default for it.
let VOICE_LANGS = [];  // [{code, voices, default_voice}]
const PICKERS = ['#voice', '#stdvoice', '#rvvoice'];
function savedVoices() {
  try { return JSON.parse(localStorage.getItem('ebookAudioVoices') || '{}'); } catch (e) { return {}; }
}
const voiceLang = (voice) => VOICE_LANGS.find(l => l.voices.includes(voice))?.code;
function preferredVoice(lang) {
  const l = VOICE_LANGS.find(x => x.code === lang), saved = savedVoices()[lang];
  return l && l.voices.includes(saved) ? saved : l?.default_voice;
}
// Show `lang` in the picker whose Voice list is `sel`, with `voice` chosen when it speaks that language.
function setVoice(sel, lang, voice) {
  const l = VOICE_LANGS.find(x => x.code === lang) || VOICE_LANGS[0];
  if (!l) return;
  $(sel + 'lang').value = l.code;
  const pick = l.voices.includes(voice) ? voice : preferredVoice(l.code);
  $(sel).innerHTML = l.voices.map(v => `<option${v === pick ? ' selected' : ''}>${v}</option>`).join('');
}
function setVoiceLanguages(langs) {
  const keep = Object.fromEntries(PICKERS.map(s => [s, $(s).value]));  // a refresh after installing keeps choices
  VOICE_LANGS = langs || [];
  let start = 'en';
  try { start = localStorage.getItem('ebookAudioVoiceLang') || (LANG.startsWith('zh') ? 'zh' : 'en'); } catch (e) { /* */ }
  PICKERS.forEach(s => {
    const name = { en: t('voice_lang.en'), zh: t('voice_lang.zh') };
    $(s + 'lang').innerHTML = VOICE_LANGS.map(l => `<option value="${l.code}">${esc(name[l.code] || l.code)}</option>`).join('');
    setVoice(s, voiceLang(keep[s]) || start, keep[s]);
  });
}
document.querySelectorAll('.vlang').forEach(el => el.onchange = () => {
  setVoice(el.dataset.for, el.value);
  try { localStorage.setItem('ebookAudioVoiceLang', el.value); } catch (e) { /* this visit */ }
  $(el.dataset.for).dispatchEvent(new Event('change'));
});
PICKERS.forEach(s => $(s).addEventListener('change', () => {
  try { localStorage.setItem('ebookAudioVoices', JSON.stringify({ ...savedVoices(), [voiceLang($(s).value)]: $(s).value })); }
  catch (e) { /* not remembered */ }
}));

// The optional Kokoro v1.1-zh model (D-044): install or remove it; while it downloads, the line shows how far it is.
let zhTimer = null;
async function zhModel(method = 'GET') {
  const r = await fetch(`${API}/models/zh`, { method });
  if (!r.ok) { $('#zhstate').textContent = await errText(r); $('#zhstate').classList.add('err'); return; }
  const m = await r.json();
  $('#zhstate').classList.toggle('err', !!m.error);
  // Hugging Face's xet transfer writes the file only at the end, so a count is shown only when there is one.
  const mb = { done: Math.round(m.done_bytes / 1e6), total: Math.round(m.total_bytes / 1e6) };
  $('#zhstate').textContent = m.error || (m.installing
    ? (m.done_bytes ? t('zh.downloading', mb) : t('zh.downloading_start', mb))
    : m.installed ? t('zh.installed') : t('zh.not_installed'));
  $('#zhinstall').hidden = m.installed || m.installing;
  $('#zhremove').hidden = !m.installed;
  clearTimeout(zhTimer);
  if (m.installing) zhTimer = setTimeout(() => zhModel(), 1500);
  else if (zhModel.last !== undefined && m.installed !== zhModel.last) loadInfo();  // the Chinese voice list changed
  zhModel.last = m.installed;
}
$('#zhinstall').onclick = () => zhModel('POST');
$('#zhremove').onclick = () => { if (confirm(t('zh.confirm_remove'))) zhModel('DELETE'); };

// ---------------- the phone's address: the QR code can show any of the PC's addresses, or one typed by hand
let addrs = [];  // [{address, adapter, url, pair_url, qr_svg}], the default first
function pickAddress(i) {
  const a = addrs[i];
  $('#url').textContent = a.url;
  $('#qr').innerHTML = a.qr_svg || '';
  $('#addrs').innerHTML = addrs.map((x, k) => `<button type="button" class="addr${k === i ? ' on' : ''}" data-k="${k}"
    aria-pressed="${k === i}">${esc(x.address)} <span class="muted">${k === 0 && x.adapter !== 'typed' ? `${t('addr.default')} · ` : ''}${esc(x.adapter || t('addr.other'))}</span></button>`).join('');
  document.querySelectorAll('#addrs .addr').forEach(b => b.onclick = () => pickAddress(+b.dataset.k));
  try {
    localStorage.setItem('ebookAudioAddress', JSON.stringify(
      { url: a.url, typed: a.adapter === 'typed' ? a.typedAs : undefined }));
  } catch (e) { /* not remembered */ }
}
async function addTyped(text) {
  const r = await fetch(`${API}/qr?address=${encodeURIComponent(text)}`);
  if (!r.ok) { formMsg('#addrmsg', await errText(r), true); return false; }
  addrs = addrs.filter(a => a.adapter !== 'typed');  // one typed address at a time
  addrs.push({ ...(await r.json()), typedAs: text });
  return true;
}
$('#addrform').onsubmit = async (e) => {
  e.preventDefault();
  formMsg('#addrmsg', '');
  if (await addTyped($('#addrin').value)) { pickAddress(addrs.length - 1); $('#addrin').value = ''; }
};
const show = (id) => ['#home', '#review', '#reader'].forEach(s => $(s).style.display = s === id ? 'block' : 'none');

// ---------------- tabs: Clean | Convert | Library (kept in the URL hash, so a reload stays on the tab)
function showTab() {
  const tab = ['clean', 'convert', 'library'].includes(location.hash.slice(1)) ? location.hash.slice(1) : 'clean';
  document.querySelectorAll('.tabs a').forEach(a => a.classList.toggle('on', a.dataset.tab === tab));
  document.querySelectorAll('.tab').forEach(t => t.classList.toggle('on', t.id === `tab-${tab}`));
}
addEventListener('hashchange', showTab);

// ---------------- voice samples: ▶ next to every Voice list plays ~5 s of that voice (D-031)
const sampleAudio = new Audio();
let sampleBtn = null;
const resetSample = () => { if (sampleBtn) sampleBtn.textContent = '▶'; sampleBtn = null; };
sampleAudio.onended = resetSample;
document.querySelectorAll('.hear').forEach(btn => btn.onclick = async () => {
  const playing = sampleBtn === btn;
  sampleAudio.pause(); resetSample();
  if (playing) return;  // a second click stops it
  sampleBtn = btn; btn.textContent = '…';  // the first sample of a session also loads the model (~10 s)
  sampleAudio.src = tok(`${API}/voices/${$(btn.dataset.for).value}/sample`);
  try { await sampleAudio.play(); if (sampleBtn === btn) btn.textContent = '■'; }
  catch (e) { resetSample(); alert(t('sample.error')); }
});
const goTab = (tab) => { show('#home'); location.hash = tab; showTab(); };

async function loadBooks() {
  const books = await getJSON('/books');
  $('#books').innerHTML = books.length ? books.map(b => `
    <div class="book" data-id="${b.id}">
      ${b.cover ? `<img class="cover" src="${tok(`${API}/books/${b.id}/files/${b.cover}`)}">` : `<div class="cover"></div>`}
      <div class="t">${esc(b.title)}</div>
      <div class="muted">${esc(b.author||'')}<br>${fmt(b.duration_ms)} · ${t('library.chapters', { n: b.chapters_total && b.chapters < b.chapters_total ? t('library.of', { n: b.chapters, total: b.chapters_total }) : b.chapters })}${b.converting ? ` · ${t('library.converting')}` : ''}</div>
    </div>`).join('') : `<div class="muted">${t('library.empty')}</div>`;
  document.querySelectorAll('.book').forEach(el => el.onclick = () => openBook(el.dataset.id));
}

const draftStatus = (s) => ({ cleaning: t('status.cleaning'), review: t('status.review'), queued: t('status.queued'),
  converting: t('status.converting'), done: t('status.done'), error: t('status.error') })[s] || s;
const jobStatus = (s) => ({ queued: t('job.queued'), running: t('job.running'), done: t('job.done'),
  error: t('job.error'), cancelled: t('job.cancelled') })[s] || s;

const CLEAN_STATES = ['cleaning', 'review', 'error'];

function renderDrafts(drafts) {
  draftList('#drafts', drafts.filter(d => CLEAN_STATES.includes(d.status)), t('clean.empty'));
  draftList('#approved', drafts.filter(d => !CLEAN_STATES.includes(d.status)), t('convert.approved_empty'));
  document.querySelectorAll('[data-review]').forEach(el => el.onclick = () => openReview(el.dataset.review));
  document.querySelectorAll('[data-open]').forEach(el => el.onclick = () => openBook(el.dataset.open));
  document.querySelectorAll('[data-discard]').forEach(el => el.onclick = () => discard(el.dataset.discard));
  document.querySelectorAll('[data-cancel]').forEach(el => el.onclick = () => cancelConversion(`/drafts/${el.dataset.cancel}`));
}

// Stop a conversion (D-038): the server keeps running; finished chapters and sentences are kept for a resume.
async function cancelConversion(path) {
  if (!confirm(t('confirm.cancel'))) return;
  const r = await fetch(`${API}${path}/cancel`, { method: 'POST' });
  if (!r.ok) alert(await errText(r));
  pollNow();
}

function draftList(target, drafts, empty) {
  $(target).innerHTML = drafts.length ? `<div class="card">${drafts.map(d => {
    const pct = d.total ? (100*d.done/d.total).toFixed(0) : 0;
    const info = d.chapters ? ` · ${t('draft.chapters', { n: d.chapters })}${d.checks ? ` · <b>${t('draft.checks', { n: d.checks })}</b>` : ''}` : '';
    // "converted 3 of 12" when only some chapters are in the library (D-035)
    const some = d.converted && d.converted.length && d.converted.length < d.chapters
      ? t('draft.partial', { n: d.converted.length, total: d.chapters }) : '';
    const label = some && d.status === 'done' ? some : draftStatus(d.status) + (some ? ` · ${some}` : '');
    const btns = [
      ['queued', 'converting'].includes(d.status) ? `<button data-cancel="${d.id}">${t('btn.cancel')}</button>` : '',
      ['review', 'done'].includes(d.status) ? `<button data-review="${d.id}">${t('btn.review')}</button>` : '',
      d.status === 'done' && d.book_id ? `<button data-open="${d.book_id}">${t('btn.listen')}</button>` : '',
      ['review', 'done', 'error'].includes(d.status) ? `<button data-discard="${d.id}">${t('btn.discard')}</button>` : '',
    ].join(' ');
    return `<div class="job"><div class="row" style="justify-content:space-between"><b>${esc(d.file)}</b>
        <span class="muted">${label}${info}</span></div>
      <div class="row" style="justify-content:space-between"><span class="muted ${d.error?'err':''}">${esc(d.error || d.message)}</span><span>${btns}</span></div>
      ${d.status==='cleaning' && d.total ? `<div class="bar"><div style="width:${pct}%"></div></div>` : ''}</div>`;
  }).join('')}</div>` : `<div class="muted">${empty}</div>`;
}

let lastJobsSig = '';
const pollNow = () => refresh();  // one extra refresh; the 2 s interval keeps running
async function refresh() {
  try {
    const [jobs, drafts] = await Promise.all([getJSON('/jobs'), getJSON('/drafts')]);
    renderDrafts(drafts);
    const active = jobs.filter(j => !['done', 'cancelled'].includes(j.status) || Date.now()/1000 - j.created < 600);
    $('#jobs').innerHTML = active.length ? `<div class="card">${active.map(j => {
      const pct = j.total ? (100*j.done/j.total).toFixed(1) : 0;
      const stop = ['queued', 'running'].includes(j.status) ? `<button data-canceljob="${j.id}">${t('btn.cancel')}</button>` : '';
      return `<div class="job"><div class="row" style="justify-content:space-between"><b>${esc(j.file)}</b><span class="muted">${jobStatus(j.status)}${j.total?` · ${t('job.progress', { done: j.done, total: j.total, pct })}`:''}</span></div>
        <div class="row" style="justify-content:space-between"><span class="muted">${esc(j.error || j.message)}</span><span>${stop}</span></div>${j.status==='running'?`<div class="bar"><div style="width:${pct}%"></div></div>`:''}</div>`;
    }).join('')}</div>` : `<div class="muted">${t('job.empty')}</div>`;
    document.querySelectorAll('[data-canceljob]').forEach(el => el.onclick = () => cancelConversion(`/jobs/${el.dataset.canceljob}`));
    const sig = jobs.map(j => j.status + j.done).join();
    if (sig !== lastJobsSig) { lastJobsSig = sig; loadBooks(); }
  } catch (e) { /* server restarting: try again on the next tick */ }
}

// Each form reports under itself (not in a pop-up), so a slow reply can't look like it came from the other page.
function formMsg(sel, text, isError = false) { $(sel).textContent = text; $(sel).classList.toggle('err', isError); }

// Upload a book to clean; used by the Clean form and by "Clean it now?" on the Convert page.
async function cleanUpload(file, voice, speed, auto, ocr) {
  const fd = new FormData();
  fd.append('file', file);
  fd.append('voice', voice);
  fd.append('speed', speed);
  fd.append('auto', auto);
  fd.append('ocr', ocr);
  const r = await fetch(`${API}/drafts`, { method: 'POST', body: fd });
  return r.ok ? null : await errText(r);
}

$('#auto').onchange = () => $('#go').textContent = $('#auto').checked ? t('clean.go_auto') : t('clean.go');
$('#form').onsubmit = async (e) => {
  e.preventDefault();
  const file = $('#file').files[0];
  $('#go').disabled = true;
  formMsg('#cleanmsg', t('msg.uploading', { name: file.name }));
  const err = await cleanUpload(file, $('#voice').value, $('#speed').value, $('#auto').checked, $('#ocr').value);
  $('#go').disabled = false;
  if (err) { formMsg('#cleanmsg', err, true); return; }
  formMsg('#cleanmsg', t('msg.uploaded', { name: file.name }));
  $('#file').value = ''; ocrForFile();
  pollNow();
};
// OCR only means something for a PDF: greyed out otherwise, with the reason shown.
function ocrForFile() {
  const pdf = /\.pdf$/i.test($('#file').files[0]?.name || '');
  $('#ocr').disabled = !pdf;
  $('#ocrhint').textContent = pdf ? '' : t('ocr.hint');
}
$('#file').onchange = () => { ocrForFile(); formMsg('#cleanmsg', ''); };

$('#stdform').onsubmit = async (e) => {
  e.preventDefault();
  const file = $('#stdfile').files[0];
  const [voice, speed] = [$('#stdvoice').value, $('#stdspeed').value];
  const fd = new FormData();
  fd.append('file', file);
  fd.append('voice', voice);
  fd.append('speed', speed);
  $('#stdgo').disabled = true;
  formMsg('#stdmsg', t('msg.uploading', { name: file.name }));
  const r = await fetch(`${API}/drafts/cleaned`, { method: 'POST', body: fd });
  $('#stdgo').disabled = false;
  if (r.ok) {
    formMsg('#stdmsg', t('msg.converting', { name: file.name }));
    $('#stdfile').value = ''; pollNow(); return;
  }
  const err = await errText(r);
  // An original book on this page: offer to clean it instead of only refusing (D-032 follow-up).
  if (r.status === 400 && /Not a cleaned book/.test(err) && /\.(epub|pdf|txt)$/i.test(file.name)) {
    formMsg('#stdmsg', t('msg.not_cleaned', { name: file.name }), true);
    if (confirm(t('confirm.clean', { name: file.name }))) {
      formMsg('#stdmsg', t('msg.uploading_clean', { name: file.name }));
      const cleanErr = await cleanUpload(file, voice, speed, false, 'auto');
      if (cleanErr) { formMsg('#stdmsg', cleanErr, true); return; }
      formMsg('#stdmsg', ''); $('#stdfile').value = '';
      goTab('clean'); formMsg('#cleanmsg', t('msg.uploaded', { name: file.name })); pollNow();
    }
    return;
  }
  formMsg('#stdmsg', err, true);
};
$('#stdfile').onchange = () => formMsg('#stdmsg', '');

async function discard(id) {
  if (!confirm(t('confirm.discard'))) return false;
  const r = await fetch(`${API}/drafts/${id}`, { method: 'DELETE' });
  if (!r.ok) { alert(await errText(r)); return false; }
  return true;
}

// ---------------- review a cleaned book before converting
let draft = null;
const list = (items) => `<ul>${items.map(t => `<li>${esc(t)}</li>`).join('')}</ul>`;

async function openReview(id) {
  draft = await getJSON(`/drafts/${id}`);
  const rep = draft.report;
  show('#review'); window.scrollTo(0, 0);
  $('#rvtitle').textContent = draft.file;
  $('#rvmethod').textContent = rep.method;
  // Chapters added to a book keep its voice unless the user picks another (D-035). The Language starts on the book's
  // own (D-043): a voice picked at upload in another language gives way to that language's voice.
  setVoice('#rvvoice', rep.language || voiceLang(draft.voice) || 'en', draft.book_voice || draft.voice);
  $('#rvspeed').value = draft.book_speed || draft.speed;
  $('#rvdownload').href = tok(`${API}/drafts/${id}/std.epub`);
  $('#rvchecks').innerHTML = rep.checks.length
    ? `<div class="card checks"><b>${t('review.checks', { n: rep.checks.length })}</b>${list(rep.checks)}</div>` : '';
  // Ticked by default: chapters not converted yet; after an interrupted or failed run, only the ones it was doing.
  const conv = new Set(draft.converted || []), last = draft.last_chapters;
  const resume = last && draft.status === 'review';
  $('#rvchapters').innerHTML = rep.chapters.map(([title, n], i) => {
    const on = !conv.has(i + 1) && (!resume || last.includes(i + 1));
    return `<div data-i="${i}"><input type="checkbox" class="pick" data-n="${i+1}"${on ? ' checked' : ''} aria-label="${esc(t('review.pick_aria', { n: i + 1 }))}"> `
      + `${i+1}. ${esc(title)} <span class="muted">${t('review.chars', { n: n.toLocaleString() })}</span>${conv.has(i + 1) ? ` <span class="ok">${t('review.converted')}</span>` : ''}</div>`;
  }).join('');
  document.querySelectorAll('#rvchapters div').forEach(el => el.onclick = () => reviewChapter(+el.dataset.i));
  document.querySelectorAll('#rvchapters input.pick').forEach(cb => {
    cb.onclick = e => e.stopPropagation();  // ticking doesn't open the chapter
    cb.onchange = updatePick;
  });
  updatePick();
  const more = [
    [t('review.removed'), rep.removed.map(([why, text]) => `${why}: ${text}`)],
    [t('review.toc_ignored'), rep.unconfirmed],
    [t('review.notes'), rep.notes],
  ].filter(([, items]) => items.length);
  $('#rvmore').innerHTML = more.map(([title, items]) =>
    `<details class="card" style="margin-top:10px"><summary>${esc(t('review.count', { title, n: items.length }))}</summary>${list(items)}</details>`).join('');
  if (rep.chapters.length) reviewChapter(0);
}

async function reviewChapter(i) {
  document.querySelectorAll('#rvchapters div').forEach((el, k) => el.classList.toggle('on', k === i));
  const r = await fetch(`${API}/drafts/${draft.id}/chapters/${i}`);
  if (!r.ok) { $('#rvtext').textContent = await errText(r); return; }
  const ch = await r.json();
  $('#rvtext').innerHTML = `<h3>${esc(ch.title)}</h3>` + ch.paragraphs.map(p => `<p>${esc(p)}</p>`).join('');
}

const picked = () => [...document.querySelectorAll('#rvchapters input.pick')].filter(cb => cb.checked).map(cb => +cb.dataset.n);

function updatePick() {
  if (!draft) return;
  const all = draft.report.chapters.length, n = picked().length;
  const btn = $('#rvapprove');
  btn.disabled = !n || !['review', 'done'].includes(draft.status);
  btn.textContent = n === all ? (draft.status === 'done' ? t('review.approve_all_again') : t('review.approve_all'))
    : t(n === 1 ? 'review.approve_one' : 'review.approve_many', { n });
  // Warn when new chapters would be read in another voice than the ones already in the book.
  const kept = (draft.converted || []).filter(k => !picked().includes(k)).length;
  const mix = kept && draft.book_voice
    && ($('#rvvoice').value !== draft.book_voice || +$('#rvspeed').value !== draft.book_speed);
  $('#rvmix').hidden = !mix;
  if (mix) $('#rvmix').textContent = t('review.mix', { voice: draft.book_voice, speed: draft.book_speed });
}
$('#rvvoice').addEventListener('change', updatePick);
$('#rvspeed').addEventListener('input', updatePick);
const setPicks = (want) => (e) => {
  e.preventDefault();
  const conv = new Set(draft.converted || []);
  document.querySelectorAll('#rvchapters input.pick').forEach(cb => cb.checked = want(+cb.dataset.n, conv));
  updatePick();
};
$('#rvall').onclick = setPicks(() => true);
$('#rvnone').onclick = setPicks(() => false);
$('#rvnew').onclick = setPicks((n, conv) => !conv.has(n));

$('#rvback').onclick = () => { show('#home'); draft = null; };
$('#rvapprove').onclick = async () => {
  const chapters = picked();
  const body = JSON.stringify({ voice: $('#rvvoice').value, speed: +$('#rvspeed').value,
                                chapters: chapters.length === draft.report.chapters.length ? null : chapters });
  const r = await fetch(`${API}/drafts/${draft.id}/approve`,
                        { method: 'POST', headers: { 'Content-Type': 'application/json' }, body });
  if (!r.ok) { alert(await errText(r)); return; }
  goTab('convert'); draft = null;  // the approved book now waits on the Convert page
};
$('#rvupload').onclick = () => $('#rvfile').click();
$('#rvfile').onchange = async () => {
  const fd = new FormData();
  fd.append('file', $('#rvfile').files[0]);
  $('#rvfile').value = '';
  const r = await fetch(`${API}/drafts/${draft.id}/std.epub`, { method: 'PUT', body: fd });
  if (!r.ok) { alert(await errText(r)); return; }
  openReview(draft.id);
};
$('#rvdiscard').onclick = async () => { if (await discard(draft.id)) { show('#home'); draft = null; } };

// ---------------- reader with sentence sync
let book = null, chIdx = 0, starts = [], spans = [], cur = -1;
const audio = $('#audio');

async function openBook(id) {
  book = await getJSON(`/books/${id}`);
  show('#reader'); $('#player').hidden = false;
  $('#rtitle').textContent = book.title; $('#rauthor').textContent = book.author || '';
  $('#chapters').innerHTML = book.chapters.map((c, i) => `<div data-i="${i}">${c.number}. ${esc(c.title)} <span class="muted">${fmt(c.duration_ms)}</span>`
    + `<a class="dl" href="${tok(`${API}/books/${esc(book.id)}/files/${esc(c.audio)}?download=1`)}" download title="${esc(t('reader.download'))}" aria-label="${esc(t('reader.download_aria', { title: c.title }))}">⬇</a></div>`).join('');
  document.querySelectorAll('#chapters div').forEach(el => el.onclick = () => loadChapter(+el.dataset.i, 0, true));
  document.querySelectorAll('#chapters a.dl').forEach(a => a.onclick = e => e.stopPropagation());  // download only, no chapter switch
  loadChapter(0, 0, false);
}

function loadChapter(i, atMs, play) {
  chIdx = i; const ch = book.chapters[i];
  document.querySelectorAll('#chapters div').forEach((el, k) => el.classList.toggle('on', k === i));
  $('#nowch').textContent = ch.title;
  const paras = [];
  for (const s of ch.sentences) (paras[s.p] ||= []).push(s);
  const gap = book.language === 'zh' ? '' : ' ';  // Chinese sentences follow each other with no space (D-042)
  $('#text').innerHTML = paras.filter(Boolean).map(p => `<p>${p.map(s => `<span data-i="${s.i}">${esc(s.text)}</span>`).join(gap)}</p>`).join('');
  spans = [...document.querySelectorAll('#text span')];
  spans.forEach(el => el.onclick = () => { audio.currentTime = ch.sentences[+el.dataset.i].start_ms / 1000; audio.play(); });
  starts = ch.sentences.map(s => s.start_ms); cur = -1;
  audio.src = tok(`${API}/books/${book.id}/files/${ch.audio}`);
  audio.playbackRate = +$('#rate').value;
  audio.onloadedmetadata = () => { audio.currentTime = atMs / 1000; if (play) audio.play(); };
}

// Binary search: last sentence with start_ms <= t
function sentenceAt(t) {
  let lo = 0, hi = starts.length - 1, ans = 0;
  while (lo <= hi) { const mid = (lo + hi) >> 1; if (starts[mid] <= t) { ans = mid; lo = mid + 1; } else hi = mid - 1; }
  return ans;
}

let userScrollUntil = 0;
addEventListener('wheel', () => userScrollUntil = Date.now() + 4000, { passive: true });
addEventListener('touchmove', () => userScrollUntil = Date.now() + 4000, { passive: true });

function tick() {
  if (book && spans.length) {
    const i = sentenceAt(audio.currentTime * 1000);
    if (i !== cur) {
      spans[cur]?.classList.remove('cur'); spans[i].classList.add('cur'); cur = i;
      if (Date.now() > userScrollUntil) spans[i].scrollIntoView({ block: 'center', behavior: 'smooth' });
    }
  }
  requestAnimationFrame(tick);
}
requestAnimationFrame(tick);

// Sentence buttons, the same rules as the Android app (android/.../SentenceSync.kt): "previous" restarts the current
// sentence when more than 1.5 s into it, else goes to the one before; "next" does nothing on the last sentence.
const RESTART_MS = 1500;
function seekMs(ms) { audio.currentTime = ms / 1000; if (audio.paused) audio.play(); }
$('#prevs').onclick = () => {
  if (!starts.length) return;
  const t = audio.currentTime * 1000, i = sentenceAt(t);
  seekMs(t - starts[i] > RESTART_MS || i === 0 ? starts[i] : starts[i - 1]);
};
$('#nexts').onclick = () => {
  if (!starts.length) return;
  const i = sentenceAt(audio.currentTime * 1000);
  if (i + 1 < starts.length) seekMs(starts[i + 1]);
};

// Text size, remembered in this browser (12–32 px, steps of 2, like the app).
const TEXT_SIZE = { min: 12, max: 32, step: 2, def: 18 };
function textSize() {
  try { return Math.min(TEXT_SIZE.max, Math.max(TEXT_SIZE.min, +localStorage.getItem('textSize') || TEXT_SIZE.def)); }
  catch (e) { return TEXT_SIZE.def; }
}
function setTextSize(px) {
  px = Math.min(TEXT_SIZE.max, Math.max(TEXT_SIZE.min, px));
  try { localStorage.setItem('textSize', px); } catch (e) { /* private mode: not remembered */ }
  $('#text').style.setProperty('--text-size', px + 'px');
  $('#smaller').disabled = px <= TEXT_SIZE.min; $('#larger').disabled = px >= TEXT_SIZE.max;
}
$('#smaller').onclick = () => setTextSize(textSize() - TEXT_SIZE.step);
$('#larger').onclick = () => setTextSize(textSize() + TEXT_SIZE.step);
setTextSize(textSize());

audio.onended = () => { if (chIdx + 1 < book.chapters.length) loadChapter(chIdx + 1, 0, true); };
$('#rate').onchange = () => audio.playbackRate = +$('#rate').value;
$('#back').onclick = () => { audio.pause(); goTab('library'); $('#player').hidden = true; book = null; };

showTab();
loadStrings().then(() => { ocrForFile(); loadInfo(); zhModel(); refresh(); setInterval(refresh, 2000); });
