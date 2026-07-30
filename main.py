from flask import Flask
app = Flask(__name__)
@app.route('/')
def home(): return "✅ RblXLua Service Running"

import os
import discord
from discord import File
from discord.ext import commands
import aiohttp
import re
import random
import io
import base64
import json
import pymongo
from pymongo.mongo_client import MongoClient
from pymongo.server_api import ServerApi
import asyncio
import subprocess
import tempfile

TOKEN = os.getenv("TOKEN")
MONGODB_URI = os.getenv("MONGODB_URI")
DEEPSEEK_API_KEY = "sk-fd2727bedcd4402f98f82dad020c2d6c"
AI_CHANNELS_FILE = "ai_channels.json"

mongo_client = None
db = None
settings_col = None
logs_col = None

try:
    mongo_client = MongoClient(MONGODB_URI, server_api=ServerApi('1'))
    mongo_client.admin.command('ping')
    db = mongo_client["rblxlua_data"]
    settings_col = db["settings"]
    logs_col = db["usage_logs"]
    print("✅ MongoDB Connected Successfully")
except Exception as e:
    print(f"❌ MongoDB Error: {str(e)}")

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix=".", intents=intents, help_command=None)

ai_enabled_channels = set()

def load_ai_channels():
    global ai_enabled_channels
    try:
        with open(AI_CHANNELS_FILE, "r") as f:
            data = json.load(f)
            ai_enabled_channels = set(data.get("channels", []))
        print(f"✅ Loaded AI channels: {ai_enabled_channels}")
    except Exception as e:
        ai_enabled_channels = set()
        print(f"⚠️ Could not load ai_channels.json: {e}")

def save_ai_channels():
    with open(AI_CHANNELS_FILE, "w") as f:
        json.dump({"channels": list(ai_enabled_channels)}, f)
    print(f"💾 Saved AI channels: {ai_enabled_channels}")

load_ai_channels()

async def delete_cmds_only(ctx):
    if ctx.invoked_with in ["cmds"]:
        try: await ctx.message.delete()
        except: pass

def decode_all_escapes(s: str) -> str:
    try:
        s = re.sub(r'\\x([0-9a-fA-F]{2})', lambda m: chr(int(m.group(1),16)), s)
        s = re.sub(r'\\([0-9]{1,3})', lambda m: chr(int(m.group(1))), s)
        return s.strip()
    except: return s

def extract_url(input_text: str) -> str:
    patterns = [r'https?://[a-zA-Z0-9\-\.]+\.[a-zA-Z]{2,}(:\d+)?(/[^\s<>"\'\)\]]*)?', r'https?://[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}(:\d+)?(/[^\s<>"\'\)\]]*)?']
    for pat in patterns:
        match = re.search(pat, input_text)
        if match: return match.group(0)
    return ""

def xor_obfuscate(source):
    key = random.randint(30, 230)
    bytes_list = [ord(c) ^ key for c in source]
    encoded = ",".join(str(b) for b in bytes_list)
    return f'''-- XOR-obfuscated Lua | key={key}
local _k={key}
local _d={{{encoded}}}
local _s=""
for _i=1,#_d do _s=_s..string.char(_d[_i]~_k) end
local _f=loadstring or load
local _fn,_err=_f(_s)
if _fn then _fn() else error(_err) end'''

