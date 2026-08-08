from flask import Flask
app = Flask(__name__)
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

OWNER_ID = 1445289457866506290

mongo_client = None
db = None
settings_col = None
logs_col = None
tickets_col = None
ticket_panels_col = None
verification_config_col = None
level_config_col = None
user_xp_col = None
active_checker_col = None
auto_delete_config_col = None

try:
    mongo_client = MongoClient(MONGODB_URI, server_api=ServerApi('1'))
    mongo_client.admin.command('ping')
    db = mongo_client["rblxlua_data"]
    settings_col = db["settings"]
    logs_col = db["usage_logs"]
    tickets_col = db["tickets"]
    ticket_panels_col = db["ticket_panels"]
    verification_config_col = db["verification_config"]
    level_config_col = db["level_config"]
    user_xp_col = db["user_xp"]
    active_checker_col = db["active_checker_config"]
    auto_delete_config_col = db["auto_delete_config"]
    print("✅ MongoDB Connected")
except Exception as e:
    print(f"❌ MongoDB Error: {e}")

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix=".", intents=intents, help_command=None)

XP_PER_LEVEL = {
    1: 20, 2: 50, 3: 100, 4: 150, 5: 200,
    6: 250, 7: 300, 8: 350, 9: 400, 10: 500
}

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

async def get_level_config(guild_id):
    if level_config_col is None:
        return None
    return await asyncio.to_thread(level_config_col.find_one, {"guild_id": guild_id})

async def set_level_config(guild_id, channel_id, level_roles, enabled=True):
    if level_config_col is not None:
        await asyncio.to_thread(level_config_col.update_one,
            {"guild_id": guild_id},
            {"$set": {"channel_id": channel_id, "level_roles": level_roles, "enabled": enabled}},
            upsert=True
        )

async def update_level_enabled(guild_id, enabled):
    if level_config_col is not None:
        await asyncio.to_thread(level_config_col.update_one,
            {"guild_id": guild_id},
            {"$set": {"enabled": enabled}},
            upsert=True
        )

async def get_user_xp(guild_id, user_id):
    if user_xp_col is None:
        return {"xp": 0, "level": 0}
    doc = await asyncio.to_thread(user_xp_col.find_one, {"guild_id": guild_id, "user_id": user_id})
    if not doc:
        return {"xp": 0, "level": 0}
    return {"xp": doc.get("xp", 0), "level": doc.get("level", 0)}

async def set_user_xp(guild_id, user_id, xp, level):
    if user_xp_col is not None:
        await asyncio.to_thread(user_xp_col.update_one,
            {"guild_id": guild_id, "user_id": user_id},
            {"$set": {"xp": xp, "level": level}},
            upsert=True
        )

async def get_max_level(guild_id):
    config = await get_level_config(guild_id)
    if not config:
        return 0
    level_roles = config.get("level_roles", {})
    max_lv = 0
    for key in level_roles.keys():
        if key.isdigit():
            lv = int(key)
            if lv > max_lv:
                max_lv = lv
    return max_lv

def get_required_xp(level):
    return XP_PER_LEVEL.get(level, 500)

