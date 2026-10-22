# Errors2Experts Weekly Workshops (Django)

A Django website for weekly workshops. **Registrations are stored only in one Excel file** (`data/registrations.xlsx`). No Google Sheets.

What is stored where:

| Data | Where |
|---|---|
| Student registrations | `data/registrations.xlsx` only |
| Workshops (title, date, poster...) and admin logins | A small file `db.sqlite3` that Django needs. It holds **no** registrations. |
| Poster images | `media/` folder |

## Run it on Windows (step by step)

1. **Install Python** from python.org (version 3.10 or newer). On the first installer screen, tick **"Add python.exe to PATH"**.
2. Unzip the project, open a terminal inside the folder (`e2e_django`).
3. Create a private Python environment and install the libraries:
   ```
   py -m venv venv
   venv\Scripts\activate
   pip install -r requirements.txt
   ```
   (Run `venv\Scripts\activate` again every time you open a new terminal.)
4. Copy `.env.example` and rename the copy to `.env`. Leave `DEBUG=True` for now.
5. Create the database and your admin login:
   ```
   python manage.py migrate
   python manage.py createsuperuser
   ```
6. Start the site:
   ```
   python manage.py runserver
   ```
7. Open http://127.0.0.1:8000/admin/ and sign in.

## New in this version

| Feature | How to use it |
|---|---|
| **Weekly payment QR** | In the admin, open the workshop, section *Fee and payment QR*. Set the **Fee** (for example 9) and upload that week's **Payment QR image**. If you leave the image empty, the site makes a UPI QR from the **UPI ID** and the fee. Each workshop has its own, so next week you set a new fee and QR on the new workshop. A fee of 0 or blank means free: no payment step. |
| **Registration with payment** | Student fills the details, taps **Continue to payment**, sees the QR and amount, pays, attaches the **screenshot**, and submits. Screenshots are kept privately in `data/payments/` and open only for signed-in staff (the **Screenshot** link in Registrations). The Excel file gets a `payment_screenshot` column. |
| **Previous workshop photos and feedback screenshots** | Admin, open a workshop, scroll to the photo rows at the bottom: pick *Students at the workshop* or *Student feedback screenshot*, upload, add several at once. Or use **Gallery images** in the admin. They appear on the home page under *Our previous workshops* and *What students say*. |
| **Feedback form** | `/feedback/` (also in the menu and on completed workshops). Fields: workshop, name, official email ID, 1 to 5 star rating, feedback. One feedback per email per workshop. Name, rating and text show on the home page; the email never does. |
| **Delete feedback** | Sign in, **Dashboard**, **Feedback** tab, **Delete** (asks to confirm). In the Django admin you can also *hide* feedback without deleting it. |

## Latest changes (v4)