async def fetch_content(url: str) -> tuple[bool, str, str]:
    clean_url = extract_url(url)
    if not clean_url: return False, "", "No valid URL found"
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=25)) as session:
            headers_list = [
                {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/125.0.0.0 Safari/537.36", "Accept": "*/*"},
                {"User-Agent": "Roblox/WinInet", "Accept": "text/plain,application/lua"},
                {"User-Agent": "curl/8.4.0", "Accept": "*/*"}
            ]
            last_error = ""
            for headers in headers_list:
                try:
                    async with session.get(clean_url, headers=headers, allow_redirects=True, max_redirects=8) as resp:
                        if resp.status == 404: last_error = "❌ 404: File does not exist"; continue
                        if resp.status == 403: last_error = "❌ 403: Access blocked by host"; continue
                        if resp.status >= 400: last_error = f"❌ HTTP Error: {resp.status}"; continue
                        body = await resp.text(encoding="utf-8", errors="replace")
                        if body and len(body.strip()) > 0: return True, decode_all_escapes(body), "Successfully fetched"
                except Exception as e: last_error = str(e); continue
            try:
                proxy_url = f"https://api.allorigins.win/raw?url={clean_url}"
                async with session.get(proxy_url, headers={"User-Agent":"curl/8.4.0"}, timeout=aiohttp.ClientTimeout(total=20)) as resp:
                    if resp.status == 200:
                        body = await resp.text(encoding="utf-8", errors="replace")
                        return True, decode_all_escapes(body), "Successfully fetched via proxy"
            except: pass
            return False, "", last_error if last_error else "❌ Could not retrieve content"
    except Exception as e: return False, "", f"❌ Error: {str(e)[:120]}"

async def extract_code(ctx):
    content = ""
    for att in ctx.message.attachments:
        if att.filename.endswith(('.lua', '.txt')):
            try:
                data = await att.read()
                content = data.decode('utf-8')
                return decode_all_escapes(content)
            except: pass
    code_blocks = re.findall(r'```(?:lua)?\n(.*?)```', ctx.message.content, re.DOTALL)
    if code_blocks: return decode_all_escapes('\n'.join(code_blocks))
    inline = re.findall(r'`([^`]+)`', ctx.message.content)
    if inline: return decode_all_escapes('\n'.join(inline))
    urls = re.findall(r'https?://[^\s<>]+', ctx.message.content)
    for u in urls:
        ok, res, _ = await fetch_content(u)
        if ok: return res
    if ctx.message.reference:
        try:
            ref_msg = await ctx.channel.fetch_message(ctx.message.reference.message_id)
            return await extract_code(ref_msg)
        except: pass
    if len(ctx.message.content.strip()) > 80: return decode_all_escapes(ctx.message.content)
    return None

def deobfuscate_code(source_text):
    max_depth = 12
    report = {"detected": [], "steps": [], "anti": []}

    def clean_escapes(txt):
        txt = re.sub(r'\\x([0-9a-fA-F]{2})', lambda m: chr(int(m.group(1), 16)), txt)
        txt = re.sub(r'\\([0-9]{1,3})', lambda m: chr(int(m.group(1))), txt)
        txt = re.sub(r'\\(.)', r'\1', txt)
        return txt.strip()

    def decode_b64(txt):
        found = re.findall(r'["\']([A-Za-z0-9+/=]{25,})["\']', txt)
        for chunk in found:
            try:
                out = base64.b64decode(chunk).decode('utf-8', 'replace')
                if len(out) > len(chunk) and out != txt:
                    return True, out
            except: pass
        return False, ""

    def decode_strchar(txt):
        m = re.search(r'string\.char\(([\d,\s]+)\)', txt, re.DOTALL)
        if not m: return False, ""
        try:
            nums = [int(n) for n in re.findall(r'\d+', m.group(1)) if n.isdigit()]
            out = ''.join(chr(n) for n in nums)
            if len(out) > 30 and out != txt:
                return True, out
        except: pass
        return False, ""

    def decode_xor(txt):
        mk = re.search(r'local\s+_?k\s*=\s*(\d{1,3})', txt)
        md = re.search(r'local\s+_?d\s*=\s*\{([^}]{120,})\}', txt, re.DOTALL)
        if mk and md:
            try:
                key = int(mk.group(1))
                nums = [int(n) for n in re.findall(r'\d+', md.group(1)) if n.isdigit()]
                out = ''.join(chr(b ^ key) for b in nums)
                if len(out) > 30 and out != txt:
                    return True, out
            except: pass
        mx = re.search(r'["\']([^"\']{5,30})["\'].*?["\']([A-Za-z0-9+/=]{30,})["\']', txt, re.DOTALL)
        if mx:
            try:
                k, d = mx.group(1), base64.b64decode(mx.group(2)).decode('latin1', 'replace')
                out = ''.join(chr(ord(c) ^ ord(k[i % len(k)])) for i, c in enumerate(d))
                if len(out) > 30 and out != txt:
                    return True, out
            except: pass
        return False, ""

    def scan_signatures(txt):
        sigs = [
            ("Prometheus", r'--.*Prometheus|levno-710'),
            ("Lunr", r'--.*Lunr|return\(function\(L,M,I'),
            ("Luraph", r'--.*Luraph|luraph\.net'),
            ("Fualmor", r'fualmor|canary|_tripwire|4294967296'),
            ("WeAreDevs", r'wearedevs\.net|WAD_OBF'),
            ("Anti-Env/Log", r'envlog|galactic|writefile.*\.lua|discord.*webhook')
        ]
        for name, pat in sigs:
            if re.search(pat, txt, re.I):
                if name not in report["detected"]: report["detected"].append(name)
                if "Anti" in name: report["anti"].append(name)

    buf = clean_escapes(source_text)
    scan_signatures(buf)
    changed = True
    depth = 0
    while changed and depth < max_depth:
        changed = False
        depth += 1
        ok, res = decode_b64(buf)
        if ok: buf = res; changed = True; report["steps"].append(f"Layer {depth}: Base64 decoded")
        ok, res = decode_strchar(buf)
        if ok: buf = res; changed = True; report["steps"].append(f"Layer {depth}: string.char decoded")
        ok, res = decode_xor(buf)
        if ok: buf = res; changed = True; report["steps"].append(f"Layer {depth}: XOR decoded")
        buf = re.sub(r'if\s*\w+\s*[=<>]+\s*\w+\s*then\s*return\s*[01]+\s*end', '', buf)
        buf = re.sub(r'\b\w{18,}\s*[=<>]+\s*[01]', '', buf)
    buf = re.sub(r'--\[\[.*?\]\]', '', buf, re.DOTALL)
    buf = re.sub(r'--.*$', '', buf, re.MULTILINE).strip()
    return {
        "result": buf,
        "layers_done": depth,
        "detected": report["detected"],
        "anti_found": report["anti"],
        "steps": report["steps"],
        "status": "Fully unpacked" if depth >= 3 else "Partially unpacked" if depth > 0 else "No unpack needed"
    }

class EnvBypassDumper:
    def __init__(self):
        self.spoof = {}
        self.block = [
            "writefile", "readfile", "listfiles", "makefolder",
            "delfile", "getfenv", "setfenv", "getgenv",
            "debug.getupvalue", "debug.setupvalue", "debug.getlocal",
            "debug.setlocal", "debug.getregistry", "hookfunction",
            "rawset", "rawget", "rawequal", "newcclosure",
            "loadstring", "load", "require"
        ]

    def remove_anti_env_checks(self, src):
        patterns_remove = [
            r'if\s*_?G\s*[=!]=?\s*nil\s*then.*?end',
            r'if\s*_?ENV\s*[=!]=?\s*nil\s*then.*?end',
            r'if\s*getgenv\s*[=!]=?\s*nil\s*then.*?end',
            r'if\s*type\s*\(\s*getgenv\s*\)\s*~=\s*["\']function["\'].*?end',
            r'_?\._?LOADED\s*[=!]=?\s*true.*?return',
            r'_?\._?ENVLOG.*?Kick\(.*?\)',
            r'_?\._?GALACTIC.*?Kick\(.*?\)',
            r'_?\._?LOGGER.*?Kick\(.*?\)',
            r'_?\._?UNOBF.*?Kick\(.*?\)',
            r'_?\._?INTERCEPT.*?Kick\(.*?\)',
            r'if\s*debug\s*~=\s*nil.*?then.*?error.*?end',
            r'for\s+_+,\s+v\s+in\s+pairs\s*\(\s*debug\s*\)\s+do.*?end',
            r'if\s*type\s*\(\s*rawget\s*\)\s*~=',
            r'if\s*loadstring\s*~=\s*nil\s+and\s+_l\s*~=\s*loadstring',
            r'if\s*_p\s*~=\s*nil\s+or\s+_j\s*~=\s*nil'
        ]
        for p in patterns_remove:
            src = re.sub(p, '', src, flags=re.DOTALL | re.IGNORECASE)
        return src

    def patch_function_checks(self, src):
        repl = [
            (r'local\s+_l\s*=\s*loadstring.*?local\s+_l\s*=\s*loadstring', 'local _l = loadstring or load'),
            (r'local\s+_g\s*=\s*game\.HttpGet', 'local _g = function() return "" end'),
            (r'if\s+_l\s*~=\s*loadstring.*?then\s*__:Kick.*?end', ''),
            (r'if\s+_g\s*~=\s*game\.HttpGet.*?then\s*__:Kick.*?end', '')
        ]
        for old,new in repl: src = re.sub(old, new, src, flags=re.DOTALL)
        return src

    def inject_dummy_returns(self, src):
        for name in self.block:
            src = re.sub(
                rf'if\s+type\s*\(\s*{name}\s*\)\s*[=!]=?\s*["\']?nil["\']?\s+then.*?(Kick|error|return).*?end',
                f'local {name} = nil',
                src, flags=re.DOTALL
            )
        return src

    def full_bypass(self, code):
        out = code
        out = self.remove_anti_env_checks(out)
        out = self.patch_function_checks(out)
        out = self.inject_dummy_returns(out)
        return {
            "patched_code": out.strip(),
            "bypassed_count": len(re.findall(r'Kick|error|return', code)) - len(re.findall(r'Kick|error|return', out))
        }

def make_result_embed(ctx, title: str, deobf: dict=None, raw: str=None):
    if deobf:
        obf = deobf["obfuscator"]
        steps = "\n".join([f"• {s}" for s in deobf["steps"]]) if deobf["steps"] else "• No unpack steps"
        anti = "\n".join(deobf["anti_found"]) if deobf["anti_found"] else "• None detected"
        desc = f"""{ctx.author.mention}
**Obfuscator:** `{obf['name']}`
**Confidence:** `{obf['confidence']}%`
**Status:** `{deobf['status']}`
**Layers:** `{deobf['layers_reached']}/{deobf['max_layers']}`

**Anti-Env / Anti-Tamper Found:**
{anti}

**Processing Steps:**
{steps}
"""
        content = deobf["result"]
    elif raw:
        desc = f"{ctx.author.mention}\n**Status:** Raw decoded content"
        content = decode_all_escapes(raw)
    else:
        emb = discord.Embed(title=title, color=0xe74c3c, description=f"{ctx.author.mention}\n❌ Empty result")
        return emb, None
    if not content or len(content) < 5:
        emb = discord.Embed(title=title, color=0xe74c3c, description=desc+"\n❌ No usable code")
        return emb, None
    size_b = content.encode('utf-8')
    size_kb = len(size_b) / 1024
    file = None
    if size_kb > 10 or len(content) > 1800:
        file = File(io.BytesIO(size_b), filename="processed.lua")
        desc += f"\n📦 Size: `{round(size_kb,2)} KB` → Full code sent as file"
        emb = discord.Embed(title=title, color=0x3498db, description=desc)
    else:
        prev = content[:1500] + ("\n... [truncated]" if len(content) > 1500 else "")
        desc += f"\n📦 Size: `{round(size_kb,2)} KB`\n\n**Preview:**\n```lua\n{prev}\n```"
        emb = discord.Embed(title=title, color=0x2ecc71 if "Fully unpacked" in desc else 0xf39c12, description=desc)
    emb.set_footer(text=f"Requested by {ctx.author}")
    return emb, file

async def query_deepseek(user_message: str, guild_name: str = None, user_name: str = None, channel_name: str = None) -> str:
    command_list = (
        "`.l <link/loadstring/code>` - Full deobfuscation with anti-env detection\n"
        "`.get <link/loadstring>` - Raw source fetch and decode\n"
        "`.env <link/loadstring>` - Deep anti-env bypass and unpack\n"
        "`.obf <link/loadstring/code>` - XOR obfuscate Lua code\n"
        "`.talking <#channel/id>` (admin) - Toggle AI auto-reply in a channel\n"
        "`.db status` - Check database connection\n"
        "`.db clear` (owner) - Clear stored data\n"
        "`.cmds` - Show this command list"
    )
    context_info = f"Server: {guild_name or 'Direct Message'}, Channel: {channel_name or 'Unknown'}, User: {user_name or 'Unknown'}"
    system_prompt = (
        f"You are a highly intelligent and helpful AI assistant integrated into the RblXLua Discord bot. "
        f"You are an expert in Lua scripting, Roblox, obfuscation, deobfuscation, Discord bot development, web hosting, and all RblXLua tools. "
        f"You respond clearly, concisely, and with a friendly, helpful tone. Always greet the user and mention their name if known. "
        f"You are aware of the current context: {context_info}. "
        f"The bot's prefix is `.`. Here are the available commands:\n{command_list}\n"
        f"You are knowledgeable about how each command works and can explain them. "
        f"When users ask about deobfuscation or Lua code, provide insightful and accurate answers. "
        f"If the user asks for help with a specific command, explain its usage and what it does. "
        f"Be proactive and offer additional tips or suggestions if relevant. "
        f"Stay within the scope of the bot's capabilities and Lua/Roblox ecosystem."
    )
    payload = {
        "model": "deepseek-chat",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message}
        ],
        "temperature": 0.7,
        "max_tokens": 1024
    }
    try:
        timeout = aiohttp.ClientTimeout(total=20)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(
                "https://api.deepseek.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
                    "Content-Type": "application/json"
                },
                json=payload
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if "choices" in data and len(data["choices"]) > 0:
                        return data["choices"][0]["message"]["content"].strip()
                    else:
                        print("DeepSeek response missing 'choices'")
                        return None
                else:
                    error_text = await resp.text()
                    print(f"DeepSeek API error: {resp.status} - {error_text}")
                    return None
    except asyncio.TimeoutError:
        print("DeepSeek request timed out")
        return None
    except aiohttp.ClientError as e:
        print(f"DeepSeek client error: {e}")
        return None
    except Exception as e:
        print(f"DeepSeek unexpected error: {e}")
        return None