def get_level_up_embed(user, level, guild, roles_added=None):
    if level == 1:
        color = 0x1e90ff
        title = "🌟 Level Up!"
        desc = f"{user.mention} has reached **Level 1**!"
        footer = "Keep chatting to level up further!"
    elif level == 2:
        color = 0x00bfff
        title = "🌟 Level Up!"
        desc = f"{user.mention} has reached **Level 2**!\nYou're getting the hang of it!"
        footer = "Next level requires 50 XP"
    elif level == 3:
        color = 0x1e90ff
        title = "🌟 Level Up!"
        desc = f"{user.mention} has reached **Level 3**!\nYou're on fire!"
        footer = "Next level requires 100 XP"
    elif level == 4:
        color = 0x4169e1
        title = "🌟 Level Up!"
        desc = f"{user.mention} has reached **Level 4**!\nAmazing progress!"
        footer = "Next level requires 150 XP"
    elif level == 5:
        color = 0x6a5acd
        title = "🌟 Level Up!"
        desc = f"{user.mention} has reached **Level 5**!\nYou're a legend!"
        footer = "Next level requires 200 XP"
    elif level == 6:
        color = 0x8a2be2
        title = "🌟 Level Up!"
        desc = f"{user.mention} has reached **Level 6**!\nIncredible!"
        footer = "Next level requires 250 XP"
    elif level == 7:
        color = 0x9400d3
        title = "🌟 Level Up!"
        desc = f"{user.mention} has reached **Level 7**!\nYou're unstoppable!"
        footer = "Next level requires 300 XP"
    elif level == 8:
        color = 0x9932cc
        title = "🌟 Level Up!"
        desc = f"{user.mention} has reached **Level 8**!\nPhenomenal!"
        footer = "Next level requires 350 XP"
    elif level == 9:
        color = 0xba55d3
        title = "🌟 Level Up!"
        desc = f"{user.mention} has reached **Level 9**!\nAlmost at the top!"
        footer = "Next level requires 400 XP"
    elif level == 10:
        color = 0xff69b4
        title = "🌟 LEVEL MAX! 🌟"
        desc = f"{user.mention} has reached the **MAX LEVEL 10**!\nYou are the ultimate champion!"
        footer = "You've mastered the level system!"
    else:
        color = 0x1e90ff
        title = "🌟 Level Up!"
        desc = f"{user.mention} has reached **Level {level}**!"
        footer = "Keep going!"

    embed = discord.Embed(title=title, description=desc, color=color)
    embed.set_thumbnail(url=user.display_avatar.url)
    if roles_added:
        role_mentions = " ".join([f"<@&{rid}>" for rid in roles_added])
        embed.add_field(name="🎖️ Roles Received", value=role_mentions, inline=False)
    embed.set_footer(text=footer)
    return embed

async def apply_roles_to_all_members(guild):
    if not guild.me.guild_permissions.manage_roles:
        return
    config = await get_level_config(guild.id)
    if not config:
        return
    level_roles = config.get("level_roles", {})
    if not level_roles:
        return
    async for member in guild.fetch_members(limit=None):
        if member.bot:
            continue
        data = await get_user_xp(guild.id, member.id)
        level = data["level"]
        if level == 0:
            continue
        target_role_ids = level_roles.get(str(level), [])
        target_roles = [guild.get_role(rid) for rid in target_role_ids if guild.get_role(rid)]
        current_roles = member.roles
        to_remove = []
        for lv, rids in level_roles.items():
            if lv == "_channel":
                continue
            if int(lv) != level:
                for rid in rids:
                    role = guild.get_role(rid)
                    if role and role in current_roles:
                        to_remove.append(role)
        to_add = [r for r in target_roles if r not in current_roles]
        changes = []
        if to_remove:
            changes.append(member.remove_roles(*to_remove, reason="Sync level roles"))
        if to_add:
            changes.append(member.add_roles(*to_add, reason="Sync level roles"))
        if changes:
            try:
                await asyncio.gather(*changes)
            except discord.Forbidden:
                pass
            await asyncio.sleep(0.3)

