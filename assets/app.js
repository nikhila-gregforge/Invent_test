'use strict';
const $ = id => document.getElementById(id);
const node = (tag, text, cls) => {
  const el = document.createElement(tag);
  if (text !== undefined) el.textContent = text;
  if (cls) el.className = cls;
  return el;
};
const display = value => {
  if (value == null) return '';
  if (Array.isArray(value)) return value.join('; ');
  if (typeof value === 'object') return value.__excel_date__ || value.__excel_time__ || JSON.stringify(value);
  return String(value);
};
const defaults = () => ({status: 'Errors', field: '', q: '', page: 1, size: 25});
const state = {runs: [], id: null, filters: defaults(), data: null, autoStatus: true, view: '', record: null, recordRun: null, recordKey: null, fields: [], rulesFields: [],
  sequence: 0, busy: false, loading: false, controller: null, returnKey: null, deleteRun: null};
let searchTimer;
function notice(message = '') { $('notice').textContent = message; $('notice').hidden = !message; }
function badge(status, label) {
  return node('span', label || status, 'badge '+({Errors:'failed',Passed:'passed'}[status] || ''));
}
function option(value, label) { const el = node('option', label); el.value = value; return el; }
function button(label, callback, cls = 'quiet') {
  const el = node('button', label, cls); el.type = 'button'; el.addEventListener('click', callback); return el;
}
function dateLabel(value) {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString(undefined, {dateStyle:'medium', timeStyle:'short'});
}
async function api(url, options = {}) {
  const response = await fetch(url, options);
  let data;
  try { data = await response.json(); } catch { throw new Error('The server returned an unreadable response. Please retry.'); }
  if (!response.ok) { const error = new Error(data.error || 'The request failed. Please retry.'); error.data = data; throw error; }
  return data;
}
function rememberFilters() {
  try { sessionStorage.setItem('inventory-review-4', JSON.stringify({id: state.id, filters:state.filters, returnKey:state.returnKey})); } catch { /* Storage is optional. */ }
}
function selectRun(id) {
  if (state.id === id) return;
  state.id = id; state.filters = defaults(); state.data = null; state.fields = []; state.returnKey = null; state.autoStatus = true;
  try {
    const saved = JSON.parse(sessionStorage.getItem('inventory-review-4'));
    if (saved && saved.id === id) {
      for (const key of Object.keys(state.filters)) if (key in saved.filters) state.filters[key] = saved.filters[key];
      state.returnKey = saved.returnKey; state.autoStatus = false;
    }
  } catch { /* A new review still works without saved navigation. */ }
}
function showView(view) {
  state.view = view;
  if (view !== 'review') resetCharts();
  for (const name of ['home','review','record']) $(name+'-view').hidden = name !== view;
  notice();
}
function navigate(hash) {
  if (state.busy) return;
  if (location.hash === hash) route(); else location.hash = hash;
}
function beginRequest() {
  if (state.controller) state.controller.abort();
  state.controller = new AbortController();
  return {sequence: ++state.sequence, signal: state.controller.signal};
}
function isCurrent(sequence, view) { return sequence === state.sequence && state.view === view; }
async function route() {
  clearTimeout(searchTimer);
  const hash = location.hash;
  const match = hash.match(/^#run\/([\w-]+)(?:\/record\/(\d+))?$/);
  if (match) {
    selectRun(match[1]);
    if (match[2] !== undefined) { state.recordKey = Number(match[2]); await loadRecord(); }
    else { showView('review'); await loadResults(true); }
  } else {
    beginRequest(); showView('home'); renderHistory();
  }
}
async function loadHistory() {
  $('home-loading').hidden = false;
  try {
    const data = await api('/api/runs'); state.runs = data.runs;
    $('file-limits').textContent = 'CSV only · '+data.max_bytes/1024/1024+' MiB · '+data.max_rows.toLocaleString()+' records';
    renderHistory();
  }
  catch (error) { notice(error.message); }
  finally { $('home-loading').hidden = true; }
}
function clickableRow(row, title, onOpen) {
  const open = button(title, event => { event.stopPropagation(); onOpen(); }, 'record-open');
  row.addEventListener('click', event => { if (!event.target.closest('button,a')) onOpen(); });
  return open;
}
function renderHistory() {
  $('history').replaceChildren();
  $('history-wrap').hidden = !state.runs.length; $('home-empty').hidden = !!state.runs.length;
  for (const run of state.runs) {
    const row = node('tr'), name = node('td');
    row.dataset.runId = run.id;
    name.append(clickableRow(row, run.filename, () => navigate('#run/'+run.id)));
    if (run.sheet) name.append(node('div',run.sheet,'record-id'));
    const results = node('td'), chips = node('div',undefined,'history-results');
    if (run.archived) chips.append(node('span','Upload again to review','muted small'));
    for (const [status, count] of run.archived ? [] : [['Errors',run.errors],['Passed',run.passed]]) {
      if (count) chips.append(badge(status, count.toLocaleString()+(status === 'Errors' ? ' with errors' : ' passed')));
    }
    results.append(chips);
    row.append(name, node('td',run.total.toLocaleString(),'numeric'), results, node('td',dateLabel(run.created_at),'small muted'));
    const actions = node('td',undefined,'history-actions');
    const remove = button('Delete',event => { event.stopPropagation(); openDelete(run); },'danger review-delete');
    remove.setAttribute('aria-label','Delete review '+run.filename);
    remove.disabled = state.busy; actions.append(remove); row.append(actions);
    $('history').append(row);
  }
}
function setBusy(busy) {
  state.busy = busy;
  for (const el of document.querySelectorAll('.upload-trigger, #home-button, #upload-dialog button, #upload-dialog input, #upload-dialog select, .review-delete, #delete-dialog button')) el.disabled = busy;
}
function openDelete(run) {
  if (state.busy) return;
  state.deleteRun = run;
  $('delete-message').textContent = 'Delete the saved review and uploaded copy for “'+run.filename+'”?';
  $('delete-error').hidden = true;
  $('delete-dialog').showModal();
  $('delete-cancel').focus();
}
$('delete-dialog').addEventListener('cancel',event => { if (state.busy) event.preventDefault(); });
$('delete-dialog').addEventListener('close',() => { state.deleteRun = null; });
$('delete-confirm').addEventListener('click',async () => {
  if (state.busy || !state.deleteRun) return;
  const id = state.deleteRun.id;
  $('delete-error').hidden = true; setBusy(true); $('delete-confirm').textContent = 'Deleting…';
  try {
    await api('/api/runs/'+encodeURIComponent(id),{method:'DELETE',headers:{'X-Requested-With':'AIInventory'}});
    state.runs = state.runs.filter(run => run.id !== id);
    if (state.id === id) {
      state.id = null; state.data = null; state.record = null; state.recordRun = null;
      state.recordKey = null; state.fields = []; state.returnKey = null;
    }
    try {
      const saved = JSON.parse(sessionStorage.getItem('inventory-review-4'));
      if (saved && saved.id === id) sessionStorage.removeItem('inventory-review-4');
    } catch { /* Storage is optional. */ }
    setBusy(false); $('delete-dialog').close(); renderHistory();
    const next = $('history').querySelector('.record-open') || document.querySelector('.upload-trigger');
    next.focus();
  } catch (error) {
    $('delete-error').textContent = error.message; $('delete-error').hidden = false;
  } finally { setBusy(false); $('delete-confirm').textContent = 'Delete review'; }
});
function clearUploadErrors() {
  $('upload-error').hidden = true; $('header-errors').hidden = true; $('header-errors').replaceChildren();
}
function openUpload() {
  if (state.busy) return;
  $('upload-form').reset();
  clearUploadErrors(); $('upload-progress').hidden = true; $('upload-dialog').showModal();
}
function showHeaderErrors(columns) {
  $('header-errors').hidden = false;
  for (const [key,title,instruction] of [
    ['missing','Missing columns','Add these headers exactly as shown in the template.'],
    ['unexpected','Unexpected columns','Rename these headers to the correct inventory names, or remove columns that are not part of the template.'],
    ['duplicates','Repeated column names','Keep each inventory column exactly once.'],
    ['blank_columns','Unnamed columns','Give these column positions their correct inventory headers, or remove unused columns.']]) {
    if (!columns[key].length) continue;
    const section = node('section',undefined,'header-problem'), list = node('ul');
    section.append(node('h3',title),node('p',instruction));
    for (const value of columns[key]) list.append(node('li',String(value)));
    section.append(list); $('header-errors').append(section);
  }
}
$('upload-form').addEventListener('submit', async event => {
  event.preventDefault(); if (state.busy) return;
  const file = $('file').files[0]; if (!file) return;
  clearUploadErrors();
  if (!/\.csv$/i.test(file.name)) {
    $('upload-error').textContent = 'Only CSV files are accepted. Export your inventory as a .csv file and upload it again.';
    $('upload-error').hidden = false;
    return;
  }
  $('upload-progress').hidden = false; setBusy(true);
  try {
    const form = new FormData(); form.append('file',file);
    const result = await api('/api/runs',{method:'POST',body:form,headers:{'X-Requested-With':'AIInventory'}});
    $('upload-dialog').close(); setBusy(false);
    state.id = result.id; state.filters = defaults(); state.autoStatus = true;
    state.data = null; state.fields = []; state.returnKey = null; rememberFilters();
    navigate('#run/'+result.id); await loadHistory();
  } catch (error) {
    $('upload-error').textContent = error.message; $('upload-error').hidden = false;
    if (error.data && error.data.columns) showHeaderErrors(error.data.columns);
  } finally { setBusy(false); $('upload-progress').hidden = true; }
});
$('file').addEventListener('change', clearUploadErrors);
function query() { return new URLSearchParams(state.filters); }
function syncFilters() {
  if (document.activeElement !== $('search')) $('search').value = state.filters.q;
  $('status').value = state.filters.status; $('field').value = state.filters.field;
}
async function loadResults(focus = false) {
  const {sequence,signal} = beginRequest(); const id = state.id;
  if (!state.data || state.data.run.id !== id) resetCharts();
  $('review-content').hidden = !state.data || state.data.run.id !== id;
  notice(); state.data = null; $('review-rules').disabled = true; $('archived-review').hidden = true; $('run-meta').textContent = '';
  state.loading = true; $('results-loading').hidden = false; $('download-open').disabled = true;
  $('records').replaceChildren(); $('no-results').hidden = true; $('record-count').textContent = '';
  $('filename').textContent = (state.runs.find(r => r.id === id) || {}).filename || 'Inventory review';
  $('previous').disabled = true; $('next').disabled = true;
  try {
    let data = await api('/api/runs/'+id+'?'+query(),{signal});
    if (!isCurrent(sequence,'review')) return;
    if (state.autoStatus && data.run.errors === 0) {
      state.filters.status = 'all'; data = await api('/api/runs/'+id+'?'+query(),{signal});
      if (!isCurrent(sequence,'review')) return;
    }
    state.autoStatus = false; state.data = data; state.fields = data.fields; state.filters.page = data.page; rememberFilters();
    renderResults(); $('review-rules').disabled = false;
    if (focus) {
      const last = $('records').querySelector('[data-key="'+state.returnKey+'"] .record-open');
      if (last) last.focus(); else $('filename').focus();
    }
  } catch (error) {
    if (isCurrent(sequence,'review') && error.name !== 'AbortError') {
      if (error.data && error.data.archived) {
        $('filename').textContent = error.data.run.filename;
        $('run-meta').textContent = 'Reviewed '+dateLabel(error.data.run.created_at);
        $('archived-message').textContent = error.message; $('archived-review').hidden = false;
      } else notice(error.message);
    }
  }
  finally { if (isCurrent(sequence,'review')) { state.loading = false; $('results-loading').hidden = true; $('download-open').disabled = !state.data; } }
}
function renderResults() {
  const data = state.data, run = data.run;
  $('review-content').hidden = false;
  $('filename').textContent = run.filename;
  $('run-meta').textContent = (run.sheet ? run.sheet+' · ' : '')+'Reviewed '+dateLabel(run.created_at);
  $('summary').replaceChildren();
  $('inventory-error-count').textContent = 'Result: '+data.inventory_error_records.toLocaleString()+' of '+run.total.toLocaleString()+' records have an entry error in at least one of the 21 inventory fields. Each record is counted once. Overall totals also include Submitter Name and Date Submitted checks.';
  for (const [label,count,status,cls] of [['Total records',run.total,'all',''],['Records with errors',run.errors,'Errors','errors'],['Passed',run.passed,'Passed','passed']]) {
    const el = button(label,() => changeFilter('status',status),cls+(state.filters.status === status ? ' selected' : ''));
    el.setAttribute('aria-pressed',String(state.filters.status === status)); el.append(node('strong',count.toLocaleString())); $('summary').append(el);
  }
  const byId = Object.fromEntries(data.fields.map(f => [f.id,f]));
  $('field').replaceChildren(option('','All fields'),...data.fields.map(f => option(f.id,f.label)));
  syncFilters(); $('records').replaceChildren();
  for (const record of data.records) {
    const row = node('tr'); row.dataset.key = record.key;
    const label = node('td'); label.append(clickableRow(row,record.name || '(Missing system name)',() => openRecord(record.key)),
      node('div',(record.application_id ? 'ID '+record.application_id+' · ' : '')+'Source row '+record.source_row,'record-id'));
    const status = node('td'); status.append(badge(record.status));
    const issues = node('td',undefined,'issue-counts');
    if (record.errors) issues.append(node('div',record.errors+' error'+(record.errors === 1 ? '' : 's'),'error-text'));
    if (!record.errors) issues.append(node('span','0','muted'));
    row.append(label,status,issues,node('td',record.affected_fields.map(f => byId[f] ? byId[f].label : f).join(' · ') || '—','affected-fields'));
    $('records').append(row);
  }
  $('no-results').hidden = !!data.records.length;
  const start = data.records.length ? (data.page-1)*data.size+1 : 0;
  $('record-count').textContent = data.matched ? start+'–'+Math.min(data.page*data.size,data.matched)+' of '+data.matched.toLocaleString()+' records' : '0 records';
  $('page-info').textContent = 'Page '+data.page+' of '+data.pages;
  $('previous').disabled = data.page <= 1; $('next').disabled = data.page >= data.pages;
  loadCharts();
}
function changeFilter(key,value) { state.autoStatus = false; clearTimeout(searchTimer); state.filters[key] = value; state.filters.page = 1; rememberFilters(); loadResults(); }
function resetFilters() { state.autoStatus = false; clearTimeout(searchTimer); state.filters = {...defaults(),status:'all'}; rememberFilters(); loadResults(); }
$('search').addEventListener('input', () => { clearTimeout(searchTimer); searchTimer = setTimeout(() => changeFilter('q',$('search').value),250); });
$('status').addEventListener('change', () => changeFilter('status',$('status').value));
$('field').addEventListener('change', () => changeFilter('field',$('field').value));
$('clear-filters').addEventListener('click',resetFilters); $('show-all').addEventListener('click',resetFilters);
$('previous').addEventListener('click',() => { state.filters.page--; loadResults(); });
$('next').addEventListener('click',() => { state.filters.page++; loadResults(); });
function openRecord(key) { state.returnKey = key; rememberFilters(); navigate('#run/'+state.id+'/record/'+key); }
$('back-to-results').addEventListener('click', () => navigate('#run/'+state.id));
async function loadRecord() {
  showView('record'); const {sequence,signal} = beginRequest();
  state.record = null; $('record-content').hidden = true; $('record-error').hidden = true; $('record-retry').hidden = false; $('record-loading').hidden = false;
  $('record-rules').disabled = true; $('record-title').textContent = 'Record details'; $('record-title').focus();
  $('record-status').replaceChildren(); $('record-meta').textContent = '';
  const run = (state.data && state.data.run.id === state.id ? state.data.run : state.runs.find(r => r.id === state.id));
  $('record-file').textContent = run ? run.filename : 'Inventory review';
  try {
    const data = await api('/api/runs/'+state.id+'/records/'+state.recordKey,{signal});
    if (!isCurrent(sequence,'record')) return;
    state.record = data.record; state.recordRun = data.run; state.fields = data.fields;
    $('record-file').textContent = data.run.filename;
    renderRecord(); $('record-rules').disabled = false;
  } catch (error) {
    if (isCurrent(sequence,'record') && error.name !== 'AbortError') {
      $('record-error-message').textContent = error.message; $('record-error').hidden = false;
      $('record-retry').hidden = !!(error.data && error.data.archived);
    }
  } finally { if (isCurrent(sequence,'record')) $('record-loading').hidden = true; }
}
$('record-retry').addEventListener('click',loadRecord);
function renderRecord() {
  const record = state.record;
  $('record-title').textContent = record.name || '(Missing system name)';
  $('record-meta').textContent = (record.application_id ? 'ID '+record.application_id+' · ' : '')+'Source row '+record.source_row;
  $('record-status').append(badge(record.status),node('span',record.errors+' error'+(record.errors === 1 ? '' : 's')));
  if (record.status === 'Passed') $('record-status').append(node('span','All applicable checks passed.'));
  $('source-values').replaceChildren();
  const hasError = field => record.findings.some(f => f.fields.includes(field.id)) ? 1 : 0;
  for (const field of [...state.fields].sort((a,b) => hasError(b)-hasError(a))) {
    const row = node('tr'); row.dataset.field = field.id;
    if (hasError(field)) row.className = 'field-error';
    const label = node('td',undefined,'source-label');
    label.append(node('strong',field.label),button('View field rules',() => openRules(field.id)));
    const value = node('td'); value.append(node('span','Submitted value','value-caption'),node('div',display(record.cells[field.id]) || '(blank)','field-value'));
    const validation = node('td');
    const findings = record.findings.filter(f => f.fields.includes(field.id));
    if (!findings.length) validation.append(node('span',(record.field_results || {})[field.id] || 'No errors','muted'));
    for (const finding of findings) {
      const article = node('article',undefined,'field-issue');
      article.append(node('h3',finding.title),node('p',finding.message));
      const action = node('p',undefined,'expected'); action.append(node('strong','How to fix: '),document.createTextNode(finding.fix)); article.append(action);
      const detail = node('details'); detail.append(node('summary','Requirement · '+finding.rule_id),node('p',finding.requirement)); article.append(detail);
      validation.append(article);
    }
    row.append(label,value,validation); $('source-values').append(row);
  }
  for (const [column, submitted] of Object.entries(record.extra_values || {})) {
    const row = node('tr'); row.dataset.sourceColumn = column;
    const label = node('td',undefined,'source-label'); label.append(node('strong',column));
    const value = node('td');
    value.append(node('span','Submitted value','value-caption'),node('div',display(submitted) || '(blank)','field-value'));
    row.append(label,value,node('td','Source data · Not validated','muted'));
    $('source-values').append(row);
  }
  const unchecked = record.not_checked || [];
  $('not-checked').hidden = !unchecked.length; $('not-checked').open = false;
  $('not-checked-title').textContent = unchecked.length+' checks depend on errors above'; $('not-checked-list').replaceChildren();
  for (const check of unchecked) { const article = node('article'); article.append(node('h3',check.title+' · '+check.rule_id),node('p',check.reason)); $('not-checked-list').append(article); }
  $('record-content').hidden = false;
}
function openRules(selected = '') {
  state.rulesFields = state.fields;
  $('rules-meta').textContent = 'Correct errors in the source file and upload again.';
  $('rules-field').replaceChildren(option('','All inventory fields'),...state.rulesFields.map(f => option(f.id,f.label)));
  $('rules-field').value = selected; renderRules(); $('rules-dialog').showModal();
}
function renderRules() {
  $('rules-list').replaceChildren();
  for (const field of state.rulesFields.filter(f => !$('rules-field').value || f.id === $('rules-field').value)) {
    const section = node('section',undefined,'rule-field');
    section.append(node('h3',field.label),node('p',field.required ? 'Value required' : 'Value optional / conditional','small muted'),node('p',field.description || '','field-description'));
    if (field.format) section.append(node('p',field.format,'format'));
    if (field.example) section.append(node('p','Example: '+field.example,'small muted'));
    if (field.options && field.options.length) {
      const choices = node('details',undefined,'rule-choices'); choices.append(node('summary','Common choices and examples'),node('p',field.options.join(' · ')));
      if (field.aliases && Object.keys(field.aliases).length) choices.append(node('p','Also accepted: '+Object.entries(field.aliases).map(([a,b]) => a+' → '+b).join('; ')));
      section.append(choices);
    }
    for (const check of field.checks || []) {
      const article = node('article',undefined,'rule-check'), title = node('div',undefined,'check-title');
      title.append(node('h4',check.title),node('span',check.id,'small muted'));
      article.append(title,node('p',check.requirement),node('p','How to fix: '+check.fix,'muted')); section.append(article);
    }
    $('rules-list').append(section);
  }
  $('rules-dialog').scrollTop = 0;
}
$('rules-field').addEventListener('change',renderRules);
for (const id of ['review-rules','record-rules']) $(id).addEventListener('click',() => openRules());
function reportLinks() {
  const scope = $('report-scope').value;
  for (const kind of ['errors','records']) {
    const params = query(); params.delete('page'); params.delete('size'); params.set('kind',kind); params.set('scope',scope);
    $(kind+'-download').href = '/api/runs/'+state.id+'/export?'+params;
  }
}
$('download-open').addEventListener('click',() => {
  if (state.loading || !state.data) return;
  $('report-scope').replaceChildren(option('filtered','Current view · '+state.data.matched+' records'),option('all','Entire file · '+state.data.run.total+' records'));
  reportLinks(); $('report-dialog').showModal();
});
$('report-scope').addEventListener('change',reportLinks);
$('home-button').addEventListener('click',() => navigate('#reviews'));
for (const el of document.querySelectorAll('.upload-trigger')) el.addEventListener('click',openUpload);
for (const el of document.querySelectorAll('[data-close]')) el.addEventListener('click',() => { if (!state.busy) $(el.dataset.close).close(); });
$('upload-dialog').addEventListener('cancel',event => { if (state.busy) event.preventDefault(); });
window.addEventListener('hashchange',route);
initializeCharts();
(async () => { await loadHistory(); await route(); })();