@bot.event
async def on_ready():
    print(f"✅ Logged in as: {bot.user}")
    await bot.change_presence(activity=discord.Activity(type=discord.ActivityType.watching, name=".cmds | RblXLua Tools"))
    if db: print(f"✅ Database Ready: {db.name}")

@bot.event
async def on_message(message):
    if message.author.bot:
        return
    await bot.process_commands(message)
    if message.channel.id not in ai_enabled_channels:
        return
    if message.content.startswith(bot.command_prefix):
        return
    if message.content.strip() == "Hi":
        await message.reply(f"Hello {message.author.mention}! This is a test reply. The AI system is working perfectly.", mention_author=True)
        return
    async with message.channel.typing():
        guild_name = message.guild.name if message.guild else None
        user_name = message.author.display_name
        channel_name = message.channel.name if hasattr(message.channel, 'name') else None
        reply = await query_deepseek(message.content, guild_name, user_name, channel_name)
        if reply:
            await message.reply(reply, mention_author=True)
        else:
            await message.reply(f"⚠️ {message.author.mention} AI service is currently unavailable. Please try again later.", mention_author=True)

@bot.command(name="talking")
@commands.has_permissions(manage_channels=True)
async def talking_command(ctx, channel: discord.TextChannel = None):
    await delete_cmds_only(ctx)
    if not channel:
        emb = discord.Embed(title="⚠️ Missing Channel", color=0xf39c12, description=f"{ctx.author.mention}\nUsage: `.talking #channel` or `.talking channel_id`")
        return await ctx.reply(embed=emb, mention_author=True)
    if channel.id in ai_enabled_channels:
        ai_enabled_channels.discard(channel.id)
        save_ai_channels()
        await ctx.reply(f"AI chat disabled in {channel.mention}", mention_author=True)
    else:
        ai_enabled_channels.add(channel.id)
        save_ai_channels()
        await ctx.reply(f"AI chat enabled in {channel.mention}", mention_author=True)

@talking_command.error
async def talking_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.reply("You need `Manage Channels` permission to use this command.", mention_author=True)

@bot.group(name="db", invoke_without_command=True)
async def db_group(ctx):
    await delete_cmds_only(ctx)
    emb = discord.Embed(title="Database Commands", color=0x2b2d31, description=f"Hey {ctx.author.mention}\nUse these sub-commands:")
    emb.add_field(name="`db status`", value="Check database connection", inline=False)
    emb.add_field(name="`db clear`", value="Clear stored data", inline=False)
    await ctx.send(embed=emb)

@db_group.command(name="status")
async def db_status(ctx):
    await delete_cmds_only(ctx)
    emb = discord.Embed(title="Database Status", color=0x2ecc71 if db else 0xe74c3c, description=f"✅ {ctx.author.mention}\nConnected" if db else f"❌ {ctx.author.mention}\nNot available")
    await ctx.send(embed=emb)

@db_group.command(name="clear")
@commands.is_owner()
async def db_clear(ctx):
    await delete_cmds_only(ctx)
    if settings_col and logs_col: settings_col.delete_many({}); logs_col.delete_many({})
    emb = discord.Embed(title="Database Status", color=0x2ecc71, description=f"✅ {ctx.author.mention}\nAll data cleared")
    await ctx.send(embed=emb)

