-- Network-wide ICBC impact rollups for the map dashboard.
-- Run in Supabase SQL Editor after schema + seed data are loaded.
--
-- Fetch: GET /rest/v1/icbc_network_stats_summary?select=*

create or replace view public.icbc_network_stats_summary as
with weekly as (
    select
        count(*) filter (where w.total_attendance > 0)::integer as sundays_recorded,
        round(avg(w.total_attendance) filter (where w.total_attendance > 0)::numeric, 1) as avg_attendance,
        coalesce(sum(w.salvations), 0)::integer as total_salvations,
        coalesce(sum(w.baptisms), 0)::integer as total_baptisms,
        coalesce(sum(w.home_visits), 0)::integer as total_home_visits
    from public.weekly_stats w
),
plough as (
    select
        coalesce(sum(p.hours_ploughed), 0)::numeric as total_hours_ploughed,
        coalesce(sum(p.families_impacted), 0)::integer as total_families_ploughed,
        coalesce(sum(p.hectares_ploughed), 0)::numeric as total_hectares_ploughed
    from public.ploughing_records p
),
maize as (
    select
        coalesce(sum(m.kilograms_bought), 0)::numeric as total_maize_kg,
        coalesce(sum(m.farmers_impacted), 0)::integer as total_farmers_supported
    from public.maize_buyback_records m
),
preschool as (
    select coalesce(sum(pe.children_count), 0)::integer as total_preschool_children
    from public.preschool_enrollment pe
),
sites as (
    select
        count(*)::integer as icbc_sites_planted,
        count(*) filter (where s.latitude is not null and s.longitude is not null)::integer as icbc_sites_mapped
    from public.icbc_sites s
),
staff as (
    select count(*)::integer as total_staff
    from public.staff st
)
select
    sites.icbc_sites_planted,
    sites.icbc_sites_mapped,
    weekly.sundays_recorded,
    weekly.avg_attendance,
    weekly.total_salvations,
    weekly.total_baptisms,
    weekly.total_home_visits,
    plough.total_hours_ploughed,
    plough.total_families_ploughed,
    plough.total_hectares_ploughed,
    maize.total_maize_kg,
    maize.total_farmers_supported,
    preschool.total_preschool_children,
    staff.total_staff
from sites, weekly, plough, maize, preschool, staff;

comment on view public.icbc_network_stats_summary is
    'Network-wide ICBC impact totals for the map dashboard.';

grant select on public.icbc_network_stats_summary to anon, authenticated;
