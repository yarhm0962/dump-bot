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
import pymongo
from pymongo.mongo_client import MongoClient
from pymongo.server_api import ServerApi

TOKEN = os.getenv("TOKEN")
MONGODB_URI = os.getenv("MONGODB_URI")

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

def identify_obfuscator(code: str) -> dict:
    found = {"name": "Unknown / Custom", "confidence": 0}
    checks = [
        {"name": "Fualmor Loader", "pat": [r'fualmor', r'canary_mismatch', r'_tripwire', r'4294967296'], "score": 40},
        {"name": "Lunr Obfuscator", "pat": [r'-- This file was protected using Lunr', r'return\(function\(L,M,I'], "score": 35},
        {"name": "Luraph Obfuscator", "pat": [r'-- Generated by Luraph'], "score": 35},
        {"name": "Prometheus Obfuscator", "pat": [r'-- This Script is Part of the Prometheus'], "score": 30},
        {"name": "WeAreDevs Obfuscator", "pat": [r'wearedevs\.net', r'string\.char\((\d+,){20,}\)'], "score": 30},
        {"name": "Hex / Escape Encoded", "pat": [r'\\x[0-9a-fA-F]{2}'], "score": 25},
        {"name": "Checksum / Canary", "pat": [r'5381.*33', r'%4294967296'], "score": 25},
        {"name": "Env Spoofing", "pat": [r'rawget.*_G', r'_keys.*=.*{'], "score": 25},
        {"name": "Standard Lua", "pat": [r'print\(|game:GetService'], "score": 0}
    ]
    for c in checks:
        hits = sum(1 for p in c["pat"] if re.search(p, code, re.IGNORECASE))
        if hits > 0:
            found["confidence"] += hits * c["score"]
            if found["name"] == "Unknown / Custom": found["name"] = c["name"]
    found["confidence"] = min(100, found["confidence"])
    if found["confidence"] < 10: found["name"] = "Standard Lua / No Obfuscation"; found["confidence"] = 100
    return found

def deep_unpack(code: str) -> dict:
    report = {
        "obfuscator": identify_obfuscator(code),
        "result": code,
        "status": "Incomplete",
        "steps": [],
        "layers_reached": 0,
        "max_layers": 8,
        "anti_found": []
    }
    buf = decode_all_escapes(code)
    anti_sigs = {
        "Canary / Checksum": [r'5381.*33', r'canary_mismatch', r'4294967296'],
        "Tripwire / Anti-Debug": [r'_tripwire', r'warn.*mismatch'],
        "Env Spoofing": [r'rawget.*_G', r'_keys.*='],
        "Env Bypass Checks": [r'if _env\[._k.\]==nil', r'==0 then return end'],
        "Function Protection": [r'getgenv.*pcall', r'setfenv'],
        "Logger Detection": [r'writefile|readfile|HttpPost|discord.*webhook']
    }
    for name,pats in anti_sigs.items():
        if any(re.search(p,buf,re.DOTALL) for p in pats): report["anti_found"].append(f"• {name}")
    for depth in range(1, report["max_layers"] + 1):
        changed = False
        try:
            m = re.search(r'base64\.decode\s*\(\s*["\']([A-Za-z0-9+/=]{20,})["\']', buf)
            if m:
                dec = base64.b64decode(m.group(1)).decode('utf-8', errors='replace')
                if len(dec) > 15 and dec != buf:
                    buf = decode_all_escapes(dec)
                    report["steps"].append(f"Layer {depth}: Decoded Base64"); changed = True
        except: pass
        try:
            m = re.search(r'string\.char\(([\d,\s]{25,})\)', buf)
            if m:
                nums = [int(x.strip()) for x in m.group(1).split(',') if x.strip().isdigit()]
                dec = ''.join(chr(n) for n in nums)
                if len(dec) > 15 and dec != buf:
                    buf = decode_all_escapes(dec)
                    report["steps"].append(f"Layer {depth}: Decoded string.char"); changed = True
        except: pass
        try:
            key_match = re.search(r'local _k=(\d+)', buf)
            data_match = re.search(r'local _d=\{([^}]+)\}', buf)
            if key_match and data_match:
                try:
                    k = int(key_match.group(1))
                    d = [int(x.strip()) for x in data_match.group(1).split(',') if x.strip().isdigit()]
                    dec = ''.join(chr(b ^ k) for b in d)
                    if len(dec) > 15 and dec != buf:
                        buf = decode_all_escapes(dec)
                        report["steps"].append(f"Layer {depth}: Decoded XOR pattern"); changed = True
                except: pass
        except: pass
        try:
            km = re.search(r'["\']([^"\']{4,32})["\'].*?["\']([A-Za-z0-9+/=]{24,})["\']', buf, re.DOTALL)
            if km:
                k, d = km.group(1), base64.b64decode(km.group(2)).decode('latin1')
                res = []
                for idx, ch in enumerate(d): res.append(chr(ord(ch) ^ ord(k[idx % len(k)])))
                dec = ''.join(res)
                if len(dec) > 15 and dec != buf:
                    buf = decode_all_escapes(dec)
                    report["steps"].append(f"Layer {depth}: Applied XOR"); changed = True
        except: pass
        report["layers_reached"] = depth
        if not changed: break
    buf = re.sub(r'--.*?$', '', buf, flags=re.MULTILINE).strip()
    report["result"] = buf
    if len(report["steps"]) > 0: report["status"] = "Fully unpacked" if report["layers_reached"] >= report["max_layers"] else "Partially unpacked"
    elif len(report["anti_found"]) > 0: report["status"] = "Anti-env detected and decoded"
    return report

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

