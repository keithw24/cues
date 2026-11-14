begin;
-- Backend-only acknowledgement of the exact consent snapshot used for a send.
-- Lock profile first, matching consent capture and phone invalidation lock order.
create function public.record_teacher_notification_send(
  p_user_id uuid, p_phone text, p_attempt uuid, p_project_id text, p_result text
) returns boolean
language plpgsql security definer set search_path = '' as $$
declare current_phone text; changed integer;
begin
  if p_result not in ('accepted','target_not_allowed','provider_failure','network_failure')
    or p_result is null then
    raise exception 'Invalid send result' using errcode='22023';
  end if;
  select phone_number into current_phone from public.teacher_profiles
    where user_id=p_user_id for update;
  if not found or current_phone is distinct from p_phone then return false; end if;
  update public.teacher_notification_settings set
    photon_registration_status=case p_result when 'accepted' then 'registered'
      when 'target_not_allowed' then 'registering' else 'failed' end,
    photon_registered_at=case when p_result='accepted' then clock_timestamp() end,
    photon_registration_error=case when p_result in ('accepted','target_not_allowed')
      then null else p_result end,
    updated_at=clock_timestamp()
  where user_id=p_user_id and notification_opt_in=true
    and notification_phone=p_phone and registration_attempt=p_attempt
    and photon_project_id=p_project_id;
  get diagnostics changed = row_count;
  return changed=1;
end;
$$;
revoke all on function public.record_teacher_notification_send(uuid,text,uuid,text,text)
  from public, anon, authenticated;
grant execute on function public.record_teacher_notification_send(uuid,text,uuid,text,text)
  to service_role;
commit;
