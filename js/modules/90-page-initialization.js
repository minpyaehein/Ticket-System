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
    if (file === 'email-notifications.html') {
      try { await handleEmailPage(); }
      finally { document.documentElement.classList.remove('gp-email-role-pending'); }
    }
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
