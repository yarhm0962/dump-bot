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
import string
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

async def fetch_content(url: str) -> str:
    async with aiohttp.ClientSession() as session:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.1 Safari/537.36",
            "Referer": "https://roblox.com/"
        }
        async with session.get(url) as resp:
            return await resp.text()

def advanced_deobfuscate(code: str) -> str:
    original = code
    result = code

    result = re.sub(r'--\[\[=*\[.*?\]=*\]', '', result, flags=re.DOTALL)
    result = re.sub(r'--.*?$', '', result, flags=re.MULTILINE)
    result = re.sub(r'^\s*#![^\n]*\n', '', result)

    xor_pattern = r'local\s+\w+\s*=\s*\{([^}]+)\}.*?for.*?\w+\s*=\s*(\d+)\s*,.*?\1\s*\^=\s*string\.byte\('
    if re.search(xor_pattern, result, re.DOTALL):
        try:
            key_match = re.search(r'local\s+\w+\s*=\s*["\']([^"\']+)["\']', result)
            data_match = re.search(r'local\s+\w+\s*=\s*([\'"])([0-9a-fA-F+/=]+)\1', result)
            if key_match and data_match:
                key = key_match.group(1)
                b64_data = data_match.group(2)
                decoded = base64.b64decode(b64_data).decode('latin1')
                deobf = []
                for i, c in enumerate(decoded):
                    kc = key[i % len(key)]
                    deobf.append(chr(ord(c) ^ ord(kc)))
                result = ''.join(deobf)
        except: pass

    wearedevs_patterns = [
        r'local\s+_=string\.dump\(loadstring\(string\.char\((\d+(?:,\d+)*)\)\)\)',
        r'local\s+\w+\s*=\s*0x[0-9a-fA-F]+\s*\^\s*0x[0-9a-fA-F]+',
        r'for\s+\w+\s*=\s*\d+\s*,\s*string\.len\(\w+\)\s*do\s*.*?\w+\s*=\s*\w+\s*\^\s*\(\w+%#\w+\)'
    ]
    for pat in wearedevs_patterns:
        if re.search(pat, result):
            try:
                nums = re.search(pat, result).group(1).split(',')
                chars = ''.join(chr(int(n)) for n in nums)
                result = chars
                break
            except: pass

    return result if len(result.strip()) > 10 else original

def scan_envlog(code: str) -> dict:
    findings = {"risks": [], "severity": "Safe", "count": 0}
    patterns = {
        "Galactic Env Logger": r'Galactic|galactic.*logger|envlog',
        "String Dump Extraction": r'string\.dump\s*\(',
        "Hooked Functions": r'hookfunction|newcclosure|hookmetamethod',
        "Code Dumping": r'writefile|readfile.*\.lua|listfiles',
        "Remote Logging": r'HttpPost|HttpGet.*discord\.com/api/webhook'
    }
    for name, pat in patterns.items():
        if re.search(pat, code, re.IGNORECASE):
            findings["risks"].append(f"⚠️ {name} Detected")
            findings["count"] += 1
    if findings["count"] >= 3: findings["severity"] = "High Risk"
    elif findings["count"] >= 1: findings["severity"] = "Low Risk"
    return findings

def make_result_embed(ctx, title: str, content: str, status: str):
    size_kb = len(content.encode('utf-8')) / 1024
    if size_kb > 10:
        file = File(io.BytesIO(content.encode('utf-8')), filename="result.lua")
        emb = discord.Embed(title=title, color=0x3498db, description=f"{ctx.author.mention}\n✅ Completed | Status: **{status}**\n📦 File Size: `{round(size_kb, 2)} KB`\n📎 Too large for preview, sent as attachment")
        return emb, file
    else:
        preview = content[:1900] + ("\n... (truncated)" if len(content) > 1900 else "")
        emb = discord.Embed(title=title, color=0x2ecc71, description=f"{ctx.author.mention}\n✅ Completed | Status: **{status}**\n📦 Size: `{round(size_kb, 2)} KB`\n\n```lua\n{preview}\n```")
        return emb, None

@bot.event
async def on_ready():
    print(f"✅ Logged in as: {bot.user}")
    if db is not None: print(f"✅ Database Ready: {db.name}")

@bot.group(name="db", invoke_without_command=True)
async def db_group(ctx):
    await delete_cmds_only(ctx)
    emb = discord.Embed(title="Database Commands", color=0x2b2d31, description=f"Hey {ctx.author.mention}\nUse these sub-commands:")
    emb.add_field(name="`db status`", value="Check database connection", inline=False)
    emb.add_field(name="`db clear`", value="Clear all stored data (owner only)", inline=False)
    await ctx.send(embed=emb)

@db_group.command(name="status")
async def db_status(ctx):
    await delete_cmds_only(ctx)
    if mongo_client is not None and db is not None:
        emb = discord.Embed(title="Database Status", color=0x2ecc71, description=f"✅ {ctx.author.mention}\nMongoDB is connected and working properly")
    else:
        emb = discord.Embed(title="Database Status", color=0xe74c3c, description=f"❌ {ctx.author.mention}\nNot connected to database")
    await ctx.send(embed=emb)

