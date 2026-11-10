# Free email sending with Google Apps Script

This project can send OTP and fraud-alert emails through a Google Apps Script
web app. It sends from the Google account that authorizes the script, so it
doesn't need a custom domain or Gmail SMTP App Password. A personal Google
account currently has a quota of 100 email recipients per day; Google can
change quotas at any time.

## 1. Create the Apps Script project

1. Sign in to the Google account that should send the project's emails.
2. Open [script.google.com](https://script.google.com/) and create a new project.
3. Replace the editor's contents with [`Code.gs`](./Code.gs), then save.
4. Open **Project Settings** (gear icon), find **Script properties**, and add:
   - Property: `APP_SHARED_SECRET`
   - Value: a new, long random secret

Generate a secret on your computer with:

```sh
python3 -c 'import secrets; print(secrets.token_urlsafe(32))'
```

Keep this value private. Use the same value for the Apps Script property and
the Vercel `APPS_SCRIPT_SECRET` environment variable. Do not put it in the
browser or in the frontend source.

## 2. Authorize and deploy the web app

1. In the Apps Script editor, select and run `authorizeMail` once. Approve
   Google's permission prompt so the script can send email.
2. Choose **Deploy → New deployment**.
3. Choose **Web app** as the deployment type.
4. Set **Execute as** to **Me**.
5. Set **Who has access** to **Anyone**, then deploy and approve the requested
   permissions.
6. Copy the deployed web app URL ending in `/exec`.

This public endpoint checks the shared secret before sending anything. Keep
that secret only in the Apps Script property and server-side Vercel settings.
If a school-managed Google account does not offer **Anyone**, use a personal
Google account or its administrator may need to allow anonymous web apps.

## 3. Configure Vercel

Open the Vercel project's **Settings → Environment Variables** and add these
for **Production** (and **Preview** if you want to use preview deployments):

| Name | Value |
| --- | --- |
| `EMAIL_PROVIDER` | `apps_script` |
| `APPS_SCRIPT_URL` | The deployed `/exec` URL |
| `APPS_SCRIPT_SECRET` | The same random secret saved as `APP_SHARED_SECRET` |
| `OTP_MODE` | `email` |
| `FLASK_SECRET_KEY` | A separate long random secret for Flask sessions |

Save the variables and redeploy the Vercel project. A deployment doesn't pick
up environment variable changes made after it was created.
