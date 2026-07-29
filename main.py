from flask import Flask
app = Flask(__name__)
@app.route('/')
def home(): return "✅ Service Running"

import os
import discord
from discord import File
from discord.ext import commands
import aiohttp
import re
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
    if ctx.invoked_with == "cmds":
        try: await ctx.message.delete()
        except: pass

async def fetch_content(url: str) -> tuple[bool, str, str]:
    valid_url = re.search(r'https?://[^\s"\'<>)]+', url)
    if not valid_url:
        return False, "", "Invalid URL format detected"
    clean_url = valid_url.group(0)
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as session:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
                "Accept": "text/plain,application/lua,text/x-lua"
            }
            async with session.get(clean_url, headers=headers, allow_redirects=True) as resp:
                if resp.status == 404:
                    return False, "", "❌ Server returned 404: File/Page Not Found"
                if resp.status == 403:
                    return False, "", "❌ Server returned 403: Access Forbidden / Blocked"
                if resp.status >= 400:
                    return False, "", f"❌ Server Error: Status Code {resp.status}"
                body = await resp.text(encoding="utf-8", errors="replace")
                return True, body, "Success"
    except aiohttp.ClientConnectionError:
        return False, "", "❌ Could not connect to domain / DNS failed"
    except aiohttp.ClientTimeout:
        return False, "", "❌ Request timed out, site took too long to respond"
    except Exception as e:
        return False, "", f"❌ Fetch Error: {str(e)[:100]}"

def advanced_deobfuscate(code: str) -> str:
    if not code or len(code.strip()) < 5: return "No valid script content found"
    result = code

    result = re.sub(r'--\[\[=*\[.*?\]=*\]', '', result, flags=re.DOTALL)
    result = re.sub(r'--.*?$', '', result, flags=re.MULTILINE)
    result = re.sub(r'^\s*#![^\n]*\n', '', result)
    result = re.sub(r'\s+', ' ', result)

    try:
        b64_pattern = r'loadstring\s*\(\s*base64\.decode\s*\(\s*["\']([A-Za-z0-9+/=]+)["\']\s*\)'
        m = re.search(b64_pattern, result)
        if m:
            decoded = base64.b64decode(m.group(1)).decode('utf-8', errors='replace')
            result = decoded
    except: pass

    try:
        xor_key = re.search(r'local\s+\w+\s*=\s*["\']([^"\']{4,})["\']', result)
        xor_data = re.search(r'["\']([A-Za-z0-9+/=]{16,})["\']', result)
        if xor_key and xor_data:
            key = xor_key.group(1)
            data = base64.b64decode(xor_data.group(2)).decode('latin1')
            out = []
            for idx, ch in enumerate(data):
                k = ord(key[idx % len(key)])
                out.append(chr(ord(ch) ^ k))
            result = ''.join(out)
    except: pass

    wearedevs = re.search(r'string\.char\(([\d,\s]+)\)', result)
    if wearedevs:
        try:
            nums = [int(x.strip()) for x in wearedevs.group(1).split(',') if x.strip().isdigit()]
            result = ''.join(chr(n) for n in nums)
        except: pass

    return result.strip()

def scan_envlog(code: str) -> dict:
    findings = {"risks": [], "severity": "Safe", "count": 0}
    patterns = {
        "Galactic / Env Logger": r'galactic|env.?log|dump.?script',
        "Bytecode Extraction": r'string\.dump\(',
        "Function Hooking": r'hookfunction|cclosure|hookmetamethod',
        "File Operations": r'writefile|readfile|makefolder|listfiles',
        "Data Exfiltration": r'HttpPost|discord\.com/api/webhook|pastebin|transfer.sh',
        "Debug Interception": r'debug\.getupvalue|debug\.getlocal|getfenv'
    }
    for name, pat in patterns.items():
        if re.search(pat, code, re.IGNORECASE):
            findings["risks"].append(f"⚠️ {name}")
            findings["count"] += 1
    if findings["count"] >= 3: findings["severity"] = "High Risk"
    elif findings["count"] >= 1: findings["severity"] = "Low Risk"
    return findings

