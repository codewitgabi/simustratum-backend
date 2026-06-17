# BACKEND.md

End-to-end backend design for Simustratum — authentication, session management, AI question generation, scoring, transcripts, and progress tracking.

---

## Database Schema

### `users`

```sql
id             UUID PRIMARY KEY DEFAULT gen_random_uuid()
email          TEXT NOT NULL UNIQUE
password_hash  TEXT                          -- null for OAuth-only users
full_name   TEXT NOT NULL
avatar_url     TEXT
provider       TEXT NOT NULL DEFAULT 'email' -- 'email' | 'google'
provider_id    TEXT                          -- Google sub, null for email users
created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
updated_at     TIMESTAMPTZ NOT NULL DEFAULT now()
```

### `sessions`

```sql
id               UUID PRIMARY KEY DEFAULT gen_random_uuid()
user_id          UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE
scenario_id      TEXT NOT NULL        -- 'tutorial'|'presentation'|'defense'|'oral'|'seminar'|'english'
topic            TEXT NOT NULL
status           TEXT NOT NULL DEFAULT 'active'  -- 'active'|'paused'|'completed'|'abandoned'
options          JSONB NOT NULL DEFAULT '{}'      -- { feedback, timer, transcript }
started_at       TIMESTAMPTZ
ended_at         TIMESTAMPTZ
duration_seconds INTEGER
question_count   INTEGER NOT NULL DEFAULT 0
answered_count   INTEGER NOT NULL DEFAULT 0
score_clarity    NUMERIC(5,2)
score_confidence NUMERIC(5,2)
score_structure  NUMERIC(5,2)
score_overall    NUMERIC(5,2)
created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
updated_at       TIMESTAMPTZ NOT NULL DEFAULT now()
```

### `session_panelists`

```sql
id             UUID PRIMARY KEY DEFAULT gen_random_uuid()
session_id     UUID NOT NULL REFERENCES sessions(id) ON DELETE CASCADE
name           TEXT NOT NULL
role           TEXT NOT NULL
strict         INTEGER NOT NULL DEFAULT 50   -- 0–100
inquisitive    INTEGER NOT NULL DEFAULT 50   -- 0–100
position_index INTEGER NOT NULL DEFAULT 0    -- order in the panel (0-based)
```

### `session_questions`

AI-generated questions for each session. Stored so they can be replayed and referenced during scoring.

```sql
id             UUID PRIMARY KEY DEFAULT gen_random_uuid()
session_id     UUID NOT NULL REFERENCES sessions(id) ON DELETE CASCADE
panelist_id    UUID NOT NULL REFERENCES session_panelists(id)
text           TEXT NOT NULL
sequence       INTEGER NOT NULL    -- 0-based order
asked_at       TIMESTAMPTZ
```

### `session_transcript`

Full conversation log (both panelist questions and user answers).

```sql
id          UUID PRIMARY KEY DEFAULT gen_random_uuid()
session_id  UUID NOT NULL REFERENCES sessions(id) ON DELETE CASCADE
speaker     TEXT NOT NULL       -- panelist name or 'You'
text        TEXT NOT NULL
is_user     BOOLEAN NOT NULL DEFAULT false
sequence    INTEGER NOT NULL    -- insertion order
created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
```

### `answer_scores`

Per-answer AI scoring. Aggregated at session end to produce `sessions.score_*` columns.

```sql
id              UUID PRIMARY KEY DEFAULT gen_random_uuid()
session_id      UUID NOT NULL REFERENCES sessions(id) ON DELETE CASCADE
question_id     UUID NOT NULL REFERENCES session_questions(id)
answer_text     TEXT NOT NULL
clarity         NUMERIC(5,2)
confidence      NUMERIC(5,2)
structure       NUMERIC(5,2)
ai_feedback     TEXT            -- one-sentence tip shown after the answer
scored_at       TIMESTAMPTZ NOT NULL DEFAULT now()
```

### `saved_panels`

Reusable panelist configurations a user can recall in future sessions.

```sql
id          UUID PRIMARY KEY DEFAULT gen_random_uuid()
user_id     UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE
name        TEXT NOT NULL    -- e.g. "My Defense Panel"
panelists   JSONB NOT NULL   -- SessionPanelist[] (same shape as session_panelists)
created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
```

