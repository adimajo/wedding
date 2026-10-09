# wedding

A small, self-hosted Django site for a **wedding**: information per event, a personal RSVP page with menu choices,
and e-mail campaigns with per-guest links.

- Guests open the site with a **personal link** received by e-mail (or create an account with a shared access code).
  They only see the events they are invited to.
- Guests answer the **RSVP** (family by family, with a menu choice per course when the event has a menu), and the
  couple follow the answers on a staff-only dashboard.
- The couple manage events, menus, guests and invitations in the Django admin, import guests from a CSV and send four
  e-mail campaigns (*save the date*, *invitation*, *preparation*, *thank you*) with tracking of who opened them.
- Optional one-click log-in to a [Lychee](https://lycheeorg.dev) photo gallery.
- Container image and TrueNAS SCALE instructions included. Everything personal (names, dates, texts, photos, SMTP
  credentials) lives in environment variables, in the admin database and in a private overlay directory, never in
  the repository.

The project started as a fork of [django-wedding-website](https://github.com/czue/django-wedding-website) by Cory Zue
(Apache-2.0); see `NOTICE`.

## Quick start (development)

```bash
cp .env.example .env            # set DEBUG=true and EMAIL_BACKEND=django.core.mail.backends.console.EmailBackend
uv sync
uv run python manage.py migrate
uv run python manage.py createsuperuser
uv run python manage.py runserver
```
Then, in `/admin/`, create an **event** (with its menu choices if you want guests to pick a meal), and import guests:

```bash
uv run python manage.py import_guests guests.csv --dry-run
uv run python manage.py import_guests guests.csv
```

Tests and checks:

```bash
uv run python manage.py test
uv run ruff check . && uv run ruff format --check .
```

## Configuration

All settings are environment variables (a `.env` file at the project root is loaded automatically, without overriding
real environment variables); `.env.example` lists them with comments. The important ones:

| Variable | Meaning |
|---|---|
| `SECRET_KEY` | Required when `DEBUG` is off |
| `SITE_URL`, `ALLOWED_HOSTS` | Public URL / host names (used for links in e-mails, CSRF and secure cookies) |
| `REGISTRATION_CODE` | Phrase that lets people without a personal link create an account; empty disables `/register/` |
| `COUPLE_NAMES`, `SITE_TITLE`, `RSVP_DEADLINE`, `GIFT_POT_URL` | Shown in the default texts and e-mails |
| `HEADER_IMAGE`, `EMAIL_HERO_IMAGE`, `EMAIL_HEADER_IMAGE` | Images (static paths) for the web header and the e-mails |
| `*_SUBJECT` | E-mail subjects (`{event}` is replaced by the event name) |
| `EMAIL_*`, `DEFAULT_FROM_EMAIL`, `REPLY_TO_EMAIL`, `CC_LIST` | SMTP and campaign headers |
| `LYCHEE_URL`, `LYCHEE_API_URL`, `LYCHEE_ADMIN_USER`, `LYCHEE_ADMIN_PASSWORD` | Optional photo gallery |
| `DB_PATH` | SQLite file location |
| `SITE_CONTENT_DIR` | Private overlay with `templates/` and `static/` that override the defaults |

### Events and menus (in the admin)
An **event** has a slug, a name, a date, a place and a free description. It can have **menu choices** (starter, main,
dessert): guests who say they come then choose one per course (children are never asked). Guests are invited
**per event**, so the home page, the RSVP page and the e-mails only talk about the events of the guest.

### Private overlay
Put your own texts and images in `SITE_CONTENT_DIR` (default `./content`, git-ignored): `partials/welcome.html`,
`partials/event_<slug>.html` (replaces the generic section of one event), `partials/gifts.html`, `partials/story.html`,
`partials/contact.html`, the e-mail templates in `guests/email_templates/` and any image under `static/`. Reference
images with `HEADER_IMAGE` / `EMAIL_HERO_IMAGE`, or embed more in an e-mail template with `{% email_image 'path' %}`.
The list of overridable files is in [`deploy/truenas/README.md`](deploy/truenas/README.md#4-private-overlay-content).

## Guest list (CSV)
The first row names the columns (order, case and punctuation do not matter; French names such as `prénom` work too):

```csv
family,first_name,last_name,is_child,email,invited_ceremony,invited_party
The Starks,Ned,Stark,n,ned@example.org,y,y
The Starks,Arya,Stark,y,,y,n
```
- `first_name` is required. `family` groups people who answer together (default: the person alone).
- Each `invited_<event-slug>` column (`y`/`n`) invites the guest to the event with that slug; create the events first
  or use `--create-events`.
- Guests are matched on their e-mail address, so importing again updates instead of duplicating, and never deletes.
  Children and people without e-mail are fine: they answer through a family member's link.

## Operating

| Task | Command |
|---|---|
| Import guests | `manage.py import_guests guests.csv [--dry-run] [--create-events]` |
| Export the RSVP state | `manage.py export_guests > answers.csv` (or the staff-only link in the dashboard) |
| Send a campaign | `manage.py send_campaign save_the_date\|invitation\|preparation\|thank_you [--event SLUG] [--send] [--mark-sent] [--reset] [--delay S]` (dry run unless `--send`) |
| QR codes (table cards...) | `manage.py generate_qr_codes DIR [--event SLUG] [--target home\|photos]` |
| Create gallery accounts | `manage.py sync_lychee_users [--event SLUG] [--dry-run]` |
| Delete old guests (retention) | `manage.py purge_guests --older-than-days 180` |
| Delete all guests | `manage.py wipe_guest_list` |

Staff-only pages: `/admin/` and `/dashboard/` (answers, who has not opened or answered, e-mail previews and test
sends to yourself). Password (re)set goes through an e-mailed link at `/password/reset/`.

## Security notes
- Personal links contain a secret token and log the guest in: tell guests not to forward the e-mail. A link gives
  access to the answers of the whole family of the guest, and to nothing else.
- Guests have no password unless they choose one; passwords are hashed.
- The guest list cannot be read from the public site: only staff can use the dashboard, the admin and the export.
- Run behind HTTPS; the container trusts `X-Forwarded-Proto` from your proxy.
- The gallery log-in derives one password per guest from `SECRET_KEY`; keep the gallery for guests only.

## Deployment
See [`deploy/truenas/README.md`](deploy/truenas/README.md) (TrueNAS SCALE 25.04+: Caddy with automatic HTTPS in front of
the app, deployed with `deploy/truenas/deploy.sh`) and `compose.yaml`. Dependencies are locked with
[uv](https://docs.astral.sh/uv/) (`uv.lock`); the image is built with `uv sync --locked` from digest-pinned base
images, and Dependabot proposes updates through CI-checked pull requests.

## License
Apache License 2.0, see `LICENSE` and `NOTICE`.
