  async function loadLookups() {
    try { lookupData = await api('/api/lookups'); }
    catch (_) { lookupData = {}; }
  }
  function optionRows(select, rows, valueKey, labelFn, placeholder) {
    const oldIndex = select.selectedIndex;
    const old = oldIndex > 0 ? select.value : '';
    const oldLabel = select.selectedOptions?.[0]?.textContent?.trim() || old;
    const blank = document.createElement('option'); blank.value = ''; blank.textContent = placeholder || 'Select an option';
    select.replaceChildren(blank);
    (rows || []).forEach(row => {
      const o = document.createElement('option'); o.value = String(row[valueKey] ?? ''); o.textContent = labelFn(row); select.appendChild(o);
    });
    if (old) {
      let match = [...select.options].find(o => o.value === old);
      // Keep a saved value visible during edit even if it is no longer in the
      // current filtered lookup set. Do not silently replace it with the first option.
      if (!match) { match = document.createElement('option'); match.value = old; match.textContent = oldLabel || old; select.appendChild(match); }
      select.value = old;
    }
  }
  function agentsForTicketPair(teamId, _serviceCode, keepCurrentAssignee = '') {
    // Assignment must stay within the ticket's Support Team. Agents already
    // handling an unresolved ticket are unavailable for new assignments.
    const selectedTeamId = String(teamId || '');
    const keepName = String(keepCurrentAssignee || '').trim().toLowerCase();
    return (lookupData.users || []).filter(user => {
      if (user.role !== 'agent' || user.active === false) return false;
      const isCurrentAssignee = keepName && String(user.fullname || '').trim().toLowerCase() === keepName;
      if (user.available_for_assignment === false && !isCurrentAssignee) return false;
      if (!selectedTeamId) return true;
      const memberships = Array.isArray(user.team_ids) ? user.team_ids.map(String) : [];
      if (user.team_id !== undefined && user.team_id !== null) memberships.push(String(user.team_id));
      return memberships.includes(selectedTeamId);
    }).sort((a, b) => String(a.fullname || '').localeCompare(String(b.fullname || '')));
  }
  function setAssignableAgentOptions(select, teamId, serviceCode, selectedValue = '') {
    if (!select) return [];
    const currentChoice = String(selectedValue || '');
    if (currentChoice && currentChoice !== '__clear__') select.dataset.gpLastAssignedChoice = currentChoice;
    const previousAgent = String(select.dataset.gpLastAssignedChoice || '');
    const choiceToMatch = currentChoice === '__clear__' ? '' : currentChoice;
    const agents = agentsForTicketPair(teamId, serviceCode, choiceToMatch || previousAgent);
    const matchedAgent = agents.find(agent =>
      String(agent.fullname).trim().toLowerCase() === choiceToMatch.trim().toLowerCase());

    const placeholder = document.createElement('option');
    placeholder.value = '';
    placeholder.textContent = 'Unassigned';
    select.replaceChildren(placeholder);
    agents.forEach(agent => {
      const option = document.createElement('option');
      option.value = String(agent.fullname);
      option.textContent = agent.fullname;
      select.appendChild(option);
    });
    let legacyClearOption = null;
    if (previousAgent && !matchedAgent) {
      legacyClearOption = document.createElement('option');
      legacyClearOption.value = '__clear__';
      legacyClearOption.textContent = `Unassign previous Agent (${previousAgent})`;
      select.appendChild(legacyClearOption);
    }
    select.value = currentChoice === '__clear__' ? '__clear__' :
      (matchedAgent ? String(matchedAgent.fullname) : (legacyClearOption ? '__clear__' : ''));
    select.disabled = false;
    return agents;
  }
  function configureSelects() {
    const cfg = activeFormConfig || formConfig[file];
    if (!cfg) return;
    const mainForm = getMainForm(); if (!mainForm) return;
    mainForm.querySelectorAll('.field').forEach(field => {
      const label = labelKey(field.querySelector('label')?.textContent || '');
      const select = field.querySelector('select'); if (!select) return;
      if (label === 'customer') {
        // A ticket may be created for any existing customer record; a portal login is not a prerequisite.
        const rows = lookupData.customers || [];
        optionRows(select, rows, 'customer_id', r => r.customer_name, 'Select customer');
      }
      else if (label === 'project' || label === 'project (optional)' || label === 'customer/project') optionRows(select, lookupData.projects, 'project_id', r => r.project_name, 'Select project');
      else if (label === 'contract (optional)' || label === 'contract / plan' || label === 'contract / support plan') optionRows(select, lookupData.contracts, 'contract_id', r => `${r.contract_code || 'CON-' + r.contract_id} · ${r.contract_name}`, 'Select contract (optional)');
      else if ((label === 'support plan' || label === 'support plan (optional)') && !['add-ticket.html', 'user-create-ticket.html'].includes(file)) optionRows(select, lookupData.plans, 'plan_id', r => `${r.plan_name}${r.plan_type ? ' · ' + r.plan_type : ''}`, 'Select support plan');
      else if (label === 'asset' || label === 'asset (optional)' || label === 'related asset' || label === 'related asset (optional)') optionRows(select, lookupData.assets, 'asset_id', r => `${r.asset_tag} · ${r.asset_name}`, label.startsWith('related') ? 'No asset linked' : 'No asset linked');
      else if (label === 'mapped team') optionRows(select, lookupData.teams, 'team_name', r => r.team_name, 'Select team');
      else if (label === 'support team' || label === 'support team (optional)') optionRows(select, lookupData.teams, 'team_id', r => r.team_name, 'Select team');
      else if (label === 'service catalog') optionRows(select, lookupData.services, 'code_id', r => r.name, 'Select service');
      else if (label === 'contact' || label === 'contact (optional)') optionRows(select, lookupData.contacts, 'contact_id', r => `${r.fullname}${r.customer_name ? ' · ' + r.customer_name : ''}`, 'Select contact');
      else if (label === 'team members') optionRows(select, (lookupData.users || []).filter(u => u.role === 'agent'), 'fullname', r => r.fullname, 'Select team members');
      else if (label === 'service' || label === 'service / request type' || label === 'service / request type (optional)') optionRows(select, lookupData.services, 'code_id', r => r.name, 'Select service');
      else if (label === 'request type' && file === 'add-ticket.html') { optionRows(select, lookupData.services, 'code_id', r => r.name, 'Select request type'); select.required = true; }
      else if (label === 'request type' && file === 'add-user.html') {
        // Agent Request Type must be selected from the existing Service Catalog only.
        optionRows(select, lookupData.services, 'code_id', r => r.name, 'Select request type');
        select.required = true;
      }
      else if (label === 'assigned' || label === 'assigned to') {
        const agents = (lookupData.users || []).filter(u => u.role === 'agent' || u.role === 'admin');
        optionRows(select, agents.filter(r => r.role === 'agent' && r.active !== false), 'fullname', r => r.fullname, 'Unassigned');
      }
    });
  }

  function setupNonNegativeSupportPlanFields() {
    const form = getMainForm(); if (!form) return;
    form.querySelectorAll('.field').forEach(field => {
      const label = labelForField(field);
      const input = field.querySelector('input'); if (!input) return;
      if (['response warning %', 'response critical %', 'resolution warning %', 'resolution critical %'].includes(label) && file === 'add-support-plan.html') {
        input.type = 'text'; input.min = '0'; input.max = '99'; input.step = '1'; input.maxLength = 2; input.pattern = '[0-9]{1,2}'; input.inputMode = 'numeric';
        input.addEventListener('keydown', ev => { if (ev.key === '-' || ev.key === 'Subtract' || ev.key === '+' || ev.key === 'e' || ev.key === 'E') ev.preventDefault(); });
        input.addEventListener('input', () => { input.value = input.value.replace(/[^0-9]/g, '').slice(0, 2); });
      }
      if (label === 'sort order' && ['add-service.html', 'add-request-type.html'].includes(file)) {
        input.type = 'number'; input.min = '0'; input.step = '1'; input.inputMode = 'numeric';
        input.addEventListener('keydown', ev => { if (['-', 'Subtract', '+', 'e', 'E', '.'].includes(ev.key)) ev.preventDefault(); });
        input.addEventListener('input', () => { if (input.value.startsWith('-')) input.value = input.value.replace(/-/g, ''); });
      }
      if (['response sla', 'resolution sla'].includes(label) && file === 'add-support-plan.html') {
        input.inputMode = 'text';
        input.addEventListener('keydown', ev => { if (ev.key === '-' && input.selectionStart === 0) ev.preventDefault(); });
        input.addEventListener('input', () => { input.value = input.value.replace(/^(\s*)-\s*/, '$1'); });
      }
    });
  }

  function yangonTodayString() {
    const parts = new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Yangon', year: 'numeric', month: '2-digit', day: '2-digit' }).formatToParts(new Date());
    const pick = type => parts.find(p => p.type === type)?.value || '00';
    return `${pick('year')}-${pick('month')}-${pick('day')}`;
  }
  function addDaysIso(value, days) { const d = new Date(`${value}T00:00:00Z`); d.setUTCDate(d.getUTCDate() + days); return d.toISOString().slice(0, 10); }
  function setupDateConstraints() {
    const form = getMainForm(); if (!form) return;
    const today = yangonTodayString();
    const getField = (name) => [...form.querySelectorAll('.field')].find(f => labelForField(f) === name)?.querySelector('input[type="date"]');
    const created = getField('created');
    if (file === 'add-ticket.html' && created) { if (!idParam) created.value = today; created.disabled = true; if (!idParam) { created.min = today; created.max = today; } }
    const start = getField('start date');
    const end = getField('end date');
    const due = getField('due date');
    // Date rules are strict on both create and edit forms: no past dates.
    if (start) { start.min = today; if (!start.value) start.value = today; }
    if (due) { due.min = today; }
    const syncEnd = () => {
      if (!end) return;
      const minimum = start?.value ? addDaysIso(start.value, 1) : addDaysIso(today, 1);
      end.min = minimum;
      if (end.value && end.value < minimum) end.setCustomValidity('End Date must be later than Start Date and cannot be in the past.');
      else end.setCustomValidity('');
    };
    start?.addEventListener('input', syncEnd);
    start?.addEventListener('change', syncEnd); syncEnd();
  }
  function setupPhoneEmailValidation() {
    const form = getMainForm(); if (!form) return;
    form.querySelectorAll('.field').forEach(field => {
      const label = labelForField(field);
      const input = field.querySelector('input'); if (!input) return;
      if (label.includes('phone')) {
        input.type = 'tel'; input.inputMode = 'tel'; input.maxLength = 16; input.pattern = '\\+?[0-9]{1,15}'; input.title = 'Use up to 15 digits. A leading + is optional; hyphens and spaces are not allowed.';
        input.addEventListener('keydown', ev => { if (ev.key === '-' || ev.key === ' ') ev.preventDefault(); });
        input.addEventListener('input', () => { let v = input.value.replace(/[^0-9+]/g, ''); v = (v.startsWith('+') ? '+' : '') + v.replace(/\+/g, '').replace(/^\+/, '').replace(/\+/g, ''); if (v.startsWith('+')) v = '+' + v.slice(1).slice(0, 15); else v = v.slice(0, 15); input.value = v; });
      }
      if (label.includes('email')) {
        input.type = 'email'; input.maxLength = 254; input.autocomplete = 'email';
        input.addEventListener('blur', () => { input.value = input.value.trim().toLowerCase(); });
      }
    });
  }
  function validateTicketSetupBeforeSave(page, payload) {
    let customerId = payload.customer_id;
    if (page === 'user-create-ticket.html') customerId = (lookupData.customers || [])[0]?.customer_id;
    if (!customerId) throw new Error('Select a customer before creating this ticket.');
    if (page === 'add-ticket.html' && !(lookupData.customers || []).some(c => String(c.customer_id) === String(customerId))) {
      throw new Error('The selected Customer is not available. Refresh and select it again.');
    }
    if (!String(payload.subject || '').trim()) throw new Error('Enter a ticket subject.');
  }

  function validateFormBeforeSave(page, payload) {
    const today = yangonTodayString();
    const validEmail = value => !value || /^[a-z0-9.!#$%&'*+/=?^_`{|}~-]+@[a-z0-9-]+(?:\.[a-z0-9-]+)+$/i.test(String(value).trim());
    if (payload.email && !validEmail(payload.email)) throw new Error('Enter a valid email address, for example name@gmail.com.');
    if (payload.phone) { const value = String(payload.phone).trim(); const digits = value.startsWith('+') ? value.slice(1) : value; if (!/^\+?[0-9]{1,15}$/.test(value) || digits.length > 15) throw new Error('Phone number must contain up to 15 digits. Do not use hyphens or spaces.'); }
    if (page === 'add-ticket.html') {
      payload.date = today;
      if (payload.due_date && payload.due_date < today) throw new Error(`Due Date cannot be earlier than today (${today}).`);
      if (!payload.type) payload.type = 'Incident';
      validateTicketSetupBeforeSave(page, payload);
    }
    if (page === 'user-create-ticket.html') {
      if (!payload.type) payload.type = 'Incident';
      validateTicketSetupBeforeSave(page, payload);
    }
    if (['add-contract.html', 'add-project.html'].includes(page)) {
      const start = payload.start_date || '', end = payload.end_date || '';
      const fields = [...getMainForm().querySelectorAll('.field')];
      const startOriginal = fields.find(f => labelForField(f) === 'start date')?.querySelector('input')?.dataset.originalValue;
      const endOriginal = fields.find(f => labelForField(f) === 'end date')?.querySelector('input')?.dataset.originalValue;
      if (!start) throw new Error('Select a Start Date.');
      if (!end) throw new Error('Select an End Date.');
      if (start < today) throw new Error(`Start Date cannot be earlier than today (${today}).`);
      if (end < today) throw new Error(`End Date cannot be earlier than today (${today}).`);
      if (end <= start) throw new Error('End Date must be later than Start Date. Same-day dates are not allowed.');
    }
    if (page === 'add-user.html') {
      const role = String(payload.role || 'customer').toLowerCase();
      if (role === 'agent') {
        if ((payload.team_ids || []).length !== 1 && !payload.other_team_name) throw new Error('Choose exactly one Support Team for this Agent.');
        if (!payload.request_type_code) throw new Error('Choose exactly one Request Type for this Agent.');
      }
    }
  }
  function setupDependentDropdowns() {
    const form = getMainForm(); if (!form) return;
    const field = (...labels) => [...form.querySelectorAll('.field')].find(f => labels.includes(labelForField(f)));
    const selectOf = (...labels) => field(...labels)?.querySelector('select');
    const customerSelect = selectOf('customer', 'ticket');
    const projectSelect = selectOf('project', 'project (optional)', 'customer/project');
    const contactSelect = selectOf('contact', 'contact (optional)');
    const isTicketForm = ['add-ticket.html', 'user-create-ticket.html'].includes(file);
    const contractSelect = isTicketForm ? selectOf('contract (optional)', 'contract / plan', 'contract / support plan') : null;
    const planSelect = isTicketForm ? selectOf('support plan', 'support plan (optional)') : null;
    const assetSelect = selectOf('asset', 'asset (optional)', 'related asset', 'related asset (optional)');
    const serviceSelect = selectOf('service', 'service / request type', 'service / request type (optional)', 'request type');
    const teamSelect = selectOf('support team', 'support team (optional)');
    const assignedSelect = selectOf('assigned', 'assigned to');
    const getCustomerId = () => customerSelect?.value || (currentUser?.role === 'customer' ? (lookupData.customers || [])[0]?.customer_id : '');
    const selectedService = () => {
      const value = String(serviceSelect?.value || '');
      return (lookupData.services || []).find(r => String(r.code_id) === value || String(r.name) === value) || null;
    };
    const sync = () => {
      const customerId = String(getCustomerId() || '');
      const projectId = String(projectSelect?.value || '');
      const oldProject = projectSelect?.value || '';
      const projectRows = (lookupData.projects || []).filter(r => customerId && String(r.customer_id) === customerId);
      if (projectSelect) { optionRows(projectSelect, projectRows, 'project_id', r => r.project_name, 'Select customer project'); if (oldProject && [...projectSelect.options].some(o => o.value === oldProject)) projectSelect.value = oldProject; }

      if (contactSelect) {
        const old = contactSelect.value;
        const rows = (lookupData.contacts || []).filter(r => customerId && String(r.customer_id) === customerId);
        optionRows(contactSelect, rows, 'contact_id', r => r.fullname, 'Select customer contact');
        if (old && [...contactSelect.options].some(o => o.value === old)) contactSelect.value = old;
      }
      if (contractSelect) {
        const old = contractSelect.value;
        const rows = (lookupData.contracts || []).filter(r => customerId && String(r.customer_id) === customerId && (!projectId || !r.project_id || String(r.project_id) === projectId));
        optionRows(contractSelect, rows, 'contract_id', r => `${r.contract_code || 'CTR-' + r.contract_id} · ${r.contract_name}`, 'Select customer contract');
        if (old && [...contractSelect.options].some(o => o.value === old)) contractSelect.value = old;
      }
      const contract = (lookupData.contracts || []).find(r => contractSelect && String(r.contract_id) === String(contractSelect.value)) || null;
      if (planSelect) {
        const linkedPlan = (lookupData.plans || []).find(r => contract?.plan_id && String(r.plan_id) === String(contract.plan_id)) || null;
        planSelect.replaceChildren();
        const placeholder = document.createElement('option');
        placeholder.value = '';
        placeholder.textContent = contract ? (linkedPlan ? 'Select contract support plan' : 'No support plan linked to this contract') : 'Select a contract first';
        planSelect.appendChild(placeholder);
        if (linkedPlan) {
          const option = document.createElement('option');
          option.value = String(linkedPlan.plan_id);
          option.textContent = `${linkedPlan.plan_name}${linkedPlan.plan_type ? ' · ' + linkedPlan.plan_type : ''}`;
          planSelect.appendChild(option);
          // A Contract has exactly one linked Support Plan, so select that plan.
          planSelect.value = String(linkedPlan.plan_id);
        } else {
          planSelect.value = '';
        }
        planSelect.disabled = !linkedPlan;
      }
      if (assetSelect) {
        const old = assetSelect.value;
        const rows = (lookupData.assets || []).filter(r => customerId && String(r.customer_id) === customerId && (!projectId || !r.project_id || String(r.project_id) === projectId));
        optionRows(assetSelect, rows, 'asset_id', r => `${r.asset_tag} · ${r.asset_name}`, 'No matching customer asset');
        if (old && [...assetSelect.options].some(o => o.value === old)) assetSelect.value = old;
      }
      if (teamSelect) {
        const old = teamSelect.value;
        optionRows(teamSelect, lookupData.teams, 'team_id', r => r.team_name, 'Select Support Team');
        if (old && [...teamSelect.options].some(o => o.value === old)) teamSelect.value = old;
        teamSelect.disabled = false;
      }
      if (assignedSelect) {
        const oldAssigned = assignedSelect.value;
        const service = selectedService();
        const mappedTeamName = String(service?.mapped_team || '').trim().toLowerCase();
        const mappedTeam = (lookupData.teams || []).find(team =>
          String(team.team_name || '').trim().toLowerCase() === mappedTeamName ||
          String(team.team_code || '').trim().toLowerCase() === mappedTeamName ||
          String(team.code_id || '') === String(service?.code_id || '') ||
          (Array.isArray(team.service_code_ids) && team.service_code_ids.map(String).includes(String(service?.code_id || '')))
        );
        const effectiveTeamId = teamSelect?.value || mappedTeam?.team_id || '';
        setAssignableAgentOptions(assignedSelect, effectiveTeamId, serviceSelect?.value, oldAssigned);
        if (assignedSelect.dataset.initialUiValue === undefined) assignedSelect.dataset.initialUiValue = assignedSelect.value;
      }
    };
    customerSelect?.addEventListener('change', () => {
      if (projectSelect) projectSelect.value = ''; if (contactSelect) contactSelect.value = '';
      if (contractSelect) contractSelect.value = ''; if (assetSelect) assetSelect.value = '';
      sync();
    });
    projectSelect?.addEventListener('change', () => { if (contractSelect) contractSelect.value = ''; if (assetSelect) assetSelect.value = ''; sync(); });
    contractSelect?.addEventListener('change', () => {
      const selected = (lookupData.contracts || []).find(row => String(row.contract_id) === String(contractSelect.value));
      // Selecting a project-specific contract also selects its parent project.
      if (projectSelect && selected?.project_id && !projectSelect.value) { projectSelect.value = String(selected.project_id); }
      sync();
    });
    serviceSelect?.addEventListener('change', sync);
    teamSelect?.addEventListener('change', sync);
    sync();
  }
  function setupPrimaryContactRule() {
    if (file !== 'add-contact.html') return;
    const form = getMainForm();
    if (!form) return;
    const fields = [...form.querySelectorAll('.field')];
    const customerSelect = fields.find(field => labelForField(field) === 'customer')?.querySelector('select');
    const typeField = fields.find(field => labelForField(field) === 'type');
    const typeSelect = typeField?.querySelector('select');
    if (!customerSelect || !typeSelect) return;

    const allContacts = Array.isArray(lookupData.allContacts) ? lookupData.allContacts : (lookupData.contacts || []);
    const isPrimary = row => String(row.type || '').trim().toLowerCase() === 'primary contact';
    const primaryOption = [...typeSelect.options].find(option =>
      String(option.value || option.textContent).trim().toLowerCase() === 'primary contact'
    );
    if (!primaryOption) return;

    let note = typeField.querySelector('[data-primary-contact-note]');
    if (!note) {
      note = document.createElement('small');
      note.dataset.primaryContactNote = '';
      note.style.display = 'block';
      note.style.marginTop = '6px';
      note.style.color = '#a45a14';
      typeField.appendChild(note);
    }

    const sync = () => {
      const customerId = String(customerSelect.value || '');
      const currentId = String(idParam || '');
      const current = allContacts.find(row => String(row.contact_id) === currentId);
      const currentIsThisCustomerPrimary = Boolean(
        current && String(current.customer_id) === customerId && isPrimary(current)
      );
      const hasOtherPrimary = allContacts.some(row =>
        String(row.customer_id) === customerId && isPrimary(row) && String(row.contact_id) !== currentId
      );
      const blocked = Boolean(customerId && hasOtherPrimary && !currentIsThisCustomerPrimary);

      primaryOption.disabled = blocked;
      primaryOption.textContent = blocked ? 'Primary contact (already assigned)' : 'Primary contact';
      if (blocked && String(typeSelect.value || '').trim().toLowerCase() === 'primary contact') {
        const alternative = [...typeSelect.options].find(option =>
          option.value && String(option.value || option.textContent).trim().toLowerCase() !== 'primary contact'
        );
        typeSelect.value = alternative ? alternative.value : '';
      }
      note.textContent = blocked ? 'This customer already has a Primary Contact. Select another contact type.' : '';
      note.hidden = !blocked;
    };

    customerSelect.addEventListener('change', sync);
    typeSelect.addEventListener('change', sync);
    sync();
  }

  function getMainForm() {
    return [...document.querySelectorAll('form')].find(f => !f.classList.contains('compact-search') && !f.classList.contains('filter-grid') && !f.querySelector('input[type="search"]')) || null;
  }
  function labelForField(field) { return labelKey(field.querySelector('label')?.textContent || ''); }
  function fieldRawValue(field, page, label) {
    if (page === 'add-user.html' && label === 'support team') {
      const select = field.querySelector('[data-agent-team-select]');
      return select?.value && select.value !== '__other__' ? [select.value] : [];
    }
    const select = field.querySelector('select');
    if (select) {
      if (select.multiple) return [...select.selectedOptions].map(o => o.value || o.textContent.trim()).filter(Boolean);
      return select.value;
    }
    const checkboxes = [...field.querySelectorAll('input[type="checkbox"]')];
    if (checkboxes.length) return checkboxes.length === 1 && checkboxes[0].name !== 'team_ids' ? checkboxes[0].checked : checkboxes.filter(x => x.checked).map(x => x.value);
    const input = field.querySelector('input,textarea'); return input ? input.value : null;
  }
  function payloadForForm(page, form, cfg) {
    const payload = {};
    form.querySelectorAll('.field').forEach(field => {
      const label = labelForField(field), key = cfg.map[label];
      if (!key) return;
      let value = fieldRawValue(field, page, label);
      if (key === 'customer_visible' || key === 'auto_assign') {
        if (typeof value === 'string') value = ['yes', 'true', 'enabled', '1', 'on'].includes(value.toLowerCase());
      }
      if (key === 'member' && Array.isArray(value)) value = value.join(', ');
      if (page === 'add-user.html' && key === 'team_ids') {
        value = (Array.isArray(value) ? value : (value ? [value] : [])).map(v => Number(v)).filter(Number.isInteger);
      }
      if (key === 'category' && ['add-service.html', 'add-request-type.html'].includes(page) && String(value).trim().toLowerCase() === 'other') {
        const custom = field.querySelector('[data-other-category]')?.value.trim() || '';
        if (!custom) throw new Error('Enter a name for the new Service Catalog category.');
        value = custom;
      }
      if (key === 'mapped_team' && ['add-service.html', 'add-request-type.html'].includes(page) && String(value).trim().toLowerCase() === 'other') {
        const custom = field.querySelector('[data-other-mapped-team]')?.value.trim() || '';
        if (!custom) throw new Error('Enter the new Support Team name.');
        value = custom;
      }
      if (key === 'service_codes') {
        payload.service_codes = Array.isArray(value) ? value : (value ? [value] : []);
        if (payload.service_codes.length) payload.code_id = payload.service_codes[0];
        return;
      }
      if (key === 'service_code' && value) payload.service_code = value;
      else if ((key === 'type' && page === 'add-ticket.html') && value) {
        // The admin form's request type is the service name, matching the ticket ERD field.
        payload.type = value;
      } else payload[key] = value;
    });
    if (page === 'add-user.html') {
      const role = String(payload.role || 'customer').toLowerCase();
      const teamSelect = form.querySelector('[data-agent-team-select]');
      if (role === 'agent' && teamSelect?.value === '__other__') {
        payload.team_ids = [];
        const custom = String(form.querySelector('[data-user-other-team-name]')?.value || '').trim();
        if (!custom) throw new Error('Enter the new Support Team name.');
        payload.other_team_name = custom;
      }
    }
    if (page === 'add-customer.html' && customerEntityMode) {
      form.querySelectorAll('[data-customer-edit-field]').forEach(input => { payload[input.dataset.customerEditField] = input.value; });
      delete payload.role; delete payload.password; delete payload.team_id; delete payload.fullname;
    }
    if (page === 'add-support-plan.html') {
      if (String(payload.plan_type || '').trim().toLowerCase() === 'other') {
        const custom = String(payload.custom_plan_type || '').trim();
        if (!custom) throw new Error('Enter the new Plan Type.');
        payload.plan_type = custom;
      }
      delete payload.custom_plan_type;
      for (const key of ['response_sla', 'resolution_sla']) {
        if (/^\s*-\s*\d/.test(String(payload[key] || ''))) throw new Error(`${key.replace('_', ' ').toUpperCase()} cannot be negative.`);
      }
      for (const key of ['response_warning', 'response_critical', 'resolution_warning', 'resolution_critical']) {
        const value = payload[key];
        if (value !== undefined && value !== null && value !== '' && (!Number.isInteger(Number(value)) || Number(value) < 0 || Number(value) > 99)) throw new Error(`${key.replace(/_/g, ' ')} must be a whole number of zero or greater.`);
      }
    }
    if (page === 'user-create-ticket.html') {
      payload.status = 'Open'; payload.priority = payload.priority || 'Medium';
      if (!payload.subject) throw new Error('Enter a subject for your request.');
      if (!payload.type || ['select request type', 'incident type'].includes(String(payload.type).toLowerCase())) payload.type = 'Incident';
    }
    if (page === 'add-asset.html') {
      if (!payload.customer_id) throw new Error('Select a customer for this asset.');
      if (payload.project_id) { const project = (lookupData.projects || []).find(p => String(p.project_id) === String(payload.project_id)); if (!project || String(project.customer_id) !== String(payload.customer_id)) throw new Error('Select a project belonging to the selected customer.'); }
    }
    if (page === 'add-team.html') {
      const members = String(payload.member || '').split(',').map(x => x.trim()).filter(Boolean);
      if (members.length < 1) throw new Error('Choose at least 1 Agent for this Support Team.');
      if (members.length > 4) throw new Error('A Support Team can have a maximum of 4 Agents.');
      payload.member = [...new Set(members)].join(', ');
      if ((payload.service_codes || []).length !== 1 || !payload.service_codes[0]) throw new Error('Choose exactly one Service Catalog item for this Support Team.');
    }
    return payload;
  }
  function setField(field, value, page, label) {
    if (value === undefined || value === null) return;
    if (page === 'add-support-plan.html' && label === 'working days') {
      const select = field.querySelector('select');
      if (select) { const raw = String(value).trim(); const normalized = raw.toLowerCase(); const alias = normalized === 'weekdays' ? 'Weekdays' : normalized === 'weekend' ? 'Weekend' : normalized.includes('sunday') ? 'Monday-Sunday' : 'Monday-Friday'; select.value = alias; }
      return;
    }
    const select = field.querySelector('select');
    if (select) {
      if (select.multiple) {
        const vals = (Array.isArray(value) ? value : String(value).split(',')).map(x => String(x).trim());
        [...select.options].forEach(o => o.selected = vals.includes(o.value) || vals.includes(o.textContent.trim()));
      } else {
        let match = [...select.options].find(o => String(o.value) === String(value)) || [...select.options].find(o => o.textContent.trim().toLowerCase() === String(value).toLowerCase());
        if (!match && String(value).trim()) { match = document.createElement('option'); match.value = String(value); match.textContent = String(value); select.appendChild(match); }
        if (match) select.value = match.value;
      }
      return;
    }
    const checks = page === 'add-user.html' && label === 'support teams'
      ? [...field.querySelectorAll('input[name="team_ids"]')]
      : [...field.querySelectorAll('input[type="checkbox"]')];
    if (checks.length) {
      const values = new Set((Array.isArray(value) ? value : [value]).map(v => String(v)));
      checks.forEach(check => { check.checked = values.has(String(check.value)); });
      return;
    }
    const input = field.querySelector('input,textarea'); if (input) input.value = value;
  }
  async function fillEditForm(cfg) {
    if (!idParam || !cfg || cfg.alwaysUpdate) return;
    const form = getMainForm(); if (!form) return;
    const row = await api(`/api/${cfg.resource}/${encodeURIComponent(idParam)}`);
    form.querySelectorAll('.field').forEach(field => {
      const label = labelForField(field), key = cfg.map[label];
      if (customerEditMode) {
        const custom = field.querySelector('[data-customer-edit-field]');
        if (custom && row[custom.dataset.customerEditField] !== undefined) custom.value = row[custom.dataset.customerEditField] || '';
      }
      if (!key) return;
      let value = row[key];
      if (file === 'add-ticket.html' && label === 'request type') {
        value = row.service_code || (lookupData.services || []).find(service =>
          String(service.name || '').trim().toLowerCase() === String(row.type || '').trim().toLowerCase())?.code_id || '';
      }
      if (['start date', 'end date', 'due date', 'created'].includes(label)) {
        const dateInput = field.querySelector('input[type="date"]');
        if (dateInput) dateInput.dataset.originalValue = String(value || '').slice(0, 10);
      }
      if (file === 'add-contract.html' && label === 'support plan') value = row.plan_id;
      if (file === 'add-support-plan.html' && label === 'plan type') {
        const builtins = ['standard', 'premium', 'enterprise', 'vvip'];
        const savedType = String(row.plan_type || 'Standard');
        if (!builtins.includes(savedType.toLowerCase())) {
          value = 'Other';
          const customField = form.querySelector('[data-plan-type-other]');
          if (customField) customField.value = savedType;
        }
      }
      if (file === 'add-user.html' && label === 'support teams') value = row.team_ids || (row.team_id ? [row.team_id] : []);
      if ((file === 'add-team.html' || file === 'add-asset.html') && label === 'service catalog') value = row.service_code_ids || (row.code_id ? [row.code_id] : []);
      if (file === 'add-team.html' && label === 'team members') value = row.member || '';
      setField(field, value, file, label);
      if (['add-service.html', 'add-request-type.html'].includes(file) && label === 'mapped team' && row.mapped_team) {
        const mappedName = String(row.mapped_team).trim();
        const knownTeam = (lookupData.teams || []).find(team => String(team.team_name || '').toLowerCase() === mappedName.toLowerCase() || String(team.team_code || '').toLowerCase() === mappedName.toLowerCase());
        const mappedSelect = field.querySelector('select');
        const customInput = field.querySelector('[data-other-mapped-team]');
        if (!knownTeam && mappedSelect && customInput) { mappedSelect.value = 'other'; customInput.value = mappedName; customInput.hidden = false; customInput.required = true; }
      }
      // Normalize legacy phone values when editing older records so hyphens/spaces
      // do not make an otherwise valid edit fail the new phone-number rules.
      if (label.includes('phone')) {
        const phoneInput = field.querySelector('input');
        if (phoneInput) {
          let raw = String(phoneInput.value || '').replace(/[^0-9+]/g, '');
          const prefix = raw.startsWith('+') ? '+' : '';
          raw = raw.replace(/\+/g, '').slice(0, 15);
          phoneInput.value = prefix + raw;
        }
      }
    });
    if (file === 'add-support-plan.html') {
      setupOtherSupportPlanType();
      form.querySelector('[data-plan-type-select]')?.dispatchEvent(new Event('change', { bubbles: true }));
    }
    if (file === 'add-user.html') {
      const roleSelect = [...form.querySelectorAll('.field')].find(field => labelForField(field) === 'role')?.querySelector('select');
      roleSelect?.dispatchEvent(new Event('change', { bubbles: true }));
      const requestSelect = form.querySelector('[data-agent-request-select]');
      requestSelect?.dispatchEvent(new Event('change', { bubbles: true }));
      const teamSelect = form.querySelector('[data-agent-team-select]');
      if (teamSelect && row.team_id) teamSelect.value = String(row.team_id);
      teamSelect?.dispatchEvent(new Event('change', { bubbles: true }));
      const passwordField = [...form.querySelectorAll('.field')].find(field => labelForField(field) === 'password');
      const passwordInput = passwordField?.querySelector('input');
      if (passwordInput) { passwordInput.required = false; passwordInput.placeholder = 'Leave blank to keep current password'; }
    }
    if (file === 'add-ticket.html' && currentUser.role === 'agent') {
      const agentEditableFields = new Set(['status', 'priority', 'assigned', 'due date']);
      form.querySelectorAll('.field').forEach(field => {
        const label = labelForField(field);
        if (!agentEditableFields.has(label)) field.style.display = 'none';
      });
      const notice = form.closest('.card')?.querySelector('.notice');
      if (notice) notice.textContent = 'Agent edit mode: only Status, Priority, Assigned and Due Date can be changed. Other ticket details are read-only.';
    }
    const submit = form.querySelector('button[type="submit"]'); if (submit) submit.textContent = submit.textContent.replace(/Create|Save|Submit/i, 'Update');
    const title = document.querySelector('h1'); if (title && !title.textContent.toLowerCase().includes('edit')) title.textContent = (file === 'add-ticket.html' ? 'Edit ticket' : `Edit ${title.textContent.trim()}`);
  }
