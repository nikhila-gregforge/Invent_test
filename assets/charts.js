'use strict';
const chartState = {sequence: 0, controller: null, data: null};
const chartPalette = ['#66c9d4','#a99fe8','#f0bd6f','#83cbaa','#ed9bae','#91b7eb','#d9c37b','#b5c1cd','#c39dc9','#7ac4b4'];
const percentLabel = value => value.toLocaleString(undefined, {maximumFractionDigits: 1})+'%';

function chartColor(chart, bucket) {
  if (bucket.label === 'Missing') return '#687787';
  if (bucket.label === 'Invalid') return '#e9869e';
  if (bucket.label === 'Unclassified') return '#b5c1cd';
  if (chart.id === 'risk_tier') return {High:'#ef9298',Medium:'#f0bd6f',Low:'#83cbaa',Unknown:'#a5b3c0'}[bucket.label] || '#687787';
  return chartPalette[Math.max(0,bucket.color_index) % chartPalette.length];
}

function resetCharts() {
  if (chartState.controller) chartState.controller.abort();
  chartState.sequence++;
  chartState.data = null;
  $('charts-content').hidden = true;
  $('charts-error').hidden = true;
  $('charts-loading').hidden = true;
  $('charts-context').textContent = '';
}

async function loadCharts() {
  if (!state.data || state.view !== 'review') return;
  resetCharts();
  const sequence = chartState.sequence, reviewSequence = state.sequence, id = state.id;
  chartState.controller = new AbortController();
  const params = query(); params.delete('page'); params.delete('size'); params.set('scope',$('chart-scope').value);
  const current = () => chartState.sequence === sequence && state.sequence === reviewSequence && state.id === id && state.view === 'review';
  $('charts-loading').hidden = false;
  try {
    const data = await api('/api/runs/'+id+'/analytics?'+params, {signal:chartState.controller.signal});
    if (!current()) return;
    chartState.data = data;
    $('charts-context').textContent = (data.scope === 'all' ? 'Entire file' : 'Current filters, across all pages')+' · '+data.total_records.toLocaleString()+' application records. Unclassified entries do not match a chart category; this alone is not a validation error.';
    $('primary-charts').replaceChildren(...data.charts.slice(0,3).map(renderChart));
    const selected = $('extra-chart-field').value || 'human_oversight';
    $('extra-chart-field').replaceChildren(...data.charts.slice(3).map(chart => option(chart.id,chart.title)));
    $('extra-chart-field').value = selected;
    renderExtraChart();
    $('charts-content').hidden = false;
  } catch (error) {
    if (current() && error.name !== 'AbortError') {
      $('charts-error-message').textContent = error.message;
      $('charts-error').hidden = false;
    }
  } finally { if (current()) $('charts-loading').hidden = true; }
}

function pieGraphic(chart) {
  const svgNode = (tag, attrs) => {
    const element = document.createElementNS('http://www.w3.org/2000/svg',tag);
    for (const [key,value] of Object.entries(attrs)) element.setAttribute(key,value);
    return element;
  };
  const svg = svgNode('svg',{viewBox:'0 0 180 180',class:'pie-chart','aria-hidden':'true'});
  const entries = chart.buckets.filter(bucket => bucket.count > 0);
  const total = entries.reduce((sum,bucket) => sum+bucket.count,0);
  if (!total) { svg.append(svgNode('circle',{cx:90,cy:90,r:78,fill:'#303c49'})); return svg; }
  let angle = -Math.PI/2;
  for (const bucket of entries) {
    const next = angle + bucket.count/total*Math.PI*2;
    const point = value => [90+78*Math.cos(value),90+78*Math.sin(value)].join(' ');
    const sector = entries.length === 1 ? svgNode('circle',{cx:90,cy:90,r:78}) :
      svgNode('path',{d:'M 90 90 L '+point(angle)+' A 78 78 0 '+(next-angle>Math.PI ? 1 : 0)+' 1 '+point(next)+' Z'});
    sector.setAttribute('fill',chartColor(chart,bucket));
    sector.setAttribute('stroke','#181f27'); sector.setAttribute('stroke-width','1.5');
    const tooltip = svgNode('title',{});
    tooltip.textContent = bucket.label+': '+bucket.count.toLocaleString()+' ('+percentLabel(bucket.percent)+')';
    sector.append(tooltip); svg.append(sector); angle = next;
  }
  return svg;
}

