# Deploying on TrueNAS SCALE (25.04 and later, Docker apps)

Layout: a **Caddy** container terminates HTTPS on its own LAN address (macvlan), and the Django app (gunicorn +
SQLite) is only reachable from Caddy. Certificates come from Let's Encrypt with the TLS-ALPN-01 challenge, which only
needs **port 443** to be reachable from the internet (no port 80, no DNS API).

```
internet :443 -> router port forward -> LAN_IP:443 (Caddy) -> wedding:8000 (Django)
                                                          \-> /photos/ -> your Lychee gallery (optional)
```

## 1. Prerequisites
- A hostname pointing to your public IP (any DNS provider, including a DDNS service), and a router port forward
  `public:443 -> LAN_IP:443`. `LAN_IP` must be a free address outside the DHCP range.
- A dataset for the app, e.g. `POOL/Apps/wedding` (the deploy script creates the sub-folders).
- SSH access as root to the NAS (key based).
- Two private, git-ignored files on your workstation:
  - `deploy/truenas/deploy.private.env`, copied from `deploy.env.example` (dataset path, host name, LAN IP, NIC name,
    subnet, gateway; `ACME_CA` for the Let's Encrypt staging CA while testing).
  - `prod.private.env`, copied from `.env.example` (all app settings and secrets).
- Optionally a `content/` directory next to the repository with your private overlay (see below).

## 2. Deploy / update
```bash
SSH_OPTS="-i ~/.ssh/my_key -o IdentitiesOnly=yes" deploy/truenas/deploy.sh root@nas
```
The script (needs a clean git tree) uploads the committed sources, your env files and the overlay, builds the image on
the NAS (tagged with the commit), renders `compose.yaml` and creates or updates the `wedding` custom app via the
TrueNAS API. The container runs migrations and collects static files on every start; `/healthz` is the healthcheck.

Tip: set `ACME_CA=https://acme-staging-v02.api.letsencrypt.org/directory` for the first run to validate the whole path
(router forward, DNS) without hitting Let's Encrypt rate limits, then remove it and deploy again.

Notes
- With macvlan the NAS itself cannot reach `LAN_IP` (Docker limitation); other LAN machines can. Test from another device:
  `curl --resolve host:443:LAN_IP https://host/healthz`.
- Data lives in `<APP_DIR>/data` (SQLite, owned by uid 568): snapshot that dataset for backups. Caddy keeps its
  certificates in `<APP_DIR>/caddy`.
- The app container runs read-only, as a non-root user, without capabilities; the `egress` network only exists so that
  it can reach your SMTP server (and the gallery API, if you use one).

## 3. First steps
Container names follow `ix-wedding-<service>-1`; adjust them if `docker ps` shows something else.
```bash
docker exec -it ix-wedding-wedding-1 python manage.py createsuperuser       # then log in at /admin/
```
1. In `/admin/`, create the **events** (slug, name, date, place) and, for each one, its **menu choices** if guests choose
   a meal.
2. Put your guest list (see the format in the main README) in `<APP_DIR>/data/guests.csv`, owned by `568:568`, and import it:
   ```bash
   docker exec ix-wedding-wedding-1 python manage.py import_guests /data/guests.csv --dry-run
   docker exec ix-wedding-wedding-1 python manage.py import_guests /data/guests.csv
   ```
3. Check the e-mails from `/dashboard/` (staff only): preview them and send yourself a test.
4. Send the campaigns, one event at a time (everything is a dry run unless `--send`):
   ```bash
   docker exec ix-wedding-wedding-1 python manage.py send_campaign save_the_date --event ceremony
   docker exec ix-wedding-wedding-1 python manage.py send_campaign save_the_date --event ceremony --send --mark-sent
   ```
   The other campaigns are `invitation`, `preparation` and `thank_you`; the last two only go to guests who said they come.
5. After the event: `python manage.py purge_guests --older-than-days 180` (keeps staff accounts).

## 4. Private overlay (`content/`)
Anything in `content/templates` takes precedence over the repository templates and `content/static` is added to the
static files:

```
content/templates/partials/welcome.html            # welcome text on the home page
content/templates/partials/event_<slug>.html       # replaces the generic section of the event with that slug
content/templates/partials/gifts.html              # gift list / charities / pot
content/templates/partials/story.html              # "our story" (nothing is shown without it)
content/templates/partials/contact.html            # contact section (phone numbers...)
content/templates/partials/nav_extra.html          # extra menu entries
content/templates/guests/email_templates/*.html    # e-mail wording (save_the_date, invitation, preparation, thank_you)
content/static/wedding/hero.jpg                    # point HEADER_IMAGE / EMAIL_HERO_IMAGE at it: wedding/hero.jpg
```
Inside an e-mail template, `{% email_image 'wedding/menu.png' %}` embeds any image of the static directories.
The directory is git-ignored; versioning it in a separate private repository is a good idea.

## 5. Photo gallery (optional)
The site can log guests in to a [Lychee](https://lycheeorg.dev) gallery with a single click:
1. Run Lychee on another machine or app and create an administrator.
2. In `Caddyfile`, uncomment the `/photos/*` block and put the gallery address there.
3. Set in `prod.private.env`: `LYCHEE_URL=https://<SITE_HOST>/photos`, `LYCHEE_API_URL=<internal address of the gallery>`,
   `LYCHEE_ADMIN_USER` and `LYCHEE_ADMIN_PASSWORD`, then deploy again.
4. Create one gallery account per guest: `python manage.py sync_lychee_users` (names and passwords are derived from
   `SECRET_KEY`: changing the key means creating the accounts again).

The client speaks the legacy Lychee API (`/api/Session::login`, `/api/Users::create`); it has not been exercised against
recent Lychee releases, so check it on a test account first (the endpoints are constants in `guests/lychee.py`).

## 6. Keeping a dynamic IP up to date
If your ISP can change your public IP, make your router (or a cron job on the NAS) update the DNS record; the app
itself does not depend on the IP.
