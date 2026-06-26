-- Aggregated weekly stats for the map sidebar.
-- Run AFTER schema.sql and AFTER weekly_stats rows are loaded.
--
-- This is SQL (not a seed CSV). In Supabase: SQL Editor → New query → paste → Run.
--
-- Sidebar display rules (value must be GREATER THAN the threshold):
--   Avg attendance     — always shown when weekly data exists
--   Avg men/women/youth/children — per Sunday (weeks with attendance > 0)
--   Total salvations   — only if total > 10
--   Total baptisms     — only if total > 10
--   Total home visits  — only if total > 50
--
-- Fetch from the static map (example):
--   GET /rest/v1/icbc_site_stats_summary?slug=eq.bulunga&select=*

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
                'value', round(coalesce(avg(w.total_attendance) filter (where w.total_attendance > 0), 0)::numeric, 1),
                'format', 'decimal'
            )
        )
        || case
            when count(w.id) filter (where w.total_attendance > 0) > 0 then
                jsonb_build_array(
                    jsonb_build_object(
                        'key', 'avg_men',
                        'title', 'Avg men',
                        'value', round(coalesce(avg(w.men) filter (where w.total_attendance > 0), 0)::numeric, 1),
                        'format', 'decimal'
                    ),
                    jsonb_build_object(
                        'key', 'avg_women',
                        'title', 'Avg women',
                        'value', round(coalesce(avg(w.women) filter (where w.total_attendance > 0), 0)::numeric, 1),
                        'format', 'decimal'
                    ),
                    jsonb_build_object(
                        'key', 'avg_youth',
                        'title', 'Avg youth',
                        'value', round(coalesce(avg(w.youth) filter (where w.total_attendance > 0), 0)::numeric, 1),
                        'format', 'decimal'
                    ),
                    jsonb_build_object(
                        'key', 'avg_children',
                        'title', 'Avg children',
                        'value', round(coalesce(avg(w.children) filter (where w.total_attendance > 0), 0)::numeric, 1),
                        'format', 'decimal'
                    )
                )
            else '[]'::jsonb
        end
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

comment on view public.icbc_site_stats_summary is
    'Per-site weekly stat rollups for the map sidebar (avg attendance + conditional totals).';

-- Expose to the Supabase REST API (anon key / static site reads)
grant select on public.icbc_site_stats_summary to anon, authenticated;