### `password_reset_tokens`

```sql
id          UUID PRIMARY KEY DEFAULT gen_random_uuid()
user_id     UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE
token_hash  TEXT NOT NULL UNIQUE
expires_at  TIMESTAMPTZ NOT NULL
used        BOOLEAN NOT NULL DEFAULT false
created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
```

---

## Auth Flow

### Token Strategy

- **Access token** — JWT, signed with `ACCESS_TOKEN_SECRET`, expires in **15 minutes**. Sent in `Authorization: Bearer <token>` header.
- **Refresh token** — opaque random string, hashed before storage, stored in an **httpOnly Secure cookie** (`ss_refresh`), expires in **7 days**. Only valid against `POST /api/auth/refresh`.

### Email / Password Signup

```
POST /api/auth/signup
Body: { email, password, displayName }

1. Validate email uniqueness → 409 if taken
2. Hash password with bcrypt (cost 12)
3. INSERT into users
4. Issue access token + refresh token
5. Set ss_refresh cookie
6. Return { user, accessToken }
```

### Login

```
POST /api/auth/login
Body: { email, password }

1. Fetch user by email → 401 if not found or provider != 'email'
2. bcrypt.compare(password, hash) → 401 on mismatch
3. Issue access token + refresh token
4. Set ss_refresh cookie
5. Return { user, accessToken }
```

### Google OAuth

```
GET  /api/auth/google          -- redirects to Google consent screen
GET  /api/auth/google/callback -- Google redirects here with code

Callback flow:
1. Exchange code for Google tokens
2. Fetch Google profile (sub, email, name, picture)
3. UPSERT users WHERE provider='google' AND provider_id=sub
   - On first login: create user with provider='google', no password_hash
   - On return: update display_name and avatar_url if changed
4. Issue access token + refresh token
5. Set ss_refresh cookie
6. Redirect to /dashboard
```

### Token Refresh

```
POST /api/auth/refresh
Cookie: ss_refresh=<token>

1. Validate cookie present → 401
2. Hash incoming token; lookup refresh_tokens by hash
3. Check not revoked and not expired → 401
4. Revoke old token (set revoked=true)
5. Issue new access token + new refresh token (rotation)
6. Return { accessToken }
```

### Logout

```
POST /api/auth/logout
Cookie: ss_refresh=<token>

1. Hash cookie → find and revoke refresh_token row
2. Clear ss_refresh cookie
3. Return 204
```

### Password Reset

```
POST /api/auth/forgot-password
Body: { email }
→ Generate token, hash it, store in password_reset_tokens (expires 1 hour)
→ Send email via Resend with reset link (/reset-password?token=<raw>)
→ Always return 200 (don't leak whether email exists)

POST /api/auth/reset-password
Body: { token, newPassword }
→ Hash token, lookup row, check not used and not expired
→ bcrypt hash newPassword, update users.password_hash
→ Mark token used=true
→ Return 200
```

---

## Standard Response Format

```jsonc
// Success
{ "data": { ... }, "meta": { ... } }

// Paginated list
{ "data": [...], "meta": { "total": 42, "page": 1, "limit": 20 } }

// Error
{ "error": { "code": "INVALID_CREDENTIALS", "message": "Email or password is incorrect." } }
```

HTTP status codes follow REST conventions (200, 201, 204, 400, 401, 403, 404, 409, 422, 500).

---

## API Endpoints

All routes below `/api/` except auth are protected — require `Authorization: Bearer <accessToken>`.

---

### Auth

| Method | Path | Description |
|---|---|---|
| POST | `/api/auth/signup` | Email/password registration |
| POST | `/api/auth/login` | Email/password login |
| POST | `/api/auth/logout` | Revoke refresh token, clear cookie |
| POST | `/api/auth/refresh` | Rotate refresh token, return new access token |
| GET | `/api/auth/me` | Return current user object |
| GET | `/api/auth/google` | Start Google OAuth flow |
| GET | `/api/auth/google/callback` | Google OAuth callback |
| POST | `/api/auth/forgot-password` | Send password reset email |
| POST | `/api/auth/reset-password` | Apply new password via reset token |

---

### User

#### `GET /api/user/profile`

