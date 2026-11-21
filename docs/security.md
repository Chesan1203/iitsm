# Security

This documents what the system does about security and, just as importantly, what it does **not** do.

## 1. What is in place

### Authentication
- **Login** (`AuthServiceImpl.login`): looks the user up by username and checks the password against its
  stored bcrypt hash.
- **One generic failure.** An unknown username, a wrong password and a deactivated account all raise the same
  `InvalidLoginError("Invalid username or password")`, so an attacker learns nothing about which accounts
  exist. The login page shows exactly that message, keeps the username that was typed, and never sends the
  password back.
- **Equal timing.** When the username is unknown the service still verifies the password against a decoy hash,
  so "no such user" and "wrong password" take about the same time.
- **The system actor cannot log in.** The internal actor used for automatic actions (classification, scheduled
  jobs) has id 0, is never stored in the database, and has an invalid password hash.

### Sessions
- The session is Starlette's `SessionMiddleware`: a cookie **signed** with `SECRET_KEY` that stores **only the
  user's id**. The cookie is `HttpOnly` (scripts on the page cannot read it) and `SameSite=Lax`, and it lasts
  14 days (a test checks the first two).
- **The user is reloaded from the database on every request** (`AuthService.get_user`), never trusted from the
  cookie. A user who has been deactivated is therefore signed out at their next request, and the dead session
  is **cleared**, so it does not come back if the account is reactivated later.
- **Signing in replaces the whole session**, so nothing from before the login survives.
- **Signing out is a POST**, so a link or an image on another page cannot sign someone out.
- **The page to return to after login** (`?next=`) is only used if it is a plain path on this site. Addresses
  such as `//evil.example`, `https://evil.example` and `/\evil.example` are ignored.
- The user is **never taken from a form field or the URL**. Hidden fields such as `user_id`, `status` or
  `priority` are ignored (a test submits them and confirms they have no effect).

### Password protection
- Passwords are hashed with **bcrypt** (a one-way hash with a built-in random salt, work factor 12). The plain
  password is never stored or logged.
- Rules: at least 8 characters (`BusinessRules.MIN_PASSWORD_LENGTH`) and at most 72 bytes, because bcrypt only
  uses the first 72 bytes and the library rejects longer input. Over-long passwords give a normal input error,
  and verifying one simply returns "no match", never a crash.
- The seeded demo users share one hash of the documented demo password (`docs/demo_data.md`). That is for the
  demo only.

### Role-based authorization (checked in three places)
1. **Web layer:** every router carries a role guard, so typing a URL directly is blocked just like a hidden menu
   link. An anonymous visitor is redirected to `/login`; the wrong role gets a **403** page. Examples: the
   `/admin/...` pages and all administrator actions need the administrator role; `/tech/...` and the
   technician actions need the technician role; reporting needs an employee. Which buttons an incident page
   shows is decided in `app/web/actions.py`, which is a display hint only.
2. **Services layer** (`AccessPolicy`): administrators only for every admin, report and assignment method;
   employees see only their own incidents, technicians only those assigned to them. Search criteria are narrowed
   to the actor and a conflicting filter is overridden, so an employee cannot read someone else's incidents by
   asking for them.
3. **Domain layer** (`state/permissions.py`): for example only the assigned technician can acknowledge or
   resolve, and only the reporter can reject a resolution or give feedback.

Every service method checks the actor itself. Nothing relies on the user interface hiding a button. A test walks **every route of the running application** and requires each one to be public on purpose or to match an explicit access rule, then checks that anonymous visitors are redirected and every disallowed role gets a 403, so a new route cannot be added without a guard.

### Input validation and output safety
- Usernames: 3 to 30 letters, digits, dots or underscores. Email: simple format check. Names, titles and free
  text have length limits (title 200, other text 4000 characters).
- Counts and choices are type-checked (for example affected users must be a whole number of at least 1 and not
  a boolean; impact and urgency must be real levels). Form text is converted to numbers and enum values in one
  place (`app/web/forms.py`); anything unreadable becomes "missing" and is rejected by the service.
