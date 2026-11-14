// The Cues mark: a head and a raised arm (Figma "Cues logo", round 8, Y4a).
// The head uses currentColor; the arm uses --cues-mark-accent, falling back
// to currentColor so the mark also works in one colour.
export default function CuesMark({
  size = 28,
  className,
}: {
  size?: number;
  className?: string;
}) {
  return (
    <svg
      className={className}
      width={size}
      height={size}
      viewBox="4 5.5 56 56"
      fill="none"
      aria-hidden="true"
      focusable="false"
    >
      <path
        fill="currentColor"
        d="M14 31C13 24 19 20 24 21C30 22 32 27 31 32C30 37 24 39 19 38C15 37 14.5 34 14 31Z"
      />
      <path
        style={{ fill: "var(--cues-mark-accent, currentColor)" }}
        d="M30.92 55.98Q35.95 32.5 43.7 9.7A3 3 0 0 1 49.52 11.15Q42.94 34.25 39.08 58.02A4.2 4.2 0 0 1 30.92 55.98Z"
      />
    </svg>
  );
}