class LevelConfigView(discord.ui.View):
    def __init__(self, guild, level, channel_id, interaction, is_update=False, enabled=True):
        super().__init__(timeout=60)
        self.guild = guild
        self.level = level
        self.channel_id = channel_id
        self.is_update = is_update
        self.enabled = enabled
        self.interaction = interaction

        roles = [r for r in guild.roles if r.name != "@everyone"]
        roles.sort(key=lambda r: r.position, reverse=True)

        if len(roles) > 25:
            roles = roles[:25]
            self.add_item(discord.ui.Button(label="Too many roles, only first 25 shown", disabled=True))

        options = []
        for r in roles:
            options.append(discord.SelectOption(
                label=r.name,
                value=str(r.id),
                description=f"ID: {r.id}",
                emoji=None
            ))

        select = discord.ui.Select(
            placeholder=f"Select exactly {level} role(s) for Level {level}. Previous level roles will be removed on level up.",
            min_values=level,
            max_values=level,
            options=options,
            custom_id="level_role_select"
        )
        select.callback = self.select_callback
        self.add_item(select)

    async def select_callback(self, interaction: discord.Interaction):
        if interaction.user != interaction.message.interaction.user:
            await interaction.response.send_message("You are not the one who ran the command.", ephemeral=True)
            return

        selected_role_ids = [int(value) for value in interaction.data["values"]]
        config = await get_level_config(self.guild.id)
        if config:
            level_roles = config.get("level_roles", {})
            enabled = config.get("enabled", True)
        else:
            level_roles = {}
            enabled = self.enabled
        level_roles[str(self.level)] = selected_role_ids
        await set_level_config(self.guild.id, self.channel_id, level_roles, enabled)

        await apply_roles_to_all_members(self.guild)

        action = "updated" if self.is_update else "saved"
        embed = discord.Embed(
            title=f"✅ Level Configuration {action.capitalize()}",
            description=f"Level **{self.level}** will now assign the following roles:\n" +
                        "\n".join([f"<@&{rid}>" for rid in selected_role_ids]),
            color=0x1e90ff
        )
        embed.set_footer(text="Roles have been applied to all users based on their current level.")
        await interaction.response.edit_message(embed=embed, view=None)
        self.stop()

    async def on_timeout(self):
        for child in self.children:
            child.disabled = True
        try:
            await self.interaction.edit_original_response(view=self)
            await self.interaction.followup.send(
                "❌ Your command is Expired you need to use a `/level_up_system` command again.",
                ephemeral=True
            )
        except:
            pass

