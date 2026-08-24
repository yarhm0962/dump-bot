markdown
# RblXLua Bot

A feature‑rich Discord bot for Lua deobfuscation, ticket management, verification with role assignment, active checkers, auto‑delete (instant and timer‑based), a talking bot, and administrative utilities.

---

## Features

- **Lua Deobfuscation** – Fetch code from a URL, attachment, or reply and run multi‑layer deobfuscation (Prometheus, WeAreDevs, enhanced fallback). Displays a preview and optionally sends the full code as a file.

- **Ticket System** – Persistent ticket panels with custom roles, claim functionality, and closing.

- **Verification System** – Restrict server access until users verify by clicking a **Verify** button. The bot automatically assigns a **Verified** role and a **Not Verified** role, with a 24‑hour deadline after which unverified members receive the Not Verified role.

- **Active Checker** – Periodically ping `@everyone` in a specified channel to check user activity.

- **Instant Auto‑Delete** – Delete every message as soon as it is sent in chosen channels.

- **Timer‑Based Auto‑Delete** – Delete all messages in a channel after a configurable period of inactivity. The timer resets whenever a new message is sent, and only triggers if no messages appear during the entire cooldown.

- **Talking Bot** – Enable a conversational bot in a specific channel that replies to user messages with relevant answers about Lua, exploits, Delta, and bot commands.

- **Bypass Utility** – Extract keys from obfuscated URLs (Delta‑style).

- **Slash & Prefix Commands** – Modern slash commands and traditional prefix commands (`.`).

- **Command Channel Restriction** – Limit commands to a single text channel (with owner bypass).

- **MongoDB Persistence** – All settings, logs, tickets, verification records, and configurations are stored in MongoDB.

---

## Commands

### Prefix Commands (`.`)

| Command | Description |
|---------|-------------|
| `.get` | Fetch and deobfuscate code from a URL, attachment, or reply. Displays cleaned code with preview/file. |
| `.cmds` | Show a help embed with an image and a download link. |
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
| `/verification_system` | Set up the verification system. Creates a **Verify** button and a 24‑hour deadline. The selected role is given upon verification. All other channels are hidden from unverified members. | Administrator |
| `/verify` | Immediately apply the **Not Verified** role to all currently unverified members. Shows an estimate of the time required. | Administrator |
| `/active_checker` | Set up a periodic @everyone ping in a channel. | Administrator |
| `/bypass` | Extract a key from a URL (Delta‑style bypass). | None |
| `/auto_delete_messages` | Enable instant deletion in a channel (all new messages are deleted immediately). Supports a `disable: True` option. | Administrator |
| `/atd_view_channel` | View all channels with instant deletion active. | None |
| `/atd_remove_channel` | Remove a channel from instant deletion. | Administrator |
| `/timer_delete_msg` | Set up timer‑based auto‑delete. Requires a channel and a duration (e.g., `10s`, `5m`, `1h`). Supports `disable: True`. | Administrator |
| `/talking_bot` | Enable the talking bot in a channel. The bot replies to user messages with context‑aware answers about Lua, exploits, and bot features. Supports `disable: True`. | Administrator |

---

## Setup

### 1. Prerequisites

- Python 3.9 or higher
- A MongoDB database (Atlas or self‑hosted)
- A Discord Bot Token
- Cloudflare Turnstile site key and secret key (for web verification – optional, only if using the web verification page)

### 2. Environment Variables

Set these on your hosting platform (e.g., Render):

| Variable | Description |
|----------|-------------|
| `TOKEN` | Your Discord bot token. |
| `MONGODB_URI` | MongoDB connection string. |
| `TURNSTILE_SECRET_KEY` | Cloudflare Turnstile secret key (for web verification). |
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
- **Manage Messages** – For auto‑delete and timer‑delete functionality.
- **Administrator** – Recommended for setup commands.

---

## Database Collections

- `settings` – Command channel restriction.
- `usage_logs` – Logs of `.get` usage.
- `tickets` – Open/closed ticket data.
- `ticket_panels` – Configuration for each ticket panel.
- `verification_config` – Verification role, channel, message ID, deadline, and processed flag.
- `active_checker_config` – Active checker interval and channel.
- `auto_delete_config` – Channel IDs for instant deletion.
- `verified_users` – Records of successful verifications: `guild_id`, `user_id`, `verified_at`, `verified_by`, and `gender` (string).
- `timer_delete_config` – Channel ID and duration (in seconds) for timer‑based deletion.
- `talking_bot_config` – Channel IDs where the talking bot is enabled.

---

## Customization

- **Deobfuscation** – Modify the `PROMETHEUS_DEOBF_LUA` template or the `deobfuscate_code` fallback logic.
- **Verification deadline** – The bot uses a fixed 24‑hour deadline; change `DEFAULT_VERIFICATION_DURATION` in the code to any value in seconds.
- **Web verification** – Adjust the Turnstile site key in `index.html` and the API endpoint URL if needed.
- **Talking bot responses** – Edit the `responses` dictionary in `handle_talking_bot` to add or modify reply patterns.
- **User cache TTL** – Modify `USER_CACHE_TTL` (in seconds) to control how often Discord user data is refreshed.

---

## Support

For issues or feature requests, open an issue on GitHub or contact the bot owner.

---

## License

This project is provided as‑is. Use at your own risk.
