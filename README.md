# RblXLua Bot

A feature-rich Discord bot for Lua obfuscation, server management (tickets, verification, leveling), automated moderation, and script searching.

---

## Features

- **Lua Obfuscation** – Obfuscate Lua source code with a stable Prometheus-style single-base64 chunk.
- **Level System** – Award XP for chatting, assign roles at each level (1–10), and announce level-ups.
- **Ticket System** – Create persistent ticket panels with custom roles, claim functionality, and closing.
- **Verification System** – Automatically restrict server access until users verify via a button.
- **Active Checker** – Periodically ping `@everyone` in a specified channel to check user activity.
- **Auto-Delete Messages** – Instantly delete all messages in chosen channels.
- **Script Search** – Search the web for a script and retrieve its loadstring and source URL.
- **Slash & Prefix Commands** – Mix of modern slash commands and traditional prefix commands (`.`).
- **Command Channel Restriction** – Limit commands to a single text channel (with owner bypass).
- **Bypass Utility** – Extract keys from obfuscated URLs (Delta-like).
- **MongoDB Persistence** – All settings and logs are stored in MongoDB.

---

## Commands

### Prefix Commands (`.`)

| Command | Description |
|---------|-------------|
| `.obf` | Obfuscate Lua code using Prometheus. Attach a file, paste code, or reply to a message. |
| `.level` or `.lvl` | Show your current level, XP, and progress. |
| `.cmds` | Show this help menu (paginated). |
| `.db status` | Check MongoDB connection status. |
| `.db clear` | (Owner only) Clear all stored data. |
| `.request <query>` | Search the web for a script and return its loadstring and source URL. |

### Slash Commands (`/`)

| Command | Description | Required Permissions |
|---------|-------------|----------------------|
| `/ping` | Check bot latency. | None |
| `/channel_set` | Restrict all prefix commands to a specific channel. | Administrator |
| `/channel_view` | Show the currently restricted channel. | None |
| `/channel_clear` | Remove the channel restriction. | Administrator |
| `/ticket` | Create a ticket panel with custom roles, claim button, embed color, etc. | Administrator |
| `/verify_system` | Set up the verification system (creates "Not Verified" role, applies perms). | Administrator |
| `/level_up_system` | Configure level roles (1–10), announcement channel, enable/disable. | Administrator |
| `/active_checker` | Set up a periodic `@everyone` ping in a channel. | Administrator |
| `/bypass` | Extract a key from a URL (Delta-style bypass). | None |
| `/auto_delete_messages` | Add a text channel to auto-delete all new messages. | Administrator |
| `/atd_view_channel` | View all channels currently set for auto-deletion. | None |
| `/atd_remove_channel` | Remove a channel from auto-deletion. | Administrator |

---

## Setup

### 1. Prerequisites

- Python 3.9 or higher
- A MongoDB database (Atlas or self-hosted)
- A Discord Bot Token
- BeautifulSoup and lxml for web searching (`pip install beautifulsoup4 lxml`)

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
beautifulsoup4
lxml
```

### 4. Running the Bot

```bash
python bot.py
```

The bot will start a Flask web server on port 10000 (for health checks) and the Discord client.

---

## Permissions Required

- **Manage Roles** – For level system, verification, and ticket role assignments.
- **Manage Channels** – For ticket creation, verification channel permission overrides.
- **View Channel / Send Messages** – To function in designated channels.
- **Read Message History** – For ticket and verification message updates.
- **Manage Messages** – For auto-delete functionality (it deletes messages).
- **Administrator** – For setup commands (recommended for ease).

---

## Database Collections

The bot uses the following MongoDB collections:

- `settings` – Command channel restriction.
- `usage_logs` – Logs of `.obf`, `.level`, etc. (for audit).
- `tickets` – Open/closed ticket data.
- `ticket_panels` – Configuration for each ticket panel.
- `verification_config` – Verification role and channel settings.
- `level_config` – Per-guild level system settings (levels, roles, enabled).
- `user_xp` – XP and level for each user per guild.
- `active_checker_config` – Active checker interval and channel.
- `auto_delete_config` – List of channel IDs for auto-deletion.

---

## Customization

- **Level XP Requirements** – Modify the `XP_PER_LEVEL` dictionary in the source code.
- **Level-Up Embeds** – Customize the `get_level_up_embed` function.
- **Auto-Delete** – The bot deletes messages immediately; you can add a delay by modifying the `on_message` event.
- **Script Search** – Adjust the search logic or add more sources in the `search_web` and `find_script_from_search` functions.

---

## Support

For issues or feature requests, please open an issue on the GitHub repository or contact the bot owner.

---

## License

This project is provided as-is. Use at your own risk.
