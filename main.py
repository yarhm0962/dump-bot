from flask import Flask, request, jsonify
app = Flask(__name__)

@app.after_request
def after_request(response):
    response.headers.add('Access-Control-Allow-Origin', '*')
    response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization')
    response.headers.add('Access-Control-Allow-Methods', 'GET,PUT,POST,DELETE,OPTIONS')
    return response

@app.route('/')
def home(): return "✅ RblXLua Service Running"
@app.route('/ping')
def ping(): return "pong"

import os
import discord
from discord import File, app_commands
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
import threading
import time
import subprocess
import tempfile
from urllib.parse import urlparse, parse_qs, quote_plus
from bson import ObjectId
from datetime import datetime, timedelta
import marshal
import codecs
import zlib
import gzip
import bz2
from pathlib import Path
import shutil
from typing import Union, Optional, Sequence, Callable
from bs4 import BeautifulSoup

TOKEN = os.getenv("TOKEN")
if not TOKEN:
    print("❌ TOKEN missing")
    exit(1)

MONGODB_URI = os.getenv("MONGODB_URI")
if not MONGODB_URI:
    print("❌ MONGODB_URI missing")
    exit(1)

TURNSTILE_SECRET_KEY = os.getenv("TURNSTILE_SECRET_KEY")
if not TURNSTILE_SECRET_KEY:
    print("❌ TURNSTILE_SECRET_KEY missing")
    exit(1)

GUILD_ID = int(os.getenv("GUILD_ID", 0))
if not GUILD_ID:
    print("❌ GUILD_ID missing or invalid")
    exit(1)

OWNER_ID = 1445289457866506290

mongo_client = None
db = None
settings_col = None
logs_col = None
tickets_col = None
ticket_panels_col = None
verification_config_col = None
active_checker_col = None
auto_delete_config_col = None
verified_users_col = None

try:
    mongo_client = MongoClient(MONGODB_URI, server_api=ServerApi('1'))
    mongo_client.admin.command('ping')
    db = mongo_client["rblxlua_data"]
    settings_col = db["settings"]
    logs_col = db["usage_logs"]
    tickets_col = db["tickets"]
    ticket_panels_col = db["ticket_panels"]
    verification_config_col = db["verification_config"]
    active_checker_col = db["active_checker_config"]
    auto_delete_config_col = db["auto_delete_config"]
    verified_users_col = db["verified_users"]
    print("✅ MongoDB Connected")
except Exception as e:
    print(f"❌ MongoDB Error: {e}")

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix=".", intents=intents, help_command=None)

user_cache = {}
USER_CACHE_TTL = 3600

def get_discord_user(user_id):
    now = time.time()
    if user_id in user_cache and (now - user_cache[user_id]['ts']) < USER_CACHE_TTL:
        return user_cache[user_id]['data']
    try:
        future = asyncio.run_coroutine_threadsafe(bot.fetch_user(user_id), bot.loop)
        user = future.result(timeout=5)
        data = {
            'username': user.name,
            'display_name': user.display_name,
            'avatar_url': str(user.display_avatar.url)
        }
        user_cache[user_id] = {'data': data, 'ts': now}
        return data
    except Exception as e:
        print(f"Failed to fetch user {user_id}: {e}")
        return {'username': str(user_id), 'display_name': str(user_id), 'avatar_url': ''}

async def get_allowed_channel():
    if settings_col is None:
        return None
    doc = await asyncio.to_thread(settings_col.find_one, {"key": "command_channel"})
    if doc:
        return doc.get("value")
    return None

async def set_allowed_channel(channel_id):
    if settings_col is not None:
        await asyncio.to_thread(settings_col.update_one, {"key": "command_channel"}, {"$set": {"value": channel_id}}, upsert=True)

async def clear_allowed_channel():
    if settings_col is not None:
        await asyncio.to_thread(settings_col.delete_one, {"key": "command_channel"})

@bot.event
async def on_message(message):
    if message.author.bot:
        return
    if not message.guild:
        return

    if auto_delete_config_col is not None:
        config = await asyncio.to_thread(auto_delete_config_col.find_one, {"guild_id": message.guild.id})
        if config and message.channel.id in config.get("channels", []):
            try:
                await message.delete()
            except:
                pass
            return

    if message.content.startswith("."):
        await bot.process_commands(message)

@bot.tree.command(name="active_checker", description="Set up an active checker that pings @everyone periodically")
@app_commands.describe(
    time="Interval (e.g., 1d, 1week, 1month, 1year)",
    channel="The channel where the active check message will be sent"
)
@app_commands.default_permissions(administrator=True)
async def active_checker(
    interaction: discord.Interaction,
    time: str,
    channel: discord.TextChannel
):
    try:
        interval = parse_time_interval(time)
    except ValueError as e:
        await interaction.response.send_message(str(e), ephemeral=True)
        return

    guild_id = interaction.guild.id
    existing = await asyncio.to_thread(active_checker_col.find_one, {"guild_id": guild_id})

    if existing:
        existing_channel_id = existing.get("channel_id")
        existing_interval = existing.get("interval")
        if existing_channel_id == channel.id and existing_interval == interval:
            await interaction.response.send_message(
                "❌ You already have an Active Checker set up with the same time and channel. "
                "To change it, use a different time or channel.",
                ephemeral=True
            )
            return
        else:
            if guild_id in active_checker_tasks:
                active_checker_tasks[guild_id].cancel()
                del active_checker_tasks[guild_id]

    await asyncio.to_thread(active_checker_col.update_one,
        {"guild_id": guild_id},
        {"$set": {"channel_id": channel.id, "interval": interval}},
        upsert=True
    )

    task = asyncio.create_task(active_checker_loop(guild_id, channel.id, interval))
    active_checker_tasks[guild_id] = task

    embed = discord.Embed(
        title="✅ Active Checker Set Up",
        description=f"Will ping @everyone in {channel.mention} every **{time}** with an active check message.",
        color=0x1e90ff
    )
    await interaction.response.send_message(embed=embed, ephemeral=True)

active_checker_tasks = {}

def parse_time_interval(time_str: str) -> int:
    time_str = time_str.lower().strip()
    if time_str.endswith("d"):
        return int(time_str[:-1]) * 86400
    elif time_str.endswith("week"):
        return int(time_str[:-4]) * 604800
    elif time_str.endswith("month"):
        return int(time_str[:-5]) * 2592000
    elif time_str.endswith("year"):
        return int(time_str[:-4]) * 31536000
    else:
        raise ValueError("Invalid time format. Use e.g., 1d, 1week, 1month, 1year")

async def active_checker_loop(guild_id, channel_id, interval_seconds):
    await bot.wait_until_ready()
    await asyncio.sleep(interval_seconds)
    while not bot.is_closed():
        try:
            guild = bot.get_guild(guild_id)
            if not guild:
                break
            channel = guild.get_channel(channel_id)
            if not channel:
                break

            embed = discord.Embed(
                title="🟢 Active Check",
                description="Active check. I just want y'all to check if you are Active. React so we know if y'all is Active.",
                color=0x1e90ff
            )
            embed.set_footer(text="Powered by MonLua Bot")
            msg = await channel.send(content="@everyone", embed=embed)
            await msg.add_reaction("✅")
            await asyncio.sleep(interval_seconds)
        except Exception as e:
            print(f"Active checker error: {e}")
            await asyncio.sleep(60)

