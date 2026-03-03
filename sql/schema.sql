-- Enable pgvector (Supabase Postgres)
create extension if not exists vector;

-- Documents (one sheet = one source)
create table if not exists documents (
    id uuid primary key default gen_random_uuid (),
    source text not null, -- e.g., 'gsheet'
    title text not null,
    external_id text not null, -- e.g., gsheet_id
    updated_at timestamptz not null default now(),
    unique (source, external_id)
);

-- Each row in Google Sheet becomes one chunk
-- Embedding dim for intfloat/multilingual-e5-small = 384
create table if not exists doc_chunks (
    id uuid primary key default gen_random_uuid (),
    document_id uuid references documents (id) on delete cascade,
    row_id text not null, -- sheet row number (string)
    meeting_date date,
    topic text,
    departments text, -- raw string from sheet
    departments_arr text [] default '{}'::text [], -- normalized dept list ✅
    start_time text, -- store as 'HH:MM' if possible
    zoom_link text,
    notes text,
    content text not null, -- concatenated text used for embedding
    metadata jsonb not null default '{}'::jsonb,
    embedding vector (384) not null
);

-- Vector index
create index if not exists idx_doc_chunks_embedding on doc_chunks using ivfflat (embedding vector_cosine_ops)
with (lists = 100);

-- Helpful filters
create index if not exists idx_doc_chunks_meeting_date on doc_chunks (meeting_date);

create index if not exists idx_doc_chunks_departments_arr on doc_chunks using gin (departments_arr);