@bot.tree.command(name="level_up_system", description="Configure the level-up system")
@app_commands.describe(
    level="The level number (1-10) to configure",
    select_channel="The channel where level-up announcements will be sent",
    enabled="Enable or disable the level system (optional, True/False)",
    update="Update an existing configuration (optional, True/False)"
)
@app_commands.choices(enabled=[
    app_commands.Choice(name="True", value="True"),
    app_commands.Choice(name="False", value="False")
])
@app_commands.choices(update=[
    app_commands.Choice(name="True", value="True"),
    app_commands.Choice(name="False", value="False")
])
@app_commands.default_permissions(administrator=True)
async def level_up_system(
    interaction: discord.Interaction,
    level: int,
    select_channel: discord.TextChannel,
    enabled: app_commands.Choice[str] = None,
    update: app_commands.Choice[str] = None
):
    if level < 1 or level > 10:
        await interaction.response.send_message("Level must be between 1 and 10.", ephemeral=True)
        return

    if not interaction.guild.me.guild_permissions.manage_roles:
        await interaction.response.send_message("I need the 'Manage Roles' permission to assign roles.", ephemeral=True)
        return

    config = await get_level_config(interaction.guild.id)

    if enabled is not None:
        new_status = True if enabled.value == "True" else False
        await update_level_enabled(interaction.guild.id, new_status)
        status_text = "enabled" if new_status else "disabled"
        embed = discord.Embed(
            title="✅ Level System Updated",
            description=f"The level system has been **{status_text}**.",
            color=0x1e90ff
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return

    has_roles = False
    if config:
        level_roles = config.get("level_roles", {})
        for key in level_roles:
            if key != "_channel":
                has_roles = True
                break

    if config and has_roles:
        if update is not None and update.value == "True":
            view = LevelConfigView(interaction.guild, level, select_channel.id, interaction, is_update=True, enabled=config.get("enabled", True))
            embed = discord.Embed(
                title="🎛️ Level Role Update",
                description=f"Select exactly **{level}** role(s) to assign when a user reaches Level {level}.\n\n**Note:** When a user levels up, roles from all previous levels will be automatically removed.",
                color=0x1e90ff
            )
            embed.set_footer(text="You have 1 minute to choose roles.")
            await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
            return
        else:
            await interaction.response.send_message(
                "❌ Your Level System is already set on this Server!\n"
                "Use `/level_up_system` with `update: True` to modify existing configuration, or `enabled: True/False` to toggle the system.",
                ephemeral=True
            )
            return

    view = LevelConfigView(interaction.guild, level, select_channel.id, interaction, is_update=False, enabled=True)
    embed = discord.Embed(
        title="🎛️ Level Role Configuration",
        description=f"Select exactly **{level}** role(s) to assign when a user reaches Level {level}.\n\n**Note:** When a user levels up, roles from all previous levels will be automatically removed.",
        color=0x1e90ff
    )
    embed.set_footer(text="You have 1 minute to choose roles.")
    await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

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
        return

    config = await get_level_config(message.guild.id)
    if not config or not config.get("enabled", True):
        await bot.process_commands(message)
        return

    guild = message.guild
    user = message.author

    data = await get_user_xp(guild.id, user.id)
    current_level = data["level"]
    max_lv = await get_max_level(guild.id)

    if current_level >= max_lv and max_lv > 0:
        await bot.process_commands(message)
        return

    current_xp = data["xp"]
    current_xp += 1
    next_level = current_level + 1

    if next_level <= max_lv and current_xp >= get_required_xp(next_level):
        new_level = next_level
        current_xp = 0
        await set_user_xp(guild.id, user.id, current_xp, new_level)

        level_roles = config.get("level_roles", {})
        roles_to_remove = []
        for lv in range(1, new_level):
            role_ids = level_roles.get(str(lv), [])
            for rid in role_ids:
                role = guild.get_role(rid)
                if role and role in user.roles:
                    roles_to_remove.append(role)
        if roles_to_remove:
            try:
                await user.remove_roles(*roles_to_remove, reason=f"Leveled up to Level {new_level}")
            except discord.Forbidden:
                pass

        role_ids = level_roles.get(str(new_level), [])
        roles_to_add = [guild.get_role(rid) for rid in role_ids if guild.get_role(rid)]
        if roles_to_add:
            try:
                await user.add_roles(*roles_to_add, reason=f"Reached Level {new_level}")
            except discord.Forbidden:
                pass
        else:
            roles_to_add = []

        channel_id = config.get("channel_id")
        if channel_id:
            channel = guild.get_channel(channel_id)
            if channel:
                embed = get_level_up_embed(user, new_level, guild, [r.id for r in roles_to_add])
                await channel.send(content=user.mention, embed=embed)

        try:
            dm_embed = discord.Embed(
                title=f"🌟 Level Up in {guild.name}!",
                description=f"You've reached **Level {new_level}**!",
                color=0x1e90ff
            )
            dm_embed.set_thumbnail(url=user.display_avatar.url)
            if roles_to_add:
                role_mentions = " ".join([r.mention for r in roles_to_add])
                dm_embed.add_field(name="🎖️ Roles Received", value=role_mentions, inline=False)
            dm_embed.set_footer(text="Keep chatting to level up further!")
            await user.send(embed=dm_embed)
        except:
            pass

    else:
        await set_user_xp(guild.id, user.id, current_xp, current_level)

    await bot.process_commands(message)

@bot.command(name="level")
async def level_command(ctx):
    config = await get_level_config(ctx.guild.id)
    if not config or not config.get("enabled", True):
        embed = discord.Embed(
            title="❌ Level System Not Active",
            description=(
                "The Level System is not set up or is currently disabled on this Server.\n"
                "An administrator should use `/level_up_system` to configure it."
            ),
            color=0xe74c3c
        )
        await ctx.reply(embed=embed, mention_author=False)
        return

    data = await get_user_xp(ctx.guild.id, ctx.author.id)
    level = data["level"]
    xp = data["xp"]
    max_lv = await get_max_level(ctx.guild.id)

    if max_lv == 0:
        await ctx.reply("No levels configured yet.", mention_author=False)
        return

    if level >= max_lv:
        embed = discord.Embed(
            title="📊 Your Level Stats",
            description=f"{ctx.author.mention}",
            color=0x1e90ff
        )
        embed.add_field(name="Level", value=f"**{level}** (MAX)", inline=True)
        embed.add_field(name="Total XP", value=f"**{xp}**", inline=True)
        embed.add_field(name="Required XP", value="**MAX**", inline=True)
        embed.set_thumbnail(url=ctx.author.display_avatar.url)
        embed.set_footer(text="You've reached the maximum level!")
        await ctx.reply(embed=embed, mention_author=False)
    else:
        next_level = level + 1
        required = get_required_xp(next_level)
        progress = xp / required
        bar_length = 10
        filled = int(progress * bar_length)
        bar = "█" * filled + "░" * (bar_length - filled)
        embed = discord.Embed(
            title="📊 Your Level Stats",
            description=f"{ctx.author.mention}",
            color=0x1e90ff
        )
        embed.add_field(name="Level", value=f"**{level}**", inline=True)
        embed.add_field(name="XP", value=f"**{xp}** / {required}", inline=True)
        embed.add_field(name="Progress", value=f"`{bar}` {int(progress*100)}%", inline=False)
        embed.set_thumbnail(url=ctx.author.display_avatar.url)
        embed.set_footer(text=f"{xp} XP until Level {next_level}")
        await ctx.reply(embed=embed, mention_author=False)

@bot.command(name="lvl")
async def level_shortcut(ctx):
    await level_command(ctx)

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

class VerifyView(discord.ui.View):
    def __init__(self, guild_id):
        super().__init__(timeout=None)
        self.guild_id = guild_id
        button = discord.ui.Button(
            label="Verify",
            style=discord.ButtonStyle.green,
            emoji="👤",
            custom_id=f"verify_{guild_id}"
        )
        button.callback = self.verify_callback
        self.add_item(button)

    async def verify_callback(self, interaction: discord.Interaction):
        config = await asyncio.to_thread(verification_config_col.find_one, {"guild_id": interaction.guild.id})
        if not config:
            await interaction.response.send_message("⚠️ Verification system not configured.", ephemeral=True)
            return

        not_verified_role_id = config["not_verified_role_id"]
        verified_role_id = config["verified_role_id"]

        not_verified_role = interaction.guild.get_role(not_verified_role_id)
        verified_role = interaction.guild.get_role(verified_role_id)

        if not not_verified_role or not verified_role:
            await interaction.response.send_message("❌ Roles are missing. Contact an admin.", ephemeral=True)
            return

        if not_verified_role not in interaction.user.roles:
            await interaction.response.send_message("✅ You are already verified.", ephemeral=True)
            return

        try:
            await interaction.user.remove_roles(not_verified_role, reason="User verified")
            await interaction.user.add_roles(verified_role, reason="User verified")
            await interaction.response.send_message("✅ You have been verified!", ephemeral=True)
        except discord.Forbidden:
            await interaction.response.send_message("❌ I don't have permission to manage your roles. Contact an admin.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ An error occurred: {str(e)}", ephemeral=True)

@bot.tree.command(name="verify_system", description="Set up the verification system")
@app_commands.describe(
    select_role="The role to give upon verification",
    channel="The channel where the verification message will be sent"
)
@app_commands.default_permissions(administrator=True)
async def verify_system(
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

    embed = discord.Embed(
        title="🔐 Server Verification",
        description=(
            "Welcome to the server! We are glad to Have you here.\n\n"
            "To gain access to all the channels and features, please verify yourself by clicking the **VERIFY** button below.\n"
            "This helps us keep the server safe and secure."
        ),
        color=0x1e90ff
    )
    embed.set_footer(text="Verification System")

    view = VerifyView(guild.id)
    msg = await channel.send(embed=embed, view=view)
    bot.add_view(view, message_id=msg.id)

    config_data = {
        "guild_id": guild.id,
        "not_verified_role_id": not_verified_role.id,
        "verified_role_id": select_role.id,
        "channel_id": channel.id,
        "message_id": msg.id
    }
    await asyncio.to_thread(verification_config_col.update_one,
        {"guild_id": guild.id},
        {"$set": config_data},
        upsert=True
    )

    await interaction.followup.send(
        f"✅ Verification system set up!\n"
        f"Not Verified role: {not_verified_role.mention}\n"
        f"Verified role: {select_role.mention}\n"
        f"Verification channel: {channel.mention}\n"
        f"Assigned Not Verified role to {members_assigned} members.",
        ephemeral=True
    )

def decode_base64_urlsafe(data: str) -> str:
    data = data.strip()
    data = data.replace('-', '+').replace('_', '/')
    padding = 4 - (len(data) % 4)
    if padding != 4:
        data += '=' * padding
    return base64.b64decode(data).decode('utf-8', errors='ignore')

def extract_possible_keys(text: str) -> list:
    patterns = [
        r'FREE_[A-Za-z0-9_]{25,}',
        r'PREMIUM_[A-Za-z0-9_]{25,}',
        r'[A-Z0-9a-z]{8}-[A-Z0-9a-z]{4}-[A-Z0-9a-z]{4}-[A-Z0-9a-z]{4}-[A-Z0-9a-z]{12}',
        r'\b[A-F0-9a-f]{32}\b',
        r'\b[A-F0-9a-f]{64}\b'
    ]
    bad_words = ["cloudflare", "insights", "analytics", "cdn", "sha256", "uuid", "var", "function", "document"]
    keys = []
    for pat in patterns:
        matches = re.findall(pat, text)
        for m in matches:
            if len(m) < 28:
                continue
            if any(bad in m.lower() for bad in bad_words):
                continue
            keys.append(m)
    return keys

async def bypass_delta_key(url: str) -> tuple[bool, str, str]:
    try:
        parsed = urlparse(url)
        query = parse_qs(parsed.query)
        param_names = ['d', 'r', 'token', 'key', 'data', 'url', 'u', 'redirect']
        found_url = None
        for name in param_names:
            if name in query:
                val = query[name][0]
                try:
                    decoded = base64.b64decode(val).decode('utf-8', errors='ignore')
                    if decoded.startswith('http'):
                        found_url = decoded
                        break
                except:
                    pass
                try:
                    decoded = decode_base64_urlsafe(val)
                    if decoded.startswith('http'):
                        found_url = decoded
                        break
                except:
                    pass
                if val.startswith('http'):
                    found_url = val
                    break

        if not found_url:
            found_url = url

        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as session:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/125.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.5",
            }
            async with session.get(found_url, headers=headers, allow_redirects=True, max_redirects=10) as resp:
                if resp.status != 200:
                    return False, None, f"HTTP {resp.status} when fetching URL."
                text = await resp.text(encoding='utf-8', errors='replace')

        keys = extract_possible_keys(text)
        if keys:
            return True, keys[0], None

        keys = extract_possible_keys(url)
        if keys:
            return True, keys[0], None

        return False, None, "No key found in the page content or URL."
    except Exception as e:
        return False, None, f"Error during bypass: {str(e)}"

@bot.tree.command(name="bypass", description="Bypass any URL and extract key")
@app_commands.describe(url="The URL to bypass")
async def slash_bypass(interaction: discord.Interaction, url: str):
    await interaction.response.defer()
    success, key, error = await bypass_delta_key(url)

    if not success:
        embed = discord.Embed(
            title="❌ Bypass Failed",
            description=f"An error occurred:\n```{error}```",
            color=0xe74c3c
        )
        await interaction.followup.send(embed=embed)
        return

    embed = discord.Embed(
        title="<:checkmark2:1446118933425033259> Bypass Successful",
        description=f"🔑 Key retrieved — copy it and paste it into the application.\n\n```\n{key}\n```",
        color=0x2ecc71
    )
    embed.set_footer(text=f"Request by {interaction.user.display_name}")
    await interaction.followup.send(embed=embed)

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
            "title": "RblXLua Tool Commands (1/2)",
            "description": f"Hello {ctx.author.mention}",
            "fields": [
                {"name": "`.obf`", "value": "Obfuscate Lua code using Prometheus (single base64 chunk, stable).", "inline": False},
                {"name": "`.level` / `.lvl`", "value": "Check your current level and XP.", "inline": False},
                {"name": "`.cmds`", "value": "Show this help menu.", "inline": False},
                {"name": "`.db`", "value": "Database commands: `status`, `clear` (owner only).", "inline": False},
                {"name": "`.request`", "value": "Search the web for a script and return its loadstring and source URL.", "inline": False},
            ]
        },
        {
            "title": "RblXLua Tool Commands (2/2)",
            "description": f"Hello {ctx.author.mention}",
            "fields": [
                {"name": "**Slash Commands**", "value": "`/ping` - Check bot latency\n`/channel_set` - Restrict commands to a channel\n`/channel_view` - View current restriction\n`/channel_clear` - Remove restriction\n`/ticket` - Create a ticket panel (admin only)\n`/verify_system` - Set up verification system (admin only)\n`/level_up_system` - Configure level-up system (admin only)\n`/active_checker` - Set up active checker (admin only)\n`/bypass` - Bypass any URL and extract key\n`/auto_delete_messages` - Add a channel for auto-deletion\n`/atd_view_channel` - View auto-delete channels\n`/atd_remove_channel` - Remove a channel from auto-delete", "inline": False},
            ]
        }
    ]

    view = CmdsPaginationView(pages, ctx.author.id)
    embed = view.get_embed()
    message = await ctx.reply(embed=embed, view=view, mention_author=True)
    view.message = message

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