- A failure raises `InvalidInputError` naming the field, which the page shows next to the form field. A message
  about a field the form does not have is shown in the form's general error area, so no message is lost.
- **Every page escapes what it displays** (Jinja2 auto-escaping is on). Text such as `<script>alert(1)</script>`
  typed as an incident title, a note, a user's name or a notification is shown as text and never runs; tests
  check this on several pages.
- Self-registration always creates an **Employee**, whatever else the request contains. Only an administrator can
  create technicians and administrators.

### Protection against unauthorised operations and data loss
- Users are **deactivated, never deleted**, so history stays readable. An administrator cannot deactivate their
  own account.
- The audit trail is append-only through the application (no update or delete path).
- Illegal incident transitions are impossible by construction (State pattern).
- A user can mark only their own notifications as read; an unknown id and someone else's id give the same error,
  so nothing is revealed about other people's notifications.
- Unexpected errors show a generic page. The details go to the server log, never to the browser.

### Database security (P2)
- Every value reaches SQL as a `?` parameter. The only text inserted into SQL statements is fixed column names
  and lists of `?`. Tests use `x' OR '1'='1` as search input and confirm it is treated as plain text.
- Foreign keys and `CHECK` constraints are enforced by the database, and raw database errors never leave the
  persistence layer (they become `PersistenceError`).

## 2. Honest limitations

These are deliberate omissions for the scope of a course project. Each would be needed before real use.

| Gap | Consequence | What production would add |
| --- | --- | --- |
| **No CSRF tokens** | `SameSite=Lax` keeps modern browsers from sending the cookie on a cross-site form post, which stops the common attack, but it is not a complete defence (older browsers, and attacks from a sibling site) | A CSRF token in every form, checked on every POST |
| **No rate limiting or account lockout** | Passwords can be guessed by repeated attempts | Throttling per account and per address, lockout or increasing delays |
| **No HTTPS in the demo; the cookie has no `Secure` flag** | Passwords and the session cookie travel unencrypted | TLS termination and `https_only` cookies |
| **Default `SECRET_KEY`** (`dev-only-change-me`) | Anyone who knows it can forge a session cookie for any user id | A long random secret from the environment, never committed |
| **Signed, not encrypted, stateless cookie sessions** | The user id is readable by the user. A session cannot be revoked: a cookie value that was copied before sign-out stays valid until it expires (14 days) or the account is deactivated | Server-side sessions with expiry and revocation |
| **Password policy is length only** | Weak but long passwords are accepted | Breached-password checks, complexity guidance |
| **No password reset, email verification or multi-factor login** | A forgotten password needs an administrator | Reset links, verified email, MFA for administrators |
| **Shared demo password** | Anyone who reads the docs can log in to a demo database | Never seed demo users outside demos (`SEED_DEMO_DATA=false`) |
| **Bootstrap is loaded from a CDN with no integrity hash** | If the CDN were compromised, its script and styles would run in the pages | Serve the files from the application, or add `integrity` hashes |
| **FastAPI's `/docs`, `/redoc` and `/openapi.json` are public** | They list the application's routes (not data) to anyone | Turn them off outside development |
| **Audit trail is not tamper-proof** | Someone with direct access to the database file could edit it | Write-once storage or hash-chained records |
| **Simulated email log** | `logs/emails.log` holds notification text in plain text | Remove the simulated channel; use a real, access-controlled gateway |
| **No encryption at rest** | The SQLite file is readable by anyone with file access | Database encryption, or a server database with access control |
| **Lost-update window** | A background job and a user acting on the same incident within milliseconds can overwrite each other | Version numbers checked on save |
| **Observers run before the save** | A failed save can leave an audit record for an unsaved change | Write audit and incident in one transaction |

## 3. Operating it safely

- Set `SECRET_KEY` to a long random value in the environment, and never reuse the default.
- Run with `SEED_DEMO_DATA=false` and an empty database for anything other than a demo.
- Keep the `data/` and `logs/` folders out of version control (they are git-ignored).
- Put the application behind HTTPS if it is ever used outside a laptop.
