CREATE TABLE IF NOT EXISTS users (
    id BIGSERIAL PRIMARY KEY,
    username TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS tokens (
    token_hash TEXT PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_used_at TIMESTAMPTZ
);
CREATE TABLE IF NOT EXISTS realms (
    id BIGSERIAL PRIMARY KEY,
    name TEXT NOT NULL UNIQUE
);
CREATE TABLE IF NOT EXISTS scans (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    realm_id BIGINT NOT NULL REFERENCES realms(id),
    taken_at TIMESTAMPTZ NOT NULL,
    uploaded_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    item_count INTEGER NOT NULL,
    UNIQUE (user_id, realm_id, taken_at)
);
CREATE TABLE IF NOT EXISTS prices (
    scan_id BIGINT NOT NULL REFERENCES scans(id) ON DELETE CASCADE,
    item_id BIGINT NOT NULL,
    name TEXT,
    min_price BIGINT NOT NULL,
    available INTEGER NOT NULL DEFAULT 0,
    day_high BIGINT,
    PRIMARY KEY (scan_id, item_id)
);
CREATE INDEX IF NOT EXISTS prices_item ON prices (item_id);
CREATE TABLE IF NOT EXISTS characters (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    realm_id BIGINT NOT NULL REFERENCES realms(id),
    name TEXT NOT NULL,
    published BOOLEAN NOT NULL DEFAULT FALSE,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (user_id, realm_id, name)
);
CREATE TABLE IF NOT EXISTS character_skills (
    character_id BIGINT NOT NULL REFERENCES characters(id) ON DELETE CASCADE,
    profession TEXT NOT NULL,
    rank INTEGER NOT NULL,
    max_rank INTEGER NOT NULL,
    PRIMARY KEY (character_id, profession)
);
CREATE TABLE IF NOT EXISTS character_recipes (
    character_id BIGINT NOT NULL REFERENCES characters(id) ON DELETE CASCADE,
    item_id BIGINT NOT NULL,
    name TEXT,
    min_made INTEGER NOT NULL DEFAULT 1,
    max_made INTEGER NOT NULL DEFAULT 1,
    difficulty TEXT,
    profession TEXT NOT NULL,
    reagents JSONB NOT NULL,
    PRIMARY KEY (character_id, item_id)
);
