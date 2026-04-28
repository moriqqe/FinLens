CREATE EXTENSION IF NOT EXISTS "pgcrypto";

CREATE TABLE users (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    username          VARCHAR(30) UNIQUE NOT NULL,
    password_hash     TEXT NOT NULL,
    role              VARCHAR(10) DEFAULT 'user' CHECK (role IN ('user', 'admin')),
    api_key_encrypted TEXT,
    use_admin_key     BOOLEAN DEFAULT FALSE,
    is_active         BOOLEAN DEFAULT TRUE,
    created_at        TIMESTAMPTZ DEFAULT NOW(),
    last_login_at     TIMESTAMPTZ,
    last_login_ip     INET
);

CREATE TABLE uploads (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id             UUID REFERENCES users(id) ON DELETE CASCADE,
    filename            TEXT NOT NULL,
    file_format         VARCHAR(10) NOT NULL,
    transactions_data   TEXT NOT NULL,
    tx_count            INTEGER NOT NULL,
    date_from           DATE,
    date_to             DATE,
    total_expenses      NUMERIC(12,2),
    total_income        NUMERIC(12,2),
    ai_result           TEXT,
    created_at          TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_uploads_user_id ON uploads(user_id);

CREATE TABLE audit_logs (
    id          BIGSERIAL PRIMARY KEY,
    user_id     UUID REFERENCES users(id) ON DELETE SET NULL,
    action      VARCHAR(50) NOT NULL,
    ip          INET,
    user_agent  TEXT,
    details     JSONB,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_audit_logs_user_id ON audit_logs(user_id);
CREATE INDEX idx_audit_logs_created_at ON audit_logs(created_at DESC);

CREATE TABLE settings (
    key     VARCHAR(50) PRIMARY KEY,
    value   TEXT NOT NULL
);
INSERT INTO settings VALUES
    ('registration_open', 'true'),
    ('admin_key_encrypted', '');
