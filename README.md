# RblXLua Bot

A feature‑rich Discord bot for Lua deobfuscation, obfuscation, ticket management, verification with Cloudflare Turnstile and gender selection, active checks, auto‑delete, and administrative utilities.

---

## Features

- **Lua Deobfuscation** – Fetch code from a link, attachment, or reply and run multi‑layer deobfuscation (Prometheus, WeAreDevs, enhanced fallback). Displays preview and optionally sends file.
- **Lua Obfuscation** – Obfuscate Lua source code with a stable Prometheus‑style single‑base64 chunk.
- **Ticket System** – Persistent ticket panels with custom roles, claim functionality, and closing.
- **Verification System** – Restrict server access until users verify via a website.  
  - **Intro Animation** – A cinematic lock‑and‑key animation on page load.  
  - **Gender Selection** – Users choose Girl, Gay, or Boy; selection is saved in `localStorage` and never shown again.  
  - **Cloudflare Turnstile** – “Ads verification” step.  
  - **Real‑time Verified Users List** – Shows avatars, display names, timestamps, and gender icons (Girl, Gay, Boy).  
  - **24‑hour Deadline** – Automatic countdown; unverified members receive the **Not Verified** role after the deadline.  
  - **Re‑verification** – If a user loses the Verified role, they can verify again.
- **Active Checker** – Periodically ping @everyone in a specified channel to check user activity.
- **Auto‑Delete Messages** – Instantly delete all messages in chosen channels.
- **Bypass Utility** – Extract keys from obfuscated URLs (Delta‑style).
- **Slash & Prefix Commands** – Modern slash commands and traditional prefix commands (`.`).
- **Command Channel Restriction** – Limit commands to a single text channel (with owner bypass).
- **MongoDB Persistence** – All settings, logs, tickets, and verification records (including gender) are stored in MongoDB.

---

## Commands

### Prefix Commands (`.`)

| Command | Description |
|---------|-------------|
| `.get` | Fetch and deobfuscate code from a URL, attachment, or reply. Displays cleaned code with preview/file. |
| `.obf` | Obfuscate Lua code using Prometheus (single base64 chunk). Accepts link, attachment, or pasted code. |
| `.cmds` | Show this help menu (paginated). |
| `.db status` | Check MongoDB connection status. |
| `.db clear` | (Owner only) Clear all stored data. |
| `.ping` | Check bot latency (prefix version). |

### Slash Commands (`/`)

| Command | Description | Required Permissions |
|---------|-------------|----------------------|
| `/ping` | Check bot latency. | None |
| `/channel_set` | Restrict all prefix commands to a specific channel. | Administrator |
| `/channel_view` | Show the currently restricted channel. | None |
| `/channel_clear` | Remove the channel restriction. | Administrator |
| `/ticket` | Create a ticket panel with custom roles, claim button, embed color, etc. | Administrator |
| `/verification_system` | Set up verification system. **Automatically sets a 24‑hour countdown deadline**. The embed shows a timestamp; when it expires, all unverified members get the **Not Verified** role. The message includes a **Verify on Website** link button. | Administrator |
| `/active_checker` | Set up a periodic @everyone ping in a channel. | Administrator |
| `/bypass` | Extract a key from a URL (Delta‑style bypass). | None |
| `/auto_delete_messages` | Add a text channel to auto‑delete all new messages. | Administrator |
| `/atd_view_channel` | View all channels currently set for auto‑deletion. | None |
| `/atd_remove_channel` | Remove a channel from auto‑deletion. | Administrator |

---

## Verification Website

The verification website is a **single HTML file** with a modern, smooth, and animated experience:

- **Intro Animation** – A realistic lock‑and‑key SVG animation that plays on first visit.
- **Gender Selection** – Users select their gender (Girl, Gay, Boy). The choice is saved in `localStorage` and never asked again.
- **Cloudflare Turnstile** – The “ads verification” challenge (sitekey included). The Verify button is disabled until the challenge is passed and a User ID is entered.
- **Verification API** – The page sends a POST request to `/api/verify` with `user_id`, `cf_token`, and `gender`. The bot validates the token, assigns the Verified role, and stores the gender in the `verified_users` collection.
- **Real‑time User List** – The verified users list is refreshed every 15 seconds and shows each user’s avatar, display name, username, verification timestamp, and a gender icon (Girl, Gay, Boy) with distinct colors.

The website is fully self‑contained – no external dependencies besides the Turnstile script.

---

## Setup

### 1. Prerequisites

- Python 3.9 or higher
- A MongoDB database (Atlas or self‑hosted)
- A Discord Bot Token
- Cloudflare Turnstile site key and secret key (for the web verification)

### 2. Environment Variables

Set these on your hosting platform (e.g., Render):

| Variable | Description |
|----------|-------------|
| `TOKEN` | Your Discord bot token. |
| `MONGODB_URI` | MongoDB connection string. |
| `TURNSTILE_SECRET_KEY` | Cloudflare Turnstile secret key. |
| `GUILD_ID` | Your Discord server ID (integer). |

Example:

```bash
export TOKEN="your_discord_bot_token"
export MONGODB_URI="mongodb+srv://user:pass@cluster.mongodb.net/"
export TURNSTILE_SECRET_KEY="0x4AAAAAAEKmf0BjB9dr0YMk5Mc4zGOd-pw"
export GUILD_ID="123456789012345678"
```

### 3. Installation

```bash
git clone https://github.com/yourusername/rblxlua-bot.git
cd rblxlua-bot
pip install -r requirements.txt
```

`requirements.txt`:

```
discord.py
aiohttp
pymongo
requests
flask
beautifulsoup4
lxml
```

### 4. Running the Bot

```bash
python main.py
```

The bot will start a Flask web server on port `10000` (for health checks and the `/api/verify` and `/api/verified_users` endpoints) and the Discord client.

---

## Permissions Required

- **Manage Roles** – For verification and ticket role assignments.
- **Manage Channels** – For ticket creation and verification channel permission overrides.
- **View Channel / Send Messages** – To function in designated channels.
- **Read Message History** – For ticket and verification message updates.
- **Manage Messages** – For auto‑delete functionality.
- **Administrator** – Recommended for setup commands.

---

## Database Collections

- `settings` – Command channel restriction.
- `usage_logs` – Logs of `.get`, `.obf`, etc.
- `tickets` – Open/closed ticket data.
- `ticket_panels` – Configuration for each ticket panel.
- `verification_config` – Verification role, channel, message ID, deadline, and processed flag.
- `active_checker_config` – Active checker interval and channel.
- `auto_delete_config` – Channel IDs for auto‑deletion.
- `verified_users` – Records of successful verifications: `guild_id`, `user_id`, `verified_at`, `verified_by`, and `gender` (string).

---

## Customization

- **Deobfuscation** – Modify the `PROMETHEUS_DEOBF_LUA` template or the `deobfuscate_code` fallback logic.
- **Verification deadline** – The bot uses a fixed 24‑hour deadline; you can change `DEFAULT_VERIFICATION_DURATION` in the code to any value in seconds.
- **Web verification** – Adjust the Turnstile site key in `index.html` and the API endpoint URL in the JavaScript if needed.
- **Gender icons** – Edit the SVG markup in `index.html` to change the look of the Girl, Gay, and Boy icons.
- **User cache TTL** – Modify `USER_CACHE_TTL` (in seconds) to control how often Discord user data is refreshed.

---

## Support

For issues or feature requests, open an issue on GitHub or contact the bot owner.

---

## License

This project is provided as‑is. Use at your own risk.