def make_result_embed(ctx, title: str, content: str, status: str):
    if not content or len(content.strip()) < 3:
        emb = discord.Embed(title=title, color=0xe74c3c, description=f"{ctx.author.mention}\n❌ Result is empty or too small to process\nStatus: **{status}**")
        return emb, None
    content_bytes = content.encode('utf-8')
    size_kb = len(content_bytes) / 1024
    file = None
    if size_kb > 10 or len(content) > 1900:
        file = File(io.BytesIO(content_bytes), filename="processed_result.lua")
        desc = f"{ctx.author.mention}\n✅ Completed | Status: **{status}**\n📦 Size: `{round(size_kb, 2)} KB`\n📎 Sent as file to keep full content safe"
        emb = discord.Embed(title=title, color=0x3498db, description=desc)
    else:
        preview = content[:1850] + ("\n... [truncated end]" if len(content) > 1850 else "")
        desc = f"{ctx.author.mention}\n✅ Completed | Status: **{status}**\n📦 Size: `{round(size_kb, 2)} KB`\n\n```lua\n{preview}\n```"
        emb = discord.Embed(title=title, color=0x2ecc71, description=desc)
    emb.set_footer(text=f"Requested by: {ctx.author}")
    return emb, file

@bot.event
async def on_ready():
    print(f"✅ Logged in as: {bot.user}")
    if db: print(f"✅ Database Ready: {db.name}")

@bot.group(name="db", invoke_without_command=True)
async def db_group(ctx):
    await delete_cmds_only(ctx)
    emb = discord.Embed(title="Database Commands", color=0x2b2d31, description=f"Hey {ctx.author.mention}\nUse these sub-commands:")
    emb.add_field(name="`db status`", value="Check database connection", inline=False)
    emb.add_field(name="`db clear`", value="Clear stored data (owner only)", inline=False)
    await ctx.send(embed=emb)

@db_group.command(name="status")
async def db_status(ctx):
    await delete_cmds_only(ctx)
    if mongo_client and db:
        emb = discord.Embed(title="Database Status", color=0x2ecc71, description=f"✅ {ctx.author.mention}\nMongoDB connected and working")
    else:
        emb = discord.Embed(title="Database Status", color=0xe74c3c, description=f"❌ {ctx.author.mention}\nNot connected to database")
    await ctx.send(embed=emb)

@db_group.command(name="clear")
@commands.is_owner()
async def db_clear(ctx):
    await delete_cmds_only(ctx)
    if settings_col and logs_col:
        settings_col.delete_many({})
        logs_col.delete_many({})
        emb = discord.Embed(title="Database Status", color=0x2ecc71, description=f"✅ {ctx.author.mention}\nAll data cleared successfully")
    else:
        emb = discord.Embed(title="Database Status", color=0xe74c3c, description=f"❌ {ctx.author.mention}\nDatabase not available")
    await ctx.send(embed=emb)

@bot.command(name="cmds")
async def show_commands(ctx):
    await delete_cmds_only(ctx)
    emb = discord.Embed(title="RblXLua Tool Commands", color=0x9b59b6, description=f"Hello {ctx.author.mention}, available commands:")
    emb.add_field(name="`.l <link/loadstring>`", value="Advanced deobfuscation", inline=False)
    emb.add_field(name="`.get <link/loadstring>`", value="Fetch raw full source", inline=False)
    emb.add_field(name="`.env <link/loadstring>`", value="Deep anti-log scan", inline=False)
    emb.add_field(name="`.db`", value="Database tools", inline=False)
    emb.set_footer(text="Smart output: preview if small, file if large/long")
    await ctx.send(embed=emb)

