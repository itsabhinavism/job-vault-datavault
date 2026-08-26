-- Phase 2: Data Vault schema (lite version of the Medium article's design)
--
-- Hubs hold business keys only. Links hold relationships. Satellites
-- hold descriptive details, one row per version, never overwritten.
-- Every key is an MD5 hash of the business key - that is what lets
-- different websites join with zero manual mapping.

CREATE TABLE IF NOT EXISTS h_company (
    hk_company    TEXT PRIMARY KEY,             -- MD5 hash of company name
    company_name  TEXT NOT NULL UNIQUE,         -- business key (normalized)
    load_date     TEXT NOT NULL,                -- when we first saw this company
    record_source TEXT NOT NULL                 -- which website it came from
);

CREATE TABLE IF NOT EXISTS h_job (
    hk_job        TEXT PRIMARY KEY,             -- MD5 hash of (source, job id)
    source        TEXT NOT NULL,                -- part of business key, e.g. greenhouse_razorpay
    source_job_id TEXT NOT NULL,                -- part of business key, e.g. 4718628005
    load_date     TEXT NOT NULL,
    record_source TEXT NOT NULL,
    UNIQUE (source, source_job_id)
);

CREATE TABLE IF NOT EXISTS l_job_company (
    lhk_job_company TEXT PRIMARY KEY,           -- MD5 hash of both hub keys
    hk_job          TEXT NOT NULL REFERENCES h_job(hk_job),
    hk_company      TEXT NOT NULL REFERENCES h_company(hk_company),
    load_date       TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS s_job (
    hk_job          TEXT NOT NULL REFERENCES h_job(hk_job),
    load_date       TEXT NOT NULL,              -- when THIS version was loaded
    batch_date      TEXT NOT NULL,              -- which daily batch it belongs to
    title           TEXT NOT NULL,
    location        TEXT,
    url             TEXT,
    first_published TEXT,
    updated_at      TEXT,
    status          TEXT NOT NULL DEFAULT 'open',   -- 'open' or 'closed'
    record_source   TEXT NOT NULL,
    PRIMARY KEY (hk_job, load_date)             -- one row per version, append only
);