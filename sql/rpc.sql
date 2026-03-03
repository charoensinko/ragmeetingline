create or replace function match_meetings(
  query_embedding vector(384),
  match_count int default 5,
  date_filter date default null,
  dept_filter text default null
)
returns table (
  id uuid,
  row_id text,
  meeting_date date,
  topic text,
  departments text,
  start_time text,
  zoom_link text,
  notes text,
  content text,
  metadata jsonb,
  score float
)
language sql stable
as $$
  select
    dc.id,
    dc.row_id,
    dc.meeting_date,
    dc.topic,
    dc.departments,
    dc.start_time,
    dc.zoom_link,
    dc.notes,
    dc.content,
    dc.metadata,
    1 - (dc.embedding <=> query_embedding) as score
  from doc_chunks dc
  where
    (date_filter is null or dc.meeting_date = date_filter)
    and (
      dept_filter is null
      or dept_filter = any(dc.departments_arr)                 -- ✅ match แบบแยกฝ่าย
      or dc.departments ilike ('%' || dept_filter || '%')      -- fallback
      or dc.content ilike ('%' || dept_filter || '%')          -- fallback
    )
  order by dc.embedding <=> query_embedding
  limit match_count;
$$;