@bot.command(name="cmds")
async def show_commands(ctx):
    await delete_cmds_only(ctx)
    emb = discord.Embed(title="RblXLua Tool Commands", color=0x9b59b6, description=f"Hello {ctx.author.mention}\nCommands:")
    emb.add_field(name="`.l <link/loadstring/code>`", value="Full decode + anti-env detection", inline=False)
    emb.add_field(name="`.get <link/loadstring>`", value="Raw decoded source", inline=False)
    emb.add_field(name="`.env <link/loadstring>`", value="Deep env/anti-env scan + unpack", inline=False)
    emb.add_field(name="`.obf <link/loadstring/code>`", value="XOR obfuscate Lua code", inline=False)
    emb.add_field(name="`.talking <#channel/id>` (admin)", value="Toggle AI auto-reply in a channel", inline=False)
    emb.set_footer(text="Now fully supports XOR patterns + Fualmor style protection")
    await ctx.send(embed=emb)

# ========== The new Lua dumper script embedded as a string ==========
LUA_DUMPER_SCRIPT = r'''
os.execute = nil debug.getinfo = function() return "you cant skid from the skidder" end local realprint = print local _VERSION = "Luau" local d = { 	output = {}, 	registry = {}, 	unusedHttp = {}, 	counter = 0, 	indent = 0, 	funcDepth = 0, } local LOOP_THRESHOLD = 10 local MAX_BLOCK_SIZE = 1500 local function pad() return string.rep(" ", d.indent) end local function normalizeLine(str) return str:gsub("_[0-9]+", "_X") end local function emit(line, log) 	if line then 		table.insert(d.output, pad() .. line) 		local n = #d.output 		if n >= LOOP_THRESHOLD then 			for blockSize = 1, MAX_BLOCK_SIZE do 				if n >= blockSize * LOOP_THRESHOLD then 					local isCycle = true 					for r = 1, LOOP_THRESHOLD - 1 do 						for i = 0, blockSize - 1 do 							local currentLine = normalizeLine(d.output[n - i]) 							local previousLine = normalizeLine(d.output[n - i - (r * blockSize)]) 							if currentLine ~= previousLine then 								isCycle = false 								break 							end 						end 						if not isCycle then break end 					end 					if isCycle then 						local block = {} 						for i = blockSize - 1, 0, -1 do table.insert(block, d.output[n - i]) end 						for _ = 1, blockSize * LOOP_THRESHOLD do table.remove(d.output) end 						table.insert(d.output, pad() .. "while true do") 						for _, l in ipairs(block) do table.insert(d.output, " " .. l) end 						table.insert(d.output, pad() .. "end") 						error("LOOP_DETECTED", 0) 					end 				end 			end 		end 	end 	if log and line then realprint(d.output[#d.output]) end end local createProxy, makeProxy local function serialize(v, ind, seen) 	ind = ind or 0 	seen = seen or {} 	local t = type(v) 	 	if t == "string" then 		return '"' .. v:gsub("\\", "\\\\"):gsub("\n", "\\n"):gsub("\r", "\\r"):gsub("\t", "\\t"):gsub('"', '\\"') .. '"' 	elseif t == "number" or t == "boolean" then 		return tostring(v) 	elseif t == "nil" then 		return "nil" 	elseif t == "function" then 		if d.funcDepth > 2 then return "function(...) end" end 		d.funcDepth = d.funcDepth + 1 		 		local oldOutput = d.output 		local oldIndent = d.indent 		d.output = {} 		d.indent = ind + 1 		 		local mockArgs = {} 		for i = 1, 3 do 			d.counter = d.counter + 1 			table.insert(mockArgs, makeProxy("arg_" .. d.counter, false)) 		end 		 		pcall(v, table.unpack(mockArgs)) 		 		local captured = d.output 		d.output = oldOutput 		d.indent = oldIndent 		d.funcDepth = d.funcDepth - 1 		 		if #captured > 0 then 			return "function(...)\n" .. table.concat(captured, "\n") .. "\n" .. string.rep(" ", ind) .. "end" 		else 			return "function(...) end" 		end 	elseif t == "table" then 		if d.registry[v] then return d.registry[v] end 		if seen[v] then return "{...}" end 		seen[v] = true 		 		local isArray, maxKey = true, 0 		for k, _ in pairs(v) do 			if type(k) ~= "number" or k <= 0 or math.floor(k) ~= k then isArray = false break end 			if k > maxKey then maxKey = k end 		end 		if isArray then 			local parts = {} 			for i = 1, maxKey do table.insert(parts, serialize(v[i], ind, seen)) end 			return "{" .. table.concat(parts, ", ") .. "}" 		else 			local parts = {} 			local innerPad = string.rep(" ", ind + 1) 			local empty = true 			for k, val in pairs(v) do 				empty = false 				local key = (type(k) == "string" and k:match("^[%a_][%w_]*$")) and k or ("[" .. serialize(k, 0, seen) .. "]") 				local value = serialize(val, ind + 1, seen) 				table.insert(parts, innerPad .. key .. " = " .. value) 			end 			if empty then return "{}" end 			return "{\n" .. table.concat(parts, ",\n") .. "\n" .. string.rep(" ", ind) .. "}" 		end 	else 		return d.registry[v] or tostring(v) 	end end local function serializeArgs(args, start) 	local out = {} 	for i = start or 1, #args do table.insert(out, serialize(args[i], d.indent)) end 	return out end local function nextVar(prefix) 	d.counter = d.counter + 1 	return (prefix or "var") .. "_" .. d.counter end local COLON_METHODS = { 	HttpGet = true, HttpGetAsync = true, WaitForChild = true, FindFirstChild = true, 	FindFirstChildOfClass = true, FindFirstChildWhichIsA = true, GetService = true, 	Connect = true, Once = true, Wait = true, Clone = true, Destroy = true, Create = true, 	Play = true, Stop = true, FireServer = true, InvokeServer = true, SetCore = true, 	GetCore = true, JSONEncode = true, JSONDecode = true, GetAsync = true, PostAsync = true, 	GetChildren = true, GetDescendants = true, IsA = true, SetAttribute = true, 	GetAttribute = true, ClearAllChildren = true, Remove = true, RequestAsync = true, 	Kick = true, Ban = true, Disconnect = true, Fire = true, Invoke = true, 	BindToRenderStep = true, UnbindFromRenderStep = true, CreateWindow = true, AddButton = true, 	AddToggle = true, AddSlider = true, AddDropdown = true, AddColorPicker = true, MakeWindow = true, 	AddTab = true, AddSection = true, AddLabel = true, AddTextbox = true, AddBind = true, 	AddKeybind = true, Init = true, Build = true, CreateSection = true, CreateTab = true, 	CreateSlider = true, CreateButton = true, CreateToggle = true, AddParagraph = true, 	MakeTab = true, MakeSection = true, GetPivot = true, GetBoundingBox = true, 	GetFullName = true, IsDescendantOf = true, FindFirstAncestor = true, FindFirstAncestorOfClass = true, 	GetPlayers = true, GetPlayerByUserId = true, SendKeyEvent = true, SendMouseButtonEvent = true, 	IsKeyDown = true, IsMouseButtonPressed = true, Send = true, Close = true, 	CreateLib = true, NewTab = true, NewButton = true, NewToggle = true, 	NewSlider = true, NewDropdown = true, NewColorPicker = true, NewKeybind = true, NewTextBox = true } local VOID_METHODS = { 	Destroy = true, Play = true, Stop = true, FireServer = true, ClearAllChildren = true, 	Remove = true, Kick = true, Ban = true, Disconnect = true, SetAttribute = true, Fire = true, 	CaptureFocus = true, ReleaseFocus = true, SetPrimaryPartCFrame = true, BreakJoints = true, 	PivotTo = true, SendKeyEvent = true, SendMouseButtonEvent = true, Send = true, Close = true, } local DOTCALL_METHODS = { 	fromRGB = true, fromHSV = true, fromHex = true, lookAt = true, Angles = true, 	fromAxisAngle = true, fromOrientation = true, } local READ_ONLY_PROPERTIES = { ClassName = true, IsLoaded = true, AbsolutePosition = true, AbsoluteSize = true, RobloxVersion = true, Version = true } createProxy = function() 	if type(newproxy) == "function" then return newproxy(true) end 	local p = {} 	setmetatable(p, {}) 	return p end makeProxy = function(name, register) 	local proxy = createProxy() 	local mt = getmetatable(proxy) 	if register then d.registry[proxy] = name end 	mt.__index = function(self, key) 		if type(key) == "number" then return nil end 		local path = d.registry[self] or name 		local keyStr = tostring(key) if keyStr == "ClassName" then local pName = path:match("([%w_]+)") or "Instance" return pName end 		local newPath = path .. (COLON_METHODS[keyStr] and ":" or ".") .. keyStr 		local p = makeProxy(newPath, false) 		d.registry[p] = newPath 		return p 	end 	mt.__newindex = function(self, key, value) 		local path = d.registry[self] or name local keyStr = tostring(key) if READ_ONLY_PROPERTIES[keyStr] or path == "Heartbeat" or path == "RunService" or path == "game" then if keyStr == "IsLoaded" or keyStr == "ClassName" then error(keyStr .. " cannot be assigned to", 2) end end 		emit(path .. "." .. keyStr .. " = " .. serialize(value, d.indent), true) 	end 	mt.__call = function(self, ...) 		local fullPath = d.registry[self] or name 		local raw = { ... } 		local parent, method = fullPath:match("(.+)[%.:]([^%.:]+)$") 		 		local isColonCall = false 		if parent and raw and (d.registry[raw] == parent or tostring(raw) == parent) then 			isColonCall = true 		end 		local args = {} 		local startIdx = isColonCall and 2 or 1 		for i = startIdx, #raw do table.insert(args, raw[i]) end 		for _, arg in ipairs(args) do 			local argName = d.registry[arg] 			if argName and d.unusedHttp[argName] then d.unusedHttp[argName] = nil end 		end 		local sep = COLON_METHODS[method] and ":" or "." 		local callPrefix = parent and (parent .. sep .. method) or fullPath 		 		local argStrs = serializeArgs(args) 		local var = nextVar(method and method:lower():sub(1,3) or "r") 		 		if not parent then 			emit("local " .. var .. " = " .. fullPath .. "(" .. table.concat(argStrs, ", ") .. ")", true) 			local p = makeProxy(var, false) 			d.registry[p] = var 			return p 		end 		if method == "new" then 			if parent == "Instance" then 				var = nextVar("inst") 				emit("local " .. var .. " = " .. parent .. ".new(" .. table.concat(argStrs, ", ") .. ")", true) 			else 				local expr = parent .. ".new(" .. table.concat(argStrs, ", ") .. ")" 				local p = makeProxy(expr, false) 				d.registry[p] = expr 				return p 			end 		elseif DOTCALL_METHODS[method] then 			local expr = parent .. "." .. method .. "(" .. table.concat(argStrs, ", ") .. ")" 			local p = makeProxy(expr, false) 			d.registry[p] = expr 			return p 		elseif method == "GetService" then 			var = nextVar(tostring(args):sub(1, 4):lower()) 			emit("local " .. var .. " = " .. parent .. ":GetService(" .. serialize(args, 0) .. ")", true) 		elseif VOID_METHODS[method] then 			emit(callPrefix .. "(" .. table.concat(argStrs, ", ") .. ")", true) 		else 			emit("local " .. var .. " = " .. callPrefix .. "(" .. table.concat(argStrs, ", ") .. ")", true) 			if method == "HttpGet" or method == "HttpGetAsync" then d.unusedHttp[var] = true end 		end 		local p = makeProxy(var, false) 		d.registry[p] = var 		return p 	end 	mt.__tostring = function(self) return d.registry[self] or name end 	mt.__concat = function(a, b) return tostring(a) .. tostring(b) end 	return proxy end local function mockProxy(name) 	return function(...) 		local argStrs = serializeArgs({...}) 		local var = nextVar((name:match("[^%.]+$") or "proxy"):lower()) 		emit("local " .. var .. " = " .. name .. "(" .. table.concat(argStrs, ", ") .. ")", true) 		local p = makeProxy(var, false) 		d.registry[p] = var 		return p 	end end local function mockVoid(name) 	return function(...) 		local argStrs = serializeArgs({...}) 		emit(name .. "(" .. table.concat(argStrs, ", ") .. ")", true) 	end end local function mockReturn(name, val) 	return function(...) 		local argStrs = serializeArgs({...}) 		if #argStrs > 0 then 			emit("local _ = " .. name .. "(" .. table.concat(argStrs, ", ") .. ")", true) 		else 			emit("local _ = " .. name .. "()", true) 		end 		return val 	end end local function makeLibrary(name, predefined) 	local lib = predefined or {} 	return setmetatable(lib, { 		__index = function(_, k) return mockProxy(name .. "." .. tostring(k)) end, 		__newindex = function(_, k, v) emit(name .. "." .. tostring(k) .. " = " .. serialize(v, d.indent), true) end 	}) end local function buildEnv() 	local env = {} 	 	local robloxTypes = { 		"Axes", "BrickColor", "CatalogSearchParams", "CFrame", "Color3", "ColorSequence", 		"ColorSequenceKeypoint", "DateTime", "DockWidgetPluginGuiInfo", "Enum", "Enums", 		"Faces", "FloatCurveKey", "Font", "Instance", "NumberRange", "NumberSequence", 		"NumberSequenceKeypoint", "OverlapParams", "PathWaypoint", "PhysicalProperties", 		"Random", "Ray", "RaycastParams", "RaycastResult", "RBXScriptConnection", 		"RBXScriptSignal", "Rect", "Region3", "Region3int16", "RotationCurveKey", 		"Secret", "SharedTable", "TweenInfo", "UDim", "UDim2", "Vector2", "Vector2int16", 		"Vector3", "Vector3int16", "RaycastParams", "RaycastResult" 	} 	 	local robloxGlobals = { "game", "workspace", "script", "shared", "_G", "AssetService", "AvatarEditorService", "BadgeService", "Chat", "CollectionService", "ContentProvider", "ContextActionService", "ControllerService", "CoreGui", "CorePackages", "DataStoreService", "Debris", "GamePassService", "GroupService", "GuiService", "HapticService", "HttpService", "InsertService", "JointsService", "Lighting", "LocalizationService", "LogService", "MarketplaceService", "MaterialService", "MemoryStoreService", "MessagingService", "PathfindingService", "PhysicsService", "Players", "PolicyService", "ProcessService", "ProximityPromptService", "ReplicatedFirst", "ReplicatedStorage", "RunService", "ScriptContext", "Selection", "SocialService", "SoundService", "StarterGui", "StarterPack", "StarterPlayer", "Stats", "Teams", "TeleportService", "TestService", "TextChatService", "TextService", "TimerService", "TweenService", "UserInputService", "VoiceChatService", "VRService", "VirtualUser", "VirtualInputManager", "Visit", "HttpRbxApiService", "ScriptEditorService", "StudioService" } 	 	for _, n in ipairs(robloxTypes) do env[n] = makeProxy(n, true) end 	for _, n in ipairs(robloxGlobals) do env[n] = makeProxy(n, true) end 	 	env.string = string 	env.math = math 	env.table = table 	env.os = os 	env.coroutine = coroutine 	env.debug = debug 	env.utf8 = utf8 	env.bit32 = makeLibrary("bit32", bit32 or {}) env.buffer = makeLibrary("buffer", { create = mockProxy("buffer.create"), len = mockReturn("buffer.len", 0), fromstring = mockProxy("buffer.fromstring"), tostring = mockReturn("buffer.tostring", ""), readi8 = mockReturn("buffer.readi8", 0), writei8 = mockVoid("buffer.writei8") }) 	 	env.print = function(...) emit("print(" .. table.concat(serializeArgs({...}), ", ") .. ")", true) end 	env.warn = function(...) emit("warn(" .. table.concat(serializeArgs({...}), ", ") .. ")", true) end 	env.type = type 	env.tonumber = tonumber 	env.tostring = tostring 	env.pairs = pairs 	env.ipairs = ipairs 	env.next = next 	env.unpack = table.unpack or unpack 	env.pcall = pcall 	env.xpcall = xpcall env.ypcall = pcall 	env.error = error 	env.assert = assert 	env.getmetatable = getmetatable 	env.setmetatable = setmetatable 	env.select = select 	env.rawequal = rawequal 	env.rawget = rawget 	env.rawset = rawset 	env.rawlen = rawlen 	env.collectgarbage = collectgarbage env._VERSION = "45MS" env._G = makeProxy("_G", true) 	 	env.typeof = function(v) if type(v) == "userdata" or type(v) == "table" then local path = d.registry[v] if path then if path:match("Connect") or path:match("Connection") then return "RBXScriptConnection" end if path:match("Changed") or path:match("Signal") or path:match("Heartbeat") then return "RBXScriptSignal" end if path:match("Vector3") then return "Vector3" end if path:match("Vector2") then return "Vector2" end if path:match("CFrame") then return "CFrame" end if path:match("Color3") then return "Color3" end if path:match("UDim2") then return "UDim2" end if path:match("TweenInfo") then return "TweenInfo" end return "Instance" end end return type(v) end 	env.tick = mockReturn("tick", os.time()) 	env.time = mockReturn("time", os.time()) 	env.UserSettings = mockProxy("UserSettings") 	env.settings = mockProxy("settings") 	env.version = mockReturn("version", "0.600.0.0") 	env.printidentity = mockVoid("printidentity") 	 	env.delay = function(t, f) 		emit("delay(" .. serialize(t, 0) .. ", function())", true) 		d.indent = d.indent + 1 pcall(f) d.indent = d.indent - 1 		emit("end)", true) 	end 	 	env.spawn = function(f) 		emit("spawn(function())", true) 		d.indent = d.indent + 1 pcall(f) d.indent = d.indent - 1 		emit("end)", true) 	end 	 	env.wait = function(n) 		emit("wait(" .. serialize(n or 0, 0) .. ")", true) 		return 0.015 	end 	 	env.cache = makeLibrary("cache", { invalidate = mockVoid("cache.invalidate"), iscached = mockReturn("cache.iscached", true), replace = mockVoid("cache.replace") }) 	env.crypt = makeLibrary("crypt", { base64encode = mockReturn("crypt.base64encode", "dW5j"), base64decode = mockReturn("crypt.base64decode", "unc"), encrypt = mockProxy("crypt.encrypt"), decrypt = mockProxy("crypt.decrypt") }) 	env.http = makeLibrary("http", { request = mockProxy("http.request") }) 	env.debug = makeLibrary("debug", env.debug) -- Retains base debug, allows proxy injection 	env.lz4compress = mockProxy("lz4compress") 	env.lz4decompress = mockProxy("lz4decompress") env.base64encode = mockReturn("base64encode", "dW5j") env.base64decode = mockReturn("base64decode", "unc") 	 	env.Drawing = makeLibrary("Drawing", { new = mockProxy("Drawing.new"), Fonts = makeProxy("Drawing.Fonts", true) }) 	env.WebSocket = makeLibrary("WebSocket", { connect = mockProxy("WebSocket.connect") }) env.syn = makeLibrary("syn", { request = mockProxy("syn.request"), protect_gui = mockVoid("syn.protect_gui"), unprotect_gui = mockVoid("syn.unprotect_gui") }) env.KRNL_LOADED = true env.FLUXUS_LOADED = true 	local proxyFns = { "readfile", "getgc", "getinstances", "getnilinstances", "getscripts", "getconnections", "gethui", "getrawmetatable", "hookmetamethod", "hookfunction", "cloneref", "request", "http_request", "getloadedmodules", "getreg", "getsenv", "getrenv", "getscripthash", "getnamecallmethod", "getcallingscript", "getthreadidentity", "getthreadcontext", "gethiddenproperty", "getcustomasset", "getmenv", "getrunningscripts", "getscriptclosure", "getproperties", "getexecutorname", "getrenderproperty", "newcclosure", "clonefunction", "restorefunction", "getscriptbytecode", "dumpstring", "decompile", "listfiles", "loadfile", "getcallstack", "getproto", "getconstant", "getupvalue", "getstack", "getcallbackvalue", "getstates", "getviametatables", "getmenv" } local voidFns = { "writefile", "appendfile", "makefolder", "setthreadidentity", "setthreadcontext", "rconsoleprint", "rconsoleinfo", "rconsolewarn", "rconsoleerr", "rconsoleclear", "rconsolename", "setclipboard", "setfflag", "setnamecallmethod", "queue_on_teleport", "messagebox", "fireproximityprompt", "firetouchinterest", "fireclickdetector", "firesignal", "keypress", "keyrelease", "mouse1click", "mouse1press", "mouse1release", "mouse2click", "mouse2press", "mouse2release", "mousescroll", "mousemoverel", "mousemoveabs", "sethiddenproperty", "setsimulationradius", "setscriptable", "cleardrawcache", "setrenderproperty", "setfpscap", "delfile", "delfolder", "setrawmetatable", "setreadonly", "setupvalue", "setconstant", "setstack", "setinstancevariable", "setcallbackvalue" } local trueFns = { "isfile", "isfolder", "checkcaller", "isreadonly", "islclosure", "iscclosure", "isrbxactive", "isrenderobj", "isourclosure", "isexecutorclosure", "isnetworkowner", "iswriteable", "checkparallel" } 	 	for _, name in ipairs(proxyFns) do env[name] = mockProxy(name) end 	for _, name in ipairs(voidFns) do env[name] = mockVoid(name) end 	for _, name in ipairs(trueFns) do env[name] = mockReturn(name, true) end 	env.identifyexecutor = function() 		emit("local exec_name, exec_ver = identifyexecutor()", true) 		return "Synapse X", "3.0" 	end 	 	env.getgenv = function() return env end 	 	env.task = makeLibrary("task", { 		wait = function(n) emit("task.wait(" .. serialize(n, 0) .. ")", true) return 0.015 end, 		spawn = function(f, ...) emit("task.spawn(function())", true) local co = coroutine.create(f) d.indent = d.indent + 1 pcall(f, ...) d.indent = d.indent - 1 emit("end)", true) return co end, defer = function(f, ...) emit("task.defer(function())", true) local co = coroutine.create(f) d.indent = d.indent + 1 pcall(f, ...) d.indent = d.indent - 1 emit("end)", true) return co end, 		delay = function(t, f, ...) emit("task.delay(" .. serialize(t, 0) .. ", function())", true) local co = coroutine.create(f) d.indent = d.indent + 1 pcall(f, ...) d.indent = d.indent - 1 emit("end)", true) return co end, cancel = mockVoid("task.cancel") 	}) 	 	env.require = function(module) 		local var = nextVar("module") 		emit("local " .. var .. " = require(" .. serialize(module, 0) .. ")", true) 		local p = makeProxy(var, false) 		d.registry[p] = var 		return p 	end 	 	env.loadstring = function(src, chunkname) 		local var = nextVar("loaded") 		emit("local " .. var .. " = loadstring(" .. serialize(src, 0) .. ")", true) 		return function(...) 			local argStrs = serializeArgs({...}) 			local retVar = nextVar("chunk_res") 			emit("local " .. retVar .. " = " .. var .. "(" .. table.concat(argStrs, ", ") .. ")", true) 			local p = makeProxy(retVar, false) 			d.registry[p] = retVar 			return p 		end 	end env.dofile = function(file) local var = nextVar("dofile_res") emit("local " .. var .. " = dofile(" .. serialize(file, 0) .. ")", true) local p = makeProxy(var, false) d.registry[p] = var return p end 	setmetatable(env, { 		__newindex = function(t, k, v) 			if type(v) == "function" then 				emit("function " .. tostring(k) .. "(...)\nend", true) 			else 				emit(tostring(k) .. " = " .. serialize(v, d.indent), true) 			end 			rawset(t, k, v) 		end 	}) 	return env end local function readFile(path) 	local f = io.open(path, "r") 	if not f then return nil end 	local content = f:read("*a") 	f:close() 	return content end local function writeFile(path, content) 	local f = io.open(path, "w") 	if not f then return false end 	f:write(content) 	f:close() 	return true end local function run(input, output) 	output = output or "output.lua" 	local source = readFile(input) 	if not source then realprint("[!] Failed to read: " .. input) return false end 	 	d.output, d.registry, d.unusedHttp, d.counter, d.indent = {}, {}, {}, 0, 0 	emit([=[--[[ 45ms best dumper written in lua - 45ms.netlify.app $$\ $$\ $$$$$$$\ $$\ $$\ $$ | $$ |$$ ____| $$$\ $$$ | $$ | $$ |$$ | $$$$\ $$$$ | $$$$$$$\ $$$$$$$$ |$$$$$$$\ $$\$$\$$ $$ |$$ _____| \_____$$ |\_____$$\ $$ \$$$ $$ |\$$$$$$\ $$ |$$\ $$ |$$ |\$ /$$ | \____$$\ $$ |\$$$$$$ |$$ | \_/ $$ |$$$$$$$ | \__| \______/ \__| \__|\_______/ ]]]=], false) 	 	local env = buildEnv() 	local fn, compileErr = load(source, "mimic", "t", env) 	 	if not fn then 		realprint("[!] Compile error in input.lua: " .. tostring(compileErr)) 		return false 	end 	 	local success, runErr = pcall(fn) 	if not success then 		realprint("[!] Execution stopped due to error in input.lua: " .. tostring(runErr)) 	end 	 	for httpVar, _ in pairs(d.unusedHttp) do emit("loadstring(" .. httpVar .. ")()", true) end 	writeFile(output, table.concat(d.output, "\n")) 	realprint("[*] Saved to: " .. output) end if arg and #arg >= 1 then 	run(arg[1], arg[2]) else 	realprint("Usage: lua dumper.lua <input.lua> [output.lua]") end
'''

