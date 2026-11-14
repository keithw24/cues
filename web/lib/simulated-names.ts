/**
 * Made-up first names for simulated people, so the demo reads like a
 * classroom. Names follow the position id (S1-P3 → third name); they never
 * identify anyone, and a seat that is not simulated keeps its own label.
 */
const NAMES = ["Maya", "Leo", "Ava", "Noah", "Zoe", "Eli", "Ruby", "Kai"];

export function displayName(
  seat: { id: string; display_name: string; is_simulated: boolean },
  enabled: boolean,
): string {
  if (!enabled || !seat.is_simulated) return seat.display_name;
  const position = Number(/-P(\d+)$/.exec(seat.id)?.[1]);
  return Number.isInteger(position) && position > 0
    ? NAMES[(position - 1) % NAMES.length]
    : seat.display_name;
}
