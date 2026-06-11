-- Run once in SQL Editor so the static map (anon key) can read sidebar views.
grant select on public.icbc_site_sidebar to anon, authenticated;
grant select on public.icbc_site_staff to anon, authenticated;
grant select on public.preschool_enrollment to anon, authenticated;
