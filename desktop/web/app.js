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
const fmt = (ms) => { const s = Math.round(ms/1000), h = Math.floor(s/3600), m = Math.floor(s%3600/60); return h ? `${h}h ${m}m` : `${m}m ${s%60}s`; };
const esc = (t) => t.replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));

// Every API error is JSON {"detail": ...}; a 422 (wrong field type) has a list there.
async function errText(r) {
  try { const d = (await r.json()).detail; return Array.isArray(d) ? d.map(e => e.msg).join('; ') : d; }
  catch (e) { return `${r.status} ${r.statusText}`; }
}
const getJSON = async (path) => (await fetch(API + path)).json();

async function loadInfo() {
  const r = await fetch(`${API}/info`);
  if (r.status === 401) {  // another device without (or with an old) token
    $('#url').textContent = 'not paired';
    $('#unpaired').hidden = false;
    return;
  }
  const info = await r.json();
  addrs = info.urls;
  const opts = info.voices.map(v => `<option ${v===info.default_voice?'selected':''}>${v}</option>`).join('');
  ['#voice', '#rvvoice', '#stdvoice'].forEach(s => $(s).innerHTML = opts);
  // The QR code starts on the default (local) address, or on the one picked last time in this browser.
  let saved = {};
  try { saved = JSON.parse(localStorage.getItem('ebookAudioAddress') || '{}'); } catch (e) { /* none */ }
  if (saved.typed && !await addTyped(saved.typed)) saved = {};
  // match the whole URL: a typed address can share its host with a listed one and differ only in the port
  pickAddress(Math.max(0, addrs.findIndex(a => a.url === saved.url)));
}

// ---------------- the phone's address: the QR code can show any of the PC's addresses, or one typed by hand
let addrs = [];  // [{address, adapter, url, pair_url, qr_svg}], the default first
function pickAddress(i) {
  const a = addrs[i];
  $('#url').textContent = a.url;
  $('#qr').innerHTML = a.qr_svg || '';
  $('#addrs').innerHTML = addrs.map((x, k) => `<button type="button" class="addr${k === i ? ' on' : ''}" data-k="${k}"
    aria-pressed="${k === i}">${esc(x.address)} <span class="muted">${k === 0 && x.adapter !== 'typed' ? 'default · ' : ''}${esc(x.adapter || 'other')}</span></button>`).join('');
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
  catch (e) { resetSample(); alert('Could not play the voice sample.'); }
});
const goTab = (tab) => { show('#home'); location.hash = tab; showTab(); };

async function loadBooks() {
  const books = await getJSON('/books');
  $('#books').innerHTML = books.length ? books.map(b => `
    <div class="book" data-id="${b.id}">
      ${b.cover ? `<img class="cover" src="${tok(`${API}/books/${b.id}/files/${b.cover}`)}">` : `<div class="cover"></div>`}
      <div class="t">${esc(b.title)}</div>
      <div class="muted">${esc(b.author||'')}<br>${fmt(b.duration_ms)} · ${b.chapters_total && b.chapters < b.chapters_total ? `${b.chapters} of ${b.chapters_total}` : b.chapters} ch${b.converting ? ' · converting…' : ''}</div>
    </div>`).join('') : '<div class="muted">No books yet.</div>';
  document.querySelectorAll('.book').forEach(el => el.onclick = () => openBook(el.dataset.id));
}

const DRAFT_STATUS = { cleaning: 'cleaning', review: 'ready for review', queued: 'waiting to convert',
  converting: 'converting', done: 'converted', error: 'failed' };

const CLEAN_STATES = ['cleaning', 'review', 'error'];

function renderDrafts(drafts) {
  draftList('#drafts', drafts.filter(d => CLEAN_STATES.includes(d.status)), 'Nothing here. Add a book above.');
  draftList('#approved', drafts.filter(d => !CLEAN_STATES.includes(d.status)),
            'No approved books yet. Approve one on the Clean page, or upload a cleaned book above.');
  document.querySelectorAll('[data-review]').forEach(el => el.onclick = () => openReview(el.dataset.review));
  document.querySelectorAll('[data-open]').forEach(el => el.onclick = () => openBook(el.dataset.open));
  document.querySelectorAll('[data-discard]').forEach(el => el.onclick = () => discard(el.dataset.discard));
  document.querySelectorAll('[data-cancel]').forEach(el => el.onclick = () => cancelConversion(`/drafts/${el.dataset.cancel}`));
}

