-- Align the original synthetic activity with shared/contracts.py (merged later).
update public.activities
set check_type = 'rule', no_progress_seconds = coalesce(no_progress_seconds, 30)
where id = 'raise_hand' and check_type = 'raise_hand';