async def search_web(query: str) -> list:
    results = []
    script_sites = [
        "pastebin.com",
        "github.com",
        "rentry.co",
        "controlc.com",
        "hastebin.com",
        "pastebin.pl",
        "justpaste.it",
        "textbin.net",
        "0x0.st",
        "privatebin.net"
    ]
    search_engines = [
        f"https://html.duckduckgo.com/html/?q={quote_plus(query)}",
        f"https://html.duckduckgo.com/html/?q={quote_plus('site:pastebin.com ' + query)}",
        f"https://html.duckduckgo.com/html/?q={quote_plus('site:github.com ' + query)}",
        f"https://html.duckduckgo.com/html/?q={quote_plus('site:rentry.co ' + query)}",
        f"https://html.duckduckgo.com/html/?q={quote_plus('site:controlc.com ' + query)}",
        f"https://html.duckduckgo.com/html/?q={quote_plus('site:hastebin.com ' + query)}",
        f"https://html.duckduckgo.com/html/?q={quote_plus('site:pastebin.pl ' + query)}",
        f"https://html.duckduckgo.com/html/?q={quote_plus('site:justpaste.it ' + query)}",
        f"https://html.duckduckgo.com/html/?q={quote_plus('site:textbin.net ' + query)}",
        f"https://html.duckduckgo.com/html/?q={quote_plus('site:0x0.st ' + query)}",
        f"https://html.duckduckgo.com/html/?q={quote_plus('site:privatebin.net ' + query)}"
    ]
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=25)) as session:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/125.0.0.0 Safari/537.36"}
        for search_url in search_engines:
            try:
                async with session.get(search_url, headers=headers) as resp:
                    if resp.status != 200:
                        continue
                    html = await resp.text()
                    soup = BeautifulSoup(html, "html.parser")
                    for a in soup.select("a.result__a"):
                        href = a.get("href")
                        if href and href.startswith("//"):
                            href = "https:" + href
                        title = a.text.strip()
                        if href and title and href not in [r[1] for r in results]:
                            results.append((title, href))
                    for url_elem in soup.select(".result__url"):
                        href = url_elem.text.strip()
                        if href and any(site in href for site in script_sites) and href.startswith("http"):
                            results.append(("Script", href))
                await asyncio.sleep(0.5)
            except:
                continue
    seen = set()
    unique_results = []
    for title, url in results:
        if url not in seen:
            seen.add(url)
            unique_results.append((title, url))
    return unique_results[:15]