Returns the authenticated user's profile.

```jsonc
// Response 200
{
  "data": {
    "id": "uuid",
    "email": "user@example.com",
    "displayName": "Gabriel Michael",
    "avatarUrl": "https://res.cloudinary.com/...",
    "provider": "email",
    "createdAt": "2026-06-01T10:00:00Z"
  }
}
```

#### `PATCH /api/user/profile`

```jsonc
// Body (all fields optional)
{ "displayName": "Gabriel M.", "avatarUrl": "https://..." }

// Response 200 — updated user object
```

#### `POST /api/user/avatar`

Multipart upload. Accepts `image/*`, max 5 MB. Uploads to Cloudinary, stores URL.

```
Content-Type: multipart/form-data
Field: file (image)

Response 200: { "data": { "avatarUrl": "..." } }
```

#### `DELETE /api/user`

Deletes the account and all associated data (cascades via FK). Requires password confirmation for email users.

```jsonc
// Body
{ "password": "current-password" }   // omit for Google users

// Response 204
```

---

### Sessions

#### `POST /api/sessions`

Creates a session record and immediately triggers AI question generation.

```jsonc
// Body
{
  "scenarioId": "defense",
  "topic": "The effect of social media on academic performance",
  "panelists": [
    { "name": "Dr. Okafor", "role": "Research Methods", "strict": 75, "inquisitive": 80 },
    { "name": "Prof. Amara", "role": "Theory", "strict": 50, "inquisitive": 60 }
  ],
  "options": {
    "feedback": true,
    "timer": false,
    "transcript": true
  }
}

// Response 201
{
  "data": {
    "id": "session-uuid",
    "scenarioId": "defense",
    "topic": "The effect of social media on academic performance",
    "status": "active",
    "panelists": [ { "id": "...", "name": "Dr. Okafor", ... } ],
    "questions": [
      { "id": "q-uuid", "panelistId": "p-uuid", "text": "Walk us through...", "sequence": 0 },
      ...
    ],
    "options": { "feedback": true, "timer": false, "transcript": true },
    "createdAt": "2026-06-16T08:00:00Z"
  }
}
```

**Side effect**: calls Claude to generate `N` questions (see AI section below) and stores them in `session_questions`. The client receives all questions upfront so it can drive the session locally without round-tripping per question.

#### `GET /api/sessions`

Paginated list of the user's sessions, newest first.

Query params: `page` (default 1), `limit` (default 20), `status` (filter), `scenarioId` (filter).

```jsonc
// Response 200
{
  "data": [
    {
      "id": "...",
      "scenarioId": "defense",
      "topic": "...",
      "status": "completed",
      "scoreOverall": 82,
      "durationSeconds": 1140,
      "answeredCount": 6,
      "createdAt": "..."
    }
  ],
  "meta": { "total": 14, "page": 1, "limit": 20 }
}
```

#### `GET /api/sessions/:id`

Full session detail including panelists, options, and scores.

```jsonc
// Response 200
{
  "data": {
    "id": "...",
    "scenarioId": "defense",
    "topic": "...",
    "status": "completed",
    "options": { ... },
    "panelists": [ ... ],
    "scores": {
      "clarity": 88,
      "confidence": 74,
      "structure": 85,
      "overall": 82
    },
    "durationSeconds": 1140,
    "questionCount": 6,
    "answeredCount": 6,
    "startedAt": "...",
    "endedAt": "..."
  }
}
```

#### `PATCH /api/sessions/:id`

Update session status (start, pause, resume, end, abandon). Validates state transitions.

```jsonc
// Body
{ "status": "completed", "durationSeconds": 1140 }

// Valid transitions:
// active → paused, completed, abandoned
// paused → active, abandoned

// Response 200 — updated session
```

When `status` is set to `"completed"`, the server aggregates all `answer_scores` rows for this session and writes the final `score_clarity`, `score_confidence`, `score_structure`, and `score_overall` to `sessions`.

#### `DELETE /api/sessions/:id`

Hard-deletes a session and all related rows. Returns 204.

---

### Session Answers

#### `POST /api/sessions/:id/answers`

Submit the user's spoken/typed answer to the current question. The server scores it asynchronously via Claude and stores the result.