// Stop a conversion (D-038): the server keeps running; finished chapters and sentences are kept for a resume.
async function cancelConversion(path) {
  if (!confirm('Cancel this conversion? Finished chapters stay in the library; approving again resumes ' +
               'where it stopped.')) return;
  const r = await fetch(`${API}${path}/cancel`, { method: 'POST' });
  if (!r.ok) alert(await errText(r));
  pollNow();
}

function draftList(target, drafts, empty) {
  $(target).innerHTML = drafts.length ? `<div class="card">${drafts.map(d => {
    const pct = d.total ? (100*d.done/d.total).toFixed(0) : 0;
    const info = d.chapters ? ` · ${d.chapters} ch${d.checks ? ` · <b>${d.checks} to check</b>` : ''}` : '';
    // "converted 3 of 12" when only some chapters are in the library (D-035)
    const some = d.converted && d.converted.length && d.converted.length < d.chapters
      ? `converted ${d.converted.length} of ${d.chapters}` : '';
    const label = some && d.status === 'done' ? some : (DRAFT_STATUS[d.status] || d.status) + (some ? ` · ${some}` : '');
    const btns = [
      ['queued', 'converting'].includes(d.status) ? `<button data-cancel="${d.id}">Cancel</button>` : '',
      ['review', 'done'].includes(d.status) ? `<button data-review="${d.id}">Review</button>` : '',
      d.status === 'done' && d.book_id ? `<button data-open="${d.book_id}">Listen</button>` : '',
      ['review', 'done', 'error'].includes(d.status) ? `<button data-discard="${d.id}">Discard</button>` : '',
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
      const stop = ['queued', 'running'].includes(j.status) ? `<button data-canceljob="${j.id}">Cancel</button>` : '';
      return `<div class="job"><div class="row" style="justify-content:space-between"><b>${esc(j.file)}</b><span class="muted">${j.status}${j.total?` · ${j.done}/${j.total} sentences · ${pct}%`:''}</span></div>
        <div class="row" style="justify-content:space-between"><span class="muted">${esc(j.error || j.message)}</span><span>${stop}</span></div>${j.status==='running'?`<div class="bar"><div style="width:${pct}%"></div></div>`:''}</div>`;
    }).join('')}</div>` : '<div class="muted">No conversions running.</div>';
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

$('#auto').onchange = () => $('#go').textContent = $('#auto').checked ? 'Clean & convert' : 'Clean';
$('#form').onsubmit = async (e) => {
  e.preventDefault();
  const file = $('#file').files[0];
  $('#go').disabled = true;
  formMsg('#cleanmsg', `Uploading ${file.name}…`);
  const err = await cleanUpload(file, $('#voice').value, $('#speed').value, $('#auto').checked, $('#ocr').value);
  $('#go').disabled = false;
  if (err) { formMsg('#cleanmsg', err, true); return; }
  formMsg('#cleanmsg', `${file.name}: uploaded, cleaning below.`);
  $('#file').value = ''; ocrForFile();
  pollNow();
};
// OCR only means something for a PDF: greyed out otherwise, with the reason shown.
function ocrForFile() {
  const pdf = /\.pdf$/i.test($('#file').files[0]?.name || '');
  $('#ocr').disabled = !pdf;
  $('#ocrhint').textContent = pdf ? '' : 'OCR reads scanned PDFs. Pick a PDF to choose a mode; ' +
    'EPUB and TXT files have their own text, so they need no OCR.';
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
  formMsg('#stdmsg', `Uploading ${file.name}…`);
  const r = await fetch(`${API}/drafts/cleaned`, { method: 'POST', body: fd });
  $('#stdgo').disabled = false;
  if (r.ok) {
    formMsg('#stdmsg', `${file.name}: converting, see below.`);
    $('#stdfile').value = ''; pollNow(); return;
  }
  const err = await errText(r);
  // An original book on this page: offer to clean it instead of only refusing (D-032 follow-up).
  if (r.status === 400 && /Not a cleaned book/.test(err) && /\.(epub|pdf|txt)$/i.test(file.name)) {
    formMsg('#stdmsg', `${file.name} is not cleaned yet.`, true);
    if (confirm(`"${file.name}" is not cleaned yet, so it can't be converted directly.\n\nClean it now? ` +
                'It will appear on the Clean page for review.')) {
      formMsg('#stdmsg', `Uploading ${file.name} to clean…`);
      const cleanErr = await cleanUpload(file, voice, speed, false, 'auto');
      if (cleanErr) { formMsg('#stdmsg', cleanErr, true); return; }
      formMsg('#stdmsg', ''); $('#stdfile').value = '';
      goTab('clean'); formMsg('#cleanmsg', `${file.name}: uploaded, cleaning below.`); pollNow();
    }
    return;
  }
  formMsg('#stdmsg', err, true);
};
$('#stdfile').onchange = () => formMsg('#stdmsg', '');

async function discard(id) {
  if (!confirm('Discard this cleaned book? The uploaded file and the cleaned version are deleted.')) return false;
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
  // Chapters added to a book keep its voice unless the user picks another (D-035).
  $('#rvvoice').value = draft.book_voice || draft.voice; $('#rvspeed').value = draft.book_speed || draft.speed;
  $('#rvdownload').href = tok(`${API}/drafts/${id}/std.epub`);
  $('#rvchecks').innerHTML = rep.checks.length
    ? `<div class="card checks"><b>Check by hand (${rep.checks.length})</b>${list(rep.checks)}</div>` : '';
  // Ticked by default: chapters not converted yet; after an interrupted or failed run, only the ones it was doing.
  const conv = new Set(draft.converted || []), last = draft.last_chapters;
  const resume = last && draft.status === 'review';
  $('#rvchapters').innerHTML = rep.chapters.map(([t, n], i) => {
    const on = !conv.has(i + 1) && (!resume || last.includes(i + 1));
    return `<div data-i="${i}"><input type="checkbox" class="pick" data-n="${i+1}"${on ? ' checked' : ''} aria-label="Convert chapter ${i+1}"> `
      + `${i+1}. ${esc(t)} <span class="muted">${n.toLocaleString()} chars</span>${conv.has(i + 1) ? ' <span class="ok">✓ converted</span>' : ''}</div>`;
  }).join('');
  document.querySelectorAll('#rvchapters div').forEach(el => el.onclick = () => reviewChapter(+el.dataset.i));
  document.querySelectorAll('#rvchapters input.pick').forEach(cb => {
    cb.onclick = e => e.stopPropagation();  // ticking doesn't open the chapter
    cb.onchange = updatePick;
  });
  updatePick();
  const more = [
    ['Removed', rep.removed.map(([why, text]) => `${why}: ${text}`)],
    ['TOC entries ignored', rep.unconfirmed],
    ['Notes', rep.notes],
  ].filter(([, items]) => items.length);
  $('#rvmore').innerHTML = more.map(([title, items]) =>
    `<details class="card" style="margin-top:10px"><summary>${title} (${items.length})</summary>${list(items)}</details>`).join('');
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
  btn.textContent = n === all ? (draft.status === 'done' ? 'Convert all again' : 'Approve & convert')
    : `Convert ${n} chapter${n === 1 ? '' : 's'}`;
  // Warn when new chapters would be read in another voice than the ones already in the book.
  const kept = (draft.converted || []).filter(k => !picked().includes(k)).length;
  const mix = kept && draft.book_voice
    && ($('#rvvoice').value !== draft.book_voice || +$('#rvspeed').value !== draft.book_speed);
  $('#rvmix').hidden = !mix;
  if (mix) $('#rvmix').textContent = `Other chapters of this book use ${draft.book_voice} at ${draft.book_speed}×; `
    + 'the book will mix voices.';
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
    + `<a class="dl" href="${tok(`${API}/books/${esc(book.id)}/files/${esc(c.audio)}?download=1`)}" download title="Download this chapter" aria-label="Download ${esc(c.title)}">⬇</a></div>`).join('');
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
  $('#text').innerHTML = paras.filter(Boolean).map(p => `<p>${p.map(s => `<span data-i="${s.i}">${esc(s.text)}</span>`).join(' ')}</p>`).join('');
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

audio.onended = () => { if (chIdx + 1 < book.chapters.length) loadChapter(chIdx + 1, 0, true); };
$('#rate').onchange = () => audio.playbackRate = +$('#rate').value;
$('#back').onclick = () => { audio.pause(); goTab('library'); $('#player').hidden = true; book = null; };

showTab(); ocrForFile(); loadInfo(); refresh(); setInterval(refresh, 2000);
