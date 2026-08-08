# RblXLua Bot

A feature-rich Discord bot for Lua deobfuscation, obfuscation, ticket management, verification, active checks, auto-delete, and administrative utilities.

---

## Features

- **Lua Deobfuscation** – Fetch code from a link, attachment, or reply and run multi‑layer deobfuscation (Prometheus, WeAreDevs, enhanced fallback). Displays preview and optionally sends file.
- **Lua Obfuscation** – Obfuscate Lua source code with a stable Prometheus-style single-base64 chunk.
- **Ticket System** – Persistent ticket panels with custom roles, claim functionality, and closing.
- **Verification System** – Restrict server access until users verify via a button; automatically sets up permissions and a "Not Verified" role.
- **Active Checker** – Periodically ping @everyone in a specified channel to check user activity.
- **Auto-Delete Messages** – Instantly delete all messages in chosen channels.
- **Bypass Utility** – Extract keys from obfuscated URLs (Delta‑style).
- **Slash & Prefix Commands** – Modern slash commands and traditional prefix commands (`.`).
- **Command Channel Restriction** – Limit commands to a single text channel (with owner bypass).
- **MongoDB Persistence** – All settings and logs are stored in MongoDB.

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
| `/verify_system` | Set up the verification system (creates "Not Verified" role, applies perms). | Administrator |
| `/active_checker` | Set up a periodic @everyone ping in a channel. | Administrator |
| `/bypass` | Extract a key from a URL (Delta‑style bypass). | None |
| `/auto_delete_messages` | Add a text channel to auto‑delete all new messages. | Administrator |
| `/atd_view_channel` | View all channels currently set for auto‑deletion. | None |
| `/atd_remove_channel` | Remove a channel from auto‑deletion. | Administrator |

---

## Setup

### 1. Prerequisites

- Python 3.9 or higher
- A MongoDB database (Atlas or self‑hosted)
- A Discord Bot Token
- BeautifulSoup and lxml for web searching (used by `.get` for parsing, though you can remove if not needed)
- (Optional) Lua interpreter if you intend to use the Prometheus deobfuscation engine that calls Lua (the bot will fall back to other methods if not available).

### 2. Environment Variables

The bot reads the following environment variables:

| Variable | Description |
|----------|-------------|
| `TOKEN` | Your Discord bot token. |
| `MONGODB_URI` | MongoDB connection string. |

Example:

```bash
export TOKEN="your_discord_bot_token"
export MONGODB_URI="mongodb+srv://user:pass@cluster.mongodb.net/"
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

The bot will start a Flask web server on port 10000 (for health checks) and the Discord client.

---

## Permissions Required

- **Manage Roles** – For verification and ticket role assignments.
- **Manage Channels** – For ticket creation and verification channel permission overrides.
- **View Channel / Send Messages** – To function in designated channels.
- **Read Message History** – For ticket and verification message updates.
- **Manage Messages** – For auto‑delete functionality (it deletes messages).
- **Administrator** – For setup commands (recommended for ease).

---

## Database Collections

The bot uses the following MongoDB collections:

- `settings` – Command channel restriction.
- `usage_logs` – Logs of `.get`, `.obf`, etc. (for audit).
- `tickets` – Open/closed ticket data.
- `ticket_panels` – Configuration for each ticket panel.
- `verification_config` – Verification role and channel settings.
- `active_checker_config` – Active checker interval and channel.
- `auto_delete_config` – List of channel IDs for auto‑deletion.

---

## Customization

- **Deobfuscation** – Modify the `PROMETHEUS_DEOBF_LUA` template or the `deobfuscate_code` fallback logic.
- **Auto‑Delete** – The bot deletes messages immediately; you can add a delay by modifying the `on_message` event.
- **Command Channel** – Use the `/channel_*` slash commands to restrict or allow command usage.

---

## Support

For issues or feature requests, please open an issue on the GitHub repository or contact the bot owner.

---

## License

This project is provided as‑is. Use at your own risk.
