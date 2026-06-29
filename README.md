# Run the GUI without Docker

The GUI runs locally with Python. The full ETL/DW/ML pipeline still needs
PostgreSQL, but you install and start PostgreSQL yourself; the app only checks
the connection and may create `PSQL_DBNAME` when your user has permission.

## Windows

```powershell
py -m venv .venv
.venv\Scripts\activate
py -m pip install --upgrade pip
py -m pip install -r requirements.txt
```

Install PostgreSQL from the official Windows installer, then edit `.env`:

```env
PSQL_HOST=localhost
PSQL_PORT=5432
PSQL_USER=postgres
PSQL_PASSWORD=your_real_password
PSQL_DBNAME=staging
```

Replace `your_real_password` with the password you set during PostgreSQL
installation.

Run the GUI:

```powershell
py -m pipeline_frontend_gui.run
```

## Linux

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

PostgreSQL install example for Debian/Ubuntu:

```bash
sudo apt install postgresql postgresql-contrib
sudo systemctl enable --now postgresql
sudo -u postgres psql -c "ALTER USER postgres PASSWORD 'your_real_password';"
```

Edit `.env`:

```env
PSQL_HOST=localhost
PSQL_PORT=5432
PSQL_USER=postgres
PSQL_PASSWORD=your_real_password
PSQL_DBNAME=staging
```

Replace `your_real_password` with the password you set in the `ALTER USER`
command.

Run the GUI:

```bash
python -m pipeline_frontend_gui.run
```

## Checks

```bash
python -m pipeline_frontend_gui.selfcheck
```

If `PSQL_DBNAME` does not exist, the app tries to create it. If PostgreSQL
refuses that, create it manually:

```bash
createdb -h localhost -p 5432 -U postgres staging
```
