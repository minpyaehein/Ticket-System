/* Golden Pride: keeps the supplied HTML/CSS pages and connects them to FastAPI/PostgreSQL. */
(() => {
  'use strict';
  const file = (location.pathname.split('/').pop() || 'login.html').toLowerCase();
  const params = new URLSearchParams(location.search);
  const idParam = params.get('id');
  const scrollKey = 'gpScroll:' + location.pathname + location.search;
  if ('scrollRestoration' in history) history.scrollRestoration = 'manual';

  // The URL is the source of truth for the selected page. This keeps the
  // sidebar state correct on direct navigation, refresh, and Back/Forward.
  const activePageAliases = {
    'admin-dashboard.html': 'dashboard.html',
    'add-ticket.html': 'tickets.html',
    'ticket-detail.html': 'tickets.html',
    'my-tickets.html': 'my-tickets.html',
    'user-ticket-detail.html': 'my-tickets.html',
    'user-create-ticket.html': 'user-create-ticket.html',
    'add-customer.html': 'customers.html',
    'customer-detail.html': 'customers.html',
    'add-project.html': 'projects.html',
    'add-contract.html': 'contracts.html',
    'add-support-plan.html': 'support-plans.html',
    'add-service.html': 'service-catalog.html',
    'add-request-type.html': 'service-catalog.html',
    'add-contact.html': 'contacts.html',
    'add-asset.html': 'assets.html',
    'asset-detail.html': 'assets.html',
    'add-user.html': 'users.html',
    'add-team.html': 'teams.html',
    'add-role.html': 'roles-access.html',
    'role-admin.html': 'roles-access.html'
  };
  const activeNavPage = activePageAliases[file] || file;
  document.querySelectorAll('.sidebar .nav a[href]').forEach(link => {
    let target = '';
    try {
      const url = new URL(link.getAttribute('href'), location.href);
      if (url.origin === location.origin) target = url.pathname.split('/').pop().toLowerCase();
    } catch (_) { }
    const isActive = target === activeNavPage;
    link.classList.toggle('active', isActive);
    if (isActive) link.setAttribute('aria-current', 'page');
    else link.removeAttribute('aria-current');
  });

  // Clicking the already-open sidebar destination should not reload the page.
  document.querySelector('.sidebar .nav')?.addEventListener('click', event => {
    const link = event.target.closest('a[href]');
    if (!link || link.hasAttribute('data-logout') || link.target === '_blank') return;
    try {
      const url = new URL(link.getAttribute('href'), location.href);
      if (url.origin === location.origin && url.pathname === location.pathname && url.search === location.search) {
        event.preventDefault();
      }
    } catch (_) { }
  });

  // Save the scroll offset for this exact URL before leaving or refreshing.
  // Do not delete the destination's saved offset: Back/Forward must be able
  // to restore the position previously saved for that page.
  window.addEventListener('pagehide', () => {
    try { sessionStorage.setItem(scrollKey, String(window.scrollY)); } catch (_) { }
  });
  const homeByRole = { admin: 'admin-dashboard.html', agent: 'agent-dashboard.html', customer: 'user-dashboard.html' };
  const allowedByRole = {
    admin: null,
    agent: ['agent-dashboard.html', 'dashboard.html', 'tickets.html', 'ticket-detail.html', 'customers.html', 'customer-detail.html', 'projects.html', 'contracts.html', 'support-plans.html', 'service-catalog.html', 'contacts.html', 'assets.html', 'asset-detail.html', 'email-notifications.html', 'change-password.html'],
    customer: ['user-dashboard.html', 'my-tickets.html', 'user-create-ticket.html', 'user-ticket-detail.html', 'user-service-catalog.html', 'user-assets.html', 'email-notifications.html', 'change-password.html']
  };
  const pageResource = {
    'tickets.html': 'tickets', 'my-tickets.html': 'tickets', 'dashboard.html': 'tickets',
    'admin-dashboard.html': 'tickets', 'agent-dashboard.html': 'tickets', 'user-dashboard.html': 'tickets',
    'projects.html': 'projects', 'customers.html': 'customers', 'contacts.html': 'contacts', 'contracts.html': 'contracts',
    'support-plans.html': 'plans', 'service-catalog.html': 'services', 'user-service-catalog.html': 'services',
    'teams.html': 'teams', 'users.html': 'users', 'assets.html': 'assets', 'user-assets.html': 'assets', 'audit-log.html': 'audit-logs'
  };
  const customerEntityConfig = { resource: 'customers', redirect: 'customers.html', map: { 'company name': 'customer_name', 'initial contact name': 'contact_name', 'general email': 'email', 'phone': 'phone', 'address': 'address' } };
  const customerEditConfig = customerEntityConfig;
  const formConfig = {
    'add-asset.html': { resource: 'assets', redirect: 'assets.html', map: { 'customer': 'customer_id', 'project': 'project_id', 'service catalog': 'service_codes', 'asset tag': 'asset_tag', 'asset name': 'asset_name', 'type': 'type', 'asset status': 'status', 'vendor': 'vendor', 'model': 'model', 'serial number': 'serial_no', 'ip address': 'ip_address', 'note': 'note' } },
    'add-contact.html': { resource: 'contacts', redirect: 'contacts.html', map: { 'customer': 'customer_id', 'contact no': 'contact_code', 'full name': 'fullname', 'department': 'department', 'job title': 'job_title', 'email': 'email', 'phone': 'phone', 'type': 'type', 'notes': 'note' } },
    'add-contract.html': { resource: 'contracts', redirect: 'contracts.html', map: { 'customer': 'customer_id', 'project': 'project_id', 'contract no': 'contract_code', 'contract name': 'contract_name', 'support plan': 'plan_id', 'start date': 'start_date', 'end date': 'end_date', 'scope / covered service': 'scope' } },
    'add-user.html': { resource: 'users', redirect: 'users.html', map: { 'full name': 'fullname', 'email': 'email', 'password': 'password', 'role': 'role', 'support team': 'team_ids', 'request type': 'request_type_code', 'notes': 'notes' } },
    'add-project.html': { resource: 'projects', redirect: 'projects.html', map: { 'customer': 'customer_id', 'project code': 'project_code', 'project name': 'project_name', 'project manager': 'project_manager', 'project status': 'status', 'start date': 'start_date', 'end date': 'end_date', 'description': 'description' } },
    'add-service.html': { resource: 'services', redirect: 'service-catalog.html', map: { 'code': 'code_id', 'name': 'name', 'category': 'category', 'sort order': 'request_order', 'customer visible': 'customer_visible', 'asset requirements': 'asset_requirement', 'mapped team': 'mapped_team', 'auto assign': 'auto_assign', 'assignment method': 'assignment_method', 'description': 'description' } },
    'add-request-type.html': { resource: 'services', redirect: 'service-catalog.html', map: { 'code': 'code_id', 'name': 'name', 'category': 'category', 'sort order': 'request_order', 'customer visible': 'customer_visible', 'asset requirements': 'asset_requirement', 'mapped team': 'mapped_team', 'auto assign': 'auto_assign', 'assignment method': 'assignment_method', 'description': 'description' } },
    'add-support-plan.html': { resource: 'plans', redirect: 'support-plans.html', map: { 'plan code': 'plan_code', 'plan type': 'plan_type', 'new plan type': 'custom_plan_type', 'plan name': 'plan_name', 'response sla': 'response_sla', 'resolution sla': 'resolution_sla', 'response warning %': 'response_warning', 'response critical %': 'response_critical', 'resolution warning %': 'resolution_warning', 'resolution critical %': 'resolution_critical', 'sla calendar mode': 'sla_mode', 'time zone': 'time_zone', 'business start': 'business_start_hour', 'business end': 'business_end_hour', 'working days': 'working_days', 'escalation level': 'escalation_level', 'remote support': 'remote_support', 'onsite support': 'onsite_support', 'description': 'description' } },
    'add-team.html': { resource: 'teams', redirect: 'teams.html', map: { 'team code': 'team_code', 'team name': 'team_name', 'team members': 'member', 'service catalog': 'service_codes', 'description': 'description' } },
    'add-ticket.html': { resource: 'tickets', redirect: 'tickets.html', map: { 'customer': 'customer_id', 'project (optional)': 'project_id', 'contact (optional)': 'contact_id', 'contract (optional)': 'contract_id', 'support plan (optional)': 'plan_id', 'request type': 'service_code', 'support team (optional)': 'team_id', 'subject': 'subject', 'description': 'description', 'status': 'status', 'priority': 'priority', 'asset (optional)': 'asset_id', 'assigned': 'assigned', 'created': 'date', 'due date': 'due_date', 'attachment reference': 'attachment_reference' } },
    'user-create-ticket.html': { resource: 'tickets', redirect: 'my-tickets.html', map: { 'project (optional)': 'project_id', 'contact (optional)': 'contact_id', 'contract (optional)': 'contract_id', 'support plan (optional)': 'plan_id', 'service / request type (optional)': 'service_code', 'request category': 'type', 'subject': 'subject', 'description': 'description', 'priority': 'priority', 'related asset (optional)': 'asset_id', 'attachment reference (optional)': 'attachment_reference' } },
    'ticket-detail.html': { resource: 'tickets', redirect: 'tickets.html', map: { 'status': 'status', 'priority': 'priority', 'assigned to': 'assigned', 'due date': 'due_date' }, alwaysUpdate: true },
  };
  let currentUser = null;
  let activeFormConfig = null;
  let customerEditMode = false;
  let customerEntityMode = false;
  let lookupData = {};
  let loadedRows = {};

  const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const labelKey = label => (label || '').replace(/\*/g, '').replace(/\s+/g, ' ').trim().toLowerCase();
  const eventRuleKey = label => { const k = labelKey(label).replace(/ /g, '_'); return k === 'new_comment_or_reply' ? 'new_reply' : k; };
  const normalStatus = value => String(value || '').trim().toLowerCase().replace(/[_-]/g, ' ');
  const fmtDate = value => {
    if (!value) return '—';
    const s = String(value).slice(0, 10);
    const d = new Date(`${s}T00:00:00`);
    return Number.isNaN(d.getTime()) ? esc(value) : d.toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: '2-digit' });
  };
  const fmtMyanmarDateTime = value => {
    if (!value) return '—';
    const d = new Date(value);
    if (Number.isNaN(d.getTime())) return String(value);
    return `${new Intl.DateTimeFormat('en-GB', { timeZone: 'Asia/Yangon', year: 'numeric', month: 'short', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: true }).format(d)} MMT`;
  };
  const badge = value => {
    const v = String(value || '—');
    const l = normalStatus(v);
    let klass = 'status-neutral';
    // Shared status palette used consistently by Tickets, Projects and Assets.
    if (l === 'open' || l === 'planning' || l === 'assigned' || l === 'new') klass = 'status-blue';
    else if (l === 'in progress' || l === 'maintenance' || l === 'active work') klass = 'status-yellow';
    else if (l === 'pending customer' || l === 'on hold' || l === 'review' || l === 'waiting') klass = 'status-orange';
    else if (l === 'resolved' || l === 'completed' || l === 'in service' || l === 'active' || l === 'success' || l === 'enabled' || l === 'yes' || l === 'included') klass = 'status-green';
    else if (l === 'closed' || l === 'retired' || l === 'deactivated' || l === 'inactive' || l === 'cancelled' || l === 'failed') klass = 'status-red';
    else if (l === 'high' || l === 'critical' || l === 'disabled' || l === 'no') klass = 'high';
    else if (l === 'medium') klass = 'medium';
    else if (l === 'low') klass = 'low';
    else if (l === 'in progress') klass = 'status-yellow';
    return `<span class="badge ${klass}">${esc(v)}</span>`;
  };
  function toast(message, type = 'success') {
    let box = document.getElementById('api-toast');
    if (!box) {
      box = document.createElement('div'); box.id = 'api-toast';
      Object.assign(box.style, { position: 'fixed', right: '20px', bottom: '20px', zIndex: '9999', maxWidth: 'min(440px,calc(100vw - 32px))', padding: '13px 16px', borderRadius: '11px', fontSize: '13px', fontWeight: '600', boxShadow: '0 12px 34px #15223b30', background: '#fff', border: '1px solid #dce3ee' });
      document.body.appendChild(box);
    }
    box.style.color = type === 'error' ? '#a92e3e' : '#176b50';
    box.style.borderColor = type === 'error' ? '#efc5cb' : '#bfe8d7';
    box.textContent = message; box.style.display = 'block';
    clearTimeout(box._hideTimer); box._hideTimer = setTimeout(() => { box.style.display = 'none'; }, 5000);
  }
  function showAlertDialog(message, title = 'Notice') {
    const dialog = document.createElement('dialog');
    dialog.className = 'gp-confirm-dialog';
    dialog.setAttribute('aria-labelledby', 'gp-alert-title');
    dialog.setAttribute('aria-describedby', 'gp-alert-message');
    dialog.innerHTML = '<div class="gp-confirm-content"><div class="gp-confirm-icon" aria-hidden="true">!</div><h2 id="gp-alert-title"></h2><p id="gp-alert-message"></p><div class="gp-confirm-actions"><button type="button" class="btn btn-primary" data-alert-ok>OK</button></div></div>';
    dialog.querySelector('#gp-alert-title').textContent = title;
    dialog.querySelector('#gp-alert-message').textContent = message;
    const close = () => { try { if (dialog.open) dialog.close(); } catch (_) { } dialog.remove(); };
    dialog.querySelector('[data-alert-ok]').addEventListener('click', close);
    dialog.addEventListener('cancel', ev => { ev.preventDefault(); close(); });
    dialog.addEventListener('close', () => dialog.remove(), { once: true });
    document.body.appendChild(dialog);
    if (typeof dialog.showModal === 'function') dialog.showModal();
    else { dialog.setAttribute('open', 'open'); Object.assign(dialog.style, { position: 'fixed', inset: '0', margin: 'auto', zIndex: '10050' }); }
    dialog.querySelector('[data-alert-ok]').focus();
    return dialog;
  }
  function confirmDialog(message, title = 'Please confirm') {
    return new Promise(resolve => {
      let dialog = document.getElementById('gp-confirm-dialog');
      if (!dialog) {
        dialog = document.createElement('dialog');
        dialog.id = 'gp-confirm-dialog';
        dialog.className = 'gp-confirm-dialog';
        dialog.innerHTML = '<div class="gp-confirm-content"><div class="gp-confirm-icon">?</div><h2 data-confirm-title></h2><p data-confirm-message></p><div class="gp-confirm-actions"><button type="button" class="btn" data-confirm-cancel>Cancel</button><button type="button" class="btn btn-primary" data-confirm-ok>OK</button></div></div>';
        document.body.appendChild(dialog);
      }
      dialog.querySelector('[data-confirm-title]').textContent = title;
      dialog.querySelector('[data-confirm-message]').textContent = message;
      const ok = dialog.querySelector('[data-confirm-ok]');
      const cancel = dialog.querySelector('[data-confirm-cancel]');
      let settled = false;
      const finish = value => { if (settled) return; settled = true; dialog.close?.(); dialog.removeAttribute('open'); ok.removeEventListener('click', onOk); cancel.removeEventListener('click', onCancel); dialog.removeEventListener('cancel', onNativeCancel); resolve(value); };
      const onOk = () => finish(true), onCancel = () => finish(false), onNativeCancel = ev => { ev.preventDefault(); finish(false); };
      ok.addEventListener('click', onOk); cancel.addEventListener('click', onCancel); dialog.addEventListener('cancel', onNativeCancel);
      if (typeof dialog.showModal === 'function') dialog.showModal(); else dialog.setAttribute('open', 'open');
      cancel.focus();
    });
  }
  async function api(url, options = {}) {
    const opts = { ...options, credentials: 'same-origin', headers: { ...(options.body ? { 'Content-Type': 'application/json' } : {}), ...(options.headers || {}) } };
    const response = await fetch(url, { ...opts, cache: 'no-store' });
    const contentType = response.headers.get('content-type') || '';
    const data = contentType.includes('application/json') ? await response.json() : await response.text();
    if (!response.ok) {
      let detail = data && typeof data === 'object'
        ? (data.detail || data.message || `Request failed (${response.status})`)
        : '';
      if (!detail && typeof data === 'string') {
        const plain = data.replace(/<script[\s\S]*?<\/script>/gi, ' ')
          .replace(/<style[\s\S]*?<\/style>/gi, ' ')
          .replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ').trim();
        detail = plain && plain.length < 320 ? plain : `Server error (${response.status}). Check the Uvicorn terminal for the full error details.`;
      }
      if (!detail) detail = `Request failed (${response.status})`;
      const error = new Error(typeof detail === 'string' ? detail : JSON.stringify(detail)); error.status = response.status; throw error;
    }
    return data;
  }
  function setSession(user) {
    currentUser = user;
    sessionStorage.setItem('gpRole', user.role);
    sessionStorage.setItem('gpName', user.fullname);
    sessionStorage.setItem('gpEmail', user.email);
    sessionStorage.setItem('gpSignedIn', 'yes');
  }
  function clearSession() {
    ['gpRole', 'gpName', 'gpEmail', 'gpSignedIn'].forEach(k => sessionStorage.removeItem(k));
  }
  async function initLogin() {
    const form = document.getElementById('login-form');
    if (!form) return;
    form.addEventListener('submit', async ev => {
      ev.preventDefault();
      const errorBox = document.getElementById('login-error');
      errorBox.classList.remove('show');
      const button = form.querySelector('[type="submit"]');
      if (button) { button.disabled = true; button.textContent = 'Signing in…'; }
      try {
        const user = await api('/api/auth/login', { method: 'POST', body: JSON.stringify({ username: document.getElementById('username').value.trim(), password: document.getElementById('password').value }) });
        setSession(user); location.href = user.must_change_password ? 'change-password.html' : user.home;
      } catch (e) {
        errorBox.textContent = e.message || 'The username or password is incorrect.'; errorBox.classList.add('show');
      } finally { if (button) { button.disabled = false; button.textContent = 'Sign in →'; } }
    });
    // A valid server-side session can go directly to its role dashboard.
    try { const user = await api('/api/auth/me'); setSession(user); location.replace(user.must_change_password ? 'change-password.html' : (homeByRole[user.role] || 'login.html')); }
    catch (_) { clearSession(); }
  }
  function profileAndGuard() {
    const role = currentUser.role, page = file;
    // The old per-role permission dashboards are intentionally removed from the user-facing product.
    if (['role-user.html', 'role-agent.html'].includes(page)) {
      location.replace(homeByRole[role] || 'login.html'); return false;
    }
    document.querySelectorAll('a[href="role-user.html"],a[href="role-agent.html"]').forEach(a => a.remove());
    document.querySelectorAll('.item').forEach(item => { if (/my permissions|view your permission details/i.test(item.textContent)) item.remove(); });
    document.querySelectorAll('a,button').forEach(el => { if (/my permissions/i.test(el.textContent || '')) el.remove(); });
    if (currentUser.must_change_password && page !== 'change-password.html') { location.replace('change-password.html'); return false; }
    if (allowedByRole[role] && !allowedByRole[role].includes(page)) {
      location.replace(`${homeByRole[role]}?denied=${encodeURIComponent(page)}`); return false;
    }
    configureRoleNavigation(role);
    configureRoleActions(role);
    ensureSidebarProfile();
    const brandCaption = document.querySelector('.sidebar .brand small');
    if (brandCaption) {
      const teams = Array.isArray(currentUser.team_names) ? currentUser.team_names.filter(Boolean) : [];
      brandCaption.textContent = role === 'agent' ? (teams.join(' · ') || currentUser.team_name || 'Support Team') : 'Service workspace';
      brandCaption.title = brandCaption.textContent;
    }
    document.querySelectorAll('[data-customer-name]').forEach(el => { if (el.matches('input,textarea')) el.value = currentUser.fullname; else el.textContent = currentUser.fullname; });
    document.querySelectorAll('[data-customer-email]').forEach(el => { if (el.matches('input,textarea')) el.value = currentUser.email; else el.textContent = currentUser.email; });
    document.querySelectorAll('[data-customer-avatar]').forEach(el => el.textContent = currentUser.fullname.split(/\s+/).map(x => x[0]).join('').slice(0, 2).toUpperCase());
    const profile = document.querySelector('.sidebar-bottom');
    if (profile) {
      const avatar = profile.querySelector('.avatar'); if (avatar) avatar.textContent = currentUser.fullname.split(/\s+/).map(x => x[0]).join('').slice(0, 2).toUpperCase();
      const strong = profile.querySelector('strong'); if (strong) strong.textContent = currentUser.fullname;
      const small = profile.querySelector('small'); if (small) small.textContent = currentUser.email;
    }
    if (!document.body.dataset.logoutHandlerInstalled) {
      document.body.dataset.logoutHandlerInstalled = '1';
      document.addEventListener('click', async ev => { const el = ev.target.closest('[data-logout]'); if (!el) return; ev.preventDefault(); try { await api('/api/auth/logout', { method: 'POST' }); } catch (_) { } clearSession(); location.href = 'login.html'; });
    }
    document.querySelectorAll('a[href="dashboard.html"]').forEach(a => a.setAttribute('href', homeByRole[role] || 'dashboard.html'));
    const denied = params.get('denied');
    if (denied) { const box = document.getElementById('access-notice'); if (box) { box.className = 'access-callout'; box.textContent = `Access restricted: your ${role} role does not have permission to open ${denied}.`; } }
    return true;
  }
  function configureRoleNavigation(role) {
    const nav = document.querySelector('.sidebar .nav');
    if (!nav || role === 'admin') {
      document.querySelectorAll('a[href="role-user.html"],a[href="role-agent.html"]').forEach(a => a.remove());
      return;
    }
    const agentLinks = [
      ['agent-dashboard.html', '▦', 'Dashboard'], ['tickets.html', '▤', 'Tickets'], ['customers.html', '♙', 'Customers'],
      ['projects.html', '◈', 'Projects'], ['contracts.html', '▣', 'Contracts'], ['support-plans.html', '◇', 'Support Plans'],
      ['service-catalog.html', '☷', 'Service Catalog'], ['contacts.html', '♧', 'Contacts'], ['assets.html', '▧', 'Assets'], ['email-notifications.html', '✉', 'Email Notifications']
    ];
    const customerLinks = [
      ['user-dashboard.html', '▦', 'Dashboard'], ['my-tickets.html', '▤', 'My Tickets'],
      ['user-create-ticket.html', '＋', 'Create Ticket'], ['user-service-catalog.html', '☷', 'Service Catalog'], ['user-assets.html', '▧', 'My Assets'], ['email-notifications.html', '✉', 'Email Notifications']
    ];
    const links = role === 'customer' ? customerLinks : agentLinks;
    nav.replaceChildren();
    links.forEach(([href, icon, label]) => {
      const a = document.createElement('a'); a.href = href;
      const target = href.toLowerCase();
      const aliases = {
        'tickets.html': ['add-ticket.html', 'ticket-detail.html'],
        'customers.html': ['add-customer.html', 'customer-detail.html'],
        'service-catalog.html': ['add-service.html', 'add-request-type.html'],
        'user-create-ticket.html': ['user-create-ticket.html'],
        'my-tickets.html': ['user-ticket-detail.html'],
        'user-dashboard.html': ['dashboard.html'],
        'agent-dashboard.html': ['dashboard.html']
      };
      if (target === file || (aliases[target] || []).includes(file) || (file === 'dashboard.html' && target === homeByRole[role])) a.className = 'active';
      const i = document.createElement('span'); i.className = 'nav-icon'; i.textContent = icon;
      const name = document.createElement('span'); name.textContent = label;
      a.append(i, name); nav.appendChild(a);
    });
  }
  function configureRoleActions(role) {
    if (role !== 'agent') return;
    // Agents work tickets assigned to them or routed to their Support Team; ticket creation is reserved for Admins and Customers.
    const blockedPages = new Set(['add-ticket.html',
      'add-project.html', 'add-customer.html', 'add-contract.html',
      'add-request-type.html', 'add-service.html', 'add-support-plan.html',
      'add-contact.html', 'add-asset.html'
    ]);
    document.querySelectorAll('a[href]').forEach(link => {
      const raw = (link.getAttribute('href') || '').split(/[?#]/, 1)[0].toLowerCase();
      const label = (link.textContent || '').trim();
      if (blockedPages.has(raw) || raw === 'add-ticket.html') link.remove();
      // Template editing is not implemented by this version of the backend.
      else if (raw === '#templates' && /^edit( templates)?$/i.test(label)) link.remove();
    });
    // These registers have no Agent-supported row action; remove the dead column immediately,
    // even before the API has replaced the page's sample rows.
    if (['projects.html', 'contracts.html', 'support-plans.html', 'service-catalog.html', 'contacts.html'].includes(file)) {
      document.querySelectorAll('table').forEach(table => {
        const heads = [...table.querySelectorAll('thead th')];
        const index = heads.findIndex(th => /^actions?$/i.test(th.textContent.trim()));
        if (index >= 0) { heads[index].remove(); table.querySelectorAll('tbody tr').forEach(tr => tr.children[index]?.remove()); }
      });
    }
    // Remove only top-bar Add/Create shortcuts; keep the real Add buttons inside page content.
    document.querySelectorAll('.topbar .top-actions a,.topbar .top-actions button').forEach(el => {
      const label = (el.textContent || '').trim().replace(/^\+\s*/, '');
      if (/^(add|create)\s+(ticket|project|customer|contract|request type|service|support plan|contact|asset|user|team)\b/i.test(label)) el.remove();
    });
  }
  function installNotificationCenter() {
    const topActions = document.querySelector('.topbar .top-actions');
    if (!topActions || document.getElementById('gp-notification-wrap')) return;
    const style = document.createElement('style');
    style.textContent = `.gp-notification-wrap{position:relative;display:inline-flex;align-items:center}.gp-notification-bell{position:relative;border:1px solid #7653d6;background:#7653d6;border-radius:9px;padding:9px 12px;cursor:pointer;font-size:13px;font-weight:700;color:#fff}.gp-notification-count{display:inline-flex;min-width:18px;height:18px;align-items:center;justify-content:center;border-radius:20px;background:#fff;color:#7653d6;border:1px solid #d8cdf7;font-size:10px;margin-left:5px;padding:0 4px}.gp-notification-panel{display:none;position:absolute;right:0;top:calc(100% + 9px);width:min(390px,calc(100vw - 30px));max-height:470px;overflow:auto;background:#fff;border:1px solid #e3e7ee;border-radius:12px;box-shadow:0 14px 38px rgba(12,26,46,.18);z-index:1000}.gp-notification-panel.open{display:block}.gp-notification-head{display:flex;justify-content:space-between;align-items:center;padding:13px 14px;border-bottom:1px solid #edf0f4;font-size:13px;font-weight:800}.gp-notification-head button{border:0;background:none;color:#7653d6;font-size:11px;font-weight:700;cursor:pointer}.gp-notification-item{display:block;width:100%;padding:12px 14px;border:0;border-bottom:1px solid #f0f2f5;background:#fff;text-align:left;cursor:pointer}.gp-notification-item.unread{background:#f5f0ff}.gp-notification-item strong{display:block;font-size:12px;color:#263143}.gp-notification-item small{display:block;font-size:10px;color:#8b93a0;margin:4px 0}.gp-notification-item span{display:block;font-size:11px;color:#586273;line-height:1.45}.gp-notification-empty{padding:24px 14px;text-align:center;color:#8a929e;font-size:12px}`;
    document.head.appendChild(style);
    const wrap = document.createElement('div'); wrap.className = 'gp-notification-wrap'; wrap.id = 'gp-notification-wrap';
    const bell = document.createElement('button'); bell.type = 'button'; bell.className = 'gp-notification-bell'; bell.innerHTML = '🔔 Notifications <span class="gp-notification-count" id="gp-notification-count">0</span>';
    const panel = document.createElement('div'); panel.className = 'gp-notification-panel'; panel.id = 'gp-notification-panel';
    const head = document.createElement('div'); head.className = 'gp-notification-head'; head.innerHTML = '<span>Notifications</span><button type="button" id="gp-notification-read-all">Mark all read</button>';
    const list = document.createElement('div'); list.id = 'gp-notification-list'; panel.append(head, list); wrap.append(bell, panel);
    topActions.prepend(wrap);
    bell.addEventListener('click', () => { panel.classList.toggle('open'); if (panel.classList.contains('open')) loadNotifications(); });
    document.addEventListener('click', ev => { if (!wrap.contains(ev.target)) panel.classList.remove('open'); });
    document.getElementById('gp-notification-read-all')?.addEventListener('click', async () => { try { await api('/api/notifications/read-all', { method: 'POST' }); await loadNotifications(); } catch (e) { toast(e.message, 'error'); } });
    async function loadNotifications() {
      try {
        const data = await api('/api/notifications?limit=30');
        const count = document.getElementById('gp-notification-count'); if (count) count.textContent = data.unread_count > 99 ? '99+' : String(data.unread_count || 0);
        list.replaceChildren();
        if (!data.items?.length) { const empty = document.createElement('div'); empty.className = 'gp-notification-empty'; empty.textContent = 'No notifications yet.'; list.appendChild(empty); return; }
        data.items.forEach(item => {
          const button = document.createElement('button'); button.type = 'button'; button.className = 'gp-notification-item' + (!item.is_read ? ' unread' : '');
          const when = item.created_at ? new Date(item.created_at).toLocaleString() : '';
          button.innerHTML = `<strong>${esc(item.title)}</strong><small>${esc(when)}${item.actor_name ? ' · ' + esc(item.actor_name) : ''}</small><span>${esc(item.message)}</span>`;
          button.addEventListener('click', async () => {
            try { await api(`/api/notifications/${item.notification_id}/read`, { method: 'POST' }); } catch (_) { }
            panel.classList.remove('open');
            if (item.ticket_id) { const target = currentUser?.role === 'customer' ? 'user-ticket-detail.html' : 'ticket-detail.html'; location.href = `${target}?id=${encodeURIComponent(item.ticket_id)}`; }
            else await loadNotifications();
          });
          list.appendChild(button);
        });
      } catch (_) {/* The user may be signed out during navigation. */ }
    }
    loadNotifications();
    window.setInterval(loadNotifications, 30000);
  }

  function ensureSidebarProfile() {
    const sidebar = document.querySelector('.sidebar'); if (!sidebar) return;
    let profile = sidebar.querySelector('.sidebar-bottom');
    if (!profile) { profile = document.createElement('div'); profile.className = 'sidebar-bottom'; sidebar.appendChild(profile); }
    if (!profile.querySelector('[data-logout]')) {
      const identity = document.createElement('div');
      const name = document.createElement('strong'); name.dataset.customerName = ''; name.textContent = 'Signed-in user';
      const email = document.createElement('small'); email.dataset.customerEmail = ''; email.textContent = '';
      const logout = document.createElement('a'); logout.href = 'login.html'; logout.dataset.logout = ''; logout.className = 'logout-link'; logout.textContent = 'Sign out ↗';
      identity.append(name, email, logout);
      if (!profile.querySelector('.avatar')) { const avatar = document.createElement('div'); avatar.className = 'avatar'; avatar.dataset.customerAvatar = ''; avatar.textContent = 'GP'; profile.appendChild(avatar); }
      profile.appendChild(identity);
    }
  }

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
    renderDashboardStatusChart(stats.daily_breakdown || []);
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

  function renderDashboardStatusChart(dailyRows) {
    const target = document.querySelector('[data-dashboard-status-chart]');
    if (!target) return;
    target.replaceChildren();
    const days = Array.isArray(dailyRows) ? dailyRows : [];
    const maxTotal = Math.max(1, ...days.map(day => Number(day.total) || 0));
    const series = [
      { key: 'Open', label: 'Open', className: 'open' },
      { key: 'In Progress', label: 'In Progress', className: 'progress' },
      { key: 'Pending Customer', label: 'Pending Customer', className: 'pending' },
      { key: 'Resolved', label: 'Resolved', className: 'resolved' },
      { key: 'Closed', label: 'Closed', className: 'closed' },
      { key: 'Other', label: 'Other', className: 'other' }
    ];
    if (!days.length) {
      const empty = document.createElement('p');
      empty.className = 'muted dashboard-empty';
      empty.textContent = 'No ticket data is available yet.';
      target.appendChild(empty);
      return;
    }

    const chart = document.createElement('div');
    chart.className = 'dashboard-daily-chart';
    days.forEach(day => {
      const column = document.createElement('div');
      column.className = 'dashboard-day-column';
      const total = Number(day.total) || 0;
      const value = document.createElement('strong');
      value.className = 'dashboard-day-total';
      value.textContent = String(total);
      const stack = document.createElement('div');
      stack.className = 'dashboard-day-stack';
      stack.setAttribute('aria-label', `${day.date}: ${total} tickets created`);
      series.forEach(item => {
        const count = Number(day[item.key]) || 0;
        if (!count) return;
        const segment = document.createElement('div');
        segment.className = `dashboard-day-segment status-${item.className}`;
        segment.style.height = `${(count / maxTotal) * 150}px`;
        segment.title = `${item.label}: ${count}`;
        stack.appendChild(segment);
      });
      const label = document.createElement('span');
      label.className = 'dashboard-day-label';
      label.textContent = String(day.label || day.date || '—');
      label.title = String(day.date || '');
      column.append(value, stack, label);
      chart.appendChild(column);
    });
    target.appendChild(chart);

    const legend = document.createElement('div');
    legend.className = 'dashboard-chart-legend';
    series.forEach(item => {
      const count = days.reduce((sum, day) => sum + (Number(day[item.key]) || 0), 0);
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
    const recentTotal = days.reduce((sum, day) => sum + (Number(day.total) || 0), 0);
    const summary = document.createElement('div');
    summary.className = 'dashboard-chart-summary';
    summary.textContent = `${recentTotal.toLocaleString()} tickets created in the last 7 days · Live database data`;
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
    if (!isAdmin) {
      adminSections.forEach(el => el.classList.add('hidden'));
      if (metrics) metrics.classList.add('hidden');
      const personal = document.getElementById('personal-preferences'); if (personal) personal.style.display = 'block';
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
    };
    toggle.addEventListener('click', () => sidebar.classList.contains('mobile-open') ? close() : open());
    backdrop.addEventListener('click', close);
    sidebar.querySelectorAll('.nav a, .brand, [data-logout]').forEach(link => link.addEventListener('click', close));
    document.addEventListener('keydown', event => { if (event.key === 'Escape') close(); });
    window.addEventListener('resize', () => { if (window.innerWidth > 900) close(); });
  }

  async function initPage() {
    let user;
    try { user = await api('/api/auth/me'); }
    catch (_) { clearSession(); location.replace('login.html'); return; }
    setSession(user);
    // dashboard.html is the retired prototype page; route users to their live,
    // role-specific dashboard instead of displaying its former sample figures.
    if (file === 'dashboard.html') {
      location.replace(homeByRole[user.role] || 'login.html');
      return;
    }
    if (!profileAndGuard()) return;
    if (file === 'tickets.html' && Number(params.get('consolidated') || 0) > 0) {
      const count = Number(params.get('consolidated'));
      toast(`${count} duplicate ticket${count === 1 ? ' was' : 's were'} closed for the same Project and Request Type.`);
      const cleanUrl = new URL(location.href); cleanUrl.searchParams.delete('consolidated'); history.replaceState({}, '', cleanUrl);
    }
    if (file === 'customers.html' && params.get('customer_created') === '1') {
      const linked = params.get('linked_user_created') === '1';
      toast(linked
        ? 'Customer created. A linked Customer login was added to User Management. Use Reset password to issue the first sign-in password.'
        : 'Customer profile created and linked to the existing Customer login.');
      const cleanUrl = new URL(location.href); cleanUrl.searchParams.delete('customer_created'); cleanUrl.searchParams.delete('linked_user_created'); history.replaceState({}, '', cleanUrl);
    }
    installResponsiveNavigation();
    document.querySelectorAll('.compact-alert,.alert-button,[data-alert]').forEach(el => el.remove());
    document.querySelectorAll('a,button,[role=button]').forEach(el => {
      const label = [el.textContent, el.getAttribute('aria-label'), el.getAttribute('title')].filter(Boolean).join(' ').trim();
      if (/^alerts?$/i.test(label) || /^(?:🔔|\u{1F514})\s*alerts?$/iu.test(label)) el.remove();
    });
    document.querySelectorAll('.topbar .top-actions a,.topbar .top-actions button').forEach(el => {
      const label = (el.textContent || '').replace(/^\+\s*/, '').trim();
      if (/^new ticket$/i.test(label) || /^ticket workspace$/i.test(label) || /^add (customer|project|contract|plan|support plan|request type|contact|asset|user|team)$/i.test(label)) el.remove();
    });
    installNotificationCenter();
    try { await loadLookups(); } catch (_) { }
    if (file === 'add-contact.html') {
      try { lookupData.allContacts = await api('/api/contacts'); }
      catch (_) { lookupData.allContacts = lookupData.contacts || []; }
    }
    let cfg = formConfig[file];
    if (file === 'add-customer.html') {
      const isEdit = Boolean(idParam);
      setupCustomerEntityMode(isEdit);
      cfg = customerEntityConfig;
    }
    activeFormConfig = cfg;
    configureSelects();
    setupUserTeamField();
    setupTeamMembersField();
    setupOtherSupportPlanType();
    setupOtherServiceCategory();
    setupOtherMappedTeam();
    setupNonNegativeSupportPlanFields();
    setupDateConstraints();
    setupPhoneEmailValidation();
    if (cfg && !cfg.alwaysUpdate) {
      try { await fillEditForm(cfg); } catch (e) {
        toast(e.message, 'error');
        if (e.status === 404 && idParam) {
          const form = getMainForm();
          if (form) {
            form.querySelectorAll('input:not([type=hidden]), textarea').forEach(el => { if (el.type === 'checkbox' || el.type === 'radio') el.checked = false; else el.value = ''; });
            form.querySelectorAll('select').forEach(el => { el.selectedIndex = 0; });
            form.querySelectorAll('[type=submit]').forEach(button => button.disabled = true);
            const notice = document.createElement('div'); notice.className = 'notice warning';
            notice.textContent = 'This record has already been deleted. It cannot be edited or saved.';
            form.closest('.card')?.querySelector('.card-body')?.prepend(notice) || form.prepend(notice);
          }
        }
      }
      setupDateConstraints();
      setupDependentDropdowns();
      setupPrimaryContactRule();
      setupUserStatusActions();
      await handleStandardForm(cfg);
    } else {
      setupDependentDropdowns();
      setupPrimaryContactRule();
    }
    if (file === 'ticket-detail.html') { await handleTicketDetail(); await handleStaffTicketConversation(); }
    if (file === 'user-create-ticket.html') await handleCustomerCreateTicket();
    if (file === 'user-ticket-detail.html') await handleTicketConversation();
    if (file === 'asset-detail.html' || file === 'customer-detail.html') await handleEditDetails();
    if (file === 'email-notifications.html') await handleEmailPage();
    if (file === 'change-password.html') await handleChangePassword();
    if (file === 'add-role.html') await handleRoleForm();
    if (pageResource[file]) await loadList(pageResource[file]);
    if (file === 'audit-log.html') await handleAuditPage();
    if (['dashboard.html', 'admin-dashboard.html', 'agent-dashboard.html', 'user-dashboard.html'].includes(file)) {
      await refreshDashboard();
      window.setInterval(() => { if (document.visibilityState === 'visible') refreshDashboard(); }, 15000);
    }
    installSearch();
    try {
      const savedScroll = sessionStorage.getItem(scrollKey);
      const y = Math.max(0, Number(savedScroll || 0));
      if (y > 0) {
        // Wait until the page's async content has rendered before restoring.
        requestAnimationFrame(() => requestAnimationFrame(() => {
          window.scrollTo({ top: y, behavior: 'auto' });
        }));
      }
    } catch (_) {
      // If storage is unavailable, leave the browser's default initial position.
    }
    // Update older prototype-only copy without changing the supplied page layout/features.
    document.querySelectorAll('.notice').forEach(n => { if (/static prototype does not save submitted data/i.test(n.textContent)) n.textContent = 'Records are saved securely to the connected database when you submit this form.'; if (/prototype mode/i.test(n.textContent) && file === 'email-notifications.html') n.textContent = 'Email delivery runs through the Python backend. Configure SMTP settings below to send notifications.'; });
  }
  // Do not flash or briefly resurrect hard-coded prototype rows on refresh.
  document.querySelectorAll('.table-wrap table tbody').forEach(tbody => tbody.replaceChildren());
  if (file === 'user-service-catalog.html') document.querySelector('.three-col')?.replaceChildren();
  if (file === 'login.html') initLogin();
  else initPage();
})();