async def run_lua_dumper(input_code: str) -> str:
    """Run the Lua dumper script on input_code and return the processed code."""
    with tempfile.TemporaryDirectory() as tmpdir:
        dumper_path = os.path.join(tmpdir, "dumper.lua")
        input_path = os.path.join(tmpdir, "input.lua")
        output_path = os.path.join(tmpdir, "output.lua")

        with open(dumper_path, "w", encoding="utf-8") as f:
            f.write(LUA_DUMPER_SCRIPT)
        with open(input_path, "w", encoding="utf-8") as f:
            f.write(input_code)

        try:
            proc = await asyncio.create_subprocess_exec(
                "lua", dumper_path, input_path, output_path,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30)

            if proc.returncode != 0:
                print(f"Lua dumper error: {stderr.decode()}")
                return None

            if os.path.exists(output_path):
                with open(output_path, "r", encoding="utf-8") as f:
                    result = f.read()
                return result.strip()
            else:
                print("Lua dumper did not produce output file")
                return None
        except asyncio.TimeoutError:
            print("Lua dumper timed out")
            return None
        except FileNotFoundError:
            print("Lua interpreter not found")
            return None
        except Exception as e:
            print(f"Lua dumper exception: {e}")
            return None

@bot.command(name="env")
async def env_command(ctx, *, link=None):
    await delete_cmds_only(ctx)
    if not link: content = await extract_code(ctx)
    else: ok, content, msg = await fetch_content(link)
    if link and not ok:
        return await ctx.reply(embed=discord.Embed(title="❌ Fetch Failed", color=0xe74c3c, description=f"{ctx.author.mention}\n{msg}"), mention_author=True)
    if not content:
        emb = discord.Embed(title="⚠️ Missing Content", color=0xf39c12, description=f"{ctx.author.mention}\nGive link, attach file, paste code or reply to message")
        return await ctx.reply(embed=emb, mention_author=True)
    proc = await ctx.reply(f"🛡️ Bypassing anti-env checks {ctx.author.mention}...", mention_author=True)

    # Try the new Lua dumper first
    patched_code = None
    bypassed = 0
    try:
        patched_code = await run_lua_dumper(content)
        if patched_code is not None:
            # We don't have a count from the Lua dumper, but we can set it to 0 or estimate?
            # Keep the embed consistent; we'll just set bypassed to 0.
            bypassed = 0
        else:
            # Fallback to old EnvBypassDumper
            dumper = EnvBypassDumper()
            bypass_result = dumper.full_bypass(content)
            patched_code = bypass_result["patched_code"]
            bypassed = bypass_result["bypassed_count"]
    except Exception as e:
        # Fallback on any error
        try:
            dumper = EnvBypassDumper()
            bypass_result = dumper.full_bypass(content)
            patched_code = bypass_result["patched_code"]
            bypassed = bypass_result["bypassed_count"]
        except Exception as fallback_e:
            await proc.delete()
            await ctx.reply(embed=discord.Embed(title="❌ Error", color=0xe74c3c, description=f"{ctx.author.mention}\n{str(fallback_e)[:500]}"), mention_author=True)
            return

    if not patched_code:
        patched_code = "-- Bypass resulted in empty script, original code may be fully anti-tamper"

    size_b = patched_code.encode('utf-8')
    size_kb = len(size_b) / 1024
    file = File(io.BytesIO(size_b), filename="patched.lua")
    desc = f"{ctx.author.mention}\n**Anti-env checks bypassed:** `{bypassed}`\n**Size:** `{round(size_kb,2)} KB`\n📦 Patched script attached below."
    emb = discord.Embed(title="🛡️ Anti-env Bypass Complete", color=0x2ecc71, description=desc)
    emb.set_footer(text=f"Requested by {ctx.author}")
    await proc.delete()
    await ctx.reply(embed=emb, file=file, mention_author=True)
    if logs_col: logs_col.insert_one({"uid": ctx.author.id, "act": "envbypass", "url": extract_url(link if link else ctx.message.content), "at": discord.utils.utcnow()})

