/* Golden Pride: keeps the supplied HTML/CSS pages and connects them to FastAPI/PostgreSQL. */
(() => {
  'use strict';
  const file = (location.pathname.split('/').pop() || 'login.html').toLowerCase();
  const params = new URLSearchParams(location.search);
  const idParam = params.get('id');
  const scrollKey = 'gpScroll:' + location.pathname + location.search;
  if ('scrollRestoration' in history) history.scrollRestoration = 'manual';
  window.addEventListener('pagehide', () => { try { sessionStorage.setItem(scrollKey, String(window.scrollY)); } catch (_) {} });
  document.addEventListener('click', ev => {
    const a = ev.target.closest('a[href]');
    if (!a || a.hasAttribute('data-logout') || a.getAttribute('href') === '#' || a.target === '_blank') return;
    const url = new URL(a.href, location.href);
    if (url.origin === location.origin && !/^(mailto:|tel:)/i.test(a.getAttribute('href') || '')) {
      try { sessionStorage.setItem('gpNextScroll', String(window.scrollY)); } catch (_) {}
    }
  }, true);
  const homeByRole = { admin: 'admin-dashboard.html', agent: 'agent-dashboard.html', customer: 'user-dashboard.html' };
  const allowedByRole = {
    admin: null,
    agent: ['agent-dashboard.html','dashboard.html','tickets.html','add-ticket.html','ticket-detail.html','customers.html','customer-detail.html','projects.html','contracts.html','support-plans.html','service-catalog.html','contacts.html','assets.html','asset-detail.html','email-notifications.html','change-password.html'],
    customer: ['user-dashboard.html','my-tickets.html','user-create-ticket.html','user-ticket-detail.html','user-service-catalog.html','user-assets.html','email-notifications.html','change-password.html']
  };
  const pageResource = {
    'tickets.html':'tickets','my-tickets.html':'tickets','dashboard.html':'tickets',
    'admin-dashboard.html':'tickets','agent-dashboard.html':'tickets','user-dashboard.html':'tickets',
    'projects.html':'projects','customers.html':'customers','contacts.html':'contacts','contracts.html':'contracts',
    'support-plans.html':'plans','service-catalog.html':'services','user-service-catalog.html':'services',
    'teams.html':'teams','users.html':'users','assets.html':'assets','user-assets.html':'assets','audit-log.html':'audit-logs'
  };
  const customerEntityConfig = {resource:'customers', redirect:'customers.html', map:{'company name':'customer_name','initial contact name':'contact_name','general email':'email','phone':'phone','address':'address'}};
  const customerEditConfig = customerEntityConfig;
  const formConfig = {
    'add-asset.html': {resource:'assets', redirect:'assets.html', map:{'customer':'customer_id','project':'project_id','asset tag':'asset_tag','asset name':'asset_name','type':'type','asset status':'status','vendor':'vendor','model':'model','serial number':'serial_no','ip address':'ip_address','note':'note'}},
    'add-contact.html': {resource:'contacts', redirect:'contacts.html', map:{'customer':'customer_id','contact no':'contact_code','full name':'fullname','department':'department','job title':'job_title','email':'email','phone':'phone','type':'type','notes':'note'}},
    'add-contract.html': {resource:'contracts', redirect:'contracts.html', map:{'customer':'customer_id','project':'project_id','contract no':'contract_code','contract name':'contract_name','support plan':'plan_id','start date':'start_date','end date':'end_date','scope / covered service':'scope'}},
    'add-user.html': {resource:'users', redirect:'users.html', map:{'full name':'fullname','email':'email','password':'password','role':'role','support team':'team_id','notes':'notes'}},
    'add-project.html': {resource:'projects', redirect:'projects.html', map:{'customer':'customer_id','project code':'project_code','project name':'project_name','project manager':'project_manager','project status':'status','start date':'start_date','end date':'end_date','description':'description'}},
    'add-service.html': {resource:'services', redirect:'service-catalog.html', map:{'code':'code_id','name':'name','category':'category','sort order':'request_order','customer visible':'customer_visible','asset requirements':'asset_requirement','mapped team':'mapped_team','auto assign':'auto_assign','assignment method':'assignment_method','description':'description'}},
    'add-request-type.html': {resource:'services', redirect:'service-catalog.html', map:{'code':'code_id','name':'name','category':'category','sort order':'request_order','customer visible':'customer_visible','asset requirements':'asset_requirement','mapped team':'mapped_team','auto assign':'auto_assign','assignment method':'assignment_method','description':'description'}},
    'add-support-plan.html': {resource:'plans', redirect:'support-plans.html', map:{'plan code':'plan_code','plan name':'plan_name','response sla':'response_sla','resolution sla':'resolution_sla','response warning %':'response_warning','response critical %':'response_critical','resolution warning %':'resolution_warning','resolution critical %':'resolution_critical','sla calendar mode':'sla_mode','time zone':'time_zone','business start':'business_start_hour','business end':'business_end_hour','working days':'working_days','escalation level':'escalation_level','remote support':'remote_support','onsite support':'onsite_support','description':'description'}},
    'add-team.html': {resource:'teams', redirect:'teams.html', map:{'team code':'team_code','team name':'team_name','team members':'member','service catalog':'service_codes','description':'description'}},
    'add-ticket.html': {resource:'tickets', redirect:'tickets.html', map:{'ticket':'customer_id','customer/project':'project_id','contact':'contact_id','contract / plan':'contract_id','request type':'type','subject':'subject','description':'description','status':'status','priority':'priority','asset':'asset_id','assigned':'assigned','created':'date','due date':'due_date','attachment reference':'attachment_reference'}},
    'user-create-ticket.html': {resource:'tickets', redirect:'my-tickets.html', map:{'service':'service_code','request type':'type','subject':'subject','description':'description','related asset (optional)':'asset_id','attachment reference (optional)':'attachment_reference'}},
    'ticket-detail.html': {resource:'tickets', redirect:'tickets.html', map:{'status':'status','priority':'priority','assigned to':'assigned','due date':'due_date'}, alwaysUpdate:true},
  };
  let currentUser = null;
  let activeFormConfig = null;
  let customerEditMode = false;
  let customerEntityMode = false;
  let lookupData = {};
  let loadedRows = {};

  const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const labelKey = label => (label || '').replace(/\*/g,'').replace(/\s+/g,' ').trim().toLowerCase();
  const eventRuleKey = label => { const k=labelKey(label).replace(/ /g,'_'); return k==='new_comment_or_reply' ? 'new_reply' : k; };
  const normalStatus = value => String(value || '').trim().toLowerCase().replace(/[_-]/g,' ');
  const fmtDate = value => {
    if (!value) return '—';
    const s = String(value).slice(0,10);
    const d = new Date(`${s}T00:00:00`);
    return Number.isNaN(d.getTime()) ? esc(value) : d.toLocaleDateString(undefined,{year:'numeric',month:'short',day:'2-digit'});
  };
  const badge = value => {
    const v = String(value || '—');
    const l = normalStatus(v);
    let klass = 'open';
    if (['closed','resolved','active','in service','success','included','enabled','yes','assigned','completed'].includes(l)) klass = 'closed';
    else if (['in progress','pending customer','waiting','medium','planning','on hold'].includes(l)) klass = 'progress';
    else if (['high','critical','failed','retired','disabled','no','maintenance'].includes(l)) klass = 'high';
    return `<span class="badge ${klass}">${esc(v)}</span>`;
  };
  function toast(message, type='success') {
    let box = document.getElementById('api-toast');
    if (!box) {
      box = document.createElement('div'); box.id='api-toast';
      Object.assign(box.style,{position:'fixed',right:'20px',bottom:'20px',zIndex:'9999',maxWidth:'min(440px,calc(100vw - 32px))',padding:'13px 16px',borderRadius:'11px',fontSize:'13px',fontWeight:'600',boxShadow:'0 12px 34px #15223b30',background:'#fff',border:'1px solid #dce3ee'});
      document.body.appendChild(box);
    }
    box.style.color = type==='error' ? '#a92e3e' : '#176b50';
    box.style.borderColor = type==='error' ? '#efc5cb' : '#bfe8d7';
    box.textContent = message; box.style.display='block';
    clearTimeout(box._hideTimer); box._hideTimer = setTimeout(()=>{box.style.display='none';},5000);
  }
  function confirmDialog(message, title='Please confirm') {
    return new Promise(resolve => {
      let dialog=document.getElementById('gp-confirm-dialog');
      if(!dialog){
        dialog=document.createElement('dialog');
        dialog.id='gp-confirm-dialog';
        dialog.className='gp-confirm-dialog';
        dialog.innerHTML='<div class="gp-confirm-content"><div class="gp-confirm-icon">?</div><h2 data-confirm-title></h2><p data-confirm-message></p><div class="gp-confirm-actions"><button type="button" class="btn" data-confirm-cancel>Cancel</button><button type="button" class="btn btn-primary" data-confirm-ok>OK</button></div></div>';
        document.body.appendChild(dialog);
      }
      dialog.querySelector('[data-confirm-title]').textContent=title;
      dialog.querySelector('[data-confirm-message]').textContent=message;
      const ok=dialog.querySelector('[data-confirm-ok]');
      const cancel=dialog.querySelector('[data-confirm-cancel]');
      let settled=false;
      const finish=value=>{if(settled)return;settled=true;dialog.close?.();dialog.removeAttribute('open');ok.removeEventListener('click',onOk);cancel.removeEventListener('click',onCancel);dialog.removeEventListener('cancel',onNativeCancel);resolve(value);};
      const onOk=()=>finish(true),onCancel=()=>finish(false),onNativeCancel=ev=>{ev.preventDefault();finish(false);};
      ok.addEventListener('click',onOk);cancel.addEventListener('click',onCancel);dialog.addEventListener('cancel',onNativeCancel);
      if(typeof dialog.showModal==='function')dialog.showModal();else dialog.setAttribute('open','open');
      cancel.focus();
    });
  }
  async function api(url, options={}) {
    const opts = {...options, credentials:'same-origin', headers:{...(options.body ? {'Content-Type':'application/json'} : {}), ...(options.headers||{})}};
    const response = await fetch(url, opts);
    const contentType = response.headers.get('content-type') || '';
    const data = contentType.includes('application/json') ? await response.json() : await response.text();
    if (!response.ok) {
      const detail = data && typeof data==='object' ? (data.detail || data.message || `Request failed (${response.status})`) : `Request failed (${response.status})`;
      const error = new Error(typeof detail==='string' ? detail : JSON.stringify(detail)); error.status=response.status; throw error;
    }
    return data;
  }
  function setSession(user) {
    currentUser=user;
    sessionStorage.setItem('gpRole', user.role);
    sessionStorage.setItem('gpName', user.fullname);
    sessionStorage.setItem('gpEmail', user.email);
    sessionStorage.setItem('gpSignedIn','yes');
  }
  function clearSession() {
    ['gpRole','gpName','gpEmail','gpSignedIn'].forEach(k=>sessionStorage.removeItem(k));
  }
  async function initLogin() {
    const form=document.getElementById('login-form');
    if (!form) return;
    form.addEventListener('submit',async ev=>{
      ev.preventDefault();
      const errorBox=document.getElementById('login-error');
      errorBox.classList.remove('show');
      const button=form.querySelector('[type="submit"]');
      if(button){button.disabled=true;button.textContent='Signing in…';}
      try {
        const user=await api('/api/auth/login',{method:'POST',body:JSON.stringify({username:document.getElementById('username').value.trim(),password:document.getElementById('password').value,role:document.getElementById('role').value.toLowerCase()})});
        setSession(user); location.href=user.must_change_password ? 'change-password.html' : user.home;
      } catch(e) {
        errorBox.textContent=e.message || 'The username or password is incorrect.'; errorBox.classList.add('show');
      } finally {if(button){button.disabled=false;button.textContent='Sign in →';}}
    });
    // A valid server-side session can go directly to its role dashboard.
    try { const user=await api('/api/auth/me'); setSession(user); location.replace(user.must_change_password ? 'change-password.html' : (homeByRole[user.role] || 'login.html')); }
    catch (_) { clearSession(); }
  }
  function profileAndGuard() {
    const role=currentUser.role, page=file;
    // The old per-role permission dashboards are intentionally removed from the user-facing product.
    if (['role-user.html','role-agent.html'].includes(page)) {
      location.replace(homeByRole[role] || 'login.html'); return false;
    }
    document.querySelectorAll('a[href="role-user.html"],a[href="role-agent.html"]').forEach(a=>a.remove());
    document.querySelectorAll('.item').forEach(item=>{if(/my permissions|view your permission details/i.test(item.textContent)) item.remove();});
    document.querySelectorAll('a,button').forEach(el=>{if(/my permissions/i.test(el.textContent||'')) el.remove();});
    if (currentUser.must_change_password && page !== 'change-password.html') { location.replace('change-password.html'); return false; }
    if (allowedByRole[role] && !allowedByRole[role].includes(page)) {
      location.replace(`${homeByRole[role]}?denied=${encodeURIComponent(page)}`); return false;
    }
    configureRoleNavigation(role);
    ensureSidebarProfile();
    document.querySelectorAll('[data-customer-name]').forEach(el=>{if(el.matches('input,textarea')) el.value=currentUser.fullname; else el.textContent=currentUser.fullname;});
    document.querySelectorAll('[data-customer-email]').forEach(el=>{if(el.matches('input,textarea')) el.value=currentUser.email; else el.textContent=currentUser.email;});
    document.querySelectorAll('[data-customer-avatar]').forEach(el=>el.textContent=currentUser.fullname.split(/\s+/).map(x=>x[0]).join('').slice(0,2).toUpperCase());
    const profile=document.querySelector('.sidebar-bottom');
    if(profile){
      const avatar=profile.querySelector('.avatar'); if(avatar) avatar.textContent=currentUser.fullname.split(/\s+/).map(x=>x[0]).join('').slice(0,2).toUpperCase();
      const strong=profile.querySelector('strong'); if(strong) strong.textContent=currentUser.fullname;
      const small=profile.querySelector('small'); if(small) small.textContent=currentUser.email;
    }
    if(!document.body.dataset.logoutHandlerInstalled){
      document.body.dataset.logoutHandlerInstalled='1';
      document.addEventListener('click',async ev=>{const el=ev.target.closest('[data-logout]');if(!el)return;ev.preventDefault();try{await api('/api/auth/logout',{method:'POST'});}catch(_){}clearSession();location.href='login.html';});
    }
    document.querySelectorAll('a[href="dashboard.html"]').forEach(a=>a.setAttribute('href',homeByRole[role]||'dashboard.html'));
    const denied=params.get('denied');
    if(denied){const box=document.getElementById('access-notice');if(box){box.className='access-callout';box.textContent=`Access restricted: your ${role} role does not have permission to open ${denied}.`;}}
    return true;
  }
  function configureRoleNavigation(role) {
    const nav=document.querySelector('.sidebar .nav');
    if(!nav || role==='admin') {
      document.querySelectorAll('a[href="role-user.html"],a[href="role-agent.html"]').forEach(a=>a.remove());
      return;
    }
    const agentLinks=[
      ['agent-dashboard.html','▦','Dashboard'],['tickets.html','▤','Tickets'],['customers.html','♙','Customers'],
      ['projects.html','◈','Projects'],['contracts.html','▣','Contracts'],['support-plans.html','◇','Support Plans'],
      ['service-catalog.html','☷','Service Catalog'],['contacts.html','♧','Contacts'],['assets.html','▧','Assets'],['email-notifications.html','✉','Email Notifications']
    ];
    const customerLinks=[
      ['user-dashboard.html','▦','Dashboard'],['my-tickets.html','▤','My Tickets'],
      ['user-create-ticket.html','＋','Create Ticket'],['user-service-catalog.html','☷','Service Catalog'],['user-assets.html','▧','My Assets'],['email-notifications.html','✉','Email Notifications']
    ];
    const links=role==='customer'?customerLinks:agentLinks;
    nav.replaceChildren();
    links.forEach(([href,icon,label])=>{
      const a=document.createElement('a');a.href=href;
      const target=href.toLowerCase();
      const aliases={
        'tickets.html':['add-ticket.html','ticket-detail.html'],
        'customers.html':['add-customer.html','customer-detail.html'],
        'service-catalog.html':['add-service.html','add-request-type.html'],
        'user-create-ticket.html':['user-create-ticket.html'],
        'my-tickets.html':['user-ticket-detail.html'],
        'user-dashboard.html':['dashboard.html'],
        'agent-dashboard.html':['dashboard.html']
      };
      if(target===file || (aliases[target]||[]).includes(file) || (file==='dashboard.html' && target===homeByRole[role]))a.className='active';
      const i=document.createElement('span');i.className='nav-icon';i.textContent=icon;
      const name=document.createElement('span');name.textContent=label;
      a.append(i,name);nav.appendChild(a);
    });
  }
  function ensureSidebarProfile() {
    const sidebar=document.querySelector('.sidebar');if(!sidebar)return;
    let profile=sidebar.querySelector('.sidebar-bottom');
    if(!profile){profile=document.createElement('div');profile.className='sidebar-bottom';sidebar.appendChild(profile);}
    if(!profile.querySelector('[data-logout]')){
      const identity=document.createElement('div');
      const name=document.createElement('strong');name.dataset.customerName='';name.textContent='Signed-in user';
      const email=document.createElement('small');email.dataset.customerEmail='';email.textContent='';
      const logout=document.createElement('a');logout.href='login.html';logout.dataset.logout='';logout.className='logout-link';logout.textContent='Sign out ↗';
      identity.append(name,email,logout);
      if(!profile.querySelector('.avatar')){const avatar=document.createElement('div');avatar.className='avatar';avatar.dataset.customerAvatar='';avatar.textContent='GP';profile.appendChild(avatar);}
      profile.appendChild(identity);
    }
  }

  async function loadLookups() {
    try { lookupData=await api('/api/lookups'); }
    catch (_) { lookupData={}; }
    const teamList=document.getElementById('support-team-options');
    if(teamList){teamList.replaceChildren();(lookupData.teams||[]).forEach(team=>{const opt=document.createElement('option');opt.value=team.team_name;teamList.appendChild(opt);});}
  }
  function optionRows(select, rows, valueKey, labelFn, placeholder) {
    const old=select.value;
    const blank=document.createElement('option'); blank.value=''; blank.textContent=placeholder || 'Select an option';
    select.replaceChildren(blank);
    (rows||[]).forEach(row=>{
      const o=document.createElement('option'); o.value=String(row[valueKey] ?? ''); o.textContent=labelFn(row); select.appendChild(o);
    });
    if(old && [...select.options].some(o=>o.value===old)) select.value=old;
  }
  function configureSelects() {
    const cfg=activeFormConfig || formConfig[file];
    if(!cfg) return;
    const mainForm=getMainForm(); if(!mainForm) return;
    mainForm.querySelectorAll('.field').forEach(field=>{
      const label=labelKey(field.querySelector('label')?.textContent || '');
      const select=field.querySelector('select'); if(!select) return;
      if(label==='customer' || label==='ticket') optionRows(select,lookupData.customers,'customer_id',r=>r.customer_name,'Select customer');
      else if(label==='project' || label==='customer/project') optionRows(select,lookupData.projects,'project_id',r=>r.project_name,'Select project');
      else if(label==='contract / plan') optionRows(select,lookupData.contracts,'contract_id',r=>`${r.contract_code || 'CON-'+r.contract_id} · ${r.contract_name}`,'Select contract');
      else if(label==='support plan') optionRows(select,lookupData.plans,'plan_id',r=>r.plan_name,'Select support plan');
      else if(label==='asset' || label==='related asset (optional)') optionRows(select,lookupData.assets,'asset_id',r=>`${r.asset_tag} · ${r.asset_name}`, label.startsWith('related')?'None':'No asset linked');
      else if(label==='mapped team') optionRows(select,lookupData.teams,'team_name',r=>r.team_name,'Select team');
      else if(label==='service catalog') optionRows(select,lookupData.services,'code_id',r=>r.name,'Select service');
      else if(label==='contact') optionRows(select,lookupData.contacts,'contact_id',r=>`${r.fullname}${r.customer_name?' · '+r.customer_name:''}`,'Select contact');
      else if(label==='team members') optionRows(select,(lookupData.users||[]).filter(u=>u.role==='agent'),'fullname',r=>r.fullname,'Select team members');
      else if(label==='service' && file==='user-create-ticket.html') optionRows(select,lookupData.services,'code_id',r=>r.name,'Select service');
      else if(label==='request type' && file==='add-ticket.html') optionRows(select,lookupData.services,'name',r=>r.name,'Select request type');
      else if(label==='support team') optionRows(select,lookupData.teams,'team_id',r=>r.team_name,'Select support team');
      else if(label==='assigned' || label==='assigned to') {
        const agents=(lookupData.users||[]).filter(u=>u.role==='agent' || u.role==='admin');
        optionRows(select,agents,'fullname',r=>r.fullname,'Unassigned');
      }
    });
  }
  function getMainForm() {
    return [...document.querySelectorAll('form')].find(f=>!f.classList.contains('compact-search') && !f.classList.contains('filter-grid') && !f.querySelector('input[type="search"]')) || null;
  }
  function labelForField(field) { return labelKey(field.querySelector('label')?.textContent || ''); }
  function fieldRawValue(field, page, label) {
    if (page==='add-support-plan.html' && label==='working days') {
      return [...field.querySelectorAll('input[type="checkbox"]:checked')].map(ch=>ch.parentElement.querySelector('span')?.textContent.trim()).filter(Boolean).join(',');
    }
    const select=field.querySelector('select');
    if (select) {
      if (select.multiple) return [...select.selectedOptions].map(o=>o.value || o.textContent.trim()).filter(Boolean);
      return select.value;
    }
    const checkboxes=[...field.querySelectorAll('input[type="checkbox"]')];
    if (checkboxes.length) return checkboxes.length===1 ? checkboxes[0].checked : checkboxes.filter(x=>x.checked).map(x=>x.value);
    const input=field.querySelector('input,textarea'); return input ? input.value : null;
  }
  function payloadForForm(page, form, cfg) {
    const payload={};
    form.querySelectorAll('.field').forEach(field=>{
      const label=labelForField(field), key=cfg.map[label];
      if(!key) return;
      let value=fieldRawValue(field,page,label);
      if(key==='customer_visible' || key==='auto_assign') {
        if(typeof value==='string') value=['yes','true','enabled','1','on'].includes(value.toLowerCase());
      }
      if(key==='member' && Array.isArray(value)) value=value.join(', ');
      if(page==='add-user.html' && key==='team_id'){
        const team=(lookupData.teams||[]).find(t=>String(t.team_id)===String(value)||String(t.team_name).toLowerCase()===String(value||'').trim().toLowerCase());
        if(value && !team) throw new Error('Choose a Support Team from the available team names.');
        value=team?team.team_id:null;
      }
      if(key==='service_codes') {
        payload.service_codes=Array.isArray(value)?value:(value?[value]:[]);
        if(payload.service_codes.length) payload.code_id=payload.service_codes[0];
        return;
      }
      if(key==='service_code' && value) payload.service_code=value;
      else if((key==='type' && page==='add-ticket.html') && value) {
        // The admin form's request type is the service name, matching the ticket ERD field.
        payload.type=value;
      } else payload[key]=value;
    });
    if(page==='add-customer.html' && customerEntityMode) {
      form.querySelectorAll('[data-customer-edit-field]').forEach(input=>{payload[input.dataset.customerEditField]=input.value;});
      delete payload.role; delete payload.password; delete payload.team_id; delete payload.fullname;
    }
    if(page==='add-ticket.html' && payload.contract_id) {
      const contract=(lookupData.contracts||[]).find(c=>String(c.contract_id)===String(payload.contract_id));
      if(contract && contract.plan_id) payload.plan_id=contract.plan_id;
      if(!payload.subject) throw new Error('Enter a ticket subject.');
      if(!payload.customer_id) throw new Error('Select a customer.');
    }
    if(page==='user-create-ticket.html') {
      payload.status='Open'; payload.priority='Medium';
      if(!payload.subject) throw new Error('Enter a subject for your request.');
      if(!payload.service_code) throw new Error('Select a service.');
      if(!payload.type || ['select request type','incident type'].includes(String(payload.type).toLowerCase())) throw new Error('Select a request type.');
    }
    if(page==='add-team.html') {
      if(!payload.member) payload.member='';
    }
    return payload;
  }
  function setField(field, value, page, label) {
    if(value===undefined || value===null) return;
    if(page==='add-support-plan.html' && label==='working days') {
      const days=String(value).split(',').map(x=>x.trim().toLowerCase());
      field.querySelectorAll('input[type="checkbox"]').forEach(ch=>{const text=ch.parentElement.querySelector('span')?.textContent.trim().toLowerCase();ch.checked=days.includes(text);}); return;
    }
    const select=field.querySelector('select');
    if(select) {
      if(select.multiple) {
        const vals=(Array.isArray(value)?value:String(value).split(',')).map(x=>String(x).trim());
        [...select.options].forEach(o=>o.selected=vals.includes(o.value)||vals.includes(o.textContent.trim()));
      } else {
        let match=[...select.options].find(o=>String(o.value)===String(value)) || [...select.options].find(o=>o.textContent.trim().toLowerCase()===String(value).toLowerCase());
        if(!match && String(value).trim()) { match=document.createElement('option'); match.value=String(value); match.textContent=String(value); select.appendChild(match); }
        if(match) select.value=match.value;
      }
      return;
    }
    const check=field.querySelector('input[type="checkbox"]');
    if(check){check.checked=Boolean(value);return;}
    const input=field.querySelector('input,textarea'); if(input) input.value=value;
  }
  async function fillEditForm(cfg) {
    if(!idParam || !cfg || cfg.alwaysUpdate) return;
    const form=getMainForm(); if(!form) return;
    const row=await api(`/api/${cfg.resource}/${encodeURIComponent(idParam)}`);
    form.querySelectorAll('.field').forEach(field=>{
      const label=labelForField(field), key=cfg.map[label];
      if(customerEditMode) {
        const custom=field.querySelector('[data-customer-edit-field]');
        if(custom && row[custom.dataset.customerEditField]!==undefined) custom.value=row[custom.dataset.customerEditField]||'';
      }
      if(!key) return;
      let value=row[key];
      if(file==='add-contract.html' && label==='support plan') value=row.plan_id;
      if(file==='add-user.html' && label==='support team') value=row.team_name || '';
      if(file==='add-team.html' && label==='service catalog') value=row.service_code_ids || (row.code_id?[row.code_id]:[]);
      if(file==='add-team.html' && label==='team members') value=row.member || '';
      setField(field,value,file,label);
    });
    if(file==='add-user.html') {
      const passwordField=[...form.querySelectorAll('.field')].find(field=>labelForField(field)==='password');
      const passwordInput=passwordField?.querySelector('input');
      if(passwordInput){passwordInput.required=false;passwordInput.placeholder='Leave blank to keep current password';}
    }
    const submit=form.querySelector('button[type="submit"]'); if(submit) submit.textContent=submit.textContent.replace(/Create|Save|Submit/i,'Update');
    const title=document.querySelector('h1'); if(title && !title.textContent.toLowerCase().includes('edit')) title.textContent=(file==='add-ticket.html'?'Edit ticket':`Edit ${title.textContent.trim()}`);
  }
  function actionLink(url,label,cls='btn btn-sm') { return `<a class="${cls}" href="${url}">${esc(label)}</a>`; }
  function rowActions(resource, id, editHref, viewHref=null, viewLabel='View') {
    if(currentUser.role==='admin') return `${viewHref?actionLink(viewHref,viewLabel):''} ${editHref?actionLink(editHref,'Edit'):''} <button type="button" class="btn btn-sm" data-delete-resource="${esc(resource)}" data-delete-id="${esc(id)}" style="color:#b12c44">Delete</button>`;
    if(viewHref) return actionLink(viewHref,viewLabel);
    return '—';
  }
  function ticketHref(row) { return `${currentUser.role==='customer'?'user-ticket-detail.html':'ticket-detail.html'}?id=${encodeURIComponent(row.ticket_id)}`; }
  function cellFor(resource,row,header,page) {
    const h=header.toLowerCase().replace(/\s+/g,' ').trim();
    if(resource==='tickets') {
      if(h.includes('ticket')) return `<a class="ticket-id" href="${ticketHref(row)}">${esc(row.ticket_code || ('TKT-'+row.ticket_id))}</a>`;
      if(h.includes('customer') && h.includes('project')) return `${esc(row.customer_name)}${row.project_name&&row.project_name!=='—'?`<span class="sub-cell">${esc(row.project_name)}</span>`:''}`;
      if(h==='contract' || h.includes('contract / plan') || h.includes('contract /')) return `${esc(row.contract_code || row.contract_name || '—')}${row.plan_name&&row.plan_name!=='—'?`<span class="sub-cell">${esc(row.plan_name)}</span>`:''}`;
      if(h.includes('request type')) return esc(row.type);
      if(h.includes('subject')) return `<a class="ticket-id" href="${ticketHref(row)}">${esc(row.subject)}</a>`;
      if(h.includes('status')) return badge(row.status);
      if(h.includes('priority')) return badge(row.priority);
      if(h.includes('asset')) return esc(row.asset_tag || '—');
      if(h.includes('assigned')) return esc(row.assigned || 'Unassigned');
      if(h.includes('created') || h.includes('last updated') || h.includes('updated')) return fmtDate(h.includes('updated') && !h.includes('created') ? row.updated_at : row.date);
      if(h==='action' || h==='actions') return currentUser.role==='admin' ? `${actionLink(ticketHref(row),'View')} ${actionLink(`add-ticket.html?id=${encodeURIComponent(row.ticket_id)}`,'Edit')} <button type="button" class="btn btn-sm" data-delete-resource="tickets" data-delete-id="${esc(row.ticket_id)}" style="color:#b12c44">Delete</button>` : rowActions('tickets',row.ticket_id,null,ticketHref(row),'View');
    }
    if(resource==='projects') {
      if(h.includes('customer')) return esc(row.customer_name);
      if(h.includes('project code')) return esc(row.project_code || row.project_id);
      if(h.includes('project name')) return currentUser.role==='admin' ? actionLink(`add-project.html?id=${row.project_id}`,row.project_name,'ticket-id') : esc(row.project_name);
      if(h.includes('manager')) return esc(row.project_manager || '—');
      if(h.includes('status')) return badge(row.status);
      if(h.includes('start date')) return fmtDate(row.start_date);
      if(h.includes('end date')) return fmtDate(row.end_date);
      if(h.includes('action')) return rowActions('projects',row.project_id,`add-project.html?id=${row.project_id}`,null);
    }
    if(resource==='customers') {
      if(h.includes('company')) return actionLink(`customer-detail.html?id=${row.customer_id}`,row.customer_name,'ticket-id');
      if(h.includes('primary contact')) return esc(row.contact_name || '—');
      if(h==='projects') return esc(row.projects_count ?? 0);
      if(h==='contracts') return esc(row.contracts_count ?? 0);
      if(h.includes('tickets')) return esc(row.tickets_count ?? 0);
      if(h.includes('status')) return badge('Active');
      if(h.includes('action')) return rowActions('customers',row.customer_id,`add-customer.html?id=${row.customer_id}&edit_customer=1`,`customer-detail.html?id=${row.customer_id}`,'View');
    }
    if(resource==='contacts') {
      if(h.includes('customer')) return esc(row.customer_name);
      if(h.includes('contact no')) return esc(row.contact_code || ('CON-'+row.contact_id));
      if(h.includes('contact name')) return esc(row.fullname);
      if(h.includes('department')) return esc(row.department || '—');
      if(h.includes('job title')) return esc(row.job_title || '—');
      if(h==='email') return esc(row.email || '—');
      if(h==='phone') return esc(row.phone || '—');
      if(h==='type') return badge(row.type || 'General');
      if(h.includes('action')) return rowActions('contacts',row.contact_id,`add-contact.html?id=${row.contact_id}`,null);
    }
    if(resource==='contracts') {
      if(h.includes('customer')) return esc(row.customer_name);
      if(h.includes('project')) return esc(row.project_name);
      if(h.includes('contract no')) return esc(row.contract_code || ('CON-'+row.contract_id));
      if(h.includes('contract name')) return esc(row.contract_name);
      if(h.includes('support plan')) return esc(row.plan_name || '—');
      if(h.includes('start date')) return fmtDate(row.start_date);
      if(h.includes('end date')) return fmtDate(row.end_date);
      if(h.includes('action')) return rowActions('contracts',row.contract_id,`add-contract.html?id=${row.contract_id}`,null);
    }
    if(resource==='plans') {
      if(h.includes('action')) return rowActions('plans',row.plan_id,`add-support-plan.html?id=${row.plan_id}`,null);
      const mappings=[['plan code',row.plan_code || ('PLAN-'+row.plan_id)],['plan name',row.plan_name],['response sla',row.response_sla],['rsponse sla',row.response_sla],['resolution sla',row.resolution_sla],['reslution sla',row.resolution_sla],['response warning',row.response_warning],['reslution warning',row.resolution_warning],['response critical',row.response_critical],['reslution critical',row.resolution_critical],['calendar mode',row.sla_mode],['calender mode',row.sla_mode],['time zone',row.time_zone],['business start',row.business_start_hour],['business end',row.business_end_hour],['working days',row.working_days],['escalation level',row.escalation_level],['remote support',row.remote_support],['on-site support',row.onsite_support]];
      const found=mappings.find(([key])=>h.includes(key)); if(found) return esc(found[1] ?? '—');
    }
    if(resource==='services') {
      if(h==='code') return esc(row.code_id);
      if(h==='name') return esc(row.name);
      if(h.includes('category')) return esc(row.category || '—');
      if(h.includes('sort order')) return esc(row.request_order);
      if(h.includes('customer visible')) return badge(row.customer_visible?'Yes':'No');
      if(h.includes('asset requirement')) return esc(row.asset_requirement || '—');
      if(h.includes('mapped team')) return esc(row.mapped_team || '—');
      if(h.includes('auto assign')) return badge(row.auto_assign?'Enabled':'Disabled');
      if(h.includes('assignment method') || h.includes('assigenment method') || h.includes('assignement method')) return esc(row.assignment_method || '—');
      if(h.includes('action')) return rowActions('services',row.code_id,`add-service.html?id=${encodeURIComponent(row.code_id)}`,null);
    }
    if(resource==='teams') {
      if(h.includes('team code')) return esc(row.team_code || ('TEAM-'+row.team_id));
      if(h.includes('team name')) return esc(row.team_name);
      if(h.includes('team members')) return esc(row.member || '—');
      if(h.includes('service catalog')) return esc(row.service_names || row.service_name || '—');
      if(h.includes('action')) return rowActions('teams',row.team_id,`add-team.html?id=${row.team_id}`,null);
    }
    if(resource==='assets') {
      if(h==='customers' || h==='customer') return esc(row.customer_name || '—');
      if(h==='project') return esc(row.project_name || '—');
      if(h.includes('asset tag')) return actionLink(`asset-detail.html?id=${row.asset_id}`,row.asset_tag,'ticket-id');
      if(h.includes('asset name')) return esc(row.asset_name);
      if(h==='type') return esc(row.type || '—');
      if(h.includes('status')) return badge(row.status);
      if(h==='vendor') return esc(row.vendor || '—');
      if(h==='model') return esc(row.model || '—');
      if(h.includes('serial')) return esc(row.serial_no || '—');
      if(h.includes('ip address')) return esc(row.ip_address || '—');
      if(h.includes('assigned to')) return esc(row.assigned_to || currentUser.fullname);
      if(h.includes('action')) return rowActions('assets',row.asset_id,`add-asset.html?id=${row.asset_id}`,`asset-detail.html?id=${row.asset_id}`,'View');
    }
    if(resource==='users') {
      if(h.includes('fullname') || h==='full name') return esc(row.fullname);
      if(h==='email') return esc(row.email);
      if(h==='password') return '••••••••';
      if(h==='role') return badge(row.role);
      if(h.includes('support team')) return esc(row.team_name || '—');
      if(h.includes('action')) return `${rowActions('users',row.user_id,`add-user.html?id=${row.user_id}`,null)} ${row.role==='customer'?`<button type="button" class="btn btn-sm" data-reset-customer-password="${esc(row.user_id)}">Reset password</button>`:''}`;
    }
    if(resource==='audit-logs') {
      if(h.includes('timestamp') || h==='date') return `<span class="audit-date">${esc(row.created_at ? new Date(row.created_at).toLocaleString() : '—')}</span>`;
      if(h==='customer' || h==='user' || h==='user name') return `<div class="audit-user"><strong>${esc(row.user_name || 'System')}</strong><span class="sub-cell">${esc(row.actor_role || 'system')}</span></div>`;
      if(h==='action') return `<span class="audit-action-pill">${esc(row.action || '—')}</span>`;
      if(h==='module' || h==='entity') return `<div class="audit-entity">${esc(row.module || '—')}<span class="sub-cell">${esc(row.entity_label || row.entity_id || '')}</span></div>`;
      if(h==='record' || h==='summary' || h.includes('summary')) return `<div class="audit-summary">${esc(row.details || '—')}</div>`;
      if(h==='ip' || h.includes('ip address')) return esc(row.ip_address || '—');
      if(h==='result') return badge(row.action==='LOGIN_FAILED'||row.action==='EMAIL_FAILED'||row.action==='PASSWORD_RESET_EMAIL_FAILED'?'Failed':row.action==='EMAIL_SKIPPED'?'Skipped':'Success');
      if(h==='details' || h==='details / changes') return `<button type="button" class="btn btn-sm" data-audit-view="${esc(row.audit_id)}">${row.changes && Object.keys(row.changes).length?'View Changes':'View Details'}</button>`;
    }
    return '—';
  }
  function renderTable(resource, rows, table, page=file) {
    if(!table) return;
    const tbody=table.querySelector('tbody'); if(!tbody) return;
    const headers=[...table.querySelectorAll('thead th')].map(th=>th.textContent.replace(/\s+/g,' ').trim());
    if(!headers.length) return;
    tbody.replaceChildren();
    if(!rows.length){const tr=document.createElement('tr');const td=document.createElement('td');td.colSpan=headers.length;td.className='empty-data';td.textContent='No records found in the database yet.';td.style.padding='22px';td.style.textAlign='center';td.style.color='#7b8497';tr.appendChild(td);tbody.appendChild(tr);return;}
    rows.forEach(row=>{
      const tr=document.createElement('tr');
      headers.forEach(header=>{
        const td=document.createElement('td');
        const normalized=header.toLowerCase().replace(/\s+/g,' ').trim();
        if(resource==='plans' && normalized.includes('action') && currentUser?.role==='admin'){
          const edit=document.createElement('a');edit.className='btn btn-sm';edit.href=`add-support-plan.html?id=${encodeURIComponent(row.plan_id)}`;edit.textContent='Edit';
          const del=document.createElement('button');del.type='button';del.className='btn btn-sm';del.dataset.deleteResource='plans';del.dataset.deleteId=String(row.plan_id);del.style.color='#b12c44';del.style.marginLeft='6px';del.textContent='Delete';
          td.append(edit,del);
        } else td.innerHTML=cellFor(resource,row,header,page);
        tr.appendChild(td);
      });
      tbody.appendChild(tr);
    });
    const foot=table.closest('.card')?.querySelector('.table-foot');
    if(foot){const span=foot.querySelector('span');if(span)span.textContent=`Showing ${rows.length} record${rows.length===1?'':'s'}`;const pagination=foot.querySelector('.pagination');if(pagination)pagination.innerHTML='';}
  }
  function chooseTable(resource) {
    const tables=[...document.querySelectorAll('table')];
    return tables.find(t=>{const text=t.querySelector('thead')?.textContent.toLowerCase()||'';return resource==='tickets'?text.includes('ticket'):resource==='assets'?text.includes('asset'):resource==='services'?text.includes('code')||text.includes('service'):resource==='audit-logs'?(text.includes('timestamp')||(text.includes('date')&&text.includes('user'))):resource==='users'?text.includes('fullname'):resource==='projects'?text.includes('project code'):resource==='customers'?text.includes('company'):resource==='contacts'?text.includes('contact no'):resource==='contracts'?text.includes('contract no'):resource==='plans'?text.includes('plan code'):resource==='teams'?text.includes('team code'):false;}) || tables[0];
  }
  async function loadList(resource=pageResource[file]) {
    if(!resource) return;
    try {
      const rows=await api(`/api/${resource}`); loadedRows[resource]=rows;
      const table=chooseTable(resource);
      if(table) renderTable(resource,rows,table,file);
      if(resource==='services' && file==='user-service-catalog.html') renderCustomerServiceCards(rows);
      if(resource==='assets' && file==='user-assets.html') renderUserAssets(rows);
      return rows;
    } catch(e) { if(e.status===403) toast(e.message,'error'); else if(e.status!==404) toast(e.message,'error'); }
  }
  function renderCustomerServiceCards(rows) {
    const grid=document.querySelector('.three-col'); if(!grid) return;
    grid.replaceChildren();
    const icons=['⌘','◇','⇄','▧','♧','✉'];
    rows.forEach((r,i)=>{
      const card=document.createElement('section');card.className='card';
      card.innerHTML=`<div class="card-body"><div class="stat-icon" style="margin-bottom:12px">${icons[i%icons.length]}</div><h2 style="font-size:14px;margin:0 0 6px">${esc(r.name)}</h2><p class="subtitle" style="min-height:35px">${esc(r.description||r.category||'Request support for this service.')}</p><div style="margin-top:16px"><a class="btn btn-primary btn-sm" href="user-create-ticket.html?service=${encodeURIComponent(r.name)}">Request service →</a></div></div>`;
      grid.appendChild(card);
    });
    if(!rows.length) grid.innerHTML='<p class="notice">There are no customer-visible services configured yet.</p>';
  }
  function renderUserAssets(rows) {
    const table=chooseTable('assets'); if(!table) return;
    const tbody=table.querySelector('tbody'); if(!tbody) return;
    tbody.replaceChildren();
    rows.forEach(r=>{const tr=document.createElement('tr');tr.innerHTML=`<td><span class="ticket-id">${esc(r.asset_tag)}</span></td><td>${esc(r.asset_name)}</td><td>${esc(r.type||'—')}</td><td>${esc(currentUser.fullname)}</td><td>${badge(r.status)}</td>`;tbody.appendChild(tr);});
    if(!rows.length) tbody.innerHTML='<tr><td colspan="5" style="padding:22px;text-align:center;color:#7b8497">No assets are linked to your account.</td></tr>';
  }
  function updateDashboard(stats) {
    if(!stats) return;
    document.querySelectorAll('.stat').forEach(card=>{
      const label=(card.querySelector('.stat-top')?.textContent||'').toLowerCase();
      const strong=card.querySelector('strong'); if(!strong) return;
      if(label.includes('total ticket') || label==='my tickets') strong.textContent=stats.tickets_total;
      else if(label.includes('open ticket')) strong.textContent=stats.open_tickets;
      else if(label.includes('in progress')) strong.textContent=stats.in_progress;
      else if(label.includes('waiting')) strong.textContent=stats.waiting;
      else if(label.includes('resolved')) strong.textContent=stats.resolved;
      else if(label==='projects') strong.textContent=stats.projects;
      else if(label.includes('asset')) strong.textContent=stats.assets;
      else if(label.includes('contract')) strong.textContent=stats.contracts;
      else if(label==='users') strong.textContent=(loadedRows.users||[]).length || strong.textContent;
    });
  }
  function installSearch() {
    if(!document.body.dataset.deleteHandlerInstalled){
      document.body.dataset.deleteHandlerInstalled='1';
      document.addEventListener('click',async ev=>{
        const button=ev.target.closest('[data-delete-resource]');if(!button)return;
        const resource=button.dataset.deleteResource,id=button.dataset.deleteId;
        if(!window.confirm(`Delete this ${resource.replace(/s$/,'')} record? This cannot be undone.`))return;
        button.disabled=true;
        try{await api(`/api/${encodeURIComponent(resource)}/${encodeURIComponent(id)}`,{method:'DELETE'});toast('Record deleted.');await loadList(resource);}
        catch(e){toast(e.message,'error');button.disabled=false;}
      });
      document.addEventListener('click',async ev=>{
        const button=ev.target.closest('[data-reset-customer-password]');if(!button)return;
        const id=button.dataset.resetCustomerPassword;
        const confirmed=await confirmDialog('Reset this customer password and email a temporary password to their registered email address?','Reset customer password');
        if(!confirmed)return;
        button.disabled=true;
        try{const result=await api(`/api/users/${encodeURIComponent(id)}/reset-password`,{method:'POST'});toast(result.message);}
        catch(e){toast(e.message,'error');}
        finally{button.disabled=false;}
      });
    }
    document.querySelectorAll('form.compact-search').forEach(form=>form.addEventListener('submit',ev=>{
      const input=form.querySelector('input[type="search"]');if(!input)return;
      const q=input.value.trim().toLowerCase();
      const resource=pageResource[file]; const rows=loadedRows[resource]||[];
      if(rows.length){ev.preventDefault();const filtered=rows.filter(r=>JSON.stringify(r).toLowerCase().includes(q));const table=chooseTable(resource);if(table)renderTable(resource,filtered,table,file);}
    }));
    const filterForm=[...document.querySelectorAll('form')].find(f=>f.classList.contains('filter-grid') || f.querySelector('.filter-grid'));
    if(filterForm) filterForm.addEventListener('submit',ev=>{
      const resource=pageResource[file], rows=loadedRows[resource];if(!rows)return;
      ev.preventDefault();const values=[...filterForm.querySelectorAll('input,select')].map(x=>x.value.trim().toLowerCase()).filter(Boolean);
      const filtered=rows.filter(r=>values.filter(v=>!/^all\s/i.test(v)).every(v=>JSON.stringify(r).toLowerCase().includes(v)));
      const table=chooseTable(resource);if(table)renderTable(resource,filtered,table,file);
    });
    document.querySelectorAll('.filters').forEach(panel=>{
      if(panel.querySelector('form.filter-grid')) return;
      const searchButton=panel.querySelector('.filter-actions button');
      const resource=pageResource[file];
      if(searchButton && resource) searchButton.addEventListener('click',ev=>{
        ev.preventDefault();const rows=loadedRows[resource]||[];
        let filtered=rows;
        if(file==='audit-log.html'){
          const fields=[...panel.querySelectorAll('.filter-grid .field')];
          const valueAt=i=>fields[i]?.querySelector('input,select')?.value?.trim()||'';
          const query=valueAt(0).toLowerCase(), module=valueAt(1).toLowerCase(), from=valueAt(2), to=valueAt(3);
          filtered=rows.filter(r=>{
            const searchable=`${r.user_name||''} ${r.action||''} ${r.module||''} ${r.details||''}`.toLowerCase();
            const day=String(r.created_at||r.timestamp||'').slice(0,10);
            return (!query||searchable.includes(query))&&(!module||/^all\s/i.test(module)||String(r.module||'').toLowerCase()===module)&&(!from||day>=from)&&(!to||day<=to);
          });
        } else {
          const values=[...panel.querySelectorAll('.filter-grid input,.filter-grid select')].map(x=>x.value.trim().toLowerCase()).filter(Boolean).filter(v=>!/^all\s/i.test(v));
          filtered=rows.filter(r=>values.every(v=>JSON.stringify(r).toLowerCase().includes(v)));
        }
        const table=chooseTable(resource);if(table)renderTable(resource,filtered,table,file);
      });
      const reset=[...panel.querySelectorAll('a')].find(a=>/^reset$/i.test(a.textContent.trim()));
      if(reset && resource) reset.addEventListener('click',ev=>{ev.preventDefault();panel.querySelectorAll('input,select').forEach(el=>{if(el.tagName==='SELECT')el.selectedIndex=0;else el.value='';});const table=chooseTable(resource);if(table)renderTable(resource,loadedRows[resource]||[],table,file);});
    });
    document.querySelectorAll('a[href="#"]').forEach(a=>{
      if(/export csv|^export$|export log/i.test(a.textContent.trim())) a.addEventListener('click',ev=>{ev.preventDefault();const resource=pageResource[file],rows=loadedRows[resource]||[];exportCsv(resource,rows);});
    });
    if(file==='audit-log.html') document.querySelectorAll('a').forEach(a=>{if(/export log/i.test(a.textContent)&&a.getAttribute('href')!=='#')a.addEventListener('click',ev=>{ev.preventDefault();exportCsv('audit-logs',loadedRows['audit-logs']||[]);});});
  }
  function exportCsv(resource, rows) {
    if(!rows.length){toast('There are no records to export.','error');return;}
    const keys=Object.keys(rows[0]).filter(k=>!['password_hash','password'].includes(k));
    const quote=v=>'"'+String(v??'').replace(/"/g,'""')+'"';
    const csv=[keys.map(quote).join(','),...rows.map(r=>keys.map(k=>quote(r[k])).join(','))].join('\r\n');
    const url=URL.createObjectURL(new Blob([csv],{type:'text/csv;charset=utf-8;'}));
    const a=document.createElement('a');a.href=url;a.download=`golden-pride-${resource}.csv`;a.click();URL.revokeObjectURL(url);
  }
  async function handleStandardForm(cfg) {
    const form=getMainForm(); if(!form) return;
    const id=idParam && !cfg.alwaysUpdate ? idParam : (cfg.alwaysUpdate ? idParam : null);
    form.addEventListener('submit', async ev=>{
      ev.preventDefault();
      try {
        const payload=payloadForForm(file,form,cfg);
        if(file==='add-user.html') {
          const role=String(payload.role||'customer').toLowerCase();payload.role=role==='administrator'?'admin':role;
          if(!payload.password && !id) throw new Error('Enter a temporary password for this account.');
          if(!payload.team_id) throw new Error('Select a valid Support Team from the available team names.');
        }
        if(file==='add-project.html' && !payload.customer_id) throw new Error('Select a customer for this project.');
        if(file==='add-customer.html' && !payload.customer_name) throw new Error('Enter the company name.');
        if(file==='add-ticket.html') {
          if(!payload.customer_id) throw new Error('Select a customer.');
          if(!payload.subject) throw new Error('Enter a ticket subject.');
          const service=(lookupData.services||[]).find(x=>String(x.name)===String(payload.type)||String(x.code_id)===String(payload.type));
          if(service) payload.service_code=service.code_id;
          const contract=(lookupData.contracts||[]).find(x=>String(x.contract_id)===String(payload.contract_id));
          if(contract && contract.plan_id) payload.plan_id=contract.plan_id;
        }
        if(file==='add-contact.html' && !payload.customer_id) throw new Error('Select the contact’s customer.');
        if(file==='add-contract.html' && !payload.customer_id) throw new Error('Select a customer for this contract.');
        if(file==='add-asset.html' && !payload.asset_tag) throw new Error('Enter an asset tag.');
        if(file==='add-team.html' && payload.service_codes?.length) payload.code_id=payload.service_codes[0];
        const shouldUpdate=Boolean(id);
        const result=await api(shouldUpdate?`/api/${cfg.resource}/${encodeURIComponent(id)}`:`/api/${cfg.resource}`,{method:shouldUpdate?'PUT':'POST',body:JSON.stringify(payload)});
        toast(shouldUpdate?'Record updated successfully.':'Record created successfully.');
        if(file==='add-user.html') location.href='users.html';
        else if(file==='add-ticket.html' && shouldUpdate) location.href=`ticket-detail.html?id=${encodeURIComponent(id)}`;
        else location.href=cfg.redirect;
      } catch(e){toast(e.message || 'Unable to save the record.','error');}
    });
  }
  async function handleTicketDetail() {
    const form=getMainForm();
    if(!idParam) {
      const notice=document.createElement('div');notice.className='notice warning';notice.textContent='Open a ticket using View from the ticket register so the ticket ID is included.';
      document.querySelector('.breadcrumb')?.after(notice);
      if(form) form.querySelectorAll('button[type="submit"]').forEach(b=>b.disabled=true);
      return;
    }
    try {
      const ticket=await api(`/api/tickets/${encodeURIComponent(idParam)}`);
      document.querySelectorAll('.breadcrumb').forEach(b=>{if(b.textContent.toLowerCase().includes('ticket')) b.innerHTML=`<a href="tickets.html">Tickets</a> / ${esc(ticket.ticket_code)}`;});
      const h1=document.querySelector('main h1');if(h1)h1.textContent=`Ticket ${ticket.ticket_code}`;
      const editLink=[...document.querySelectorAll('a')].find(a=>/edit ticket/i.test(a.textContent));
      if(editLink){editLink.href=`add-ticket.html?id=${encodeURIComponent(ticket.ticket_id)}`;if(currentUser.role==='customer')editLink.style.display='none';}
      const pills=document.querySelectorAll('.inline .badge, .inline .code');
      pills.forEach(el=>{if(/priority/i.test(el.textContent))el.textContent=`${ticket.priority||'Medium'} priority`;else if(/open|closed|resolved|progress|pending/i.test(el.textContent))el.textContent=ticket.status||'Open';else if(el.classList.contains('code'))el.textContent=ticket.ticket_code;});
      const headings=[...document.querySelectorAll('h2')];
      headings.forEach(h=>{if(/Database connection|Ticket information|Ticket details/i.test(h.textContent))h.textContent=ticket.subject||'Ticket details';});
      const headerCard=[...document.querySelectorAll('.card')].find(c=>c.querySelector('h2')?.textContent===(ticket.subject||''));
      if(headerCard){
        const meta=headerCard.querySelector('.card-head p');if(meta)meta.textContent=`Created ${fmtDate(ticket.date)}${ticket.updated_at?` · Last updated ${new Date(ticket.updated_at).toLocaleString()}`:''}`;
        const notice=headerCard.querySelector('.notice');if(notice)notice.textContent=ticket.description||'No description was provided for this ticket.';
        const fields=[...headerCard.querySelectorAll('.form-grid .field')];
        const values=[ticket.customer_name,ticket.project_name,ticket.contract_code||ticket.contract_name,ticket.type,ticket.assigned||'Unassigned',ticket.asset_tag];
        fields.forEach((field,i)=>{const strong=field.querySelector('strong');if(strong&&values[i]!==undefined)strong.textContent=values[i]||'—';});
      }
      const sla=[...document.querySelectorAll('.item')].find(item=>/Support plan/i.test(item.textContent));
      if(sla){const strong=sla.querySelector('strong');if(strong)strong.textContent=ticket.plan_name||'—';}
      if(form){form.querySelectorAll('.field').forEach(field=>{const label=labelForField(field);const key=cfgFieldForTicket(label);if(key)setField(field,ticket[key],file,label);});form.addEventListener('submit',async ev=>{ev.preventDefault();try{const payload=payloadForForm(file,form,formConfig[file]);await api(`/api/tickets/${ticket.ticket_id}`,{method:'PUT',body:JSON.stringify(payload)});toast('Ticket updated.');location.href=`ticket-detail.html?id=${ticket.ticket_id}`;}catch(e){toast(e.message,'error');}});}
    }catch(e){toast(e.message,'error');}
  }
  function cfgFieldForTicket(label){return formConfig['ticket-detail.html'].map[label];}
  async function handleCustomerCreateTicket() {
    const serviceName=params.get('service');
    const form=getMainForm();if(!form)return;
    if(serviceName){const serviceSelect=[...form.querySelectorAll('.field')].find(f=>labelForField(f)==='service')?.querySelector('select');if(serviceSelect){const option=[...serviceSelect.options].find(o=>o.value===serviceName||o.textContent===serviceName);if(option)serviceSelect.value=option.value;}}
  }
  async function handleStaffTicketConversation(){
    const id=idParam;if(!id)return;
    try{
      const ticket=await api(`/api/tickets/${encodeURIComponent(id)}`);
      const activity=[...document.querySelectorAll('section.card')].find(s=>/activity|comments/i.test(s.textContent));
      if(!activity)return;
      const body=activity.querySelector('.card-body');if(!body)return;
      body.innerHTML='<div data-replies></div><form data-staff-reply-form class="staff-reply-form" style="margin-top:16px"><div class="field"><label data-reply-label>Public reply</label><textarea class="textarea" placeholder="Write a reply to the customer" required></textarea></div><div class="reply-mode-wrap"><span class="reply-mode-caption">Message type</span><div class="reply-mode-switch" role="group" aria-label="Choose message type"><button class="reply-mode-option is-selected" type="button" data-reply-mode="public" aria-pressed="true">Public reply</button><button class="reply-mode-option" type="button" data-reply-mode="internal" aria-pressed="false">🔒 Internal note</button></div><p class="reply-mode-hint" data-internal-note-hint>Visible to the customer and staff.</p></div><div class="form-actions"><button class="btn btn-primary" type="submit" data-reply-submit>Send reply</button></div></form>';
      let replies=await api(`/api/tickets/${ticket.ticket_id}/replies`);renderReplies(replies,ticket);
      const form=body.querySelector('[data-staff-reply-form]');const textarea=form.querySelector('textarea');const modeButtons=[...form.querySelectorAll('[data-reply-mode]')];let internalMode=false;
      const updateNoteMode=()=>{form.classList.toggle('is-internal-note',internalMode);modeButtons.forEach(button=>{const selected=button.dataset.replyMode===(internalMode?'internal':'public');button.classList.toggle('is-selected',selected);button.setAttribute('aria-pressed',String(selected));});form.querySelector('[data-reply-label]').textContent=internalMode?'Internal note':'Public reply';textarea.placeholder=internalMode?'Write a private note for Admin and Agent only':'Write a reply to the customer';form.querySelector('[data-internal-note-hint]').textContent=internalMode?'Staff only · Not visible to customers · No customer email':'Visible to the customer and staff';form.querySelector('[data-reply-submit]').textContent=internalMode?'Add internal note':'Send reply';};
      modeButtons.forEach(button=>button.addEventListener('click',()=>{internalMode=button.dataset.replyMode==='internal';updateNoteMode();}));
      form.addEventListener('submit',async ev=>{ev.preventDefault();const text=textarea.value.trim();if(!text)return;const internal=internalMode;try{await api(`/api/tickets/${ticket.ticket_id}/replies`,{method:'POST',body:JSON.stringify({body:text,is_internal:internal})});textarea.value='';internalMode=false;updateNoteMode();toast(internal?'Internal note saved for Admin and Agent only.':'Reply sent.');replies=await api(`/api/tickets/${ticket.ticket_id}/replies`);renderReplies(replies,ticket);}catch(e){toast(e.message,'error');}});
    }catch(e){toast(e.message,'error');}
  }

  async function handleTicketConversation() {
    const id=idParam;
    if(!id){const notice=document.createElement('div');notice.className='notice warning';notice.textContent='Please open this ticket from My Tickets so its ID is included.';document.querySelector('.breadcrumb')?.after(notice);return;}
    try {
      const ticket=await api(`/api/tickets/${encodeURIComponent(id)}`);
      const heading=document.querySelector('main h1');if(heading)heading.textContent=`${ticket.ticket_code} · ${ticket.subject}`;
      document.querySelectorAll('.breadcrumb').forEach(b=>{if(b.textContent.toLowerCase().includes('ticket'))b.innerHTML=`<a href="my-tickets.html">My tickets</a> / ${esc(ticket.ticket_code)}`;});
      let replies=await api(`/api/tickets/${ticket.ticket_id}/replies`);
      const form=getMainForm();if(form) form.addEventListener('submit',async ev=>{ev.preventDefault();const textarea=form.querySelector('textarea');const body=textarea?.value.trim();if(!body){toast('Write a reply before sending.','error');return;}try{await api(`/api/tickets/${ticket.ticket_id}/replies`,{method:'POST',body:JSON.stringify({body,is_internal:false})});textarea.value='';toast('Reply sent.');replies=await api(`/api/tickets/${ticket.ticket_id}/replies`);renderReplies(replies,ticket);}catch(e){toast(e.message,'error');}});
      renderReplies(replies,ticket);
    }catch(e){toast(e.message,'error');}
  }
  function renderReplies(replies,ticket){
    let section=[...document.querySelectorAll('section.card')].find(s=>/conversation|repl|activity/i.test(s.textContent));
    if(!section){const main=document.querySelector('main');if(!main)return;section=document.createElement('section');section.className='card';section.innerHTML='<div class="card-head"><h2>Conversation</h2></div><div class="card-body"><div data-replies></div></div>';const form=getMainForm();if(form)form.closest('section.card')?.before(section);else main.append(section);}
    let host=section.querySelector('[data-replies]');if(!host){host=document.createElement('div');host.dataset.replies='';section.querySelector('.card-body')?.prepend(host);}
    host.innerHTML=`<div class="item-list">${replies.length?replies.map(r=>`<div class="item" style="align-items:flex-start"><div><strong>${esc(r.user_name)} ${r.is_internal?'<span class="badge high">Internal note · Staff only</span>':''}</strong><small>${esc(new Date(r.created_at).toLocaleString())}</small><p style="margin:8px 0 0;white-space:pre-wrap">${esc(r.body)}</p></div></div>`).join(''):'<p class="subtitle">No replies yet.</p>'}</div>`;
  }
  async function handleEditDetails() {
    if(!idParam)return;
    if(file==='asset-detail.html'){
      try {
        const asset=await api(`/api/assets/${encodeURIComponent(idParam)}`);
        const values=[asset.asset_tag,asset.asset_name,asset.customer_name,asset.type,asset.serial_no,asset.note,asset.status];
        document.querySelectorAll('.item-list .item').forEach((item,i)=>{const strong=item.querySelector('strong');if(strong&&values[i]!==undefined)strong.textContent=values[i]||'—';});
        const edit=document.querySelector('a[href="add-asset.html"]');if(edit){if(currentUser.role==='admin')edit.href=`add-asset.html?id=${asset.asset_id}`;else edit.style.display='none';}
        const ticketRows=await api('/api/tickets');const linked=ticketRows.filter(t=>String(t.asset_id)===String(asset.asset_id));
        const table=[...document.querySelectorAll('table')].find(t=>(t.querySelector('thead')?.textContent||'').toLowerCase().includes('ticket'));
        if(table)renderTable('tickets',linked,table,file);
      }catch(e){toast(e.message,'error');}
    } else if(file==='customer-detail.html') {
      try {
        let customer=await api(`/api/customers/${encodeURIComponent(idParam)}`);
        const crumb=document.querySelector('.breadcrumb');if(crumb)crumb.innerHTML=`<a href="customers.html">Customers</a> / ${esc(customer.customer_name)}`;
        const edit=document.querySelector('a[href="add-customer.html"]');if(edit){if(currentUser.role==='admin')edit.href=`add-customer.html?id=${customer.customer_id}&edit_customer=1`;else edit.style.display='none';}
        const values=[customer.customer_name,customer.email,customer.phone,customer.address,customer.contact_name];
        document.querySelectorAll('.item-list .item').forEach((item,i)=>{const strong=item.querySelector('strong');if(strong&&values[i]!==undefined)strong.textContent=values[i]||'—';});
      }catch(e){toast(e.message,'error');}
    }
  }
  async function handleEmailPage() {
    const isAdmin=currentUser.role==='admin';
    const columns=[...document.querySelectorAll('.two-col > div')];
    const smtpCard=columns[0]?.querySelector('section.card');
    const rulesCard=columns[0]?.querySelectorAll('section.card')[1];
    if(!isAdmin){
      if(smtpCard)smtpCard.style.display='none';
      columns[1]?.querySelectorAll('section.card').forEach(card=>card.style.display='none');
      const title=rulesCard?.querySelector('h2'); if(title)title.textContent='My email notification preferences';
      const desc=rulesCard?.querySelector('.card-head p'); if(desc)desc.textContent='Choose the email updates you want to receive at your registered email address.';
      const warning=document.querySelector('.notice'); if(warning)warning.textContent='Your preferences apply to ticket notifications sent to your account. SMTP server settings and system-wide rules are managed by an administrator.';
      const tabs=document.querySelector('.tabs'); if(tabs)tabs.style.display='none';
      document.querySelectorAll('.top-actions a[href="email-notifications.html"]').forEach(a=>a.style.display='none');
      const btn=[...document.querySelectorAll('button')].find(b=>/save event rules/i.test(b.textContent)); if(btn)btn.textContent='Save preferences';
    }
    const rulesForm=[...document.querySelectorAll('button')].find(b=>/save (event rules|preferences)/i.test(b.textContent));
    const toggleRows=[...document.querySelectorAll('.toggle-row')];
    if(isAdmin){
      const settingsForm=document.getElementById('email-server-settings-form');
      const testForm=[...document.querySelectorAll('form')].find(f=>[...f.querySelectorAll('button')].some(b=>/send test email/i.test(b.textContent)));
      const provider=document.getElementById('smtp-provider');
      const emailInput=document.getElementById('smtp-email-address');
      const passwordInput=document.getElementById('smtp-app-password');
      const fromNameInput=document.getElementById('smtp-from-name');
      const hostInput=document.getElementById('smtp-host');
      const portInput=document.getElementById('smtp-port');
      const encryptionInput=document.getElementById('smtp-encryption');
      const authInput=document.getElementById('smtp-authentication');
      const usernameInput=document.getElementById('smtp-username');
      const fromEmailInput=document.getElementById('smtp-from-email');
      const replyToInput=document.getElementById('smtp-reply-to');
      const timeoutInput=document.getElementById('smtp-timeout');
      const badgeEl=smtpCard?.querySelector('.card-head .badge');
      function applyProvider(value, force=true){
        if(value==='gmail'){
          if(force||!hostInput.value||hostInput.value==='stmp.cmp'){hostInput.value='smtp.gmail.com';portInput.value='587';encryptionInput.value='STARTTLS';authInput.value='Username and password';}
        }else if(value==='outlook'){
          if(force||!hostInput.value){hostInput.value='smtp.office365.com';portInput.value='587';encryptionInput.value='STARTTLS';authInput.value='Username and password';}
        }
        if(value!=='custom'){
          if(emailInput.value){usernameInput.value=emailInput.value;fromEmailInput.value=emailInput.value;}
          const advanced=document.querySelector('.advanced-mail-settings');if(advanced)advanced.open=false;
        }else{
          const advanced=document.querySelector('.advanced-mail-settings');if(advanced)advanced.open=true;
        }
      }
      provider?.addEventListener('change',()=>applyProvider(provider.value,true));
      emailInput?.addEventListener('input',()=>{if(provider.value!=='custom'){usernameInput.value=emailInput.value;fromEmailInput.value=emailInput.value;}});
      try {
        const settings=await api('/api/email-settings');
        const host=String(settings.smtp_host||'').trim().toLowerCase();
        let providerChoice=host==='smtp.gmail.com'?'gmail':(host==='smtp.office365.com'?'outlook':(host==='stmp.cmp'||!host?'gmail':'custom'));
        if(provider)provider.value=providerChoice;
        if(emailInput)emailInput.value=settings.smtp_username||settings.from_email||'';
        if(passwordInput)passwordInput.value='';
        if(fromNameInput)fromNameInput.value=settings.from_name||'Golden Pride Support';
        if(hostInput)hostInput.value=(providerChoice==='gmail'&&host==='stmp.cmp')?'smtp.gmail.com':(settings.smtp_host||'smtp.gmail.com');
        if(portInput)portInput.value=settings.smtp_port||587;
        if(encryptionInput)encryptionInput.value=settings.encryption||'STARTTLS';
        if(authInput)authInput.value=settings.authentication||'Username and password';
        if(usernameInput)usernameInput.value=settings.smtp_username||settings.from_email||'';
        if(fromEmailInput)fromEmailInput.value=settings.from_email||settings.smtp_username||'';
        if(replyToInput)replyToInput.value=settings.reply_to_email||'';
        if(timeoutInput)timeoutInput.value=settings.timeout||15;
        if(providerChoice!=='custom'&&host!=='stmp.cmp')applyProvider(providerChoice,false);
        if(badgeEl){const ready=Boolean(settings.smtp_password_set&&settings.smtp_username&&settings.from_email&&host!=='stmp.cmp');badgeEl.textContent=ready?'Configured':'Setup required';badgeEl.className=`badge ${ready?'closed':'high'}`;}
      } catch(e){if(badgeEl){badgeEl.textContent='Setup required';badgeEl.className='badge high';}}
      if(settingsForm)settingsForm.addEventListener('submit',async ev=>{
        ev.preventDefault();
        const selected=provider?.value||'gmail';
        const email=(emailInput?.value||'').trim();
        if(!email||!email.includes('@')){toast('Enter the email address used to send notifications.','error');emailInput?.focus();return;}
        const v={event_rules:{},smtp_host:(hostInput?.value||'').trim(),smtp_port:Number(portInput?.value||587),encryption:encryptionInput?.value||'STARTTLS',authentication:authInput?.value||'Username and password',smtp_username:email,from_email:email,from_name:(fromNameInput?.value||'Golden Pride Support').trim(),reply_to_email:(replyToInput?.value||'').trim(),timeout:Number(timeoutInput?.value||15),smtp_password:passwordInput?.value||''};
        if(selected==='gmail'){v.smtp_host='smtp.gmail.com';v.smtp_port=587;v.encryption='STARTTLS';v.authentication='Username and password';}
        else if(selected==='outlook'){v.smtp_host='smtp.office365.com';v.smtp_port=587;v.encryption='STARTTLS';v.authentication='Username and password';}
        else{v.smtp_username=(usernameInput?.value||email).trim();v.from_email=(fromEmailInput?.value||email).trim();}
        toggleRows.forEach(row=>{const k=eventRuleKey(row.querySelector('strong')?.textContent||'');const checkbox=row.querySelector('input[type="checkbox"]');if(checkbox)v.event_rules[k]=checkbox.checked;});
        try{
          const result=await api('/api/email-settings',{method:'PUT',body:JSON.stringify(v)});
          toast(result.message||'Email settings saved.');
          if(badgeEl){badgeEl.textContent='Saved · Test email next';badgeEl.className='badge progress';}
          if(passwordInput)passwordInput.value='';
        }catch(e){toast(e.message,'error');}
      });
      if(testForm)testForm.addEventListener('submit',async ev=>{ev.preventDefault();const input=testForm.querySelector('input[type="email"]');try{const res=await api('/api/email-settings/test',{method:'POST',body:JSON.stringify({recipient:input?.value||''})});toast(res.message);await loadEmailDeliveryActivity();}catch(e){toast(e.message,'error');}});
      async function loadEmailDeliveryActivity(){
        try{
          const records=await api('/api/audit-logs?search=EMAIL');
          const delivery=records.filter(r=>['EMAIL_SENT','EMAIL_FAILED','EMAIL_SKIPPED','SEND_TEST','DAILY_SUMMARY'].includes(r.action)).slice(0,8);
          const table=[...document.querySelectorAll('table')].find(t=>(t.querySelector('thead')?.textContent||'').toLowerCase().includes('event'));
          if(!table)return;const tbody=table.querySelector('tbody');if(!tbody)return;tbody.replaceChildren();
          if(!delivery.length){tbody.innerHTML='<tr><td colspan="3" class="empty-data" style="padding:16px">No delivery attempts have been recorded yet.</td></tr>';return;}
          delivery.forEach(r=>{const tr=document.createElement('tr');const detail=String(r.details||'');const event=(detail.match(/Event ([^;]+)/i)||[])[1]||r.action.replaceAll('_',' ');const recipient=(detail.match(/recipients?: ([^;]+)/i)||[])[1]||r.entity_label||'—';const status=['EMAIL_SENT','SEND_TEST','DAILY_SUMMARY'].includes(r.action)?'Sent':(r.action==='EMAIL_SKIPPED'?'Skipped':'Failed');tr.innerHTML=`<td>${esc(recipient)}</td><td>${esc(event)}</td><td>${badge(status)}</td>`;tbody.appendChild(tr);});
        }catch(_){/* delivery history is admin-only */}
      }
      await loadEmailDeliveryActivity();
      if(rulesForm)rulesForm.addEventListener('click',async ev=>{ev.preventDefault();try{const settings=await api('/api/email-settings');const rules={};toggleRows.forEach(row=>{const k=eventRuleKey(row.querySelector('strong')?.textContent||'');const checkbox=row.querySelector('input[type="checkbox"]');if(checkbox)rules[k]=checkbox.checked;});settings.event_rules=rules;settings.smtp_password='';await api('/api/email-settings',{method:'PUT',body:JSON.stringify(settings)});toast('Global email notification rules saved.');}catch(e){toast(e.message,'error');}});
    } else {
      try {
        const result=await api('/api/notification-preferences');
        toggleRows.forEach(row=>{const key=eventRuleKey(row.querySelector('strong')?.textContent||'');const cb=row.querySelector('input[type="checkbox"]');if(cb&&result.preferences&&Object.prototype.hasOwnProperty.call(result.preferences,key))cb.checked=Boolean(result.preferences[key]);});
      } catch(e){toast(e.message,'error');}
      if(rulesForm)rulesForm.addEventListener('click',async ev=>{ev.preventDefault();const preferences={};toggleRows.forEach(row=>{const k=eventRuleKey(row.querySelector('strong')?.textContent||'');const checkbox=row.querySelector('input[type="checkbox"]');if(checkbox)preferences[k]=checkbox.checked;});try{const result=await api('/api/notification-preferences',{method:'PUT',body:JSON.stringify({preferences})});toast(result.message||'Preferences saved.');}catch(e){toast(e.message,'error');}});
    }
  }

  async function handleAuditPage() {
    if(currentUser.role!=='admin')return;
    const form=document.getElementById('audit-filter-form');const table=document.querySelector('.audit-table');if(!form||!table)return;
    let auditRows=[];const actionSelect=document.getElementById('audit-action');const entitySelect=document.getElementById('audit-entity');const search=document.getElementById('audit-search');const from=document.getElementById('audit-from');const to=document.getElementById('audit-to');const count=document.getElementById('audit-count');
    async function fetchRows(useFilters=true){const qs=new URLSearchParams();if(useFilters){if(search.value.trim())qs.set('search',search.value.trim());if(actionSelect.value)qs.set('action',actionSelect.value);if(entitySelect.value)qs.set('entity',entitySelect.value);if(from.value)qs.set('from_date',from.value);if(to.value)qs.set('to_date',to.value);}try{auditRows=await api('/api/audit-logs'+(qs.toString()?'?'+qs.toString():''));loadedRows['audit-logs']=auditRows;renderTable('audit-logs',auditRows,table,file);if(count)count.textContent=`Showing ${auditRows.length} record${auditRows.length===1?'':'s'}`;}catch(e){toast(e.message,'error');}}
    await fetchRows(false);
    const actions=[...new Set((auditRows||[]).map(r=>r.action).filter(Boolean))].sort();actions.forEach(value=>{const option=document.createElement('option');option.value=value;option.textContent=value.replaceAll('_',' ');actionSelect.appendChild(option);});
    form.addEventListener('submit',ev=>{ev.preventDefault();fetchRows(true);});document.getElementById('audit-clear')?.addEventListener('click',()=>{form.reset();fetchRows(false);});
    document.getElementById('audit-export')?.addEventListener('click',()=>{const headers=['Date','User','Role','Action','Entity','Entity ID','Summary','IP','Changes'];const rows=auditRows.map(r=>[r.created_at,r.user_name,r.actor_role,r.action,r.entity_label||r.module,r.entity_id,r.details,r.ip_address,JSON.stringify(r.changes||{})]);const csv=[headers,...rows].map(row=>row.map(v=>'"'+String(v??'').replace(/"/g,'""')+'"').join(',')).join('\r\n');const blob=new Blob([csv],{type:'text/csv;charset=utf-8;'});const url=URL.createObjectURL(blob);const a=document.createElement('a');a.href=url;a.download='golden-pride-audit-log.csv';a.click();URL.revokeObjectURL(url);toast('Audit log exported.');});
    document.addEventListener('click',async ev=>{const button=ev.target.closest('[data-audit-view]');if(!button)return;try{const record=await api(`/api/audit-logs/${encodeURIComponent(button.dataset.auditView)}`);let dialog=document.getElementById('audit-changes-dialog');if(!dialog){dialog=document.createElement('dialog');dialog.id='audit-changes-dialog';dialog.className='audit-changes-dialog';document.body.appendChild(dialog);}const changes=record.changes||{};const rows=Object.entries(changes).map(([key,val])=>`<tr><td><strong>${esc(key.replaceAll('_',' '))}</strong></td><td>${esc(val?.from===null||val?.from===undefined?'—':(typeof val.from==='object'?JSON.stringify(val.from):String(val.from)))}</td><td>${esc(val?.to===null||val?.to===undefined?'—':(typeof val.to==='object'?JSON.stringify(val.to):String(val.to)))}</td></tr>`).join('');dialog.innerHTML=`<div class="audit-dialog-head"><div><strong>Audit details</strong><div class="subtitle">${esc(record.user_name||'System')} · ${esc(record.action)} · ${esc(record.entity_label||record.module||'')}</div></div><button type="button" class="btn btn-sm" data-audit-close>Close</button></div><div class="audit-dialog-body"><p><strong>Summary:</strong> ${esc(record.details||'—')}</p><p><strong>Entity:</strong> ${esc(record.module||'—')} / ${esc(record.entity_id||'—')} <strong style="margin-left:12px">IP:</strong> ${esc(record.ip_address||'—')}</p>${rows?`<h3 style="margin:18px 0 8px">Field changes</h3><table class="audit-change-grid"><thead><tr><th>Field</th><th>Previous value</th><th>New value</th></tr></thead><tbody>${rows}</tbody></table>`:'<p class="subtitle">No field-level changes were recorded for this event.</p>'}</div>`;if(dialog.showModal)dialog.showModal();else dialog.setAttribute('open','open');}catch(e){toast(e.message,'error');}});
    document.addEventListener('click',ev=>{if(ev.target.closest('[data-audit-close]'))document.getElementById('audit-changes-dialog')?.close?.();});
  }

  async function handleChangePassword() {
    if(file!=='change-password.html')return;const form=document.getElementById('change-password-form');if(!form)return;
    form.addEventListener('submit',async ev=>{ev.preventDefault();const current=form.querySelector('[name="current_password"]')?.value||'';const next=form.querySelector('[name="new_password"]')?.value||'';const confirm=form.querySelector('[name="confirm_password"]')?.value||'';if(next!==confirm){toast('The new password and confirmation do not match.','error');return;}if(next.length<10){toast('Use at least 10 characters for the new password.','error');return;}try{const result=await api('/api/auth/change-password',{method:'POST',body:JSON.stringify({current_password:current,new_password:next})});currentUser.must_change_password=false;toast(result.message);location.href=homeByRole[currentUser.role]||'login.html';}catch(e){toast(e.message,'error');}});
  }

  async function handleRoleForm() {
    if(file!=='add-role.html' || currentUser.role!=='admin')return;
    const form=getMainForm();if(!form)return;
    form.addEventListener('submit',async ev=>{ev.preventDefault();const fields=[...form.querySelectorAll('.field')];const roleName=fields[0]?.querySelector('input')?.value.trim();const description=fields[1]?.querySelector('input')?.value.trim()||'';if(!roleName){toast('Enter a role name.','error');return;}const permissions={};
      form.querySelectorAll('tbody tr').forEach(tr=>{const cells=[...tr.children];const module=cells[0]?.textContent.trim();if(!module)return;permissions[module]=cells.slice(1).map(td=>!!td.querySelector('input[type="checkbox"]:checked'));});
      try{await api('/api/role-permissions',{method:'POST',body:JSON.stringify({role_key:roleName,description,permissions})});toast('Role permissions saved.');location.href='roles-access.html';}catch(e){toast(e.message,'error');}
    });
  }
  function setupCustomerEntityMode(isEdit) {
    customerEntityMode = true;
    customerEditMode = Boolean(isEdit);
    const title=document.querySelector('main h1'); if(title) title.textContent=isEdit?'Edit customer':'Add customer';
    const subtitle=document.querySelector('main .subtitle'); if(subtitle) subtitle.textContent=isEdit?'Update the customer organization profile':'Create a customer organization profile';
    const intro=document.querySelector('.notice'); if(intro) intro.textContent=isEdit?'Edit the saved company details and save your changes.':'Create a customer organization profile. User login accounts are managed separately in User Management.';
    const form=getMainForm(); const submit=form?.querySelector('button[type="submit"]'); if(submit) submit.textContent=isEdit?'Save customer changes':'Create customer';
  }

  async function initPage() {
    let user;
    try { user=await api('/api/auth/me'); }
    catch (_) { clearSession(); location.replace('login.html'); return; }
    setSession(user);
    if(!profileAndGuard())return;
    try { await loadLookups(); } catch(_) {}
    let cfg=formConfig[file];
    if(file==='add-customer.html') {
      const isEdit=Boolean(idParam);
      setupCustomerEntityMode(isEdit);
      cfg=customerEntityConfig;
    }
    activeFormConfig=cfg;
    configureSelects();
    if(cfg && !cfg.alwaysUpdate) {
      try { await fillEditForm(cfg); } catch(e){toast(e.message,'error');}
      await handleStandardForm(cfg);
    }
    if(file==='ticket-detail.html') { await handleTicketDetail(); await handleStaffTicketConversation(); }
    if(file==='user-create-ticket.html') await handleCustomerCreateTicket();
    if(file==='user-ticket-detail.html') await handleTicketConversation();
    if(file==='asset-detail.html' || file==='customer-detail.html') await handleEditDetails();
    if(file==='email-notifications.html') await handleEmailPage();
    if(file==='change-password.html') await handleChangePassword();
    if(file==='add-role.html') await handleRoleForm();
    if(pageResource[file]) await loadList(pageResource[file]);
    if(file==='audit-log.html') await handleAuditPage();
    if(['dashboard.html','admin-dashboard.html','agent-dashboard.html','user-dashboard.html'].includes(file)) {
      try {const stats=await api('/api/dashboard/stats');updateDashboard(stats);if(file==='user-dashboard.html'){const t=document.querySelector('table');if(t)renderTable('tickets',stats.recent_tickets||[],t,file);}}catch(_){}
    }
    installSearch();
    try { const next=sessionStorage.getItem('gpNextScroll'); const same=sessionStorage.getItem('gpScroll:'+location.pathname+location.search); sessionStorage.removeItem('gpNextScroll'); const y=Number(next!==null?next:(same||0)); if(y>0) requestAnimationFrame(()=>window.scrollTo({top:y,behavior:'auto'})); } catch (_) {}
    // Update older prototype-only copy without changing the supplied page layout/features.
    document.querySelectorAll('.notice').forEach(n=>{if(/static prototype does not save submitted data/i.test(n.textContent))n.textContent='Records are saved securely to the connected database when you submit this form.';if(/prototype mode/i.test(n.textContent)&&file==='email-notifications.html')n.textContent='Email delivery runs through the Python backend. Configure SMTP settings below to send notifications.';});
  }
  if(file==='login.html') initLogin();
  else initPage();
})();