@bot.command(name="l")
async def deobf_command(ctx, *, link=None):
    await delete_cmds_only(ctx)
    if not link:
        emb = discord.Embed(title="⚠️ Missing Link", color=0xf39c12, description=f"{ctx.author.mention}\nPlease include the full link or loadstring!\nExample: `.l https://api-booster.onrender.com/script.lua`")
        return await ctx.reply(embed=emb, mention_author=True)
    processing = await ctx.reply(f"🔄 Processing deobfuscation {ctx.author.mention}...", mention_author=True)
    ok, content, msg = await fetch_content(link)
    if not ok:
        await processing.delete()
        err_emb = discord.Embed(title="❌ Fetch Failed", color=0xe74c3c, description=f"{ctx.author.mention}\n{msg}")
        return await ctx.reply(embed=err_emb, mention_author=True)
    result = advanced_deobfuscate(content)
    emb, file = make_result_embed(ctx, "🔓 Deobfuscation Complete", result, "Successfully Processed")
    await processing.delete()
    if file:
        await ctx.reply(embed=emb, file=file, mention_author=True)
    else:
        await ctx.reply(embed=emb, mention_author=True)
    if logs_col: logs_col.insert_one({"uid": ctx.author.id, "act": "deobf", "url": link, "at": discord.utils.utcnow()})

@bot.command(name="get")
async def fetch_command(ctx, *, link=None):
    await delete_cmds_only(ctx)
    if not link:
        emb = discord.Embed(title="⚠️ Missing Link", color=0xf39c12, description=f"{ctx.author.mention}\nPlease include the full link!\nExample: `.get https://example.com/script.lua`")
        return await ctx.reply(embed=emb, mention_author=True)
    processing = await ctx.reply(f"🔄 Fetching source {ctx.author.mention}...", mention_author=True)
    ok, content, msg = await fetch_content(link)
    if not ok:
        await processing.delete()
        err_emb = discord.Embed(title="❌ Fetch Failed", color=0xe74c3c, description=f"{ctx.author.mention}\n{msg}")
        return await ctx.reply(embed=err_emb, mention_author=True)
    emb, file = make_result_embed(ctx, "📄 Raw Source Code", content, "Fetched Successfully")
    await processing.delete()
    if file:
        await ctx.reply(embed=emb, file=file, mention_author=True)
    else:
        await ctx.reply(embed=emb, mention_author=True)
    if logs_col: logs_col.insert_one({"uid": ctx.author.id, "act": "fetch", "url": link, "at": discord.utils.utcnow()})

@bot.command(name="env")
async def envlog_command(ctx, *, link=None):
    await delete_cmds_only(ctx)
    if not link:
        emb = discord.Embed(title="⚠️ Missing Link", color=0xf39c12, description=f"{ctx.author.mention}\nPlease include the full link or loadstring!")
        return await ctx.reply(embed=emb, mention_author=True)
    processing = await ctx.reply(f"🔍 Running deep scan {ctx.author.mention}...", mention_author=True)
    ok, content, msg = await fetch_content(link)
    if not ok:
        await processing.delete()
        err_emb = discord.Embed(title="❌ Fetch Failed", color=0xe74c3c, description=f"{ctx.author.mention}\n{msg}")
        return await ctx.reply(embed=err_emb, mention_author=True)
    scan = scan_envlog(content)
    await processing.delete()
    emb = discord.Embed(title="🛡️ Environment Scan Report", color=0xe67e22, description=f"{ctx.author.mention}\n**Severity:** `{scan['severity']}`\n**Total Risks:** `{scan['count']}`\n")
    if scan["risks"]:
        for r in scan["risks"]: emb.add_field(name=r, value="— Detected", inline=False)
    else:
        emb.description += "\n✅ No env loggers, dumpers or anti-tamper bypass found"
    emb.add_field(name="Info", value="Scan detects most common logging tools used right now", inline=False)
    await ctx.reply(embed=emb, mention_author=True)
    if logs_col: logs_col.insert_one({"uid": ctx.author.id, "act": "envscan", "url": link, "at": discord.utils.utcnow()})

if __name__ == "__main__":
    from threading import Thread
    def run_flask(): app.run(host="0.0.0.0", port=10000)
    Thread(target=run_flask, daemon=True).start()
    bot.run(TOKEN)
