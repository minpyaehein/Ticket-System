  async function handleStandardForm(cfg) {
    const form = getMainForm(); if (!form) return;
    const id = idParam && !cfg.alwaysUpdate ? idParam : (cfg.alwaysUpdate ? idParam : null);
    form.addEventListener('submit', async ev => {
      ev.preventDefault();
      // Prevent rapid clicks / Enter-key repeats while one API request is in flight.
      if (form.dataset.gpSubmitting === '1') return;
      form.dataset.gpSubmitting = '1';
      const submitButton = form.querySelector('[type="submit"]');
      const originalButtonText = submitButton?.textContent || '';
      if (submitButton) { submitButton.disabled = true; submitButton.dataset.gpBusy = '1'; submitButton.textContent = 'Saving…'; }
      try {
        const payload = payloadForForm(file, form, cfg);
        if (file === 'add-ticket.html') {
          const assignedField = [...form.querySelectorAll('.field')].find(field => labelForField(field) === 'assigned');
          const assignedSelect = assignedField?.querySelector('select');
          if (assignedSelect?.value === '__clear__') payload.assigned = '';
          else if (id && assignedSelect && assignedSelect.value === String(assignedSelect.dataset.initialUiValue ?? assignedSelect.value)) delete payload.assigned;
        }
        validateFormBeforeSave(file, payload);
        if (file === 'add-user.html') {
          const role = String(payload.role || 'customer').toLowerCase(); payload.role = role === 'administrator' ? 'admin' : role;
          if (!payload.password && !id) throw new Error('Enter a temporary password for this account.');
          if (role === 'agent' && !(payload.team_ids || []).length && !payload.other_team_name) throw new Error('Select at least one Support Team for this Agent.');
          if (role !== 'agent') payload.team_ids = [];
        }
        if (file === 'add-project.html' && !payload.customer_id) throw new Error('Select a customer for this project.');
        if (file === 'add-customer.html' && !payload.customer_name) throw new Error('Enter the company name.');
        if (file === 'add-customer.html' && !payload.email) throw new Error('Enter the General Email. It is used to link the Customer profile to User Management.');
        if (file === 'add-ticket.html') {
          if (!payload.customer_id) throw new Error('Select a customer.');
          if (!payload.subject) throw new Error('Enter a ticket subject.');
          if (!payload.service_code) throw new Error('Select a Request Type.');
          if (payload.service_code) {
            const service = (lookupData.services || []).find(x => String(x.code_id) === String(payload.service_code));
            if (!service) throw new Error('Select a valid Request Type from the Service Catalog.');
          }
        }
        if (file === 'add-contact.html') {
          if (!payload.customer_id) throw new Error('Select the contact’s customer.');
          if (String(payload.type || '').trim().toLowerCase() === 'primary contact') {
            const allContacts = Array.isArray(lookupData.allContacts) ? lookupData.allContacts : (lookupData.contacts || []);
            const current = allContacts.find(row => String(row.contact_id) === String(id || ''));
            const currentAlreadyPrimaryForCustomer = Boolean(current && String(current.customer_id) === String(payload.customer_id) && String(current.type || '').trim().toLowerCase() === 'primary contact');
            const duplicate = allContacts.some(row => String(row.customer_id) === String(payload.customer_id) && String(row.contact_id) !== String(id || '') && String(row.type || '').trim().toLowerCase() === 'primary contact');
            if (duplicate && !currentAlreadyPrimaryForCustomer) throw new Error('This customer already has a Primary Contact. Choose another contact type.');
          }
        }
        if (file === 'add-contract.html' && !payload.customer_id) throw new Error('Select a customer for this contract.');
        if ((file === 'add-service.html' || file === 'add-request-type.html') && (payload.request_order === null || payload.request_order === undefined || Number(payload.request_order) < 0 || !Number.isInteger(Number(payload.request_order)))) throw new Error('Sort Order must be zero or a positive whole number.');
        if (file === 'add-team.html' && payload.service_codes?.length) payload.code_id = payload.service_codes[0];
        const shouldUpdate = Boolean(id);
        const result = await api(shouldUpdate ? `/api/${cfg.resource}/${encodeURIComponent(id)}` : `/api/${cfg.resource}`, { method: shouldUpdate ? 'PUT' : 'POST', body: JSON.stringify(payload) });
        if (file === 'add-customer.html' && !shouldUpdate) {
          const nextUrl = new URL('customers.html', location.href);
          nextUrl.searchParams.set('customer_created', '1');
          nextUrl.searchParams.set('linked_user_created', result?.linked_user_created ? '1' : '0');
          location.href = nextUrl.href;
        } else {
          toast(shouldUpdate ? 'Record updated successfully.' : 'Record created successfully.');
          if (file === 'add-user.html') location.href = 'users.html';
          else if (file === 'add-ticket.html' && shouldUpdate) location.href = `ticket-detail.html?id=${encodeURIComponent(id)}`;
          else if (file === 'add-ticket.html' && Number(result?.consolidated_ticket_count || 0) > 0) location.href = `tickets.html?consolidated=${Number(result.consolidated_ticket_count)}`;
          else location.href = cfg.redirect;
        }
      } catch (e) {
        let structuredError = null;
        try { structuredError = JSON.parse(e.message); } catch (_) { }
        if (file === 'user-create-ticket.html' && structuredError?.code === 'SUPPORT_HOURS_BLOCKED') {
          showAlertDialog(structuredError.message || 'Your Support Plan is outside its configured support hours. Please create your ticket during the next available support period.', 'Ticket Creation Not Available');
        } else {
          toast(e.message || 'Unable to save the record.', 'error');
        }
      }
      finally {
        form.dataset.gpSubmitting = '0';
        if (submitButton && submitButton.isConnected) {
          submitButton.disabled = false;
          delete submitButton.dataset.gpBusy;
          submitButton.textContent = originalButtonText;
        }
      }
    });
  }
  async function handleTicketDetail() {
    const form = getMainForm();
    if (!idParam) {
      const notice = document.createElement('div'); notice.className = 'notice warning'; notice.textContent = 'Open a ticket using View from the ticket register so the ticket ID is included.';
      document.querySelector('.breadcrumb')?.after(notice);
      if (form) form.querySelectorAll('button[type="submit"]').forEach(b => b.disabled = true);
      return;
    }
    try {
      const ticket = await api(`/api/tickets/${encodeURIComponent(idParam)}`);
      document.querySelectorAll('.breadcrumb').forEach(b => { if (b.textContent.toLowerCase().includes('ticket')) b.innerHTML = `<a href="tickets.html">Tickets</a> / ${esc(ticket.ticket_code)}`; });
      const h1 = document.querySelector('main h1'); if (h1) h1.textContent = `Ticket ${ticket.ticket_code}`;
      const editLink = [...document.querySelectorAll('a')].find(a => /edit ticket/i.test(a.textContent));
      if (editLink) { editLink.href = `add-ticket.html?id=${encodeURIComponent(ticket.ticket_id)}`; if (['customer', 'agent'].includes(currentUser.role)) editLink.style.display = 'none'; }
      const pills = document.querySelectorAll('.inline .badge, .inline .code');
      pills.forEach(el => { if (/priority/i.test(el.textContent)) el.textContent = `${ticket.priority || 'Medium'} priority`; else if (/open|closed|resolved|progress|pending/i.test(el.textContent)) el.textContent = ticket.status || 'Open'; else if (el.classList.contains('code')) el.textContent = ticket.ticket_code; });
      const headings = [...document.querySelectorAll('h2')];
      headings.forEach(h => { if (/Database connection|Ticket information|Ticket details/i.test(h.textContent)) h.textContent = ticket.subject || 'Ticket details'; });
      const headerCard = [...document.querySelectorAll('.card')].find(c => c.querySelector('h2')?.textContent === (ticket.subject || ''));
      if (headerCard) {
        const meta = headerCard.querySelector('.card-head p'); if (meta) meta.textContent = `Created ${fmtDate(ticket.date)}${ticket.updated_at ? ` · Last updated ${new Date(ticket.updated_at).toLocaleString()}` : ''}`;
        const notice = headerCard.querySelector('.notice'); if (notice) notice.textContent = ticket.description || 'No description was provided for this ticket.';
        const fields = [...headerCard.querySelectorAll('.form-grid .field')];
        const values = [ticket.customer_name, ticket.project_name, ticket.contract_code || ticket.contract_name, ticket.service_name || ticket.type, ticket.team_name || '—', ticket.assigned || 'Unassigned', ticket.asset_tag];
        fields.forEach((field, i) => { const strong = field.querySelector('strong'); if (strong && values[i] !== undefined) strong.textContent = values[i] || '—'; });
      }
      const sla = [...document.querySelectorAll('.item')].find(item => /Support plan/i.test(item.textContent));
      if (sla) { const strong = sla.querySelector('strong'); if (strong) strong.textContent = ticket.plan_name || '—'; }
      if (form) {
        form.querySelectorAll('.field').forEach(field => { const label = labelForField(field); const key = cfgFieldForTicket(label); if (key) setField(field, ticket[key], file, label); });
        const statusField = [...form.querySelectorAll('.field')].find(field => labelForField(field) === 'status');
        const statusSelect = statusField?.querySelector('select');
        const allowedStatuses = ['Open', 'In progress', 'Pending Customer', 'Resolved', 'Closed'];
        if (statusSelect) {
          const selected = String(ticket.status || 'Open').trim().toLowerCase().replace(/[_-]+/g, ' ');
          const canonical = selected === 'pending' || selected === 'pending customer' || selected === 'waiting for customer' ? 'Pending Customer' : allowedStatuses.find(value => value.toLowerCase() === selected) || 'Open';
          statusSelect.replaceChildren(...allowedStatuses.map(value => { const option = document.createElement('option'); option.value = value; option.textContent = value; return option; }));
          statusSelect.value = canonical;
        }
        const isAgent = currentUser?.role === 'agent';
        const isAssignedAgent = isAgent && Number(ticket.assigned_agent_id || 0) === Number(currentUser?.user_id || 0);
        if (isAgent) {
          form.querySelectorAll('.field').forEach(field => { if (labelForField(field) !== 'status') { field.hidden = true; field.style.display = 'none'; } });
          if (!isAssignedAgent) {
            if (statusField) { statusField.hidden = true; statusField.style.display = 'none'; }
            form.querySelectorAll('[type="submit"]').forEach(button => { button.hidden = true; button.style.display = 'none'; });
            const hint = document.createElement('div'); hint.className = 'notice'; hint.textContent = 'Only the Agent explicitly assigned to this ticket can change its status. You can view this Team ticket here.';
            form.closest('.card')?.querySelector('.card-body')?.prepend(hint);
          } else {
            const hint = document.createElement('small'); hint.className = 'field-hint'; hint.textContent = 'You can update the ticket status. Other ticket properties are managed by Admin.';
            statusField?.appendChild(hint);
            const submit = form.querySelector('[type="submit"]'); if (submit) submit.textContent = 'Update status';
          }
        }
        const dueDateInput = [...form.querySelectorAll('.field')].find(field => labelForField(field) === 'due date')?.querySelector('input[type="date"]');
        if (dueDateInput) {
          const today = yangonTodayString();
          dueDateInput.value = ticket.due_date ? String(ticket.due_date).slice(0, 10) : '';
          if (dueDateInput.value && dueDateInput.value < today) {
            // Preserve an existing overdue due date so an Agent can still save
            // status/priority/assignment changes without changing the deadline.
            dueDateInput.removeAttribute('min');
            dueDateInput.addEventListener('change', () => {
              dueDateInput.min = today;
              dueDateInput.setCustomValidity(dueDateInput.value && dueDateInput.value < today ? `Due Date cannot be earlier than today (${today}).` : '');
            });
          } else dueDateInput.min = today;
        }
        const assignedField = [...form.querySelectorAll('.field')].find(field => labelForField(field) === 'assigned to');
        const assignedSelect = assignedField?.querySelector('select');
        if (assignedSelect) {
          const previousAssigned = String(ticket.assigned || '');
          setAssignableAgentOptions(assignedSelect, ticket.team_id, ticket.service_code, previousAssigned);
          assignedSelect.dataset.initialUiValue = assignedSelect.value;
          const pairHint = assignedField.querySelector('[data-assignment-pair-hint]');
          if (pairHint) pairHint.remove();
          let assignmentHint = assignedField.querySelector('[data-assignment-help]');
          if (!assignmentHint) { assignmentHint = document.createElement('small'); assignmentHint.dataset.assignmentHelp = ''; assignmentHint.className = 'field-hint'; assignedField.appendChild(assignmentHint); }
          assignmentHint.textContent = `Choose an active Agent from ${ticket.team_name && ticket.team_name !== '—' ? ticket.team_name : 'the ticket Support Team'}.`;
        }
        form.addEventListener('submit', async ev => {
          ev.preventDefault(); if (form.dataset.gpSubmitting === '1') return;
          form.dataset.gpSubmitting = '1';
          const save = form.querySelector('[type="submit"]'); const oldText = save?.textContent || 'Save changes';
          if (save) { save.disabled = true; save.textContent = 'Saving…'; }
          try {
            let payload;
            if (isAgent) {
              if (!isAssignedAgent) throw new Error('Only the Agent assigned to this ticket can change its status.');
              payload = { status: statusSelect?.value || ticket.status };
            } else {
              payload = payloadForForm(file, form, formConfig[file]);
              if (assignedSelect?.value === '__clear__') payload.assigned = '';
              else if (assignedSelect && assignedSelect.value === String(assignedSelect.dataset.initialUiValue ?? assignedSelect.value)) delete payload.assigned;
            }
            await api(`/api/tickets/${ticket.ticket_id}`, { method: 'PUT', body: JSON.stringify(payload) });
            toast(isAgent ? 'Ticket status updated.' : 'Ticket updated.'); location.href = `ticket-detail.html?id=${ticket.ticket_id}`;
          } catch (e) { toast(e.message, 'error'); }
          finally { form.dataset.gpSubmitting = '0'; if (save && save.isConnected) { save.disabled = false; save.textContent = oldText; } }
        });
      }
    } catch (e) {
      toast(e.message, 'error');
      if (e.status === 404) {
        const main = document.querySelector('main');
        main?.querySelectorAll('.card').forEach(card => card.remove());
        const notice = document.createElement('section'); notice.className = 'notice warning';
        notice.textContent = 'This ticket no longer exists or has been deleted.';
        main?.appendChild(notice);
      }
    }
  }
  function cfgFieldForTicket(label) { return formConfig['ticket-detail.html'].map[label]; }
  async function handleCustomerCreateTicket() {
    const serviceName = params.get('service');
    const form = getMainForm(); if (!form) return;
    if (serviceName) { const serviceSelect = [...form.querySelectorAll('.field')].find(f => ['service', 'service / request type'].includes(labelForField(f)))?.querySelector('select'); if (serviceSelect) { const option = [...serviceSelect.options].find(o => o.value === serviceName || o.textContent === serviceName); if (option) { serviceSelect.value = option.value; serviceSelect.dispatchEvent(new Event('change', { bubbles: true })); } } }
  }
  async function handleStaffTicketConversation() {
    const id = idParam; if (!id) return;
    try {
      const ticket = await api(`/api/tickets/${encodeURIComponent(id)}`);
      const activity = [...document.querySelectorAll('section.card')].find(s => /activity|comments/i.test(s.textContent));
      if (!activity) return;
      const body = activity.querySelector('.card-body'); if (!body) return;
      const isAgentView = currentUser?.role === 'agent';
      const isAssignedAgent = isAgentView && Number(ticket.assigned_agent_id || 0) === Number(currentUser?.user_id || 0);
      const canPostConversation = !isAgentView || isAssignedAgent;
      body.innerHTML = '<div data-replies></div>' + (canPostConversation ? '<form data-staff-reply-form class="staff-reply-form" style="margin-top:16px"><div class="field"><label data-reply-label>Public reply</label><textarea class="textarea" placeholder="Write a reply to the customer" required></textarea></div><div class="reply-mode-wrap"><span class="reply-mode-caption">Message type</span><div class="reply-mode-switch" role="group" aria-label="Choose message type"><button class="reply-mode-option is-selected" type="button" data-reply-mode="public" aria-pressed="true">Public reply</button><button class="reply-mode-option" type="button" data-reply-mode="internal" aria-pressed="false">🔒 Internal note</button></div><p class="reply-mode-hint" data-internal-note-hint>Visible to the customer and staff.</p></div><div class="form-actions"><button class="btn btn-primary" type="submit" data-reply-submit>Send reply</button></div></form>' : '<p class="subtitle">Only the Agent assigned to this ticket can reply or add an internal note. Other team Agents have read-only access.</p>');
      let replies = await api(`/api/tickets/${ticket.ticket_id}/replies`); renderReplies(replies, ticket);
      // Keep the open ticket conversation current when Admin or Customer adds
      // a public reply. Internal-note filtering is enforced by the API.
      startTicketReplyRefresh(ticket.ticket_id, ticket, () => replies, (latest) => { replies = latest; });
      if (!canPostConversation) return;
      const form = body.querySelector('[data-staff-reply-form]'); const textarea = form.querySelector('textarea'); const modeButtons = [...form.querySelectorAll('[data-reply-mode]')]; let internalMode = false;
      const updateNoteMode = () => { form.classList.toggle('is-internal-note', internalMode); modeButtons.forEach(button => { const selected = button.dataset.replyMode === (internalMode ? 'internal' : 'public'); button.classList.toggle('is-selected', selected); button.setAttribute('aria-pressed', String(selected)); }); form.querySelector('[data-reply-label]').textContent = internalMode ? 'Internal note' : 'Public reply'; textarea.placeholder = internalMode ? 'Write a private note for Admin and the assigned Agent only' : 'Write a reply to the customer'; form.querySelector('[data-internal-note-hint]').textContent = internalMode ? 'Admin + assigned Agent only · Not visible to customers or other team Agents' : 'Visible to the customer and staff'; form.querySelector('[data-reply-submit]').textContent = internalMode ? 'Add internal note' : 'Send reply'; };
      modeButtons.forEach(button => button.addEventListener('click', () => { internalMode = button.dataset.replyMode === 'internal'; updateNoteMode(); }));
      form.addEventListener('submit', async ev => { ev.preventDefault(); if (form.dataset.gpSubmitting === '1') return; const text = textarea.value.trim(); if (!text) return; form.dataset.gpSubmitting = '1'; const sendButton = form.querySelector('[data-reply-submit]'); const oldText = sendButton?.textContent || 'Send reply'; if (sendButton) { sendButton.disabled = true; sendButton.textContent = 'Sending…'; } const internal = internalMode; try { await api(`/api/tickets/${ticket.ticket_id}/replies`, { method: 'POST', body: JSON.stringify({ body: text, is_internal: internal }) }); textarea.value = ''; internalMode = false; updateNoteMode(); toast(internal ? 'Internal note saved for Admin and the assigned Agent only.' : 'Reply sent to the customer.'); replies = await api(`/api/tickets/${ticket.ticket_id}/replies`); renderReplies(replies, ticket); } catch (e) { toast(e.message, 'error'); } finally { form.dataset.gpSubmitting = '0'; if (sendButton && sendButton.isConnected) { sendButton.disabled = false; sendButton.textContent = internal ? 'Add internal note' : 'Send reply'; } } });
    } catch (e) {
      toast(e.message, 'error');
      if (e.status === 404 && !document.querySelector('main .notice.warning')) {
        const main = document.querySelector('main');
        const notice = document.createElement('section'); notice.className = 'notice warning';
        notice.textContent = 'This ticket no longer exists or has been deleted.';
        main?.querySelectorAll('.card').forEach(card => card.remove()); main?.appendChild(notice);
      }
    }
  }

  async function handleTicketConversation() {
    const id = idParam;
    if (!id) { const notice = document.createElement('div'); notice.className = 'notice warning'; notice.textContent = 'Please open this ticket from My Tickets so its ID is included.'; document.querySelector('.breadcrumb')?.after(notice); return; }
    try {
      const ticket = await api(`/api/tickets/${encodeURIComponent(id)}`);
      const assignedSummary = [...document.querySelectorAll('.item')].find(item => /assigned (team|to)/i.test(item.textContent));
      if (assignedSummary) { const label = assignedSummary.querySelector('span'); const value = assignedSummary.querySelector('strong'); if (label) label.textContent = 'Assigned to'; if (value) value.textContent = ticket.assigned || 'Service Desk'; }
      const heading = document.querySelector('main h1'); if (heading) heading.textContent = `${ticket.ticket_code} · ${ticket.subject}`;
      document.querySelectorAll('.breadcrumb').forEach(b => { if (b.textContent.toLowerCase().includes('ticket')) b.innerHTML = `<a href="my-tickets.html">My tickets</a> / ${esc(ticket.ticket_code)}`; });
      let replies = await api(`/api/tickets/${ticket.ticket_id}/replies`);
      const twoCol = document.querySelector('main .two-col');
      if (['resolved', 'closed'].includes(String(ticket.status || '').trim().toLowerCase()) && twoCol && !document.querySelector('[data-resolution-confirmation]')) {
        const confirmation = document.createElement('section');
        confirmation.className = 'card';
        confirmation.dataset.resolutionConfirmation = '';
        confirmation.style.marginBottom = '16px';
        const isResolved = String(ticket.status || '').trim().toLowerCase() === 'resolved';
        confirmation.innerHTML = `<div class="card-head"><div><h2>${isResolved ? 'Is your issue resolved?' : 'Need more help with this closed ticket?'}</h2><p class="subtitle">${isResolved ? 'The support team marked this ticket as Resolved. Please confirm whether the solution fixed your issue.' : 'This ticket is closed. If the issue is still not fixed or has returned, you can reopen it.'}</p></div></div><div class="card-body"><div class="form-actions" style="justify-content:flex-start">${isResolved ? '<button type="button" class="btn btn-primary" data-accept-ticket-resolution>Accept Resolution</button>' : ''}<button type="button" class="btn" data-reopen-ticket>Reopen Ticket — Still Need Help</button></div></div>`;
        twoCol.parentNode.insertBefore(confirmation, twoCol);
        const acceptButton = confirmation.querySelector('[data-accept-ticket-resolution]');
        const reopenButton = confirmation.querySelector('[data-reopen-ticket]');
        const submitResolutionChoice = async (button, endpoint, confirmText) => {
          if (confirmation.dataset.submitting === '1') return;
          if (!await confirmDialog(confirmText, 'Confirm ticket resolution')) return;
          confirmation.dataset.submitting = '1';
          if (acceptButton) acceptButton.disabled = true; reopenButton.disabled = true;
          const original = button.textContent; button.textContent = 'Saving…';
          try {
            const result = await api(`/api/tickets/${ticket.ticket_id}/${endpoint}`, { method: 'POST' });
            toast(result.message);
            location.reload();
          } catch (e) {
            toast(e.message, 'error');
            confirmation.dataset.submitting = '0';
            if (acceptButton) acceptButton.disabled = false; reopenButton.disabled = false; button.textContent = original;
          }
        };
        if (acceptButton) acceptButton.addEventListener('click', () => submitResolutionChoice(acceptButton, 'accept-resolution', 'Accept this solution and close the ticket?'));
        reopenButton.addEventListener('click', () => submitResolutionChoice(reopenButton, 'reopen', 'The issue is still not fixed. Reopen this ticket?'));
      }
      // Capture the reply form before adding the editor so it remains the conversation form.
      const replyForm = getMainForm();
      if (twoCol && !document.querySelector('[data-customer-ticket-editor]')) {
        const editor = document.createElement('section');
        editor.className = 'card';
        editor.dataset.customerTicketEditor = '';
        editor.style.marginBottom = '16px';
        editor.innerHTML = `<div class="card-head" style="justify-content:space-between;align-items:center"><div><h2>Edit your request</h2><p class="subtitle">You can update the subject, priority and problem description, even after the request is resolved.</p></div><button class="btn" type="button" data-toggle-ticket-editor>Edit request</button></div><div class="card-body" data-ticket-editor-body hidden><form data-ticket-editor-form><div class="form-grid"><div class="field"><label>Subject *</label><input class="input" name="subject" type="text" maxlength="180" required value="${esc(ticket.subject || '')}"></div><div class="field"><label>Priority</label><select class="select" name="priority"><option value="Low">Low</option><option value="Medium">Medium</option><option value="High">High</option><option value="Critical">Critical</option></select></div><div class="field full"><label>Problem description *</label><textarea class="textarea" name="description" rows="5" required>${esc(ticket.description || '')}</textarea></div></div><div class="form-actions"><button class="btn" type="button" data-cancel-ticket-edit>Cancel</button><button class="btn btn-primary" type="submit">Save changes</button></div></form></div>`;
        twoCol.parentNode.insertBefore(editor, twoCol);
        const editorForm = editor.querySelector('[data-ticket-editor-form]');
        const priority = editorForm.querySelector('[name="priority"]'); priority.value = ticket.priority || 'Medium';
        const body = editor.querySelector('[data-ticket-editor-body]');
        const toggle = editor.querySelector('[data-toggle-ticket-editor]');
        const closeEditor = () => { body.hidden = true; toggle.textContent = 'Edit request'; };
        toggle.addEventListener('click', () => { body.hidden = !body.hidden; toggle.textContent = body.hidden ? 'Edit request' : 'Close editor'; });
        editor.querySelector('[data-cancel-ticket-edit]').addEventListener('click', closeEditor);
        editorForm.addEventListener('submit', async ev => {
          ev.preventDefault(); if (editorForm.dataset.gpSubmitting === '1') return;
          const subject = editorForm.elements.subject.value.trim();
          const description = editorForm.elements.description.value.trim();
          if (!subject || !description) { toast('Enter both a subject and problem description.', 'error'); return; }
          editorForm.dataset.gpSubmitting = '1';
          const save = editorForm.querySelector('[type="submit"]'); const original = save.textContent; save.disabled = true; save.textContent = 'Saving…';
          try {
            const updated = await api(`/api/tickets/${ticket.ticket_id}`, { method: 'PUT', body: JSON.stringify({ subject, description, priority: priority.value }) });
            toast(updated.status === 'Open' && ['Resolved', 'Closed'].includes(String(ticket.status || '')) ? 'Your request was updated and reopened.' : 'Your request was updated.');
            location.reload();
          } catch (e) { toast(e.message, 'error'); }
          finally { editorForm.dataset.gpSubmitting = '0'; if (save.isConnected) { save.disabled = false; save.textContent = original; } }
        });
      }
      if (replyForm) replyForm.addEventListener('submit', async ev => { ev.preventDefault(); if (replyForm.dataset.gpSubmitting === '1') return; const textarea = replyForm.querySelector('textarea'); const body = textarea?.value.trim(); if (!body) { toast('Write a reply before sending.', 'error'); return; } replyForm.dataset.gpSubmitting = '1'; const sendButton = replyForm.querySelector('[type="submit"]'); const oldText = sendButton?.textContent || 'Send reply'; if (sendButton) { sendButton.disabled = true; sendButton.textContent = 'Sending…'; } try { await api(`/api/tickets/${ticket.ticket_id}/replies`, { method: 'POST', body: JSON.stringify({ body, is_internal: false }) }); textarea.value = ''; toast('Reply sent.'); replies = await api(`/api/tickets/${ticket.ticket_id}/replies`); renderReplies(replies, ticket); } catch (e) { toast(e.message, 'error'); } finally { replyForm.dataset.gpSubmitting = '0'; if (sendButton && sendButton.isConnected) { sendButton.disabled = false; sendButton.textContent = oldText; } } });
      renderReplies(replies, ticket);
      // Customer portal also refreshes the shared conversation so staff
      // public replies appear without requiring a manual browser reload.
      startTicketReplyRefresh(ticket.ticket_id, ticket, () => replies, (latest) => { replies = latest; });
    } catch (e) {
      toast(e.message, 'error');
      if (e.status === 404) {
        const main = document.querySelector('main');
        main?.querySelectorAll('.card').forEach(card => card.remove());
        const notice = document.createElement('section'); notice.className = 'notice warning';
        notice.textContent = 'This ticket no longer exists or has been deleted.';
        main?.appendChild(notice);
      }
    }
  }
  function renderReplies(replies, ticket) {
    let host = document.querySelector('[data-replies]');
    let section = host?.closest('section.card') || [...document.querySelectorAll('section.card')].find(s => /conversation|repl|activity/i.test(s.textContent));
    if (!section) { const main = document.querySelector('main'); if (!main) return; section = document.createElement('section'); section.className = 'card'; section.innerHTML = '<div class="card-head"><h2>Conversation</h2></div><div class="card-body"><div data-replies></div></div>'; const form = getMainForm(); if (form) form.closest('section.card')?.before(section); else main.append(section); }
    if (!host || !section.contains(host)) { host = section.querySelector('[data-replies]'); }
    if (!host) { host = document.createElement('div'); host.dataset.replies = ''; section.querySelector('.card-body')?.prepend(host); }
    host.innerHTML = `<div class="item-list">${replies.length ? replies.map(r => `<div class="item" style="align-items:flex-start"><div><strong>${esc(r.user_name)} ${r.is_internal ? '<span class="badge high">Internal note · Staff only</span>' : ''}</strong><small>${esc(new Date(r.created_at).toLocaleString())}</small><p style="margin:8px 0 0;white-space:pre-wrap">${esc(r.body)}</p></div></div>`).join('') : '<p class="subtitle">No replies yet.</p>'}</div>`;
  }
  function startTicketReplyRefresh(ticketId, ticket, getCurrentReplies, setCurrentReplies) {
    let checking = false;
    const signature = items => JSON.stringify((items || []).map(item => [
      item.reply_id, item.user_id, item.user_name, item.body, Boolean(item.is_internal), item.created_at
    ]));
    const refresh = async () => {
      if (checking || document.visibilityState !== 'visible') return;
      checking = true;
      try {
        const latest = await api(`/api/tickets/${ticketId}/replies`);
        if (signature(latest) !== signature(getCurrentReplies())) {
          setCurrentReplies(latest);
          renderReplies(latest, ticket);
        }
      } catch (_error) {
        // A temporary network/authentication issue should not interrupt typing.
        // The next visible refresh will retry; the API remains authoritative.
      } finally { checking = false; }
    };
    const timer = window.setInterval(refresh, 5000);
    window.addEventListener('pagehide', () => window.clearInterval(timer), { once: true });
  }
  async function refreshCustomerDetail() {
    if (!idParam) throw new Error('Open a customer from the Customers register to view its live profile.');
    const customer = await api(`/api/customers/${encodeURIComponent(idParam)}`);
    const [allProjects, allContracts, allAssets, allTickets] = await Promise.all([
      api('/api/projects'), api('/api/contracts'), api('/api/assets'), api('/api/tickets')
    ]);
    const sameCustomer = row => String(row.customer_id) === String(customer.customer_id);
    const projects = allProjects.filter(sameCustomer);
    const contracts = allContracts.filter(sameCustomer);
    const assets = allAssets.filter(sameCustomer);
    const tickets = allTickets.filter(sameCustomer);
    const activeTickets = tickets.filter(ticket => !['resolved', 'closed', 'cancelled'].includes(normalStatus(ticket.status)));
    const activeProjects = projects.filter(project => !['completed', 'cancelled', 'inactive'].includes(normalStatus(project.status)));
    const activeContracts = contracts.filter(contract => normalStatus(contract.status) === 'active');

    const crumb = document.querySelector('[data-customer-breadcrumb]') || document.querySelector('.breadcrumb');
    if (crumb) crumb.innerHTML = `<a href="customers.html">Customers</a> / ${esc(customer.customer_name)}`;
    const edit = document.querySelector('a[href="add-customer.html"]');
    if (edit) { if (currentUser?.role === 'admin') edit.href = `add-customer.html?id=${customer.customer_id}&edit_customer=1`; else edit.style.display = 'none'; }
    const title = document.querySelector('[data-customer-title]'); if (title) title.textContent = customer.customer_name || 'Customer profile';
    const status = document.querySelector('[data-customer-active]');
    if (status) { status.textContent = customer.active === false ? 'Inactive' : 'Active customer'; status.className = `badge ${customer.active === false ? 'status-red' : 'status-green'}`; }

    const fieldValues = { customer_name: customer.customer_name, email: customer.email, phone: customer.phone, address: customer.address, contact_name: customer.contact_name, notes: customer.notes };
    document.querySelectorAll('[data-customer-field]').forEach(el => {
      const key = el.dataset.customerField; el.textContent = fieldValues[key] || '—';
    });
    const counts = {
      open_tickets: { value: activeTickets.length, note: `${tickets.length} total ticket${tickets.length === 1 ? '' : 's'}` },
      projects: { value: projects.length, note: `${activeProjects.length} active project${activeProjects.length === 1 ? '' : 's'}` },
      assets: { value: assets.length, note: 'Registered assets' },
      contracts: { value: contracts.length, note: `${activeContracts.length} active contract${activeContracts.length === 1 ? '' : 's'}` }
    };
    Object.entries(counts).forEach(([key, info]) => {
      const value = document.querySelector(`[data-customer-stat="${key}"]`); if (value) value.textContent = String(info.value);
      const note = document.querySelector(`[data-customer-stat-note="${key}"]`); if (note) note.textContent = info.note;
    });

    const idKey = { projects: 'project_id', contracts: 'contract_id', assets: 'asset_id', tickets: 'ticket_id' };
    const renderRelated = (key, rows, titleField, subtitleFn, link) => {
      const host = document.querySelector(`[data-related-list="${key}"]`);
      const count = document.querySelector(`[data-related-count="${key}"]`);
      if (count) count.textContent = String(rows.length);
      if (!host) return;
      const sorted = [...rows].sort((a, b) => Number(b[idKey[key]] || 0) - Number(a[idKey[key]] || 0)).slice(0, 5);
      host.innerHTML = sorted.length ? sorted.map(row => {
        const label = esc(row[titleField] || '—');
        const sub = esc(subtitleFn(row) || '—');
        return `<div class="item"><div><strong>${label}</strong><small>${sub}</small></div><a class="btn btn-sm" href="${link(row)}">Open</a></div>`;
      }).join('') : `<p class="subtitle">No ${esc(key)} linked to this customer.</p>`;
    };
    renderRelated('projects', projects, 'project_name', row => row.status || row.project_code || '', row => 'projects.html');
    renderRelated('contracts', contracts, 'contract_name', row => `${row.contract_code || 'Contract'} · ${row.status || '—'}`, row => 'contracts.html');
    renderRelated('assets', assets, 'asset_name', row => `${row.asset_tag || 'Asset'} · ${row.status || '—'}`, row => 'assets.html');
    renderRelated('tickets', tickets, 'subject', row => `${row.ticket_code || 'Ticket'} · ${row.status || '—'}`, row => `ticket-detail.html?id=${encodeURIComponent(row.ticket_id)}`);
    const updated = document.querySelector('[data-customer-last-updated]');
    if (updated) updated.textContent = `Updated ${new Date().toLocaleTimeString()}`;
  }

  async function handleEditDetails() {
    if (!idParam) return;
    if (file === 'asset-detail.html') {
      try {
        const asset = await api(`/api/assets/${encodeURIComponent(idParam)}`);
        const values = [asset.asset_tag, asset.asset_name, asset.customer_name, asset.type, asset.serial_no, asset.note, asset.status];
        document.querySelectorAll('.item-list .item').forEach((item, i) => { const strong = item.querySelector('strong'); if (strong && values[i] !== undefined) strong.textContent = values[i] || '—'; });
        const edit = document.querySelector('a[href="add-asset.html"]'); if (edit) { if (currentUser.role === 'admin') edit.href = `add-asset.html?id=${asset.asset_id}`; else edit.style.display = 'none'; }
        const ticketRows = await api('/api/tickets'); const linked = ticketRows.filter(t => String(t.asset_id) === String(asset.asset_id));
        const table = [...document.querySelectorAll('table')].find(t => (t.querySelector('thead')?.textContent || '').toLowerCase().includes('ticket'));
        if (table) renderTable('tickets', linked, table, file);
      } catch (e) {
        toast(e.message, 'error');
        if (e.status === 404) {
          document.querySelector('.item-list')?.replaceChildren();
          const main = document.querySelector('main'); const notice = document.createElement('section'); notice.className = 'notice warning'; notice.textContent = 'This asset no longer exists or has been deleted.'; main?.appendChild(notice);
          const edit = document.querySelector('a[href="add-asset.html"]'); if (edit) edit.remove();
        }
      }
    } else if (file === 'customer-detail.html') {
      try {
        await refreshCustomerDetail();
        if (!window.gpCustomerDetailRefresh) {
          window.gpCustomerDetailRefresh = window.setInterval(() => {
            if (document.visibilityState === 'visible') refreshCustomerDetail().catch(() => { });
          }, 15000);
        }
      } catch (e) {
        toast(e.message, 'error');
        if (e.status === 404) {
          document.querySelectorAll('[data-customer-info], [data-related-list]').forEach(el => el.replaceChildren());
          const crumb = document.querySelector('[data-customer-breadcrumb]') || document.querySelector('.breadcrumb'); if (crumb) crumb.textContent = 'Customers / Not found';
          const main = document.querySelector('main'); const notice = document.createElement('section'); notice.className = 'notice warning'; notice.textContent = 'This customer no longer exists or has been deleted.'; main?.appendChild(notice);
          const edit = document.querySelector('a[href="add-customer.html"]'); if (edit) edit.remove();
        }
      }
    }
  }