class PersistentTicketPanel(discord.ui.View):
    def __init__(self, panel_id, button_label="Open Ticket", button_emoji="🎟️", button_style=discord.ButtonStyle.gray):
        super().__init__(timeout=None)
        self.panel_id = panel_id
        button = discord.ui.Button(
            label=button_label,
            style=button_style,
            emoji=button_emoji,
            custom_id=f"open_ticket:{panel_id}"
        )
        button.callback = self.open_ticket_callback
        self.add_item(button)

    async def open_ticket_callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        try:
            panel = await asyncio.to_thread(ticket_panels_col.find_one, {"_id": ObjectId(self.panel_id)})
            if not panel:
                await interaction.followup.send("❌ This ticket panel is no longer valid.", ephemeral=True)
                return

            existing = await asyncio.to_thread(tickets_col.find_one, {
                "guild_id": interaction.guild.id,
                "user_id": interaction.user.id,
                "closed": False
            })
            if existing:
                channel = interaction.guild.get_channel(existing["channel_id"])
                if channel is None:
                    await asyncio.to_thread(tickets_col.update_one,
                        {"_id": existing["_id"]},
                        {"$set": {"closed": True, "closed_at": datetime.utcnow(), "closed_by": None}}
                    )
                    existing = None
                else:
                    await interaction.followup.send("❌ You already have an open ticket. Please close it before opening a new one.", ephemeral=True)
                    return

            guild = interaction.guild
            category = discord.utils.get(guild.categories, name="Tickets")
            if not category:
                category = await guild.create_category("Tickets")

            channel = await guild.create_text_channel(
                name=f"ticket-{interaction.user.name}",
                category=category,
                topic=f"Ticket for {interaction.user} ({interaction.user.id})"
            )

            overwrites = {
                guild.default_role: discord.PermissionOverwrite(view_channel=False),
                interaction.user: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True),
                guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True, manage_channels=True),
            }
            ping_role_ids = []
            if panel.get("ping_role"):
                ping_role_ids.append(panel["ping_role"])
            for i in range(2, 5):
                rid = panel.get(f"ping_role_{i}")
                if rid:
                    ping_role_ids.append(rid)
            for rid in ping_role_ids:
                role = guild.get_role(rid)
                if role:
                    overwrites[role] = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True)

            await channel.edit(overwrites=overwrites)

            mention_text = " ".join([f"<@&{rid}>" for rid in ping_role_ids]) if ping_role_ids else None

            embed_ticket = discord.Embed(
                title="🎟️ Ticket Created",
                description=f"{interaction.user.mention} has created a New Ticket 🎟️.",
                color=panel.get("color", 0x2b2d31)
            )
            embed_ticket.set_footer(text=panel.get("footer_text", "Made by MonLua Bot"), icon_url=bot.user.display_avatar.url)

            ticket_doc = {
                "guild_id": guild.id,
                "channel_id": channel.id,
                "user_id": interaction.user.id,
                "claimed_by": None,
                "closed": False,
                "created_at": datetime.utcnow(),
                "panel_id": self.panel_id
            }
            result = await asyncio.to_thread(tickets_col.insert_one, ticket_doc)
            ticket_id = str(result.inserted_id)
            await asyncio.to_thread(tickets_col.update_one,
                {"_id": result.inserted_id},
                {"$set": {"ticket_id": ticket_id}}
            )

            ticket_view = TicketView(ticket_id, panel)
            await channel.send(content=mention_text, embed=embed_ticket, view=ticket_view)
            bot.add_view(ticket_view)

            jump_view = discord.ui.View()
            jump_button = discord.ui.Button(
                label="Go to Ticket",
                style=discord.ButtonStyle.primary,
                url=channel.jump_url
            )
            jump_view.add_item(jump_button)

            await interaction.followup.send("✅ Ticket Created", view=jump_view, ephemeral=True)

        except Exception as e:
            print(f"Ticket creation error: {e}")
            try:
                await interaction.followup.send(f"❌ An error occurred while creating your ticket: {str(e)[:200]}", ephemeral=True)
            except:
                pass

class TicketView(discord.ui.View):
    def __init__(self, ticket_id, panel, claim_disabled=None):
        super().__init__(timeout=None)
        self.ticket_id = ticket_id
        self.panel = panel

        close_button = discord.ui.Button(
            label="Close",
            style=discord.ButtonStyle.danger,
            emoji="🔒",
            custom_id=f"close_ticket:{ticket_id}"
        )
        close_button.callback = self.close_callback
        self.add_item(close_button)

        if claim_disabled is None:
            claim_disabled = not panel.get("claim_enabled", False)

        claim_button = discord.ui.Button(
            label="Claim",
            style=discord.ButtonStyle.gray,
            emoji="📜",
            custom_id=f"claim_ticket:{ticket_id}",
            disabled=claim_disabled
        )
        claim_button.callback = self.claim_callback
        self.add_item(claim_button)

    async def claim_callback(self, interaction: discord.Interaction):
        ticket_id = interaction.data["custom_id"].split(":")[1]
        ticket = await asyncio.to_thread(tickets_col.find_one, {"_id": ObjectId(ticket_id)})
        if not ticket:
            await interaction.response.send_message("❌ Ticket not found.", ephemeral=True)
            return

        panel = await asyncio.to_thread(ticket_panels_col.find_one, {"_id": ObjectId(ticket["panel_id"])})
        if not panel:
            await interaction.response.send_message("❌ Panel config not found.", ephemeral=True)
            return

        ping_role_ids = []
        if panel.get("ping_role"):
            ping_role_ids.append(panel["ping_role"])
        for i in range(2, 5):
            rid = panel.get(f"ping_role_{i}")
            if rid:
                ping_role_ids.append(rid)

        has_permission = False
        for rid in ping_role_ids:
            if discord.utils.get(interaction.user.roles, id=rid):
                has_permission = True
                break
        if not has_permission:
            await interaction.response.send_message("❌ You are not able to claim this ticket. Only admins with the configured ping roles can claim.", ephemeral=True)
            return

        if ticket.get("claimed_by"):
            await interaction.response.send_message(f"❌ This ticket is already claimed by <@{ticket['claimed_by']}>.", ephemeral=True)
            return

        await asyncio.to_thread(tickets_col.update_one,
            {"_id": ObjectId(ticket_id)},
            {"$set": {"claimed_by": interaction.user.id}}
        )

        channel = interaction.guild.get_channel(ticket["channel_id"])
        if channel:
            creator_mention = f"<@{ticket['user_id']}>"
            embed_claim = discord.Embed(
                title="🖐️ Ticket Claimed",
                description=f"{interaction.user.mention} Has been claimed your ticket.",
                color=discord.Color.green()
            )
            await channel.send(content=interaction.user.mention, embed=embed_claim)

            try:
                async for msg in channel.history(limit=10):
                    if msg.author == bot.user and msg.embeds:
                        embed_obj = msg.embeds[0]
                        if embed_obj.title == "🎟️ Ticket Created":
                            new_embed = discord.Embed.from_dict(embed_obj.to_dict())
                            new_embed.description = f"{new_embed.description}\n\n**Claimed by:** {interaction.user.mention}"
                            await msg.edit(embed=new_embed)
                            break
            except:
                pass

            new_view = TicketView(ticket_id, panel, claim_disabled=True)
            new_view.clear_items()
            close_button = discord.ui.Button(
                label="Close",
                style=discord.ButtonStyle.danger,
                emoji="🔒",
                custom_id=f"close_ticket:{ticket_id}"
            )
            close_button.callback = new_view.close_callback
            new_view.add_item(close_button)
            claim_button = discord.ui.Button(
                label="Claim",
                style=discord.ButtonStyle.gray,
                emoji="📜",
                custom_id=f"claim_ticket:{ticket_id}",
                disabled=True
            )
            claim_button.callback = new_view.claim_callback
            new_view.add_item(claim_button)
            try:
                async for msg in channel.history(limit=10):
                    if msg.author == bot.user and msg.components:
                        await msg.edit(view=new_view)
                        break
            except:
                pass

        await interaction.response.send_message("✅ Successfully Claimed the ticket", ephemeral=True)

    async def close_callback(self, interaction: discord.Interaction):
        ticket_id = interaction.data["custom_id"].split(":")[1]
        ticket = await asyncio.to_thread(tickets_col.find_one, {"_id": ObjectId(ticket_id)})
        if not ticket:
            await interaction.response.send_message("❌ Ticket not found.", ephemeral=True)
            return

        panel = await asyncio.to_thread(ticket_panels_col.find_one, {"_id": ObjectId(ticket["panel_id"])})
        if not panel:
            await interaction.response.send_message("❌ Panel config not found.", ephemeral=True)
            return

        ping_role_ids = []
        if panel.get("ping_role"):
            ping_role_ids.append(panel["ping_role"])
        for i in range(2, 5):
            rid = panel.get(f"ping_role_{i}")
            if rid:
                ping_role_ids.append(rid)

        has_permission = False
        for rid in ping_role_ids:
            if discord.utils.get(interaction.user.roles, id=rid):
                has_permission = True
                break
        if not has_permission and interaction.user.id != ticket["user_id"] and interaction.user.id != ticket.get("claimed_by"):
            await interaction.response.send_message("❌ You are not able to close this ticket. Only the ticket creator, the claimer, or admins with the configured ping roles can close.", ephemeral=True)
            return

        channel = interaction.guild.get_channel(ticket["channel_id"])
        if channel:
            await channel.delete(reason=f"Ticket closed by {interaction.user}")

        await asyncio.to_thread(tickets_col.update_one,
            {"_id": ObjectId(ticket_id)},
            {"$set": {"closed": True, "closed_at": datetime.utcnow(), "closed_by": interaction.user.id}}
        )

        try:
            creator = await bot.fetch_user(ticket["user_id"])
            if creator:
                embed_dm = discord.Embed(
                    title="Ticket Closed",
                    description=f"This ticket has been closed by {interaction.user.mention}.",
                    color=0x2b2d31
                )
                embed_dm.add_field(name="Ticket name", value=f"ticket-{creator.name}", inline=False)
                embed_dm.add_field(name="Server", value=interaction.guild.name, inline=False)
                embed_dm.set_footer(text="MonLua Bot")
                await creator.send(embed=embed_dm)
        except Exception as e:
            print(f"Failed to DM user: {e}")

        await interaction.response.send_message("✅ Ticket closed.", ephemeral=True)

