-- Golden Pride Ticket Service System PostgreSQL schema
-- Generated from main.py SQLAlchemy models. The FastAPI app runs create_all() on startup.

CREATE TABLE IF NOT EXISTS customers (
	customer_id SERIAL NOT NULL, 
	customer_name VARCHAR(160) NOT NULL, 
	email VARCHAR(254), 
	phone VARCHAR(50), 
	address TEXT, 
	contact_name VARCHAR(160), 
	notes TEXT, 
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	PRIMARY KEY (customer_id)
);

CREATE TABLE IF NOT EXISTS email_settings (
	setting_id INTEGER NOT NULL, 
	settings_json TEXT NOT NULL, 
	updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	PRIMARY KEY (setting_id)
);

CREATE TABLE IF NOT EXISTS plans (
	plan_id SERIAL NOT NULL, 
	plan_code VARCHAR(50), 
	plan_name VARCHAR(160) NOT NULL, 
	response_sla VARCHAR(80), 
	resolution_sla VARCHAR(80), 
	response_warning INTEGER, 
	response_critical INTEGER, 
	resolution_warning INTEGER, 
	resolution_critical INTEGER, 
	sla_mode VARCHAR(80), 
	time_zone VARCHAR(80), 
	business_start_hour VARCHAR(10), 
	business_end_hour VARCHAR(10), 
	working_days TEXT, 
	escalation_level VARCHAR(50), 
	remote_support VARCHAR(40), 
	onsite_support VARCHAR(40), 
	description TEXT, 
	PRIMARY KEY (plan_id), 
	UNIQUE (plan_name)
);

CREATE TABLE IF NOT EXISTS role_permissions (
	role_permission_id SERIAL NOT NULL, 
	role_key VARCHAR(80) NOT NULL, 
	description TEXT, 
	permissions_json TEXT NOT NULL, 
	PRIMARY KEY (role_permission_id), 
	UNIQUE (role_key)
);

CREATE TABLE IF NOT EXISTS service_catalog (
	code_id VARCHAR(50) NOT NULL, 
	name VARCHAR(180) NOT NULL, 
	category VARCHAR(100), 
	request_order INTEGER NOT NULL, 
	customer_visible BOOLEAN NOT NULL, 
	asset_requirement VARCHAR(80), 
	mapped_team VARCHAR(160), 
	auto_assign BOOLEAN NOT NULL, 
	assignment_method VARCHAR(80), 
	description TEXT, 
	PRIMARY KEY (code_id)
);