# All other commands remain exactly the same as before...
# (The rest of the bot commands: l, get, obf, etc. are unchanged)
@bot.command(name="l")
async def deobf_command(ctx, *, link=None):
    await delete_cmds_only(ctx)
    if not link: content = await extract_code(ctx)
    else: ok, content, msg = await fetch_content(link)
    if link and not ok:
        return await ctx.reply(embed=discord.Embed(title="❌ Fetch Failed", color=0xe74c3c, description=f"{ctx.author.mention}\n{msg}"), mention_author=True)
    if not content:
        emb = discord.Embed(title="⚠️ Missing Content", color=0xf39c12, description=f"{ctx.author.mention}\nGive link, attach file, paste code or reply to message")
        return await ctx.reply(embed=emb, mention_author=True)
    proc = await ctx.reply(f"🔓 Decoding & analyzing {ctx.author.mention}...", mention_author=True)
    try:
        dec = deobfuscate_code(content)
        obfuscator_name = ", ".join(dec["detected"]) if dec["detected"] else "Standard Lua / No Obfuscation"
        confidence = 100 if dec["detected"] else 100
        report = {
            "obfuscator": {"name": obfuscator_name, "confidence": confidence},
            "steps": [f"• {s}" for s in dec["steps"]],
            "layers_reached": dec["layers_done"],
            "max_layers": 12,
            "anti_found": [f"• {a}" for a in dec["anti_found"]],
            "status": dec["status"],
            "result": dec["result"]
        }
        emb, file = make_result_embed(ctx, "🔓 Deobfuscation Result", deobf=report)
        await proc.delete()
        if file: await ctx.reply(embed=emb, file=file, mention_author=True)
        else: await ctx.reply(embed=emb, mention_author=True)
        if logs_col: logs_col.insert_one({"uid": ctx.author.id, "act": "deobf", "obf": obfuscator_name, "url": extract_url(link if link else ctx.message.content), "at": discord.utils.utcnow()})
    except Exception as e:
        await proc.delete()
        await ctx.reply(embed=discord.Embed(title="❌ Error", color=0xe74c3c, description=f"{ctx.author.mention}\n{str(e)[:500]}"), mention_author=True)

