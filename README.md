All-in-one Discord bot for Lua processing, server management, and key extraction. Built for RblXLua community.
 
 
 
🚀 Quick Info
 
- Bot Name: RblXLua Bot
- Language: Python 3.12+
- Database: MongoDB Atlas
- Hosting: Render / Replit / any Python host
- Prefix:  .  | Slash Commands: Enabled
 
 
 
📦 Requirements
 
Put this in your  requirements.txt :
 
plaintext
  
discord.py==2.4.0
aiohttp==3.9.5
pymongo==4.6.3
Flask==3.0.3
python-dateutil==2.9.0.post0
 
 
 
 
🔑 Environment Variables
 
Set these in your host's Variables/Secrets section:
 
Key Value 
 TOKEN  Your Discord bot token 
 MONGODB_URI  Your full MongoDB connection string 
 
 
 
✨ All Features
 
🛠️ Lua Tools
 
Command Type What It Does 
 .l [link/code/file]  Prefix Deobfuscate Lua: Supports Prometheus, WeAreDevs, XOR, base64, string.char, anti-env detection, multi-layer unpacking 
 .get [link]  Prefix Fetch raw Lua code from any direct/raw link, handles 403/404 with proxy fallback 
 .env [link/code/file]  Prefix Anti-Env Bypass: Removes anti-logger, anti-debug, and kick checks; patches function detection 
 .obf [link/code/file]  Prefix Obfuscate code with Prometheus-style protection 
 .cmds  Prefix Show all commands in paginated embed 
 .db [status/clear]  Prefix Check database status / clear data (owner only) 
 
📈 Level System
 
Command Type What It Does 
 /level_up_system  Slash Configure levels 1–10: assign roles, set announcement channel, toggle system 
 .level  /  .lvl  Prefix Check your XP, current level, and progress bar 
 
- Auto-grant/remove roles on level up
- +1 XP per valid message; XP resets on level up
- Predefined XP requirements: 20/50/100/150/200/250/300/350/400/500
 
🎫 Ticket System
 
Command Type What It Does 
 /ticket  Slash Create custom ticket panels: set ping roles, button style/emoji, embed color/footer 
 
- Persistent panels survive bot restarts
- Claim/Close buttons; auto-cleanup; DM creator when closed
 
🔐 Verification System
 
Command Type What It Does 
 /verify_system  Slash One-click setup: creates Not Verified role, adjusts all channel permissions 
 
- One button verify; auto-swaps roles; restricts channels before verification
 
🟢 Active Checker
 
Command Type What It Does 
 /active_checker  Slash Schedule periodic @everyone pings: use  1d ,  1week ,  1month , etc. 
 
🔗 Link & Key Tools
 
Command Type What It Does 
 /bypass [url]  Slash Bypass ad links, extract Delta keys; supports base64/urlsafe decoding; finds all valid key formats 
 
⚙️ Admin Utility
 
Command Type What It Does 
 /ping  Slash + Prefix Check API latency and response time 
 /channel_set [channel]  Slash Restrict all commands to one channel 
 /channel_view  Slash See current allowed channel 
 /channel_clear  Slash Remove channel restriction 
 
 
 
📁 File Structure
 
plaintext
  
your-project/
├─ main.py            # Full bot code
├─ requirements.txt   # Dependencies list
└─ README.md          # This file
 
 
 
 
🛠️ How To Deploy
 
1. Upload files to GitHub or host directly
2. Add the 2 environment variables
3. Set build command:  pip install -r requirements.txt 
4. Set start command:  python main.py 
5. Invite bot with scope  bot+applications.commands  and Administrator permission
 
 
 
⚠️ Notes
 
- The built-in Prometheus deobfuscator requires Lua installed on your host for full support; if not available, Python fallback unpacking will run instead
- Flask runs silently on port 10000 just to keep the service alive
- Owner ID is hardcoded in the script — update it if you need to change the owner
- All large outputs are sent as  .lua  files automatically, previews show up to ~30% of content
