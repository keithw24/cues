begin;
create table public.teacher_profiles (
  user_id uuid primary key references auth.users(id) on delete cascade,
  display_name text,
  phone_number text check (phone_number is null or phone_number ~ '^\+[1-9][0-9]{7,14}$'),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create function public.normalize_teacher_profile() returns trigger
language plpgsql set search_path = '' as $$
begin
  new.phone_number := nullif(regexp_replace(new.phone_number, '[[:space:]().-]', '', 'g'), '');
  if TG_OP = 'UPDATE' then
    new.created_at := old.created_at;
  end if;
  new.updated_at := clock_timestamp();
  return new;
end;
$$;
create trigger teacher_profile_normalize before insert or update on public.teacher_profiles
for each row execute function public.normalize_teacher_profile();
alter table public.teacher_profiles enable row level security;
revoke all on public.teacher_profiles from anon, authenticated;
grant select, insert, update on public.teacher_profiles to authenticated;
grant all on public.teacher_profiles to service_role;
create policy own_teacher_profile on public.teacher_profiles to authenticated
using (user_id = auth.uid()) with check (user_id = auth.uid());

alter table public.sessions add column teacher_id uuid references auth.users(id);
create index sessions_teacher_id_idx on public.sessions(teacher_id);
-- Historical sessions remain unowned; never assign an arbitrary teacher.
-- Browser session creation is RPC-only. The SECURITY DEFINER start RPC
-- validates station membership/activity and assigns auth.uid() (migration 007).
revoke insert on public.sessions from authenticated;
create policy own_session_read on public.sessions for select to authenticated
using (teacher_id = auth.uid());

drop policy demo_teacher_reviews_read on public.teacher_reviews;
create policy own_teacher_reviews_read on public.teacher_reviews for select to authenticated
using (exists (select 1 from public.sessions s
  where s.id = teacher_reviews.session_id and s.teacher_id = auth.uid()));
revoke select on public.teacher_reviews from anon;

create or replace function public.resolve_teacher_review(review_id uuid, action text)
returns setof public.teacher_reviews
language plpgsql security definer set search_path = '' as $$
declare target public.teacher_reviews;
begin
  if auth.uid() is null or auth.role() <> 'authenticated' then
    raise exception 'authenticated user required' using errcode = '42501';
  end if;
  if action is null or action not in ('confirmed', 'dismissed') then
    raise exception 'invalid review action' using errcode = '22023';
  end if;
  select r.* into target from public.teacher_reviews r where r.id = review_id for update;
  if not found then
    raise exception 'unknown review ID' using errcode = 'P0002';
  end if;
  -- Lock ownership for the duration of resolution.
  perform 1 from public.sessions s where s.id = target.session_id
    and s.teacher_id = auth.uid() for share;
  if not found then
    raise exception 'review outside owned session' using errcode = '42501';
  end if;
  if target.status <> 'pending' then
    raise exception 'review already resolved' using errcode = '22023';
  end if;
  return query update public.teacher_reviews r
    set status = action, resolved_at = clock_timestamp()
    where r.id = review_id and r.status = 'pending' returning r.*;
end;
$$;
revoke all on function public.resolve_teacher_review(uuid,text) from public, anon, service_role;
grant execute on function public.resolve_teacher_review(uuid,text) to authenticated;
commit;
