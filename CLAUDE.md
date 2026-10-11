# CLAUDE.md

Django 5.2 wedding site: per-event information, RSVP with menu choices, per-guest magic links, e-mail campaigns,
optional Lychee gallery log-in. Public repository: **never commit personal data** (names, e-mails, phone numbers,
domains, LAN addresses, photos, secrets). Anything personal lives in `.env`, `prod.private.env`, `content/` (all
git-ignored) or the database.

## Commands
```bash
uv sync                                   # install (Python 3.12, uv.lock is authoritative)
uv run python manage.py test              # whole suite; one app: `test guests.tests.test_rsvp`
uv run ruff check . && uv run ruff format --check .
uv run python manage.py makemigrations --check --dry-run
uv run coverage run manage.py test && uv run coverage report --fail-under=85   # CI threshold
```
Settings need `SECRET_KEY`, or `DEBUG=true` in `.env` for development (`.env.example` lists every variable).

## Layout
- `bigday/`: project package (settings from env, URLs, context processor, base templates, vendored Bootstrap 4 CSS,
  small vanilla JS files). Only the Bootstrap CSS is vendored, so any behaviour (navbar toggle, countdown, RSVP
  meal toggle) is hand-written JS in `bigday/static/bigday/js/`.
- `guests/`: the only app. `models.py` (Family, Event, MealOption, Guest, Invitation), `campaigns.py` (the four
  `Campaign` instances), `forms.py` (RSVP), `views.py`, `csv_import.py`, `lychee.py`, `templatetags/wedding.py`,
  `management/commands/`.
- `deploy/truenas/`, `Dockerfile`, `compose.yaml`, `docker/entrypoint.sh`: documented TrueNAS SCALE deployment
  (Caddy + gunicorn). `deploy.sh` builds on the NAS and needs a clean git tree.

## Conventions and gotchas
- Settings are env variables parsed in `bigday/settings.py` (`env_str`/`env_bool`/`env_list`); add new ones to
  `.env.example` and the README table. Site text and images are overridable from `SITE_CONTENT_DIR` (templates first,
  then static), so defaults in the repo must stay neutral French text with no personal content.
- Events, slugs and menus are data (admin), never code. Per-event page override: `partials/event_<slug>.html`.
- `Guest.email` is nullable, lower-cased, and `None` (not `""`) when empty: several guests without e-mail must not
  collide on the unique column. Guests normally have no usable password; access is through `Invitation.token`.
- Personal links (`/invite/<token>/`, `/home/<token>/?c=<campaign>`, `/photos/<token>/`) identify one invitation.
  Treat tokens as secrets: never log or display them to other guests.
- Campaigns: `send_all` is a dry run unless `send=True`; `mark_sent` only after a successful send. Inline e-mail images
  go through `{% email_image 'static/path' %}` (registers a `cid:` attachment), not hard-coded filenames.
- Subjects use `.replace("{event}", ...)`, not `str.format`.
- Staff-only views use `staff_member_required`; state-changing views are POST-only.
- Tests: subclass `bigday.test_utils.AppTestCase` (plain static storage, locmem mail, fixed settings) and build data
  with `guests/tests/helpers.py`. Use fictional data only (Stark/Lannister, `example.org`).
- The Lychee client targets the legacy `/api/Session::login` / `/api/Users::create` endpoints and has only been tested
  against mocks.
- Never push, change branches on the remote, or deploy without being asked.
