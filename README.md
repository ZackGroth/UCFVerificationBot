# UCFVerificationBot

A Discord verification bot customized for **University of Central Florida (UCF)** communities.  
Users verify their membership using a UCF email address and are automatically granted access to the server upon successful verification.

This bot is designed for large student servers where role-based access control and domain-restricted verification are required.

---

## How It Works

1. A user joins the Discord server and is given access to limited channels.
2. The user submits their institutional email using a bot command:	!email example@ucf.edu
3. The bot sends a short verification code to the provided email address.
4. The user submits the code in Discord:	!verify 1234
5. If the code is valid, the bot assigns a configured role granting full server access.

---

## Features

- Domain-restricted email verification  
- Configurable verified role  
- Modular command structure  
- Docker and non-Docker deployment support  
- Admin and moderation utilities  
- Optional manual verification for moderators  

---

## Setup

### Requirements

- Python **3.7+**
- A Discord bot token
- Access to an SMTP email account for sending verification codes

---

### Environment Variables

Create a `.env` file in the project root (**do not commit this file**) and configure the required values:

DISCORD_TOKEN=your_bot_token
EMAIL_DOMAIN=ucf.edu
SMTP_HOST=your.smtp.server
SMTP_PORT=587
SMTP_USER=your_email@domain
SMTP_PASS=your_email_password
VERIFIED_ROLE_ID=discord_role_id

Additional variables may be required depending on configuration.

---

## Run Locally (Python)

```bash
python -m venv venv
.\venv\Scripts\activate
pip install -r requirements.txt
python bot.py

## Docker (Recommended)

Ensure **Docker** and **Docker Compose** are installed.

1. Edit `docker-compose.yml` and set your environment variables.
2. Build and start the container:

    docker compose build  
    docker compose up -d

---

## Required Discord Permissions

The bot requires the following permissions:

- Manage Server
- Manage Roles
- View Channels
- Send Messages
- Manage Messages
- Read Message History
- Add Reactions

Ensure role hierarchy is configured correctly or verification will fail.

---

## Commands

| Command | Description | Permission |
|-------|------------|------------|
| vhelp | Displays usage instructions | None |
| email `<email>` | Sends verification email | None |
| verify `<code>` | Verifies user | None |
| uptime | Shows bot uptime | None |
| activetokens | Lists pending verifications | None |
| prune `<n>` | Deletes recent messages | Manage Server |
| modverify `<email>` `<user_id>` | Manual verification | Manage Server |
| reactoradd | Adds reaction role | Manage Server |
| reactordelete | Removes reactors | Manage Server |
| reactorget | Lists reactors | Manage Server |
| reactorclearall | Clears all reactors | Manage Server |

---

## Security Notes

- **Never commit** `.env` files or credentials
- Rotate tokens immediately if exposed
- Limit bot permissions to only what is required
- Audit role assignment behavior carefully

---

## Attribution

This project is derived from **VerificationBot**, originally developed for the UVic Engineering & Computer Science Discord community and later contributors.

The codebase has been modified and extended for UCF-specific use cases, configuration, and deployment.

Original project and contributors are credited in accordance with the license.

---

## License

This project is licensed under the **GNU General Public License v3.0 (GPL-3.0)**.  
See the `LICENSE` file for full terms.

---

## Disclaimer

This project is **not affiliated** with Discord or the University of Central Florida.