function chartLegend(chart) {
  const table = node('table',undefined,'chart-legend');
  const caption = node('caption',chart.title+' distribution','visually-hidden'); table.append(caption);
  const head = node('thead'), headings = node('tr');
  for (const label of ['Category','Count','% of records']) { const th = node('th',label); th.scope='col'; headings.append(th); }
  head.append(headings); table.append(head);
  const body = node('tbody');
  for (const bucket of chart.buckets) {
    const row = node('tr'), label = node('th'), name = node('span',undefined,'chart-category'); label.scope='row';
    const swatch = node('span',undefined,'chart-swatch'); swatch.style.backgroundColor = chartColor(chart,bucket); swatch.setAttribute('aria-hidden','true');
    name.append(swatch,document.createTextNode(bucket.label)); label.append(name);
    row.append(label,node('td',bucket.count.toLocaleString()),node('td',percentLabel(bucket.percent)));
    body.append(row);
  }
  table.append(body); return table;
}

function barGraphic(chart) {
  const list = node('ul',undefined,'chart-bars');
  for (const bucket of chart.buckets) {
    const item = node('li'), heading = node('div',undefined,'chart-bar-label');
    heading.append(node('span',bucket.label),node('strong',bucket.count.toLocaleString()+' · '+percentLabel(bucket.percent)));
    const track = node('div',undefined,'chart-bar-track'), fill = node('div',undefined,'chart-bar-fill');
    track.setAttribute('aria-hidden','true'); fill.style.width = bucket.percent+'%'; fill.style.backgroundColor = chartColor(chart,bucket);
    track.append(fill); item.append(heading,track); list.append(item);
  }
  return list;
}

function renderChart(chart) {
  const card = node('article',undefined,'chart-card'); card.dataset.chart = chart.id;
  card.append(node('h3',chart.title));
  const basis = chart.total_records.toLocaleString()+' records · % of records';
  card.append(node('p',basis,'chart-basis'));
  if (chart.denominator === 0 || !chart.buckets.some(bucket => bucket.count > 0)) card.append(node('p',chart.total_records ? 'No categorized values to chart.' : 'No records in this view.','chart-empty'));
  else if (chart.kind === 'pie') {
    const layout = node('div',undefined,'pie-layout'), legend = node('div',undefined,'chart-legend-wrap');
    legend.append(chartLegend(chart)); layout.append(pieGraphic(chart),legend); card.append(layout);
  } else card.append(barGraphic(chart));
  const quality = chart.valid_records.toLocaleString()+' categorized · '+chart.missing_records.toLocaleString()+' missing · '+chart.invalid_records.toLocaleString()+' invalid · '+(chart.unclassified_records || 0).toLocaleString()+' unclassified';
  card.append(node('p',quality,'chart-quality'));
  if (chart.multi) card.append(node('p','Each bar is a percentage of all records in this view. Records can appear in multiple categories, so percentages can total more than 100%.','chart-note'));
  return card;
}

function renderExtraChart() {
  if (!chartState.data) return;
  const chart = chartState.data.charts.find(item => item.id === $('extra-chart-field').value);
  $('extra-chart').replaceChildren(...(chart ? [renderChart(chart)] : []));
}

function initializeCharts() {
  $('chart-scope').addEventListener('change',loadCharts);
  $('extra-chart-field').addEventListener('change',renderExtraChart);
  $('charts-retry').addEventListener('click',loadCharts);
}
