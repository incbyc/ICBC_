-- ICBC Eswatini map – normalized Supabase schema
-- Run this once in Supabase: SQL Editor → New query → Paste → Run
--
-- Design goals:
-- 1. Keep `icbc_sites` focused on core site profile data only.
-- 2. Store programme and historical data in dedicated tables keyed by `site_id`.
-- 3. Make CSV imports easy by providing staging tables that use `site_slug`.

create extension if not exists pgcrypto;

-- ---------------------------------------------------------------------------
-- Helper functions
-- ---------------------------------------------------------------------------

create or replace function public.set_row_updated_at()
returns trigger
language plpgsql
as $$
begin
    new.updated_at = now();
    return new;
end;
$$;

create or replace function public.normalise_site_slug(raw text)
returns text
language sql
immutable
as $$
    select btrim(
        regexp_replace(lower(coalesce(raw, '')), '[^a-z0-9]+', '-', 'g'),
        '-'
    );
$$;

-- ---------------------------------------------------------------------------
-- Core site tables
-- ---------------------------------------------------------------------------

create table if not exists public.icbc_sites (
    id uuid primary key default gen_random_uuid(),
    slug text not null unique,
    name text not null,
    region text default '',
    year_constructed text default '',
    water_source text default '',
    projects text default '',
    about text default '',
    site_link text default '',
    video_url text default '',
    photo_path text default '',
    cover_image_url text default '',
    latitude double precision,
    longitude double precision,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

drop trigger if exists trg_icbc_sites_updated_at on public.icbc_sites;
create trigger trg_icbc_sites_updated_at
before update on public.icbc_sites
for each row
execute function public.set_row_updated_at();

create table if not exists public.staff (
    id uuid primary key default gen_random_uuid(),
    site_id uuid not null references public.icbc_sites (id) on delete cascade,
    full_name text not null,
    description text default '',
    role text not null,
    year_joined integer,
    photo_url text default '',
    spouse_name text default '',
    children_count integer,
    sort_order integer default 0,
    created_at timestamptz not null default now(),
    constraint staff_role_check check (
        role in ('Pastor', 'Teacher', 'Compassionate Care', 'Other')
    ),
    constraint staff_unique_person_per_role unique (site_id, full_name, role)
);

create index if not exists staff_site_id_idx on public.staff (site_id);
create index if not exists staff_role_idx on public.staff (site_id, role);

comment on column public.staff.photo_url is
    'Full GitHub-hosted URL for the staff member portrait.';

create unique index if not exists staff_one_pastor_per_site
    on public.staff (site_id)
    where role = 'Pastor';

create table if not exists public.bubele_care_sites (
    id uuid primary key default gen_random_uuid(),
    site_name text not null,
    family_code text not null unique,
    region text default '',
    latitude double precision,
    longitude double precision,
    created_at timestamptz not null default now()
);

create table if not exists public.site_updates (
    id uuid primary key default gen_random_uuid(),
    site_id uuid not null references public.icbc_sites (id) on delete cascade,
    title text not null,
    body text default '',
    image_url text default '',
    created_at timestamptz not null default now()
);

create table if not exists public.site_images (
    id uuid primary key default gen_random_uuid(),
    site_id uuid not null references public.icbc_sites (id) on delete cascade,
    image_url text not null,
    caption text default '',
    is_featured boolean default false,
    sort_order integer default 0
);

-- ---------------------------------------------------------------------------
-- Historical programme tables
-- ---------------------------------------------------------------------------

create table if not exists public.preschool_snapshots (
    id uuid primary key default gen_random_uuid(),
    site_id uuid not null references public.icbc_sites (id) on delete cascade,
    children_count integer not null,
    snapshot_date date not null,
    year integer not null,
    teachers_count integer,
    children_impacted_since_inception integer,
    notes text default '',
    created_at timestamptz not null default now(),
    unique (site_id, snapshot_date)
);

create index if not exists preschool_snapshots_site_id_idx
    on public.preschool_snapshots (site_id, snapshot_date desc);

create table if not exists public.preschool_enrollment (
    id uuid primary key default gen_random_uuid(),
    site_id uuid not null references public.icbc_sites (id) on delete cascade,
    year integer not null,
    children_count integer not null default 0,
    teachers_count integer,
    notes text default '',
    created_at timestamptz not null default now(),
    unique (site_id, year)
);

create index if not exists preschool_enrollment_site_year_idx
    on public.preschool_enrollment (site_id, year desc);

create table if not exists public.ploughing_records (
    id uuid primary key default gen_random_uuid(),
    site_id uuid not null references public.icbc_sites (id) on delete cascade,
    year integer not null,
    hours_ploughed double precision default 0,
    families_impacted integer default 0,
    hectares_ploughed double precision default 0,
    notes text default '',
    created_at timestamptz not null default now(),
    unique (site_id, year)
);

create table if not exists public.maize_buyback_records (
    id uuid primary key default gen_random_uuid(),
    site_id uuid not null references public.icbc_sites (id) on delete cascade,
    year integer not null,
    farmers_impacted integer default 0,
    kilograms_bought double precision default 0,
    meals_made integer default 0,
    notes text default '',
    created_at timestamptz not null default now(),
    unique (site_id, year)
);

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

create table if not exists public.weekly_stats (
    id uuid primary key default gen_random_uuid(),
    site_id uuid not null references public.icbc_sites (id) on delete cascade,
    stat_date date not null,
    source_file text default '',
    sheet_name text default '',
    total_attendance integer default 0,
    men integer default 0,
    women integer default 0,
    youth integer default 0,
    children integer default 0,
    salvations integer default 0,
    baptisms integer default 0,
    home_visits integer default 0,
    meals_food_packs integer default 0,
    preschool_attendance integer default 0,
    created_at timestamptz not null default now(),
    unique (site_id, stat_date)
);

create index if not exists weekly_stats_site_date_idx
    on public.weekly_stats (site_id, stat_date desc);

-- ---------------------------------------------------------------------------
-- Import staging tables
-- Import CSVs into these tables when your files use `site_slug`.
-- Then run the corresponding process_* function below.
-- ---------------------------------------------------------------------------

create table if not exists public.staff_import (
    id bigserial primary key,
    site_slug text not null,
    full_name text not null,
    description text default '',
    role text not null,
    year_joined integer,
    photo_url text default '',
    sort_order integer default 0,
    imported_at timestamptz not null default now()
);

create table if not exists public.preschool_snapshots_import (
    id bigserial primary key,
    site_slug text not null,
    children_count integer not null,
    snapshot_date text not null,
    year integer not null,
    teachers_count integer,
    children_impacted_since_inception integer,
    notes text default '',
    imported_at timestamptz not null default now()
);

create table if not exists public.preschool_enrollment_import (
    id bigserial primary key,
    site_slug text not null,
    year integer not null,
    children_count integer not null,
    teachers_count integer,
    notes text default '',
    imported_at timestamptz not null default now()
);

create table if not exists public.ploughing_records_import (
    id bigserial primary key,
    site_slug text not null,
    year integer not null,
    hours_ploughed double precision default 0,
    families_impacted integer default 0,
    hectares_ploughed double precision default 0,
    notes text default '',
    imported_at timestamptz not null default now()
);

create table if not exists public.maize_buyback_records_import (
    id bigserial primary key,
    site_slug text not null,
    year integer not null,
    farmers_impacted integer default 0,
    kilograms_bought double precision default 0,
    meals_made integer default 0,
    notes text default '',
    imported_at timestamptz not null default now()
);

comment on table public.staff_import is
    'CSV staging table keyed by site_slug. Run process_staff_import() after import.';

comment on table public.preschool_snapshots_import is
    'CSV staging table keyed by site_slug. Run process_preschool_snapshots_import() after import.';

comment on table public.preschool_enrollment_import is
    'CSV staging keyed by site_slug + year. Run process_preschool_enrollment_import() after import.';

comment on table public.ploughing_records_import is
    'CSV staging table keyed by site_slug. Run process_ploughing_records_import() after import.';

comment on table public.maize_buyback_records_import is
    'CSV staging table keyed by site_slug. Run process_maize_buyback_records_import() after import.';

-- ---------------------------------------------------------------------------
-- Import processors
-- ---------------------------------------------------------------------------

create or replace function public.process_staff_import()
returns table (
    inserted integer,
    updated integer,
    unmatched_site_slugs text[]
)
language plpgsql
as $$
declare
    v_inserted integer := 0;
    v_updated integer := 0;
    v_unmatched text[];
    v_site_id uuid;
    v_exists boolean;
    r record;
begin
    for r in
        select *
        from public.staff_import
        order by id
    loop
        select s.id into v_site_id
        from public.icbc_sites s
        where s.slug = public.normalise_site_slug(r.site_slug)
        limit 1;

        if v_site_id is null then
            v_unmatched := array_append(v_unmatched, r.site_slug);
            continue;
        end if;

        select exists (
            select 1
            from public.staff st
            where st.site_id = v_site_id
              and st.full_name = trim(r.full_name)
              and st.role = r.role
        ) into v_exists;

        insert into public.staff (
            site_id,
            full_name,
            description,
            role,
            year_joined,
            photo_url,
            sort_order
        )
        values (
            v_site_id,
            trim(r.full_name),
            coalesce(r.description, ''),
            r.role,
            r.year_joined,
            coalesce(r.photo_url, ''),
            coalesce(r.sort_order, 0)
        )
        on conflict (site_id, full_name, role) do update set
            description = excluded.description,
            year_joined = excluded.year_joined,
            photo_url = excluded.photo_url,
            sort_order = excluded.sort_order;

        if v_exists then
            v_updated := v_updated + 1;
        else
            v_inserted := v_inserted + 1;
        end if;
    end loop;

    return query select v_inserted, v_updated, v_unmatched;
end;
$$;

create or replace function public.process_preschool_snapshots_import()
returns table (
    inserted integer,
    updated integer,
    skipped_bad_date integer,
    unmatched_site_slugs text[]
)
language plpgsql
as $$
declare
    v_inserted integer := 0;
    v_updated integer := 0;
    v_skipped integer := 0;
    v_unmatched text[];
    v_site_id uuid;
    v_exists boolean;
    v_snapshot_date date;
    r record;
begin
    for r in
        select *
        from public.preschool_snapshots_import
        order by id
    loop
        select s.id into v_site_id
        from public.icbc_sites s
        where s.slug = public.normalise_site_slug(r.site_slug)
        limit 1;

        if v_site_id is null then
            v_unmatched := array_append(v_unmatched, r.site_slug);
            continue;
        end if;

        begin
            v_snapshot_date := r.snapshot_date::date;
        exception
            when others then
                v_skipped := v_skipped + 1;
                continue;
        end;

        select exists (
            select 1
            from public.preschool_snapshots ps
            where ps.site_id = v_site_id
              and ps.snapshot_date = v_snapshot_date
        ) into v_exists;

        insert into public.preschool_snapshots (
            site_id,
            children_count,
            snapshot_date,
            year,
            teachers_count,
            children_impacted_since_inception,
            notes
        )
        values (
            v_site_id,
            r.children_count,
            v_snapshot_date,
            r.year,
            r.teachers_count,
            r.children_impacted_since_inception,
            coalesce(r.notes, '')
        )
        on conflict (site_id, snapshot_date) do update set
            children_count = excluded.children_count,
            year = excluded.year,
            teachers_count = excluded.teachers_count,
            children_impacted_since_inception = excluded.children_impacted_since_inception,
            notes = excluded.notes;

        if v_exists then
            v_updated := v_updated + 1;
        else
            v_inserted := v_inserted + 1;
        end if;
    end loop;

    return query select v_inserted, v_updated, v_skipped, v_unmatched;
end;
$$;

create or replace function public.process_preschool_enrollment_import()
returns table (
    inserted integer,
    updated integer,
    unmatched_site_slugs text[]
)
language plpgsql
as $$
declare
    v_inserted integer := 0;
    v_updated integer := 0;
    v_unmatched text[];
    v_site_id uuid;
    v_exists boolean;
    r record;
begin
    for r in
        select *
        from public.preschool_enrollment_import
        order by id
    loop
        select s.id into v_site_id
        from public.icbc_sites s
        where s.slug = public.normalise_site_slug(r.site_slug)
        limit 1;

        if v_site_id is null then
            v_unmatched := array_append(v_unmatched, r.site_slug);
            continue;
        end if;

        select exists (
            select 1
            from public.preschool_enrollment pe
            where pe.site_id = v_site_id
              and pe.year = r.year
        ) into v_exists;

        insert into public.preschool_enrollment (
            site_id,
            year,
            children_count,
            teachers_count,
            notes
        )
        values (
            v_site_id,
            r.year,
            coalesce(r.children_count, 0),
            r.teachers_count,
            coalesce(r.notes, '')
        )
        on conflict (site_id, year) do update
        set
            children_count = excluded.children_count,
            teachers_count = excluded.teachers_count,
            notes = excluded.notes;

        if v_exists then
            v_updated := v_updated + 1;
        else
            v_inserted := v_inserted + 1;
        end if;
    end loop;

    return query select v_inserted, v_updated, v_unmatched;
end;
$$;

create or replace function public.process_ploughing_records_import()
returns table (
    inserted integer,
    updated integer,
    unmatched_site_slugs text[]
)
language plpgsql
as $$
declare
    v_inserted integer := 0;
    v_updated integer := 0;
    v_unmatched text[];
    v_site_id uuid;
    v_exists boolean;
    r record;
begin
    for r in
        select *
        from public.ploughing_records_import
        order by id
    loop
        select s.id into v_site_id
        from public.icbc_sites s
        where s.slug = public.normalise_site_slug(r.site_slug)
        limit 1;

        if v_site_id is null then
            v_unmatched := array_append(v_unmatched, r.site_slug);
            continue;
        end if;

        select exists (
            select 1
            from public.ploughing_records pr
            where pr.site_id = v_site_id
              and pr.year = r.year
        ) into v_exists;

        insert into public.ploughing_records (
            site_id,
            year,
            hours_ploughed,
            families_impacted,
            hectares_ploughed,
            notes
        )
        values (
            v_site_id,
            r.year,
            coalesce(r.hours_ploughed, 0),
            coalesce(r.families_impacted, 0),
            coalesce(r.hectares_ploughed, 0),
            coalesce(r.notes, '')
        )
        on conflict (site_id, year) do update set
            hours_ploughed = excluded.hours_ploughed,
            families_impacted = excluded.families_impacted,
            hectares_ploughed = excluded.hectares_ploughed,
            notes = excluded.notes;

        if v_exists then
            v_updated := v_updated + 1;
        else
            v_inserted := v_inserted + 1;
        end if;
    end loop;

    return query select v_inserted, v_updated, v_unmatched;
end;
$$;

create or replace function public.process_maize_buyback_records_import()
returns table (
    inserted integer,
    updated integer,
    unmatched_site_slugs text[]
)
language plpgsql
as $$
declare
    v_inserted integer := 0;
    v_updated integer := 0;
    v_unmatched text[];
    v_site_id uuid;
    v_exists boolean;
    r record;
begin
    for r in
        select *
        from public.maize_buyback_records_import
        order by id
    loop
        select s.id into v_site_id
        from public.icbc_sites s
        where s.slug = public.normalise_site_slug(r.site_slug)
        limit 1;

        if v_site_id is null then
            v_unmatched := array_append(v_unmatched, r.site_slug);
            continue;
        end if;

        select exists (
            select 1
            from public.maize_buyback_records mr
            where mr.site_id = v_site_id
              and mr.year = r.year
        ) into v_exists;

        insert into public.maize_buyback_records (
            site_id,
            year,
            farmers_impacted,
            kilograms_bought,
            meals_made,
            notes
        )
        values (
            v_site_id,
            r.year,
            coalesce(r.farmers_impacted, 0),
            coalesce(r.kilograms_bought, 0),
            coalesce(r.meals_made, 0),
            coalesce(r.notes, '')
        )
        on conflict (site_id, year) do update set
            farmers_impacted = excluded.farmers_impacted,
            kilograms_bought = excluded.kilograms_bought,
            meals_made = excluded.meals_made,
            notes = excluded.notes;

        if v_exists then
            v_updated := v_updated + 1;
        else
            v_inserted := v_inserted + 1;
        end if;
    end loop;

    return query select v_inserted, v_updated, v_unmatched;
end;
$$;

create or replace function public.process_all_site_imports()
returns jsonb
language plpgsql
as $$
declare
    v_staff record;
    v_preschool record;
    v_ploughing record;
    v_maize record;
begin
    select * into v_staff from public.process_staff_import();
    select * into v_preschool from public.process_preschool_snapshots_import();
    select * into v_ploughing from public.process_ploughing_records_import();
    select * into v_maize from public.process_maize_buyback_records_import();

    return jsonb_build_object(
        'staff', jsonb_build_object(
            'inserted', coalesce(v_staff.inserted, 0),
            'updated', coalesce(v_staff.updated, 0),
            'unmatched_site_slugs', coalesce(to_jsonb(v_staff.unmatched_site_slugs), '[]'::jsonb)
        ),
        'preschool_snapshots', jsonb_build_object(
            'inserted', coalesce(v_preschool.inserted, 0),
            'updated', coalesce(v_preschool.updated, 0),
            'skipped_bad_date', coalesce(v_preschool.skipped_bad_date, 0),
            'unmatched_site_slugs', coalesce(to_jsonb(v_preschool.unmatched_site_slugs), '[]'::jsonb)
        ),
        'ploughing_records', jsonb_build_object(
            'inserted', coalesce(v_ploughing.inserted, 0),
            'updated', coalesce(v_ploughing.updated, 0),
            'unmatched_site_slugs', coalesce(to_jsonb(v_ploughing.unmatched_site_slugs), '[]'::jsonb)
        ),
        'maize_buyback_records', jsonb_build_object(
            'inserted', coalesce(v_maize.inserted, 0),
            'updated', coalesce(v_maize.updated, 0),
            'unmatched_site_slugs', coalesce(to_jsonb(v_maize.unmatched_site_slugs), '[]'::jsonb)
        )
    );
end;
$$;

-- ---------------------------------------------------------------------------
-- Views for the frontend
-- ---------------------------------------------------------------------------

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
    st.spouse_name,
    st.children_count,
    st.sort_order
from public.staff st
join public.icbc_sites s on s.id = st.site_id
order by s.slug, st.role, st.sort_order, st.full_name;

-- Weekly stat rollups for the map sidebar (run weekly_stats_sidebar_view.sql
-- for the full definition if you set up stats after the initial schema import).
create or replace view public.icbc_site_stats_summary as
select
    s.id as site_id,
    s.slug,
    s.name as site_name,
    count(w.id) filter (where w.total_attendance > 0)::integer as sundays_recorded,
    case
        when count(w.id) > 0
        then round(avg(w.total_attendance)::numeric, 1)
    end as avg_attendance,
    coalesce(sum(w.salvations), 0)::integer as total_salvations,
    coalesce(sum(w.baptisms), 0)::integer as total_baptisms,
    coalesce(sum(w.home_visits), 0)::integer as total_home_visits,
    (coalesce(sum(w.salvations), 0) > 10) as show_salvations,
    (coalesce(sum(w.baptisms), 0) > 10) as show_baptisms,
    (coalesce(sum(w.home_visits), 0) > 50) as show_home_visits,
    (
        jsonb_build_array(
            jsonb_build_object(
                'key', 'avg_attendance',
                'title', 'Avg attendance',
                'value', round(coalesce(avg(w.total_attendance), 0)::numeric, 1),
                'format', 'decimal'
            )
        )
        || case
            when coalesce(sum(w.salvations), 0) > 10 then
                jsonb_build_array(
                    jsonb_build_object(
                        'key', 'salvations',
                        'title', 'Total salvations',
                        'value', sum(w.salvations)::integer,
                        'format', 'integer'
                    )
                )
            else '[]'::jsonb
        end
        || case
            when coalesce(sum(w.baptisms), 0) > 10 then
                jsonb_build_array(
                    jsonb_build_object(
                        'key', 'baptisms',
                        'title', 'Total baptisms',
                        'value', sum(w.baptisms)::integer,
                        'format', 'integer'
                    )
                )
            else '[]'::jsonb
        end
        || case
            when coalesce(sum(w.home_visits), 0) > 50 then
                jsonb_build_array(
                    jsonb_build_object(
                        'key', 'home_visits',
                        'title', 'Total home visits',
                        'value', sum(w.home_visits)::integer,
                        'format', 'integer'
                    )
                )
            else '[]'::jsonb
        end
    ) as sidebar_metrics
from public.icbc_sites s
left join public.weekly_stats w on w.site_id = s.id
group by s.id, s.slug, s.name;

grant select on public.icbc_site_sidebar to anon, authenticated;
grant select on public.icbc_site_staff to anon, authenticated;
grant select on public.icbc_site_stats_summary to anon, authenticated;
grant select on public.site_rainfall_monthly to anon, authenticated;

-- ---------------------------------------------------------------------------
-- Row Level Security (public read for the static site)
-- Staging import tables are intentionally left out of public policies.
-- ---------------------------------------------------------------------------

alter table public.icbc_sites enable row level security;
alter table public.staff enable row level security;
alter table public.bubele_care_sites enable row level security;
alter table public.site_updates enable row level security;
alter table public.site_images enable row level security;
alter table public.preschool_snapshots enable row level security;
alter table public.preschool_enrollment enable row level security;
alter table public.ploughing_records enable row level security;
alter table public.maize_buyback_records enable row level security;
alter table public.weekly_stats enable row level security;

drop policy if exists "Public read icbc_sites" on public.icbc_sites;
drop policy if exists "Public read staff" on public.staff;
drop policy if exists "Public read bubele_care_sites" on public.bubele_care_sites;
drop policy if exists "Public read site_updates" on public.site_updates;
drop policy if exists "Public read site_images" on public.site_images;
drop policy if exists "Public read preschool_snapshots" on public.preschool_snapshots;
drop policy if exists "Public read preschool_enrollment" on public.preschool_enrollment;
drop policy if exists "Public read ploughing_records" on public.ploughing_records;
drop policy if exists "Public read maize_buyback_records" on public.maize_buyback_records;
drop policy if exists "Public read weekly_stats" on public.weekly_stats;

create policy "Public read icbc_sites"
    on public.icbc_sites for select
    using (true);

create policy "Public read staff"
    on public.staff for select
    using (true);

create policy "Public read bubele_care_sites"
    on public.bubele_care_sites for select
    using (true);

create policy "Public read site_updates"
    on public.site_updates for select
    using (true);

create policy "Public read site_images"
    on public.site_images for select
    using (true);

create policy "Public read preschool_snapshots"
    on public.preschool_snapshots for select
    using (true);

create policy "Public read preschool_enrollment"
    on public.preschool_enrollment for select
    using (true);

create policy "Public read ploughing_records"
    on public.ploughing_records for select
    using (true);

create policy "Public read maize_buyback_records"
    on public.maize_buyback_records for select
    using (true);

create policy "Public read weekly_stats"
    on public.weekly_stats for select
    using (true);

-- Authenticated users (Supabase dashboard / service role) can manage writes.
-- Later: add explicit INSERT/UPDATE/DELETE policies for an admin role if needed.
