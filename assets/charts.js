'use strict';

const chartState = {
  sequence: 0,
  controller: null,
  data: null,
  comparing: false,
  levels: [],
  cache: null,
  explorer: null
};

const chartPalette = [
  '#66c9d4', '#a99fe8', '#f0bd6f', '#83cbaa', '#ed9bae',
  '#91b7eb', '#d9c37b', '#b5c1cd', '#c39dc9', '#7ac4b4'
];

const percentLabel = value =>
  value.toLocaleString(undefined, {
    maximumFractionDigits: 1
  }) + '%';


function chartColor(chart, bucket) {
  if (bucket.label === 'Missing') return '#687787';
  if (bucket.label === 'Invalid') return '#e9869e';
  if (bucket.label === 'Unclassified') return '#b5c1cd';

  if (chart.id === 'risk_tier') {
    return {
      High: '#ef9298',
      Medium: '#f0bd6f',
      Low: '#83cbaa',
      Unknown: '#a5b3c0'
    }[bucket.label] || '#687787';
  }

  return chartPalette[
    Math.max(0, bucket.color_index) % chartPalette.length
  ];
}


function resetCharts() {
  if (chartState.controller) {
    chartState.controller.abort();
  }

  chartState.sequence++;
  chartState.data = null;

  $('charts-content').hidden = true;
  $('charts-error').hidden = true;
  $('charts-loading').hidden = true;
  $('charts-context').textContent = '';
}


function selectedChartFields() {
  const fields = [$('extra-chart-field').value];
  if (chartState.comparing) fields.push($('breakdown-chart-field').value, ...chartState.levels);
  const empty = fields.indexOf('');
  return fields.slice(0, Math.min(5, empty < 0 ? fields.length : empty));
}

function updateChartControls() {
  const charts = chartState.data?.charts || [];
  const fields = selectedChartFields();
  const slots = chartState.comparing ? 2 + chartState.levels.length : 1;
  $('add-chart-field').hidden = slots >= 5 || (charts.length > 0 && slots >= charts.length);
  $('add-chart-field').disabled = !fields.length || fields.length < slots;
  $('add-chart-field').setAttribute('aria-expanded', String(chartState.comparing));
  $('breakdown-chart-label').hidden = !chartState.comparing;
  $('remove-chart-field').hidden = !chartState.comparing;
  $('remove-chart-field').title = 'Remove the last breakdown field';

  function populate(select, value, preceding) {
    select.replaceChildren(option('', 'Select another field'), ...charts
      .filter(chart => !preceding.includes(chart.id))
      .map(chart => option(chart.id, chart.title)));
    select.value = value;
  }
  populate($('breakdown-chart-field'), $('breakdown-chart-field').value, fields.slice(0, 1));
  $('nested-chart-fields').replaceChildren(...chartState.levels.map((value, index) => {
    const label = node('label', 'Then by');
    const select = node('select');
    select.id = 'nested-chart-field-' + (index + 3);
    populate(select, value, fields.slice(0, index + 2));
    select.addEventListener('change', () => {
      chartState.levels[index] = select.value;
      chartState.levels = chartState.levels.slice(0, index + 1);
      loadCharts();
    });
    label.append(select);
    return label;
  }));
}

function chartParams() {
  const params = $('chart-scope').value === 'all' ? new URLSearchParams() : query();
  params.delete('page');
  params.delete('size');
  params.set('scope', $('chart-scope').value);
  return params;
}

async function loadCharts() {
  if (!state.data || state.view !== 'review') return;
  const groupBy = $('extra-chart-field').value;
  resetCharts();
  const sequence = chartState.sequence;
  const reviewSequence = state.sequence;
  const id = state.id;
  chartState.controller = new AbortController();
  const params = chartParams();
  const key = id + '?' + params;
  const current = () => chartState.sequence === sequence &&
    state.sequence === reviewSequence && state.id === id && state.view === 'review';
  $('charts-loading').hidden = false;
  try {
    if (chartState.cache?.key !== key) {
      const data = await api('/api/runs/' + id + '/analytics?' + params,
        {signal: chartState.controller.signal});
      if (!current()) return;
      chartState.cache = {key, data};
    }
    if (!current()) return;
    const data = chartState.cache.data;
    chartState.data = data;
    const scopeLabel = data.scope === 'all' ? 'Entire file' : 'Current filters, across all pages';
    $('charts-context').textContent = scopeLabel + ' · ' + data.total_records.toLocaleString() +
      ' application records. Unclassified entries do not match a chart category; this alone is not a validation error.';
    $('primary-charts').replaceChildren(...data.charts.slice(0, 3).map(renderChart));
    $('extra-chart-field').replaceChildren(option('', 'Choose a field'),
      ...data.charts.map(chart => option(chart.id, chart.title)));
    $('extra-chart-field').value = groupBy;
    updateChartControls();
    renderExtraChart();
    $('charts-content').hidden = false;
  } catch (error) {
    if (current() && error.name !== 'AbortError') {
      $('charts-error-message').textContent = error.message;
      $('charts-error').hidden = false;
    }
  } finally {
    if (current()) $('charts-loading').hidden = true;
  }
}


