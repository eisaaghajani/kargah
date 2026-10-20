Workshop Manager — Agricultural Workshop Management
A Persian-first web application for managing agricultural workshops.
Track daily work, workers, materials, income, expenses, crop stages,
and generate financial reports.

Features
Multi-workshop & multi-year — manage several workshops, each with multiple farming years

Daily work log — register activities, number of workers, wages, food costs

Materials tracking — record fertilizer, pesticide and other material usage per activity, with prices captured at the moment of use

Income & expense ledger — custom income types and expense categories per workshop

Financial reports — date-range reports, monthly breakdown, year-over-year comparison

CSV export — download reports as UTF-8 CSV (opens correctly in Excel)

Photo archive — document crop stages (dormancy, pruning, flowering, harvest, …) with photos and notes

Free / Pro plan — free plan includes 30 photos; Pro plan is unlimited, activated via license codes

Audit-friendly — all records are timestamped; backup & restore from the account page

RTL Persian UI — built for Persian users, using the Vazir font

Responsive — works on desktop, tablet and mobile

Tech Stack
Layer Technology
Backend Flask 2.3, SQLAlchemy, Flask-Login
Database SQLite
Templating Jinja2
Frontend Vanilla JavaScript, Bootstrap RTL, Vazir font
Persian calendar jdatetime
Image processing Pillow
Icons Font Awesome
Run with Docker (Recommended)
The fastest way to run the app without installing Python or dependencies manually:

Make sure you have Docker Desktop installed.

Clone the repository:
git clone https://github.com/eisaaghajani/kargah.git
cd kargah

Make a copy of .env.example and name it .env, then generate a SECRET_KEY inside it.

Start the container:
docker compose up -d --build

Open http://localhost:5011 in your browser.

Note: Database files and uploaded photos are automatically persisted in the instance/ folder on your host machine (via Docker Volume).

Installation (Manual)
Requirements
Python 3.9+

pip

Steps
Clone the repository:
git clone https://github.com/eisaaghajani/kargah.git
cd kargah

Create a virtual environment:
python -m venv venv

Activate it:

On Windows: venv\Scripts\activate

On macOS / Linux: source venv/bin/activate

Install dependencies:
pip install -r requirements.txt

Create your .env from the example:

On Windows: copy .env.example .env

On macOS / Linux: cp .env.example .env

Generate a SECRET_KEY and put it in .env:
python -c "import secrets; print(secrets.token_hex(32))"

Run the app:
python app.py

The app will be available at http://localhost:5011.

On first run, you will be redirected to /setup to create the owner account.

First Steps
Open http://localhost:5011 — you'll be redirected to /setup

Create the owner account (name, email optional, password)

You'll land on the Workshops page — click "کارگاه جدید" to create your first workshop

Add one or more farming years (e.g. 1404-1405)

You'll be redirected to the dashboard — explore the tiles:

کار روزانه — daily work log

درآمد — income

هزینه — expenses

گزارش مالی — financial reports

آرشیو — photo archive

مدیریت — workshop settings (activities, materials, years)

Configuration
All configuration is via environment variables (see .env.example):

Variable Default Description
SECRET_KEY auto-generated Flask session signing key. Change in production.
ALLOW_REGISTER 0 Set to 1 to allow public registration
BEHIND_PROXY 0 Set to 1 when behind nginx / a reverse proxy
COOKIE_SECURE 0 Set to 1 when serving over HTTPS
ALLOWED_ORIGINS (empty) Comma-separated list of extra allowed origins (for CORS)
License
Portfolio and educational purposes.
For commercial use, please contact the author.

Author & Company
Eisa Aghajani

GitHub: @eisaaghajani

Email: eisa.aghajani@gmail.com

Parseh Pardazeshgar Rayka Tak

Website: pprt.ir
