# RblXLua Bot

A feature-rich Discord bot for Lua deobfuscation, obfuscation, ticket management, verification with Cloudflare Turnstile, active checks, auto-delete, and administrative utilities.

---

## Features

- **Lua Deobfuscation** – Fetch code from a link, attachment, or reply and run multi‑layer deobfuscation (Prometheus, WeAreDevs, enhanced fallback). Displays preview and optionally sends file.
- **Lua Obfuscation** – Obfuscate Lua source code with a stable Prometheus-style single-base64 chunk.
- **Ticket System** – Persistent ticket panels with custom roles, claim functionality, and closing.
- **Verification System** – Restrict server access until users verify via a button. Supports optional countdown deadline. Also includes a standalone web page with Cloudflare Turnstile (ads verification) that calls the bot's API to assign the Verified role automatically.
- **Active Checker** – Periodically ping @everyone in a specified channel to check user activity.
- **Auto-Delete Messages** – Instantly delete all messages in chosen channels.
- **Bypass Utility** – Extract keys from obfuscated URLs (Delta‑style).
- **Slash & Prefix Commands** – Modern slash commands and traditional prefix commands (`.`).
- **Command Channel Restriction** – Limit commands to a single text channel (with owner bypass).
- **MongoDB Persistence** – All settings and logs are stored in MongoDB.
- **Web Verification** – A clean, branded verification page using Cloudflare Turnstile as an "ad" step. Users enter their Discord ID, complete the Turnstile challenge, and get verified instantly in the server.

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
| `/verify_system` | Set up verification system. Optional `duration` (e.g., `1d`, `12h`, `30m`) to set a countdown deadline. When the deadline expires, all unverified members get the **Not Verified** role. | Administrator |
| `/active_checker` | Set up a periodic @everyone ping in a channel. | Administrator |
| `/bypass` | Extract a key from a URL (Delta‑style bypass). | None |
| `/auto_delete_messages` | Add a text channel to auto‑delete all new messages. | Administrator |
| `/atd_view_channel` | View all channels currently set for auto‑deletion. | None |
| `/atd_remove_channel` | Remove a channel from auto‑deletion. | Administrator |

---

## Verification Website

The bot includes a standalone verification web page (`index.html`) that integrates Cloudflare Turnstile as an "ads verification" step.

- Users visit the page, enter their Discord User ID, and complete the Turnstile challenge.
- Upon success, the page sends a POST request to the bot's `/api/verify` endpoint.
- The bot validates the Turnstile token (using the secret key) and assigns the **Verified** role to the user in the configured guild.
- If the user already has the Verified role, the API returns an error message (prevents double verification).

### Web Page Setup

1. Upload `index.html` to your static hosting (e.g., Cloudflare Pages, Netlify, Vercel).
2. Ensure the page's `fetch` URL points to your bot's public endpoint (e.g., `https://your-bot-domain.com/api/verify`). The provided HTML uses a relative path `/api/verify` – if your bot runs on the same domain, it will work; otherwise, you need to adjust the `apiUrl` in the JavaScript.
3. The bot must have the environment variables `TURNSTILE_SECRET_KEY` and `GUILD_ID` set (see Setup below).

---

## Setup

### 1. Prerequisites

- Python 3.9 or higher
- A MongoDB database (Atlas or self‑hosted)
- A Discord Bot Token
- Cloudflare Turnstile site key and secret key (for the web verification)
- (Optional) Lua interpreter for Prometheus deobfuscation (falls back to other methods if not available)

### 2. Environment Variables

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

Clone the repository and install dependencies:

```bash
git clone https://github.com/yourusername/rblxlua-bot.git
cd rblxlua-bot
pip install -r requirements.txt
```

Requirements (`requirements.txt`):

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

The bot will start a Flask web server on port 10000 (for health checks) and the Discord client. The `/api/verify` endpoint will be available at that port.

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

---

## Customization

- **Deobfuscation** – Modify the `PROMETHEUS_DEOBF_LUA` template or the `deobfuscate_code` fallback logic.
- **Verification deadline** – The bot checks every minute; you can change the interval in `check_verification_deadlines()`.
- **Web verification** – Adjust the Turnstile site key in `index.html` and the API endpoint URL if needed.

---

## Support

For issues or feature requests, open an issue on GitHub or contact the bot owner.

---

## License

This project is provided as‑is. Use at your own risk.