```jsonc
// Body
{
  "questionId": "q-uuid",
  "text": "I chose a quantitative approach because..."
}

// Response 201
{
  "data": {
    "id": "answer-uuid",
    "questionId": "q-uuid",
    "scores": {
      "clarity": 82,
      "confidence": 68,
      "structure": 79
    },
    "feedback": "Good structure — try to define your terms earlier for maximum clarity."
  }
}
```

The per-answer scores are written to `answer_scores`. The `feedback` field is displayed in real-time if the user has `options.feedback = true`.

---

### Session Transcript

#### `GET /api/sessions/:id/transcript`

Returns the full ordered transcript for a completed session.

```jsonc
// Response 200
{
  "data": {
    "sessionId": "...",
    "messages": [
      { "id": "...", "speaker": "Dr. Okafor", "text": "Walk us through...", "isUser": false, "sequence": 0 },
      { "id": "...", "speaker": "You", "text": "I chose quantitative...", "isUser": true, "sequence": 1 }
    ]
  }
}
```

#### `POST /api/sessions/:id/transcript`

Append a message to the transcript during an active session. Called by the client after each panelist question is delivered and after each user answer.

```jsonc
// Body
{ "speaker": "Dr. Okafor", "text": "Walk us through...", "isUser": false, "sequence": 0 }

// Response 201 — the created message
```

---

### Dashboard

#### `GET /api/dashboard`

Single endpoint to populate the dashboard. Returns recent sessions, aggregate stats, and progress snapshot.

```jsonc
// Response 200
{
  "data": {
    "recentSessions": [
      {
        "id": "...",
        "scenarioId": "defense",
        "topic": "Effect of social media...",
        "scoreOverall": 82,
        "durationSeconds": 1140,
        "endedAt": "2026-06-14T12:00:00Z"
      }
    ],
    "stats": {
      "totalSessions": 14,
      "avgScore": 78,
      "totalMinutesPracticed": 210,
      "currentStreak": 3    // consecutive days with at least one session
    },
    "scoreHistory": [
      { "date": "2026-06-01", "scoreOverall": 65 },
      { "date": "2026-06-07", "scoreOverall": 74 },
      { "date": "2026-06-14", "scoreOverall": 82 }
    ]
  }
}
```

---

### Progress

#### `GET /api/progress`

Detailed score history for the progress page. Supports date range filtering.

Query params: `from` (ISO date), `to` (ISO date), `scenarioId` (filter by type).

```jsonc
// Response 200
{
  "data": {
    "sessions": [
      {
        "id": "...",
        "scenarioId": "defense",
        "topic": "...",
        "scores": { "clarity": 88, "confidence": 74, "structure": 85, "overall": 82 },
        "endedAt": "..."
      }
    ],
    "averagesByDimension": {
      "clarity": 81,
      "confidence": 72,
      "structure": 79
    },
    "byScenario": {
      "defense": { "count": 5, "avgScore": 79 },
      "oral": { "count": 3, "avgScore": 85 }
    }
  }
}
```

---

### Saved Panels

#### `GET /api/panels`

```jsonc
// Response 200
{
  "data": [
    {
      "id": "...",
      "name": "My Defense Panel",
      "panelists": [ { "name": "Dr. Okafor", "role": "Research Methods", "strict": 75, "inquisitive": 80 } ],
      "createdAt": "..."
    }
  ]
}
```

#### `POST /api/panels`

```jsonc
// Body
{
  "name": "My Defense Panel",
  "panelists": [
    { "name": "Dr. Okafor", "role": "Research Methods", "strict": 75, "inquisitive": 80 }
  ]
}

// Response 201 — saved panel object
```

#### `DELETE /api/panels/:id`

Returns 204. Only the owner can delete.

---

## AI Integration

### Question Generation

Called during `POST /api/sessions`. Generates a full question set for the session before the client receives the response.

**Model**: `claude-sonnet-4-6`

**Prompt template**:

```
System:
You are an AI question generator for an academic practice platform called Simustratum.
Generate exactly {N} challenging, realistic questions for a {scenarioLabel} session.
Return a JSON array of objects with this shape: [{ "panelistIndex": number, "text": string }]
Do not include any other text or markdown.

User:
Topic: {topic}
Scenario: {scenarioLabel}

Panelists:
{panelists.map((p, i) => `${i}. ${p.name} (${p.role}) — strict: ${p.strict}/100, inquisitive: ${p.inquisitive}/100`).join('\n')}

Rules:
- Distribute questions across panelists roughly proportionally to their inquisitiveness score
- Panelists with higher strict scores ask harder, more challenging questions
- Panelists with higher inquisitive scores ask more follow-up and probing questions
- Questions must relate directly to the topic
- Vary question types: methodology, theory, implications, evidence, clarification
- Scenario context: {scenarioDescription}
```

**Question count `N`** by scenario:

| Scenario | Questions |
|---|---|
| tutorial | 5 |
| presentation | 6 |
| defense | 8 |
| oral | 10 |
| seminar | 7 |
| english | 6 |

**Response parsing**: Expect a JSON array. If Claude returns malformed JSON or wrong shape, fall back to a set of generic scenario questions stored as a constant (same as current `DEMO_QUESTIONS` pattern).

---

### Answer Scoring

Called on `POST /api/sessions/:id/answers`. Runs asynchronously — the endpoint returns after the score is ready (p95 < 2 s with Sonnet).

**Model**: `claude-haiku-4-5-20251001` (fast and cheap for per-answer scoring)

**Prompt template**:

```
System:
You score spoken answers in an academic practice session. Return only JSON.
Shape: { "clarity": number, "confidence": number, "structure": number, "feedback": string }
All scores are integers 0–100. feedback is a single actionable sentence.

User:
Question: {question.text}
Scenario: {scenarioLabel}
Answer: {answer.text}

Scoring criteria:
- clarity: Was the answer easy to understand? Were terms defined? Was language precise?
- confidence: Did the speaker assert their points, or hedge excessively? Avoid "I think maybe..."
- structure: Did the answer have a clear opening, supporting detail, and conclusion?
```

---

## Middleware & Cross-Cutting Concerns

### Auth Middleware

All protected routes use a shared middleware:

1. Extract `Authorization: Bearer <token>` header
2. Verify JWT signature and expiry using `ACCESS_TOKEN_SECRET`
3. Attach `req.user = { id, email }` to the request
4. Return 401 if token is missing, malformed, or expired

### Rate Limiting

| Route group | Limit |
|---|---|
| `POST /api/auth/login` | 10 req / 15 min per IP |
| `POST /api/auth/signup` | 5 req / hour per IP |
| `POST /api/auth/forgot-password` | 3 req / hour per IP |
| `POST /api/sessions` | 20 req / hour per user |
| `POST /api/sessions/:id/answers` | 120 req / hour per user |
| All other routes | 300 req / 15 min per user |

### Ownership Guard

For any resource-scoped route (`/sessions/:id`, `/panels/:id`, etc.), verify `resource.user_id === req.user.id` after fetching. Return 404 (not 403) to avoid leaking existence.

### Environment Variables

```
DATABASE_URL=postgresql://...
ACCESS_TOKEN_SECRET=...
REFRESH_TOKEN_SECRET=...
ANTHROPIC_API_KEY=...
GOOGLE_CLIENT_ID=...
GOOGLE_CLIENT_SECRET=...
NEXTAUTH_URL=http://localhost:3000
CLOUDINARY_URL=...
RESEND_API_KEY=...
```

---

## Session Lifecycle Summary

```
User clicks "Begin Session"
   → POST /api/sessions          (creates session + panelists + AI questions)
   → client stores session_id, drives local speech/timer loop
   → each panelist question plays: POST /api/sessions/:id/transcript { isUser: false }
   → user answers:               POST /api/sessions/:id/answers    → returns live score
   → answer logged:              POST /api/sessions/:id/transcript { isUser: true }
   → all questions answered OR user clicks "End & get feedback"
   → PATCH /api/sessions/:id { status: "completed", durationSeconds }
   → server aggregates answer_scores → writes final session scores
   → client reads scores from PATCH response and renders the results card
```

---

## Prisma Schema (summary)

