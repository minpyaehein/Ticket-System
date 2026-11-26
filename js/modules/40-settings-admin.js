  async function handleEmailPage() {
    const isAdmin = currentUser.role === 'admin';
    const adminSections = [...document.querySelectorAll('.admin-only')];
    const metrics = document.getElementById('email-metrics');
    const notice = document.getElementById('email-page-notice');
    const eventDefs = [
      ['ticket_created_support', 'New Ticket - Support Notification', 'Assigned Engineer / Team Members'],
      ['ticket_created_customer', 'New Ticket - Customer Confirmation', 'Ticket Requester / Creator'],
      ['ticket_assigned', 'Assigned / Reassigned', 'Admins + Newly Assigned Engineer'],
      ['customer_reply', 'Customer Reply', 'Admins + Assigned Engineer'],
      ['engineer_public_reply', 'Engineer Public Reply', 'Customer Users'],
      ['internal_note', 'Internal Note', 'Admins + Assigned Agent only · Never send to customers or other team Agents'],
      ['pending_customer', 'Pending Customer', 'Customer Users'],
      ['resolved', 'Resolved', 'Customer Users'],
      ['customer_accepted_resolution', 'Customer Accepted Resolution', 'Admins + Assigned Agent + Customer'],
      ['ticket_reopened', 'Ticket Reopened', 'Admins + Assigned Engineer'],
      ['ticket_closed', 'Ticket Closed', 'Customer Users · Admins always receive activity alerts'],
      ['status_changed', 'Ticket Status Changed', 'Customer Users · Admins always receive activity alerts'],
      ['ticket_updated_customer', 'Ticket Details Updated - Customer', 'Customer Users when Admin edits ticket details'],
      ['response_sla_warning', 'Response SLA Warning', 'Active · Support Plan response SLA warning percentage; checked every minute'],
      ['response_sla_critical', 'Response SLA Critical', 'Active · Support Plan response SLA critical percentage; checked every minute'],
      ['response_sla_breach', 'Response SLA Breach', 'Active · sent when the Support Plan first-response SLA is exceeded'],
      ['resolution_sla_warning', 'Resolution SLA Warning', 'Active · Support Plan resolution target warning percentage; pauses while Pending Customer; checked every minute'],
      ['resolution_sla_critical', 'Resolution SLA Critical', 'Active · Support Plan resolution target critical percentage; pauses while Pending Customer; checked every minute'],
      ['resolution_sla_breach', 'Resolution SLA Breach', 'Active · sent when the Support Plan resolution target is exceeded; clock pauses while Pending Customer'],
      ['unassigned_team_queue', 'Unassigned Admin Dispatch Queue', 'Admins only; Agents see a ticket after assignment'],
      ['pending_customer_reminder', 'Pending Customer Reminder', 'Active · sent once after the configured number of Pending Customer minutes'],
      ['resolution_confirmation_reminder', 'Resolution Confirmation Reminder', 'Active · sent once after the configured number of Resolved minutes'],
      ['auto_closed', 'Auto Closed', 'Active · closes Resolved tickets after the configured minutes; 0 disables it'],
      ['daily_summary', 'Daily Ticket Summary', 'Admin / Agent digest · daily at 09:00 Asia/Yangon']
    ];
    const customerPersonalDefs = [
      ['ticket_created', 'New ticket confirmation', 'When your ticket is created'],
      ['status_changed', 'Ticket status updates', 'When your ticket status changes'],
      ['new_reply', 'Engineer public replies', 'When a support engineer posts a public reply'],
      ['ticket_resolved', 'Ticket resolved', 'When your ticket is resolved']
    ];
    const staffPersonalDefs = [
      ['ticket_assigned', 'Ticket assignment', 'When a ticket is assigned to you'],
      ['new_reply', 'Customer replies', 'When a customer replies to your assigned ticket'],
      ['internal_note', 'Internal notes', 'Staff-only notes for your assigned tickets'],
      ['sla_approaching', 'SLA reminders', 'When a ticket due date approaches'],
      ['daily_summary', 'Daily ticket summary', 'Admin / Agent digest']
    ];
    const personalDefs = currentUser.role === 'customer' ? customerPersonalDefs : staffPersonalDefs;
    const variables = ['recipient_name', 'recipient_email', 'event_label', 'event_message', 'event_details', 'reply_message', 'requester_name', 'requester_email', 'ticket_no', 'ticket_subject', 'ticket_description', 'customer_name', 'project_name', 'contract_no', 'service_name', 'priority', 'status', 'team_name', 'assigned_to', 'due_date', 'created_by_name', 'created_by_email', 'created_timestamp', 'resolution'];
    const eventGrid = document.getElementById('email-event-grid');
    const templateSelect = document.getElementById('template-event');
    const templateVars = document.getElementById('template-vars');
    let settings = { event_rules: {}, templates: {} };
    let activeTemplateKey = 'ticket_created_support__admin';
    let activeTemplateField = 'template-body';
    const safe = (v) => String(v ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
    const defaultTemplate = (key) => settings.default_templates?.[key] || ({ subject: '[Golden Pride] {{event_label}} - {{ticket_no}} - {{ticket_subject}}', body: 'Dear {{recipient_name}},\n\n{{event_message}}\n\nTicket No: {{ticket_no}}\nSubject: {{ticket_subject}}\nCustomer: {{customer_name}}\nPriority: {{priority}}\nStatus: {{status}}\nSupport Team: {{team_name}}\nAssigned To: {{assigned_to}}\nDue Date: {{due_date}}\n\nGolden Pride Support' });
    function renderTemplateOptions(options) {
      if (!templateSelect) return; templateSelect.replaceChildren();
      (options || []).forEach(item => { const opt = document.createElement('option'); opt.value = item.key; opt.textContent = item.label; templateSelect.appendChild(opt); });
    }
    function renderEventDefs(target, defs, rules, isPersonal = false) {
      if (!target) return; target.replaceChildren();
      defs.forEach(([key, label, detail]) => {
        const row = document.createElement('label'); row.className = 'event-option';
        const checkbox = document.createElement('input'); checkbox.type = 'checkbox'; checkbox.dataset.eventKey = key; checkbox.checked = rules?.[key] !== false;
        const text = document.createElement('span'); text.innerHTML = `<strong>${safe(label)}</strong><small>${safe(detail)}</small>`;
        row.append(checkbox, text); target.appendChild(row);
      });
    }
    function fillTemplate(key) {
      activeTemplateKey = key;
      const tpl = settings.templates?.[key] || defaultTemplate(key);
      const subject = document.getElementById('template-subject'); const body = document.getElementById('template-body');
      if (subject) subject.value = tpl.subject || ''; if (body) body.value = tpl.body || '';
    }
    // Apply the authenticated role before revealing any part of this shared page.
    // The initial HTML also carries hidden attributes, so Admin controls cannot flash
    // while /api/auth/me is being checked during a refresh.
    adminSections.forEach(section => {
      section.hidden = !isAdmin;
      section.classList.toggle('hidden', !isAdmin);
    });
    if (metrics) {
      metrics.hidden = !isAdmin;
      metrics.classList.toggle('hidden', !isAdmin);
    }
    const personal = document.getElementById('personal-preferences');
    if (personal) {
      personal.hidden = isAdmin;
      personal.classList.toggle('hidden', isAdmin);
    }

    if (!isAdmin) {
      if (notice) notice.textContent = 'Your own email preferences are shown below. Admin manages SMTP settings and global event rules. Your in-app notifications still appear in the notification bell.';
      try {
        const result = await api('/api/notification-preferences');
        renderEventDefs(document.getElementById('personal-pref-grid'), personalDefs, result.preferences || {}, true);
      } catch (e) { toast(e.message, 'error'); }
      document.getElementById('save-personal-prefs')?.addEventListener('click', async () => {
        const preferences = {}; document.querySelectorAll('#personal-pref-grid input[data-event-key]').forEach(cb => preferences[cb.dataset.eventKey] = cb.checked);
        try { const result = await api('/api/notification-preferences', { method: 'PUT', body: JSON.stringify({ preferences }) }); toast(result.message || 'Preferences saved.'); } catch (e) { toast(e.message, 'error'); }
      });
      return;
    }
    renderEventDefs(eventGrid, eventDefs, {});
    if (templateVars) {
      templateVars.replaceChildren(); variables.forEach(name => {
        const chip = document.createElement('button'); chip.type = 'button'; chip.className = 'var-chip'; chip.textContent = '{{' + name + '}}'; chip.addEventListener('click', () => {
          const field = document.activeElement?.id === 'template-subject' ? document.getElementById('template-subject') : document.getElementById(activeTemplateField);
          if (!field) return; const token = '{{' + name + '}}'; const start = field.selectionStart ?? field.value.length; const end = field.selectionEnd ?? start; field.setRangeText(token, start, end, 'end'); field.focus();
        }); templateVars.appendChild(chip);
      });
    }
    document.getElementById('template-subject')?.addEventListener('focus', () => activeTemplateField = 'template-subject');
    document.getElementById('template-body')?.addEventListener('focus', () => activeTemplateField = 'template-body');
    templateSelect?.addEventListener('change', () => fillTemplate(templateSelect.value));

    // The scheduler stores all durations as minutes. These controls let Admin choose
    // minutes, hours, or days without changing the existing backend timer format.
    const durationUnitMinutes = { minutes: 1, hours: 60, days: 1440 };
    function updateDurationLimit(prefix, maxMinutes, allowZero = false) {
      const input = document.getElementById(`${prefix}-value`);
      const unit = document.getElementById(`${prefix}-unit`);
      if (!input || !unit) return;
      input.min = allowZero ? '0' : '1';
      input.max = String(Math.floor(maxMinutes / (durationUnitMinutes[unit.value] || 1)));
    }
    function setDurationControl(prefix, totalMinutes, maxMinutes, allowZero = false) {
      const input = document.getElementById(`${prefix}-value`);
      const unit = document.getElementById(`${prefix}-unit`);
      if (!input || !unit) return;
      const minutes = Math.max(0, Math.trunc(Number(totalMinutes) || 0));
      let selectedUnit = 'minutes';
      if (!(allowZero && minutes === 0)) {
        if (minutes > 0 && minutes % 1440 === 0) selectedUnit = 'days';
        else if (minutes > 0 && minutes % 60 === 0) selectedUnit = 'hours';
      }
      unit.value = selectedUnit;
      input.value = String(minutes / (durationUnitMinutes[selectedUnit] || 1));
      updateDurationLimit(prefix, maxMinutes, allowZero);
    }
    function readDurationMinutes(prefix, maxMinutes, allowZero = false) {
      const input = document.getElementById(`${prefix}-value`);
      const unit = document.getElementById(`${prefix}-unit`);
      if (!input || !unit) throw new Error(`Missing automation timing control: ${prefix}.`);
      const raw = String(input.value ?? '').trim();
      const amount = Number(raw);
      if (raw === '' || !Number.isSafeInteger(amount)) throw new Error('Enter a whole number for each automation duration.');
      const minimum = allowZero ? 0 : 1;
      if (amount < minimum) throw new Error(`${prefix.replace(/-/g, ' ')} must be at least ${minimum}.`);
      const factor = durationUnitMinutes[unit.value];
      if (!factor) throw new Error('Choose Minutes, Hours, or Days for each automation duration.');
      const minutes = amount * factor;
      if (!Number.isSafeInteger(minutes) || minutes > maxMinutes) throw new Error(`${prefix.replace(/-/g, ' ')} cannot exceed ${Math.floor(maxMinutes / 1440)} days.`);
      return minutes;
    }
    function readAutomationTiming() {
      return {
        pending_customer_reminder_minutes: readDurationMinutes('pending-reminder', 43200, false),
        resolution_confirmation_reminder_minutes: readDurationMinutes('resolution-reminder', 43200, false),
        auto_close_resolved_minutes: readDurationMinutes('auto-close', 129600, true)
      };
    }
    for (const [prefix, maxMinutes, allowZero] of [['pending-reminder', 43200, false], ['resolution-reminder', 43200, false], ['auto-close', 129600, true]]) {
      document.getElementById(`${prefix}-unit`)?.addEventListener('change', () => updateDurationLimit(prefix, maxMinutes, allowZero));
    }

    try {
      settings = await api('/api/email-settings');
      renderTemplateOptions(settings.template_options || []);
      document.getElementById('smtp-enabled').checked = Boolean(settings.enabled);
      const host = String(settings.smtp_host || '').trim().toLowerCase();
      const provider = host === 'smtp.gmail.com' ? 'gmail' : host === 'smtp.office365.com' ? 'outlook' : 'custom';
      document.getElementById('smtp-provider').value = provider;
      document.getElementById('smtp-host').value = settings.smtp_host || (provider === 'gmail' ? 'smtp.gmail.com' : '');
      document.getElementById('smtp-port').value = settings.smtp_port || 587;
      document.getElementById('smtp-username').value = settings.smtp_username || '';
      document.getElementById('smtp-password').value = '';
      document.getElementById('smtp-from-email').value = settings.from_email || '';
      document.getElementById('smtp-from-name').value = settings.from_name || 'Golden Pride Ticket System';
      document.getElementById('smtp-reply-to').value = settings.reply_to_email || '';
      document.getElementById('smtp-ssl').checked = (settings.encryption || 'STARTTLS') === 'SSL / TLS';
      document.getElementById('smtp-starttls').checked = (settings.encryption || 'STARTTLS') === 'STARTTLS';
      document.getElementById('smtp-self-signed').checked = Boolean(settings.allow_self_signed_certificate);
      document.getElementById('smtp-auth').value = settings.authentication || 'Username and password';
      document.getElementById('smtp-max-retry').value = settings.max_retry ?? 3;
      document.getElementById('smtp-retry-delay').value = settings.retry_delay ?? 5;
      document.getElementById('smtp-timeout').value = settings.timeout || 15;
      setDurationControl('pending-reminder', settings.pending_customer_reminder_minutes ?? 5, 43200, false);
      setDurationControl('resolution-reminder', settings.resolution_confirmation_reminder_minutes ?? 5, 43200, false);
      setDurationControl('auto-close', settings.auto_close_resolved_minutes ?? 10, 129600, true);
      settings.templates = settings.templates || {}; settings.event_rules = settings.event_rules || {};
      renderEventDefs(eventGrid, eventDefs, settings.event_rules);
      // Each event switch is persisted immediately; its rule applies to the next matching ticket event.
      let ruleSaveChain = Promise.resolve();
      eventGrid?.addEventListener('change', ev => {
        const checkbox = ev.target.closest('input[data-event-key]'); if (!checkbox) return;
        settings.event_rules = { ...(settings.event_rules || {}), [checkbox.dataset.eventKey]: checkbox.checked };
        checkbox.disabled = true;
        ruleSaveChain = ruleSaveChain.then(async () => {
          const payload = { ...settings, event_rules: { ...settings.event_rules }, smtp_password: '' };
          const result = await api('/api/email-settings', { method: 'PUT', body: JSON.stringify(payload) });
          toast(`${checkbox.dataset.eventKey.replace(/_/g, ' ')} rule saved. It will apply when that ticket event happens.`);
          return result;
        }).catch(e => { toast(e.message, 'error'); }).finally(() => { checkbox.disabled = false; });
      });
      const saveRulesAction = document.getElementById('save-rules')?.closest('.action-line'); if (saveRulesAction) saveRulesAction.style.display = 'none';
      if (templateSelect && templateSelect.options.length) {
        const preferred = 'ticket_created_support__admin';
        templateSelect.value = settings.templates?.[preferred] ? preferred : templateSelect.options[0].value;
      }
      fillTemplate(templateSelect?.value || activeTemplateKey);
    } catch (e) { toast(e.message, 'error'); }

    const sslCheck = document.getElementById('smtp-ssl');
    const starttlsCheck = document.getElementById('smtp-starttls');
    sslCheck?.addEventListener('change', () => { if (sslCheck.checked) starttlsCheck.checked = false; });
    starttlsCheck?.addEventListener('change', () => { if (starttlsCheck.checked) sslCheck.checked = false; });
    document.getElementById('smtp-provider')?.addEventListener('change', ev => {
      const val = ev.target.value; const host = document.getElementById('smtp-host'); const port = document.getElementById('smtp-port');
      if (val === 'gmail') { host.value = 'smtp.gmail.com'; port.value = 587; sslCheck.checked = false; starttlsCheck.checked = true; }
      else if (val === 'outlook') { host.value = 'smtp.office365.com'; port.value = 587; sslCheck.checked = false; starttlsCheck.checked = true; }
    });
    document.getElementById('save-smtp')?.addEventListener('click', async () => {
      const val = id => document.getElementById(id)?.value ?? '';
      let automationTiming;
      try { automationTiming = readAutomationTiming(); } catch (e) { toast(e.message, 'error'); return; }
      const payload = {
        smtp_host: val('smtp-host').trim(), smtp_port: Number(val('smtp-port') || 587),
        encryption: document.getElementById('smtp-ssl').checked ? 'SSL / TLS' : document.getElementById('smtp-starttls').checked ? 'STARTTLS' : 'None',
        authentication: val('smtp-auth'), allow_self_signed_certificate: document.getElementById('smtp-self-signed').checked,
        smtp_username: val('smtp-username').trim(), smtp_password: val('smtp-password'),
        from_name: val('smtp-from-name').trim() || 'Golden Pride Ticket System', from_email: val('smtp-from-email').trim(),
        reply_to_email: val('smtp-reply-to').trim(), timeout: Number(val('smtp-timeout') || 15),
        enabled: document.getElementById('smtp-enabled').checked,
        max_retry: Number(val('smtp-max-retry') || 3), retry_delay: Number(val('smtp-retry-delay') || 5),
        ...readAutomationTiming(),
        event_rules: settings.event_rules || {}, templates: settings.templates || {}
      };
      const emailRe = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
      if (payload.enabled && (!payload.smtp_host || !emailRe.test(payload.from_email))) { toast('Enter SMTP host and a valid From email before enabling the service.', 'error'); return; }
      if (payload.from_email && !emailRe.test(payload.from_email)) { toast('Enter a valid From email address.', 'error'); return; }
      try { const result = await api('/api/email-settings', { method: 'PUT', body: JSON.stringify(payload) }); settings = { ...settings, ...payload }; document.getElementById('smtp-password').value = ''; toast(result.message || 'SMTP settings saved.'); await loadDelivery(); } catch (e) { toast(e.message, 'error'); }
    });
    document.getElementById('save-automation-timing')?.addEventListener('click', async () => {
      let timing;
      try { timing = readAutomationTiming(); } catch (e) { toast(e.message, 'error'); return; }
      const payload = {
        ...settings, ...timing,
        event_rules: settings.event_rules || {}, templates: settings.templates || {}, smtp_password: ''
      };
      try { const result = await api('/api/email-settings', { method: 'PUT', body: JSON.stringify(payload) }); settings = { ...settings, ...timing }; toast(result.message || 'Automation timing saved.'); } catch (e) { toast(e.message, 'error'); }
    });
    document.getElementById('send-test')?.addEventListener('click', async () => {
      const recipient = document.getElementById('test-recipient').value.trim(); const resultEl = document.getElementById('smtp-test-result');
      try { const result = await api('/api/email-settings/test', { method: 'POST', body: JSON.stringify({ recipient }) }); if (resultEl) resultEl.textContent = result.message; toast(result.message); await loadDelivery(); } catch (e) { if (resultEl) resultEl.textContent = e.message; toast(e.message, 'error'); await loadDelivery(); }
    });
    document.getElementById('save-rules')?.addEventListener('click', async () => {
      const rules = { ...settings.event_rules }; document.querySelectorAll('#email-event-grid input[data-event-key]').forEach(cb => rules[cb.dataset.eventKey] = cb.checked);
      const payload = { ...settings, event_rules: rules, smtp_password: '' };
      try { const result = await api('/api/email-settings', { method: 'PUT', body: JSON.stringify(payload) }); settings.event_rules = rules; toast(result.message || 'Event rules saved.'); } catch (e) { toast(e.message, 'error'); }
    });
    document.getElementById('save-template')?.addEventListener('click', async () => {
      const key = templateSelect?.value || activeTemplateKey;
      settings.templates = settings.templates || {}; settings.templates[key] = { subject: document.getElementById('template-subject').value, body: document.getElementById('template-body').value };
      const payload = { ...settings, smtp_password: '' };
      try { const result = await api('/api/email-settings', { method: 'PUT', body: JSON.stringify(payload) }); toast('Email template saved.'); } catch (e) { toast(e.message, 'error'); }
    });
    document.getElementById('reset-template')?.addEventListener('click', () => { const key = templateSelect?.value || activeTemplateKey; settings.templates[key] = defaultTemplate(key); fillTemplate(key); });
    document.getElementById('reset-smtp')?.addEventListener('click', () => location.reload());
    document.getElementById('process-queue')?.addEventListener('click', async () => { try { const r = await api('/api/email-deliveries/process-queue', { method: 'POST' }); toast(r.message); await loadDelivery(); } catch (e) { toast(e.message, 'error'); } });
    document.getElementById('retry-failed')?.addEventListener('click', async () => { try { const r = await api('/api/email-deliveries/retry-failed', { method: 'POST' }); toast(r.message); await loadDelivery(); } catch (e) { toast(e.message, 'error'); } });
    let currentDeliveryPage = 1;
    const deliveryPageSize = 10;
    const deliveryFoot = document.getElementById('delivery-pagination');
    const deliveryCount = document.getElementById('delivery-count');
    const deliveryButtons = document.getElementById('delivery-page-buttons');
    document.getElementById('refresh-delivery')?.addEventListener('click', () => loadDelivery(currentDeliveryPage));
    document.getElementById('delivery-filter')?.addEventListener('change', () => { currentDeliveryPage = 1; loadDelivery(1); });
    function drawDeliveryPagination(total) {
      if (!deliveryButtons) return;
      const pages = Math.max(1, Math.ceil(total / deliveryPageSize));
      currentDeliveryPage = Math.min(currentDeliveryPage, pages);
      const first = total ? (currentDeliveryPage - 1) * deliveryPageSize + 1 : 0;
      if (deliveryCount) deliveryCount.textContent = `Showing ${first}–${Math.min(currentDeliveryPage * deliveryPageSize, total)} of ${total} email delivery records`;
      deliveryButtons.replaceChildren();
      const add = (label, target, current = false, disabled = false) => {
        const btn = document.createElement('button'); btn.type = 'button'; btn.className = 'gp-ticket-page-btn'; btn.textContent = label;
        if (current) { btn.classList.add('is-current'); btn.setAttribute('aria-current', 'page'); }
        btn.disabled = disabled; btn.addEventListener('click', () => { if (target >= 1 && target <= pages && target !== currentDeliveryPage) loadDelivery(target); }); deliveryButtons.appendChild(btn);
      };
      add('Previous', currentDeliveryPage - 1, false, currentDeliveryPage <= 1);
      let shown = pages <= 7 ? Array.from({ length: pages }, (_, i) => i + 1) : [1, ...Array.from({ length: Math.min(3, pages - 2) }, (_, i) => Math.max(2, Math.min(pages - 1, currentDeliveryPage - 1)) + i).filter(p => p < pages), pages];
      shown = [...new Set(shown)].sort((a, b) => a - b);
      let previous = 0;
      shown.forEach(page => { if (previous && page - previous > 1) { const dots = document.createElement('span'); dots.className = 'gp-ticket-page-dots'; dots.textContent = '…'; deliveryButtons.appendChild(dots); } add(String(page), page, page === currentDeliveryPage); previous = page; });
      add('Next', currentDeliveryPage + 1, false, currentDeliveryPage >= pages);
    }
    async function loadDelivery(page = currentDeliveryPage) {
      currentDeliveryPage = Math.max(1, Number(page) || 1);
      try {
        const filter = document.getElementById('delivery-filter')?.value || 'all';
        const offset = (currentDeliveryPage - 1) * deliveryPageSize;
        const data = await api('/api/email-deliveries?limit=' + deliveryPageSize + '&offset=' + offset + '&status=' + encodeURIComponent(filter));
        const maxPage = Math.max(1, Math.ceil((Number(data.total) || 0) / deliveryPageSize));
        if (currentDeliveryPage > maxPage) return loadDelivery(maxPage);
        const stats = data.stats || {};
        document.getElementById('metric-queued').textContent = stats.queued ?? 0;
        document.getElementById('metric-retry').textContent = stats.retry ?? 0;
        document.getElementById('metric-sent').textContent = stats.sent_24h ?? 0;
        document.getElementById('metric-failed').textContent = stats.failed_24h ?? 0;
        const tbody = document.getElementById('delivery-rows'); tbody.replaceChildren();
        if (!data.items?.length) { const tr = document.createElement('tr'); const td = document.createElement('td'); td.colSpan = 8; td.className = 'muted'; td.textContent = 'No email delivery records found.'; tr.appendChild(td); tbody.appendChild(tr); drawDeliveryPagination(Number(data.total) || 0); return; }
        data.items.forEach(item => {
          const tr = document.createElement('tr'); const dateText = fmtMyanmarDateTime(item.created_at); const sentText = fmtMyanmarDateTime(item.sent_at);
          const vals = [dateText, item.ticket_code || '—', item.event_label || item.event_key, `${item.recipient_name || ''}${item.recipient_name ? ' · ' : ''}${item.recipient_email || ''}`, item.status, item.attempts ?? 0, sentText, item.error || '—'];
          vals.forEach((v, i) => { const td = document.createElement('td'); if (i === 4) { const span = document.createElement('span'); span.className = 'status-pill ' + (item.status === 'failed' ? 'failed' : item.status === 'queued' ? 'queued' : ''); span.textContent = item.status; td.appendChild(span); } else td.textContent = String(v); tr.appendChild(td); }); tbody.appendChild(tr);
        });
        drawDeliveryPagination(Number(data.total) || 0);
      } catch (e) { const tbody = document.getElementById('delivery-rows'); if (tbody) tbody.innerHTML = '<tr><td colspan="8" class="muted">' + safe(e.message) + '</td></tr>'; if (deliveryCount) deliveryCount.textContent = 'Unable to load email delivery records'; }
    }
    await loadDelivery();
  }

  async function handleChangePassword() {
    if (file !== 'change-password.html') return; const form = document.getElementById('change-password-form'); if (!form) return;
    form.addEventListener('submit', async ev => {
      ev.preventDefault(); if (form.dataset.gpSubmitting === '1') return;
      const current = form.querySelector('[name="current_password"]')?.value || '';
      const next = form.querySelector('[name="new_password"]')?.value || '';
      const confirm = form.querySelector('[name="confirm_password"]')?.value || '';
      if (next !== confirm) { toast('The new password and confirmation do not match.', 'error'); return; }
      if (next.length < 10) { toast('Use at least 10 characters for the new password.', 'error'); return; }
      form.dataset.gpSubmitting = '1'; const button = form.querySelector('[type="submit"]'); const oldText = button?.textContent || 'Save password';
      if (button) { button.disabled = true; button.textContent = 'Saving…'; }
      try { const result = await api('/api/auth/change-password', { method: 'POST', body: JSON.stringify({ current_password: current, new_password: next }) }); currentUser.must_change_password = false; toast(result.message); location.href = homeByRole[currentUser.role] || 'login.html'; }
      catch (e) { toast(e.message, 'error'); }
      finally { form.dataset.gpSubmitting = '0'; if (button && button.isConnected) { button.disabled = false; button.textContent = oldText; } }
    });
  }

  async function handleRoleForm() {
    if (file !== 'add-role.html' || currentUser.role !== 'admin') return;
    const form = getMainForm(); if (!form) return;
    form.addEventListener('submit', async ev => {
      ev.preventDefault(); if (form.dataset.gpSubmitting === '1') return;
      const fields = [...form.querySelectorAll('.field')]; const roleName = fields[0]?.querySelector('input')?.value.trim(); const description = fields[1]?.querySelector('input')?.value.trim() || '';
      if (!roleName) { toast('Enter a role name.', 'error'); return; }
      const permissions = {};
      form.querySelectorAll('tbody tr').forEach(tr => { const cells = [...tr.children]; const module = cells[0]?.textContent.trim(); if (!module) return; permissions[module] = cells.slice(1).map(td => !!td.querySelector('input[type="checkbox"]:checked')); });
      form.dataset.gpSubmitting = '1'; const button = form.querySelector('[type="submit"]'); const oldText = button?.textContent || 'Save role';
      if (button) { button.disabled = true; button.textContent = 'Saving…'; }
      try { await api('/api/role-permissions', { method: 'POST', body: JSON.stringify({ role_key: roleName, description, permissions }) }); toast('Role permissions saved.'); location.href = 'roles-access.html'; }
      catch (e) { toast(e.message, 'error'); }
      finally { form.dataset.gpSubmitting = '0'; if (button && button.isConnected) { button.disabled = false; button.textContent = oldText; } }
    });
  }
  function setupUserTeamField() {
    if (file !== 'add-user.html') return;
    const form = getMainForm(); if (!form) return;
    const fields = [...form.querySelectorAll('.field')];
    const roleSelect = fields.find(f => labelForField(f) === 'role')?.querySelector('select');
    const teamField = fields.find(f => labelForField(f) === 'support team');
    const teamSelect = teamField?.querySelector('[data-agent-team-select]');
    if (!roleSelect || !teamField || !teamSelect) return;

    const selected = teamSelect.value;
    teamSelect.replaceChildren();
    const placeholder = document.createElement('option'); placeholder.value = ''; placeholder.textContent = 'Select support team'; teamSelect.appendChild(placeholder);
    (lookupData.teams || []).forEach(team => {
      const option = document.createElement('option'); option.value = String(team.team_id); option.textContent = team.team_name; teamSelect.appendChild(option);
    });
    const otherOption = document.createElement('option'); otherOption.value = '__other__'; otherOption.textContent = 'Other (Add new team)'; teamSelect.appendChild(otherOption);
    if ([...teamSelect.options].some(option => option.value === selected)) teamSelect.value = selected;

    const requestField = fields.find(f => labelForField(f) === 'request type');
    const requestSelect = requestField?.querySelector('[data-agent-request-select]') || requestField?.querySelector('select');
    // One Support Team and one Request Type per Agent; never allow multi-select.
    teamSelect.multiple = false; teamSelect.removeAttribute('multiple');
    if (requestSelect) { requestSelect.multiple = false; requestSelect.removeAttribute('multiple'); }
    const otherTeamField = form.querySelector('[data-user-other-team-field]');
    const otherTeamInput = form.querySelector('[data-user-other-team-name]');

    const syncRequest = () => {
      const agent = String(roleSelect.value || 'customer').toLowerCase() === 'agent';
      if (requestField) requestField.style.display = agent ? '' : 'none';
      if (requestSelect) { requestSelect.disabled = !agent; requestSelect.required = agent; }
    };
    const syncTeam = () => {
      const agent = String(roleSelect.value || 'customer').toLowerCase() === 'agent';
      teamField.style.display = agent ? '' : 'none';
      teamSelect.disabled = !agent;
      teamSelect.required = agent;
      if (!agent) teamSelect.value = '';
      const other = agent && teamSelect.value === '__other__';
      if (otherTeamField) { otherTeamField.hidden = !other; otherTeamField.style.display = other ? '' : 'none'; }
      if (otherTeamInput) { otherTeamInput.required = !!other; if (!other) otherTeamInput.value = ''; }
    };
    roleSelect.addEventListener('change', () => { syncTeam(); syncRequest(); });
    teamSelect.addEventListener('change', syncTeam);
    requestSelect?.addEventListener('change', syncRequest);
    syncTeam(); syncRequest();
  }

  function setupTeamMembersField() {
    if (file !== 'add-team.html') return;
    const form = getMainForm(); if (!form) return;
    const field = [...form.querySelectorAll('.field')].find(f => labelForField(f) === 'team members');
    const select = field?.querySelector('select'); if (!select) return;
    select.multiple = true; select.size = 4; select.required = true;
    select.setAttribute('aria-label', 'Select 1 to 4 active Agents for this team');
    select.title = 'Select at least 1 and at most 4 Agents. Hold Ctrl (Windows) while selecting multiple names.';
    select.addEventListener('change', () => {
      const selected = [...select.selectedOptions];
      if (selected.length > 4) {
        selected[selected.length - 1].selected = false;
        toast('A Support Team can have a maximum of 4 Agents.', 'error');
      }
      const selectedCount = [...select.selectedOptions].length;
      let hint = field.querySelector('[data-team-member-hint]');
      if (!hint) { hint = document.createElement('small'); hint.dataset.teamMemberHint = ''; hint.className = 'field-hint'; field.appendChild(hint); }
      hint.textContent = `${selectedCount} selected · choose 1–4 Agents`;
    });
    let hint = field.querySelector('[data-team-member-hint]');
    if (!hint) { hint = document.createElement('small'); hint.dataset.teamMemberHint = ''; hint.className = 'field-hint'; field.appendChild(hint); }
    hint.textContent = '0 selected · choose 1–4 Agents';
    const serviceField = [...form.querySelectorAll('.field')].find(f => labelForField(f) === 'service catalog');
    const serviceSelect = serviceField?.querySelector('select');
    if (serviceSelect) {
      serviceSelect.multiple = false; serviceSelect.size = 1; serviceSelect.required = true;
      if (serviceSelect.options.length) serviceSelect.options[0].textContent = 'Select one Service Catalog item';
    }
  }

  function setupOtherSupportPlanType() {
    if (file !== 'add-support-plan.html') return;
    const form = getMainForm(); if (!form) return;
    const select = form.querySelector('[data-plan-type-select]');
    const field = form.querySelector('[data-plan-type-other-field]');
    const input = form.querySelector('[data-plan-type-other]');
    if (!select || !field || !input) return;
    const sync = () => {
      const show = String(select.value || '').toLowerCase() === 'other';
      field.hidden = !show;
      field.style.display = show ? '' : 'none';
      input.required = show;
      if (!show) input.value = '';
    };
    if (!select.dataset.planTypeBound) { select.addEventListener('change', sync); select.dataset.planTypeBound = '1'; }
    sync();
  }

  function setupOtherMappedTeam() {
    if (!['add-service.html', 'add-request-type.html'].includes(file)) return;
    const form = getMainForm(); if (!form) return;
    const field = [...form.querySelectorAll('.field')].find(f => labelForField(f) === 'mapped team');
    const select = field?.querySelector('select'); if (!select) return;
    const savedValue = select.value;
    let input = field.querySelector('[data-other-mapped-team]');
    if (!input) {
      input = document.createElement('input'); input.className = 'input'; input.type = 'text'; input.maxLength = 160;
      input.placeholder = 'Enter the new Support Team name'; input.dataset.otherMappedTeam = ''; input.hidden = true;
      input.style.marginTop = '10px'; select.insertAdjacentElement('afterend', input);
    }
    if (![...select.options].some(o => o.value === 'other')) {
      const other = document.createElement('option'); other.value = 'other'; other.textContent = 'Other — enter a new team'; select.appendChild(other);
    }
    // If an existing saved team name is not present in Teams yet, keep it editable as Other.
    if (savedValue && savedValue !== 'other' && ![...select.options].some(o => o.value === savedValue)) {
      select.value = 'other'; input.value = savedValue;
    }
    const sync = () => { const other = select.value === 'other'; input.hidden = !other; input.required = other; if (!other) input.value = ''; };
    select.addEventListener('change', sync); sync();
  }

  function setupOtherServiceCategory() {
    if (!['add-service.html', 'add-request-type.html'].includes(file)) return;
    const form = getMainForm(); if (!form) return;
    const field = [...form.querySelectorAll('.field')].find(f => labelForField(f) === 'category');
    const select = field?.querySelector('select'); if (!select) return;
    let input = field.querySelector('[data-other-category]');
    if (!input) {
      input = document.createElement('input'); input.className = 'input'; input.type = 'text'; input.maxLength = 100;
      input.placeholder = 'Enter the new category name'; input.dataset.otherCategory = ''; input.hidden = true;
      input.style.marginTop = '10px'; select.insertAdjacentElement('afterend', input);
    }
    const sync = () => { const other = select.value.trim().toLowerCase() === 'other'; input.hidden = !other; input.required = other; if (!other) input.value = ''; };
    select.addEventListener('change', sync); sync();
  }

  function setupUserStatusActions() {
    if (file !== 'add-user.html' || !idParam || currentUser?.role !== 'admin') return;
    const form = getMainForm(); if (!form) return;
    const roleSelect = [...form.querySelectorAll('.field')].find(f => labelForField(f) === 'role')?.querySelector('select');
    const role = String(roleSelect?.value || '').toLowerCase();
    if (role !== 'agent') return;
    let area = form.querySelector('[data-agent-account-actions]');
    if (!area) { area = document.createElement('div'); area.dataset.agentAccountActions = ''; area.className = 'form-actions'; area.style.justifyContent = 'flex-start'; form.querySelector('.form-actions')?.before(area); }
    if (area.dataset.ready) return; area.dataset.ready = '1';
    const deactivate = document.createElement('button'); deactivate.type = 'button'; deactivate.className = 'btn'; deactivate.textContent = 'Deactivate Agent';
    const reset = document.createElement('button'); reset.type = 'button'; reset.className = 'btn btn-primary'; reset.textContent = 'Reset Password';
    deactivate.addEventListener('click', async () => { const active = await api(`/api/users/${encodeURIComponent(idParam)}`).then(r => r.active).catch(() => true); const confirmed = await confirmDialog(`${active ? 'Deactivate' : 'Activate'} this Agent account?`, ` ${active ? 'Deactivate' : 'Activate'} Agent`); if (!confirmed) return; deactivate.disabled = true; try { const result = await api(`/api/users/${encodeURIComponent(idParam)}/toggle-active`, { method: 'POST' }); toast(result.message); deactivate.textContent = result.active ? 'Deactivate Agent' : 'Activate Agent'; } catch (e) { toast(e.message, 'error'); } finally { deactivate.disabled = false; } });
    reset.addEventListener('click', async () => { const confirmed = await confirmDialog('Reset this Agent password and email a temporary password to their registered email address?', 'Reset Agent Password'); if (!confirmed) return; reset.disabled = true; try { const result = await api(`/api/users/${encodeURIComponent(idParam)}/reset-password`, { method: 'POST' }); toast(result.message); } catch (e) { toast(e.message, 'error'); } finally { reset.disabled = false; } });
    area.append(deactivate, reset);
    api(`/api/users/${encodeURIComponent(idParam)}`).then(user => { deactivate.textContent = user.active ? 'Deactivate Agent' : 'Activate Agent'; }).catch(() => { });
  }
  function showAuditDetails(row) {
    if (!row) return;
    let dialog = document.getElementById('audit-details-dialog');
    if (!dialog) {
      dialog = document.createElement('dialog'); dialog.id = 'audit-details-dialog'; dialog.className = 'audit-changes-dialog';
      Object.assign(dialog.style, { width: 'min(900px,calc(100vw - 32px))', maxHeight: '85vh', padding: '0', border: '1px solid #dbe2ec', borderRadius: '16px', boxShadow: '0 24px 70px #14213a44', color: 'var(--text,#1b2940)', overflow: 'auto' });
      document.body.appendChild(dialog);
      dialog.addEventListener('click', ev => { if (ev.target === dialog) { try { dialog.close(); } catch (_) { dialog.removeAttribute('open'); } } });
    }
    const changes = row.changes && typeof row.changes === 'object' ? row.changes : {};
    const rows = Object.entries(changes);
    const valueText = value => {
      if (value === null || value === undefined || value === '') return '—';
      if (typeof value === 'object') return JSON.stringify(value, null, 2);
      return String(value);
    };
    const changeHtml = rows.length ? `<div class="table-wrap"><table class="audit-change-grid"><thead><tr><th>Field</th><th>Previous value</th><th>New value</th></tr></thead><tbody>${rows.map(([key, change]) => `<tr><td><strong>${esc(key.replace(/_/g, ' '))}</strong></td><td><pre style="white-space:pre-wrap;margin:0;font:inherit">${esc(valueText(change?.from))}</pre></td><td><pre style="white-space:pre-wrap;margin:0;font:inherit">${esc(valueText(change?.to))}</pre></td></tr>`).join('')}</tbody></table></div>` : `<div class="audit-empty">No field-by-field change data was recorded for this activity.</div>`;
    dialog.innerHTML = `<div class="audit-dialog-head" style="display:flex;justify-content:space-between;align-items:center;padding:18px 22px;border-bottom:1px solid #e8edf4;position:sticky;top:0;background:#fff;z-index:2"><div><strong>Audit Log Details</strong><div class="subtitle">Record #${esc(row.audit_id)}</div></div><button type="button" class="btn btn-sm" data-audit-close>Close ×</button></div><div class="audit-dialog-body" style="padding:22px;display:grid;gap:16px"><div class="form-grid" style="margin-bottom:18px"><div class="field"><label>Date &amp; Time</label><strong>${esc(row.created_at ? new Date(row.created_at).toLocaleString() : '—')}</strong></div><div class="field"><label>User / Role</label><strong>${esc(row.user_name || 'System')} · ${esc(row.actor_role || 'system')}</strong></div><div class="field"><label>Action</label><strong>${esc(row.action || '—')}</strong></div><div class="field"><label>Module</label><strong>${esc(row.module || '—')}</strong></div><div class="field"><label>Entity</label><strong>${esc(row.entity_label || row.entity_id || '—')}</strong></div><div class="field"><label>IP Address</label><strong>${esc(row.ip_address || '—')}</strong></div></div><div class="field"><label>Activity Summary</label><div style="white-space:pre-wrap;overflow-wrap:anywhere">${esc(row.details || 'No additional summary was saved.')}</div></div><div class="field" style="margin-top:18px"><label>Field Changes</label>${changeHtml}</div></div>`;
    dialog.querySelector('[data-audit-close]')?.addEventListener('click', () => { try { dialog.close(); } catch (_) { dialog.removeAttribute('open'); } });
    if (!dialog.open) { try { if (typeof dialog.showModal === 'function') dialog.showModal(); else dialog.setAttribute('open', ''); } catch (_) { dialog.setAttribute('open', ''); dialog.style.position = 'fixed'; dialog.style.inset = '8% auto auto 50%'; dialog.style.transform = 'translateX(-50%)'; dialog.style.zIndex = '10050'; } }
  }

  async function handleAuditPage() {
    if (file !== 'audit-log.html') return;
    const rows = loadedRows['audit-logs'] || await loadList('audit-logs') || [];
    const table = chooseTable('audit-logs');
    const search = document.getElementById('audit-search');
    const action = document.getElementById('audit-action');
    const entity = document.getElementById('audit-entity');
    const from = document.getElementById('audit-from');
    const to = document.getElementById('audit-to');
    const form = document.getElementById('audit-filter-form');
    const pageSize = 10;
    let auditPage = 1;
    const auditFoot = document.querySelector('#audit-count')?.closest('.table-foot');
    const auditButtons = auditFoot?.querySelector('.pagination');
    if (auditButtons) { auditButtons.classList.remove('pagination'); auditButtons.classList.add('gp-ticket-page-buttons'); }
    const drawAuditPagination = (total) => {
      if (!auditButtons) return;
      const pages = Math.max(1, Math.ceil(total / pageSize));
      auditPage = Math.min(auditPage, pages);
      auditButtons.replaceChildren();
      const add = (label, target, isCurrent = false, disabled = false) => {
        const btn = document.createElement('button'); btn.type = 'button'; btn.className = 'gp-ticket-page-btn'; btn.textContent = label;
        if (isCurrent) { btn.classList.add('is-current'); btn.setAttribute('aria-current', 'page'); }
        btn.disabled = disabled; btn.addEventListener('click', () => { if (target !== auditPage && target >= 1 && target <= pages) { auditPage = target; apply(); } });
        auditButtons.appendChild(btn);
      };
      add('Previous', auditPage - 1, false, auditPage <= 1);
      let shown = pages <= 7 ? Array.from({ length: pages }, (_, i) => i + 1) : [1, ...Array.from({ length: Math.min(3, pages - 2) }, (_, i) => Math.max(2, Math.min(pages - 1, auditPage - 1)) + i).filter(p => p < pages), pages];
      shown = [...new Set(shown)].sort((a, b) => a - b);
      let prior = 0;
      shown.forEach(page => { if (prior && page - prior > 1) { const dots = document.createElement('span'); dots.className = 'gp-ticket-page-dots'; dots.textContent = '…'; auditButtons.appendChild(dots); } add(String(page), page, page === auditPage); prior = page; });
      add('Next', auditPage + 1, false, auditPage >= pages);
    };
    if (action) {
      const selected = action.value;
      [...new Set(rows.map(r => r.action).filter(Boolean))].sort().forEach(value => { if (![...action.options].some(o => o.value === value)) { const opt = document.createElement('option'); opt.value = value; opt.textContent = value; action.appendChild(opt); } });
      action.value = selected;
    }
    if (entity) {
      const selected = entity.value;
      [...new Set(rows.map(r => r.module).filter(Boolean))].sort().forEach(value => { if (![...entity.options].some(o => o.value === value)) { const opt = document.createElement('option'); opt.value = value; opt.textContent = value; entity.appendChild(opt); } });
      entity.value = selected;
    }
    const apply = () => {
      const q = (search?.value || '').trim().toLowerCase(), a = (action?.value || '').toLowerCase(), e = (entity?.value || '').toLowerCase(), f = from?.value || '', t = to?.value || '';
      const filtered = rows.filter(r => {
        const blob = [r.user_name, r.actor_role, r.action, r.module, r.entity_id, r.entity_label, r.details, r.ip_address].join(' ').toLowerCase();
        const day = String(r.created_at || '').slice(0, 10);
        return (!q || blob.includes(q)) && (!a || String(r.action || '').toLowerCase() === a) && (!e || String(r.module || '').toLowerCase() === e) && (!f || day >= f) && (!t || day <= t);
      });
      const pages = Math.max(1, Math.ceil(filtered.length / pageSize));
      auditPage = Math.min(auditPage, pages);
      const start = (auditPage - 1) * pageSize;
      if (table) renderTable('audit-logs', filtered.slice(start, start + pageSize), table, file);
      const count = document.getElementById('audit-count'); if (count) count.textContent = `Showing ${filtered.length ? start + 1 : 0}–${Math.min(start + pageSize, filtered.length)} of ${filtered.length} matching audit records`;
      drawAuditPagination(filtered.length);
    };
    const auditApplyButton = form?.querySelector('button[type="submit"]');
    auditApplyButton?.addEventListener('click', ev => { ev.preventDefault(); auditPage = 1; apply(); });
    form?.addEventListener('submit', ev => { ev.preventDefault(); auditPage = 1; apply(); });
    // Search the already-loaded audit records on every keystroke; other filters
    // may still be combined with Search and applied through the existing form.
    search?.addEventListener('input', () => { auditPage = 1; apply(); });
    document.getElementById('audit-clear')?.addEventListener('click', () => { form?.reset(); auditPage = 1; apply(); });
    document.getElementById('audit-export')?.addEventListener('click', () => exportCsv('audit-logs', rows));
    if (!document.body.dataset.auditDetailHandler) {
      document.body.dataset.auditDetailHandler = '1';
      document.body.addEventListener('click', async ev => {
        const button = ev.target.closest('[data-audit-view]'); if (!button) return;
        ev.preventDefault(); ev.stopPropagation(); button.disabled = true;
        try {
          let item = (loadedRows['audit-logs'] || []).find(r => String(r.audit_id) === String(button.dataset.auditView));
          if (!item || !item.changes) item = await api(`/api/audit-logs/${encodeURIComponent(button.dataset.auditView)}`);
          if (item) showAuditDetails(item); else toast('Audit record could not be found. Refresh the page and try again.', 'error');
        } catch (e) { toast(e.message || 'Unable to load audit detail.', 'error'); }
        finally { button.disabled = false; }
      });
    }
    apply();
  }

  function setupCustomerEntityMode(isEdit) {
    customerEntityMode = true;
    customerEditMode = Boolean(isEdit);
    const title = document.querySelector('main h1'); if (title) title.textContent = isEdit ? 'Edit customer' : 'Add customer';
    const subtitle = document.querySelector('main .subtitle'); if (subtitle) subtitle.textContent = isEdit ? 'Update the customer organization profile' : 'Create a customer organization profile';
    const intro = document.querySelector('.notice'); if (intro) intro.textContent = isEdit ? 'Edit the company details. The linked Customer login in User Management stays connected through the email address.' : 'Create a customer organization profile and its linked Customer login account. Admin can issue the first sign-in password from User Management using Reset password after SMTP is configured.';
    const form = getMainForm(); const submit = form?.querySelector('button[type="submit"]'); if (submit) submit.textContent = isEdit ? 'Save customer changes' : 'Create customer';
  }

  function installResponsiveNavigation() {
    const sidebar = document.querySelector('.sidebar');
    const main = document.querySelector('.main');
    if (!sidebar || !main || document.getElementById('gp-mobile-menu-toggle')) return;

    document.body.classList.add('gp-responsive-nav-ready');
    const toggle = document.createElement('button');
    toggle.type = 'button';
    toggle.id = 'gp-mobile-menu-toggle';
    toggle.className = 'mobile-menu-toggle';
    toggle.setAttribute('aria-label', 'Open navigation menu');
    toggle.setAttribute('aria-expanded', 'false');
    if (!sidebar.id) sidebar.id = 'gp-sidebar-navigation';
    toggle.setAttribute('aria-controls', sidebar.id);
    toggle.innerHTML = '<span></span>';

    const backdrop = document.createElement('button');
    backdrop.type = 'button';
    backdrop.className = 'mobile-nav-backdrop';
    backdrop.setAttribute('aria-label', 'Close navigation menu');
    document.body.appendChild(backdrop);

    const topbar = main.querySelector('.topbar');
    if (topbar) topbar.insertBefore(toggle, topbar.firstChild);
    else main.insertBefore(toggle, main.firstChild);

    const close = () => {
      sidebar.classList.remove('mobile-open');
      document.body.classList.remove('mobile-menu-open');
      toggle.setAttribute('aria-expanded', 'false');
      toggle.setAttribute('aria-label', 'Open navigation menu');
    };
    const open = () => {
      sidebar.classList.add('mobile-open');
      document.body.classList.add('mobile-menu-open');
      toggle.setAttribute('aria-expanded', 'true');
      toggle.setAttribute('aria-label', 'Close navigation menu');
