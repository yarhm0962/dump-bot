# RblXLua Bot

A feature‑rich Discord bot for Lua deobfuscation, obfuscation, ticket management, verification with Cloudflare Turnstile and Discord OAuth2, active checks, auto‑delete, and administrative utilities.

---

## Features

- **Lua Deobfuscation** – Fetch code from a link, attachment, or reply and run multi‑layer deobfuscation (Prometheus, WeAreDevs, enhanced fallback). Displays preview and optionally sends file.
- **Lua Obfuscation** – Obfuscate Lua source code with a stable Prometheus‑style single‑base64 chunk.
- **Ticket System** – Persistent ticket panels with custom roles, claim functionality, and closing.
- **Verification System** – Restrict server access until users verify via a **Discord OAuth2 login** (no manual ID entry).  
  - Users click “Login with Discord” on the verification page, authorize the `identify` scope, and are automatically redirected back.  
  - After login, they complete a Cloudflare Turnstile challenge (the “ads verification”) and click **Verify** to get the Verified role.  
  - The verification embed in the server shows a **24‑hour countdown** (automatically set). When the deadline expires, all unverified members receive the **Not Verified** role.  
  - Verification records are stored in MongoDB (`verified_users` collection) with user ID, timestamp, and method (`oauth` or `website`).  
  - If a user loses the Verified role (e.g., manually removed), they can re‑verify through the website – the bot allows it and updates the record.  
  - The website includes a **real‑time list** of verified users with avatars, display names, and timestamps (fetched from `/api/verified_users` and refreshed every 15 seconds).
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
| `/verification_system` | Set up verification system. **Automatically sets a 24‑hour countdown deadline** – no duration parameter needed. The embed shows a timestamp for the deadline; when it expires, all unverified members get the **Not Verified** role. The message includes a **Verify on Website** link button. | Administrator |
| `/active_checker` | Set up a periodic @everyone ping in a channel. | Administrator |
| `/bypass` | Extract a key from a URL (Delta‑style bypass). | None |
| `/auto_delete_messages` | Add a text channel to auto‑delete all new messages. | Administrator |
| `/atd_view_channel` | View all channels currently set for auto‑deletion. | None |
| `/atd_remove_channel` | Remove a channel from auto‑deletion. | Administrator |

---

## Verification Website

The bot includes a standalone verification web page that is **self‑contained in a single HTML file** (no external CSS/JS dependencies except Turnstile and the OAuth2 flow). The page:

- Shows a **Login with Discord** button that initiates OAuth2 (using the bot’s `/login` endpoint).
- After successful login, the user’s profile picture and username appear in the top‑right corner.
- The Turnstile challenge (ads verification) is displayed **only after login**.
- On successful Turnstile completion, the **Verify** button becomes active.
- Clicking Verify sends a POST to the bot’s `/api/verify` endpoint with the user ID and Turnstile token.
- The bot validates the Turnstile token and assigns the Verified role.
- If the user already has the Verified role, the button is disabled and shows “Already Verified”.
- The page also shows a **real‑time list** of all verified users (avatars, display names, timestamps) refreshed every 15 seconds.
- Login status is persisted in `localStorage` so returning users see the dashboard without re‑logging.

### OAuth2 Flow

1. User clicks **Login with Discord**.
2. Redirected to Discord’s OAuth2 authorization page (scope: `identify`).
3. After authorization, Discord redirects to the bot’s `/callback` endpoint.
4. The bot exchanges the code for an access token, fetches the user’s ID, username, and avatar, and **automatically assigns the Verified role** (so the user is verified immediately).
5. The bot redirects back to the website with `?verified=1&user_id=...&username=...&display_name=...&avatar_url=...`.
6. The website shows the dashboard with the user’s info and the Turnstile challenge (though the role is already assigned, the user can still complete the challenge – but if already verified, the button will be disabled after checking).

---

## Setup

### 1. Prerequisites

- Python 3.9 or higher
- A MongoDB database (Atlas or self‑hosted)
- A Discord Bot Token
- Discord Application with OAuth2 enabled (Client ID and Client Secret)
- Cloudflare Turnstile site key and secret key (for the web verification)
- (Optional) Lua interpreter for Prometheus deobfuscation (falls back to other methods if not available)

### 2. Environment Variables

Set these on your hosting platform (e.g., Render):

| Variable | Description |
|----------|-------------|
| `TOKEN` | Your Discord bot token. |
| `MONGODB_URI` | MongoDB connection string. |
| `TURNSTILE_SECRET_KEY` | Cloudflare Turnstile secret key. |
| `GUILD_ID` | Your Discord server ID (integer). |
| `DISCORD_CLIENT_ID` | Your Discord OAuth2 client ID. |
| `DISCORD_CLIENT_SECRET` | Your Discord OAuth2 client secret. |
| `DISCORD_REDIRECT_URI` | The bot’s callback URL (e.g., `https://your-bot-domain.com/callback`). |
| `WEBSITE_URL` | The URL of your verification website (e.g., `https://rblxlua-verification.pages.dev`). |

Example:

```bash
export TOKEN="your_discord_bot_token"
export MONGODB_URI="mongodb+srv://user:pass@cluster.mongodb.net/"
export TURNSTILE_SECRET_KEY="0x4AAAAAAEKmf0BjB9dr0YMk5Mc4zGOd-pw"
export GUILD_ID="123456789012345678"
export DISCORD_CLIENT_ID="1532118414900985930"
export DISCORD_CLIENT_SECRET="your_client_secret"
export DISCORD_REDIRECT_URI="https://dump-bot-m0yp.onrender.com/callback"
export WEBSITE_URL="https://rblxlua-verification.pages.dev"
```

### 3. Installation

Clone the repository and install dependencies:

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

The bot will start a Flask web server on port `10000` (for health checks and the `/login`, `/callback`, `/api/verify`, and `/api/verified_users` endpoints) and the Discord client.

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
- **Verification deadline** – The bot uses a fixed 24‑hour deadline; you can change `DEFAULT_VERIFICATION_DURATION` in the code (line where it is defined) to any value in seconds.
- **Web verification** – Adjust the Turnstile site key in `index.html` and the API endpoint URL in the JavaScript if needed.
- **User cache TTL** – Modify `USER_CACHE_TTL` (in seconds) to control how often Discord user data is refreshed.

---

## Support

For issues or feature requests, open an issue on GitHub or contact the bot owner.

---

## License

This project is provided as‑is. Use at your own risk.