@bot.tree.command(name="ticket", description="Create a ticket panel")
@app_commands.describe(
    ping_role="The role to ping when a ticket is created",
    enable_claim_button="Enable the Claim button for tickets",
    description="Panel description (default: Open the ticket below 🎟️)",
    footer="Footer text (default: Made by MonLua Bot)",
    color="Embed color (hex code or name, default: #2b2d31)",
    label_button="Button label (default: Open Ticket)",
    label_emoji="Button emoji (default: 🎟️)",
    label_color="Button color (gray, blurple, green, red, default: gray)",
    ping_role_2="Additional role to ping (optional)",
    ping_role_3="Additional role to ping (optional)",
    ping_role_4="Additional role to ping (optional)"
)
@app_commands.default_permissions(administrator=True)
async def ticket_command(
    interaction: discord.Interaction,
    ping_role: discord.Role,
    enable_claim_button: bool,
    description: str = "Open the ticket below 🎟️",
    footer: str = "Made by MonLua Bot",
    color: str = "#2b2d31",
    label_button: str = "Open Ticket",
    label_emoji: str = "🎟️",
    label_color: str = "gray",
    ping_role_2: discord.Role = None,
    ping_role_3: discord.Role = None,
    ping_role_4: discord.Role = None
):
    await interaction.response.defer(ephemeral=True)

    color_val = None
    if color.startswith("#"):
        try:
            color_val = int(color[1:], 16)
        except ValueError:
            await interaction.followup.send(
                "❌ Invalid hex color code. Please use a valid hex code (e.g., #ff0000).\nAvailable color names: `dark_magenta, light_grey, orange, gold, red, blue, dark_theme, darker_grey, blurple, yellow, greyple, magenta, dark_grey, default, dark_gold, green, dark_green, dark_orange, teal, dark_purple, purple, pink, lighter_grey, fuchsia, dark_red, dark_blue, dark_teal`",
                ephemeral=True
            )
            return
    else:
        valid_colors = [
            "dark_magenta", "light_grey", "orange", "gold", "red", "blue",
            "dark_theme", "darker_grey", "blurple", "yellow", "greyple",
            "magenta", "dark_grey", "default", "dark_gold", "green",
            "dark_green", "dark_orange", "teal", "dark_purple", "purple",
            "pink", "lighter_grey", "fuchsia", "dark_red", "dark_blue", "dark_teal"
        ]
        if color.lower() not in valid_colors:
            await interaction.followup.send(
                f"❌ Wrong color name. Please use a valid color name.\nAvailable colors: `{', '.join(valid_colors)}`",
                ephemeral=True
            )
            return
        try:
            color_val = getattr(discord.Color, color.lower()).value
        except AttributeError:
            color_val = 0x2b2d31

    color_map = {
        "gray": discord.ButtonStyle.gray,
        "blurple": discord.ButtonStyle.blurple,
        "green": discord.ButtonStyle.green,
        "red": discord.ButtonStyle.red
    }
    button_style = color_map.get(label_color.lower(), discord.ButtonStyle.gray)

    panel_data = {
        "guild_id": interaction.guild.id,
        "channel_id": interaction.channel.id,
        "ping_role": ping_role.id,
        "ping_role_2": ping_role_2.id if ping_role_2 else None,
        "ping_role_3": ping_role_3.id if ping_role_3 else None,
        "ping_role_4": ping_role_4.id if ping_role_4 else None,
        "claim_enabled": enable_claim_button,
        "description": description,
        "footer_text": footer,
        "color": color_val,
        "label_button": label_button,
        "label_emoji": label_emoji,
        "label_color": label_color,
        "created_at": datetime.utcnow()
    }
    result = await asyncio.to_thread(ticket_panels_col.insert_one, panel_data)
    panel_id = str(result.inserted_id)

    embed = discord.Embed(
        title="🎫 Ticket System",
        description=description,
        color=color_val
    )
    embed.set_footer(text=footer, icon_url=bot.user.display_avatar.url)

    view = PersistentTicketPanel(panel_id, label_button, label_emoji, button_style)
    await interaction.followup.send("✅ Successfully created a ticket panel", ephemeral=True)
    await interaction.channel.send(embed=embed, view=view)
    bot.add_view(view)

async def apply_not_verified_to_all(guild_id, not_verified_role_id):
    guild = bot.get_guild(guild_id)
    if not guild:
        return
    role = guild.get_role(not_verified_role_id)
    if not role:
        return
    config = await asyncio.to_thread(verification_config_col.find_one, {"guild_id": guild_id})
    if not config:
        return
    verified_role_id = config.get("verified_role_id")
    verified_role = guild.get_role(verified_role_id)
    count = 0
    async for member in guild.fetch_members(limit=None):
        if member.bot:
            continue
        if verified_role and verified_role in member.roles:
            continue
        if role in member.roles:
            continue
        try:
            await member.add_roles(role, reason="Verification deadline expired")
            count += 1
            if count % 10 == 0:
                await asyncio.sleep(0.5)
        except discord.Forbidden:
            continue
        except Exception as e:
            print(f"Error assigning role to {member}: {e}")
    print(f"Assigned Not Verified role to {count} members in guild {guild_id}")

async def check_verification_deadlines():
    await bot.wait_until_ready()
    while not bot.is_closed():
        try:
            now = int(time.time())
            configs = await asyncio.to_thread(
                lambda: list(verification_config_col.find({"deadline": {"$lte": now}}))
            )
            for config in configs:
                guild_id = config["guild_id"]
                not_verified_role_id = config["not_verified_role_id"]
                if config.get("deadline_processed", False):
                    continue
                await apply_not_verified_to_all(guild_id, not_verified_role_id)
                await asyncio.to_thread(
                    verification_config_col.update_one,
                    {"guild_id": guild_id},
                    {"$set": {"deadline_processed": True}}
                )
        except Exception as e:
            print(f"Verification deadline check error: {e}")
        await asyncio.sleep(60)

def parse_duration(duration_str: str) -> int:
    duration_str = duration_str.lower().strip()
    if duration_str.endswith("d"):
        return int(duration_str[:-1]) * 86400
    elif duration_str.endswith("h"):
        return int(duration_str[:-1]) * 3600
    elif duration_str.endswith("m"):
        return int(duration_str[:-1]) * 60
    elif duration_str.endswith("s"):
        return int(duration_str[:-1])
    else:
        raise ValueError("Invalid duration format. Use e.g., 1d, 12h, 30m, 45s")

