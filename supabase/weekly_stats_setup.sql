-- Weekly stats import (matches spreadsheet columns)
-- Run AFTER schema.sql and AFTER icbc_sites are loaded.
--
-- Spreadsheet columns (Weekly Data sheet):
--   Church | Date | Total Attendance | Men | Women | Youth | Children |
--   Salvations | Baptisms | Home Visits | Meals / Food Packs | Preschool Attendance

-- ---------------------------------------------------------------------------
-- Staging table: paste or CSV-import your spreadsheet here
-- ---------------------------------------------------------------------------

create table if not exists public.weekly_stats_import (
    id bigserial primary key,
    church text not null,
    date text not null,
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
    imported_at timestamptz not null default now()
);

-- Add columns when upgrading an older project
alter table public.weekly_stats_import add column if not exists home_visits integer default 0;
alter table public.weekly_stats_import add column if not exists meals_food_packs integer default 0;
alter table public.weekly_stats_import add column if not exists preschool_attendance integer default 0;

comment on table public.weekly_stats_import is
    'Staging area for weekly stats CSV. Run process_weekly_stats_import() after import.';

-- ---------------------------------------------------------------------------
-- Church name matching (same rules as Django admin import)
-- ---------------------------------------------------------------------------

create or replace function public.normalise_church_name(raw text)
returns text
language sql
immutable
as $$
    select trim(
        regexp_replace(
            regexp_replace(
                lower(split_part(coalesce(raw, ''), '(', 1)),
                '\s+clc\s+church\s*$', '', 'g'
            ),
            '\s+clc\s*$', '', 'g'
        )
    );
$$;

-- ---------------------------------------------------------------------------
-- Process staging rows into weekly_stats
-- ---------------------------------------------------------------------------

create or replace function public.process_weekly_stats_import()
returns table (
    inserted integer,
    updated integer,
    skipped_bad_date integer,
    unmatched_churches text[]
)
language plpgsql
as $$
declare
    v_inserted integer := 0;
    v_updated integer := 0;
    v_skipped integer := 0;
    v_unmatched text[];
    r record;
    v_site_id uuid;
    v_stat_date date;
    v_exists boolean;
begin
    for r in
        select *
        from public.weekly_stats_import
        order by id
    loop
        select s.id into v_site_id
        from public.icbc_sites s
        where public.normalise_church_name(s.name) = public.normalise_church_name(r.church)
        limit 1;

        if v_site_id is null then
            v_unmatched := array_append(v_unmatched, r.church);
            continue;
        end if;

        begin
            v_stat_date := r.date::date;
        exception
            when others then
                v_skipped := v_skipped + 1;
                continue;
        end;

        select exists (
            select 1
            from public.weekly_stats w
            where w.site_id = v_site_id and w.stat_date = v_stat_date
        ) into v_exists;

        insert into public.weekly_stats (
            site_id,
            stat_date,
            total_attendance,
            men,
            women,
            youth,
            children,
            salvations,
            baptisms,
            home_visits,
            meals_food_packs,
            preschool_attendance
        )
        values (
            v_site_id,
            v_stat_date,
            coalesce(r.total_attendance, 0),
            coalesce(r.men, 0),
            coalesce(r.women, 0),
            coalesce(r.youth, 0),
            coalesce(r.children, 0),
            coalesce(r.salvations, 0),
            coalesce(r.baptisms, 0),
            coalesce(r.home_visits, 0),
            coalesce(r.meals_food_packs, 0),
            coalesce(r.preschool_attendance, 0)
        )
        on conflict (site_id, stat_date) do update set
            total_attendance = excluded.total_attendance,
            men = excluded.men,
            women = excluded.women,
            youth = excluded.youth,
            children = excluded.children,
            salvations = excluded.salvations,
            baptisms = excluded.baptisms,
            home_visits = excluded.home_visits,
            meals_food_packs = excluded.meals_food_packs,
            preschool_attendance = excluded.preschool_attendance;

        if v_exists then
            v_updated := v_updated + 1;
        else
            v_inserted := v_inserted + 1;
        end if;
    end loop;

    return query select v_inserted, v_updated, v_skipped, v_unmatched;
end;
$$;

-- Preview rows that will not match an ICBC site
create or replace view public.weekly_stats_unmatched_churches as
select distinct i.church
from public.weekly_stats_import i
where not exists (
    select 1
    from public.icbc_sites s
    where public.normalise_church_name(s.name) = public.normalise_church_name(i.church)
);

-- Then run weekly_stats_sidebar_view.sql in the SQL Editor for map sidebar rollups.
