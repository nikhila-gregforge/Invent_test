'use strict';

const chartState = {
  sequence: 0,
  controller: null,
  data: null,
  comparing: false,
  levels: [],
  cache: null
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
  $('comparison-category-label').hidden = true;
}


function selectedChartFields() {
  const fields = [$('extra-chart-field').value];
  if (chartState.comparing) fields.push($('breakdown-chart-field').value, ...chartState.levels);
  const empty = fields.indexOf('');
  return empty < 0 ? fields : fields.slice(0, empty);
}

function updateChartControls() {
  const charts = chartState.data?.charts || [];
  const fields = selectedChartFields();
  const slots = chartState.comparing ? 2 + chartState.levels.length : 1;
  $('add-chart-field').hidden = charts.length > 0 && slots >= charts.length;
  $('add-chart-field').disabled = !fields.length || fields.length < slots;
  $('add-chart-field').setAttribute('aria-expanded', String(chartState.comparing));
  $('breakdown-chart-label').hidden = !chartState.comparing;
  $('remove-chart-field').hidden = !chartState.comparing;
  $('remove-chart-field').title = 'Remove the last breakdown field';
  if (!chartState.comparing) $('comparison-category-label').hidden = true;

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
      $('comparison-category').value = '';
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

async function fetchComparison(fields, path = []) {
  const cache = chartState.cache;
  const key = JSON.stringify([fields.slice(0, 2), path]);
  if (cache.comparisons.has(key)) return cache.comparisons.get(key);
  const params = chartParams();
  params.set('group_by', fields[0]);
  params.set('breakdown_by', fields[1]);
  params.set('path', JSON.stringify(path));
  params.set('comparison_only', '1');
  const result = await api('/api/runs/' + state.id + '/analytics?' + params,
    {signal: chartState.controller.signal});
  // Bound retained branch data when analysts explore many combinations.
  if (cache.comparisons.size >= 64) cache.comparisons.delete(cache.comparisons.keys().next().value);
  cache.comparisons.set(key, result.comparison);
  return result.comparison;
}

async function loadCharts() {
  if (!state.data || state.view !== 'review') return;
  const groupBy = $('extra-chart-field').value;
  const fields = selectedChartFields();
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
      chartState.cache = {key, data, comparisons: new Map()};
    }
    const comparison = fields.length >= 2 ? await fetchComparison([fields[0], fields.at(-1)]) : null;
    if (!current()) return;
    const data = {...chartState.cache.data, comparison};
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
    const note = chart.percent_label
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

  const comparison = chartState.data.comparison;

  $('comparison-category-label').hidden = !comparison;
  $('comparison-values-label').hidden = !comparison;

  if (comparison) {
    const selected = $('comparison-category').value;

    $('comparison-category').replaceChildren(
      option('', 'All categories'),
      ...comparison.groups.map(group =>
        option(
          group.label,
          group.label + ' · ' + recordCount(group.count)
        )
      )
    );

    $('comparison-category').value =
      comparison.groups.some(group => group.label === selected)
        ? selected
        : '';

    $('extra-chart').replaceChildren(
      renderComparison(comparison, $('comparison-category').value)
    );

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


function comparisonColumns(comparison) {
  const columns = new Map();

  for (const group of comparison.groups) {
    for (const bucket of group.chart.buckets) {
      columns.set(bucket.label, bucket);
    }
  }

  const quality = ['Missing', 'Invalid', 'Unclassified'];

  const rank = bucket =>
    bucket.color_index >= 0
      ? bucket.color_index
      : 10000 + Math.max(0, quality.indexOf(bucket.label));

  return [...columns.values()].sort(
    (a, b) =>
      rank(a) - rank(b) ||
      a.label.localeCompare(b.label)
  );
}


function comparisonBuckets(group, columns) {
  const buckets = new Map(
    group.chart.buckets.map(bucket => [bucket.label, bucket])
  );

  return columns.map(column =>
    buckets.get(column.label) || {
      ...column,
      count: 0,
      percent: 0,
      record_percent: 0
    }
  );
}


function renderComparison(comparison, selected) {
  const fields = selectedChartFields();
  const portfolio = $('comparison-values').value === 'portfolio';
  const population = state.data.run.total;
  const percentageBase = portfolio ? {label: '% of all products', total: population} : null;
  const countLabel = count => portfolio ? count.toLocaleString() + (count === 1 ? ' product' : ' products') : recordCount(count);
  const definitions = fields.map(field => chartState.data.charts.find(chart => chart.id === field));
  const wrapper = node('div', undefined, 'comparison-view');
  const controls = node('div', undefined, 'actions comparison-actions');
  const status = node('p', '', 'visually-hidden');
  status.setAttribute('role', 'status');
  const scope = chartState.data.scope === 'all' ? 'Entire file' : 'Current filters, across all pages';
  const chosen = comparison.groups.find(group => group.label === selected);
  const summary = chosen ? chosen.chart : comparison.summary;
  const roots = (chosen ? [chosen] : comparison.groups).map(group => entry(group, 0));
  const columns = comparisonColumns({groups: [{chart: summary}]});
  const sequence = chartState.sequence;

  function entry(group, depth) {
    return {group, depth, expanded: false, children: null, loading: false, error: ''};
  }
  function pathLabel(chart) {
    return (chart.path || []).map(item => item.title + ': ' + item.value).join(' / ');
  }
  function button(label, callback, className = 'quiet') {
    const result = node('button', label, className);
    result.type = 'button';
    result.addEventListener('click', callback);
    return result;
  }
  function visibleRows() {
    const rows = [];
    function collect(items) {
      for (const item of items) {
        rows.push(item);
        if (item.expanded && item.children) collect(item.children);
      }
    }
    collect(roots);
    return rows;
  }
  const download = button('Download table (CSV)', () => {
    chartActions.exportTable(visibleRows().map(item => ({
      chart: item.group.chart, level: item.depth + 1,
      type: item.depth < fields.length - 2 ? 'Parent group' : 'Final group',
    })), summary, columns, fields.map((field, index) => definitions[index].title), !!chosen, percentageBase);
  }, '');
  download.title = 'Export the visible group rows and distinct total. Parent and child rows are labeled separately.';
  download.disabled = !roots.length;
  const collapse = button('Collapse all', () => {
    function close(items) {
      for (const item of items) {
        item.expanded = false;
        if (item.children) close(item.children);
      }
    }
    close(roots);
    drawRows();
  });
  collapse.hidden = fields.length === 2;
  controls.append(download, collapse);
  wrapper.append(node('h3', definitions.map(chart => chart.title).join(' → ')),
    node('p', scope + ' · ' + countLabel(summary.denominator) +
      (chosen ? ' in ' + comparison.group_title + ': ' + chosen.label : '') +
      '. Columns: ' + comparison.breakdown_title + '.', 'comparison-context'), controls);

  let explanation = portfolio
    ? 'Each source row represents one product. Percentages use all ' + population.toLocaleString() + ' products in the file, including when a category or error filter is selected. Click a count to inspect products.'
    : 'Cells show count and % of row. Click a count to inspect records.';
  if (fields.length > 2) explanation += ' Expand groups to drill down; child rows are subsets of their parent.';
  if (definitions.slice(0, -1).some(chart => chart.multi)) {
    explanation += ' Multi-select groups overlap: do not add group rows together.';
  }
  if (comparison.breakdown_multi) explanation += ' Products can have several column categories; do not add those categories together.';
  wrapper.append(node('p', explanation, 'comparison-context'));
  const scroll = node('div', undefined, 'table-scroll comparison-table-wrap');
  scroll.tabIndex = 0;
  scroll.setAttribute('role', 'region');
  scroll.setAttribute('aria-label', 'Nested comparison; scroll for more rows or columns');
  const table = node('table', undefined, 'comparison-table');
  const caption = node('caption', 'Unique records by ' + definitions.map(chart => chart.title).join(', '), 'visually-hidden');
  const head = node('thead');
  const headings = node('tr');
  for (const label of ['Group', portfolio ? 'Products' : 'Unique records', ...columns.map(column => column.label)]) {
    const th = node('th', label);
    th.scope = 'col';
    headings.append(th);
  }
  head.append(headings);
  const body = node('tbody');
  const foot = node('tfoot');
  table.append(caption, head, body, foot);
  scroll.append(table);
  wrapper.append(scroll, node('p',
    'Scroll for more rows or categories. Footer counts each source record once per column. CSV includes visible rows and footer; do not sum overlapping groups or parent and child rows.',
    'chart-note'), status);
  const notes = [...new Set(definitions.map(chart => chart.note).filter(Boolean))];
  if (notes.length) {
    const details = node('details', undefined, 'comparison-notes');
    details.append(node('summary', 'Category definitions'), ...notes.map(note => node('p', note, 'chart-note')));
    wrapper.append(details);
  }

  function countCells(row, chart) {
    const total = node('td', undefined, 'comparison-total');
    const records = button(chart.denominator.toLocaleString(), () => chartActions.records(chart), 'comparison-count');
    records.disabled = !chart.denominator;
    records.setAttribute('aria-label', 'View ' + recordCount(chart.denominator) + ' in ' + (pathLabel(chart) || 'this scope'));
    total.append(records);
    row.append(total);
    for (const bucket of comparisonBuckets({chart}, columns)) {
      const cell = node('td');
      if (bucket.count) {
        const denominator = portfolio ? population : chart.denominator;
        const percent = denominator ? 100 * bucket.count / denominator : 0;
        const basis = portfolio ? 'all products in the file' : 'records in this row';
        const value = button('', () => chartActions.records(chart, bucket.label), 'comparison-count comparison-value');
        value.append(node('strong', bucket.count.toLocaleString()), node('span', percentLabel(percent), 'comparison-percent'));
        value.title = bucket.count.toLocaleString() + ' of ' + denominator.toLocaleString() + ' ' + basis;
        value.setAttribute('aria-label', 'View ' + recordCount(bucket.count) + ', ' + bucket.label + ', ' +
          percentLabel(percent) + ' of ' + denominator.toLocaleString() + ' ' + basis + '; ' + (pathLabel(chart) || 'this scope'));
        cell.style.backgroundColor = 'rgba(102, 201, 212, ' + (0.025 + percent / 100 * 0.14) + ')';
        cell.append(value);
      } else {
        cell.append(node('span', '0', 'comparison-zero'));
      }
      row.append(cell);
    }
  }

  function drawRows(focusKey) {
    const activeKey = focusKey || document.activeElement?.dataset.comparisonFocus;
    body.replaceChildren();
    for (const item of visibleRows()) {
      const {group, depth} = item;
      const row = node('tr');
      row.dataset.depth = depth;
      const label = node('th');
      label.scope = 'row';
      const content = node('div', undefined, 'comparison-group-cell');
      content.style.paddingLeft = Math.min(depth, 4) * 14 + 'px';
      const expandable = depth < fields.length - 2;
      const name = node('span', group.label, 'comparison-group-name');
      name.prepend(node('small', definitions[depth].title));
      if (expandable) {
        const key = JSON.stringify(group.chart.path);
        const toggle = button('', () => expand(item, key), 'comparison-expand');
        const arrow = node('span', item.expanded ? '▾' : '▸', 'comparison-arrow');
        arrow.setAttribute('aria-hidden', 'true');
        toggle.append(arrow, name);
        toggle.dataset.comparisonFocus = key;
        toggle.setAttribute('aria-expanded', String(item.expanded));
        toggle.setAttribute('aria-label', (item.expanded ? 'Collapse ' : 'Expand ') + pathLabel(group.chart));
        content.append(toggle);
      } else {
        content.append(name);
      }
      const chart = button('Chart', () => showComparisonChart(group.chart), 'quiet comparison-show-chart');
      chart.setAttribute('aria-label', 'View chart for ' + pathLabel(group.chart));
      content.append(chart);
      label.title = pathLabel(group.chart);
      label.append(content);
      row.append(label);
      countCells(row, group.chart);
      body.append(row);
      if (item.expanded && (item.loading || item.error)) {
        const messageRow = node('tr');
        const message = node('td', item.loading ? 'Loading groups…' : item.error, 'comparison-load');
        message.colSpan = columns.length + 2;
        if (item.error) message.append(button('Retry', () => {
          item.expanded = false;
          expand(item, JSON.stringify(group.chart.path));
        }));
        messageRow.append(message);
        body.append(messageRow);
      }
    }
    if (!roots.length) {
      const row = node('tr');
      const empty = node('td', 'No records in this scope.', 'chart-empty');
      empty.colSpan = columns.length + 2;
      row.append(empty); body.append(row);
    }
    collapse.disabled = !roots.some(item => item.expanded);
    const focused = [...body.querySelectorAll('[data-comparison-focus]')].find(button => button.dataset.comparisonFocus === activeKey);
    if (focused) focused.focus({preventScroll: true});
  }

  async function expand(item, key) {
    item.expanded = !item.expanded;
    if (!item.expanded || item.children || item.loading) { drawRows(key); return; }
    item.loading = true;
    item.error = '';
    drawRows(key);
    try {
      const next = await fetchComparison([fields[item.depth + 1], fields.at(-1)], item.group.chart.path);
      if (chartState.sequence !== sequence || !wrapper.isConnected) return;
      item.children = next.groups.map(group => entry(group, item.depth + 1));
      status.textContent = next.groups.length + ' groups loaded for ' + item.group.label + '.';
    } catch (error) {
      if (error.name === 'AbortError' || chartState.sequence !== sequence) return;
      item.error = error.message + ' ';
      status.textContent = 'Could not load groups for ' + item.group.label + '.';
    } finally {
      item.loading = false;
      if (chartState.sequence === sequence && wrapper.isConnected) drawRows();
    }
  }

  const totalRow = node('tr');
  const totalLabel = node('th', portfolio
    ? (chosen ? 'Products in selected category' : 'Products in scope')
    : (chosen ? 'Unique records in selected category' : 'Unique records in scope'));
  totalLabel.scope = 'row';
  totalRow.append(totalLabel);
  countCells(totalRow, summary);
  foot.append(totalRow);
  drawRows();
  return wrapper;
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
    $('comparison-category').value = '';
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
    $('comparison-category').value = '';
    loadCharts();
  });
  $('breakdown-chart-field').addEventListener('change', () => {
    chartState.levels = [];
    $('comparison-category').value = '';
    loadCharts();
  });
  $('comparison-category').addEventListener('change', renderExtraChart);
  $('comparison-values').addEventListener('change', renderExtraChart);
  $('charts-retry').addEventListener('click', loadCharts);
}