def get_verification_view():
    view = discord.ui.View()
    view.add_item(discord.ui.Button(
        label="Verify on Website",
        style=discord.ButtonStyle.link,
        url="https://rblxlua-verification.pages.dev"
    ))
    return view

@bot.tree.command(name="verification_system", description="Set up the verification system with an automatic deadline")
@app_commands.describe(
    select_role="The role to give upon verification",
    channel="The channel where the verification message will be sent"
)
@app_commands.default_permissions(administrator=True)
async def verification_system(
    interaction: discord.Interaction,
    select_role: discord.Role,
    channel: discord.TextChannel
):
    await interaction.response.defer(ephemeral=True)
    guild = interaction.guild

    if not interaction.guild.me.guild_permissions.manage_roles:
        await interaction.followup.send("❌ I need the 'Manage Roles' permission to set up verification.", ephemeral=True)
        return
    if not interaction.guild.me.guild_permissions.manage_channels:
        await interaction.followup.send("❌ I need the 'Manage Channels' permission to set up verification.", ephemeral=True)
        return

    bot_top_role = interaction.guild.me.top_role
    if bot_top_role <= select_role:
        await interaction.followup.send(
            "❌ My highest role is not above the selected verification role. "
            "Please move my role higher in the role hierarchy, or choose a lower role.",
            ephemeral=True
        )
        return

    not_verified_role = discord.utils.get(guild.roles, name="Not Verified")
    if not not_verified_role:
        try:
            not_verified_role = await guild.create_role(
                name="Not Verified",
                reason="Verification system role",
                hoist=False,
                mentionable=False
            )
        except discord.Forbidden:
            await interaction.followup.send("❌ I don't have permission to create roles.", ephemeral=True)
            return

    async def update_channel_perms(channel_obj):
        if channel_obj == channel:
            overwrites = {
                guild.default_role: discord.PermissionOverwrite(view_channel=False),
                not_verified_role: discord.PermissionOverwrite(
                    view_channel=True,
                    send_messages=False,
                    create_public_threads=False,
                    create_private_threads=False
                ),
                select_role: discord.PermissionOverwrite(view_channel=False)
            }
        else:
            overwrites = {
                not_verified_role: discord.PermissionOverwrite(view_channel=False),
                select_role: discord.PermissionOverwrite(view_channel=True)
            }
        try:
            await channel_obj.edit(overwrites=overwrites)
        except:
            pass

    channels_to_update = [c for c in guild.channels if isinstance(c, (discord.TextChannel, discord.CategoryChannel))]
    sem = asyncio.Semaphore(10)

    async def apply_permissions(ch):
        async with sem:
            await update_channel_perms(ch)

    tasks = [apply_permissions(ch) for ch in channels_to_update]
    await asyncio.gather(*tasks)

    members_assigned = 0
    async for member in guild.fetch_members(limit=None):
        if member.bot:
            continue
        if not_verified_role not in member.roles:
            try:
                await member.add_roles(not_verified_role, reason="Verification system initialization")
                members_assigned += 1
                if members_assigned % 10 == 0:
                    await asyncio.sleep(0.5)
            except:
                continue

    DEFAULT_VERIFICATION_DURATION = 86400
    deadline = int(time.time()) + DEFAULT_VERIFICATION_DURATION

    embed = discord.Embed(
        title="🔐 Server Verification",
        description=(
            "Welcome to the server! We are glad to Have you here.\n\n"
            "To gain access to all the channels and features, please verify yourself by clicking the **Verify on Website** button below.\n"
            "You will be redirected to our verification page where you must complete a short challenge.\n"
            "This helps us keep the server safe and secure."
        ),
        color=0x1e90ff
    )
    embed.set_footer(text="Verification System")
    embed.add_field(
        name="⏳ Verification Deadline",
        value=f"All members must verify before <t:{deadline}:R>.\nAfter that, unverified members will receive the **Not Verified** role.",
        inline=False
    )

    view = get_verification_view()
    msg = await channel.send(embed=embed, view=view)

    config_data = {
        "guild_id": guild.id,
        "not_verified_role_id": not_verified_role.id,
        "verified_role_id": select_role.id,
        "channel_id": channel.id,
        "message_id": msg.id,
        "deadline": deadline,
        "deadline_processed": False
    }
    await asyncio.to_thread(verification_config_col.update_one,
        {"guild_id": guild.id},
        {"$set": config_data},
        upsert=True
    )

    response = (
        f"✅ Verification system set up!\n"
        f"Not Verified role: {not_verified_role.mention}\n"
        f"Verified role: {select_role.mention}\n"
        f"Verification channel: {channel.mention}\n"
        f"Assigned Not Verified role to {members_assigned} members.\n"
        f"⏳ Deadline set: <t:{deadline}:R> (auto 24 hours)"
    )
    await interaction.followup.send(response, ephemeral=True)

@bot.check
async def global_channel_check(ctx):
    if ctx.author.id == OWNER_ID:
        return True
    if ctx.guild is None:
        await ctx.send("⚠️ You are not allowed to use commands in DMs.")
        return False
    allowed = await get_allowed_channel()
    if allowed is None:
        return True
    if ctx.channel.id == allowed:
        return True
    await ctx.send(f"⚠️ Commands are restricted to <#{allowed}>. Please use them there.")
    return False

@bot.tree.command(name="channel_set", description="Set the channel where commands are allowed")
@app_commands.describe(channel="The channel to allow commands in")
@app_commands.default_permissions(administrator=True)
async def channel_set(interaction: discord.Interaction, channel: discord.TextChannel):
    await set_allowed_channel(channel.id)
    await interaction.response.send_message(f"✅ Commands are now restricted to {channel.mention}.", ephemeral=True)

@bot.tree.command(name="channel_view", description="View the currently allowed channel")
async def channel_view(interaction: discord.Interaction):
    allowed = await get_allowed_channel()
    if allowed is None:
        await interaction.response.send_message("ℹ️ No channel restriction is set. Commands are allowed everywhere.", ephemeral=True)
    else:
        channel = bot.get_channel(allowed)
        if channel:
            await interaction.response.send_message(f"ℹ️ Commands are restricted to {channel.mention}.", ephemeral=True)
        else:
            await interaction.response.send_message(f"ℹ️ Commands are restricted to a channel I cannot find (ID: {allowed}).", ephemeral=True)

@bot.tree.command(name="channel_clear", description="Remove the channel restriction")
@app_commands.default_permissions(administrator=True)
async def channel_clear(interaction: discord.Interaction):
    await clear_allowed_channel()
    await interaction.response.send_message("✅ Channel restriction removed. Commands are now allowed everywhere.", ephemeral=True)

@bot.tree.command(name="ping", description="Check bot latency")
async def slash_ping(interaction: discord.Interaction):
    start = time.perf_counter()
    api_latency = round(bot.latency * 1000)
    embed = discord.Embed(
        title="🏓 Pong!",
        color=0x2c3e99,
        description=f"**API Latency:** `{api_latency} ms`"
    )
    end = time.perf_counter()
    response_time = round((end - start) * 1000)
    embed.add_field(name="Response Time", value=f"`{response_time} ms`", inline=False)
    embed.set_footer(text=f"Requested by {interaction.user}")
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.command(name="ping")
async def prefix_ping(ctx):
    start = time.perf_counter()
    api_latency = round(bot.latency * 1000)
    embed = discord.Embed(
        title="🏓 Pong!",
        color=0x2c3e99,
        description=f"**API Latency:** `{api_latency} ms`"
    )
    end = time.perf_counter()
    response_time = round((end - start) * 1000)
    embed.add_field(name="Response Time", value=f"`{response_time} ms`", inline=False)
    await ctx.reply(embed=embed, mention_author=True)

async def delete_cmds_only(ctx):
    if ctx.invoked_with in ["cmds"]:
        try: await ctx.message.delete()
        except: pass

