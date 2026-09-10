# Resale API

FastAPI inventory, purchases, sales, and refunds backed by PostgreSQL.

## Local setup

Use Python 3.14.4, matching `.python-version` and the development environment.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Edit `.env` with your development Neon connection URL and preserve its SSL
parameters. Never commit real credentials. Exported environment variables
override `.env`. URL-encode special characters in the username/password.

```bash
alembic upgrade head
alembic current
alembic check
uvicorn app:app --reload
```

Open http://127.0.0.1:8000/docs to exercise the API. `/` is a process health
check, not a database readiness check.

## Tests

```bash
DATABASE_URL=sqlite:///:memory: python -m unittest discover -s tests -v
```

These service tests use SQLite. Validate migrations separately against a
disposable PostgreSQL database with `alembic upgrade head` and `alembic check`.

## First Git commit

```bash
git init -b main
git add .
git status --short
git diff --cached --stat
git commit -m "Prepare API and migrations for deployment"
```

Before committing, confirm `.env`, `.venv`, and `__pycache__` are absent from
the staged files. Commit `alembic.ini` and the migration source files.
Create an empty GitHub repository, then use its actual URL:

```bash
git remote add origin <your-github-repository-url>
git push -u origin main
```

## Render deployment with Neon

The API currently has no authentication: public clients can read and modify
data. Use test data for an initial deployment; add access control before
exposing private inventory.

1. Use a separate Neon database or branch for the deployed environment.
2. Push this repository to GitHub.
3. In Render, create a Blueprint from that repository. `render.yaml` defines
   a free Python web service. Supply `DATABASE_URL` when prompted with the
   target Neon URL and its SSL parameters.
4. Confirm the build installs requirements and startup applies migrations.
5. Check `/`, then create and retrieve a test purchase through `/docs`.

For manual Web Service setup, use the build and start commands from
`render.yaml`, select Free, and set `DATABASE_URL` in Render's environment.
Render reads the Python version from `.python-version`.

The start command runs migrations before Uvicorn and stops if migrations fail.
This is intended for the initial single-instance free deployment. Before
scaling to multiple instances, move migrations to a single release job.
Free Render services sleep after inactivity.

An empty database needs `alembic upgrade head`. An existing database with
untracked tables must first be compared with the baseline before stamping
the matching revision; do not run initial table creation over existing tables.

## Future schema changes

With dev at the current migration head, edit models and run:

```bash
alembic revision --autogenerate -m "Describe schema change"
```

Review the generated operations, apply and test in dev, then commit the new
migration alongside the model change. Deploy the same migration files to each
environment. Do not rewrite migrations already deployed.

`requirements.txt` pins the complete currently installed dependency set,
including transitive dependencies. Update dependencies deliberately in the
virtual environment, run tests, and review a refreshed `pip freeze` snapshot.
