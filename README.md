![image](https://github.com/user-attachments/assets/09a3b588-f272-498b-80f4-dcd4551fdc16)

![GitHub License](https://img.shields.io/github/license/suriya-mca/pimify) ![GitHub commit activity](https://img.shields.io/github/commit-activity/t/suriya-mca/pimify) ![GitHub Repo stars](https://img.shields.io/github/stars/suriya-mca/pimify?style=flat&color=pink) ![GitHub forks](https://img.shields.io/github/forks/suriya-mca/pimify?style=flat&color=yellow) ![GitHub Release](https://img.shields.io/github/v/release/suriya-mca/pimify?color=green)

Pimify is an open-source Product Information Management (PIM) platform

<!-- ![edfc4784-dcb8-4995-93b8-9a9f7c64eb62](https://github.com/user-attachments/assets/5e480ae4-10a8-442a-96bb-daa882974855) -->

## Which setup do I want?

| I want to… | Use | Settings | Env file |
|---|---|---|---|
| Try it on my machine | Dev (local) | development | `.env.dev` (auto-created) |
| Try it in a container | Dev (Docker) | development | `.env.dev` |
| Run it for real in a container | Production (Docker) | production | `.env.prod` |
| Run it for real on my server | Production (VPS) | production | `.env.prod` |

`MODE` (in your shell, `-e MODE=…`, or the service unit — never inside the env file) decides which settings load and which file is read: `development` → `.env.dev`, `production` → `.env.prod`. Production refuses to boot without `.env.prod` and without a real `SECRET_KEY`.

## ⚡Dev on your machine (Mac/Linux/Windows)

You can set up the project quickly by running the installation script. Make sure you have the necessary permissions.

### Prerequisites

Ensure the following is installed on your system:

- **Python** (version 3.14 — the project pins `.python-version`)
- **uv** (the package manager; `install.sh` checks for it and points to its installer if missing)

### Clone the project & Go to the project directory

```bash
git clone https://github.com/suriya-mca/pimify.git
cd pimify
```

### Create .env.dev file

The script creates it for you from `.env.dev.example`. Dev needs no secrets — it uses a dummy key and `MODE=development` by default.

### On Mac/Linux

```bash
chmod +x script/start/install.sh
script/start/install.sh   # ends on Django's runserver (autoreload, same on all OSes)
```

### On Windows

```bash
script/start/install.bat   # same thing: runserver, since gunicorn can't run on Windows
```

## 🐋 Dev in Docker

Same app, same dev settings, inside a container. No volume needed — throwaway data is fine here.

```bash
docker build -t pimify:uv .
docker run --env-file .env.dev -e MODE=development -p 8000:8000 --name pimify-dev pimify:uv
```

## 🐋 Production in Docker

The real thing: `MODE=production`, your `.env.prod`, and a volume so uploaded images survive container restarts.

```bash
docker build -t pimify:uv .
docker run --env-file .env.prod -e MODE=production -p 8000:8000 -v pimify-media:/app/media --name pimify-container pimify:uv
```

### Create superuser
```bash
docker exec -it pimify-container python /app/manage.py createsuperuser
```

For scheduled feeds and monthly backups, run a second replica with the scheduler instead of the web server (same image, different command — see Production on a VPS below for what it does).

## 🖥️ Production on a VPS

For a server you own (as opposed to Docker or local dev):

```bash
cp .env.prod.example .env.prod   # then set a real SECRET_KEY + DOMAIN
python -c "import secrets; print(secrets.token_urlsafe(64))"  # paste as SECRET_KEY
sudo script/deploy/install.sh --supervisor systemd --proxy caddy --domain https://pimify.example.com
```

This creates an unprivileged `pimify` user, runs migrations as that user (so root never owns your database), and installs service files for the web server **and the scheduler** (monthly backups + scheduled feeds only run under a supervisor — the dev script deliberately skips it). You own the code and `git pull` as yourself; `pimify` owns `data/` `media/` `backups/` `feeds/`. Re-running the script is safe — it repairs ownership.

Add `--dry-run` to preview, or `--supervisor supervisor|none` / `--proxy nginx|traefik|none` to change the mix. Caddy is the only proxy of the three that handles TLS certificates by itself; with nginx or Traefik, certs are your job. When the installer configures a proxy it sets `TRUST_PROXY_HEADERS=true` in `.env.prod` for you (otherwise secure-cookie login fails behind TLS termination).

The units and proxy configs are templates validated for syntax here but not boot-tested on a live host — check `systemctl is-active pimify-web pimify-scheduler` (or `supervisorctl status`) after enabling. Upgrading from the old single `.env`? The installer copies it to `.env.prod` for you; `.env` is no longer read.

## 📂 Important Folders

Pimify relies on four main folders for data storage and management:

1. **`data/`**: 
   - Stores the actual database file.

2. **`backups/`**: 
   - Contains database backups, kept for the last 3 months by default.
   - You can update this setting with the `DBBACKUP_CLEANUP_KEEP` env var in your env file (`.env.dev` / `.env.prod`).

3. **`media/`**: 
   - Stores image and video files.

4. **`feeds/`**: 
   - Rendered channel feed files (created on demand by `build_feed`).

Ensure these folders are persisted properly when running Pimify in a containerized or production environment (e.g. `-v pimify-media:/app/media`).

## 🚀 Getting Started

Once the server starts, you can access the following URLs:

- **Dashboard**: [http://127.0.0.1:8000/dashboard/](http://127.0.0.1:8000/dashboard/)
- **API Documentation**: [http://127.0.0.1:8000/api/v1/docs](http://127.0.0.1:8000/api/v1/docs)

## 🧭 How It Fits Together

- The **admin** lives at `/dashboard/`; the **API** lives under `/api/v1/` (keyed with the `X-API-Key` header).
- `catalog/` is the real PIM — products, variants, attributes, media. `inventory/` and `procurement/` are read-only mirrors of the legacy tables.
- Stock, cost and lead times are deliberately **not** PIM-owned — they stay on the WMS/ERP side.
- Channel feeds are built with `build_feed` and polled via `/feeds/` and `/feeds/runs/`. Uploaded images serve out of the box, but marketplace feeds need absolute URLs — set `MEDIA_BASE_URL` in your env file for that.

All day-to-day commands run through uv, e.g. `uv sync --locked` and `uv run python manage.py ...`.

## 🤝 Contributing

Contributions are welcome. If you fix a bug or add something useful, a pull request is the fastest way to get it in. See [CONTRIBUTING.md](./CONTRIBUTING.md) for more details on how to contribute.

1. Fork this repository to your GitHub account
2. Clone the forked repository to your local machine
3. Create your Feature or Fix Branch (`git checkout -b feature/your-change`)
4. Make your changes and ensure they are properly tested
5. Commit your Changes (`git commit -m 'Describe your change'`)
6. Push to the Branch (`git push origin feature/your-change`)
7. Open a Pull Request

## 📜 License

Distributed under the Apache License. See `LICENSE` for more information.