| Feature | Where / how |
|---|---|
| **Certificate Yes/No in the registration form** | If the workshop has a fee and "Fee is for the certificate" is ticked (default), the form asks *Do you want a certificate?* **Yes** shows the payment QR, amount and screenshot upload. **No** just submits the registration, nothing to pay. Untick that box in the workshop (Admin) if everyone must pay. |
| **Amounts** | Dashboard shows *Amount verified* and *Amount waiting*. Dashboard, **Payments** shows totals per workshop and every payment with its screenshot and Verify button. |
| **Certificate ID** | Certificates, Edit certificate, *Certificate ID*: type the first ID, for example `E2E/WS/2026/500`. The first certificate gets 500, then 501, 502 ... printed on the certificate (move it with the position boxes) and shown in the email. A resend keeps the same number. |
| **Students page** | New filters: *Confirmation email* (sent / not sent), *Certificate* (wants / does not want), Payment. Each row has **Upload screenshot** so you can add a payment screenshot by hand. |
| **QR for any link** | Dashboard, **QR codes**, top box: paste a link, click Generate, download the PNG. |
| **Announce** | Write your own subject and message (`{name}` becomes the student's name), attach several brochures, save, send yourself a test, then send in batches. Students who attended earlier AND registered for the new workshop are never emailed, and nobody gets it twice. |
| **Countdown** | Home page and workshop page show days, hours, minutes and seconds until registration closes. It turns red in the last 24 hours. |
| **Seats blinking + alert** | The seats-left badge pulses, and blinks when 5 or fewer remain. When the last seat is taken, an email goes to `ADMIN_NOTIFY_EMAIL`. |
| **Posters** | Posters are never cropped now: the whole poster is shown on a soft blurred background, on the home page, workshop cards and the details page (which has a new tidy layout). |
| **Confirmation email** | Sent to the student's email as soon as registration is saved (needs the Gmail settings in `.env`). |

After upgrading run `python manage.py migrate` (migration 0004). Existing workshops that have a fee will now show the Yes/No question; untick *Fee is for the certificate* on a workshop to make the fee compulsory again.

## New in this version: certificates, one Students page, announcements

| Feature | How to use it |
|---|---|
| **Registration form = your Google Form** | The website form now asks everything your Google Form asks: name, email, phone, address, college, qualification, current status, where they heard about it, interest, skill level, free demo class choices, queries, referred by, consent. Everything goes to new columns in `data/registrations.xlsx`. |
| **Students page** (`/dashboard/registrations/`) | One page for payment, feedback and certificate. Tick **Payment verified** (it saves by itself). The **Feedback** column shows a green tick once that student has submitted feedback. The **Certificate** column shows Waiting / Ready / Sent, with Send now, Resend and View. |
| **Automatic certificate** | Emailed (PDF attached) when the workshop has a certificate template, has started, the payment is verified (or the workshop is free) and the student has submitted feedback using the same email they registered with. It is checked when you tick the box and when the student submits feedback. Each certificate is sent once. |
| **Certificate per workshop** | Dashboard, **Certificates**, **Upload certificate** for that workshop. Upload the blank template (JPG or PNG), move the name until the live preview looks right, save. Use **Email me a sample certificate** to test. A new workshop = a new template. |
| **Announce a new workshop** | Dashboard, **Announce**, pick the workshop, **Send me a test first**, then **Send next 40** (repeat for more). Goes to people who registered for earlier workshops, once each, with an unsubscribe link. |
| **Gallery** | `/gallery/` shows all workshop photos and feedback screenshots in an aligned grid. |

Command-line versions: `python manage.py send_certificates` (add `--dry-run` to only count) and `python manage.py announce_workshop <workshop id>`.

The full weekly routine is in **PROCEDURE.md**.

After upgrading an existing install run `python manage.py migrate` once. Old registrations keep working: rows saved before payment checking existed show as To check (if they have a screenshot) or Free.

## Create the first workshop

1. In the admin, click **Workshops**, then **Add workshop**.
2. Fill in the title, description, poster, start and end times (India time), mode, venue or meeting link, seat limit and so on. Set **Status** to *Published* and tick **Featured** to show it on the home page.
3. Use the **Preview** link in the list before publishing (staff can see drafts).
4. Open http://127.0.0.1:8000/register/ and submit a test registration.
5. Open http://127.0.0.1:8000/dashboard/ to see it. The Excel file is at `data/registrations.xlsx`.

Weekly routine: add the new workshop, publish it, tick Featured. Set the old one to Closed or let it expire (past workshops close automatically). The permanent QR never changes.

## Where to find things

| What | Address |
|---|---|
| Home, Workshops, Register | `/`, `/workshops/`, `/register/` |
| Workshop admin (create, edit, publish, archive, feature, open/full/closed) | `/admin/` |
| Registrations dashboard, search, filters, Excel and CSV download, email retry | `/dashboard/` |
| QR codes (permanent and per workshop, PNG download and print) | `/dashboard/qr/` |

After a student submits, they see a thank-you page and are sent to `POST_SUBMIT_REDIRECT_URL` (default https://errors2experts.com/) after 12 seconds, or at once with a button.

## Important: the Excel file

- **Do not open `data/registrations.xlsx` in Excel while students are registering.** Windows locks the file and the website will refuse to save and show an error (nothing is lost and no false "success" is shown). Use **Download Excel** on the dashboard instead; it makes a separate copy.
- Saves are protected by a file lock, so two students at the same moment will not overwrite each other. Duplicate emails and seat limits are checked inside that lock.
- Everything is stored as text, so nothing typed into the form can run as an Excel formula.
- **Back up the file regularly** (copy it somewhere safe). It is the only copy of your registrations.
- It is meant for one server. Do not run two copies of the site that both write to the same file.

## Email (confirmation to student and alert to you)

1. Use the official Gmail account. Turn on 2-Step Verification.
2. Google Account, Security, App passwords: create one.
3. In `.env` set `EMAIL_HOST_USER` (the Gmail address), `EMAIL_HOST_PASSWORD` (the app password) and `ADMIN_NOTIFY_EMAIL`.
4. Restart the server.

Emails are sent only after the registration is saved in Excel. If sending fails, the registration stays, the Excel column `email_status` says `failed: ...`, and the dashboard shows a **Retry** button. Retry never sends a second email once it has been sent. Gmail allows roughly 500 sends a day.

## Logo and brand

The theme uses the logo's own colours: red (E), gold (2) and green (E), with a serif display font like the logo lettering, and a red-gold-green rule under the header.

- Logo files are in `static/img/`: `logo.png` (full logo, footer), `logo-mark.png` (E2E mark, header), `favicon.png` (browser tab and QR centre).
- Colours are at the top of `static/css/styles.css` (`--e2e-red`, `--e2e-gold`, `--e2e-green`).
- Institute details and social links are in `.env` (`ORG_*`, `SOCIAL_*`).

## QR codes

- The permanent QR points to `SITE_URL/register/`. It always shows the open workshop(s), so it never needs reprinting.
- **Set `SITE_URL` in `.env` to your real public address before printing.** A QR made with `127.0.0.1` will not work on phones.
- Test the printed QR with one Android and one iPhone camera before printing many.

## Put it online (PythonAnywhere, free plan works for small use)

1. Create an account at pythonanywhere.com.
2. Upload the project (zip it, upload under Files, unzip in the Bash console) to `/home/YOURNAME/e2e_django`.
3. In a Bash console:
   ```
   cd ~/e2e_django
   python3 -m venv venv && source venv/bin/activate
   pip install -r requirements.txt
   cp .env.example .env
   nano .env
   ```
   In `.env` set: `DEBUG=False`, a long random `SECRET_KEY`, `ALLOWED_HOSTS=YOURNAME.pythonanywhere.com`, `CSRF_TRUSTED_ORIGINS=https://YOURNAME.pythonanywhere.com`, `SITE_URL=https://YOURNAME.pythonanywhere.com`, plus the email settings.
4. Then:
   ```
   python manage.py migrate
   python manage.py createsuperuser
   python manage.py collectstatic --noinput
   ```
5. Web tab, Add a new web app, Manual configuration, same Python version. Set the virtualenv path to `/home/YOURNAME/e2e_django/venv`.
6. Edit the WSGI file: replace its contents with
   ```python
   import os, sys
   sys.path.insert(0, '/home/YOURNAME/e2e_django')
   os.environ['DJANGO_SETTINGS_MODULE'] = 'config.settings'
   from django.core.wsgi import get_wsgi_application
   application = get_wsgi_application()
   ```
7. Click **Reload**. Open your address. Your registrations file will be at `/home/YOURNAME/e2e_django/data/registrations.xlsx` (download it from the Files tab or the dashboard).

Static files are served by the app itself. Poster images are served by Django too, which is fine for a small site.

## Tests

```
python manage.py test workshops
```
The automated tests cover payment screenshots, the weekly QR, the Google-form fields, certificates (payment tick, feedback, resend, failure), announcements and unsubscribe, feedback and the gallery, plus registration, validation, duplicates, seat limits, expiry, spam checks, Excel contents, a locked Excel file, email failure and retry, staff-only pages, exports and QR codes.

## Troubleshooting

| Problem | Fix |
|---|---|
| "Settings not found" | Copy `.env.example` to `.env` |
| `python` or `pip` not recognised | Reinstall Python and tick "Add python.exe to PATH", or use `py` instead of `python` |
| Student sees "file is open in Excel" | Close Excel. Use Download Excel on the dashboard instead |
| Email status shows `failed` | Check `EMAIL_HOST_USER`, the App Password, and that 2-Step Verification is on; then use Retry |
| 403 on forms when live | Set `CSRF_TRUSTED_ORIGINS` to your https address |
| Styles missing when live | Run `collectstatic` and reload |
| QR opens a wrong or local address | Set `SITE_URL` in `.env` and restart |
| Dates look wrong | Enter times in India time; the site uses Asia/Kolkata |
| Certificate stays "Waiting for feedback" | The student must use the same email in the feedback form as in registration. Use **Send anyway** if they used a different one |
| Name not centred on the certificate | Certificates page, Edit certificate: change the two position numbers and watch the preview |
| Student name in Tamil shows as boxes | The bundled fonts have Latin letters only. Put a Tamil-capable `.ttf` in `static/fonts` and choose it on the certificate page |

## Not verified yet

The certificate drawing and the "send only once" logic were run and checked outside Django. The pages, forms, emails and the new automated tests were written carefully but **not run**: run `python manage.py migrate` and `python manage.py test workshops` first and tell me anything that fails. Also **not yet tested:** real Gmail sending, a real phone scanning the QR code, PythonAnywhere deployment, and how the pages look in your browser.
