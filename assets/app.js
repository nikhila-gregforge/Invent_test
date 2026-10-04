'use strict';
const $ = id => document.getElementById(id);
const defaults = () => ( {
  status:'attention',field:'',rule:'',severity:'',q:'',column:'',value:'',blank:'',exact:'',sort:'issues',page:1,size:25
}
);
const state = {
  id:null,filters:defaults(),data:null,tab:'records',runs:[],controller:null,sequence:0,recordSequence:0,recordKey:null,returnFocus:null,returnScroll:0,uploading:false
}
;
const fmt = n => Number(n).toLocaleString();
function node(tag, cls='', content='') {
  const n=document.createElement(tag);
  if(cls)n.className=cls;
  if(content!==null)n.textContent=content;
  return n;
}
function valueText(value) {
  if(value===null||value===undefined)return '';
  if(typeof value==='object')return value.__excel_date__||JSON.stringify(value);
  return String(value);
}
function setNotice(message) {
  $('notice').textContent=message||'';
  $('notice').hidden=!message;
}
function badge(status) {
  const kind=status==='Failed'?'failed':status==='Needs review'?'review':'passed';
  return node('span','badge '+kind,(kind==='failed'?'× ':kind==='review'?'! ':'✓ ')+status);
}
function query() {
  const params=new URLSearchParams();
  Object.entries(state.filters).forEach(([k,v])=> {
    if(v!==''&&v!==null)params.set(k,String(v));
  }
  );
  return params;
}
function persist() {
  try {
    sessionStorage.setItem('ai-inventory-review',JSON.stringify( {
      id:state.id,filters:state.filters,tab:state.tab
    }
    ));
  }
  catch {
  }
}
async function api(url,options= {
}
) {
  const response=await fetch(url,options);
  let data;
  try {
    data=await response.json();
  }
  catch {
    throw new Error('The server could not complete this request. Please retry.');
  }
  if(!response.ok) {
    const error=new Error(data.error||'Request failed.');
    error.data=data;
    throw error;
  }
  return data;
}
function shortDate(value) {
  return new Date(value).toLocaleString(undefined, {
    month:'short',day:'numeric',hour:'2-digit',minute:'2-digit'
  }
  );
}
function options(id,items,placeholder) {
  const element=$(id);
  element.replaceChildren();
  if(placeholder!==null) {
    const opt=node('option','',placeholder);
    opt.value='';
    element.append(opt);
  }
  for(const [value,label] of items) {
    const opt=node('option','',label);
    opt.value=value;
    element.append(opt);
  }
}
function showTab(tab) {
  state.tab=tab;
  for(const name of ['records','fields','rules']) {
    $('panel-'+name).hidden=name!==tab;
    const button=$('tab-'+name);
    button.setAttribute('aria-selected',String(name===tab));
    button.tabIndex=name===tab?0:-1;
  }
  persist();
}
function renderHistory() {
  $('history').replaceChildren();
  $('run-count').textContent=fmt(state.runs.length);
  $('history-empty').hidden=state.runs.length>0;
  for(const run of state.runs) {
    const button=node('button','history-item'+(run.id===state.id?' active':''));
    button.type='button';
    button.setAttribute('aria-current',run.id===state.id?'page':'false');
    button.title=run.filename+(run.sheet?' · '+run.sheet:'');
    button.append(node('strong','',run.filename),node('span','',shortDate(run.created_at)+' · '+fmt(run.total)+' records'));
    button.addEventListener('click',()=>navigate(run.id));
    $('history').append(button);
  }
}
async function getRuns() {
  const data=await api('/api/runs');
  state.runs=data.runs;
  $('file-limits').textContent=`CSV or XLSX · ${data.max_bytes/1024/1024} MiB · ${fmt(data.max_rows)} records`;
  renderHistory();
  return data;
}
async function openRun(id,restore=false) {
  clearTimeout(debounce);
  closeRecord(false);
  state.data=null;
  $('workspace').hidden=true;
  state.id=id;
  if(!restore) {
    state.filters=defaults();
    const run=state.runs.find(r=>r.id===id);
    if(run&&run.passed===run.total)state.filters.status='all';
    showTab('records');
  }
  renderHistory();
  await loadResults();
}
function apply(patch) {
  state.filters= {
    ...state.filters,...patch,page:1
  }
  ;
  persist();
  loadResults();
}
async function loadResults() {
  if(!state.id)return;
  state.controller?.abort();
  state.controller=new AbortController();
  const sequence=++state.sequence;
  setNotice('');
  $('loading').hidden=false;
  $('workspace').setAttribute('aria-busy','true');
  document.querySelectorAll('[data-export]').forEach(a=> {
    a.removeAttribute('href');
    a.setAttribute('aria-disabled','true');
  }
  );
  try {
    const data=await api(`/api/runs/${state.id}?${query()}`, {
      signal:state.controller.signal
    }
    );
    if(sequence!==state.sequence)return;
    state.data=data;
    state.filters.page=data.page;
    $('empty').hidden=true;
    $('workspace').hidden=state.recordKey!==null;
    render(data);
    persist();
  }
  catch(error) {
    if(error.name!=='AbortError')setNotice(error.message);
  }
  finally {
    if(sequence===state.sequence) {
      $('loading').hidden=true;
      $('workspace').setAttribute('aria-busy','false');
    }
  }
}
function render(data) {
  const run=data.run;
  $('filename').textContent=run.filename;
  $('run-meta').textContent=`${run.profile==='agents'?'Agent export':'Forms disclosure'}${run.sheet?' · '+run.sheet:''} · ${shortDate(run.created_at)} · Rules ${run.rules_version}`;
  $('rule-version').textContent=run.rules_version;
  for(const [key,id] of [['total','total-count'],['passed','passed-count'],['review','review-count'],['failed','failed-count']])$(id).textContent=fmt(run[key]);
  document.querySelectorAll('[data-status]').forEach(b=> {
    const selected=b.dataset.status===state.filters.status;
    b.classList.toggle('selected',selected);
    b.setAttribute('aria-pressed',String(selected));
  }
  );
  options('field',data.fields.map(f=>[f.id,f.label]),'All fields');
  options('column',data.fields.map(f=>[f.id,f.label]),'Choose a column');
  options('rule',data.rules.map(([id,title])=>[id,title]),'All rules');
  for(const id of ['status','field','rule','severity','column','value','sort']) {
    if(id!=='value'||document.activeElement!==$('value'))$(id).value=state.filters[id]||'';
  }
  if(document.activeElement!==$('search'))$('search').value=state.filters.q;
  $('blank').checked=state.filters.blank==='1';
  $('value').disabled=!state.filters.column;
  $('blank').disabled=!state.filters.column;
  $('page-size').value=String(state.filters.size);
  if(state.filters.column)document.querySelector('.value-filter').open=true;
  $('match-count').replaceChildren(node('strong','',fmt(data.matched)),document.createTextNode(' matching records of '+fmt(run.total)+' · '+fmt(data.findings)+' findings'));
  renderChips(data);
  renderChart(data);
  renderRecords(data);
  renderFields(data);
  renderRules(data);
  for(const a of document.querySelectorAll('[data-export]')) {
    const params=query();
    params.set('kind',a.dataset.export);
    if(a.dataset.scope)params.set('scope',a.dataset.scope);
    a.href=`/api/runs/${state.id}/export?${params}`;
    a.removeAttribute('aria-disabled');
  }
  showTab(state.tab);
}
function renderChips(data) {
  const box=$('filter-chips');
  box.replaceChildren();
  const labels=Object.fromEntries(data.fields.map(f=>[f.id,f.label]));
  const chips=[];
  if(state.filters.status!=='all')chips.push(['status',state.filters.status==='attention'?'Needs attention':state.filters.status]);
  if(state.filters.field)chips.push(['field',labels[state.filters.field]]);
  if(state.filters.rule)chips.push(['rule',data.rules.find(r=>r[0]===state.filters.rule)?.[1]||state.filters.rule]);
  if(state.filters.severity)chips.push(['severity',state.filters.severity==='ERROR'?'Errors':'Warnings']);
  if(state.filters.column&&(state.filters.value||state.filters.blank))chips.push(['column',labels[state.filters.column]+': '+(state.filters.blank?'Blank':state.filters.value)]);
  if(state.filters.q)chips.push(['q','Search: '+state.filters.q]);
  for(const [key,label] of chips) {
    const button=node('button','chip',label+' ×');
    button.title='Remove filter: '+label;
    button.setAttribute('aria-label','Remove filter: '+label);
    button.addEventListener('click',()=>apply(key==='column'? {
      column:'',value:'',blank:'',exact:''
    }
    : {
      [key]:key==='status'?'all':''
    }
    ));
    box.append(button);
  }
}
function renderChart(data) {
  const chart=$('chart');
  chart.replaceChildren();
  const rows=data.fields.filter(f=>f.affected>0).sort((a,b)=>b.affected-a.affected).slice(0,6);
  $('chart-empty').hidden=rows.length>0;
  const max=Math.max(1,...rows.map(f=>f.affected));
  for(const field of rows) {
    const button=node('button','bar-row'+(state.filters.field===field.id?' selected':''));
    button.title=field.label+' · '+fmt(field.affected)+' affected records';
    button.setAttribute('aria-label',`Filter ${field.label}: ${field.affected} affected records`);
    const track=node('span','bar-track');
    const fill=node('span','bar-fill');
    fill.style.width=(field.affected/max*100)+'%';
    track.append(fill);
    button.append(node('span','bar-label',field.label),track,node('span','bar-count',fmt(field.affected)));
    button.addEventListener('click',()=>apply( {
      field:state.filters.field===field.id?'':field.id,rule:''
    }
    ));
    chart.append(button);
  }
}
function renderRecords(data) {
  const body=$('records');
  body.replaceChildren();
  const labels=Object.fromEntries(data.fields.map(f=>[f.id,f.label]));
  for(const r of data.records) {
    const tr=node('tr');
    tr.dataset.key=r.key;
    tr.addEventListener('click',()=> {
      state.returnFocus=button;
      navigate(state.id,r.key);
    });
    const status=node('td');
    status.append(badge(r.status));
    const name=node('td');
    const button=node('button','record-open',r.name||'Unnamed record');
    button.setAttribute('aria-label','Inspect '+(r.name||'unnamed record')+', source row '+r.source_row);
    button.type='button';
    name.append(button,node('div','record-id',r.response_id||'Missing ID'));
    const fields=r.affected_fields.map(f=>labels[f]||f);
    const fieldCell=node('td','field-cell',fields.slice(0,2).join(', ')+(fields.length>2?' +'+(fields.length-2):'')||'—');
    fieldCell.title=fields.join(', ');
    const issues=node('td','issue-numbers numeric');
    if(r.errors)issues.append(node('div','error-number',`${r.errors} ${r.errors===1?'error':'errors'}`));
    if(r.warnings)issues.append(node('div','warning-number',`${r.warnings} ${r.warnings===1?'warning':'warnings'}`));
    if(!r.errors&&!r.warnings)issues.textContent='—';
    tr.append(status,name,node('td','owner-cell',r.owner||'—'),fieldCell,issues,node('td','numeric muted',String(r.source_row)));
    body.append(tr);
  }
  $('no-results').hidden=data.matched>0;
  $('page-info').textContent=`Page ${data.page} of ${data.pages}`;
  $('previous').disabled=data.page<=1;
  $('next').disabled=data.page>=data.pages;
}
function renderFields(data) {
  const body=$('fields');
  body.replaceChildren();
  for(const field of data.fields) {
    const tr=node('tr');
    const name=node('td','field-name');
    const button=node('button','field-link',field.label);
    button.disabled=!field.affected;
    button.addEventListener('click',()=> {
      showTab('records');
      apply( {
        field:field.id,rule:''
      }
      );
    }
    );
    name.append(button,node('small','',field.source?'Source: '+field.source:'Not supplied in this format'));
    const common=node('td','field-common');
    for(const entry of field.common.slice(0,3)) {
      const button=node('button','',`${entry.value} · ${fmt(entry.count)}`);
      button.title=entry.value;
      button.addEventListener('click',()=> {
        showTab('records');
        apply( {
          field:'',rule:'',severity:'',column:field.id,value:entry.value,blank:'',exact:'1'
        }
        );
      }
      );
      common.append(button);
    }
    if(!field.common.length)common.textContent='—';
    tr.append(name,node('td','numeric',fmt(field.affected)),node('td','numeric error-number',fmt(field.errors)),node('td','numeric warning-number',fmt(field.warnings)),node('td','numeric',fmt(field.blank)),node('td','numeric',fmt(field.distinct)),common);
    body.append(tr);
  }
}
function renderRules(data) {
  $('rules-meta').textContent=`Rules ${data.run.rules_version} · ${data.run.profile==='agents'?'Agent export':'Forms disclosure'} · Evaluated as of ${data.run.as_of}`;
  const list=$('rules-list');
  list.replaceChildren();
  for(const field of data.fields) {
    const card=node('article','rule-card');
    card.append(node('h3','',field.label),node('small','',field.source?'Source: '+field.source:'Source metadata not supplied'),node('p','',field.rules));
    list.append(card);
  }
}
function routeHash(id,key=null) {
  return '#run/'+encodeURIComponent(id)+(key===null?'':'/record/'+key);
}
function readRoute() {
  const match=location.hash.match(/^#run\/([a-zA-Z0-9-]+)(?:\/record\/(\d+))?$/);
  return match?{id:match[1],key:match[2]===undefined?null:Number(match[2])}:null;
}
function navigate(id,key=null) {
  const hash=routeHash(id,key);
  if(location.hash!==hash)history.pushState({fromResults:key!==null&&location.hash===routeHash(id)},'',hash);
  return showRoute();
}
async function showRoute() {
  const route=readRoute();
  if(!route) {
    closeRecord();
    return;
  }
  const hash=location.hash;
  if(route.id!==state.id)await openRun(route.id);
  if(location.hash!==hash)return;
  if(route.key===null)closeRecord();
  else await openRecord(route.key);
}
function closeRecord(restorePosition=true) {
  state.recordSequence++;
  const wasOpen=state.recordKey!==null;
  state.recordKey=null;
  $('record-view').hidden=true;
  $('workspace').hidden=!state.data;
  if(wasOpen&&restorePosition) {
    state.returnFocus?.focus({preventScroll:true});
    window.scrollTo(0,state.returnScroll);
  }
}
async function openRecord(key) {
  const sequence=++state.recordSequence;
  const run=state.id;
  if(state.recordKey===null)state.returnScroll=window.scrollY;
  state.recordKey=key;
  setNotice('');
  $('workspace').hidden=true;
  $('empty').hidden=true;
  $('record-view').hidden=false;
  $('record-view').setAttribute('aria-busy','true');
  $('record-title').textContent='Record details';
  $('record-file').textContent=state.runs.find(r=>r.id===run)?.filename||'';
  $('record-meta').textContent='';
  $('record-status').replaceChildren();
  $('record-error').hidden=true;
  $('record-content').hidden=true;
  $('record-loading').hidden=false;
  window.scrollTo(0,0);
  $('record-title').focus({preventScroll:true});
  try {
    const data=await api(`/api/runs/${run}/records/${key}`);
    if(sequence!==state.recordSequence||run!==state.id)return;
    const r=data.record;
    $('record-title').textContent=r.name||'Unnamed record';
    $('record-meta').textContent=`Record ${r.response_id||'ID missing'} · Source row ${r.source_row}`;
    $('record-status').replaceChildren(badge(r.status),document.createTextNode(`  ${r.errors} ${r.errors===1?'error':'errors'} · ${r.warnings} ${r.warnings===1?'warning':'warnings'}`));
    const findings=$('record-findings');
    findings.replaceChildren();
    if(!r.findings.length)findings.append(node('p','muted','All applicable checks passed.'));
    $('source-values').replaceChildren();
    const fields=data.fields.map(field=> {
      const issues=r.findings.filter(f=>f.fields.includes(field.id));
      return {...field,issues,rank:issues.some(f=>f.severity==='ERROR')?0:issues.length?1:2};
    }).filter(field=>(field.source!==null&&field.source!==undefined)||field.issues.length);
    fields.sort((a,b)=>a.rank-b.rank);
    for(const field of fields) {
      const kind=field.rank===0?'error':field.rank===1?'warning':'';
      const tr=node('tr',kind?'field-'+kind:'');
      tr.dataset.field=field.id;
      tr.tabIndex=-1;
      const label=node('td','source-label');
      label.append(node('strong','',field.label),node('small','muted',field.source===null||field.source===undefined?'Not supplied in this file':field.source));
      const value=node('td','source-value');
      const raw=field.source===null||field.source===undefined?r.cells[field.id]:r.source_values[field.source];
      value.append(node('span','value-caption muted small','Submitted value'),node('div','field-value',valueText(raw)||'(blank)'));
      const validation=node('td','field-validation');
      if(kind) {
        const flag=node('span','badge '+(kind==='error'?'failed':'review'),kind==='error'?'× Error':'! Warning');
        validation.append(flag);
        const jump=node('button','field-jump '+kind,field.label);
        jump.append(node('span','',kind==='error'?'Error':'Warning'));
        jump.addEventListener('click',()=> {
          tr.scrollIntoView({block:'center'});
          tr.focus({preventScroll:true});
        });
        findings.append(jump);
        for(const f of field.issues) {
          const issue=node('div','field-issue');
          issue.append(node('span','rule-id',(f.severity==='ERROR'?'Error':'Warning')+' · '+f.rule_id),node('p','',f.message),node('p','expected','Expected: '+f.expected_condition));
          validation.append(issue);
        }
      }
      else validation.append(node('span','muted small','—'));
      tr.append(label,value,validation);
      $('source-values').append(tr);
    }
    $('record-content').hidden=false;
  }
  catch(error) {
    if(sequence!==state.recordSequence||run!==state.id)return;
    $('record-error-message').textContent=error.message;
    $('record-error').hidden=false;
  }
  finally {
    if(sequence===state.recordSequence&&run===state.id) {
      $('record-loading').hidden=true;
      $('record-view').setAttribute('aria-busy','false');
    }
  }
}
$('back-to-results').addEventListener('click',()=> {
  if(history.state?.fromResults)history.back();
  else {
    history.replaceState(null,'',routeHash(state.id));
    showRoute();
  }
});
$('record-retry').addEventListener('click',()=>openRecord(state.recordKey));
window.addEventListener('popstate',showRoute);
function resetFilters() {
  clearTimeout(debounce);
  state.filters= {
    ...defaults(),status:'all',size:state.filters.size
  }
  ;
  $('search').value='';
  loadResults();
}
let debounce;
$('search').addEventListener('input',()=> {
  clearTimeout(debounce);
  debounce=setTimeout(()=>apply( {
    q:$('search').value
  }
  ),250);
}
);
for(const id of ['status','field','rule','severity','sort'])$(id).addEventListener('change',()=>apply( {
  [id]:$(id).value,...(id==='field'? {
    rule:''
  }
  : {
  }
  )
}
));
$('column').addEventListener('change',()=>apply( {
  column:$('column').value,value:'',blank:'',exact:''
}
));
$('value').addEventListener('input',()=> {
  clearTimeout(debounce);
  debounce=setTimeout(()=>apply( {
    value:$('value').value,exact:''
  }
  ),250);
}
);
$('blank').addEventListener('change',()=>apply( {
  blank:$('blank').checked?'1':'',value:'',exact:''
}
));
$('clear-filters').addEventListener('click',resetFilters);
$('reset-empty').addEventListener('click',resetFilters);
$('page-size').addEventListener('change',()=>apply( {
  size:Number($('page-size').value)
}
));
for(const [id,offset] of [['previous',-1],['next',1]])$(id).addEventListener('click',()=> {
  state.filters.page+=offset;
  loadResults();
}
);
for(const button of document.querySelectorAll('[data-status]'))button.addEventListener('click',()=>apply( {
  status:button.dataset.status
}
));
const tabs=[...document.querySelectorAll('[data-tab]')];
for(const button of tabs) {
  button.addEventListener('click',()=>showTab(button.dataset.tab));
  button.addEventListener('keydown',event=> {
    if(!['ArrowLeft','ArrowRight'].includes(event.key))return;
    event.preventDefault();
    const index=(tabs.indexOf(button)+(event.key==='ArrowRight'?1:-1)+tabs.length)%tabs.length;
    showTab(tabs[index].dataset.tab);
    tabs[index].focus();
  }
  );
}
for(const button of document.querySelectorAll('[data-close]'))button.addEventListener('click',()=> {
  $(button.dataset.close).close();
}
);
for(const dialog of document.querySelectorAll('dialog'))dialog.addEventListener('click',event=> {
  if(event.target!==dialog)return;
  const bounds=dialog.getBoundingClientRect();
  if(!state.uploading&&(event.clientX<bounds.left||event.clientX>bounds.right||event.clientY<bounds.top||event.clientY>bounds.bottom))dialog.close();
}
);
$('upload-dialog').addEventListener('cancel',event=> {
  if(state.uploading)event.preventDefault();
}
);
for(const button of document.querySelectorAll('.upload-trigger'))button.addEventListener('click',()=> {
  $('upload-error').hidden=true;
  $('upload-dialog').showModal();
}
);
function fileChanged() {
  $('chosen-file').textContent=$('file').files[0]?.name||'';
  $('sheet-label').hidden=true;
  $('sheet').replaceChildren();
  $('upload-error').hidden=true;
}
$('file').addEventListener('change',fileChanged);
for(const name of ['dragenter','dragover'])$('dropzone').addEventListener(name,event=> {
  event.preventDefault();
  $('dropzone').classList.add('dragging');
}
);
$('dropzone').addEventListener('dragleave',()=>$('dropzone').classList.remove('dragging'));
$('dropzone').addEventListener('drop',event=> {
  event.preventDefault();
  $('dropzone').classList.remove('dragging');
  if(state.uploading)return;
  if(event.dataTransfer.files.length!==1) {
    $('upload-error').textContent='Upload one file at a time.';
    $('upload-error').hidden=false;
    return;
  }
  $('file').files=event.dataTransfer.files;
  fileChanged();
}
);
$('upload-form').addEventListener('submit',async event=> {
  event.preventDefault();
  if(state.uploading)return;
  const file=$('file').files[0];
  if(!file)return;
  state.uploading=true;
  $('upload-submit').disabled=true;
  $('file').disabled=true;
  document.querySelector('[data-close="upload-dialog"]').disabled=true;
  $('upload-error').hidden=true;
  $('upload-progress').hidden=false;
  $('upload-submit').textContent='Validating…';
  try {
    const form=new FormData();
    form.append('file',file);
    if(!$('sheet-label').hidden)form.append('sheet',$('sheet').value);
    const data=await api('/api/runs', {
      method:'POST',headers: {
        'X-Requested-With':'AIInventory'
      }
      ,body:form
    }
    );
    $('upload-dialog').close();
    $('file').value='';
    fileChanged();
    await getRuns();
    await navigate(data.id);
  }
  catch(error) {
    if(error.data?.sheets) {
      options('sheet',error.data.sheets.map(s=>[s,s]),null);
      $('sheet-label').hidden=false;
    }
    $('upload-error').textContent=error.message;
    $('upload-error').hidden=false;
  }
  finally {
    state.uploading=false;
    $('upload-submit').disabled=false;
    $('file').disabled=false;
    document.querySelector('[data-close="upload-dialog"]').disabled=false;
    $('upload-progress').hidden=true;
    $('upload-submit').textContent='Validate file';
  }
}
);
document.addEventListener('click',event=> {
  if(!$('export-menu').contains(event.target))$('export-menu').open=false;
}
);
async function init() {
  try {
    await getRuns();
    let saved;
    try {
      saved=JSON.parse(sessionStorage.getItem('ai-inventory-review'));
    }
    catch {
    }
    const route=readRoute();
    const id=route?.id||(saved&&state.runs.some(r=>r.id===saved.id)?saved.id:state.runs[0]?.id);
    if(id) {
      if(saved?.id===id) {
        state.filters={...defaults(),...saved.filters};
        state.tab=['records','fields','rules'].includes(saved.tab)?saved.tab:'records';
      }
      history.replaceState(history.state,'',routeHash(id,route?.key??null));
      await openRun(id,saved?.id===id);
      if(route?.key!==null&&route?.key!==undefined)await openRecord(route.key);
    }
    else $('empty').hidden=false;
  }
  catch(error) {
    setNotice(error.message);
    $('empty').hidden=false;
  }
}
init();
