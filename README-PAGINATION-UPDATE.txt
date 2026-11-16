GOLDEN PRIDE - 10-RECORD PAGINATION UPDATE

WHAT CHANGED
- Ticket register and Customer My Tickets: 10 records per page; newest tickets first.
- Customers, Projects, Contracts, Support Plans, Service Catalog, Contacts, Assets and Teams: 10 records per page.
- User Management: separate Administrators, Agents and Customers tabs; each tab has its own 10-record pagination.
- Customer portal: My Assets and customer-visible Service Catalog cards are paginated 10 per page.
- Audit Log: search/filter results are displayed 10 records per page; export still exports the full filtered source list.
- Email Delivery Log: 10 records per page, using database LIMIT/OFFSET and a total count so older delivery records remain accessible beyond the old 300-row display.
- Existing role access rules are unchanged. User Management, Audit Log and Email Delivery Log remain Admin-only.
- Existing dashboard layout, bar chart, Agent Overview and Customer Overview are retained; dashboard Recent Tickets panels remain removed.

INSTALLATION
1. Stop the FastAPI server.
2. Back up your existing golden_pride_ticket_system folder.
3. Extract the included golden_pride_ticket_system folder over your existing project folder and allow the updated files to replace the old ones.
4. Keep your existing .env file. This update archive intentionally does not include .env or .venv.
5. No PostgreSQL schema migration is required.
6. Start FastAPI again and hard-refresh the website with Ctrl+F5.

NOTES
- The standard register pages use the existing list API and paginate the loaded records in the browser. The Email Delivery Log uses database offset pagination.
- Search/filter actions reset their page to page 1.
- New ticket and ID-based records appear at the start of the list; older records are reachable on later pages.
- The update has been syntax-checked, but a live login/database test must be completed in your own PostgreSQL environment.
