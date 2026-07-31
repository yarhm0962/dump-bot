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
import concurrent.futures

TOKEN = os.getenv("TOKEN")
MONGODB_URI = os.getenv("MONGODB_URI")
GUILD_ID = os.getenv("GUILD_ID")
PREMIUM_ROLE_ID = os.getenv("PREMIUM_ROLE_ID")

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

# ---------- Global DM block with Premium check ----------
@bot.check
async def block_dms(ctx):
    if ctx.guild is None:
        try:
            if GUILD_ID and PREMIUM_ROLE_ID:
                guild = bot.get_guild(int(GUILD_ID))
                if guild:
                    member = guild.get_member(ctx.author.id)
                    if member and int(PREMIUM_ROLE_ID) in [role.id for role in member.roles]:
                        return True
        except:
            pass
        await ctx.send("⚠️ Please upgrade to premium to access private CMDS")
        return False
    return True

# ---------- Utility functions (unchanged) ----------
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

# ---------- Optimised deobfuscation (now a standalone sync function) ----------
def deobfuscate_code(source_text):
    max_depth = 6  # reduced from 12 for speed
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
        if ok:
            buf = res
            changed = True
            report["steps"].append(f"Layer {depth}: Base64 decoded")
        ok, res = decode_strchar(buf)
        if ok:
            buf = res
            changed = True
            report["steps"].append(f"Layer {depth}: string.char decoded")
        ok, res = decode_xor(buf)
        if ok:
            buf = res
            changed = True
            report["steps"].append(f"Layer {depth}: XOR decoded")
        # quick cleanup to reduce size
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

# ---------- Rest of classes (EnvBypassDumper, make_result_embed) unchanged ----------
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

# ---------- Events ----------
@bot.event
async def on_ready():
    print(f"✅ Logged in as: {bot.user}")
    await bot.change_presence(activity=discord.Activity(type=discord.ActivityType.watching, name=".cmds | RblXLua Tools"))
    if db: print(f"✅ Database Ready: {db.name}")

# ---------- Commands ----------
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
    emb.set_footer(text="Now fully supports XOR patterns + Fualmor style protection")
    await ctx.send(embed=emb)

@bot.command(name="l")
async def deobf_command(ctx, *, link=None):
    await delete_cmds_only(ctx)
    if not link:
        content = await extract_code(ctx)
    else:
        ok, content, msg = await fetch_content(link)
        if not ok:
            return await ctx.reply(embed=discord.Embed(title="❌ Fetch Failed", color=0xe74c3c, description=f"{ctx.author.mention}\n{msg}"), mention_author=True)
    if not content:
        emb = discord.Embed(title="⚠️ Missing Content", color=0xf39c12, description=f"{ctx.author.mention}\nGive link, attach file, paste code or reply to message")
        return await ctx.reply(embed=emb, mention_author=True)

    proc = await ctx.reply(f"🔓 Decoding & analyzing {ctx.author.mention}...", mention_author=True)

    try:
        # Offload the heavy deobfuscation to a thread to avoid blocking the event loop
        loop = asyncio.get_running_loop()
        # Use a timeout of 30 seconds to prevent hanging
        dec = await asyncio.wait_for(
            loop.run_in_executor(None, deobfuscate_code, content),
            timeout=30.0
        )

        obfuscator_name = ", ".join(dec["detected"]) if dec["detected"] else "Standard Lua / No Obfuscation"
        confidence = 100 if dec["detected"] else 100
        report = {
            "obfuscator": {"name": obfuscator_name, "confidence": confidence},
            "steps": [f"• {s}" for s in dec["steps"]],
            "layers_reached": dec["layers_done"],
            "max_layers": 6,  # updated to reflect the new limit
            "anti_found": [f"• {a}" for a in dec["anti_found"]],
            "status": dec["status"],
            "result": dec["result"]
        }
        emb, file = make_result_embed(ctx, "🔓 Deobfuscation Result", deobf=report)
        await proc.delete()
        if file:
            await ctx.reply(embed=emb, file=file, mention_author=True)
        else:
            await ctx.reply(embed=emb, mention_author=True)
        if logs_col:
            logs_col.insert_one({"uid": ctx.author.id, "act": "deobf", "obf": obfuscator_name, "url": extract_url(link if link else ctx.message.content), "at": discord.utils.utcnow()})
    except asyncio.TimeoutError:
        await proc.delete()
        await ctx.reply(embed=discord.Embed(title="⏱️ Timeout", color=0xe74c3c, description=f"{ctx.author.mention}\nDeobfuscation took too long (over 30 seconds). The script may be too large or heavily obfuscated."), mention_author=True)
    except Exception as e:
        await proc.delete()
        await ctx.reply(embed=discord.Embed(title="❌ Error", color=0xe74c3c, description=f"{ctx.author.mention}\n{str(e)[:500]}"), mention_author=True)

# ---------- Other commands (get, env, obf) remain unchanged ----------
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
    try:
        dumper = EnvBypassDumper()
        bypass_result = dumper.full_bypass(content)
        patched_code = bypass_result["patched_code"]
        bypassed = bypass_result["bypassed_count"]
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

# ---------- Run ----------
if __name__ == "__main__":
    from threading import Thread
    def run_flask(): app.run(host="0.0.0.0", port=10000)
    Thread(target=run_flask, daemon=True).start()
    bot.run(TOKEN)
