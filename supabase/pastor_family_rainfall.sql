-- Pastor family fields + monthly climate chart data for the map sidebar.
-- Run once in Supabase SQL Editor after pulling this update.

alter table public.staff
    add column if not exists spouse_name text default '',
    add column if not exists children_count integer;

comment on column public.staff.spouse_name is
    'Pastor spouse / wife name (displayed on the map sidebar).';
comment on column public.staff.children_count is
    'Number of pastor children (count only — names are not stored).';

create table if not exists public.site_rainfall_monthly (
    id uuid primary key default gen_random_uuid(),
    site_id uuid not null references public.icbc_sites (id) on delete cascade,
    month integer not null check (month between 1 and 12),
    month_label text default '',
    rainfall_mm numeric(8, 1) not null default 0,
    temperature_c numeric(5, 1),
    unique (site_id, month)
);

create index if not exists site_rainfall_monthly_site_id_idx
    on public.site_rainfall_monthly (site_id, month);

grant select on public.site_rainfall_monthly to anon, authenticated;

-- PostgreSQL cannot add columns to an existing view with CREATE OR REPLACE
-- when new columns are inserted before the last column — drop first.
drop view if exists public.icbc_site_rainfall;
drop view if exists public.icbc_site_staff;
drop view if exists public.icbc_site_sidebar;

create view public.icbc_site_staff as
select
    s.slug as site_slug,
    s.name as site_name,
    st.id,
    st.full_name,
    st.description,
    st.role,
    st.year_joined,
    st.photo_url,
    st.spouse_name,
    st.children_count,
    st.sort_order
from public.staff st
join public.icbc_sites s on s.id = st.site_id
order by s.slug, st.role, st.sort_order, st.full_name;

create view public.icbc_site_sidebar as
select
    s.id,
    s.slug,
    s.name,
    s.region,
    s.video_url,
    s.photo_path,
    s.cover_image_url,
    p.full_name as pastor_name,
    p.description as pastor_description,
    p.photo_url as pastor_photo_url,
    p.spouse_name as pastor_spouse_name,
    p.children_count as pastor_children_count,
    p.year_joined as pastor_year_joined,
    (select count(*)::integer from public.staff st where st.site_id = s.id) as staff_count
from public.icbc_sites s
left join lateral (
    select st.*
    from public.staff st
    where st.site_id = s.id and st.role = 'Pastor'
    order by st.sort_order, st.created_at
    limit 1
) p on true;

create view public.icbc_site_rainfall as
select
    s.slug as site_slug,
    r.month,
    r.month_label,
    r.rainfall_mm,
    r.temperature_c
from public.site_rainfall_monthly r
join public.icbc_sites s on s.id = r.site_id
order by s.slug, r.month;

grant select on public.icbc_site_rainfall to anon, authenticated;
grant select on public.icbc_site_staff to anon, authenticated;
grant select on public.icbc_site_sidebar to anon, authenticated;