class CmdsPaginationView(discord.ui.View):
    def __init__(self, pages, author_id):
        super().__init__(timeout=120)
        self.pages = pages
        self.current_page = 0
        self.author_id = author_id
        self.total_pages = len(pages)

    def get_embed(self):
        page_data = self.pages[self.current_page]
        embed = discord.Embed(
            title=page_data["title"],
            description=page_data["description"],
            color=0x9b59b6
        )
        for field in page_data.get("fields", []):
            embed.add_field(name=field["name"], value=field["value"], inline=field.get("inline", False))
        embed.set_footer(text=f"Page {self.current_page + 1}/{self.total_pages} • Owner can use commands anywhere. Channel restriction applies to others.")
        return embed

    @discord.ui.button(label="◀ Back", style=discord.ButtonStyle.secondary, custom_id="cmds_back")
    async def back_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("You are not the one who ran this command.", ephemeral=True)
            return
        if self.current_page == 0:
            await interaction.response.send_message("You are already on the first page.", ephemeral=True)
            return
        self.current_page -= 1
        await interaction.response.edit_message(embed=self.get_embed(), view=self)

    @discord.ui.button(label="Next ▶", style=discord.ButtonStyle.primary, custom_id="cmds_next")
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("You are not the one who ran this command.", ephemeral=True)
            return
        if self.current_page == self.total_pages - 1:
            await interaction.response.send_message("You are already on the last page.", ephemeral=True)
            return
        self.current_page += 1
        await interaction.response.edit_message(embed=self.get_embed(), view=self)

    async def on_timeout(self):
        for child in self.children:
            child.disabled = True
        try:
            await self.message.edit(view=self)
        except:
            pass

@bot.command(name="cmds")
async def show_commands(ctx):
    await delete_cmds_only(ctx)
    pages = [
        {
            "title": "RblXLua Bot Commands (1/2)",
            "description": f"Hello {ctx.author.mention}",
            "fields": [
                {"name": "`Obfuscator [.obf]`", "value": "Obfuscate Lua code with Prometheus (single base64 chunk). Supports link, file, or pasted code.", "inline": False},
                {"name": "`Deobfuscator [.get]`", "value": "Fetch and deobfuscate code from a URL, attachment, or reply. Multi‑layer auto‑detection.", "inline": False},
                {"name": "`Ping [.ping]`", "value": "Check the bot's latency (prefix version).", "inline": False},
                {"name": "`Database [.db]`", "value": "`status` – check MongoDB connection; `clear` (owner only) – wipe all data.", "inline": False},
            ]
        },
        {
            "title": "RblXLua Bot Commands (2/2)",
            "description": f"Hello {ctx.author.mention}",
            "fields": [
                {"name": "`Slash Commands`", "value": "`/ping` – Check bot latency\n`/channel_set` – Restrict commands to a channel\n`/channel_view` – Show current restriction\n`/channel_clear` – Remove restriction\n`/ticket` – Create ticket panel (admin)\n`/verification_system` – Set up verification with automatic 24h deadline (admin)\n`/active_checker` – Periodic @everyone ping (admin)\n`/bypass` – Bypass Delta/Platoboost/Lootlabs/Lootlink URLs\n`/auto_delete_messages` – Add auto‑delete channel (admin)\n`/atd_view_channel` – View auto‑delete channels\n`/atd_remove_channel` – Remove auto‑delete channel (admin)", "inline": False},
            ]
        }
    ]

    view = CmdsPaginationView(pages, ctx.author.id)
    embed = view.get_embed()
    try:
        await ctx.send(embed=embed, view=view, mention_author=True)
    except discord.HTTPException as e:
        print(f"Failed to send .cmds embed: {e}")
        await ctx.send("An error occurred while displaying the help menu.", mention_author=True)

@bot.tree.command(name="auto_delete_messages", description="Add a channel where messages will be automatically deleted")
@app_commands.describe(channel="The text channel to enable auto-deletion for")
@app_commands.default_permissions(administrator=True)
async def auto_delete_messages(interaction: discord.Interaction, channel: discord.TextChannel):
    guild_id = interaction.guild.id
    config = await asyncio.to_thread(auto_delete_config_col.find_one, {"guild_id": guild_id})
    channels = config.get("channels", []) if config else []

    if channel.id in channels:
        await interaction.response.send_message(f"❌ {channel.mention} is already in the auto-delete list.", ephemeral=True)
        return

    channels.append(channel.id)
    await asyncio.to_thread(auto_delete_config_col.update_one,
        {"guild_id": guild_id},
        {"$set": {"channels": channels}},
        upsert=True
    )
    await interaction.response.send_message(f"✅ {channel.mention} has been added to auto-delete. All new messages there will be instantly deleted.", ephemeral=True)

@bot.tree.command(name="atd_view_channel", description="View all channels where auto-deletion is active")
async def atd_view_channel(interaction: discord.Interaction):
    config = await asyncio.to_thread(auto_delete_config_col.find_one, {"guild_id": interaction.guild.id})
    if not config or not config.get("channels"):
        await interaction.response.send_message("ℹ️ No channels are currently set for auto-deletion.", ephemeral=True)
        return

    channel_ids = config["channels"]
    channel_mentions = []
    for cid in channel_ids:
        ch = interaction.guild.get_channel(cid)
        if ch:
            channel_mentions.append(ch.mention)
        else:
            channel_mentions.append(f"#deleted-channel ({cid})")
    embed = discord.Embed(
        title="📋 Auto‑Delete Channels",
        description="\n".join(channel_mentions) or "None",
        color=0x1e90ff
    )
    embed.set_footer(text=f"Total: {len(channel_mentions)} channels")
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="atd_remove_channel", description="Remove a channel from the auto-delete list")
@app_commands.describe(channel="The channel to remove from auto-deletion")
@app_commands.default_permissions(administrator=True)
async def atd_remove_channel(interaction: discord.Interaction, channel: discord.TextChannel):
    guild_id = interaction.guild.id
    config = await asyncio.to_thread(auto_delete_config_col.find_one, {"guild_id": guild_id})
    if not config or not config.get("channels"):
        await interaction.response.send_message("❌ No channels are currently set for auto-deletion.", ephemeral=True)
        return

    channels = config["channels"]
    if channel.id not in channels:
        await interaction.response.send_message(f"❌ {channel.mention} is not in the auto-delete list.", ephemeral=True)
        return

    channels.remove(channel.id)
    if channels:
        await asyncio.to_thread(auto_delete_config_col.update_one,
            {"guild_id": guild_id},
            {"$set": {"channels": channels}}
        )
    else:
        await asyncio.to_thread(auto_delete_config_col.delete_one, {"guild_id": guild_id})
    await interaction.response.send_message(f"✅ {channel.mention} has been removed from auto-delete.", ephemeral=True)

