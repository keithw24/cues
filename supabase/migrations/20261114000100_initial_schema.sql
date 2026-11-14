-- PRD-cues.md §17.3. Apply once to a new project through the SQL Editor.
begin;

create table public.activities (
  id text primary key, name text, check_type text, keywords text[],
  success_threshold real, review_threshold real, no_progress_seconds integer, config jsonb
);
create table public.stations (id text primary key, name text);
create table public.seats (
  id text primary key, station_id text, side text, display_name text,
  is_simulated boolean default false
);
create table public.sessions (
  id uuid primary key default gen_random_uuid(), started_at timestamptz default now(),
  current_activity_id text
);
create table public.seat_state (
  seat_id text primary key, session_id uuid, activity_id text, status text,
  task_score real, expression_context jsonb, updated_at timestamptz default now()
);
create table public.events (
  id bigserial primary key, session_id uuid, station_id text, seat_id text,
  type text, activity_id text, score real, payload jsonb, created_at timestamptz default now()
);
create table public.alerts (
  id uuid primary key default gen_random_uuid(), seat_id text, reason text,
  priority text, suggestion text, evidence jsonb, status text,
  created_at timestamptz default now(), resolved_at timestamptz
);
create table public.interventions (
  id uuid primary key default gen_random_uuid(), alert_id uuid, action text,
  approved_at timestamptz
);
create table public.support_preferences (seat_id text primary key, notes text, preferences jsonb);

-- Match the current emitter: sessions/seats need not be inserted before events.
-- No new event types, status enum, score calibration, or foreign keys imposed here.
create index events_seat_created_at_idx on public.events (seat_id, created_at desc);
create index alerts_seat_status_idx on public.alerts (seat_id, status);

alter table public.activities enable row level security;
alter table public.stations enable row level security;
alter table public.seats enable row level security;
alter table public.sessions enable row level security;
alter table public.seat_state enable row level security;
alter table public.events enable row level security;
alter table public.alerts enable row level security;
alter table public.interventions enable row level security;
alter table public.support_preferences enable row level security;

revoke all on public.activities, public.stations, public.seats, public.sessions,
  public.seat_state, public.events, public.alerts, public.interventions,
  public.support_preferences from anon, authenticated;
revoke all on sequence public.events_id_seq from anon, authenticated;
grant select on public.activities, public.stations, public.seats, public.sessions,
  public.seat_state to anon, authenticated;
grant all on public.activities, public.stations, public.seats, public.sessions,
  public.seat_state, public.events, public.alerts, public.interventions,
  public.support_preferences to service_role;
grant usage, select on sequence public.events_id_seq to service_role;

-- Public clients can read simulated demo state only. No browser writes.
create policy demo_seats_read on public.seats for select to anon, authenticated
  using (is_simulated is true);
create policy demo_state_read on public.seat_state for select to anon, authenticated
  using (exists (select 1 from public.seats s where s.id = seat_id and s.is_simulated is true));
create policy demo_stations_read on public.stations for select to anon, authenticated
  using (exists (select 1 from public.seats s where s.station_id = stations.id and s.is_simulated is true));
create policy demo_sessions_read on public.sessions for select to anon, authenticated
  using (exists (select 1 from public.seat_state ss where ss.session_id = sessions.id));
create policy demo_activities_read on public.activities for select to anon, authenticated
  using (exists (select 1 from public.seat_state ss where ss.activity_id = activities.id));

alter publication supabase_realtime add table public.seat_state;
commit;
