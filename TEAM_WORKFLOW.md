# Cues — Team Workflow

This file defines how the 3-person Cues team builds independently and integrates safely.

## Team branches

| Person | Branch | Owns |
|---|---|---|
| Keith | `keith` | Computer vision / local perception |
| Evan | `evan` | Frontend + app backend / Supabase UI |
| Michelle | `michelle` | Rules engine + Deep Agent + Groq + Photon |

`main` is the shared integration branch.

Each person should primarily edit their own area and avoid changing another person's files unless necessary for integration.

---

## 1. System split

### Keith — CV / local perception

Primary responsibility:

```text
Camera
  ↓
MediaPipe
  ↓
Gesture matching
  ↓
HSEmotion
  ↓
Structured events
  ↓
Supabase
```

Owns:

- webcam capture
- MediaPipe Hand Landmarker
- normalized hand landmarks
- teacher-recorded gesture templates
- nearest-neighbor gesture matching
- match-score calibration
- raise-hand rule
- HSEmotion
- expression-context signal
- tracking-loss handling
- structured perception events

Keith does **not** decide when the teacher should be alerted.

Keith's output is structured state/events.

---

### Evan — app / frontend + Supabase-facing product

Primary responsibility:

```text
Supabase
  ↕
Next.js
  ↓
Teacher dashboard + station UI
```

Owns:

- Next.js
- Tailwind
- teacher dashboard
- student/station page
- Supabase schema and realtime subscriptions
- seat cards
- task controls
- push-to-talk voice commands
- gesture-recording UI
- alert UI
- approve / dismiss controls
- review queue
- simulated students

Evan should be able to build the UI using fake/sample data before CV or the agent is connected.

---

### Michelle — routing / rules / agent

Primary responsibility:

```text
Supabase events
  ↓
Rules engine
  ↓
Deep Agent
  ↓
Groq / GPT-OSS
  ↓
Tool actions
  ├── Supabase alert
  └── Photon notification
```

Owns:

- rules engine
- event routing
- alert cooldowns
- Deep Agents
- Groq integration
- agent tools
- support-preference retrieval
- intervention selection
- teacher-alert creation
- Photon
- approval workflow
- deterministic fallback when the LLM is unavailable

Michelle's code receives **structured state only**.

The LLM must never receive camera frames.

---

## 2. Shared architecture

```mermaid
flowchart LR
    A[Logitech Camera] --> B[Local Vision Service]
    B --> C[MediaPipe + HSEmotion]
    C --> D[Supabase Realtime]
    D --> E[Teacher Dashboard]
    D --> F[Rules + Deep Agent]
    F --> G[Groq / GPT-OSS 20B]
    F --> H[Photon Alert]
```

---

## 3. Shared contracts

These interfaces should be agreed on early and changed carefully.

All three parts should be able to develop against fake versions of these objects.

### 3.1 `events`

Written by CV / backend.

Read by rules + agent.

Example:

```json
{
  "session_id": "demo",
  "station_id": "S1",
  "seat_id": "S1-L",
  "type": "attempt_miss",
  "activity_id": "custom_gesture_01",
  "score": 0.31,
  "payload": {},
  "created_at": "2026-11-14T02:00:00Z"
}
```

Initial event types:

```text
attempt_success
attempt_miss
review_needed
no_progress
tracking_lost
expression_context
teacher_verified
```

---

### 3.2 `seat_state`

Written/updated from perception + backend state.

Read by the frontend.

Example:

```json
{
  "seat_id": "S1-L",
  "activity_id": "custom_gesture_01",
  "status": "in_progress",
  "task_score": 0.31,
  "expression_context": {
    "label": "neutral",
    "probability": 0.74
  }
}
```

Status values:

```text
idle
in_progress
review
done
needs_help
tracking_lost
```

---

### 3.3 `alerts`

Written by Michelle's rules/agent system.

Read and updated by Evan's frontend.

Example:

```json
{
  "id": "abc123",
  "seat_id": "S1-L",
  "reason": "repeated_misses",
  "priority": "high",
  "suggestion": "Demonstrate the gesture again",
  "evidence": {
    "attempts": 3,
    "expression_signal": true
  },
  "status": "pending"
}
```

Alert status:

```text
pending
approved
dismissed
```

---

### 3.4 `activities`

Created/selected by the app.

Read by the perception pipeline.

Example:

```json
{
  "id": "custom_gesture_01",
  "name": "Custom Gesture 1",
  "check_type": "gesture",
  "success_threshold": 0.78,
  "review_threshold": 0.58,
  "no_progress_seconds": 30
}
```

Task thresholds are activity-specific.

Do not introduce one universal confidence threshold for every type of task.

---

## 4. Development rule: nobody waits for anyone

### Keith

Develop against local/fake task configuration.

Initially print events:

```text
EVENT attempt_miss
EVENT attempt_success
EVENT expression_context
```

Then replace the local emitter with Supabase writes.

### Evan

Develop with sample JSON for:

```text
seat_state
alerts
activities
```

The dashboard should work before real CV or the real agent exists.

### Michelle

Develop with fake events.

Example:

```text
attempt_miss
attempt_miss
attempt_miss
```

should be enough to test:

```text
rules trigger
→ agent invoked
→ tools selected
→ alert created
```

No camera or frontend should be required to test the agent system.

---

## 5. Facial-expression rule

HSEmotion is supporting context only.

Correct:

```text
repeated task difficulty
+
sustained expression signal
→ higher-priority context
```

Incorrect:

```text
sad face
→ student is struggling
```

Facial expression alone must never determine task failure or trigger a diagnosis.

---

## 6. Integration order

Integrate in this order:

```text
1. CV → Supabase
2. Supabase → Dashboard
3. Supabase → Rules
4. Rules → Agent
5. Agent → Alerts
6. Alerts → Dashboard
7. Agent → Photon
8. Teacher approval → approved action
```

Do not attempt full-system integration before the earlier connections work.

---

## 7. Git workflow

Branches:

```text
main
keith
evan
michelle
```

`main` is integration only.

Before starting work:

```bash
git switch <your-name>
git pull
git merge main
```

Commit small, scoped changes.

Push regularly:

```bash
git add .
git commit -m "<short description>"
git push
```

Before merging into `main`, pull the latest `main` into your branch and resolve conflicts there.

Do not force-push during the hackathon unless the whole team explicitly agrees.

---

## 8. Shared dependency rules

Python uses:

```text
uv
pyproject.toml
uv.lock
```

Add Python packages only with:

```bash
uv add <package>
```

Do not use `pip install` as the permanent project workflow.

Frontend dependencies use npm:

```bash
cd web
npm install <package>
```

Commit both lockfiles when dependencies change.

---

## 9. Product constraints shared by everyone

- Product name is **Cues**.
- Teacher assistance, not teacher replacement.
- No face recognition.
- No ESP32 / Arduino / LEDs / physical buttons.
- No YOLO / MobileNet object-state pipeline in the MVP.
- No Amazon Bedrock dependency.
- Student camera frames stay local.
- Groq / the LLM receives structured state only.
- Expression is supporting evidence only.
- Teacher approval is required before instructional changes.
- Voice task commands remain part of the MVP.

---

## 10. Definition of successful independent work

Before shared integration:

### Keith can demonstrate

```text
camera → gesture/expression → structured event
```

### Evan can demonstrate

```text
fake Supabase/sample state → responsive dashboard + alerts UI
```

### Michelle can demonstrate

```text
fake events → rules → Deep Agent → structured alert
```

Once all three work independently, begin shared integration using the order in Section 6.