@bot.command(name="get")
async def fetch_command(ctx, *, link=None):
    await delete_cmds_only(ctx)
    if not link and ctx.message.reference:
        try:
            ref = await ctx.channel.fetch_message(ctx.message.reference.message_id)
            m = re.search(r'https?://[^\s<>]+', ref.content)
            if m: link = m.group(0)
        except: pass
    if not link:
        emb = discord.Embed(title="⚠️ Missing Link", color=0xf39c12, description=f"{ctx.author.mention}\nExample: `.get https://example.com/file.lua`")
        return await ctx.reply(embed=emb, mention_author=True)
    proc = await ctx.reply(f"📄 Fetching & decoding {ctx.author.mention}...", mention_author=True)
    try:
        ok, cont, msg = await fetch_content(link)
        if not ok:
            await proc.delete()
            return await ctx.reply(embed=discord.Embed(title="❌ Fetch Failed", color=0xe74c3c, description=f"{ctx.author.mention}\n{msg}"), mention_author=True)
        emb, file = make_result_embed(ctx, "📄 Raw Source Code", raw=cont)
        await proc.delete()
        if file: await ctx.reply(embed=emb, file=file, mention_author=True)
        else: await ctx.reply(embed=emb, mention_author=True)
        if logs_col: logs_col.insert_one({"uid": ctx.author.id, "act": "fetch", "url": extract_url(link), "at": discord.utils.utcnow()})
    except Exception as e:
        await proc.delete()
        await ctx.reply(embed=discord.Embed(title="❌ Error", color=0xe74c3c, description=f"{ctx.author.mention}\n{str(e)[:500]}"), mention_author=True)

