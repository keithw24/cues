-- Approved intervention menu and teacher approval (PRD 12, 13, 26).
--
-- The agent may attach ONE suggestion to the review it requests, and only from this fixed menu
-- (teacher_reviews.suggested_intervention). Nothing changes until the teacher approves:
-- approve_review_intervention records the approval in public.interventions (the table the initial
-- schema reserved for it) and, if the review is still pending, confirms it ("Support needed").
-- Cues does not change the student's task or any instruction by itself; the record is the
-- teacher's decision. The menu is the same list as shared/contracts.py INTERVENTION_MENU and
-- web/lib/interventions.ts (a test keeps the three equal).
-- Requires 100 (interventions), 300 (teacher_reviews), 600 (review ownership).
begin;

alter table public.teacher_reviews add column suggested_intervention text
  check (suggested_intervention is null or suggested_intervention in (
    'repeat_instruction', 'show_example', 'model_task',
    'smaller_steps', 'offer_break', 'adult_check_in'));

alter table public.interventions
  add column review_id uuid references public.teacher_reviews (id) on delete cascade;
-- NOT VALID: the table was never used, but never fail a deploy over an old row.
alter table public.interventions add constraint interventions_action_check
  check (action in (
    'repeat_instruction', 'show_example', 'model_task',
    'smaller_steps', 'offer_break', 'adult_check_in')) not valid;
-- One approval per review.
create unique index interventions_one_per_review
  on public.interventions (review_id) where review_id is not null;

-- A teacher reads the approvals of reviews in sessions they own. Writes go through the RPC only.
grant select on public.interventions to authenticated;
create policy teacher_reads_own_interventions on public.interventions
  for select to authenticated using (
    exists (
      select 1 from public.teacher_reviews r
      join public.sessions s on s.id = r.session_id
      where r.id = interventions.review_id and s.teacher_id = auth.uid()
    )
  );

-- Approve a support for a review the signed-in teacher owns. action defaults to the agent's
-- suggestion; the teacher may pick any other item on the menu. A pending review becomes
-- confirmed in the same step; an already confirmed one gets its approval; dismissed, expired
-- and reviewed ones cannot be approved.
create function public.approve_review_intervention(review_id uuid, action text default null)
returns public.interventions
language plpgsql security definer set search_path = '' as $$
declare
  target public.teacher_reviews;
  chosen text;
  result public.interventions;
begin
  if auth.uid() is null or auth.role() <> 'authenticated' then
    raise exception 'authenticated user required' using errcode = '42501';
  end if;
  select r.* into target from public.teacher_reviews r where r.id = review_id for update;
  if not found then
    raise exception 'unknown review ID' using errcode = 'P0002';
  end if;
  perform 1 from public.sessions s where s.id = target.session_id
    and s.teacher_id = auth.uid() for share;
  if not found then
    raise exception 'review outside owned session' using errcode = '42501';
  end if;
  chosen := coalesce(action, target.suggested_intervention);
  if chosen is null or chosen not in (
    'repeat_instruction', 'show_example', 'model_task',
    'smaller_steps', 'offer_break', 'adult_check_in') then
    raise exception 'choose an approved intervention' using errcode = '22023';
  end if;
  if target.status not in ('pending', 'confirmed') then
    raise exception 'review is closed' using errcode = '22023';
  end if;
  if exists (select 1 from public.interventions i where i.review_id = target.id) then
    raise exception 'already approved' using errcode = '22023';
  end if;
  if target.status = 'pending' then
    update public.teacher_reviews r
      set status = 'confirmed', resolved_at = clock_timestamp()
      where r.id = target.id and r.status = 'pending';
  end if;
  insert into public.interventions (id, review_id, action, approved_at)
    values (gen_random_uuid(), target.id, chosen, clock_timestamp())
    returning * into result;
  return result;
end;
$$;
revoke all on function public.approve_review_intervention(uuid, text)
  from public, anon, service_role;
grant execute on function public.approve_review_intervention(uuid, text) to authenticated;

commit;