function pieGraphic(chart) {
  const svgNode = (tag, attrs) => {
    const element = document.createElementNS(
      'http://www.w3.org/2000/svg',
      tag
    );

    for (const [key, value] of Object.entries(attrs)) {
      element.setAttribute(key, value);
    }

    return element;
  };

  const svg = svgNode('svg', {
    viewBox: '0 0 180 180',
    class: 'pie-chart',
    'aria-hidden': 'true'
  });

  const entries = chart.buckets.filter(
    bucket => bucket.count > 0
  );

  const total = entries.reduce(
    (sum, bucket) => sum + bucket.count,
    0
  );

  if (!total) {
    svg.append(svgNode('circle', {
      cx: 90,
      cy: 90,
      r: 78,
      fill: '#303c49'
    }));

    return svg;
  }

  let angle = -Math.PI / 2;

  for (const bucket of entries) {
    const next = angle + bucket.count / total * Math.PI * 2;

    const point = value => [
      90 + 78 * Math.cos(value),
      90 + 78 * Math.sin(value)
    ].join(' ');

    const sector = entries.length === 1
      ? svgNode('circle', {cx: 90, cy: 90, r: 78})
      : svgNode('path', {
          d:
            'M 90 90 L ' + point(angle) +
            ' A 78 78 0 ' +
            (next - angle > Math.PI ? 1 : 0) +
            ' 1 ' + point(next) + ' Z'
        });

    sector.setAttribute('fill', chartColor(chart, bucket));
    sector.setAttribute('stroke', '#181f27');
    sector.setAttribute('stroke-width', '1.5');

    const tooltip = svgNode('title', {});

    tooltip.textContent =
      bucket.label + ': ' +
      bucket.count.toLocaleString() +
      ' (' + percentLabel(bucket.percent) + ')';

    sector.append(tooltip);
    svg.append(sector);
    angle = next;
  }

  return svg;
}


function chartLegend(chart) {
  const table = node('table', undefined, 'chart-legend');

  table.append(
    node(
      'caption',
      chart.title + ' distribution',
      'visually-hidden'
    )
  );

  const head = node('thead');
  const headings = node('tr');

  for (const label of [
    'Category',
    'Count',
    chart.percent_label || '% of records'
  ]) {
    const th = node('th', label);
    th.scope = 'col';
    headings.append(th);
  }

  head.append(headings);
  table.append(head);

  const body = node('tbody');

  for (const bucket of chart.buckets) {
    const row = node('tr');
    const label = node('th');
    const name = node('span', undefined, 'chart-category');

    label.scope = 'row';

    const swatch = node('span', undefined, 'chart-swatch');

    swatch.style.backgroundColor = chartColor(chart, bucket);
    swatch.setAttribute('aria-hidden', 'true');

    name.append(
      swatch,
      document.createTextNode(bucket.label)
    );

    label.append(name);

    row.append(
      label,
      node('td', bucket.count.toLocaleString()),
      node('td', percentLabel(bucket.percent))
    );

    body.append(row);
  }

  table.append(body);
  return table;
}


function barGraphic(chart) {
  const list = node('ul', undefined, 'chart-bars');

  for (const bucket of chart.buckets) {
    const item = node('li');
    const heading = node('div', undefined, 'chart-bar-label');

    heading.append(
      node('span', bucket.label),
      node(
        'strong',
        bucket.count.toLocaleString() +
        ' · ' + percentLabel(bucket.percent)
      )
    );

    const track = node('div', undefined, 'chart-bar-track');
    const fill = node('div', undefined, 'chart-bar-fill');

    track.setAttribute('aria-hidden', 'true');

    fill.style.width = bucket.percent + '%';
    fill.style.backgroundColor = chartColor(chart, bucket);

    track.append(fill);
    item.append(heading, track);
    list.append(item);
  }

  return list;
}


