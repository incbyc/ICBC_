-- Deprecated helper kept for backward compatibility.
-- New projects: use `schema.sql` only. It already includes the unified `staff`
-- table, views, and public read policy.

create table if not exists public.staff (
    id uuid primary key default gen_random_uuid(),
    site_id uuid not null references public.icbc_sites (id) on delete cascade,
    full_name text not null,
    description text default '',
    role text not null,
    year_joined integer,
    photo_url text default '',
    sort_order integer default 0,
    created_at timestamptz not null default now(),
    constraint staff_role_check check (
        role in ('Pastor', 'Teacher', 'Compassionate Care', 'Other')
    )
);

create index if not exists staff_site_id_idx on public.staff (site_id);
create index if not exists staff_role_idx on public.staff (site_id, role);

-- One lead pastor per site (optional; remove if you need co-pastors)
create unique index if not exists staff_one_pastor_per_site
    on public.staff (site_id)
    where role = 'Pastor';

comment on table public.staff is
    'All ICBC staff: pastor, teachers, compassionate care, and other roles.';

comment on column public.staff.description is
    'Brief bio shown on the map sidebar (pastor) and full profile page.';

comment on column public.staff.year_joined is
    'Calendar year the person joined this ICBC (e.g. 2018).';

comment on column public.staff.photo_url is
    'Full GitHub-hosted URL for the staff member portrait.';

-- Map sidebar: site + lead pastor + total staff count
create or replace view public.icbc_site_sidebar as
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
    p.year_joined as pastor_year_joined,
    (
        select count(*)::integer
        from public.staff st
        where st.site_id = s.id
    ) as staff_count
from public.icbc_sites s
left join lateral (
    select st.*
    from public.staff st
    where st.site_id = s.id and st.role = 'Pastor'
    order by st.sort_order, st.created_at
    limit 1
) p on true;

-- Full profile: all staff for a site (ordered)
create or replace view public.icbc_site_staff as
select
    s.slug as site_slug,
    s.name as site_name,
    st.id,
    st.full_name,
    st.description,
    st.role,
    st.year_joined,
    st.photo_url,
    st.sort_order
from public.staff st
join public.icbc_sites s on s.id = st.site_id
order by s.slug, st.role, st.sort_order, st.full_name;

alter table public.staff enable row level security;

create policy "Public read staff"
    on public.staff for select
    using (true);
