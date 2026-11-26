  function actionLink(url, label, cls = 'btn btn-sm') { return `<a class="${cls}" href="${url}">${esc(label)}</a>`; }
  function activeToggleAction(resource, id, active = true) {
    const label = active === false ? 'Activate' : 'Deactivate';
    return `<button type="button" class="btn btn-sm" data-toggle-resource-active="${esc(resource)}" data-toggle-id="${esc(id)}" style="${active === false ? 'color:#176b50' : 'color:#b12c44'}">${label}</button>`;
  }
  function rowActions(resource, id, editHref, viewHref = null, viewLabel = 'View', active = true) {
    if (currentUser.role === 'admin') {
      const canToggle = !['users', 'customers', 'audit-logs', 'role-permissions'].includes(resource);
      return `${viewHref ? actionLink(viewHref, viewLabel) : ''} ${editHref ? actionLink(editHref, 'Edit') : ''} ${canToggle ? activeToggleAction(resource, id, active) : ''}`;
    }
    if (viewHref) return actionLink(viewHref, viewLabel);
    return '';
  }
  function ticketHref(row) { return `${currentUser.role === 'customer' ? 'user-ticket-detail.html' : 'ticket-detail.html'}?id=${encodeURIComponent(row.ticket_id)}`; }
  function cellFor(resource, row, header, page) {
    const h = header.toLowerCase().replace(/\s+/g, ' ').trim();
    if (resource === 'tickets') {
      if (h.includes('ticket')) return `<a class="ticket-id" href="${ticketHref(row)}">${esc(row.ticket_code || ('TKT-' + row.ticket_id))}</a>`;
      if (h.includes('customer') && h.includes('project')) return `${esc(row.customer_name)}${row.project_name && row.project_name !== '—' ? `<span class="sub-cell">${esc(row.project_name)}</span>` : ''}`;
      if (h === 'contract' || h.includes('contract / plan') || h.includes('contract /')) return `${esc(row.contract_code || row.contract_name || '—')}${row.plan_name && row.plan_name !== '—' ? `<span class="sub-cell">${esc(row.plan_name)}</span>` : ''}`;
      if (h.includes('request type')) return esc(row.service_name || row.type || '—');
      if (h.includes('subject')) return `<a class="ticket-id" href="${ticketHref(row)}">${esc(row.subject)}</a>`;
      if (h.includes('status')) return badge(row.status);
      if (h.includes('priority')) return badge(row.priority);
      if (h.includes('asset')) return esc(row.asset_tag || '—');
      if (h.includes('support team')) return esc(row.team_name || '—');
      if (h.includes('assigned')) return esc(row.assigned || (currentUser?.role === 'customer' ? 'Service Desk' : 'Unassigned'));
      if (h.includes('created') || h.includes('last updated') || h.includes('updated')) return fmtDate(h.includes('updated') && !h.includes('created') ? row.updated_at : row.date);
      if (h === 'action' || h === 'actions') return currentUser.role === 'admin' ? `${actionLink(ticketHref(row), 'View')} ${actionLink(`add-ticket.html?id=${encodeURIComponent(row.ticket_id)}`, 'Edit')} ${activeToggleAction('tickets', row.ticket_id, row.active)}` : rowActions('tickets', row.ticket_id, null, ticketHref(row), 'View', row.active);
    }
    if (resource === 'projects') {
      if (h.includes('customer')) return esc(row.customer_name);
      if (h.includes('project code')) return esc(row.project_code || row.project_id);
      if (h.includes('project name')) return currentUser.role === 'admin' ? actionLink(`add-project.html?id=${row.project_id}`, row.project_name, 'ticket-id') : esc(row.project_name);
      if (h.includes('manager')) return esc(row.project_manager || '—');
      if (h.includes('status')) return badge(row.status);
      if (h.includes('start date')) return fmtDate(row.start_date);
      if (h.includes('end date')) return fmtDate(row.end_date);
      if (h.includes('action')) return rowActions('projects', row.project_id, `add-project.html?id=${row.project_id}`, null, 'View', row.active);
    }
    if (resource === 'customers') {
      if (h.includes('company')) return actionLink(`customer-detail.html?id=${row.customer_id}`, row.customer_name, 'ticket-id');
      if (h.includes('primary contact')) return esc(row.contact_name || '—');
      if (h === 'projects') return esc(row.projects_count ?? 0);
      if (h === 'contracts') return esc(row.contracts_count ?? 0);
      if (h.includes('tickets')) return esc(row.tickets_count ?? 0);
      if (h.includes('status')) return badge(row.active === false ? 'Deactivated' : 'Active');
      if (h.includes('action')) return currentUser.role === 'admin' ? `${rowActions('customers', row.customer_id, `add-customer.html?id=${row.customer_id}&edit_customer=1`, `customer-detail.html?id=${row.customer_id}`, 'View', row.active)} <button type="button" class="btn btn-sm" data-toggle-customer-active="${esc(row.customer_id)}">${row.active === false ? 'Activate' : 'Deactivate'}</button>` : rowActions('customers', row.customer_id, null, `customer-detail.html?id=${row.customer_id}`, 'View');
    }
    if (resource === 'contacts') {
      if (h.includes('customer')) return esc(row.customer_name);
      if (h.includes('contact no')) return esc(row.contact_code || ('CON-' + row.contact_id));
      if (h.includes('contact name')) return esc(row.fullname);
      if (h.includes('department')) return esc(row.department || '—');
      if (h.includes('job title')) return esc(row.job_title || '—');
      if (h === 'email') return esc(row.email || '—');
      if (h === 'phone') return esc(row.phone || '—');
      if (h === 'type') return badge(row.type || 'General');
      if (h.includes('action')) return rowActions('contacts', row.contact_id, `add-contact.html?id=${row.contact_id}`, null, 'View', row.active);
    }
    if (resource === 'contracts') {
      if (h.includes('customer')) return esc(row.customer_name);
      if (h.includes('project')) return esc(row.project_name);
      if (h.includes('contract no')) return esc(row.contract_code || ('CON-' + row.contract_id));
      if (h.includes('contract name')) return esc(row.contract_name);
      if (h.includes('support plan')) return esc(row.plan_name || '—');
      if (h.includes('start date')) return fmtDate(row.start_date);
      if (h.includes('end date')) return fmtDate(row.end_date);
      if (h.includes('action')) return rowActions('contracts', row.contract_id, `add-contract.html?id=${row.contract_id}`, null, 'View', row.active);
    }
    if (resource === 'plans') {
      if (h.includes('action')) return rowActions('plans', row.plan_id, `add-support-plan.html?id=${row.plan_id}`, null, 'View', row.active);
      const mappings = [['plan code', row.plan_code || ('PLAN-' + row.plan_id)], ['plan type', row.plan_type || 'Standard'], ['plan name', row.plan_name], ['response sla', row.response_sla], ['rsponse sla', row.response_sla], ['resolution sla', row.resolution_sla], ['reslution sla', row.resolution_sla], ['response warning', row.response_warning], ['reslution warning', row.resolution_warning], ['response critical', row.response_critical], ['reslution critical', row.resolution_critical], ['calendar mode', row.sla_mode], ['calender mode', row.sla_mode], ['time zone', row.time_zone], ['business start', row.business_start_hour], ['business end', row.business_end_hour], ['working days', row.working_days], ['escalation level', row.escalation_level], ['remote support', row.remote_support], ['on-site support', row.onsite_support]];
      const found = mappings.find(([key]) => h.includes(key)); if (found) return esc(found[1] ?? '—');
    }
    if (resource === 'services') {
      if (h === 'code') return esc(row.code_id);
      if (h === 'name') return esc(row.name);
      if (h.includes('category')) return esc(row.category || '—');
      if (h.includes('sort order')) return esc(row.request_order);
      if (h.includes('customer visible')) return badge(row.customer_visible ? 'Yes' : 'No');
      if (h.includes('asset requirement')) return esc(row.asset_requirement || '—');
      if (h.includes('mapped team')) return esc(row.mapped_team || '—');
      if (h.includes('auto assign')) return badge(row.auto_assign ? 'Enabled' : 'Disabled');
      if (h.includes('assignment method') || h.includes('assigenment method') || h.includes('assignement method')) return esc(row.assignment_method || '—');
      if (h.includes('action')) return rowActions('services', row.code_id, `add-service.html?id=${encodeURIComponent(row.code_id)}`, null, 'View', row.active);
    }
    if (resource === 'teams') {
      if (h.includes('team code')) return esc(row.team_code || ('TEAM-' + row.team_id));
      if (h.includes('team name')) return esc(row.team_name);
      if (h.includes('team members')) return esc(row.member || '—');
      if (h.includes('service catalog')) return esc(row.service_names || row.service_name || '—');
      if (h.includes('action')) return rowActions('teams', row.team_id, `add-team.html?id=${row.team_id}`, null, 'View', row.active);
    }
    if (resource === 'assets') {
      if (h === 'customers' || h === 'customer') return esc(row.customer_name || '—');
      if (h === 'project') return esc(row.project_name || '—');
      if (h.includes('asset tag')) return currentUser?.role === 'customer' ? esc(row.asset_tag) : actionLink(`asset-detail.html?id=${row.asset_id}`, row.asset_tag, 'ticket-id');
      if (h.includes('asset name')) return esc(row.asset_name);
      if (h === 'type') return esc(row.type || '—');
      if (h.includes('status')) return badge(row.status);
      if (h.includes('service catalog')) return esc(row.service_names || '—');
      if (h === 'vendor') return esc(row.vendor || '—');
      if (h === 'model') return esc(row.model || '—');
      if (h.includes('serial')) return esc(row.serial_no || '—');
      if (h.includes('ip address')) return esc(row.ip_address || '—');
      if (h.includes('assigned to')) return esc(row.assigned_to || currentUser.fullname);
      if (h.includes('action')) return rowActions('assets', row.asset_id, `add-asset.html?id=${row.asset_id}`, `asset-detail.html?id=${row.asset_id}`, 'View', row.active);
    }
    if (resource === 'users') {
      if (h.includes('fullname') || h === 'full name') return esc(row.fullname);
      if (h === 'email') return esc(row.email);
      if (h === 'password') return '••••••••';
      if (h === 'role') return badge(({ admin: 'Admin', agent: 'Agent', customer: 'Customer' })[String(row.role || '').toLowerCase()] || row.role);
      if (h.includes('status') || h.includes('account')) return badge(row.role === 'customer' && row.customer_active === false ? 'Deactivated' : (row.active === false ? 'Deactivated' : 'Active'));
      if (h.includes('request type')) return esc(row.request_type_name || '—');
      if (h.includes('support team')) return esc(row.team_name || '—');
      if (h.includes('action')) return `${rowActions('users', row.user_id, `add-user.html?id=${row.user_id}`, null)} ${row.role === 'admin' ? (Number(row.user_id) === Number(currentUser?.user_id) ? '<button type="button" class="btn btn-sm" disabled title="You cannot deactivate your own Admin account">Current account</button>' : `<button type="button" class="btn btn-sm" data-toggle-admin-active="${esc(row.user_id)}">${row.active === false ? 'Activate' : 'Deactivate'}</button>`) : row.role === 'customer' ? `${row.customer_id ? `<button type="button" class="btn btn-sm" data-toggle-customer-active="${esc(row.customer_id)}">${row.customer_active === false ? 'Activate' : 'Deactivate'}</button>` : ''} <button type="button" class="btn btn-sm" data-reset-customer-password="${esc(row.user_id)}">Reset password</button>` : row.role === 'agent' ? `<button type="button" class="btn btn-sm" data-toggle-agent-active="${esc(row.user_id)}">${row.active === false ? 'Activate' : 'Deactivate'}</button> <button type="button" class="btn btn-sm" data-reset-customer-password="${esc(row.user_id)}">Reset password</button>` : ''}`;
    }
    if (resource === 'audit-logs') {
      if (h.includes('timestamp') || h === 'date') return `<span class="audit-date">${esc(row.created_at ? new Date(row.created_at).toLocaleString() : '—')}</span>`;
      if (h === 'customer' || h === 'user' || h === 'user name') return `<div class="audit-user"><strong>${esc(row.user_name || 'System')}</strong><span class="sub-cell">${esc(row.actor_role || 'system')}</span></div>`;
      if (h === 'action') return `<span class="audit-action-pill">${esc(row.action || '—')}</span>`;
      if (h === 'module' || h === 'entity') return `<div class="audit-entity">${esc(row.module || '—')}<span class="sub-cell">${esc(row.entity_label || row.entity_id || '')}</span></div>`;
      if (h === 'record' || h === 'summary' || h.includes('summary')) return `<div class="audit-summary">${esc(row.details || '—')}</div>`;
      if (h === 'ip' || h.includes('ip address')) return esc(row.ip_address || '—');
      if (h === 'result') return badge(row.action === 'LOGIN_FAILED' || row.action === 'EMAIL_FAILED' || row.action === 'PASSWORD_RESET_EMAIL_FAILED' ? 'Failed' : row.action === 'EMAIL_SKIPPED' ? 'Skipped' : 'Success');
      if (h === 'details' || h === 'details / changes') return `<button type="button" class="btn btn-sm audit-detail-trigger" data-audit-view="${esc(row.audit_id)}">View Details / Changes</button>`;
    }
    return '—';
  }
  function renderTable(resource, rows, table, page = file) {
    if (!table) return;
    const tbody = table.querySelector('tbody'); if (!tbody) return;
    const headerCells = [...table.querySelectorAll('thead th')];
    let headers = headerCells.map(th => th.textContent.replace(/\s+/g, ' ').trim());
    if (currentUser?.role === 'agent' && !['tickets', 'customers', 'assets'].includes(resource)) {
      const actionIndex = headers.findIndex(h => /^actions?$/i.test(h));
      if (actionIndex >= 0) {
        headerCells[actionIndex].remove();
        table.querySelectorAll('tbody tr').forEach(tr => tr.children[actionIndex]?.remove());
        headers.splice(actionIndex, 1);
      }
    }
    if (!headers.length) return;
    tbody.replaceChildren();
    if (!rows.length) { const tr = document.createElement('tr'); const td = document.createElement('td'); td.colSpan = headers.length; td.className = 'empty-data'; td.textContent = 'No records found in the database yet.'; td.style.padding = '22px'; td.style.textAlign = 'center'; td.style.color = '#7b8497'; tr.appendChild(td); tbody.appendChild(tr); return; }
    const appendRow = row => {
      const tr = document.createElement('tr');
      const primaryKey = ({ tickets: 'ticket_id', customers: 'customer_id', contacts: 'contact_id', projects: 'project_id', users: 'user_id', teams: 'team_id', services: 'code_id', plans: 'plan_id', contracts: 'contract_id', assets: 'asset_id' })[resource];
      if (primaryKey && row[primaryKey] !== undefined) tr.dataset.gpRowId = String(row[primaryKey]);
      headers.forEach(header => {
        const td = document.createElement('td');
        const normalized = header.toLowerCase().replace(/\s+/g, ' ').trim();
        if (resource === 'plans' && normalized.includes('action') && currentUser?.role === 'admin') {
          const edit = document.createElement('a'); edit.className = 'btn btn-sm'; edit.href = `add-support-plan.html?id=${encodeURIComponent(row.plan_id)}`; edit.textContent = 'Edit';
          const toggle = document.createElement('button'); toggle.type = 'button'; toggle.className = 'btn btn-sm'; toggle.dataset.toggleResourceActive = 'plans'; toggle.dataset.toggleId = String(row.plan_id); toggle.style.color = row.active === false ? '#176b50' : '#b12c44'; toggle.style.marginLeft = '6px'; toggle.textContent = row.active === false ? 'Activate' : 'Deactivate';
          td.append(edit, toggle);
        } else td.innerHTML = cellFor(resource, row, header, page);
        tr.appendChild(td);
      });
      tbody.appendChild(tr);
    };
    if (resource === 'users') {
      const groups = [['admin', 'Administrators'], ['agent', 'Agents'], ['customer', 'Customers']];
      groups.forEach(([role, title]) => {
        const groupRows = rows.filter(row => String(row.role || '').toLowerCase() === role);
        if (!groupRows.length) return;
        const totalForRole = (loadedRows.users || []).filter(row => String(row.role || '').toLowerCase() === role).length;
        const heading = document.createElement('tr'); heading.className = 'gp-user-role-heading';
        const cell = document.createElement('td'); cell.colSpan = headers.length;
        cell.innerHTML = `<strong>${title}</strong><span>${totalForRole} account${totalForRole === 1 ? '' : 's'} · ${groupRows.length} shown on this page</span>`;
        heading.appendChild(cell); tbody.appendChild(heading);
        groupRows.forEach(appendRow);
      });
    } else rows.forEach(appendRow);
    const foot = table.closest('.card')?.querySelector('.table-foot');
    if (foot) { const span = foot.querySelector('span'); if (span) span.textContent = `Showing ${rows.length} record${rows.length === 1 ? '' : 's'}`; const pagination = foot.querySelector('.pagination'); if (pagination) pagination.innerHTML = ''; }
  }
  function chooseTable(resource) {
    const tables = [...document.querySelectorAll('table')];
    return tables.find(t => { const text = t.querySelector('thead')?.textContent.toLowerCase() || ''; return resource === 'tickets' ? text.includes('ticket') : resource === 'assets' ? text.includes('asset') : resource === 'services' ? text.includes('code') || text.includes('service') : resource === 'audit-logs' ? (text.includes('timestamp') || (text.includes('date') && text.includes('user'))) : resource === 'users' ? text.includes('fullname') : resource === 'projects' ? text.includes('project code') : resource === 'customers' ? text.includes('company') : resource === 'contacts' ? text.includes('contact no') : resource === 'contracts' ? text.includes('contract no') : resource === 'plans' ? text.includes('plan code') : resource === 'teams' ? text.includes('team code') : false; }) || tables[0];
  }
  async function loadList(resource = pageResource[file]) {
    if (!resource) return;
    const table = chooseTable(resource);
    // Clear every table body before fetching, not only the detected primary table.
    // This prevents leftover prototype/sample rows from surviving navigation or refresh.
    document.querySelectorAll('.table-wrap table tbody').forEach(tbody => tbody.replaceChildren());
    if (table?.querySelector('tbody')) table.querySelector('tbody').replaceChildren();
    const tableCard = table?.closest('section.card') || table?.closest('.card');
    const footerLabel = tableCard?.querySelector('.table-foot span');
    const pagination = tableCard?.querySelector('.table-foot .pagination');
    if (pagination) pagination.remove(); // The old static page numbers were prototype-only.
    try {
      const rows = await api(`/api/${resource}`); loadedRows[resource] = rows;
      if (table) renderTable(resource, rows, table, file);
      if (footerLabel) footerLabel.textContent = `Showing ${rows.length} ${rows.length === 1 ? 'record' : 'records'}`;
      if (resource === 'services' && file === 'user-service-catalog.html') renderCustomerServiceCards(rows);
      if (resource === 'assets' && file === 'user-assets.html') renderUserAssets(rows);
      return rows;
    } catch (e) {
      loadedRows[resource] = [];
      if (table) renderTable(resource, [], table, file);
      if (footerLabel) footerLabel.textContent = 'Showing 0 records';
      if (e.status === 403) toast(e.message, 'error'); else if (e.status !== 404) toast(e.message, 'error');
    }
  }
  let customerServicePage = 1;
  function renderCustomerServiceCards(rows, requestedPage = 1) {
    const grid = document.querySelector('.three-col'); if (!grid) return;
    const pageSize = 10;
    const totalPages = Math.max(1, Math.ceil(rows.length / pageSize));
    customerServicePage = Math.min(Math.max(1, requestedPage), totalPages);
    const start = (customerServicePage - 1) * pageSize;
    const pageRows = rows.slice(start, start + pageSize);
    grid.replaceChildren();
    const icons = ['⌘', '◇', '⇄', '▧', '♧', '✉'];
    pageRows.forEach((r, i) => {
      const card = document.createElement('section'); card.className = 'card';
      card.innerHTML = `<div class="card-body"><div class="stat-icon" style="margin-bottom:12px">${icons[(start + i) % icons.length]}</div><h2 style="font-size:14px;margin:0 0 6px">${esc(r.name)}</h2><p class="subtitle" style="min-height:35px">${esc(r.description || r.category || 'Request support for this service.')}</p><div style="margin-top:16px"><a class="btn btn-primary btn-sm" href="user-create-ticket.html?service=${encodeURIComponent(r.name)}">Request service →</a></div></div>`;
      grid.appendChild(card);
    });
    if (!rows.length) grid.innerHTML = '<p class="notice">There are no customer-visible services configured yet.</p>';
    let foot = document.getElementById('customer-service-pagination');
    if (!foot) { foot = document.createElement('div'); foot.id = 'customer-service-pagination'; foot.className = 'table-foot'; grid.insertAdjacentElement('afterend', foot); }
    foot.replaceChildren();
    const info = document.createElement('span'); info.textContent = `Showing ${rows.length ? start + 1 : 0}–${Math.min(start + pageSize, rows.length)} of ${rows.length} services`; foot.appendChild(info);
    const buttons = document.createElement('div'); buttons.className = 'gp-ticket-page-buttons'; foot.appendChild(buttons);
    const makeButton = (label, target, current = false, disabled = false) => {
      const button = document.createElement('button'); button.type = 'button'; button.className = 'gp-ticket-page-btn'; button.textContent = label;
      if (current) { button.classList.add('is-current'); button.setAttribute('aria-current', 'page'); }
      button.disabled = disabled;
      button.addEventListener('click', () => renderCustomerServiceCards(rows, target));
      buttons.appendChild(button);
    };
    makeButton('Previous', customerServicePage - 1, false, customerServicePage <= 1);
    for (let page = 1; page <= totalPages; page++) {
      if (totalPages > 7 && page !== 1 && page !== totalPages && Math.abs(page - customerServicePage) > 1) {
        if (page === 2 || page === totalPages - 1) { const dots = document.createElement('span'); dots.className = 'gp-ticket-page-dots'; dots.textContent = '…'; buttons.appendChild(dots); }
        continue;
      }
      makeButton(String(page), page, page === customerServicePage);
    }
    makeButton('Next', customerServicePage + 1, false, customerServicePage >= totalPages);
  }
  function renderUserAssets(rows) {
    const table = chooseTable('assets'); if (!table) return;
    const tbody = table.querySelector('tbody'); if (!tbody) return;
    tbody.replaceChildren();
    rows.forEach(r => { const tr = document.createElement('tr'); tr.innerHTML = `<td><span class="ticket-id">${esc(r.asset_tag)}</span></td><td>${esc(r.asset_name)}</td><td>${esc(r.type || '—')}</td><td>${esc(currentUser.fullname)}</td><td>${badge(r.status)}</td>`; tbody.appendChild(tr); });
    if (!rows.length) tbody.innerHTML = '<tr><td colspan="5" style="padding:22px;text-align:center;color:#7b8497">No assets are linked to your account.</td></tr>';
  }
  function updateDashboard(stats) {
    if (!stats) return;
    document.querySelectorAll('.stat').forEach(card => {
      const label = (card.querySelector('.stat-top')?.textContent || '').toLowerCase();
      const strong = card.querySelector('strong'); if (!strong) return;
      if (label.includes('sla at risk')) strong.textContent = stats.sla_at_risk ?? 0;
      else if (label.includes('assigned to me')) strong.textContent = stats.assigned_to_me ?? 0;
      else if (label.includes('available service')) strong.textContent = stats.available_services ?? 0;
      else if (label.includes('my open') || label.includes('open ticket')) strong.textContent = stats.open_tickets ?? 0;
      else if (label.includes('waiting')) strong.textContent = stats.waiting ?? 0;
      else if (label.includes('resolved')) strong.textContent = stats.resolved ?? 0;
      else if (label.includes('user')) strong.textContent = stats.users ?? 0;
      else if (label === 'projects') strong.textContent = stats.projects ?? 0;
      else if (label.includes('asset')) strong.textContent = stats.assets ?? 0;
      else if (label.includes('contract')) strong.textContent = stats.contracts ?? 0;
      else if (label.includes('ticket')) strong.textContent = stats.tickets_total ?? 0;
    });
    const refreshed = document.querySelector('[data-dashboard-refreshed]');
    if (refreshed) refreshed.textContent = `Live data · Updated ${new Date(stats.refreshed_at || Date.now()).toLocaleTimeString()}`;
    renderDashboardStatusChart(stats.monthly_breakdown || []);
    renderDashboardModuleOverview(stats.module_overview || []);
    renderDashboardOverview('[data-dashboard-agent-overview]', stats.agents_overview || [], 'agent');
    renderDashboardOverview('[data-dashboard-customer-overview]', stats.customers_overview || [], 'customer');
  }
  function renderDashboardModuleOverview(rows) {
    const target = document.querySelector('[data-dashboard-module-chart]');
    if (!target) return;
    target.replaceChildren();
    const modules = Array.isArray(rows) ? rows : [];
    if (!modules.length) {
      const empty = document.createElement('p');
      empty.className = 'muted dashboard-empty';
      empty.textContent = 'No module data is available for this account.';
      target.appendChild(empty);
      return;
    }

    const maxTotal = Math.max(1, ...modules.map(row => Number(row.total) || 0));
    const pageByResource = {
      tickets: 'tickets.html', customers: 'customers.html', projects: 'projects.html',
      contracts: 'contracts.html', plans: 'support-plans.html', services: 'service-catalog.html',
      contacts: 'contacts.html', assets: 'assets.html'
    };

    modules.forEach(row => {
      const active = Math.max(0, Number(row.active) || 0);
      const inactive = Math.max(0, Number(row.inactive) || 0);
      const total = Math.max(0, Number(row.total) || active + inactive);
      const item = document.createElement('div');
      item.className = 'dashboard-module-row';

      const heading = document.createElement('div');
      heading.className = 'dashboard-module-heading';
      const link = document.createElement('a');
      link.href = pageByResource[row.resource] || '#';
      link.textContent = String(row.label || row.resource || 'Module');
      const counts = document.createElement('span');
      counts.className = 'dashboard-module-counts';
      counts.textContent = `${active} active · ${inactive} deactivated · ${total} total`;
      heading.append(link, counts);

      const track = document.createElement('div');
      track.className = 'dashboard-module-track';
      track.setAttribute('role', 'img');
      track.setAttribute('aria-label', `${row.label}: ${active} active, ${inactive} deactivated, ${total} total`);
      const activeBar = document.createElement('span');
      activeBar.className = 'dashboard-module-bar-active';
      activeBar.style.width = `${Math.max(0, Math.min(100, active / maxTotal * 100))}%`;
      const inactiveBar = document.createElement('span');
      inactiveBar.className = 'dashboard-module-bar-inactive';
      inactiveBar.style.width = `${Math.max(0, Math.min(100, inactive / maxTotal * 100))}%`;
      track.append(activeBar, inactiveBar);
      item.append(heading, track);
      target.appendChild(item);
    });
  }

  function renderDashboardStatusChart(monthlyRows) {
    const target = document.querySelector('[data-dashboard-status-chart]');
    if (!target) return;
    target.replaceChildren();

    const months = Array.isArray(monthlyRows) ? monthlyRows : [];
    const maxTotal = Math.max(1, ...months.map(month => Number(month.total) || 0));
    const series = [
      { key: 'Open', label: 'Open', className: 'open' },
      { key: 'In Progress', label: 'In Progress', className: 'progress' },
      { key: 'Pending Customer', label: 'Pending Customer', className: 'pending' },
      { key: 'Resolved', label: 'Resolved', className: 'resolved' },
      { key: 'Closed', label: 'Closed', className: 'closed' },
      { key: 'Other', label: 'Other', className: 'other' }
    ];

    if (!months.length) {
      const empty = document.createElement('p');
      empty.className = 'muted dashboard-empty';
      empty.textContent = 'No ticket data is available yet.';
      target.appendChild(empty);
      return;
    }

    const chart = document.createElement('div');
    chart.className = 'dashboard-daily-chart dashboard-monthly-chart';

    months.forEach(month => {
      const column = document.createElement('div');
      column.className = 'dashboard-day-column dashboard-month-column';

      const total = Number(month.total) || 0;
      const value = document.createElement('strong');
      value.className = 'dashboard-day-total';
      value.textContent = String(total);

      const stack = document.createElement('div');
      stack.className = 'dashboard-day-stack';
      stack.setAttribute('aria-label', `${month.label || month.date}: ${total} tickets created`);

      series.forEach(item => {
        const count = Number(month[item.key]) || 0;
        if (!count) return;
        const segment = document.createElement('div');
        segment.className = `dashboard-day-segment status-${item.className}`;
        segment.style.height = `${(count / maxTotal) * 150}px`;
        segment.title = `${item.label}: ${count}`;
        stack.appendChild(segment);
      });

      const label = document.createElement('span');
      label.className = 'dashboard-day-label';
      label.textContent = String(month.label || month.date || '—');
      label.title = String(month.date || '');
      column.append(value, stack, label);
      chart.appendChild(column);
    });
    target.appendChild(chart);

    const legend = document.createElement('div');
    legend.className = 'dashboard-chart-legend';
    series.forEach(item => {
      const count = months.reduce((sum, month) => sum + (Number(month[item.key]) || 0), 0);
      if (item.key === 'Other' && count === 0) return;
      const entry = document.createElement('span');
      entry.className = `dashboard-legend-item status-${item.className}`;
      const dot = document.createElement('i');
      dot.className = 'dashboard-legend-dot';
      const text = document.createElement('span');
      text.textContent = `${item.label}: ${count}`;
      entry.append(dot, text);
      legend.appendChild(entry);
    });
    target.appendChild(legend);

    const totalTickets = months.reduce((sum, month) => sum + (Number(month.total) || 0), 0);
    const summary = document.createElement('div');
    summary.className = 'dashboard-chart-summary';
    summary.textContent = `${totalTickets.toLocaleString()} tickets created in the last 12 months · Live database data`;
    target.appendChild(summary);
  }

  function renderDashboardOverview(selector, rows, kind) {
    const target = document.querySelector(selector);
    if (!target) return;
    target.replaceChildren();
    const safeRows = Array.isArray(rows) ? rows.slice(0, 8) : [];
    if (!safeRows.length) {
      const empty = document.createElement('p');
      empty.className = 'muted dashboard-empty';
      empty.textContent = kind === 'agent' ? 'No active agents found.' : 'No active customers found.';
      target.appendChild(empty);
      return;
    }
    safeRows.forEach(row => {
      const item = document.createElement('div');
      item.className = 'dashboard-overview-row';
      const identity = document.createElement('div');
      identity.className = 'dashboard-overview-identity';
      const name = document.createElement('strong');
      name.textContent = String(row.name || '—');
      const detail = document.createElement('small');
      detail.textContent = kind === 'agent' ? String(row.team || 'No support team') : `${Number(row.open_tickets) || 0} active tickets`;
      identity.append(name, detail);
      const total = document.createElement('div');
      total.className = 'dashboard-overview-number';
      const totalValue = document.createElement('strong');
      totalValue.textContent = String(Number(row.total_tickets) || 0);
      const totalLabel = document.createElement('small');
      totalLabel.textContent = 'Total';
      total.append(totalValue, totalLabel);
      const active = document.createElement('div');
      active.className = 'dashboard-overview-number';
      const activeValue = document.createElement('strong');
      activeValue.textContent = String(kind === 'agent' ? (Number(row.active_tickets) || 0) : (Number(row.open_tickets) || 0));
      const activeLabel = document.createElement('small');
      activeLabel.textContent = kind === 'agent' ? 'Active' : 'Open';
      active.append(activeValue, activeLabel);
      item.append(identity, total, active);
      target.appendChild(item);
    });
  }
  async function refreshDashboard() {
    try {
      const stats = await api('/api/dashboard/stats');
      updateDashboard(stats);
    } catch (e) {
      const status = document.querySelector('[data-dashboard-refreshed]');
      if (status) status.textContent = 'PostgreSQL data unavailable';
      const target = document.querySelector('[data-dashboard-module-chart]');
      if (target) {
        target.replaceChildren();
        const message = document.createElement('p');
        message.className = 'muted dashboard-empty';
        message.textContent = `Could not load live module data: ${e.message || 'Check the PostgreSQL connection and server log.'}`;
        target.appendChild(message);
      }
    }
  }
  function filterSpecs(resource) {
    const specs = {
      tickets: [['Ticket View', 'ticket_view'], ['Customer', 'customer_name'], ['Project', 'project_name'], ['Contract', 'contract_filter'], ['Status', 'status'], ['Priority', 'priority'], ['Request Type', 'service_name'], ['Support Team', 'team_name']],
      customers: [['Account Status', 'customer_active']],
      projects: [['Project Status', 'status'], ['Customer', 'customer_name']],
      contacts: [['Customer', 'customer_name'], ['Contact Type', 'type']],
      contracts: [['Customer', 'customer_name'], ['Contract Status', 'status'], ['Support Plan', 'plan_name']],
      plans: [['Calendar Mode', 'sla_mode'], ['Working Days', 'working_days']],
      services: [['Category', 'category'], ['Mapped Team', 'mapped_team'], ['Customer Visible', 'customer_visible'], ['Auto Assign', 'auto_assign']],
      teams: [['Service Catalog', 'service_names']],
      assets: [['Asset Status', 'status'], ['Customer', 'customer_name'], ['Project', 'project_name'], ['Asset Type', 'type'], ['Service Catalog', 'service_names']],
      users: [['Support Team', 'team_name'], ['Account Status', 'active']]
    };
    return specs[resource] || [];
  }
  const filterText = value => String(value ?? '').trim().toLowerCase().replace(/[_-]+/g, ' ').replace(/\s+/g, ' ');
  const filterFlag = value => {
    if (value === true || value === 1) return true;
    if (value === false || value === 0 || value == null) return false;
    return ['true', '1', 'yes', 'enabled', 'active'].includes(filterText(value));
  };
  function filterValue(row, key, resource) {
    if (key === 'customer_active' || key === 'active') return filterFlag(row.active) ? 'Active' : 'Deactivated';
    if (key === 'customer_visible') return filterFlag(row.customer_visible) ? 'Yes' : 'No';
    if (key === 'auto_assign') return filterFlag(row.auto_assign) ? 'Enabled' : 'Disabled';
    if (key === 'contract_filter') return row.contract_code || row.contract_name || '';
    if (resource === 'contracts' && key === 'status') return row.status || (filterFlag(row.active) ? 'Active' : 'Deactivated');
    return row[key] ?? '';
  }
  function applyRegisterFilters(resource, rows, values) {
    const query = filterText(values.search);
    const from = values.from || '', to = values.to || '';
    return rows.filter(row => {
      if (query && !filterText(JSON.stringify(row)).includes(query)) return false;
      for (const [key, value] of Object.entries(values)) {
        if (['search', 'from', 'to'].includes(key) || value == null || value === '') continue;
        const expected = filterText(value);
        if (key === 'ticket_view') {
          const assigned = filterText(row.assigned);
          const status = filterText(row.status);
          if (expected === 'my tickets' && assigned !== filterText(currentUser?.fullname)) return false;
          if (expected === 'unassigned' && assigned && assigned !== 'unassigned' && assigned !== '—') return false;
          if (expected === 'sla at risk') {
            if (!row.due_date || ['resolved', 'closed'].includes(status)) return false;
            const due = new Date(String(row.due_date).slice(0, 10) + 'T23:59:59');
            if (Number.isNaN(due.getTime()) || due.getTime() > Date.now() + 24 * 60 * 60 * 1000) return false;
          }
          continue;
        }
        const rawActual = filterValue(row, key, resource);
        const actualValues = Array.isArray(rawActual)
          ? rawActual.map(filterText)
          : (key === 'service_names' ? String(rawActual ?? '').split(',').map(filterText) : [filterText(rawActual)]);
        if (!actualValues.includes(expected)) return false;
      }
      if (from || to) {
        // Keep the register's existing date-range meaning: both bounds apply
        // to the record's primary date (Contract Start Date for contracts).
        const raw = String(row.date || row.start_date || row.created_at || '').slice(0, 10);
        if (!raw || (from && raw < from) || (to && raw > to)) return false;
      }
      return true;
    });
  }
  function installRegisterFilters(resource) {
    const rows = loadedRows[resource] || [];
    if (!rows.length && !chooseTable(resource)) return;
    const table = chooseTable(resource); if (!table) return;
    // Replace old prototype-only filter controls with one working, data-aware filter panel.
    document.querySelectorAll('.filters').forEach(panel => panel.closest('section.card')?.remove());
    document.querySelectorAll('.gp-user-role-tabs').forEach(tabs => tabs.remove());
    const section = document.createElement('section'); section.className = 'card gp-register-filter-card';
    const panel = document.createElement('form'); panel.className = 'filters'; panel.style.margin = '0';
    const grid = document.createElement('div'); grid.className = 'filter-grid gp-register-filter-grid';
    const addField = (label, key, type = 'select') => {
      const field = document.createElement('div'); field.className = 'field';
      const lab = document.createElement('label'); lab.textContent = label; field.appendChild(lab);
      let control;
      if (type === 'search') { control = document.createElement('input'); control.type = 'search'; control.className = 'input'; control.placeholder = `Search ${resource.replace(/-/g, ' ')}...`; }
      else if (type === 'date') { control = document.createElement('input'); control.type = 'date'; control.className = 'input'; }
      else {
        control = document.createElement('select'); control.className = 'select'; const blank = document.createElement('option'); blank.value = ''; blank.textContent = `All ${label.toLowerCase()}`; control.appendChild(blank);
        const rawValues = key === 'ticket_view' ? ['My Tickets', 'Unassigned', 'SLA at Risk'] : key === 'service_names' ? rows.flatMap(r => String(r.service_names || '').split(',').map(v => v.trim()).filter(Boolean)) : rows.map(r => String(filterValue(r, key, resource) ?? '').trim()).filter(Boolean);
        const values = [...new Set(rawValues)].sort((a, b) => a.localeCompare(b));
        values.forEach(value => { const option = document.createElement('option'); option.value = value; option.textContent = value; control.appendChild(option); });
      }
      control.dataset.filterKey = key; field.appendChild(control); grid.appendChild(field);
    };
    addField('Search', 'search', 'search');
    filterSpecs(resource).forEach(([label, key]) => addField(label, key));
    if (resource === 'tickets' || resource === 'projects' || resource === 'contracts') {
      addField('From Date', 'from', 'date'); addField('To Date', 'to', 'date');
    }
    const actions = document.createElement('div'); actions.className = 'filter-actions'; actions.style.marginTop = '14px';
    const apply = document.createElement('button'); apply.type = 'button'; apply.className = 'btn btn-primary'; apply.textContent = 'Apply Filters'; apply.dataset.applyRegisterFilters = '';
    const reset = document.createElement('button'); reset.type = 'button'; reset.className = 'btn'; reset.textContent = 'Reset';
    actions.append(apply, reset); panel.append(grid, actions); section.append(panel);
    const tableSection = table.closest('section.card') || table.parentElement;
    tableSection.parentNode.insertBefore(section, tableSection);
    let selectedUserRole = 'admin';
    if (resource === 'users') {
      const tabs = document.createElement('div'); tabs.className = 'gp-user-role-tabs'; tabs.setAttribute('aria-label', 'Filter users by role');
      const roleCounts = { admin: rows.filter(r => String(r.role).toLowerCase() === 'admin').length, agent: rows.filter(r => String(r.role).toLowerCase() === 'agent').length, customer: rows.filter(r => String(r.role).toLowerCase() === 'customer').length };
      [['admin', 'Administrators'], ['agent', 'Agents'], ['customer', 'Customers']].forEach(([role, label]) => {
        const button = document.createElement('button'); button.type = 'button'; button.className = 'gp-user-role-tab'; button.dataset.userRole = role;
        button.textContent = `${label} (${roleCounts[role]})`; if (role === selectedUserRole) button.classList.add('active');
        button.addEventListener('click', () => { userRolePages[selectedUserRole] = currentPage; selectedUserRole = role; currentPage = userRolePages[role] || 1; tabs.querySelectorAll('button').forEach(b => b.classList.toggle('active', b.dataset.userRole === role)); run(false); });
        tabs.appendChild(button);
      });
      tableSection.parentNode.insertBefore(tabs, tableSection);
    }
    const isTicketRegister = resource === 'tickets' && ['tickets.html', 'my-tickets.html'].includes(file);
    const pageSize = 10;
    let currentPage = 1;
    const userRolePages = { admin: 1, agent: 1, customer: 1 };
    const paginationFoot = (() => {
      let foot = tableSection.querySelector('.table-foot');
      if (!foot) {
        foot = document.createElement('div');
        foot.className = 'table-foot';
        tableSection.appendChild(foot);
      }
      return foot;
    })();
    let pageInfo = paginationFoot.querySelector('[data-gp-ticket-page-info]') || paginationFoot.querySelector('span');
    if (!pageInfo) { pageInfo = document.createElement('span'); paginationFoot.appendChild(pageInfo); }
    pageInfo.dataset.gpTicketPageInfo = '';
    let pageButtons = paginationFoot.querySelector('[data-gp-ticket-page-buttons]');
    if (!pageButtons) {
      pageButtons = document.createElement('div');
      pageButtons.className = 'gp-ticket-page-buttons';
      pageButtons.dataset.gpTicketPageButtons = '';
      paginationFoot.appendChild(pageButtons);
    }
    const drawRegisterPagination = (total, totalPages) => {
      const first = total ? ((currentPage - 1) * pageSize) + 1 : 0;
      const last = Math.min(currentPage * pageSize, total);
      const noun = isTicketRegister ? 'ticket' : 'record';
      pageInfo.textContent = `Showing ${first}–${last} of ${total} ${noun}${total === 1 ? '' : 's'}`;
      pageButtons.replaceChildren();
      const makeButton = (label, targetPage, options = {}) => {
        const button = document.createElement('button');
        button.type = 'button';
        button.className = 'gp-ticket-page-btn';
        button.textContent = label;
        if (options.current) { button.classList.add('is-current'); button.setAttribute('aria-current', 'page'); }
        if (options.disabled) button.disabled = true;
        button.addEventListener('click', () => {
          if (targetPage === currentPage || targetPage < 1 || targetPage > totalPages) return;
          if (resource === 'users') userRolePages[selectedUserRole] = targetPage;
          currentPage = targetPage;
          run(false);
        });
        pageButtons.appendChild(button);
      };
      makeButton('Previous', currentPage - 1, { disabled: currentPage <= 1 });
      let visiblePages;
      if (totalPages <= 7) visiblePages = Array.from({ length: totalPages }, (_, i) => i + 1);
      else {
        const startPage = Math.max(2, currentPage - 1);
        const endPage = Math.min(totalPages - 1, currentPage + 1);
        visiblePages = [1];
        if (startPage > 2) visiblePages.push('…');
        for (let p = startPage; p <= endPage; p++) visiblePages.push(p);
        if (endPage < totalPages - 1) visiblePages.push('…');
        visiblePages.push(totalPages);
      }
      visiblePages.forEach(page => {
        if (page === '…') {
          const dots = document.createElement('span'); dots.className = 'gp-ticket-page-dots'; dots.textContent = '…'; pageButtons.appendChild(dots);
        } else makeButton(String(page), page, { current: page === currentPage });
      });
      makeButton('Next', currentPage + 1, { disabled: currentPage >= totalPages });
    };
    const run = (resetPage = true) => {
      const values = {}; grid.querySelectorAll('[data-filter-key]').forEach(el => values[el.dataset.filterKey] = el.value);
      let filtered = applyRegisterFilters(resource, rows, values);
      if (resource === 'users') filtered = filtered.filter(r => String(r.role || '').toLowerCase() === selectedUserRole);
      if (isTicketRegister) {
        // Ticket IDs increase as new tickets are created, so newest tickets stay on page 1.
        filtered = [...filtered].sort((a, b) => Number(b.ticket_id || 0) - Number(a.ticket_id || 0));
      } else {
        const newestKey = ({ customers: 'customer_id', projects: 'project_id', contracts: 'contract_id', plans: 'plan_id', contacts: 'contact_id', assets: 'asset_id', teams: 'team_id', users: 'user_id' })[resource];
        if (newestKey) filtered = [...filtered].sort((a, b) => Number(b[newestKey] || 0) - Number(a[newestKey] || 0));
      }
      if (resetPage) {
        currentPage = 1;
        if (resource === 'users') Object.keys(userRolePages).forEach(role => userRolePages[role] = 1);
      }
      const totalPages = Math.max(1, Math.ceil(filtered.length / pageSize));
      currentPage = Math.min(currentPage, totalPages);
      if (resource === 'users') userRolePages[selectedUserRole] = currentPage;
      const start = (currentPage - 1) * pageSize;
      renderTable(resource, filtered.slice(start, start + pageSize), table, file);
      drawRegisterPagination(filtered.length, totalPages);
      const count = section.querySelector('[data-filter-count]');
      if (count) count.textContent = `${filtered.length} matching ${isTicketRegister ? 'tickets' : 'records'}`;
    };
    // Apply is an explicit action rather than relying only on native form submission.
    // This keeps the same behavior across every register module and browser.
    apply.addEventListener('click', ev => { ev.preventDefault(); ev.stopPropagation(); run(true); });
    panel.addEventListener('submit', ev => { ev.preventDefault(); run(true); });
    reset.addEventListener('click', ev => { ev.preventDefault(); grid.querySelectorAll('input,select').forEach(el => { el.value = ''; }); run(true); });
    const search = grid.querySelector('input[data-filter-key="search"]'); search?.addEventListener('input', () => { clearTimeout(search._filterTimer); search._filterTimer = setTimeout(() => run(true), 180); });
    const foot = table.closest('.card')?.querySelector('.table-foot'); if (foot && !foot.querySelector('[data-filter-count]')) { const count = document.createElement('small'); count.dataset.filterCount = ''; count.style.marginLeft = '12px'; foot.querySelector('span')?.after(count); }
    run(true);
  }
  async function refreshListKeepingViewport(resource, recordId) {
    const startY = window.scrollY;
    const selector = `[data-gp-row-id="${CSS.escape(String(recordId))}"]`;
    const before = document.querySelector(selector);
    const beforeTop = before ? before.getBoundingClientRect().top : null;
    const rows = await loadList(resource);
    if (resource === pageResource[file]) installRegisterFilters(resource);
    await new Promise(resolve => requestAnimationFrame(resolve));
    const after = document.querySelector(selector);
    if (after && beforeTop !== null) {
      const delta = after.getBoundingClientRect().top - beforeTop;
      window.scrollTo({ top: Math.max(0, window.scrollY + delta), behavior: 'auto' });
    } else {
      window.scrollTo({ top: startY, behavior: 'auto' });
    }
    return rows;
  }
  function installSearch() {
    if (!document.body.dataset.statusHandlerInstalled) {
      document.body.dataset.statusHandlerInstalled = '1';
      document.addEventListener('click', async ev => {
        const button = ev.target.closest('[data-toggle-resource-active]'); if (!button) return;
        const resource = button.dataset.toggleResourceActive, id = button.dataset.toggleId;
        const activating = button.textContent.trim().toLowerCase() === 'activate';
        if (!activating) {
          const confirmed = await confirmDialog('Deactivate this record? It will remain in the system and can be activated again.', 'Deactivate record');
          if (!confirmed) return;
        }
        button.disabled = true;
        try {
          const result = await api(`/api/${encodeURIComponent(resource)}/${encodeURIComponent(id)}/toggle-active`, { method: 'POST' });
          toast(result.message);
          await refreshListKeepingViewport(resource, id);
        } catch (e) { toast(e.message, 'error'); button.disabled = false; }
      });
      document.addEventListener('click', async ev => {
        const button = ev.target.closest('[data-toggle-customer-active]'); if (!button) return;
        const id = button.dataset.toggleCustomerActive;
        const activating = button.textContent.trim().toLowerCase() === 'activate';
        if (!activating) { const confirmed = await confirmDialog('Deactivate this customer account? It can be activated again later.', 'Deactivate customer'); if (!confirmed) return; }
        button.disabled = true;
        try {
          const result = await api(`/api/customers/${encodeURIComponent(id)}/toggle-active`, { method: 'POST' });
          toast(result.message);
          const resource = file === 'users.html' ? 'users' : 'customers';
          await refreshListKeepingViewport(resource, file === 'users.html' ? (button.closest('tr')?.dataset.gpRowId || id) : id);
        } catch (e) { toast(e.message, 'error'); button.disabled = false; }
      });
      document.addEventListener('click', async ev => {
        const button = ev.target.closest('[data-toggle-admin-active]'); if (!button) return;
        const id = button.dataset.toggleAdminActive;
        const activating = button.textContent.trim().toLowerCase() === 'activate';
        if (!activating) {
          const confirmed = await confirmDialog('Deactivate this Admin account? The current account and the last active Admin cannot be deactivated.', 'Deactivate Admin');
          if (!confirmed) return;
        }
        button.disabled = true;
        try {
          const result = await api(`/api/users/${encodeURIComponent(id)}/toggle-active`, { method: 'POST' });
          toast(result.message);
          await refreshListKeepingViewport('users', button.closest('tr')?.dataset.gpRowId || id);
        } catch (e) { toast(e.message, 'error'); button.disabled = false; }
      });
      document.addEventListener('click', async ev => {
        const button = ev.target.closest('[data-toggle-agent-active]'); if (!button) return;
        const id = button.dataset.toggleAgentActive;
        const activating = button.textContent.trim().toLowerCase() === 'activate';
        if (!activating) { const confirmed = await confirmDialog('Deactivate this Agent account? The account can be activated again later.', 'Deactivate Agent'); if (!confirmed) return; }
        button.disabled = true;
        try {
          const result = await api(`/api/users/${encodeURIComponent(id)}/toggle-active`, { method: 'POST' });
          toast(result.message);
          await refreshListKeepingViewport('users', button.closest('tr')?.dataset.gpRowId || id);
        } catch (e) { toast(e.message, 'error'); button.disabled = false; }
      });
      document.addEventListener('click', async ev => {
        const button = ev.target.closest('[data-reset-customer-password]'); if (!button) return;
        const id = button.dataset.resetCustomerPassword;
        const confirmed = await confirmDialog('Reset this account password and email a temporary password to the registered email address?', 'Reset account password');
        if (!confirmed) return;
        button.disabled = true;
        try { const result = await api(`/api/users/${encodeURIComponent(id)}/reset-password`, { method: 'POST' }); toast(result.message); }
        catch (e) { toast(e.message, 'error'); }
        finally { button.disabled = false; }
      });
    }
    const resource = pageResource[file];
    if (resource && !['audit-log.html', 'dashboard.html', 'admin-dashboard.html', 'agent-dashboard.html', 'user-dashboard.html'].includes(file)) installRegisterFilters(resource);
    document.querySelectorAll('form.compact-search').forEach(form => {
      if (form.dataset.searchHandler) return; form.dataset.searchHandler = '1';
      form.addEventListener('submit', ev => {
        const input = form.querySelector('input[type="search"]'); if (!input) return;
        const resource = pageResource[file], rows = loadedRows[resource] || []; if (!rows.length) return;
        ev.preventDefault();
        const filterSearch = document.querySelector('.gp-register-filter-grid input[data-filter-key="search"]');
        if (filterSearch) { filterSearch.value = input.value; filterSearch.dispatchEvent(new Event('input', { bubbles: true })); }
        else { const filtered = rows.filter(r => JSON.stringify(r).toLowerCase().includes(input.value.trim().toLowerCase())); const table = chooseTable(resource); if (table) renderTable(resource, filtered, table, file); }
      });
    });
    document.querySelectorAll('a[href="#"]').forEach(a => {
      if (a.dataset.gpLinkHandler) return; a.dataset.gpLinkHandler = '1';
      if (/export csv|^export$|export log/i.test(a.textContent.trim())) a.addEventListener('click', ev => { ev.preventDefault(); const resource = pageResource[file], rows = loadedRows[resource] || []; exportCsv(resource, rows); });
      else if (/^print$/i.test(a.textContent.trim())) a.addEventListener('click', ev => { ev.preventDefault(); window.print(); });
    });
    if (file === 'audit-log.html') document.querySelectorAll('a').forEach(a => { if (/export log/i.test(a.textContent) && a.getAttribute('href') !== '#' && !a.dataset.auditExportHandler) { a.dataset.auditExportHandler = '1'; a.addEventListener('click', ev => { ev.preventDefault(); exportCsv('audit-logs', loadedRows['audit-logs'] || []); }); } });
  }
  function exportCsv(resource, rows) {
    if (!rows.length) { toast('There are no records to export.', 'error'); return; }
    const keys = Object.keys(rows[0]).filter(k => !['password_hash', 'password'].includes(k));
    const quote = v => '"' + String(v ?? '').replace(/"/g, '""') + '"';
    const csv = [keys.map(quote).join(','), ...rows.map(r => keys.map(k => quote(r[k])).join(','))].join('\r\n');
    const url = URL.createObjectURL(new Blob([csv], { type: 'text/csv;charset=utf-8;' }));
    const a = document.createElement('a'); a.href = url; a.download = `golden-pride-${resource}.csv`; a.click(); URL.revokeObjectURL(url);
  }
