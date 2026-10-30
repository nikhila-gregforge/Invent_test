'use strict';

// Load after charts.js and before app.js.
const chartActions = (() => {
  const originalChart = renderChart;

  const make = (tag, text) => {
    const element = document.createElement(tag);

    if (text !== undefined) {
      element.textContent = text;
    }

    return element;
  };

  function save(blob, name) {
    const url = URL.createObjectURL(blob);
    const link = make('a');

    link.href = url;
    link.download = name;

    document.body.append(link);
    link.click();
    link.remove();

    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  function csvCell(value) {
    let text = String(value ?? '');

    const probe = text.replace(
      /^[\s\p{Cc}\p{Cf}]+/u,
      ''
    );

    // Prevent text from becoming a spreadsheet formula.
    if (
      typeof value === 'string' &&
      /^[=+@-]/.test(probe)
    ) {
      text = "'" + text;
    }

    return '"' + text.replaceAll('"', '""') + '"';
  }

  function context() {
    return {
      run: state.id,
      file: state.data.run.filename,
      scope: $('charts-context').textContent,
      filters: chartState.data.scope === 'all'
        ? 'Entire file'
        : query().toString(),
      records: chartState.data.underlying_records,
      comparison: chartState.data.comparison
    };
  }

  function membership(ctx, chart, group, category) {
    return ctx.records.filter(record =>
      (chart.path || []).every(item => record.categories[item.field].includes(item.value)) &&
      (
        !category ||
        record.categories[chart.id].includes(category)
      )
    );
  }

  function showRecords(ctx, chart, group, category = '', selection = {}) {
    const dialog = make('dialog');
    dialog.className = 'correction-queue-dialog';
    const title = make('h2', chart.title + ' — underlying records');
    title.id = 'chart-records-title';
    dialog.setAttribute('aria-labelledby', title.id);
    const close = make('button', 'Close');
    close.type = 'button';
    close.addEventListener('click', () => dialog.close());
    const heading = make('div');
    heading.className = 'dialog-heading';
    heading.append(title, close);

    const fieldLabels = new Map(state.data.fields.map(field => [field.id, field.label]));
    const fieldLabel = id => fieldLabels.get(id) || chartState.data.charts.find(chart => chart.id === id)?.title || id;
    const valueText = value => Array.isArray(value) ? value.join('; ') : String(value ?? '');
    const pathText = path => path.map(item => item.title + ': ' + item.value).join(' / ');
    const selectedPath = () => {
      const path = [...(selection.path || chart.path || [])];
      if (select.value && !path.some(item => item.field === chart.id && item.value === select.value)) {
        path.push({field: chart.id, title: fieldLabel(chart.id), value: select.value});
      }
      return pathText(path);
    };
    const scope = make('p');
    scope.className = 'correction-queue-context';
    const baseline = make('p', 'File baseline: ' + state.data.run.total + ' records. Analytics scope: ' + ctx.scope + '.');
    baseline.className = 'correction-queue-baseline';
    const help = make('p', 'Review all saved findings on these records. Correct the source file and upload again.');
    help.className = 'correction-queue-help';

    const label = make('label', 'Category');
    const select = make('select');
    const all = make('option', selection.fixed ? 'All records in this selection' : 'All records in this chart');
    all.value = '';
    select.append(all);
    const categories = [...new Set(membership(ctx, chart, group).flatMap(record => record.categories[chart.id]))];
    for (const category of categories) {
      const option = make('option', category); option.value = category; select.append(option);
    }
    select.value = category;
    label.append(select);
    label.hidden = selection.fixed && categories.length <= 1;

    const count = make('p');
    count.setAttribute('role', 'status');
    const download = make('button', 'Download selected records (CSV)');
    download.type = 'button';
    const filters = make('div');
    filters.className = 'actions correction-queue-tools';
    filters.append(label, download);
    const scroll = make('div');
    scroll.className = 'table-scroll';
    const table = make('table');
    table.className = 'correction-queue-table';
    const head = make('thead'), headings = make('tr'), body = make('tbody');
    for (const text of ['Record', 'Owners', 'AI Inventory columns', 'Findings and submitted values', 'Required action']) {
      const th = make('th', text); th.scope = 'col'; headings.append(th);
    }
    head.append(headings); table.append(head, body); scroll.append(table);
    const controls = make('div'); controls.className = 'actions';
    const previous = make('button', 'Previous'), next = make('button', 'Next');
    previous.type = next.type = 'button'; controls.append(previous, next);
    let page = 0;
    const selectedRows = () => membership(ctx, chart, group, select.value);
    const recordFields = record => [...new Set(record.findings.flatMap(finding => finding.fields))];
    const submittedValues = record => {
      const values = new Map();
      for (const finding of record.findings) {
        for (const field of finding.fields) values.set(field, finding.values?.[field]);
      }
      return [...values].map(([field, value]) => fieldLabel(field) + ': ' + (valueText(value) || '(blank)')).join('\n');
    };
    function draw() {
      const rows = selectedRows(), start = page * 25;
      scope.textContent = 'Selection: ' + (selection.label || chart.title) +
        (selectedPath() ? '\nPath: ' + selectedPath() : '\nPath: all categories in this analytics scope');
      count.textContent = rows.length + ' matching records · ' + (rows.length ? start + 1 : 0) + '–' + Math.min(start + 25, rows.length);
      body.replaceChildren();
      for (const record of rows.slice(start, start + 25)) {
        const row = make('tr');
        const cell = make('td');
        const link = make('a', record.name || '(Missing system name)');
        link.href = '#run/' + encodeURIComponent(ctx.run) + '/record/' + record.key;
        link.addEventListener('click', () => {
          dialog.close();
          document.querySelectorAll('.comparison-chart-dialog[open]').forEach(chart => chart.close());
        });
        cell.append(link, make('p', (record.application_id || '(blank ID)') + ' · Source row ' + record.source_row), make('p', record.status));
        const owners = make('td');
        for (const field of ['business_owner_email', 'technical_owner_email', 'vendor_owner']) {
          const value = valueText(record.owners?.[field]);
          if (field === 'vendor_owner' && !value && !recordFields(record).includes(field)) continue;
          const entry = make('p'); entry.append(make('strong', fieldLabel(field) + ': '), document.createTextNode(value || '(blank)')); owners.append(entry);
        }
        const columns = make('td', recordFields(record).map(fieldLabel).join('\n') || '—');
        const findings = make('td'), actions = make('td');
        for (const finding of record.findings) {
          const detail = make('div');
          detail.className = 'correction-queue-finding';
          detail.append(make('strong', finding.rule_id + ' · ' + finding.title), make('p', finding.message));
          const values = make('p', finding.fields.map(field => fieldLabel(field) + ': ' + (valueText(finding.values?.[field]) || '(blank)')).join('\n'));
          values.className = 'correction-queue-values'; detail.append(values); findings.append(detail);
          const action = make('div'); action.className = 'correction-queue-finding';
          action.append(make('strong', finding.rule_id), make('p', finding.fix)); actions.append(action);
        }
        if (!record.findings.length) {
          findings.append(make('p', 'No findings under the saved checks.'));
          actions.append(make('p', 'No current validation correction required.'));
        }
        row.append(cell, owners, columns, findings, actions); body.append(row);
      }
      previous.disabled = page === 0; next.disabled = start + 25 >= rows.length; download.disabled = !rows.length;
    }
    download.addEventListener('click', () => {
      const records = selectedRows(), stamp = new Date().toISOString();
      const rows = [['Source file', 'Review ID', 'Selection', 'Selected path', 'Analytics scope', 'Filters', 'Selected records', 'File baseline records',
        'Source row', 'AI System / Solution Name', 'Application / System ID', 'Validation', 'Business Owner', 'Technical Owner', 'Vendor Owner',
        'AI Inventory columns', 'Rule IDs', 'Submitted values', 'Findings', 'Required actions', 'Requirements', 'Exported UTC']];
      for (const record of records) rows.push([ctx.file, ctx.run, selection.label || chart.title, selectedPath(), ctx.scope, ctx.filters,
        records.length, state.data.run.total, record.source_row, record.name, record.application_id, record.status,
        ...['business_owner_email', 'technical_owner_email', 'vendor_owner'].map(field => valueText(record.owners?.[field])),
        recordFields(record).map(fieldLabel).join('; '), [...new Set(record.findings.map(finding => finding.rule_id))].join('; '), submittedValues(record),
        record.findings.map(finding => finding.rule_id + ': ' + finding.message).join('\n'),
        record.findings.map(finding => finding.rule_id + ': ' + finding.fix).join('\n') || 'No current validation correction required.',
        record.findings.map(finding => finding.rule_id + ': ' + finding.requirement).join('\n'), stamp]);
      save(new Blob(['\ufeff' + rows.map(row => row.map(csvCell).join(',')).join('\r\n')], {type: 'text/csv;charset=utf-8'}),
        'inventory-selected-records-' + stamp.replace(/[:.]/g, '-') + '.csv');
    });
    select.addEventListener('change', () => { page = 0; draw(); });
    previous.addEventListener('click', () => { page--; draw(); });
    next.addEventListener('click', () => { page++; draw(); });
    dialog.append(heading, scope, baseline, help, filters, count, scroll, controls);
    dialog.addEventListener('close', () => dialog.remove(), {once: true});
    document.body.append(dialog); draw(); dialog.showModal();
  }

  async function chartImage(charts, ctx, groups, stamp) {
    const canvas = make('canvas');
    const pen = canvas.getContext('2d');
    const width = 1200, margin = 48, gap = 24;
    const ink = '#172d42', muted = '#536779', line = '#dce5ee';
    const commands = [];
    const font = (size, bold = false) => (bold ? '600 ' : '') + size + 'px Arial, sans-serif';
    function lines(value, maxWidth, size, bold = false) {
      pen.font = font(size, bold);
      const result = [];
      let current = '';
      for (const word of String(value).split(/\s+/)) {
        if (current && pen.measureText(current + ' ' + word).width > maxWidth) {
          result.push(current); current = '';
        }
        // File names and category labels can contain long, unbroken text.
        for (const character of (current ? ' ' : '') + word) {
          if (current && pen.measureText(current + character).width > maxWidth) {
            result.push(current); current = '';
          }
          current += character;
        }
      }
      if (current) result.push(current);
      return result;
    }
    function text(value, x, y, maxWidth, size = 18, color = ink, bold = false) {
      const wrapped = lines(value, maxWidth, size, bold);
      commands.push(() => {
        pen.font = font(size, bold); pen.fillStyle = color; pen.textBaseline = 'top';
        wrapped.forEach((value, index) => pen.fillText(value, x, y + index * (size + 7)));
      });
      return y + wrapped.length * (size + 7);
    }
    function rect(x, y, w, h, color, radius = 0, border = '') {
      return () => {
        pen.beginPath(); pen.roundRect(x, y, w, h, radius);
        pen.fillStyle = color; pen.fill();
        if (border) { pen.lineWidth = 1; pen.strokeStyle = border; pen.stroke(); }
      };
    }
    const comparison = ctx.comparison;
    const chartTitle = chart => chartState.data.charts.find(item => item.id === chart.id)?.title || chart.title;
    const heading = comparison
      ? comparison.breakdown_title + ' by ' + comparison.group_title : chartTitle(charts[0]);
    const path = comparison?.path || charts[0].path || [];
    let y = 42;
    y = text('AI INVENTORY  /  CHART ANALYSIS', margin, y, 1000, 14, '#23727d', true) + 12;
    y = text(heading, margin, y, width - margin * 2, 34, ink, true) + 12;
    if (path.length) y = text(path.map(item => item.title + ': ' + item.value).join('  /  '),
      margin, y, width - margin * 2, 17, muted) + 10;
    const total = comparison?.total_records ?? charts[0].denominator;
    const scope = ctx.filters === 'Entire file' ? 'Entire file' : 'Current filters · all pages';
    y = text(recordCount(total) + '  ·  ' + scope, margin, y, width - margin * 2, 18, ink, true) + 6;
    y = text('Source: ' + ctx.file, margin, y, width - margin * 2, 16, muted) + 24;
    const columns = charts.length > 1 ? 2 : 1;
    const cardWidth = (width - margin * 2 - gap * (columns - 1)) / columns;
    for (let start = 0; start < charts.length; start += columns) {
      const rowTop = y;
      let bottom = rowTop;
      for (let offset = 0; offset < columns && start + offset < charts.length; offset++) {
        const index = start + offset, chart = charts[index];
        const x = margin + offset * (cardWidth + gap), padding = 26;
        const left = x + padding, innerWidth = cardWidth - padding * 2;
        const backgroundIndex = commands.length;
        commands.push(null);
        let top = rowTop + padding;
        top = text(groups[index]?.label || chartTitle(chart), left, top, innerWidth, 23, ink, true) + 7;
        top = text(recordCount(chart.denominator) + ' · ' + (chart.percent_label || (chart.path?.length ? '% within group' : '% of records')) +
          (chart.percentage_denominator != null ? ' (base: ' + chart.percentage_denominator + ' records)' : ''),
          left, top, innerWidth, 15, muted) + 24;
        const entries = chart.buckets.filter(bucket => bucket.count > 0);
        const donut = columns === 1 && chart.kind === 'pie' && !chart.multi && entries.length > 0;
        const plotTop = top;
        let labelX = left, labelWidth = innerWidth;
        if (donut) {
          const cx = left + 152, cy = plotTop + 155, radius = 118;
          labelX = left + 350; labelWidth = innerWidth - 350;
          commands.push(() => {
            let angle = -Math.PI / 2;
            for (const bucket of entries) {
              const next = angle + bucket.count / chart.denominator * Math.PI * 2;
              pen.beginPath(); pen.arc(cx, cy, radius, angle, next);
              pen.lineWidth = 44; pen.strokeStyle = chartColor(chart, bucket); pen.stroke();
              angle = next;
            }
            pen.textAlign = 'center'; pen.textBaseline = 'middle'; pen.fillStyle = ink;
            pen.font = font(42, true); pen.fillText(chart.denominator.toLocaleString(), cx, cy - 10);
            pen.font = font(16); pen.fillStyle = muted; pen.fillText('records', cx, cy + 29);
            pen.textAlign = 'left';
          });
        }
        for (const bucket of entries) {
          const color = chartColor(chart, bucket);
          const labelTop = top;
          const labelEnd = text(bucket.label, labelX + 18, top, labelWidth - 150, 17, ink);
          commands.push(rect(labelX, labelTop + 4, 9, 13, color, 3));
          commands.push(() => {
            pen.textAlign = 'right'; pen.textBaseline = 'top';
            pen.font = font(17, true); pen.fillStyle = ink;
            pen.fillText(bucket.count.toLocaleString(), labelX + labelWidth - 73, labelTop);
            pen.font = font(16); pen.fillStyle = muted;
            pen.fillText(percentLabel(bucket.percent), labelX + labelWidth, labelTop);
            pen.textAlign = 'left';
          });
          top = labelEnd + 8;
          if (!donut) {
            commands.push(rect(labelX + 18, top, labelWidth - 18, 9, '#edf2f7', 4));
            commands.push(rect(labelX + 18, top, (labelWidth - 18) * Math.min(1, bucket.percent / 100), 9, color, 4));
            top += 22;
          } else {
            commands.push(rect(labelX, top, labelWidth, 1, '#edf2f7'));
            top += 16;
          }
        }
        if (!entries.length) top = text('No categories in this view.', left, top, innerWidth, 18, muted) + 20;
        if (donut) top = Math.max(top, plotTop + 310);
        top += 10;
        commands.push(rect(left, top, innerWidth, 1, line));
        top += 16;
        top = text(chart.valid_records + ' categorized · ' + chart.missing_records + ' missing · ' +
          chart.invalid_records + ' invalid · ' + (chart.unclassified_records || 0) + ' unclassified',
          left, top, innerWidth, 14, muted);
        if (chart.multi) top = text('Multiple selections; category percentages may total more than 100%.',
          left, top + 7, innerWidth, 14, muted);
        top += padding;
        commands[backgroundIndex] = rect(x, rowTop, cardWidth, top - rowTop, '#ffffff', 12, line);
        bottom = Math.max(bottom, top);
      }
      y = bottom + gap;
    }
    if (comparison?.group_multi) y = text('A record can belong to multiple groups. Group counts may exceed the total.',
      margin, y, width - margin * 2, 15, muted) + 10;
    const notes = [...new Set([comparison?.group_note, ...charts.map(chart => chart.note)].filter(Boolean))];
    for (const note of notes) y = text(note, margin, y, width - margin * 2, 14, muted) + 10;
    y += 12;
    commands.push(rect(margin, y, width - margin * 2, 1, line));
    y = text('AI Governance Team · Exported ' + stamp.slice(0, 16).replace('T', ' ') + ' UTC',
      margin, y + 17, width - margin * 2, 13, muted) + 28;
    if (y > 7000) throw new Error('This view is too large for one image. Choose a category to export, or download the CSV.');
    canvas.width = width * 2; canvas.height = Math.ceil(y) * 2;
    pen.scale(2, 2); pen.fillStyle = '#f3f6fa'; pen.fillRect(0, 0, width, y);
    pen.fillStyle = '#23727d'; pen.fillRect(0, 0, width, 6);
    for (const draw of commands) draw();
    const blob = await new Promise(resolve => canvas.toBlob(resolve, 'image/png'));
    if (!blob) throw new Error('Unable to create the image. Try an individual category.');
    return blob;
  }

  function toolbar(charts, ctx, groups = []) {
    const box = make('div');

    box.className = 'actions';
    box.style.marginTop = '16px';

    const message = make('span');
    message.setAttribute('role', 'status');

    const stamp = new Date().toISOString();

    const title = charts.length === 1
      ? charts[0].title
      : 'comparison';

    const stem = (
      ctx.file.replace(/\.[^.]+$/, '') +
      '-' + title
    )
      .replace(/[^a-z0-9_-]+/gi, '-')
      .slice(0, 120) +
      '-' + stamp.replace(/[:.]/g, '-');

    function action(text, callback) {
      const button = make('button', text);
      button.type = 'button';

      button.addEventListener('click', async () => {
        button.disabled = true;
        message.textContent = '';

        try {
          await callback();
        } catch (error) {
          message.textContent = error.message;
        } finally {
          button.disabled = false;
        }
      });

      box.append(button);
    }

    action('Download summary (CSV)', () => {
      const rows = [[
        'Source file',
        'Review ID',
        'Scope',
        'Filters',
        'Chart',
        'Group path',
        'Group',
        'Category',
        'Count',
        'Percent',
        'Denominator',
        'Percentage basis',
        'Multiple selections',
        'Exported UTC'
      ]];

      charts.forEach((chart, index) => {
        for (const bucket of chart.buckets) {
          rows.push([
            ctx.file,
            ctx.run,
            ctx.scope,
            ctx.filters,
            chart.title,
            (chart.path || []).map(item => item.title + ': ' + item.value).join(' / '),
            groups[index]?.label || '',
            bucket.label,
            bucket.count,
            bucket.percent,
            chart.percentage_denominator ?? chart.denominator,
            chart.percent_label || '% of records',
            chart.multi
              ? 'Yes; percentages may exceed 100%'
              : 'No',
            stamp
          ]);
        }
      });

      const csv = '\ufeff' + rows
        .map(row => row.map(csvCell).join(','))
        .join('\r\n');

      save(
        new Blob(
          [csv],
          {type: 'text/csv;charset=utf-8'}
        ),
        stem + '.csv'
      );
    });

    action('Download chart (PNG)', async () => {
      save(await chartImage(charts, ctx, groups, stamp), stem + '.png');
    });

    if (charts.length === 1) {
      action('View underlying records', () => {
        if (!ctx.records) {
          throw new Error(
            'Underlying records are unavailable. Refresh the review and try again.'
          );
        }

        showRecords(ctx, charts[0], groups[0]);
      });
    }

    box.append(message);

    return box;
  }

  renderChart = function(chart) {
    const card = originalChart(chart);
    const ctx = context();
    ctx.comparison = null;
    card.append(toolbar([chart], ctx));
    return card;
  };

  return {
    downloadDrilldown(model) {
      save(new Blob([comparisonExport.csv(model)], {type: 'text/csv;charset=utf-8'}),
        'inventory-drilldown-' + model.stamp.replace(/[:.]/g, '-') + '.csv');
    },
    async downloadSlide(model) {
      save(await comparisonExport.png(model),
        'inventory-drilldown-' + model.levels.length + '-levels-' + model.stamp.replace(/[:.]/g, '-') + '.png');
    },
    records(chart, category = '') {
      showRecords(context(), chart, undefined, category);
    },
    recordsByKeys(chart, keys, title, selection = {}) {
      const ctx = context();
      const selected = new Set(keys);
      ctx.records = ctx.records.filter(record => selected.has(record.key));
      showRecords(ctx, {...chart, title: title || chart.title}, undefined, '', {...selection, fixed: true, label: title || chart.title});
    },
  };
})();