CREATE TABLE IF NOT EXISTS contacts (
	contact_id SERIAL NOT NULL, 
	contact_code VARCHAR(50), 
	customer_id INTEGER NOT NULL, 
	fullname VARCHAR(160) NOT NULL, 
	department VARCHAR(120), 
	job_title VARCHAR(120), 
	email VARCHAR(254), 
	phone VARCHAR(50), 
	type VARCHAR(80), 
	note TEXT, 
	PRIMARY KEY (contact_id), 
	UNIQUE (contact_code), 
	FOREIGN KEY(customer_id) REFERENCES customers (customer_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS projects (
	project_id SERIAL NOT NULL, 
	project_code VARCHAR(50), 
	customer_id INTEGER NOT NULL, 
	project_name VARCHAR(180) NOT NULL, 
	project_manager VARCHAR(160), 
	status VARCHAR(50) NOT NULL, 
	date DATE, 
	start_date DATE, 
	end_date DATE, 
	description TEXT, 
	PRIMARY KEY (project_id), 
	FOREIGN KEY(customer_id) REFERENCES customers (customer_id) ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS teams (
	team_id SERIAL NOT NULL, 
	team_code VARCHAR(50), 
	team_name VARCHAR(160) NOT NULL, 
	member TEXT, 
	code_id VARCHAR(50), 
	description TEXT, 
	PRIMARY KEY (team_id), 
	UNIQUE (team_code), 
	UNIQUE (team_name), 
	FOREIGN KEY(code_id) REFERENCES service_catalog (code_id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS assets (
	asset_id SERIAL NOT NULL, 
	asset_tag VARCHAR(60) NOT NULL, 
	asset_name VARCHAR(180) NOT NULL, 
	customer_id INTEGER, 
	project_id INTEGER, 
	type VARCHAR(80), 
	status VARCHAR(60) NOT NULL, 
	vendor VARCHAR(160), 
	model VARCHAR(160), 
	serial_no VARCHAR(160), 
	ip_address VARCHAR(80), 
	note TEXT, 
	PRIMARY KEY (asset_id), 
	FOREIGN KEY(customer_id) REFERENCES customers (customer_id) ON DELETE SET NULL, 
	FOREIGN KEY(project_id) REFERENCES projects (project_id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS contracts (
	contract_id SERIAL NOT NULL, 
	contract_code VARCHAR(60), 
	contract_name VARCHAR(180) NOT NULL, 
	customer_id INTEGER NOT NULL, 
	project_id INTEGER, 
	plan_id INTEGER, 
	start_date DATE, 
	end_date DATE, 
	scope TEXT, 
	status VARCHAR(40) NOT NULL, 
	PRIMARY KEY (contract_id), 
	FOREIGN KEY(customer_id) REFERENCES customers (customer_id) ON DELETE RESTRICT, 
	FOREIGN KEY(project_id) REFERENCES projects (project_id) ON DELETE SET NULL, 
	FOREIGN KEY(plan_id) REFERENCES plans (plan_id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS team_service_catalog (
	team_id INTEGER NOT NULL, 
	code_id VARCHAR(50) NOT NULL, 
	PRIMARY KEY (team_id, code_id), 
	FOREIGN KEY(team_id) REFERENCES teams (team_id) ON DELETE CASCADE, 
	FOREIGN KEY(code_id) REFERENCES service_catalog (code_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS users (
	user_id SERIAL NOT NULL, 
	fullname VARCHAR(160) NOT NULL, 
	email VARCHAR(254) NOT NULL, 
	password_hash VARCHAR(300) NOT NULL, 
	role VARCHAR(40) NOT NULL, 
	team_id INTEGER, 
	notes TEXT, 
	active BOOLEAN NOT NULL, 
	must_change_password BOOLEAN NOT NULL DEFAULT FALSE, 
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	PRIMARY KEY (user_id), 
	FOREIGN KEY(team_id) REFERENCES teams (team_id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS user_notification_preferences (
	user_id INTEGER NOT NULL,
	settings_json TEXT NOT NULL,
	updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
	PRIMARY KEY (user_id),
	FOREIGN KEY(user_id) REFERENCES users (user_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS audit_logs (
	audit_id SERIAL NOT NULL, 
	user_id INTEGER, 
	user_name VARCHAR(160), 
	actor_role VARCHAR(40), 
	action VARCHAR(100) NOT NULL, 
	module VARCHAR(80) NOT NULL, 
	entity_id VARCHAR(120), 
	entity_label VARCHAR(240), 
	ip_address VARCHAR(64), 
	details TEXT, 
	change_data TEXT, 
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	PRIMARY KEY (audit_id), 
	FOREIGN KEY(user_id) REFERENCES users (user_id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS tickets (
	ticket_id SERIAL NOT NULL, 
	ticket_code VARCHAR(60), 
	project_id INTEGER, 
	customer_id INTEGER NOT NULL, 
	contact_id INTEGER, 
	plan_id INTEGER, 
	asset_id INTEGER, 
	contract_id INTEGER, 
	type VARCHAR(120) NOT NULL, 
	service_code VARCHAR(50), 
	subject VARCHAR(240) NOT NULL, 
	description TEXT, 
	status VARCHAR(50) NOT NULL, 
	priority VARCHAR(30) NOT NULL, 
	assigned VARCHAR(160), 
	date DATE NOT NULL, 
	due_date DATE, 
	attachment_reference VARCHAR(500), 
	created_by_id INTEGER, 
	updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	PRIMARY KEY (ticket_id), 
	FOREIGN KEY(project_id) REFERENCES projects (project_id) ON DELETE SET NULL, 
	FOREIGN KEY(customer_id) REFERENCES customers (customer_id) ON DELETE RESTRICT, 
	FOREIGN KEY(contact_id) REFERENCES contacts (contact_id) ON DELETE SET NULL, 
	FOREIGN KEY(plan_id) REFERENCES plans (plan_id) ON DELETE SET NULL, 
	FOREIGN KEY(asset_id) REFERENCES assets (asset_id) ON DELETE SET NULL, 
	FOREIGN KEY(contract_id) REFERENCES contracts (contract_id) ON DELETE SET NULL, 
	FOREIGN KEY(service_code) REFERENCES service_catalog (code_id) ON DELETE SET NULL, 
	FOREIGN KEY(created_by_id) REFERENCES users (user_id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS ticket_replies (
	reply_id SERIAL NOT NULL, 
	ticket_id INTEGER NOT NULL, 
	user_id INTEGER NOT NULL, 
	body TEXT NOT NULL, 
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	PRIMARY KEY (reply_id), 
	FOREIGN KEY(ticket_id) REFERENCES tickets (ticket_id) ON DELETE CASCADE, 
	FOREIGN KEY(user_id) REFERENCES users (user_id) ON DELETE RESTRICT
);

CREATE INDEX IF NOT EXISTS ix_customers_customer_name ON customers (customer_name);
CREATE INDEX IF NOT EXISTS ix_customers_customer_id ON customers (customer_id);
CREATE UNIQUE INDEX IF NOT EXISTS ix_customers_email ON customers (email);
CREATE UNIQUE INDEX IF NOT EXISTS ix_plans_plan_code ON plans (plan_code);
CREATE INDEX IF NOT EXISTS ix_plans_plan_id ON plans (plan_id);
CREATE INDEX IF NOT EXISTS ix_service_catalog_name ON service_catalog (name);
CREATE INDEX IF NOT EXISTS ix_contacts_contact_id ON contacts (contact_id);
CREATE INDEX IF NOT EXISTS ix_contacts_customer_id ON contacts (customer_id);
CREATE INDEX IF NOT EXISTS ix_projects_project_id ON projects (project_id);
CREATE INDEX IF NOT EXISTS ix_projects_project_name ON projects (project_name);
CREATE UNIQUE INDEX IF NOT EXISTS ix_projects_project_code ON projects (project_code);
CREATE INDEX IF NOT EXISTS ix_projects_customer_id ON projects (customer_id);
CREATE INDEX IF NOT EXISTS ix_teams_team_id ON teams (team_id);
CREATE INDEX IF NOT EXISTS ix_assets_project_id ON assets (project_id);
CREATE INDEX IF NOT EXISTS ix_assets_customer_id ON assets (customer_id);
CREATE INDEX IF NOT EXISTS ix_assets_asset_id ON assets (asset_id);
CREATE UNIQUE INDEX IF NOT EXISTS ix_assets_asset_tag ON assets (asset_tag);
CREATE UNIQUE INDEX IF NOT EXISTS ix_contracts_contract_code ON contracts (contract_code);
CREATE INDEX IF NOT EXISTS ix_contracts_plan_id ON contracts (plan_id);
CREATE INDEX IF NOT EXISTS ix_contracts_project_id ON contracts (project_id);
CREATE INDEX IF NOT EXISTS ix_contracts_customer_id ON contracts (customer_id);
CREATE INDEX IF NOT EXISTS ix_contracts_contract_id ON contracts (contract_id);
CREATE UNIQUE INDEX IF NOT EXISTS ix_users_email ON users (email);
CREATE INDEX IF NOT EXISTS ix_users_team_id ON users (team_id);
CREATE INDEX IF NOT EXISTS ix_users_user_id ON users (user_id);
CREATE INDEX IF NOT EXISTS ix_users_role ON users (role);
CREATE INDEX IF NOT EXISTS ix_audit_logs_created_at ON audit_logs (created_at);
CREATE INDEX IF NOT EXISTS ix_tickets_service_code ON tickets (service_code);
CREATE INDEX IF NOT EXISTS ix_tickets_contract_id ON tickets (contract_id);
CREATE INDEX IF NOT EXISTS ix_tickets_asset_id ON tickets (asset_id);
CREATE UNIQUE INDEX IF NOT EXISTS ix_tickets_ticket_code ON tickets (ticket_code);
CREATE INDEX IF NOT EXISTS ix_tickets_plan_id ON tickets (plan_id);
CREATE INDEX IF NOT EXISTS ix_tickets_contact_id ON tickets (contact_id);
CREATE INDEX IF NOT EXISTS ix_tickets_status ON tickets (status);
CREATE INDEX IF NOT EXISTS ix_tickets_ticket_id ON tickets (ticket_id);
CREATE INDEX IF NOT EXISTS ix_tickets_project_id ON tickets (project_id);
CREATE INDEX IF NOT EXISTS ix_tickets_customer_id ON tickets (customer_id);
CREATE INDEX IF NOT EXISTS ix_ticket_replies_ticket_id ON ticket_replies (ticket_id);
