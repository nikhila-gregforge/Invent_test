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
const defaults = () => ({status: 'attention', field: '', q: '', page: 1, size: 25});
const state = {runs: [], id: null, filters: defaults(), data: null, preview: null, file: null,
  mapping: {}, view: '', record: null, recordRun: null, recordKey: null, fields: [], rulesFields: [], rulesVersion: '',
  sequence: 0, busy: false, loading: false, controller: null, returnKey: null};
let searchTimer;
function notice(message = '') { $('notice').textContent = message; $('notice').hidden = !message; }
function statusLabel(value) { return ({Failed: 'Errors', 'Needs review': 'Warnings', Passed: 'Passed'})[value] || value; }
function badge(status, label) {
  return node('span', label || statusLabel(status), 'badge '+({Failed:'failed','Needs review':'review',Passed:'passed'}[status] || ''));
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
  try { sessionStorage.setItem('inventory-review', JSON.stringify({id: state.id, filters:state.filters, returnKey:state.returnKey})); } catch { /* Storage is optional. */ }
}
function selectRun(id) {
  if (state.id === id) return;
  state.id = id; state.filters = defaults(); state.data = null; state.fields = []; state.returnKey = null;
  try {
    const saved = JSON.parse(sessionStorage.getItem('inventory-review'));
    if (saved && saved.id === id) { state.filters = {...defaults(), ...saved.filters}; state.returnKey = saved.returnKey; }
  } catch { /* A new review still works without saved navigation. */ }
}
function showView(view) {
  state.view = view;
  for (const name of ['home','mapping','review','record']) $(name+'-view').hidden = name !== view;
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
  } else if (hash === '#mapping' && state.preview) {
    beginRequest(); showView('mapping'); renderMapping(); $('mapping-title').focus();
  } else {
    beginRequest(); showView('home'); renderHistory();
    if (hash === '#mapping') notice('Choose the file again to continue mapping. Unconfirmed uploads are not saved.');
  }
}
async function loadHistory() {
  $('home-loading').hidden = false;
  try { state.runs = (await api('/api/runs')).runs; renderHistory(); }
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
    name.append(clickableRow(row, run.filename, () => navigate('#run/'+run.id)),
      node('div', (run.sheet ? run.sheet+' · ' : '')+'Rules '+run.rules_version, 'record-id'));
    const results = node('td'), chips = node('div',undefined,'history-results');
    for (const [status, count] of [['Failed',run.failed],['Needs review',run.review],['Passed',run.passed]]) {
      if (count) chips.append(badge(status, count.toLocaleString()+' '+statusLabel(status).toLowerCase()));
    }
    results.append(chips);
    row.append(name, node('td',run.total.toLocaleString(),'numeric'), results, node('td',dateLabel(run.created_at),'small muted'));
    $('history').append(row);
  }
}
function setBusy(busy) {
  state.busy = busy;
  for (const el of document.querySelectorAll('.upload-trigger, #home-button, #mapping-view button, #mapping-view select, #upload-dialog button, #upload-dialog input, #upload-dialog select')) el.disabled = busy;
  if (!busy && state.preview) updateMapping();
}
function openUpload() {
  if (state.busy) return;
  $('upload-form').reset(); $('sheet-label').hidden = true; $('sheet').replaceChildren();
  $('upload-error').hidden = true; $('upload-progress').hidden = true;
  $('upload-dialog').showModal();
}
function uploadForm() {
  const form = new FormData(); form.append('file', state.file);
  if (state.preview && state.preview.sheet) form.append('sheet', state.preview.sheet);
  return form;
}
$('upload-form').addEventListener('submit', async event => {
  event.preventDefault(); if (state.busy) return;
  const file = $('file').files[0]; if (!file) return;
  $('upload-error').hidden = true; $('upload-progress').hidden = false; setBusy(true);
  try {
    const form = new FormData(); form.append('file',file);
    if (!$('sheet-label').hidden) form.append('sheet',$('sheet').value);
    const preview = await api('/api/preview',{method:'POST',body:form,headers:{'X-Requested-With':'AIInventory'}});
    state.file = file; state.preview = preview; state.mapping = {...preview.mapping};
    $('upload-dialog').close(); setBusy(false); navigate('#mapping');
  } catch (error) {
    $('upload-error').textContent = error.message; $('upload-error').hidden = false;
    if (error.data && error.data.sheets) {
      $('sheet-label').hidden = false;
      $('sheet').replaceChildren(...error.data.sheets.map(sheet => option(sheet,sheet)));
    }
  } finally { setBusy(false); $('upload-progress').hidden = true; }
});
$('file').addEventListener('change', () => { $('sheet-label').hidden = true; $('sheet').replaceChildren(); $('upload-error').hidden = true; });
function renderMapping() {
  const preview = state.preview;
  $('mapping-file').textContent = preview.filename+' · '+preview.total.toLocaleString()+' records'+(preview.sheet ? ' · '+preview.sheet : '');
  $('mapping-origin').textContent = preview.restored
    ? 'Your last confirmed mapping for these columns is shown. Review it before validating this file.'
    : 'Suggested matches are shown where column names are clear. Choose a column or Not provided for every field.';
  $('mapping-rows').replaceChildren();
  for (const field of preview.fields) {
    const row = node('tr'); row.dataset.mappingField = field.id;
    const label = node('td'); label.append(node('strong',field.label,'mapping-field-title'));
    const meta = node('div',undefined,'mapping-field-meta');
    meta.append(node('span',field.required ? 'Required' : 'Optional / conditional'), button('Rules',() => openRules(field.id)));
    label.append(meta);
    const selection = node('td'), select = node('select',undefined,'mapping-select');
    select.setAttribute('aria-label','Source column for '+field.label);
    select.append(option('','Choose a source column…'),option('none','Not provided'));
    preview.columns.forEach((column,index) => select.append(option('column:'+index,column)));
    select.value = state.mapping[field.id] === null ? 'none' : state.mapping[field.id] ? 'column:'+preview.columns.indexOf(state.mapping[field.id]) : '';
    select.addEventListener('change',() => {
      state.mapping[field.id] = select.value === 'none' ? null : select.value ? preview.columns[Number(select.value.slice(7))] : '';
      updateMapping();
    });
    selection.append(select, node('p',field.description,'mapping-note'));
    const samples = node('td',undefined,'mapping-preview'); row.append(label,selection,samples); $('mapping-rows').append(row);
  }
  updateMapping();
}
function updateMapping() {
  const preview = state.preview; if (!preview) return;
  const used = Object.values(state.mapping).filter(Boolean);
  for (const row of $('mapping-rows').children) {
    const fid = row.dataset.mappingField, value = state.mapping[fid], select = row.querySelector('select');
    select.value = value === null ? 'none' : value ? 'column:'+preview.columns.indexOf(value) : '';
    select.classList.toggle('unresolved',value === '');
    for (const choice of select.options) {
      if (choice.value.startsWith('column:')) {
        const column = preview.columns[Number(choice.value.slice(7))]; choice.disabled = column !== value && used.includes(column);
      }
    }
    const samples = row.querySelector('.mapping-preview'); samples.replaceChildren();
    for (const sample of (value && preview.samples[value] && preview.samples[value].length ? preview.samples[value] : [value === null ? 'Not provided in this file' : value ? 'No values in the sampled rows' : 'Choose a column to preview its values'])) samples.append(node('p',sample));
  }
  const unresolved = preview.fields.filter(f => state.mapping[f.id] === '').length;
  const missing = preview.fields.filter(f => f.required && state.mapping[f.id] === null);
  const extra = preview.columns.filter(c => !used.includes(c));
  $('mapping-progress').textContent = unresolved ? unresolved+' fields need a mapping decision' : preview.fields.length+' fields ready to validate';
  $('mapping-missing').hidden = !missing.length;
  $('mapping-missing').textContent = missing.length+' required fields not provided. Each record will have an error for these fields.';
  $('mapping-fill').disabled = state.busy || !unresolved;
  $('mapping-submit').disabled = state.busy || !!unresolved || new Set(used).size !== used.length || !preview.fields.some(f => f.id !== 'response_id' && state.mapping[f.id]);
  $('unmapped-summary').textContent = extra.length+' source columns kept for reference only';
  $('unmapped-columns').textContent = extra.length ? extra.join(' · ') : 'Every source column is mapped to an inventory field.';
}
$('mapping-fill').addEventListener('click', () => {
  for (const field of state.preview.fields) if (state.mapping[field.id] === '') state.mapping[field.id] = null;
  updateMapping();
});
$('mapping-cancel').addEventListener('click', () => { state.preview = null; state.file = null; state.mapping = {}; navigate('#reviews'); });
$('mapping-submit').addEventListener('click', async () => {
  if (state.busy || $('mapping-submit').disabled) return;
  notice(); setBusy(true); $('mapping-submit').textContent = 'Validating records…';
  try {
    const form = uploadForm();
    form.append('mapping',JSON.stringify(state.mapping)); form.append('file_hash',state.preview.file_hash); form.append('rules_version',state.preview.rules_version);
    const result = await api('/api/runs',{method:'POST',body:form,headers:{'X-Requested-With':'AIInventory'}});
    state.preview = null; state.file = null; state.mapping = {}; setBusy(false);
    // A new validation starts with a fresh review, even if it reused a saved run.
    state.id = result.id; state.filters = defaults(); state.data = null; state.returnKey = null; rememberFilters();
    navigate('#run/'+result.id); await loadHistory();
  } catch (error) { notice(error.message); }
  finally { setBusy(false); $('mapping-submit').textContent = 'Confirm mapping & validate'; }
});
function query() { return new URLSearchParams(state.filters); }
function syncFilters() {
  $('search').value = state.filters.q; $('status').value = state.filters.status; $('field').value = state.filters.field;
}
async function loadResults(focus = false) {
  const {sequence,signal} = beginRequest(); const id = state.id;
  notice(); state.data = null; $('review-rules').disabled = true;
  state.loading = true; $('results-loading').hidden = false; $('download-open').disabled = true;
  $('records').replaceChildren(); $('no-results').hidden = true; $('record-count').textContent = '';
  $('filename').textContent = (state.runs.find(r => r.id === id) || {}).filename || 'Inventory review';
  $('previous').disabled = true; $('next').disabled = true;
  try {
    let data = await api('/api/runs/'+id+'?'+query(),{signal});
    if (!isCurrent(sequence,'review')) return;
    if (state.filters.status === 'attention' && data.run.passed === data.run.total) {
      state.filters.status = 'all'; data = await api('/api/runs/'+id+'?'+query(),{signal});
      if (!isCurrent(sequence,'review')) return;
    }
    state.data = data; state.fields = data.fields; state.filters.page = data.page; rememberFilters();
    renderResults(); $('review-rules').disabled = false;
    if (focus) {
      const last = $('records').querySelector('[data-key="'+state.returnKey+'"] .record-open');
      if (last) last.focus(); else $('filename').focus();
    }
  } catch (error) { if (isCurrent(sequence,'review') && error.name !== 'AbortError') notice(error.message); }
  finally { if (isCurrent(sequence,'review')) { state.loading = false; $('results-loading').hidden = true; $('download-open').disabled = !state.data; } }
}
function renderResults() {
  const data = state.data, run = data.run;
  $('filename').textContent = run.filename;
  $('run-meta').textContent = (run.sheet ? run.sheet+' · ' : '')+'Reviewed '+dateLabel(run.created_at)+' · Rules '+run.rules_version;
  $('summary').replaceChildren();
  for (const [label,count,status,cls] of [['Records',run.total,'all',''],['Errors',run.failed,'Failed','errors'],['Warnings',run.review,'Needs review','warnings'],['Passed',run.passed,'Passed','passed']]) {
    const el = button(label,() => changeFilter('status',status),cls+(state.filters.status === status ? ' selected' : ''));
    el.setAttribute('aria-pressed',String(state.filters.status === status)); el.append(node('strong',count.toLocaleString())); $('summary').append(el);
  }
  const byId = Object.fromEntries(data.fields.map(f => [f.id,f]));
  $('missing-columns').hidden = !data.missing_required.length;
  $('missing-columns').textContent = 'Required fields not provided in this file: '+data.missing_required.map(id => byId[id].label).join('; ')+'. Each record includes these errors.';
  $('field').replaceChildren(option('','All fields'),...data.fields.map(f => option(f.id,f.label)));
  syncFilters(); $('records').replaceChildren();
  for (const record of data.records) {
    const row = node('tr'); row.dataset.key = record.key;
    const label = node('td'); label.append(clickableRow(row,record.name || '(Missing system name)',() => openRecord(record.key)),
      node('div',(record.response_id ? 'ID '+record.response_id+' · ' : '')+'Source row '+record.source_row,'record-id'));
    const status = node('td'); status.append(badge(record.status));
    const issues = node('td',undefined,'issue-counts');
    if (record.errors) issues.append(node('div',record.errors+' error'+(record.errors === 1 ? '' : 's'),'error-text'));
    if (record.warnings) issues.append(node('div',record.warnings+' warning'+(record.warnings === 1 ? '' : 's'),'warning-text'));
    if (!record.errors && !record.warnings) issues.append(node('span',record.status === 'Passed' ? '—' : 'Checks not completed','muted'));
    row.append(label,status,issues,node('td',record.affected_fields.map(f => byId[f] ? byId[f].label : f).join(' · ') || '—','affected-fields'));
    $('records').append(row);
  }
  $('no-results').hidden = !!data.records.length;
  const start = data.records.length ? (data.page-1)*data.size+1 : 0;
  $('record-count').textContent = data.matched ? start+'–'+Math.min(data.page*data.size,data.matched)+' of '+data.matched.toLocaleString()+' records' : '0 records';
  $('page-info').textContent = 'Page '+data.page+' of '+data.pages;
  $('previous').disabled = data.page <= 1; $('next').disabled = data.page >= data.pages;
}
function changeFilter(key,value) { clearTimeout(searchTimer); state.filters[key] = value; state.filters.page = 1; rememberFilters(); loadResults(); }
function resetFilters() { clearTimeout(searchTimer); state.filters = {...defaults(),status:'all'}; rememberFilters(); loadResults(); }
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
  state.record = null; $('record-content').hidden = true; $('record-error').hidden = true; $('record-loading').hidden = false;
  $('record-rules').disabled = true; $('record-title').textContent = 'Record details'; $('record-title').focus();
  $('record-status').replaceChildren(); $('record-meta').textContent = '';
  const run = (state.data && state.data.run.id === state.id ? state.data.run : state.runs.find(r => r.id === state.id));
  $('record-file').textContent = run ? run.filename : 'Inventory review';
  try {
    const data = await api('/api/runs/'+state.id+'/records/'+state.recordKey,{signal});
    if (!isCurrent(sequence,'record')) return;
    state.record = data.record; state.recordRun = data.run; state.fields = data.fields;
    $('record-file').textContent = data.run.filename+' · Rules '+data.run.rules_version;
    renderRecord(); $('record-rules').disabled = false;
  } catch (error) {
    if (isCurrent(sequence,'record') && error.name !== 'AbortError') {
      $('record-error-message').textContent = error.message; $('record-error').hidden = false;
    }
  } finally { if (isCurrent(sequence,'record')) $('record-loading').hidden = true; }
}
$('record-retry').addEventListener('click',loadRecord);
function renderRecord() {
  const record = state.record;
  $('record-title').textContent = record.name || '(Missing system name)';
  $('record-meta').textContent = (record.response_id ? 'ID '+record.response_id+' · ' : '')+'Source row '+record.source_row;
  $('record-status').append(badge(record.status),node('span',record.errors+' error'+(record.errors === 1 ? '' : 's')+' · '+record.warnings+' warning'+(record.warnings === 1 ? '' : 's')));
  if (record.status === 'Passed') $('record-status').append(node('span','All applicable checks passed.'));
  $('source-values').replaceChildren();
  const severity = field => record.findings.some(f => f.fields.includes(field.id) && f.severity === 'ERROR') ? 2 : record.findings.some(f => f.fields.includes(field.id)) ? 1 : 0;
  for (const field of [...state.fields].sort((a,b) => severity(b)-severity(a))) {
    const row = node('tr'); row.dataset.field = field.id;
    if (severity(field)) row.className = severity(field) === 2 ? 'field-error' : 'field-warning';
    const label = node('td',undefined,'source-label');
    label.append(node('strong',field.label),node('small',field.source ? 'Source: '+field.source : 'Source column not provided'),button('View field rules',() => openRules(field.id)));
    const value = node('td'); value.append(node('span','Submitted value','value-caption'),node('div',display(record.cells[field.id]) || '(blank)','field-value'));
    const validation = node('td');
    const findings = record.findings.filter(f => f.fields.includes(field.id));
    if (!findings.length) validation.append(node('span',(record.field_results || {})[field.id] || 'No issues','muted'));
    for (const finding of findings) {
      const article = node('article',undefined,'field-issue');
      article.append(badge(finding.severity === 'ERROR' ? 'Failed' : 'Needs review',finding.severity === 'ERROR' ? 'Error' : 'Warning'),node('h3',finding.title),node('p',finding.message));
      if (finding.why) { const reason = node('p',undefined,'expected'); reason.append(node('strong','Why this is '+(finding.severity === 'ERROR' ? 'an error: ' : 'a warning: ')),document.createTextNode(finding.why)); article.append(reason); }
      const action = node('p',undefined,'expected'); action.append(node('strong','In the source file: '),document.createTextNode(finding.expected_condition)); article.append(action);
      const detail = node('details'); detail.append(node('summary','Requirement · '+finding.rule_id),node('p',finding.requirement || finding.expected_condition)); article.append(detail);
      validation.append(article);
    }
    row.append(label,value,validation); $('source-values').append(row);
  }
  const unchecked = record.not_checked || [];
  $('not-checked').hidden = !unchecked.length; $('not-checked').open = false;
  $('not-checked-title').textContent = unchecked.length+' checks could not run'; $('not-checked-list').replaceChildren();
  for (const check of unchecked) { const article = node('article'); article.append(node('h3',check.title+' · '+check.rule_id),node('p',check.reason)); $('not-checked-list').append(article); }
  const mapped = new Set(state.fields.map(f => f.source).filter(Boolean));
  const extras = Object.entries(record.source_values || {}).filter(([column]) => !mapped.has(column));
  $('extra-values').hidden = !extras.length; $('extra-values').open = false; $('extra-values-body').replaceChildren();
  for (const [column,value] of extras) { const row = node('tr'); row.append(node('td',column),node('td',display(value) || '(blank)')); $('extra-values-body').append(row); }
  $('record-content').hidden = false;
}
function openRules(selected = '') {
  state.rulesFields = state.view === 'mapping' ? state.preview.fields : state.fields;
  const run = state.view === 'record' ? state.recordRun : state.data && state.data.run.id === state.id ? state.data.run : state.runs.find(r => r.id === state.id);
  state.rulesVersion = state.view === 'mapping' ? state.preview.rules_version : run ? run.rules_version : '';
  $('rules-meta').textContent = (state.rulesVersion ? 'Rules '+state.rulesVersion+' · ' : '')+'Errors require correction. Warnings require confirmation.';
  $('rules-field').replaceChildren(option('','All inventory fields'),...state.rulesFields.map(f => option(f.id,f.label)));
  $('rules-field').value = selected; renderRules(); $('rules-dialog').showModal();
}
function renderRules() {
  $('rules-list').replaceChildren();
  for (const field of state.rulesFields.filter(f => !$('rules-field').value || f.id === $('rules-field').value)) {
    const section = node('section',undefined,'rule-field');
    section.append(node('h3',field.label),node('p',field.required ? 'Required inventory field' : 'Optional / conditional inventory field','small muted'),node('p',field.description || '','field-description'));
    if (field.format) section.append(node('p',field.format,'format'));
    if (field.example) section.append(node('p','Example: '+field.example,'small muted'));
    if (field.options && field.options.length) {
      const choices = node('details',undefined,'rule-choices'); choices.append(node('summary','Accepted choices'),node('p',field.options.join(' · ')));
      if (field.aliases && Object.keys(field.aliases).length) choices.append(node('p','Also accepted: '+Object.entries(field.aliases).map(([a,b]) => a+' → '+b).join('; ')));
      section.append(choices);
    }
    for (const check of field.checks || []) {
      const article = node('article',undefined,'rule-check'), title = node('div',undefined,'check-title');
      title.append(badge(check.severity === 'ERROR' ? 'Failed' : 'Needs review',check.severity === 'ERROR' ? 'Error' : 'Warning'),node('h4',check.title),node('span',check.id,'small muted'));
      article.append(title,node('p',check.requirement),node('p','Why: '+check.why,'why'),node('p','Source correction: '+check.action,'why')); section.append(article);
    }
    if (!field.checks) section.append(node('p',field.rules || 'See the recorded issue for the rule applied to this review.','format'));
    $('rules-list').append(section);
  }
  $('rules-dialog').scrollTop = 0;
}
$('rules-field').addEventListener('change',renderRules);
for (const id of ['mapping-rules','review-rules','record-rules']) $(id).addEventListener('click',() => openRules());
function reportLinks() {
  const scope = $('report-scope').value;
  for (const kind of ['issues','records']) {
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
(async () => { await loadHistory(); await route(); })();
