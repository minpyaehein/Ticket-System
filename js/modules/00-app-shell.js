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
    function positionNotificationPanel() {
      if (!panel.classList.contains('open')) return;
      if (window.innerWidth <= 640) {
        const rect = bell.getBoundingClientRect();
        const width = Math.max(0, Math.min(390, window.innerWidth - 24));
        const left = Math.max(12, Math.min(rect.left, window.innerWidth - width - 12));
        const top = rect.bottom + 9;
        panel.style.position = 'fixed';
        panel.style.left = `${left}px`;
        panel.style.right = 'auto';
        panel.style.top = `${top}px`;
        panel.style.width = `${width}px`;
        panel.style.maxWidth = `${width}px`;
        panel.style.maxHeight = `${Math.max(120, Math.min(470, window.innerHeight - top - 12))}px`;
        panel.style.boxSizing = 'border-box';
      } else {
        panel.removeAttribute('style');
      }
    }
    bell.addEventListener('click', () => {
      panel.classList.toggle('open');
      if (panel.classList.contains('open')) {
        positionNotificationPanel();
        loadNotifications();
      }
    });
    window.addEventListener('resize', positionNotificationPanel);
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

