'use strict';

// One linked table and chart per selected field, conditioned on the preceding selections.
function renderComparison() {
  const fields = selectedChartFields();
  const definitions = fields.map(field => chartState.data.charts.find(chart => chart.id === field));
  const records = chartState.data.underlying_records;
  if (records.some(record => !Array.isArray(record.findings))) {
    throw new Error('Validation details are unavailable. Restart the local app and refresh this review.');
  }
  const population = state.data.run.total;
  const portfolio = $('comparison-values').value === 'portfolio';
  const key = chartState.cache.key;
  if (chartState.explorer?.key !== key) chartState.explorer = {key, fields: [], selections: [], pages: []};
  const explorer = chartState.explorer;
  let common = 0;
  while (common < fields.length && explorer.fields[common] === fields[common]) common++;
  explorer.selections.length = Math.min(explorer.selections.length, common);
  explorer.pages.length = Math.min(explorer.pages.length, common);
  explorer.fields = [...fields];
  const pageSize = fields.length > 3 ? 3 : 6;
  const wrapper = node('div', undefined, 'comparison-view');
  const board = node('section', undefined, 'analysis-board');
  board.setAttribute('aria-label', 'Record drill-down canvas');
  const status = node('p', '', 'comparison-context');
  status.setAttribute('role', 'status');
  let model;

  function concentration(members, mode, denominator) {
    const labels = {counts: 'Model counts', vendor: 'Vendor contacts', scope: 'Scope selections',
      ids: 'Application IDs', dates: 'Dates', owners: 'Owner details', required: 'Required fields', other: 'Other checks'};
    const family = id => id.startsWith('COUNT-') ? 'counts' : (id.startsWith('VENDOR-') || id === 'EMAIL-02') ? 'vendor'
      : id.startsWith('SCOPE-') ? 'scope' : id.startsWith('ID-') ? 'ids' : id.startsWith('DATE-') ? 'dates'
      : (id === 'EMAIL-01' || id === 'REQ-02') ? 'owners' : id === 'REQ-01' ? 'required' : 'other';
    const fields = new Map(state.data.fields.map(field => [field.id, field.label]));
    const groups = new Map();
    for (const record of members) {
      for (const finding of record.findings) {
        const entries = mode === 'columns' ? finding.fields.map(id => [id, fields.get(id) || id])
          : mode === 'rules' ? [[finding.rule_id, finding.rule_id + ' · ' + finding.title]]
          : [[family(finding.rule_id), labels[family(finding.rule_id)]]];
        for (const [id, label] of entries) {
          if (!groups.has(id)) groups.set(id, {id, label, keys: new Set()});
          groups.get(id).keys.add(record.key);
        }
      }
    }
    const all = [...groups.values()].map(group => ({id: group.id, label: group.label,
      keys: [...group.keys], count: group.keys.size, percent: denominator ? 100 * group.keys.size / denominator : 0}))
      .sort((a,b) => b.count - a.count || a.label.localeCompare(b.label));
    const flagged = members.filter(record => record.findings.length);
    return {mode, label: mode === 'columns' ? 'Columns in findings' : mode === 'rules' ? 'Validation rules' : 'Finding families',
      scope: chartState.validationScope === 'path' ? 'Selected path' : 'Current view',
      total: members.length, flagged: flagged.length, passed: members.length - flagged.length,
      instances: members.reduce((sum, record) => sum + record.findings.length, 0),
      denominator, percent: denominator ? 100 * flagged.length / denominator : 0,
      keys: flagged.map(record => record.key), all, visible: all.slice(0,7),
      max: Math.max(1,...all.map(group => group.count))};
  }

  function button(label, callback, className = 'quiet') {
    const element = node('button', label, className);
    element.type = 'button';
    element.addEventListener('click', callback);
    return element;
  }
  function productLabel(count) {
    return count.toLocaleString() + (count === 1 ? ' record' : ' records');
  }
  function pathLabel(path) {
    return path.map(item => item.title + ': ' + item.value).join(' / ');
  }
  function buildModel() {
    let members = records;
    const path = [];
    const levels = definitions.map((definition, index) => {
      const counts = new Map();
      const flagged = new Map();
      for (const record of members) {
        for (const label of new Set(record.categories[definition.id])) {
          counts.set(label, (counts.get(label) || 0) + 1);
          if (record.findings.length) {
            if (!flagged.has(label)) flagged.set(label, []);
            flagged.get(label).push(record.key);
          }
        }
      }
      const denominator = portfolio ? population : members.length;
      const groups = [...counts].map(([label, count]) => {
        const bucket = definition.buckets.find(item => item.label === label) || {label, color_index: -1};
        return {label, count, flagged: flagged.get(label)?.length || 0, flaggedKeys: flagged.get(label) || [],
          percent: denominator ? 100 * count / denominator : 0,
          color: chartColor(definition, bucket), color_index: bucket.color_index};
      }).sort((a, b) => b.count - a.count || a.label.localeCompare(b.label));
      const selected = groups.some(group => group.label === explorer.selections[index])
        ? explorer.selections[index] : groups[0]?.label || '';
      explorer.selections[index] = selected;
      const page = Math.max(0, Math.min(explorer.pages[index] || 0, Math.ceil(groups.length / pageSize) - 1));
      explorer.pages[index] = page;
      const chart = {...definition, path: [...path], denominator: members.length, total_records: members.length,
        title: definition.title + (path.length ? ' — ' + pathLabel(path) : ''),
        basis: productLabel(members.length) + ' in this group · ' +
          (portfolio ? '% of all ' + productLabel(population) : '% within this group'),
        percentage_denominator: denominator, percent_label: portfolio ? '% of all records' : '% within group',
        kind: 'bar', buckets: groups.map(group => ({...group, record_percent: group.percent})),
        missing_records: counts.get('Missing') || 0, invalid_records: counts.get('Invalid') || 0,
        unclassified_records: counts.get('Unclassified') || 0};
      chart.valid_records = members.length - chart.missing_records - chart.invalid_records - chart.unclassified_records;
      chart.selection_count = groups.reduce((sum, group) => sum + group.count, 0);
      const selectedPage = Math.floor(groups.findIndex(group => group.label === selected) / pageSize);
      const level = {index, field: definition.id, title: definition.title, multi: definition.multi,
        parentPath: [...path], parentCount: members.length, denominator, groups, selected, page, pageSize, chart,
        selectedPage,
        visible: groups.slice(page * pageSize, (page + 1) * pageSize),
        max: Math.max(1, ...groups.map(group => group.count))};
      if (selected) path.push({field: definition.id, title: definition.title, value: selected});
      members = selected ? members.filter(record => record.categories[definition.id].includes(selected)) : [];
      return level;
    });
    const concentrationMembers = chartState.validationScope === 'path' ? members : records;
    const activeFilters = [];
    if (chartState.data.scope === 'all') activeFilters.push('All records in the file');
    else {
      if ($('status').value !== 'all') activeFilters.push('Status: ' + $('status').value);
      if ($('field').value) activeFilters.push('Finding in ' + state.data.fields.find(field => field.id === $('field').value).label);
      if ($('search').value) activeFilters.push('Search: ' + $('search').value);
      if (!activeFilters.length) activeFilters.push('All current records');
    }
    return {levels, path, population, scopeCount: records.length, focusCount: members.length, portfolio,
      filterContext: activeFilters.join(' · '),
      focusKeys: members.map(record => record.key),
      focusFlagged: members.filter(record => record.findings.length).length,
      concentration: concentration(concentrationMembers, chartState.validationMode || 'families', portfolio ? population : concentrationMembers.length),
      scope: chartState.data.scope === 'all' ? 'Entire file' : 'Current filters, all pages',
      file: state.data.run.filename, run: state.id, stamp: new Date().toISOString(),
      focusPercent: population ? 100 * members.length / population : 0,
      title: 'Portfolio drill-down', dense: fields.length > 3};
  }
  function select(level, label) {
    explorer.selections[level.index] = label;
    explorer.selections.length = level.index + 1;
    explorer.pages.length = level.index + 1;
    draw();
    status.textContent = productLabel(model.focusCount) + ' match the selected path.';
  }
  function showProducts(level, group) {
    chartActions.records(level.chart, group?.label || '');
  }
  async function download(action, element) {
    element.disabled = true;
    status.textContent = '';
    try { await action(model); }
    catch (error) { status.textContent = error.message; }
    finally { element.disabled = !model.scopeCount; }
  }

  const tools = node('div', undefined, 'analysis-tools actions');
  const hint = node('p', 'Select a category in a chart or table to update the following levels.', 'comparison-context');
  const reset = button('Reset path', () => { explorer.selections = []; explorer.pages = []; draw(); });
  const review = button('Review selected records', () => chartActions.recordsByKeys(model.levels[0].chart,
    model.focusKeys, 'Selected path', {path: model.path}));
  const csv = button('Download data (CSV)', () => download(chartActions.downloadDrilldown, csv), '');
  const png = button('Export slide (PNG)', () => download(chartActions.downloadSlide, png), 'primary');
  for (const [text, setting, options] of [
    ['Concentration scope', 'validationScope', [['view','Current view'],['path','Selected path']]],
    ['Group findings by', 'validationMode', [['families','Finding family'],['columns','Inventory column'],['rules','Validation rule']]]
  ]) {
    const label = node('label', text);
    const select = node('select');
    select.id = setting === 'validationScope' ? 'validation-scope' : 'validation-grouping';
    select.append(...options.map(([value, text]) => option(value, text)));
    select.value = chartState[setting] || options[0][0];
    select.addEventListener('change', () => { chartState[setting] = select.value; draw(); });
    label.append(select); tools.append(label);
  }
  tools.append(reset, review, csv, png);
  wrapper.append(hint, tools, board, status);

  function renderLevel(level) {
    const panel = node('section', undefined, 'analysis-level');
    panel.dataset.level = level.index + 1;
    panel.setAttribute('aria-label', 'Level ' + (level.index + 1) + ': ' + level.title);
    const header = node('header', undefined, 'analysis-level-header');
    const title = node('div');
    title.append(node('small', 'LEVEL ' + (level.index + 1)), node('h4', level.title));
    const detail = button('Chart', () => showComparisonChart(level.chart), 'quiet');
    detail.setAttribute('aria-label', 'View ' + level.title + ' chart' +
      (level.parentPath.length ? ' within ' + pathLabel(level.parentPath) : ' for all records'));
    detail.disabled = !level.parentCount;
    header.append(title, detail);
    const context = node('p', (level.parentPath.length
      ? 'Within ' + level.parentPath.at(-1).value : model.scope) + ' · ' + productLabel(level.parentCount), 'analysis-level-context');
    context.title = pathLabel(level.parentPath) || model.scope;
    panel.append(header, context);

    const plot = node('div', undefined, 'analysis-plot');
    plot.setAttribute('role', 'group');
    plot.setAttribute('aria-label', level.title + ' chart, record counts');
    const axis = node('div', undefined, 'analysis-axis');
    axis.append(node('span', 'Flagged / total' + (level.groups.length && level.selectedPage !== level.page
      ? ' · selection on page ' + (level.selectedPage + 1) : '')), node('span', '0 – ' + level.max.toLocaleString()));
    plot.append(axis);
    for (const group of level.visible) {
      const bar = button('', () => select(level, group.label), 'analysis-bar');
      bar.dataset.category = group.label;
      bar.classList.toggle('is-selected', group.label === level.selected);
      bar.setAttribute('aria-label', 'Drill into ' + level.title + ': ' + group.label + ' from chart');
      const label = node('span', group.label, 'analysis-bar-label');
      label.title = group.label;
      const track = node('span', undefined, 'analysis-bar-track');
      const failed = node('span', undefined, 'analysis-bar-flagged');
      failed.style.width = (100 * group.flagged / level.max) + '%';
      const passed = node('span', undefined, 'analysis-bar-passed');
      passed.style.width = (100 * (group.count - group.flagged) / level.max) + '%';
      track.append(failed, passed);
      bar.append(label, track, node('strong', group.flagged.toLocaleString() + '/' + group.count.toLocaleString()));
      plot.append(bar);
    }
    if (!level.groups.length) plot.append(node('p', 'No records in this scope.', 'chart-empty'));
    panel.append(plot);

    const table = node('table', undefined, 'analysis-table');
    const caption = node('caption', level.title + ' within ' + (pathLabel(level.parentPath) || model.scope), 'visually-hidden');
    const head = node('thead');
    const headings = node('tr');
    for (const value of ['Category', 'Records', 'Flagged', 'Share']) { const th = node('th', value); th.scope = 'col'; headings.append(th); }
    head.append(headings);
    const body = node('tbody');
    for (const group of level.visible) {
      const row = node('tr');
      row.dataset.category = group.label;
      row.classList.toggle('is-selected', group.label === level.selected);
      const name = node('th'); name.scope = 'row';
      const choose = button(group.label, () => select(level, group.label), 'analysis-category');
      choose.setAttribute('aria-label', 'Drill into ' + level.title + ': ' + group.label);
      choose.setAttribute('aria-pressed', String(group.label === level.selected));
      choose.title = group.label;
      name.append(choose);
      const count = node('td');
      const inspect = button(group.count.toLocaleString(), () => showProducts(level, group), 'analysis-count');
      inspect.setAttribute('aria-label', 'View ' + productLabel(group.count) + ' for ' + level.title + ': ' + group.label);
      count.append(inspect);
      const flagged = node('td');
      const issues = button(group.flagged.toLocaleString(), () => chartActions.recordsByKeys(level.chart, group.flaggedKeys,
        level.title + ': ' + group.label + ' — records with findings',
        {path: [...level.parentPath, {field: level.field, title: level.title, value: group.label}]}), 'analysis-flagged-count');
      issues.disabled = !group.flagged;
      issues.setAttribute('aria-label', 'View ' + productLabel(group.flagged) + ' with findings for ' + level.title + ': ' + group.label);
      flagged.append(issues);
      const share = node('td', percentLabel(group.percent));
      share.title = 'Denominator: ' + productLabel(level.denominator);
      row.append(name, count, flagged, share); body.append(row);
    }
    if (!level.groups.length) { const row = node('tr'); const cell = node('td', 'No matching records'); cell.colSpan = 4; row.append(cell); body.append(row); }
    table.append(caption, head, body); panel.append(table);
    const foot = node('div', undefined, 'analysis-level-footer');
    const basis = node('span', 'Share of ' + productLabel(level.denominator) + (portfolio ? ' in file' : ' in parent'));
    foot.append(basis);
    const pagination = node('div', undefined, 'analysis-pagination');
    const previous = button('‹', () => { explorer.pages[level.index]--; draw(); });
    previous.disabled = !level.page;
    previous.setAttribute('aria-label', 'Previous categories in ' + level.title);
    const next = button('›', () => { explorer.pages[level.index]++; draw(); });
    next.disabled = (level.page + 1) * level.pageSize >= level.groups.length;
    next.setAttribute('aria-label', 'Next categories in ' + level.title);
    const start = level.groups.length ? level.page * level.pageSize + 1 : 0;
    pagination.append(previous, node('span', start + '–' + Math.min((level.page + 1) * level.pageSize, level.groups.length) + ' of ' + level.groups.length), next);
    foot.append(pagination); panel.append(foot);
    return panel;
  }

  function renderConcentration() {
    const c = model.concentration;
    const panel = node('aside', undefined, 'validation-concentration');
    panel.setAttribute('aria-label', 'Validation concentration');
    panel.append(node('h4', 'Validation concentration'), node('p', c.scope + ' · ' + productLabel(c.total), 'validation-concentration-scope'),
      node('p', model.filterContext, 'validation-concentration-filter'));
    const selection = {path: c.scope === 'Selected path' ? model.path : []};
    const flagged = button('', () => chartActions.recordsByKeys(model.levels[0].chart, c.keys,
      'Records with validation findings', selection), 'validation-concentration-total');
    flagged.disabled = !c.flagged;
    flagged.append(node('strong', c.flagged.toLocaleString()), node('span', 'records with findings'));
    panel.append(flagged, node('p', percentLabel(c.percent) + ' of ' + productLabel(c.denominator), 'validation-concentration-percent'),
      node('p', c.passed + ' pass current checks · ' + c.instances + ' finding instances', 'validation-concentration-detail'),
      node('h5', c.label));
    const groups = node('div', undefined, 'validation-concentration-groups');
    for (const group of c.visible) {
      const item = button('', () => chartActions.recordsByKeys(model.levels[0].chart, group.keys,
        group.label + ' — records with findings', selection), 'validation-concentration-group');
      item.dataset.group = group.id;
      item.setAttribute('aria-label', 'View ' + productLabel(group.count) + ' with ' + group.label + ' findings');
      const label = node('span', undefined, 'validation-concentration-label');
      const name = node('span', group.label); name.title = group.label;
      label.append(name, node('strong', group.count.toLocaleString()));
      const track = node('span', undefined, 'validation-concentration-track');
      const fill = node('span');fill.style.width = (100 * group.count / c.max) + '%';track.append(fill);
      item.append(label, track); groups.append(item);
    }
    if (!c.all.length) groups.append(node('p', 'No findings in this scope.', 'chart-empty'));
    panel.append(groups, node('p', (c.all.length > 7 ? 'Top 7 of ' + c.all.length + ' groups. ' : '') +
      'Distinct records per group; groups overlap. ' + (c.mode === 'columns' ? 'A check can use several columns. ' : '') +
      'Flagged = at least one finding.', 'validation-concentration-note'));
    return panel;
  }

  function draw() {
    model = buildModel();
    board.replaceChildren();
    board.classList.toggle('is-dense', model.dense);
    board.dataset.levels = model.levels.length;
    const heading = node('header', undefined, 'analysis-board-header');
    const title = node('div');
    title.append(node('small', 'AI INVENTORY / DRILL-DOWN'), node('h3', model.title),
      node('p', model.filterContext, 'analysis-filter-context'));
    const metrics = node('div', undefined, 'analysis-metrics');
    for (const [label, value] of [['Records in scope', model.scopeCount.toLocaleString()],
      ['Matching records', model.focusCount.toLocaleString()], ['Flagged in path', model.focusFlagged.toLocaleString()],
      ['Path share of ' + population, percentLabel(model.focusPercent)]]) {
      const metric = node('div'); metric.append(node('strong', value), node('span', label)); metrics.append(metric);
    }
    heading.append(title, metrics);
    const path = node('div', undefined, 'analysis-path');
    path.setAttribute('aria-label', 'Selected category path');
    for (const [index, item] of model.path.entries()) {
      const part = node('span', undefined, 'analysis-path-step');
      part.append(node('small', String(index + 1)), node('span', item.value));
      part.title = item.title + ': ' + item.value;
      path.append(part);
    }
    if (!model.path.length) path.append(node('span', 'No matching records'));
    const levels = node('div', undefined, 'analysis-levels');
    levels.append(...model.levels.map(renderLevel));
    const content = node('div', undefined, 'analysis-content');
    content.append(renderConcentration(), levels);
    const footer = node('footer', undefined, 'analysis-board-footer');
    const source = node('span', 'Source: ' + model.file + ' · ' + model.scope + ' · Exported ' + model.stamp.slice(0,10));
    source.title = source.textContent;
    footer.append(source, node('span', (model.portfolio ? '% of all ' + model.population + ' records.' : '% of parent records.') +
      ' Red: with findings. Teal: no findings. Groups overlap.'));
    board.append(heading, path, content, footer);
    csv.disabled = png.disabled = !model.scopeCount;
    review.disabled = !model.focusCount;
  }
  draw();
  return wrapper;
}
