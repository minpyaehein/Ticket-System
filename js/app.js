/* Golden Pride: keeps the supplied HTML/CSS pages and connects them to FastAPI/PostgreSQL. */
(() => {
  'use strict';
  const file = (location.pathname.split('/').pop() || 'login.html').toLowerCase();
  const params = new URLSearchParams(location.search);
  const idParam = params.get('id');
  const homeByRole = { admin: 'admin-dashboard.html', agent: 'agent-dashboard.html', customer: 'user-dashboard.html' };
  const allowedByRole = {
    admin: null,
    agent: ['agent-dashboard.html','dashboard.html','tickets.html','add-ticket.html','ticket-detail.html','customers.html','customer-detail.html','projects.html','contracts.html','support-plans.html','service-catalog.html','contacts.html','assets.html','asset-detail.html','role-agent.html'],
    customer: ['user-dashboard.html','my-tickets.html','user-create-ticket.html','user-ticket-detail.html','user-service-catalog.html','user-assets.html','role-user.html']
  };
  const pageResource = {
    'tickets.html':'tickets','my-tickets.html':'tickets','dashboard.html':'tickets',
    'admin-dashboard.html':'tickets','agent-dashboard.html':'tickets','user-dashboard.html':'tickets',
    'projects.html':'projects','customers.html':'customers','contacts.html':'contacts','contracts.html':'contracts',
    'support-plans.html':'plans','service-catalog.html':'services','user-service-catalog.html':'services',
    'teams.html':'teams','users.html':'users','assets.html':'assets','user-assets.html':'assets','audit-log.html':'audit-logs'
  };
  const customerEntityConfig = {resource:'customers', redirect:'customers.html', map:{'full name':'customer_name','email':'email','phone':'phone','address':'address','primary contact':'contact_name','notes':'notes'}};
  const customerEditConfig = customerEntityConfig;
  const formConfig = {
    'add-asset.html': {resource:'assets', redirect:'assets.html', map:{'customer':'customer_id','project':'project_id','asset tag':'asset_tag','asset name':'asset_name','type':'type','asset status':'status','vendor':'vendor','model':'model','serial number':'serial_no','ip address':'ip_address','note':'note'}},
    'add-contact.html': {resource:'contacts', redirect:'contacts.html', map:{'customer':'customer_id','contact no':'contact_code','full name':'fullname','department':'department','job title':'job_title','email':'email','phone':'phone','type':'type','notes':'note'}},
    'add-contract.html': {resource:'contracts', redirect:'contracts.html', map:{'customer':'customer_id','project':'project_id','contract no':'contract_code','contract name':'contract_name','support plan':'plan_id','start date':'start_date','end date':'end_date','scope / covered service':'scope'}},
    'add-customer.html': {resource:'users', redirect:'users.html', map:{'full name':'fullname','email':'email','password':'password','role':'role','support team':'team_id','notes':'notes'}},
    'add-project.html': {resource:'projects', redirect:'projects.html', map:{'customer':'customer_id','project code':'project_code','project name':'project_name','project manager':'project_manager','project status':'status','start date':'start_date','end date':'end_date','description':'description'}},
    'add-service.html': {resource:'services', redirect:'service-catalog.html', map:{'code':'code_id','name':'name','category':'category','sort order':'request_order','customer visible':'customer_visible','asset requirements':'asset_requirement','mapped team':'mapped_team','auto assign':'auto_assign','assignment method':'assignment_method','description':'description'}},
    'add-request-type.html': {resource:'services', redirect:'service-catalog.html', map:{'code':'code_id','name':'name','category':'category','sort order':'request_order','customer visible':'customer_visible','asset requirements':'asset_requirement','mapped team':'mapped_team','auto assign':'auto_assign','assignment method':'assignment_method','description':'description'}},
    'add-support-plan.html': {resource:'plans', redirect:'support-plans.html', map:{'plan code':'plan_code','plan name':'plan_name','response sla':'response_sla','resolution sla':'resolution_sla','response warning %':'response_warning','response critical %':'response_critical','resolution warning %':'resolution_warning','resolution critical %':'resolution_critical','sla calendar mode':'sla_mode','time zone':'time_zone','business start':'business_start_hour','business end':'business_end_hour','working days':'working_days','escalation level':'escalation_level','remote support':'remote_support','onsite support':'onsite_support','description':'description'}},
    'add-team.html': {resource:'teams', redirect:'teams.html', map:{'team code':'team_code','team name':'team_name','team members':'member','service catalog':'service_codes','description':'description'}},
    'add-ticket.html': {resource:'tickets', redirect:'tickets.html', map:{'ticket':'customer_id','customer/project':'project_id','contract / plan':'contract_id','request type':'type','subject':'subject','status':'status','asset':'asset_id','assigned':'assigned','created':'date'}},
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
        setSession(user); location.href=user.home;
      } catch(e) {
        errorBox.textContent=e.message || 'The username or password is incorrect.'; errorBox.classList.add('show');
      } finally {if(button){button.disabled=false;button.textContent='Sign in →';}}
    });
    // A valid server-side session can go directly to its role dashboard.
    try { const user=await api('/api/auth/me'); setSession(user); location.replace(homeByRole[user.role] || 'login.html'); }
    catch (_) { clearSession(); }
  }
  function profileAndGuard() {
    const role=currentUser.role, page=file;
    if (allowedByRole[role] && !allowedByRole[role].includes(page)) {
      location.replace(`${homeByRole[role]}?denied=${encodeURIComponent(page)}`); return false;
    }
    document.querySelectorAll('[data-customer-name]').forEach(el=>{if(el.matches('input,textarea')) el.value=currentUser.fullname; else el.textContent=currentUser.fullname;});
    document.querySelectorAll('[data-customer-email]').forEach(el=>{if(el.matches('input,textarea')) el.value=currentUser.email; else el.textContent=currentUser.email;});
    document.querySelectorAll('[data-customer-avatar]').forEach(el=>el.textContent=currentUser.fullname.split(/\s+/).map(x=>x[0]).join('').slice(0,2).toUpperCase());
    const profile=document.querySelector('.sidebar-bottom');
    if(profile){
      const avatar=profile.querySelector('.avatar'); if(avatar) avatar.textContent=currentUser.fullname.split(/\s+/).map(x=>x[0]).join('').slice(0,2).toUpperCase();
      const strong=profile.querySelector('strong'); if(strong) strong.textContent=currentUser.fullname;
      const small=profile.querySelector('small'); if(small) small.textContent=currentUser.email;
    }
    document.querySelectorAll('[data-logout]').forEach(el=>el.addEventListener('click',async ev=>{ev.preventDefault();try{await api('/api/auth/logout',{method:'POST'});}catch(_){}clearSession();location.href='login.html';}));
    document.querySelectorAll('a[href="dashboard.html"]').forEach(a=>a.setAttribute('href',homeByRole[role]||'dashboard.html'));
    const denied=params.get('denied');
    if(denied){const box=document.getElementById('access-notice');if(box){box.className='access-callout';box.textContent=`Access restricted: your ${role} role does not have permission to open ${denied}.`;}}
    return true;
  }
  async function loadLookups() {
    try { lookupData=await api('/api/lookups'); }
    catch (_) { lookupData={}; }
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
        const match=[...select.options].find(o=>String(o.value)===String(value)) || [...select.options].find(o=>o.textContent.trim().toLowerCase()===String(value).toLowerCase());
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
      if(file==='add-team.html' && label==='service catalog') value=row.service_code_ids || (row.code_id?[row.code_id]:[]);
      if(file==='add-team.html' && label==='team members') value=row.member || '';
      setField(field,value,file,label);
    });
    if(page==='add-customer.html' && !customerEntityMode) {
      const passwordField=[...form.querySelectorAll('.field')].find(field=>labelForField(field)==='password');
      const passwordInput=passwordField?.querySelector('input');
      if(passwordInput){passwordInput.required=false;passwordInput.placeholder='Leave blank to keep current password';}
    }
    const submit=form.querySelector('button[type="submit"]'); if(submit) submit.textContent=submit.textContent.replace(/Create|Save|Submit/i,'Update');
    const title=document.querySelector('h1'); if(title && !title.textContent.toLowerCase().includes('edit')) title.textContent=`Edit ${title.textContent.trim()}`;
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
      if(h==='action' || h==='actions') return rowActions('tickets',row.ticket_id,null,ticketHref(row),'View');
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
      const mappings=[['plan code',row.plan_code || ('PLAN-'+row.plan_id)],['plan name',row.plan_name],['response sla',row.response_sla],['rsponse sla',row.response_sla],['resolution sla',row.resolution_sla],['reslution sla',row.resolution_sla],['response warning',row.response_warning],['reslution warning',row.resolution_warning],['response critical',row.response_critical],['reslution critical',row.resolution_critical],['calendar mode',row.sla_mode],['calender mode',row.sla_mode],['time zone',row.time_zone],['business start',row.business_start_hour],['business end',row.business_end_hour],['working days',row.working_days],['escalation level',row.escalation_level],['remote support',row.remote_support],['on-site support',row.onsite_support],['actions',rowActions('plans',row.plan_id,`add-support-plan.html?id=${row.plan_id}`,null)]];
      const found=mappings.find(([key])=>h.includes(key)); if(found) return typeof found[1]==='string' && found[1].startsWith('<a ') ? found[1] : esc(found[1] ?? '—');
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
      if(h.includes('assignment method')) return esc(row.assignment_method || '—');
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
      if(h.includes('action')) return rowActions('users',row.user_id,`add-customer.html?id=${row.user_id}`,null);
    }
    if(resource==='audit-logs') {
      if(h.includes('timestamp')) return esc(row.created_at ? new Date(row.created_at).toLocaleString() : '—');
      if(h==='customer' || h==='user' || h==='user name') return esc(row.user_name || 'System');
      if(h==='action') return esc(row.action);
      if(h==='module') return esc(row.module);
      if(h==='record') return esc(row.details || '—');
      if(h.includes('ip address')) return '—';
      if(h==='result') return badge(row.action==='LOGIN_FAILED'?'Failed':'Success');
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
      headers.forEach(header=>{const td=document.createElement('td');td.innerHTML=cellFor(resource,row,header,page);tr.appendChild(td);});
      tbody.appendChild(tr);
    });
    const foot=table.closest('.card')?.querySelector('.table-foot');
    if(foot){const span=foot.querySelector('span');if(span)span.textContent=`Showing ${rows.length} record${rows.length===1?'':'s'}`;const pagination=foot.querySelector('.pagination');if(pagination)pagination.innerHTML='';}
  }
  function chooseTable(resource) {
    const tables=[...document.querySelectorAll('table')];
    return tables.find(t=>{const text=t.querySelector('thead')?.textContent.toLowerCase()||'';return resource==='tickets'?text.includes('ticket'):resource==='assets'?text.includes('asset'):resource==='services'?text.includes('code')||text.includes('service'):resource==='audit-logs'?text.includes('timestamp'):resource==='users'?text.includes('fullname'):resource==='projects'?text.includes('project code'):resource==='customers'?text.includes('company'):resource==='contacts'?text.includes('contact no'):resource==='contracts'?text.includes('contract no'):resource==='plans'?text.includes('plan code'):resource==='teams'?text.includes('team code'):false;}) || tables[0];
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
        const values=[...panel.querySelectorAll('.filter-grid input,.filter-grid select')].map(x=>x.value.trim().toLowerCase()).filter(Boolean).filter(v=>!/^all\s/i.test(v));
        const filtered=rows.filter(r=>values.every(v=>JSON.stringify(r).toLowerCase().includes(v)));
        const table=chooseTable(resource);if(table)renderTable(resource,filtered,table,file);
      });
      const reset=[...panel.querySelectorAll('a')].find(a=>/^reset$/i.test(a.textContent.trim()));
      if(reset && resource) reset.addEventListener('click',ev=>{ev.preventDefault();panel.querySelectorAll('input,select').forEach(el=>{if(el.tagName==='SELECT')el.selectedIndex=0;else el.value='';});const table=chooseTable(resource);if(table)renderTable(resource,loadedRows[resource]||[],table,file);});
    });
    document.querySelectorAll('a[href="#"]').forEach(a=>{
      if(/export csv/i.test(a.textContent)) a.addEventListener('click',ev=>{ev.preventDefault();const resource=pageResource[file],rows=loadedRows[resource]||[];exportCsv(resource,rows);});
    });
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
        if(file==='add-customer.html' && !customerEntityMode) {
          const role=String(payload.role||'customer').toLowerCase();payload.role=role==='administrator'?'admin':role;
          if(!payload.password && !id) throw new Error('Enter a temporary password for this account.');
        }
        if(file==='add-project.html' && !payload.customer_id) throw new Error('Select a customer for this project.');
        if(file==='add-contact.html' && !payload.customer_id) throw new Error('Select the contact’s customer.');
        if(file==='add-contract.html' && !payload.customer_id) throw new Error('Select a customer for this contract.');
        if(file==='add-asset.html' && !payload.asset_tag) throw new Error('Enter an asset tag.');
        if(file==='add-team.html' && payload.service_codes?.length) payload.code_id=payload.service_codes[0];
        const shouldUpdate=Boolean(id);
        const result=await api(shouldUpdate?`/api/${cfg.resource}/${encodeURIComponent(id)}`:`/api/${cfg.resource}`,{method:shouldUpdate?'PUT':'POST',body:JSON.stringify(payload)});
        toast(shouldUpdate?'Record updated successfully.':'Record created successfully.');
        if(file==='add-customer.html' && !customerEntityMode && result.role) location.href='users.html';
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
      document.querySelectorAll('h2').forEach(h=>{if(/Database connection|Ticket information|Ticket details/i.test(h.textContent))h.textContent=ticket.subject;});
      if(form){form.querySelectorAll('.field').forEach(field=>{const label=labelForField(field);const key=cfgFieldForTicket(label);if(key)setField(field,ticket[key],file,label);});form.addEventListener('submit',async ev=>{ev.preventDefault();try{const payload=payloadForForm(file,form,formConfig[file]);await api(`/api/tickets/${ticket.ticket_id}`,{method:'PUT',body:JSON.stringify(payload)});toast('Ticket updated.');location.href=`ticket-detail.html?id=${ticket.ticket_id}`;}catch(e){toast(e.message,'error');}});}
    }catch(e){toast(e.message,'error');}
  }
  function cfgFieldForTicket(label){return formConfig['ticket-detail.html'].map[label];}
  async function handleCustomerCreateTicket() {
    const serviceName=params.get('service');
    const form=getMainForm();if(!form)return;
    if(serviceName){const serviceSelect=[...form.querySelectorAll('.field')].find(f=>labelForField(f)==='service')?.querySelector('select');if(serviceSelect){const option=[...serviceSelect.options].find(o=>o.value===serviceName||o.textContent===serviceName);if(option)serviceSelect.value=option.value;}}
  }
  async function handleTicketConversation() {
    const id=idParam;
    if(!id){const notice=document.createElement('div');notice.className='notice warning';notice.textContent='Please open this ticket from My Tickets so its ID is included.';document.querySelector('.breadcrumb')?.after(notice);return;}
    try {
      const ticket=await api(`/api/tickets/${encodeURIComponent(id)}`);
      const heading=document.querySelector('main h1');if(heading)heading.textContent=`${ticket.ticket_code} · ${ticket.subject}`;
      document.querySelectorAll('.breadcrumb').forEach(b=>{if(b.textContent.toLowerCase().includes('ticket'))b.innerHTML=`<a href="my-tickets.html">My tickets</a> / ${esc(ticket.ticket_code)}`;});
      let replies=await api(`/api/tickets/${ticket.ticket_id}/replies`);
      const form=getMainForm();if(form) form.addEventListener('submit',async ev=>{ev.preventDefault();const textarea=form.querySelector('textarea');const body=textarea?.value.trim();if(!body){toast('Write a reply before sending.','error');return;}try{await api(`/api/tickets/${ticket.ticket_id}/replies`,{method:'POST',body:JSON.stringify({body})});textarea.value='';toast('Reply sent.');replies=await api(`/api/tickets/${ticket.ticket_id}/replies`);renderReplies(replies,ticket);}catch(e){toast(e.message,'error');}});
      renderReplies(replies,ticket);
    }catch(e){toast(e.message,'error');}
  }
  function renderReplies(replies,ticket){
    let section=[...document.querySelectorAll('section.card')].find(s=>/conversation|repl|activity/i.test(s.textContent));
    if(!section){const main=document.querySelector('main');if(!main)return;section=document.createElement('section');section.className='card';section.innerHTML='<div class="card-head"><h2>Conversation</h2></div><div class="card-body"><div data-replies></div></div>';const form=getMainForm();if(form)form.closest('section.card')?.before(section);else main.append(section);}
    let host=section.querySelector('[data-replies]');if(!host){host=document.createElement('div');host.dataset.replies='';section.querySelector('.card-body')?.prepend(host);}
    host.innerHTML=`<div class="item-list">${replies.length?replies.map(r=>`<div class="item" style="align-items:flex-start"><div><strong>${esc(r.user_name)}</strong><small>${esc(new Date(r.created_at).toLocaleString())}</small><p style="margin:8px 0 0;white-space:pre-wrap">${esc(r.body)}</p></div></div>`).join(''):'<p class="subtitle">No replies yet.</p>'}</div>`;
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
    if(currentUser.role!=='admin')return;
    const forms=[...document.querySelectorAll('form')].filter(f=>!f.classList.contains('compact-search'));
    const settingsForm=forms.find(f=>[...f.querySelectorAll('button')].some(b=>/save mail settings/i.test(b.textContent)));
    const testForm=forms.find(f=>[...f.querySelectorAll('button')].some(b=>/send test email/i.test(b.textContent)));
    try {
      const settings=await api('/api/email-settings');
      if(settingsForm){settingsForm.querySelectorAll('.field').forEach(field=>{const label=labelForField(field);const keys={'smtp host':'smtp_host','smtp port':'smtp_port','encryption':'encryption','authentication':'authentication','smtp username':'smtp_username','from name':'from_name','from email':'from_email','reply-to email':'reply_to_email','connection timeout (seconds)':'timeout'};const key=keys[label];if(key){const input=field.querySelector('input,select');if(input&&settings[key]!==undefined)input.value=settings[key];}});}
    } catch(e) { /* Settings may be new; the form stays usable. */ }
    if(settingsForm)settingsForm.addEventListener('submit',async ev=>{ev.preventDefault();const v={event_rules:{}};settingsForm.querySelectorAll('.field').forEach(field=>{const label=labelForField(field);const keys={'smtp host':'smtp_host','smtp port':'smtp_port','encryption':'encryption','authentication':'authentication','smtp username':'smtp_username','smtp password':'smtp_password','from name':'from_name','from email':'from_email','reply-to email':'reply_to_email','connection timeout (seconds)':'timeout'};const key=keys[label];if(!key)return;const el=field.querySelector('input,select');if(!el)return;v[key]=el.type==='number'?Number(el.value||0):el.value;});
      document.querySelectorAll('.toggle-row').forEach(row=>{const k=labelKey(row.querySelector('strong')?.textContent||'').replace(/ /g,'_');const checkbox=row.querySelector('input[type="checkbox"]');if(checkbox)v.event_rules[k]=checkbox.checked;});
      try{await api('/api/email-settings',{method:'PUT',body:JSON.stringify(v)});toast('Email settings saved.');const b=document.querySelector('.card-head .badge');if(b){b.textContent='Settings saved';b.className='badge closed';}}catch(e){toast(e.message,'error');}
    });
    if(testForm)testForm.addEventListener('submit',async ev=>{ev.preventDefault();const input=testForm.querySelector('input[type="email"]');try{const res=await api('/api/email-settings/test',{method:'POST',body:JSON.stringify({recipient:input?.value||''})});toast(res.message);}catch(e){toast(e.message,'error');}});
    const saveRules=[...document.querySelectorAll('button')].find(b=>/save event rules/i.test(b.textContent));
    if(saveRules)saveRules.addEventListener('click',async ev=>{ev.preventDefault();try{const settings=await api('/api/email-settings');const rules={};document.querySelectorAll('.toggle-row').forEach(row=>{const k=labelKey(row.querySelector('strong')?.textContent||'').replace(/ /g,'_');const checkbox=row.querySelector('input[type="checkbox"]');if(checkbox)rules[k]=checkbox.checked;});settings.event_rules=rules;settings.smtp_password='';await api('/api/email-settings',{method:'PUT',body:JSON.stringify(settings)});toast('Email notification rules saved.');}catch(e){toast(e.message,'error');}});
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
    const form=getMainForm(); if(!form) return;
    const grid=form.querySelector('.form-grid');
    const hideLabels=new Set(['password','role','support team']);
    form.querySelectorAll('.field').forEach(field=>{
      if(hideLabels.has(labelForField(field))) {
        field.style.display='none';
        field.querySelectorAll('input,select,textarea').forEach(control=>{control.disabled=true;control.required=false;});
      }
    });
    const fields=[['Phone','phone','tel'],['Address','address','text'],['Primary contact','contact_name','text']];
    fields.forEach(([label,name,type])=>{
      const wrapper=document.createElement('div');wrapper.className='field';
      wrapper.innerHTML=`<label>${label}</label><input class="input" type="${type}" data-customer-edit-field="${name}" value="">`;
      grid?.appendChild(wrapper);
    });
    const title=document.querySelector('main h1');if(title)title.textContent=isEdit?'Edit customer':'Create customer';
    const submit=form.querySelector('button[type="submit"]');if(submit)submit.textContent=isEdit?'Save customer changes':'Create customer record';
    const intro=document.querySelector('.notice');if(intro)intro.textContent=isEdit?'Update the customer record saved in the database.':'Create a customer organization record. Login accounts are managed separately.';
  }

  async function initPage() {
    let user;
    try { user=await api('/api/auth/me'); }
    catch (_) { clearSession(); location.replace('login.html'); return; }
    setSession(user);
    if(!profileAndGuard())return;
    try { await loadLookups(); } catch(_) {}
    let cfg=formConfig[file];
    if(file==='add-customer.html' && (params.get('edit_customer')==='1' || params.get('record')==='customer')) {
      const isEdit=params.get('edit_customer')==='1';
      setupCustomerEntityMode(isEdit);
      cfg=customerEntityConfig;
    }
    activeFormConfig=cfg;
    configureSelects();
    if(cfg && !cfg.alwaysUpdate) {
      try { await fillEditForm(cfg); } catch(e){toast(e.message,'error');}
      await handleStandardForm(cfg);
    }
    if(file==='ticket-detail.html') await handleTicketDetail();
    if(file==='user-create-ticket.html') await handleCustomerCreateTicket();
    if(file==='user-ticket-detail.html') await handleTicketConversation();
    if(file==='asset-detail.html' || file==='customer-detail.html') await handleEditDetails();
    if(file==='email-notifications.html') await handleEmailPage();
    if(file==='add-role.html') await handleRoleForm();
    if(pageResource[file]) await loadList(pageResource[file]);
    if(['dashboard.html','admin-dashboard.html','agent-dashboard.html','user-dashboard.html'].includes(file)) {
      try {const stats=await api('/api/dashboard/stats');updateDashboard(stats);if(file==='user-dashboard.html'){const t=document.querySelector('table');if(t)renderTable('tickets',stats.recent_tickets||[],t,file);}}catch(_){}
    }
    installSearch();
    // Update older prototype-only copy without changing the supplied page layout/features.
    document.querySelectorAll('.notice').forEach(n=>{if(/static prototype does not save submitted data/i.test(n.textContent))n.textContent='Records are saved securely to the connected database when you submit this form.';if(/prototype mode/i.test(n.textContent)&&file==='email-notifications.html')n.textContent='Email delivery runs through the Python backend. Configure SMTP settings below to send notifications.';});
    if(file==='add-customer.html'){
      const teamField=[...document.querySelectorAll('.field')].find(f=>labelForField(f)==='support team');const input=teamField?.querySelector('input');
      if(input){const select=document.createElement('select');select.className='select';select.innerHTML='<option value="">Select support team</option>'; (lookupData.teams||[]).forEach(t=>select.insertAdjacentHTML('beforeend',`<option value="${t.team_id}">${esc(t.team_name)}</option>`));input.replaceWith(select);}
    }
  }
  if(file==='login.html') initLogin();
  else initPage();
})();