function renderChart(chart) {
  const card = node('article', undefined, 'chart-card');
  card.dataset.chart = chart.id;

  card.append(node('h3', chart.title));

  const basis = chart.basis ||
    chart.total_records.toLocaleString() +
    ' records · % of records';

  card.append(node('p', basis, 'chart-basis'));

  if (
    chart.denominator === 0 ||
    !chart.buckets.some(bucket => bucket.count > 0)
  ) {
    card.append(
      node(
        'p',
        chart.total_records
          ? 'No categorized values to chart.'
          : 'No records in this view.',
        'chart-empty'
      )
    );
  } else if (chart.kind === 'pie') {
    const layout = node('div', undefined, 'pie-layout');
    const legend = node('div', undefined, 'chart-legend-wrap');

    legend.append(chartLegend(chart));
    layout.append(pieGraphic(chart), legend);
    card.append(layout);
  } else {
    card.append(barGraphic(chart));
  }

  const quality =
    chart.valid_records.toLocaleString() + ' categorized · ' +
    chart.missing_records.toLocaleString() + ' missing · ' +
    chart.invalid_records.toLocaleString() + ' invalid · ' +
    (chart.unclassified_records || 0).toLocaleString() +
    ' unclassified';

  card.append(node('p', quality, 'chart-quality'));

  if (chart.note) {
    card.append(node('p', chart.note, 'chart-note'));
  }

  if (chart.multi) {
    const note = chart.percent_label === '% of all records'
      ? 'Each bar uses all ' + chart.percentage_denominator.toLocaleString() + ' records in the file. ' +
        'Records can appear in several categories, so percentages can total more than 100%.'
      : chart.percent_label
      ? 'Each bar is a percentage of records in this group. ' +
        'Records can appear in multiple categories, so percentages ' +
        'can total more than 100%.'
      : 'Each bar is a percentage of all records in this view. ' +
        'Records can appear in multiple categories, so percentages ' +
        'can total more than 100%.';

    card.append(node('p', note, 'chart-note'));
  }

  return card;
}


function renderExtraChart() {
  if (!chartState.data) return;

  const comparing = selectedChartFields().length >= 2;
  $('comparison-values-label').hidden = !comparing;
  if (comparing) {
    $('extra-chart').replaceChildren(renderComparison());
    return;
  }

  const chart = chartState.data.charts.find(
    item => item.id === $('extra-chart-field').value
  );

  if (chart) {
    $('extra-chart').replaceChildren(renderChart(chart));
  } else {
    $('extra-chart').replaceChildren(
      node(
        'p',
        'Choose a field to visualize. Use + Add field to compare ' +
        'it with another inventory field.',
        'chart-note'
      )
    );
  }
}


function recordCount(count) {
  return count.toLocaleString() +
    (count === 1 ? ' record' : ' records');
}


function showComparisonChart(chart) {
  const dialog = node('dialog', undefined, 'comparison-chart-dialog');
  const close = node('button', 'Close chart', 'quiet');
  close.type = 'button';
  close.addEventListener('click', () => dialog.close());
  dialog.setAttribute('aria-label', chart.title);
  dialog.append(close, renderChart(chart));
  dialog.addEventListener('close', () => dialog.remove(), {once: true});
  document.body.append(dialog);
  dialog.showModal();
}


function initializeCharts() {
  updateChartControls();
  $('add-chart-field').addEventListener('click', () => {
    if (!$('extra-chart-field').value) return;
    if (chartState.comparing && chartState.levels.length >= 3) return;
    if (chartState.comparing) chartState.levels.push('');
    else chartState.comparing = true;
    updateChartControls();
    const id = chartState.levels.length ? 'nested-chart-field-' + (chartState.levels.length + 2) : 'breakdown-chart-field';
    $(id).focus();
  });
  $('remove-chart-field').addEventListener('click', () => {
    if (chartState.levels.length) chartState.levels.pop();
    else {
      chartState.comparing = false;
      $('breakdown-chart-field').value = '';
    }
    updateChartControls();
    $('add-chart-field').focus();
    loadCharts();
  });
  $('chart-scope').addEventListener('change', loadCharts);
  $('extra-chart-field').addEventListener('change', () => {
    if (!$('extra-chart-field').value) chartState.comparing = false;
    if (!chartState.comparing || $('breakdown-chart-field').value === $('extra-chart-field').value) {
      $('breakdown-chart-field').value = '';
    }
    chartState.levels = [];
    loadCharts();
  });
  $('breakdown-chart-field').addEventListener('change', () => {
    chartState.levels = [];
    loadCharts();
  });
  $('comparison-values').addEventListener('change', renderExtraChart);
  $('charts-retry').addEventListener('click', loadCharts);
}
