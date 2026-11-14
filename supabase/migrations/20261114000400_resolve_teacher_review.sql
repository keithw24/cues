begin;

-- Session ownership is not represented yet. Authenticated demo users may resolve
-- simulated-seat reviews only; this is NOT classroom/session authorization.
create function public.resolve_teacher_review(review_id uuid, action text)
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
  if not exists (select 1 from public.seats s
      where s.id = target.seat_id and s.is_simulated is true) then
    raise exception 'review outside authorized demo scope' using errcode = '42501';
  end if;
  if target.status <> 'pending' then
    raise exception 'review already resolved' using errcode = '22023';
  end if;
  return query update public.teacher_reviews r
    set status = action, resolved_at = clock_timestamp()
    where r.id = review_id and r.status = 'pending' returning r.*;
end;
$$;
revoke all on function public.resolve_teacher_review(uuid, text) from public, anon, service_role;
grant execute on function public.resolve_teacher_review(uuid, text) to authenticated;
commit;