```prisma
model User {
  id           String    @id @default(uuid())
  email        String    @unique
  passwordHash String?   @map("password_hash")
  displayName  String    @map("display_name")
  avatarUrl    String?   @map("avatar_url")
  provider     String    @default("email")
  providerId   String?   @map("provider_id")
  createdAt    DateTime  @default(now()) @map("created_at")
  updatedAt    DateTime  @updatedAt @map("updated_at")

  sessions       Session[]
  savedPanels    SavedPanel[]
  refreshTokens  RefreshToken[]
  resetTokens    PasswordResetToken[]
}

model Session {
  id               String    @id @default(uuid())
  userId           String    @map("user_id")
  scenarioId       String    @map("scenario_id")
  topic            String
  status           String    @default("active")
  options          Json      @default("{}")
  startedAt        DateTime? @map("started_at")
  endedAt          DateTime? @map("ended_at")
  durationSeconds  Int?      @map("duration_seconds")
  questionCount    Int       @default(0) @map("question_count")
  answeredCount    Int       @default(0) @map("answered_count")
  scoreClarity     Decimal?  @map("score_clarity")
  scoreConfidence  Decimal?  @map("score_confidence")
  scoreStructure   Decimal?  @map("score_structure")
  scoreOverall     Decimal?  @map("score_overall")
  createdAt        DateTime  @default(now()) @map("created_at")
  updatedAt        DateTime  @updatedAt @map("updated_at")

  user        User                @relation(fields: [userId], references: [id], onDelete: Cascade)
  panelists   SessionPanelist[]
  questions   SessionQuestion[]
  transcript  SessionTranscript[]
  answers     AnswerScore[]
}

model SessionPanelist {
  id            String  @id @default(uuid())
  sessionId     String  @map("session_id")
  name          String
  role          String
  strict        Int     @default(50)
  inquisitive   Int     @default(50)
  positionIndex Int     @default(0) @map("position_index")

  session   Session           @relation(fields: [sessionId], references: [id], onDelete: Cascade)
  questions SessionQuestion[]
}

model SessionQuestion {
  id          String    @id @default(uuid())
  sessionId   String    @map("session_id")
  panelistId  String    @map("panelist_id")
  text        String
  sequence    Int
  askedAt     DateTime? @map("asked_at")

  session   Session         @relation(fields: [sessionId], references: [id], onDelete: Cascade)
  panelist  SessionPanelist @relation(fields: [panelistId], references: [id])
  answer    AnswerScore?
}

model SessionTranscript {
  id        String   @id @default(uuid())
  sessionId String   @map("session_id")
  speaker   String
  text      String
  isUser    Boolean  @default(false) @map("is_user")
  sequence  Int
  createdAt DateTime @default(now()) @map("created_at")

  session Session @relation(fields: [sessionId], references: [id], onDelete: Cascade)
}

model AnswerScore {
  id          String   @id @default(uuid())
  sessionId   String   @map("session_id")
  questionId  String   @unique @map("question_id")
  answerText  String   @map("answer_text")
  clarity     Decimal?
  confidence  Decimal?
  structure   Decimal?
  aiFeedback  String?  @map("ai_feedback")
  scoredAt    DateTime @default(now()) @map("scored_at")

  session  Session         @relation(fields: [sessionId], references: [id], onDelete: Cascade)
  question SessionQuestion @relation(fields: [questionId], references: [id])
}

model SavedPanel {
  id        String   @id @default(uuid())
  userId    String   @map("user_id")
  name      String
  panelists Json
  createdAt DateTime @default(now()) @map("created_at")

  user User @relation(fields: [userId], references: [id], onDelete: Cascade)
}

model RefreshToken {
  id        String   @id @default(uuid())
  userId    String   @map("user_id")
  tokenHash String   @unique @map("token_hash")
  expiresAt DateTime @map("expires_at")
  revoked   Boolean  @default(false)
  createdAt DateTime @default(now()) @map("created_at")

  user User @relation(fields: [userId], references: [id], onDelete: Cascade)
}

model PasswordResetToken {
  id        String   @id @default(uuid())
  userId    String   @map("user_id")
  tokenHash String   @unique @map("token_hash")
  expiresAt DateTime @map("expires_at")
  used      Boolean  @default(false)
  createdAt DateTime @default(now()) @map("created_at")

  user User @relation(fields: [userId], references: [id], onDelete: Cascade)
}
```
