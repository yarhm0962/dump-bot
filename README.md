# RblXLua Bot

A feature‑rich Discord bot for Lua deobfuscation, obfuscation, ticket management, verification with Cloudflare Turnstile, active checks, auto‑delete, and administrative utilities.

---

## Features

- **Lua Deobfuscation** – Fetch code from a link, attachment, or reply and run multi‑layer deobfuscation (Prometheus, WeAreDevs, enhanced fallback). Displays preview and optionally sends file.
- **Lua Obfuscation** – Obfuscate Lua source code with a stable Prometheus‑style single‑base64 chunk.
- **Ticket System** – Persistent ticket panels with custom roles, claim functionality, and closing.
- **Verification System** – Restrict server access until users verify via a link button. Supports optional countdown deadline.  
  - A standalone web page with Cloudflare Turnstile (ads verification) calls the bot’s API to assign the Verified role.  
  - Verification records are stored in MongoDB (`verified_users` collection).  
  - If a user loses the Verified role (e.g., manually removed), they can re‑verify through the website – the bot allows it and updates the record.  
  - The website includes a real‑time list of verified users with avatars, display names, and timestamps.
- **Active Checker** – Periodically ping @everyone in a specified channel to check user activity.
- **Auto‑Delete Messages** – Instantly delete all messages in chosen channels.
- **Bypass Utility** – Extract keys from obfuscated URLs (Delta‑style).
- **Slash & Prefix Commands** – Modern slash commands and traditional prefix commands (`.`).
- **Command Channel Restriction** – Limit commands to a single text channel (with owner bypass).
- **MongoDB Persistence** – All settings, logs, tickets, and verification records are stored in MongoDB.

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
| `/verify_system` | Set up verification system. Optional `duration` (e.g., `1d`, `12h`, `30m`) to set a countdown deadline. When the deadline expires, all unverified members get the **Not Verified** role. The message includes a **Verify on Website** link button. | Administrator |
| `/active_checker` | Set up a periodic @everyone ping in a channel. | Administrator |
| `/bypass` | Extract a key from a URL (Delta‑style bypass). | None |
| `/auto_delete_messages` | Add a text channel to auto‑delete all new messages. | Administrator |
| `/atd_view_channel` | View all channels currently set for auto‑deletion. | None |
| `/atd_remove_channel` | Remove a channel from auto‑deletion. | Administrator |

---

## Verification Website

The bot includes a standalone verification web page with a modern, lightweight design. The main HTML file is under 2 KB; all CSS, JavaScript, and SVG icons are loaded as separate assets.

- Users visit the page, enter their Discord User ID, and complete the Turnstile challenge.
- Upon success, the page sends a POST request to the bot’s `/api/verify` endpoint.
- The bot validates the Turnstile token (using the secret key) and assigns the **Verified** role to the user in the configured guild.
- If the user already has the Verified role, the API returns an error message (prevents double verification while the role is present).
- If the role is later removed (by an admin), the user can verify again – the role check will pass and a new record will be added.
- All successful verifications are stored in the MongoDB `verified_users` collection.
- The website automatically shows a real‑time list of verified users with avatars, display names, and timestamps.

### Website File Structure

The verification website consists of the following files (all served from the root of your Cloudflare Pages project):

```
/
├── index.html      (main skeleton, ~2 KB)
├── style.min.css   (all styles, minified)
├── app.min.js      (all JavaScript, minified)
└── icon.svg        (favicon / site icon)
```

### Cloudflare Pages Performance Settings

Enable the following for optimal speed:

- **Brotli compression** – automatically minifies assets.
- **Rocket Loader** – improves script loading.
- **Automatic minification** – for HTML, CSS, and JS.

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
- `verified_users` – Records of successful verifications: `guild_id`, `user_id`, `verified_at`, `verified_by`.

---

## Customization

- **Deobfuscation** – Modify the `PROMETHEUS_DEOBF_LUA` template or the `deobfuscate_code` fallback logic.
- **Verification deadline** – The bot checks every minute; you can change the interval in `check_verification_deadlines()`.
- **Web verification** – Adjust the Turnstile site key in `index.html` and the API endpoint URL in `app.min.js` if needed.
- **User cache TTL** – Modify `USER_CACHE_TTL` (in seconds) to control how often Discord user data is refreshed.

---

## Support

For issues or feature requests, open an issue on GitHub or contact the bot owner.

---

## License

This project is provided as‑is. Use at your own risk.
