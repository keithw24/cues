"""Pin the authoritative session before any per-frame task checking."""

from vision.session_sync import STATION_SESSION

FLAG = "vision.session_lifecycle"


class SessionStage:
    name = "session"
    rate_hz = None

    def __init__(self, state=STATION_SESSION):
        self.state = state

    def process(self, frame, ctx):
        ctx["session_managed"] = True
        ctx["session"] = self.state.for_frame(frame.timestamp)
        # Never draw/use a previous session's matches while paused or switching.
        ctx["match"] = {}

    def draw(self, image, ctx):
        pass

    def close(self):
        pass


def create_stage():
    return SessionStage()
