-- Staff portrait storage for Streamlit Seed Admin uploads.
-- Run once in Supabase SQL Editor (Dashboard → SQL → New query).

insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values (
    'staff-photos',
    'staff-photos',
    true,
    5242880,
    array['image/jpeg', 'image/png', 'image/webp']
)
on conflict (id) do update set
    public = excluded.public,
    file_size_limit = excluded.file_size_limit,
    allowed_mime_types = excluded.allowed_mime_types;

-- Public read (map + icbc.html load photos via anon key / direct URL).
drop policy if exists "Staff photos public read" on storage.objects;
create policy "Staff photos public read"
    on storage.objects
    for select
    to public
    using (bucket_id = 'staff-photos');
