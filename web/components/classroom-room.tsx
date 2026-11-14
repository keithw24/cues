import { initials } from "@/components/workspace-rows";

// The classroom as the camera sees it: one circle per person, left to right
// in frame order. Positions only, never video. Status is a ring around the
// circle plus a text label, so color is never the only cue.
export type RoomPerson = {
  id: string;
  name: string;
  status: string;
  tone: "working" | "done" | "review" | "quiet";
  activity: string;
  selected: boolean;
};

export function ClassroomRoom({
  people,
  emptyMessage,
  onSelect,
}: {
  people: RoomPerson[];
  emptyMessage: string;
  onSelect: (id: string, opener: HTMLButtonElement) => void;
}) {
  return (
    <section className="room-stage" aria-labelledby="room-heading">
      <h2 id="room-heading">The room</h2>
      {people.length ? (
        <ul className="room-people">
          {people.map((person) => (
            <li key={person.id}>
              <button
                type="button"
                className={`room-person is-${person.tone}`}
                aria-pressed={person.selected}
                onClick={(event) => onSelect(person.id, event.currentTarget)}
              >
                <span className="room-avatar" aria-hidden="true">
                  {initials(person.name)}
                </span>
                <span className="room-name">{person.name}</span>
                <span className="room-status">{person.status}</span>
                <span className="room-activity">{person.activity}</span>
              </button>
            </li>
          ))}
        </ul>
      ) : (
        <p className="room-empty" role="status">
          {emptyMessage}
        </p>
      )}
    </section>
  );
}