# ---------- Bypass Command ----------
class BypassView(discord.ui.View):
    def __init__(self, url):
        super().__init__(timeout=60)
        self.url = url

    @discord.ui.button(label="Continue", style=discord.ButtonStyle.danger, emoji="⚠️")
    async def continue_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        # Disable the button
        button.disabled = True
        await interaction.edit_original_response(view=self)

        # Run the Node.js bypass script
        try:
            process = await asyncio.create_subprocess_exec(
                'node', 'Bypass-Delta-main/bypass.js', self.url,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await process.communicate()

            if process.returncode == 0:
                result = stdout.decode('utf-8').strip()
                embed = discord.Embed(title="✅ Bypass Successful", color=discord.Color.purple())
                embed.add_field(name="Original URL", value=f"```{self.url}```", inline=False)
                embed.add_field(name="Result", value=f"```{result}```", inline=False)
                await interaction.edit_original_response(embed=embed, view=None)
            else:
                error_msg = stderr.decode('utf-8').strip()
                embed = discord.Embed(title="⚠️ Bypass Error", color=discord.Color.red())
                embed.description = f"```{error_msg[:2000]}```"
                await interaction.edit_original_response(embed=embed, view=None)

        except Exception as e:
            embed = discord.Embed(title="⚠️ System Error", color=discord.Color.red())
            embed.description = f"```{str(e)[:2000]}```"
            await interaction.edit_original_response(embed=embed, view=None)

@bot.tree.command(name="bypass", description="Bypass Delta, Platoboost, Lootlabs, or Lootlink URLs.")
@app_commands.describe(url="The REQUIRED link you want to bypass")
async def slash_bypass(interaction: discord.Interaction, url: str):
    # Send warning embed with continue button
    embed = discord.Embed(
        title="⚠️ Warning",
        description="You are putting your account at risk because Delta has a policy that there is a chance that your Delta or Account will be banned or timed out.",
        color=discord.Color.purple()
    )
    view = BypassView(url)
    await interaction.response.send_message(embed=embed, view=view, ephemeral=False)

@app.route('/api/verify', methods=['POST'])
def api_verify():
    data = request.get_json()
    if not data:
        return jsonify({'success': False, 'message': 'Missing JSON body'}), 400

    user_id = data.get('user_id')
    cf_token = data.get('cf_token')
    gender = data.get('gender', '')

    if not user_id:
        return jsonify({'success': False, 'message': 'Missing user_id'}), 400
    if not cf_token:
        return jsonify({'success': False, 'message': 'Missing cf_token'}), 400

    async def validate_turnstile():
        async with aiohttp.ClientSession() as session:
            payload = {
                'secret': TURNSTILE_SECRET_KEY,
                'response': cf_token
            }
            async with session.post('https://challenges.cloudflare.com/turnstile/v0/siteverify', data=payload) as resp:
                result = await resp.json()
                return result.get('success', False)

    success = asyncio.run(validate_turnstile())
    if not success:
        return jsonify({'success': False, 'message': 'Turnstile challenge failed'}), 400

    guild = bot.get_guild(GUILD_ID)
    if not guild:
        return jsonify({'success': False, 'message': 'Guild not found'}), 500

    config = asyncio.run(asyncio.to_thread(verification_config_col.find_one, {'guild_id': GUILD_ID}))
    if not config:
        return jsonify({'success': False, 'message': 'Verification system not set up for this guild'}), 400

    not_verified_role_id = config['not_verified_role_id']
    verified_role_id = config['verified_role_id']

    not_verified_role = guild.get_role(not_verified_role_id)
    verified_role = guild.get_role(verified_role_id)

    if not not_verified_role or not verified_role:
        return jsonify({'success': False, 'message': 'Roles are missing'}), 500

    member = guild.get_member(int(user_id))
    if not member:
        return jsonify({'success': False, 'message': 'User not found in the server'}), 404

    if verified_role in member.roles:
        return jsonify({'success': False, 'message': 'User is already verified'}), 400

    try:
        asyncio.run_coroutine_threadsafe(member.add_roles(verified_role, reason='Verified via website'), bot.loop)
        if not_verified_role in member.roles:
            asyncio.run_coroutine_threadsafe(member.remove_roles(not_verified_role, reason='Verified via website'), bot.loop)
    except Exception as e:
        return jsonify({'success': False, 'message': f'Failed to assign role: {str(e)}'}), 500

    try:
        asyncio.run(asyncio.to_thread(
            verified_users_col.update_one,
            {'guild_id': GUILD_ID, 'user_id': int(user_id)},
            {'$set': {'verified_at': datetime.utcnow(), 'verified_by': 'website', 'gender': gender}},
            upsert=True
        ))
    except Exception as e:
        print(f"Failed to record verification: {e}")

    return jsonify({'success': True, 'message': 'You are verified!'})

@app.route('/api/verified_users', methods=['GET'])
def get_verified_users():
    try:
        docs = asyncio.run(asyncio.to_thread(
            lambda: list(verified_users_col.find({'guild_id': GUILD_ID}))
        ))
        result = []
        for doc in docs:
            user_id = doc['user_id']
            user_data = get_discord_user(user_id)
            result.append({
                'user_id': user_id,
                'username': user_data['username'],
                'display_name': user_data['display_name'],
                'avatar_url': user_data['avatar_url'],
                'verified_at': doc['verified_at'].isoformat() if doc['verified_at'] else None,
                'gender': doc.get('gender', '')
            })
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

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
        try:
            data = await att.read()
            content = data.decode('utf-8', errors='replace')
            return decode_all_escapes(content)
        except:
            pass
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

def obfuscate_prometheus_python(code: str) -> tuple[bool, str]:
    try:
        b64 = base64.b64encode(code.encode('utf-8')).decode('ascii')
        obfuscated = f'''return(function(...)local L="{b64}" local function b64dec(data)
    local b = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/'
    data = data:gsub('[^'..b..'=]', '')
    return (data:gsub('.', function(x)
        if x == '=' then return '' end
        local r,f='',(b:find(x)-1)
        for i=6,1,-1 do r=r..(f%2^i>=2^(i-1) and '1' or '0') end
        return r
    end):gsub('%d%d%d?%d?%d?%d?%d?%d?', function(x)
        if #x ~= 8 then return '' end
        local c=0
        for i=1,8 do c=c+(x:sub(i,i)=='1' and 2^(8-i) or 0) end
        return string.char(c)
    end))
end
local raw = b64dec(L)
local fn = loadstring and loadstring(raw) or load(raw)
if fn then fn() else error("Failed to load obfuscated code") end
end)(...)'''
        return True, obfuscated
    except Exception as e:
        return False, str(e)

PROMETHEUS_DEOBF_LUA = r"""
local function DeobfuscatePrometheus(source)
    local load = loadstring or load
    local encoded = source:match("return%(function%(%.-%)local L={(.-)}")
    if not encoded then return nil, "Not valid Prometheus format" end
    local parts = {}
    for s in encoded:gmatch('"(.-)"') do table.insert(parts, s) end
    local function b64dec(data)
        local b = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/'
        data = data:gsub('[^'..b..'=]', '')
        return (data:gsub('.', function(x)
            if x == '=' then return '' end
            local r,f='',(b:find(x)-1)
            for i=6,1,-1 do r=r..(f%2^i>=2^(i-1) and '1' or '0') end
            return r
        end):gsub('%d%d%d?%d?%d?%d?%d?%d?', function(x)
            if #x ~= 8 then return '' end
            local c=0
            for i=1,8 do c=c+(x:sub(i,i)=='1' and 2^(8-i) or 0) end
            return string.char(c)
        end))
    end
    local output = {}
    for _,chunk in ipairs(parts) do
        local ok, res = pcall(b64dec, chunk)
        if ok and res then table.insert(output, res) end
    end
    local raw = table.concat(output)
    local clean = raw:gsub('%z', ''):gsub('%c+', '\n')
    return clean
end

local file = io.open(arg[1], "r")
if not file then print("ERROR: Cannot read input file") os.exit(1) end
local source = file:read("*a")
file:close()

local result, err = DeobfuscatePrometheus(source)
if not result then
    print("ERROR: " .. err)
    os.exit(1)
end

local out = io.open(arg[2], "w")
if not out then print("ERROR: Cannot write output") os.exit(1) end
out:write(result)
out:close()
print("SUCCESS")
"""

async def deobfuscate_prometheus_lua(code: str) -> tuple[bool, str]:
    with tempfile.TemporaryDirectory() as tmpdir:
        script_path = os.path.join(tmpdir, "deobf.lua")
        input_path = os.path.join(tmpdir, "input.lua")
        output_path = os.path.join(tmpdir, "output.lua")

        with open(script_path, "w", encoding="utf-8") as f:
            f.write(PROMETHEUS_DEOBF_LUA)
        with open(input_path, "w", encoding="utf-8") as f:
            f.write(code)

        try:
            proc = await asyncio.create_subprocess_exec(
                "lua", script_path, input_path, output_path,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=15)
            out = stdout.decode().strip()
            if "ERROR:" in out:
                err_msg = out.split("ERROR:", 1)[1].strip()
                return False, err_msg
            if os.path.exists(output_path):
                with open(output_path, "r", encoding="utf-8") as f:
                    result = f.read()
                return True, result
            return False, "Output file not created"
        except asyncio.TimeoutError:
            return False, "Deobfuscation timed out"
        except FileNotFoundError:
            return False, "Lua interpreter not found"
        except Exception as e:
            return False, str(e)

def deobfuscate_wearedevs(code: str) -> tuple[bool, str]:
    try:
        patterns = [
            r'loadstring\s*\(\s*["\']([A-Za-z0-9+/=]{20,})["\']\s*\)\s*\(?\s*\)?',
            r'loadstring\s*\(\s*["\']([^"\']+)["\']\s*\)',
            r'local\s+_G\s*=\s*["\']([^"\']+)["\']',
        ]
        for pat in patterns:
            m = re.search(pat, code)
            if m:
                encoded = m.group(1)
                try:
                    decoded = base64.b64decode(encoded).decode('utf-8', errors='replace')
                    if len(decoded) > 10:
                        return True, decoded
                except:
                    pass
        return False, "No WeAreDevs pattern found"
    except Exception as e:
        return False, str(e)

def deobfuscate_code(source_text):
    max_depth = 8
    report = {"detected": [], "steps": [], "anti": [], "snippets": []}

    def scan_signatures(txt):
        sigs = [
            ("Prometheus", r'return\(function\(%.-%\)local L={'),
            ("Lunr", r'return\(function\(L,M,I\)'),
            ("Luraph", r'--.*Luraph|luraph\.net'),
            ("Fualmor", r'fualmor|canary|_tripwire|4294967296'),
            ("WeAreDevs", r'wearedevs\.net|WAD_OBF|loadstring%s*%(%s*["\']%s*[A-Za-z0-9+/=]+%s*["\']'),
            ("Anti-Env/Log", r'envlog|galactic|writefile.*\.lua|discord.*webhook')
        ]
        lines = txt.split('\n')
        for name, pat in sigs:
            try:
                if re.search(pat, txt, re.I):
                    if name not in report["detected"]:
                        report["detected"].append(name)
                    if "Anti" in name:
                        report["anti"].append(name)
                    for i, line in enumerate(lines):
                        if re.search(pat, line, re.I):
                            start = max(0, i-1)
                            end = min(len(lines), i+2)
                            snippet = '\n'.join(lines[start:end])
                            if snippet not in report["snippets"]:
                                report["snippets"].append(snippet)
                            if len(report["snippets"]) >= 10:
                                break
            except re.error:
                pass

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
            except:
                pass
        return False, ""

    def decode_strchar(txt):
        m = re.search(r'string\.char\(([\d,\s]+)\)', txt, re.DOTALL)
        if not m: return False, ""
        try:
            nums = [int(n) for n in re.findall(r'\d+', m.group(1)) if n.isdigit()]
            out = ''.join(chr(n) for n in nums)
            if len(out) > 30 and out != txt:
                return True, out
        except:
            pass
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
            except:
                pass
        mx = re.search(r'["\']([^"\']{5,30})["\'].*?["\']([A-Za-z0-9+/=]{30,})["\']', txt, re.DOTALL)
        if mx:
            try:
                k, d = mx.group(1), base64.b64decode(mx.group(2)).decode('latin1', 'replace')
                out = ''.join(chr(ord(c) ^ ord(k[i % len(k)])) for i, c in enumerate(d))
                if len(out) > 30 and out != txt:
                    return True, out
            except:
                pass
        return False, ""

    def extract_loadstring(txt):
        m = re.search(r'loadstring\s*\(\s*["\']([^"\']+)["\']\s*\)', txt)
        if m:
            return True, decode_all_escapes(m.group(1))
        return False, ""

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
        ok, res = extract_loadstring(buf)
        if ok:
            buf = res
            changed = True
            report["steps"].append(f"Layer {depth}: loadstring extracted")
        buf = re.sub(r'if\s*\w+\s*[=<>]+\s*\w+\s*then\s*return\s*[01]+\s*end', '', buf)
        buf = re.sub(r'\b\w{18,}\s*[=<>]+\s*[01]', '', buf)
        buf = re.sub(r'--\[\[.*?\]\]', '', buf, re.DOTALL)
        buf = re.sub(r'--.*$', '', buf, re.MULTILINE)

    buf = re.sub(r'\n\s*\n+', '\n', buf)
    return {
        "result": buf.strip(),
        "layers_done": depth,
        "detected": report["detected"],
        "anti_found": report["anti"],
        "steps": report["steps"],
        "snippets": report["snippets"][:10],
        "status": "Fully unpacked" if depth >= 3 else "Partially unpacked" if depth > 0 else "No unpack needed"
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
        snippets = deobf.get("snippets", [])
        if snippets:
            desc += "\n**Protection Snippets:**\n```lua\n"
            snippet_text = ""
            for i, snippet in enumerate(snippets[:3]):
                snippet_text += f"-- Snippet {i+1}:\n{snippet}\n\n"
            if len(snippet_text) > 500:
                snippet_text = snippet_text[:500] + "\n... [truncated]"
            desc += snippet_text + "```"
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
    if deobf:
        if deobf['layers_reached'] > 0 and deobf['status'] != "No unpack needed":
            preview_len = int(len(content) * 0.3)
            preview_len = min(preview_len, 500)
            if preview_len < 50:
                preview_len = min(150, len(content))
            preview = content[:preview_len]
            if len(content) > preview_len:
                preview += "... [truncated]"
            desc += f"\n\n**Deobfuscated Code Preview (30%):**\n```lua\n{preview}\n```"
    elif raw:
        preview = content[:500] + ("..." if len(content) > 500 else "")
        desc += f"\n\n**Raw Code Preview:**\n```lua\n{preview}\n```"

    if size_kb > 10 or len(content) > 1800:
        file = File(io.BytesIO(size_b), filename="processed.lua")
        if len(desc) > 5000:
            desc = desc[:5000] + "... [truncated description]"
        if not desc.endswith("Full code sent as file"):
            desc += f"\n📦 Size: `{round(size_kb,2)} KB` → Full code sent as file"
        emb = discord.Embed(title=title, color=0x3498db, description=desc)
    else:
        emb = discord.Embed(title=title, color=0x2ecc71 if "Fully unpacked" in desc else 0xf39c12, description=desc)
    emb.set_footer(text=f"Requested by {ctx.author}")
    return emb, file

@bot.command(name="get")
async def get_command(ctx, *, link=None):
    await delete_cmds_only(ctx)
    if not link and ctx.message.reference:
        try:
            ref = await ctx.channel.fetch_message(ctx.message.reference.message_id)
            m = re.search(r'https?://[^\s<>]+', ref.content)
            if m: link = m.group(0)
        except: pass
    if not link:
        content = await extract_code(ctx)
        if content:
            pass
        else:
            emb = discord.Embed(title="⚠️ Missing Link/Code", color=0xf39c12, description=f"{ctx.author.mention}\nProvide a link, attach a file, or paste code.\nExample: `.get https://example.com/script.lua`")
            return await ctx.reply(embed=emb, mention_author=True)

    if link:
        proc = await ctx.reply(f"📥 Fetching & deobfuscating {ctx.author.mention}...", mention_author=True)
        try:
            ok, cont, msg = await fetch_content(link)
            if not ok:
                await proc.delete()
                return await ctx.reply(embed=discord.Embed(title="❌ Fetch Failed", color=0xe74c3c, description=f"{ctx.author.mention}\n{msg}"), mention_author=True)
            content = cont
        except Exception as e:
            await proc.delete()
            return await ctx.reply(embed=discord.Embed(title="❌ Error", color=0xe74c3c, description=f"{ctx.author.mention}\n{str(e)[:500]}"), mention_author=True)
    else:
        if not content:
            emb = discord.Embed(title="⚠️ Missing Content", color=0xf39c12, description=f"{ctx.author.mention}\nProvide a link, attach a file, or paste code.")
            return await ctx.reply(embed=emb, mention_author=True)
        proc = await ctx.reply(f"🔓 Deobfuscating {ctx.author.mention}...", mention_author=True)

    try:
        success, result = await deobfuscate_prometheus_lua(content)
        if success:
            report = {
                "obfuscator": {"name": "Prometheus", "confidence": 100},
                "steps": ["• Deobfuscated using Prometheus Lua function"],
                "layers_reached": 1,
                "max_layers": 1,
                "anti_found": [],
                "status": "Fully unpacked",
                "result": result,
                "snippets": []
            }
            emb, file = make_result_embed(ctx, "🔓 Deobfuscation Result", deobf=report)
            await proc.delete()
            if file:
                await ctx.reply(embed=emb, file=file, mention_author=True)
            else:
                await ctx.reply(embed=emb, mention_author=True)
            if logs_col is not None:
                await asyncio.to_thread(logs_col.insert_one, {"uid": ctx.author.id, "act": "get", "url": extract_url(link if link else ""), "at": discord.utils.utcnow()})
            return

        success, result = deobfuscate_wearedevs(content)
        if success:
            report = {
                "obfuscator": {"name": "WeAreDevs", "confidence": 100},
                "steps": ["• Deobfuscated using WeAreDevs pattern"],
                "layers_reached": 1,
                "max_layers": 1,
                "anti_found": [],
                "status": "Fully unpacked",
                "result": result,
                "snippets": []
            }
            emb, file = make_result_embed(ctx, "🔓 Deobfuscation Result", deobf=report)
            await proc.delete()
            if file:
                await ctx.reply(embed=emb, file=file, mention_author=True)
            else:
                await ctx.reply(embed=emb, mention_author=True)
            if logs_col is not None:
                await asyncio.to_thread(logs_col.insert_one, {"uid": ctx.author.id, "act": "get", "url": extract_url(link if link else ""), "at": discord.utils.utcnow()})
            return

        timeout = 180 if len(content) > 500000 else 60
        dec = await asyncio.wait_for(
            asyncio.to_thread(deobfuscate_code, content),
            timeout=timeout
        )

        obfuscator_name = ", ".join(dec["detected"]) if dec["detected"] else "Standard Lua / No Obfuscation"
        confidence = 100 if dec["detected"] else 100
        max_layers = 8
        report = {
            "obfuscator": {"name": obfuscator_name, "confidence": confidence},
            "steps": [f"• {s}" for s in dec["steps"]],
            "layers_reached": dec["layers_done"],
            "max_layers": max_layers,
            "anti_found": [f"• {a}" for a in dec["anti_found"]],
            "status": dec["status"],
            "result": dec["result"],
            "snippets": dec["snippets"]
        }
        emb, file = make_result_embed(ctx, "🔓 Deobfuscation Result", deobf=report)
        await proc.delete()
        if file:
            await ctx.reply(embed=emb, file=file, mention_author=True)
        else:
            await ctx.reply(embed=emb, mention_author=True)
        if logs_col is not None:
            await asyncio.to_thread(logs_col.insert_one, {"uid": ctx.author.id, "act": "get", "url": extract_url(link if link else ""), "at": discord.utils.utcnow()})
    except asyncio.TimeoutError:
        await proc.delete()
        await ctx.reply(embed=discord.Embed(title="⏱️ Timeout", color=0xe74c3c, description=f"{ctx.author.mention}\nDeobfuscation took too long. Try a smaller file."), mention_author=True)
    except Exception as e:
        await proc.delete()
        await ctx.reply(embed=discord.Embed(title="❌ Error", color=0xe74c3c, description=f"{ctx.author.mention}\n{str(e)[:500]}"), mention_author=True)
        print(f"Deobf error: {e}")

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

    proc = await ctx.reply(f"🔐 Obfuscating with Prometheus {ctx.author.mention}...", mention_author=True)
    try:
        success, result = obfuscate_prometheus_python(content)
        if not success:
            await proc.delete()
            await ctx.reply(embed=discord.Embed(title="❌ Obfuscation Failed", color=0xe74c3c, description=f"{ctx.author.mention}\n{result}"), mention_author=True)
            return

        obfuscated = result
        size_b = obfuscated.encode('utf-8')
        size_kb = len(size_b) / 1024
        file = None
        desc = f"{ctx.author.mention}\n**Obfuscation:** Prometheus\n**Size:** `{round(size_kb,2)} KB`"
        if size_kb > 10 or len(obfuscated) > 1800:
            file = File(io.BytesIO(size_b), filename="obfuscated.lua")
            desc += f"\n📦 Full code sent as file"
            emb = discord.Embed(title="🔐 Obfuscated Code", color=0x9b59b6, description=desc)
        else:
            preview = obfuscated[:1500] + ("\n... [truncated]" if len(obfuscated) > 1500 else "")
            desc += f"\n\n**Preview:**\n```lua\n{preview}\n```"
            emb = discord.Embed(title="🔐 Obfuscated Code", color=0x9b59b6, description=desc)
        emb.set_footer(text=f"Requested by {ctx.author}")
        await proc.delete()
        if file:
            await ctx.reply(embed=emb, file=file, mention_author=True)
        else:
            await ctx.reply(embed=emb, mention_author=True)
        if logs_col is not None:
            await asyncio.to_thread(logs_col.insert_one, {"uid": ctx.author.id, "act": "obfuscate", "url": extract_url(link if link else ctx.message.content), "at": discord.utils.utcnow()})
    except Exception as e:
        await proc.delete()
        await ctx.reply(embed=discord.Embed(title="❌ Error", color=0xe74c3c, description=f"{ctx.author.mention}\n{str(e)[:500]}"), mention_author=True)

@bot.event
async def on_ready():
    print(f"✅ Logged in as: {bot.user}")
    try:
        await bot.tree.sync()
        print("✅ Slash commands synced globally")
    except Exception as e:
        print(f"⚠️ Failed to sync slash commands: {e}")

    panels = await asyncio.to_thread(ticket_panels_col.find)
    for panel in panels:
        panel_id = str(panel["_id"])
        button_style = discord.ButtonStyle.gray
        color_map = {"gray": discord.ButtonStyle.gray, "blurple": discord.ButtonStyle.blurple, "green": discord.ButtonStyle.green, "red": discord.ButtonStyle.red}
        if panel.get("label_color"):
            button_style = color_map.get(panel["label_color"].lower(), discord.ButtonStyle.gray)
        view = PersistentTicketPanel(
            panel_id,
            panel.get("label_button", "Open Ticket"),
            panel.get("label_emoji", "🎟️"),
            button_style
        )
        bot.add_view(view)

    configs = await asyncio.to_thread(verification_config_col.find)
    for config in configs:
        guild_id = config["guild_id"]
        channel_id = config["channel_id"]
        message_id = config["message_id"]
        guild = bot.get_guild(guild_id)
        if guild:
            channel = guild.get_channel(channel_id)
            if channel:
                try:
                    msg = await channel.fetch_message(message_id)
                    new_embed = discord.Embed(
                        title="🔐 Server Verification",
                        description=(
                            "Welcome to the server! We are glad to Have you here.\n\n"
                            "To gain access to all the channels and features, please verify yourself by clicking the **Verify on Website** button below.\n"
                            "You will be redirected to our verification page where you must complete a short challenge.\n"
                            "This helps us keep the server safe and secure."
                        ),
                        color=0x1e90ff
                    )
                    new_embed.set_footer(text="Verification System")
                    if config.get("deadline"):
                        new_embed.add_field(
                            name="⏳ Verification Deadline",
                            value=f"All members must verify before <t:{config['deadline']}:R>.\nAfter that, unverified members will receive the **Not Verified** role.",
                            inline=False
                        )
                    view = get_verification_view()
                    await msg.edit(embed=new_embed, view=view)
                except Exception as e:
                    print(f"Failed to update verification message: {e}")

    active_configs = await asyncio.to_thread(active_checker_col.find)
    for cfg in active_configs:
        guild_id = cfg["guild_id"]
        channel_id = cfg["channel_id"]
        interval = cfg["interval"]
        task = asyncio.create_task(active_checker_loop(guild_id, channel_id, interval))
        active_checker_tasks[guild_id] = task

    asyncio.create_task(check_verification_deadlines())

    await bot.change_presence(activity=discord.Activity(type=discord.ActivityType.watching, name=".cmds | /ping | /channel_* | /ticket | /verification_system | /active_checker | /bypass | /auto_delete* | .get | .obf"))
    if db is not None:
        print(f"✅ Database Ready: {db.name}")

def keep_alive():
    while True:
        try:
            import requests
            requests.get("http://localhost:10000/ping")
        except:
            pass
        time.sleep(300)

if __name__ == "__main__":
    from threading import Thread
    def run_flask(): app.run(host="0.0.0.0", port=10000)
    Thread(target=run_flask, daemon=True).start()
    Thread(target=keep_alive, daemon=True).start()
    bot.run(TOKEN)