@db_group.command(name="clear")
@commands.is_owner()
async def db_clear(ctx):
    await delete_cmds_only(ctx)
    if settings_col is not None and logs_col is not None:
        settings_col.delete_many({})
        logs_col.delete_many({})
        emb = discord.Embed(title="Database Status", color=0x2ecc71, description=f"✅ {ctx.author.mention}\nAll database data cleared successfully")
    else:
        emb = discord.Embed(title="Database Status", color=0xe74c3c, description=f"❌ {ctx.author.mention}\nDatabase not available")
    await ctx.send(embed=emb)

@bot.command(name="cmds")
async def show_commands(ctx):
    await delete_cmds_only(ctx)
    emb = discord.Embed(title="RblXLua Tool Commands", color=0x9b59b6, description=f"Hello {ctx.author.mention}, here are all available commands:")
    emb.add_field(name="`.l <link/loadstring>`", value="Advanced deobfuscation + preview/file output", inline=False)
    emb.add_field(name="`.get <link/loadstring>`", value="Fetch raw source code", inline=False)
    emb.add_field(name="`.env <link/loadstring>`", value="Full env log & anti-tamper deep scan", inline=False)
    emb.add_field(name="`.db`", value="Database management", inline=False)
    emb.set_footer(text="Smart preview: shows code under 10KB, sends file for larger")
    await ctx.send(embed=emb)

@bot.command(name="l")
async def deobf_command(ctx, *, link=None):
    await delete_cmds_only(ctx)
    if not link:
        emb = discord.Embed(title="⚠️ Missing Link", color=0xf39c12, description=f"{ctx.author.mention}\nYou need to include the script link or full loadstring!\n\n**Correct usage example:**\n`.l https://example.com/script.lua`\n`.l loadstring(game:HttpGet('link'))()`")
        await ctx.send(embed=emb)
        return
    processing = await ctx.send(f"🔄 Processing advanced deobfuscation {ctx.author.mention}...")
    try:
        code = await fetch_content(link)
        deobf_result = advanced_deobfuscate(code)
        emb, file = make_result_embed(ctx, "🔓 Deobfuscation Complete", deobf_result, "Full Recovery")
        await processing.delete()
        if file: await ctx.send(embed=emb, file=file)
        else: await ctx.send(embed=emb)
        if logs_col is not None:
            logs_col.insert_one({"user_id": ctx.author.id, "action": "deobfuscate", "url": link, "time": discord.utils.utcnow()})
    except Exception as e:
        await processing.edit(content=f"❌ {ctx.author.mention} Error: {str(e)[:120]}")

@bot.command(name="get")
async def fetch_command(ctx, *, link=None):
    await delete_cmds_only(ctx)
    if not link:
        emb = discord.Embed(title="⚠️ Missing Link", color=0xf39c12, description=f"{ctx.author.mention}\nYou need to include the script link or full loadstring!\n\n**Correct usage example:**\n`.get https://example.com/script.lua`")
        await ctx.send(embed=emb)
        return
    processing = await ctx.send(f"🔄 Fetching source {ctx.author.mention}...")
    try:
        code = await fetch_content(link)
        emb, file = make_result_embed(ctx, "📄 Raw Source Code", code, "Fetched")
        await processing.delete()
        if file: await ctx.send(embed=emb, file=file)
        else: await ctx.send(embed=emb)
        if logs_col is not None:
            logs_col.insert_one({"user_id": ctx.author.id, "action": "fetch", "url": link, "time": discord.utils.utcnow()})
    except Exception as e:
        await processing.edit(content=f"❌ {ctx.author.mention} Error: {str(e)[:120]}")

@bot.command(name="env")
async def envlog_command(ctx, *, link=None):
    await delete_cmds_only(ctx)
    if not link:
        emb = discord.Embed(title="⚠️ Missing Link", color=0xf39c12, description=f"{ctx.author.mention}\nYou need to include the script link or full loadstring!\n\n**Correct usage example:**\n`.env https://example.com/script.lua`")
        await ctx.send(embed=emb)
        return
    processing = await ctx.send(f"🔍 Running deep env log scan {ctx.author.mention}...")
    try:
        code = await fetch_content(link)
        scan = scan_envlog(code)
        emb = discord.Embed(title="🛡️ Environment Scan Report", color=0xe67e22, description=f"{ctx.author.mention}\n**Severity Level:** `{scan['severity']}`\n**Threats Found:** `{scan['count']}`\n\nDetected items:")
        if scan["risks"]:
            for r in scan["risks"]: emb.add_field(name=r, value="—", inline=False)
        else:
            emb.description += "\n✅ No env loggers or dumpers found"
        emb.add_field(name="Recommendation", value="Add anti-tamper checks if any risks appear", inline=False)
        await processing.delete()
        await ctx.send(embed=emb)
        if logs_col is not None:
            logs_col.insert_one({"user_id": ctx.author.id, "action": "envscan", "url": link, "time": discord.utils.utcnow()})
    except Exception as e:
        await processing.edit(content=f"❌ {ctx.author.mention} Error: {str(e)[:120]}")

if __name__ == "__main__":
    from threading import Thread
    def run_flask(): app.run(host="0.0.0.0", port=10000)
    Thread(target=run_flask, daemon=True).start()
    bot.run(TOKEN)
