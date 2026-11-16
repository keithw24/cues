"""Pin the authoritative session before any per-frame task checking."""

from vision.session_sync import STATION_SESSION


class SessionStage:
    name = "session"
    rate_hz = None

    def __init__(self, state=STATION_SESSION, station=None):
        from vision import station as station_module

        self.state = state
        self.station = station or station_module.STATION

    def process(self, frame, ctx):
        ctx["session_managed"] = True
        session = self.state.for_frame(frame.timestamp)
        # A session of another station (e.g. just before a switch) is never used.
        if session is not None and session.station_id != self.station.get():
            session = None
        ctx["session"] = session
        # Never draw/use a previous session's matches while paused or switching.
        ctx["match"] = {}

    def draw(self, image, ctx):
        pass

    def close(self):
        pass


def create_stage():
    """Only with a database: offline, tasks come from CUES_TASK and nothing is paused."""
    from vision.supabase_client import online

    return SessionStage() if online() else None