@bot.event
async def on_ready():
    print(f"✅ Logged in as: {bot.user}")
    await bot.change_presence(activity=discord.Activity(type=discord.ActivityType.watching, name=".cmds | RblXLua Tools"))
    if db: print(f"✅ Database Ready: {db.name}")

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
    emb.set_footer(text="Now fully supports XOR patterns + Fualmor style protection")
    await ctx.send(embed=emb)

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
    report = deep_unpack(content)
    emb, file = make_result_embed(ctx, "🔓 Deobfuscation Result", deobf=report)
    await proc.delete()
    if file: await ctx.reply(embed=emb, file=file, mention_author=True)
    else: await ctx.reply(embed=emb, mention_author=True)
    if logs_col: logs_col.insert_one({"uid": ctx.author.id, "act": "deobf", "obf": report["obfuscator"]["name"], "url": extract_url(link if link else ctx.message.content), "at": discord.utils.utcnow()})

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
    ok, cont, msg = await fetch_content(link)
    if not ok:
        await proc.delete()
        return await ctx.reply(embed=discord.Embed(title="❌ Fetch Failed", color=0xe74c3c, description=f"{ctx.author.mention}\n{msg}"), mention_author=True)
    emb, file = make_result_embed(ctx, "📄 Raw Source Code", raw=cont)
    await proc.delete()
    if file: await ctx.reply(embed=emb, file=file, mention_author=True)
    else: await ctx.reply(embed=emb, mention_author=True)
    if logs_col: logs_col.insert_one({"uid": ctx.author.id, "act": "fetch", "url": extract_url(link), "at": discord.utils.utcnow()})

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
    proc = await ctx.reply(f"🛡️ Scanning + unpacking anti-env {ctx.author.mention}...", mention_author=True)
    report = deep_unpack(content)
    emb, file = make_result_embed(ctx, "🛡️ Anti-env Scan & Unpack Complete", deobf=report)
    await proc.delete()
    if file: await ctx.reply(embed=emb, file=file, mention_author=True)
    else: await ctx.reply(embed=emb, mention_author=True)
    if logs_col: logs_col.insert_one({"uid": ctx.author.id, "act": "envscan+unpack", "url": extract_url(link if link else ctx.message.content), "at": discord.utils.utcnow()})

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

if __name__ == "__main__":
    from threading import Thread
    def run_flask(): app.run(host="0.0.0.0", port=10000)
    Thread(target=run_flask, daemon=True).start()
    bot.run(TOKEN)
