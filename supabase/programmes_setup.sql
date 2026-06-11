-- Normalize an older database that still stored programme fields on `icbc_sites`.
-- Recommended path:
-- 1. Run the latest `schema.sql`
-- 2. Run this file once to remove obsolete columns/tables from an older project

alter table public.icbc_sites
    drop column if exists preschool_summary,
    drop column if exists ploughing_season,
    drop column if exists hours_ploughed,
    drop column if exists families_ploughed_for,
    drop column if exists area_ploughed,
    drop column if exists maize_tonnes_purchased,
    drop column if exists maize_farmers_supported,
    drop column if exists preschool_children_impacted;

alter table public.staff
    drop column if exists photo_path;

alter table public.staff_import
    drop column if exists photo_path;

drop table if exists public.pastors cascade;
drop table if exists public.teachers cascade;
drop table if exists public.compassionate_care_members cascade;

alter table public.preschool_snapshots
    add column if not exists children_impacted_since_inception integer;

comment on column public.preschool_snapshots.children_impacted_since_inception is
    'Optional running total captured on a snapshot row instead of on icbc_sites.';
