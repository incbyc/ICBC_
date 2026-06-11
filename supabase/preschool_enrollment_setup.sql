-- Preschool yearly enrollment (from Enrollment_Counts.xlsx)
-- Run once in Supabase SQL Editor after schema.sql.
--
-- One row per ICBC site per calendar year. The latest year is treated as
-- current enrollment on the map sidebar; earlier years sum to previous impact.

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

comment on table public.preschool_enrollment is
    'Annual preschool children enrolled per ICBC site (2022–current). Latest year = current enrollment.';

-- ---------------------------------------------------------------------------
-- CSV import staging (site_slug + year)
-- ---------------------------------------------------------------------------

create table if not exists public.preschool_enrollment_import (
    id bigserial primary key,
    site_slug text not null,
    year integer not null,
    children_count integer not null,
    teachers_count integer,
    notes text default '',
    imported_at timestamptz not null default now()
);

comment on table public.preschool_enrollment_import is
    'CSV staging keyed by site_slug. Import seed/preschool_enrollment.csv then run process_preschool_enrollment_import().';

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

-- RLS: public read for map
alter table public.preschool_enrollment enable row level security;

drop policy if exists "Public read preschool_enrollment" on public.preschool_enrollment;
create policy "Public read preschool_enrollment"
    on public.preschool_enrollment for select
    using (true);

grant select on public.preschool_enrollment to anon, authenticated;