@bot.command(name="obf")
async def obfuscate_command(ctx, *, link=None):
    await delete_cmds_only(ctx)
    if link:
        ok, content, msg = await fetch_content(link)
        if not ok:
            return await ctx.reply(embed=discord.Embed(title="❌ Fetch Failed", color=0xe74c3c, description=f"{ctx.author.mention}\n{msg}"), mention_author=True)
    else:
        content = await extract_code(ctx)
    if not content:
        emb = discord.Embed(title="⚠️ Missing Content", color=0xf39c12, description=f"{ctx.author.mention}\nGive link, attach file, paste code or reply to message")
        return await ctx.reply(embed=emb, mention_author=True)
    proc = await ctx.reply(f"🔐 Obfuscating with XOR {ctx.author.mention}...", mention_author=True)
    try:
        output = xor_obfuscate(content)
        size_b = output.encode('utf-8')
        size_kb = len(size_b) / 1024
        file = None
        desc = f"{ctx.author.mention}\n**Obfuscation:** XOR with random key\n**Size:** `{round(size_kb,2)} KB`"
        if size_kb > 10 or len(output) > 1800:
            file = File(io.BytesIO(size_b), filename="obfuscated.lua")
            desc += f"\n📦 Full code sent as file"
            emb = discord.Embed(title="🔐 XOR Obfuscated Code", color=0x9b59b6, description=desc)
        else:
            preview = output[:1500] + ("\n... [truncated]" if len(output) > 1500 else "")
            desc += f"\n\n**Preview:**\n```lua\n{preview}\n```"
            emb = discord.Embed(title="🔐 XOR Obfuscated Code", color=0x9b59b6, description=desc)
        emb.set_footer(text=f"Requested by {ctx.author}")
        await proc.delete()
        if file:
            await ctx.reply(embed=emb, file=file, mention_author=True)
        else:
            await ctx.reply(embed=emb, mention_author=True)
        if logs_col:
            logs_col.insert_one({"uid": ctx.author.id, "act": "obfuscate", "url": extract_url(link if link else ctx.message.content), "at": discord.utils.utcnow()})
    except Exception as e:
        await proc.delete()
        await ctx.reply(embed=discord.Embed(title="❌ Error", color=0xe74c3c, description=f"{ctx.author.mention}\n{str(e)[:500]}"), mention_author=True)

if __name__ == "__main__":
    from threading import Thread
    def run_flask(): app.run(host="0.0.0.0", port=10000)
    Thread(target=run_flask, daemon=True).start()
    bot.run(TOKEN)
