from flask import Flask
app = Flask(__name__)
@app.route('/')
def home(): return "✅ Service Running"

import os
import discord
from discord.ext import commands
import aiohttp
import re
import io
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

async def delete_command_message(ctx):
    try: await ctx.message.delete()
    except: pass

async def fetch_content(url: str) -> str:
    async with aiohttp.ClientSession() as session:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.1 Safari/537.36",
            "Referer": "https://roblox.com/"
        }
        async with session.get(url, headers=headers) as resp:
            return await resp.text()

def detect_and_deobf(code: str) -> str:
    result = []
    if "Lunr" in code or ("return(function" in code and "local L={" in code):
        result.append("[✓] Detected: Lunr Obfuscation")
        code = re.sub(r'-- This file was protected using Lunr.*?\n', '', code, flags=re.DOTALL)
    if "Luraph" in code or ("bxor" in code and "string.gsub" in code):
        result.append("[✓] Detected: Luraph / Custom XOR")
    if "Prometheus" in code or "local _=getgenv" in code:
        result.append("[✓] Detected: Prometheus / Control Flow")
    if code.isascii() and len(code) % 4 == 0 and all(c in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/" for c in code.rstrip("=")):
        result.append("[✓] Detected: Raw Base64")
    result.append("\n=== RESULT ===")
    result.append(code)
    return "\n".join(result)

async def envlog_scan(code: str) -> str:
    report = ["=== ENVIRONMENT LOGGER SCAN ==="]
    bypassed = code
    checks = [
        ("_ENVLOG", "Anti-Envlog Variable"),
        ("_GALACTIC", "Anti-logger Marker"),
        ("debug.getupvalue", "Debug Interception"),
        ("Kick.*tampered", "Kick On Tamper"),
        ("loadstring.*~=", "Hook Detection"),
        ("while true do end", "Infinite Loop Freeze"),
        ("os.exit", "Force Close Script")
    ]
    found = []
    for pattern, desc in checks:
        if re.search(pattern, bypassed):
            found.append(f"[!] FOUND: {desc}")
            bypassed = re.sub(pattern, f"-- BYPASSED {pattern}", bypassed)
    if found:
        report.extend(found)
        report.append("\n[+] All markers commented out")
    else:
        report.append("[✓] No strong anti-log found")
    report.append("\n=== SCANNED CODE ===")
    report.append(bypassed)
    return "\n".join(report)

@bot.event
async def on_ready():
    print(f"✅ Logged in as: {bot.user}")
    if db is not None:
        print(f"✅ Database Ready: {db.name}")

@bot.group(name="db, invoke_without_command=True)
async def db_group(ctx):
    await delete_command_message(ctx)
    emb = discord.Embed(title="Database Commands", color=0x2b2d31, description=f"Hey {ctx.author.mention}\nUse these sub-commands:")
    emb.add_field(name="`db status`", value="Check database connection", inline=False)
    emb.add_field(name="`db clear`", value="Clear all stored data (owner only)", inline=False)
    await ctx.send(embed=emb)

@db_group.command(name="status")
async def db_status(ctx):
    await delete_command_message(ctx)
    if mongo_client is not None and db is not None:
        emb = discord.Embed(title="Database Status", color=0x2ecc71, description=f"✅ {ctx.author.mention}\nMongoDB is connected and working properly")
    else:
        emb = discord.Embed(title="Database Status", color=0xe74c3c, description=f"❌ {ctx.author.mention}\nNot connected to database")
    await ctx.send(embed=emb)

@db_group.command(name="clear")
@commands.is_owner()
async def db_clear(ctx):
    await delete_command_message(ctx)
    if settings_col is not None and logs_col is not None:
        settings_col.delete_many({})
        logs_col.delete_many({})
        emb = discord.Embed(title="Database Status", color=0x2ecc71, description=f"✅ {ctx.author.mention}\nAll database data cleared successfully")
    else:
        emb = discord.Embed(title="Database Status", color=0xe74c3c, description=f"❌ {ctx.author.mention}\nDatabase not available")
    await ctx.send(embed=emb)

@bot.command(name="cmds")
async def show_commands(ctx):
    await delete_command_message(ctx)
    emb = discord.Embed(title="RblXLua Tool Commands", color=0x9b59b6, description=f"Hello {ctx.author.mention}, here are all available commands:")
    emb.add_field(name="`.l <link/loadstring>`", value="Detect protection and deobfuscate → send result file", inline=False)
    emb.add_field(name="`.get <link/loadstring>`", value="Fetch full raw source code → send file", inline=False)
    emb.add_field(name="`.env <link/loadstring>`", value="Scan anti-log measures and bypass → send report", inline=False)
    emb.add_field(name="`.db`", value="Database management commands", inline=False)
    emb.set_footer(text="All results sent as downloadable files")
    await ctx.send(embed=emb)

@bot.command(name="l")
async def deobf_command(ctx, *, link: str):
    await delete_command_message(ctx)
    processing = await ctx.send(f"Processing obfuscation detection {ctx.author.mention}...")
    try:
        url_match = re.search(r'https?://[^\s"\'<>)]+', link)
        if not url_match:
            await processing.edit(content=f"❌ {ctx.author.mention} No valid URL found")
            return
        url = url_match.group(0)
        code = await fetch_content(url)
        result = detect_and_deobf(code)
        file = discord.File(io.StringIO(result), filename="deobfuscated_result.lua")
        await processing.delete()
        await ctx.send(f"✅ Done {ctx.author.mention}: `{url}`", file=file)
        if logs_col is not None:
            logs_col.insert_one({"user_id": ctx.author.id, "action": "deobfuscate", "url": url, "time": discord.utils.utcnow()})
    except Exception as e:
        await processing.edit(content=f"❌ {ctx.author.mention} Error: {str(e)[:120]}")

@bot.command(name="get")
async def fetch_command(ctx, *, link: str):
    await delete_command_message(ctx)
    processing = await ctx.send(f"Fetching source code {ctx.author.mention}...")
    try:
        url_match = re.search(r'https?://[^\s"\'<>)]+', link)
        if not url_match:
            await processing.edit(content=f"❌ {ctx.author.mention} No valid URL found")
            return
        url = url_match.group(0)
        code = await fetch_content(url)
        file = discord.File(io.StringIO(code), filename="raw_fetched_source.lua")
        await processing.delete()
        await ctx.send(f"✅ Done {ctx.author.mention}: `{url}`", file=file)
        if logs_col is not None:
            logs_col.insert_one({"user_id": ctx.author.id, "action": "fetch", "url": url, "time": discord.utils.utcnow()})
    except Exception as e:
        await processing.edit(content=f"❌ {ctx.author.mention} Error: {str(e)[:120]}")

@bot.command(name="env")
async def envlog_command(ctx, *, link: str):
    await delete_command_message(ctx)
    processing = await ctx.send(f"Scanning anti-environment logger {ctx.author.mention}...")
    try:
        url_match = re.search(r'https?://[^\s"\'<>)]+', link)
        if not url_match:
            await processing.edit(content=f"❌ {ctx.author.mention} No valid URL found")
            return
        url = url_match.group(0)
        code = await fetch_content(url)
        result = await envlog_scan(code)
        file = discord.File(io.StringIO(result), filename="envlog_analysis.lua")
        await processing.delete()
        await ctx.send(f"✅ Done {ctx.author.mention}: `{url}`", file=file)
        if logs_col is not None:
            logs_col.insert_one({"user_id": ctx.author.id, "action": "envscan", "url": url, "time": discord.utils.utcnow()})
    except Exception as e:
        await processing.edit(content=f"❌ {ctx.author.mention} Error: {str(e)[:120]}")

if __name__ == "__main__":
    from threading import Thread
    def run_flask(): app.run(host="0.0.0.0", port=10000)
    Thread(target=run_flask, daemon=True).start()
    bot.run(TOKEN)