async def find_script_from_search(query: str) -> tuple:
    results = await search_web(query)
    if not results:
        return None, None, "No results found."

    lua_indicators = ["loadstring", "local function", "function", "print", "game:", "script", "wait(", "task.wait", "require(", "getfenv", "setfenv"]
    for title, url in results:
        try:
            ok, content, _ = await fetch_content(url)
            if ok and content and len(content) > 100:
                lower = content.lower()
                if any(indicator in lower for indicator in lua_indicators):
                    return title, url, content
        except:
            continue
    return None, None, "No script found in the search results."

@bot.command(name="request")
async def request_script(ctx, *, query: str = None):
    if not query:
        await ctx.reply("❌ Please put a name like this: **.request <Any script name here>**", mention_author=False)
        return

    searching_embed = discord.Embed(
        title="🔍 Searching for script",
        description=f"Looking for `{query}` ...",
        color=0x1e90ff
    )
    msg = await ctx.reply(embed=searching_embed, mention_author=False)

    try:
        title, url, content = await find_script_from_search(query)
        if not content:
            await msg.edit(embed=discord.Embed(
                title="❌ Not Found",
                description="Could not find a script for that query. Try a more specific name.",
                color=0xe74c3c
            ))
            return

        if len(content) > 1800:
            file = File(io.BytesIO(content.encode('utf-8')), filename="script.lua")
            embed = discord.Embed(
                title="📜 Script Found",
                description=f"**Source:** [{title}]({url})",
                color=0x2ecc71
            )
            embed.add_field(name="Size", value=f"{round(len(content)/1024, 2)} KB", inline=False)
            await msg.edit(embed=embed, file=file)
        else:
            embed = discord.Embed(
                title="📜 Script Found",
                description=f"**Source:** [{title}]({url})",
                color=0x2ecc71
            )
            embed.add_field(name="Loadstring", value=f"```lua\n{content[:1000]}{'...' if len(content)>1000 else ''}\n```", inline=False)
            await msg.edit(embed=embed)
    except Exception as e:
        await msg.edit(embed=discord.Embed(
            title="❌ Error",
            description=f"An error occurred: {str(e)[:200]}",
            color=0xe74c3c
        ))

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
                            "To gain access to all the channels and features, please verify yourself by clicking the **VERIFY** button below.\n"
                            "This helps us keep the server safe and secure."
                        ),
                        color=0x1e90ff
                    )
                    new_embed.set_footer(text="Verification System")
                    view = VerifyView(guild_id)
                    await msg.edit(embed=new_embed, view=view)
                    bot.add_view(view, message_id=message_id)
                except Exception as e:
                    print(f"Failed to update verification message: {e}")

    for guild in bot.guilds:
        await apply_roles_to_all_members(guild)

    active_configs = await asyncio.to_thread(active_checker_col.find)
    for cfg in active_configs:
        guild_id = cfg["guild_id"]
        channel_id = cfg["channel_id"]
        interval = cfg["interval"]
        task = asyncio.create_task(active_checker_loop(guild_id, channel_id, interval))
        active_checker_tasks[guild_id] = task

    await bot.change_presence(activity=discord.Activity(type=discord.ActivityType.watching, name=".cmds | /ping | /channel_* | /ticket | /verify_system | /level_up_system | /active_checker | /bypass | /auto_delete* | .level/.lvl | .request"))
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
