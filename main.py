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
from urllib.parse import urlparse, parse_qs
from bson import ObjectId
from datetime import datetime, timedelta

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
    print("✅ MongoDB Connected")
except Exception as e:
    print(f"❌ MongoDB Error: {e}")

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix=".", intents=intents, help_command=None)

XP_PER_LEVEL = {
    1: 20,
    2: 50,
    3: 100,
    4: 150,
    5: 200,
    6: 250,
    7: 300,
    8: 350,
    9: 400,
    10: 500
}

def get_required_xp(level):
    return XP_PER_LEVEL.get(level, 500)

def get_level_config(guild_id):
    doc = level_config_col.find_one({"guild_id": guild_id})
    if not doc:
        return None
    return doc

def set_level_config(guild_id, channel_id, level_roles):
    level_config_col.update_one(
        {"guild_id": guild_id},
        {"$set": {"channel_id": channel_id, "level_roles": level_roles}},
        upsert=True
    )

def get_user_xp(guild_id, user_id):
    doc = user_xp_col.find_one({"guild_id": guild_id, "user_id": user_id})
    if not doc:
        return {"xp": 0, "level": 0}
    return {"xp": doc.get("xp", 0), "level": doc.get("level", 0)}

def set_user_xp(guild_id, user_id, xp, level):
    user_xp_col.update_one(
        {"guild_id": guild_id, "user_id": user_id},
        {"$set": {"xp": xp, "level": level}},
        upsert=True
    )

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

    embed = discord.Embed(
        title=title,
        description=desc,
        color=color
    )
    embed.set_thumbnail(url=user.display_avatar.url)
    if roles_added:
        role_mentions = " ".join([f"<@&{rid}>" for rid in roles_added])
        embed.add_field(name="🎖️ Roles Received", value=role_mentions, inline=False)
    embed.set_footer(text=footer)
    return embed

class LevelConfigView(discord.ui.View):
    def __init__(self, guild, level, channel_id):
        super().__init__(timeout=120)
        self.guild = guild
        self.level = level
        self.channel_id = channel_id

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
        config = get_level_config(self.guild.id)
        if not config:
            level_roles = {}
        else:
            level_roles = config.get("level_roles", {})
        level_roles[str(self.level)] = selected_role_ids
        set_level_config(self.guild.id, self.channel_id, level_roles)

        embed = discord.Embed(
            title="✅ Level Configuration Saved",
            description=f"Level **{self.level}** will now assign the following roles:\n" +
                        "\n".join([f"<@&{rid}>" for rid in selected_role_ids]),
            color=0x1e90ff
        )
        embed.set_footer(text="You can re-run the command to change roles.")
        await interaction.response.edit_message(embed=embed, view=None)

@bot.tree.command(name="level-up-system", description="Configure the level-up system")
@app_commands.describe(
    level="The level number (1-10) to configure",
    select_channel="The channel where level-up announcements will be sent"
)
@app_commands.default_permissions(administrator=True)
async def level_up_system(
    interaction: discord.Interaction,
    level: int,
    select_channel: discord.TextChannel
):
    if level < 1 or level > 10:
        await interaction.response.send_message("Level must be between 1 and 10.", ephemeral=True)
        return

    if not interaction.guild.me.guild_permissions.manage_roles:
        await interaction.response.send_message("I need the 'Manage Roles' permission to assign roles.", ephemeral=True)
        return

    config = get_level_config(interaction.guild.id)
    if not config:
        level_roles = {}
    else:
        level_roles = config.get("level_roles", {})
    level_roles["_channel"] = select_channel.id
    set_level_config(interaction.guild.id, select_channel.id, level_roles)

    view = LevelConfigView(interaction.guild, level, select_channel.id)

    embed = discord.Embed(
        title="🎛️ Level Role Configuration",
        description=f"Select exactly **{level}** role(s) to assign when a user reaches Level {level}.\n\n**Note:** When a user levels up, roles from all previous levels will be automatically removed.",
        color=0x1e90ff
    )
    embed.set_footer(text="You have 2 minutes to choose.")

    await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

@bot.event
async def on_message(message):
    if message.author.bot:
        return
    if not message.guild:
        return

    if message.content.startswith("."):
        await bot.process_commands(message)
        return

    guild = message.guild
    user = message.author

    data = get_user_xp(guild.id, user.id)
    current_xp = data["xp"]
    current_level = data["level"]

    current_xp += 1
    next_level = current_level + 1

    if next_level <= 10 and current_xp >= get_required_xp(next_level):
        new_level = next_level
        current_xp = 0
        set_user_xp(guild.id, user.id, current_xp, new_level)

        config = get_level_config(guild.id)
        if config:
            level_roles = config.get("level_roles", {})
            # Remove roles from previous levels (1 to new_level-1)
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

            # Add roles for new level
            role_ids = level_roles.get(str(new_level), [])
            roles_to_add = [guild.get_role(rid) for rid in role_ids if guild.get_role(rid)]
            if roles_to_add:
                try:
                    await user.add_roles(*roles_to_add, reason=f"Reached Level {new_level}")
                except discord.Forbidden:
                    pass
            else:
                roles_to_add = []

            # Announce in configured channel
            channel_id = config.get("channel_id")
            if channel_id:
                channel = guild.get_channel(channel_id)
                if channel:
                    embed = get_level_up_embed(user, new_level, guild, [r.id for r in roles_to_add])
                    await channel.send(content=user.mention, embed=embed)

            # DM user
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
        set_user_xp(guild.id, user.id, current_xp, current_level)

    await bot.process_commands(message)

@bot.command(name="level")
async def level_command(ctx):
    """Check your current level and XP."""
    data = get_user_xp(ctx.guild.id, ctx.author.id)
    level = data["level"]
    xp = data["xp"]
    next_level = level + 1
    if level >= 10:
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

# ========== TICKET SYSTEM ==========

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
        panel = ticket_panels_col.find_one({"_id": ObjectId(self.panel_id)})
        if not panel:
            await interaction.response.send_message("❌ This ticket panel is no longer valid.", ephemeral=True)
            return

        existing = tickets_col.find_one({
            "guild_id": interaction.guild.id,
            "user_id": interaction.user.id,
            "closed": False
        })
        if existing:
            channel = interaction.guild.get_channel(existing["channel_id"])
            if channel is None:
                tickets_col.update_one({"_id": existing["_id"]}, {"$set": {"closed": True, "closed_at": datetime.utcnow(), "closed_by": None}})
                existing = None
            else:
                await interaction.response.send_message("❌ You already have an open ticket. Please close it before opening a new one.", ephemeral=True)
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
        result_ticket = tickets_col.insert_one(ticket_doc)
        ticket_id = str(result_ticket.inserted_id)
        tickets_col.update_one({"_id": result_ticket.inserted_id}, {"$set": {"ticket_id": ticket_id}})

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

        await interaction.response.send_message("✅ Ticket Created", view=jump_view, ephemeral=True)

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
        ticket = tickets_col.find_one({"_id": ObjectId(ticket_id)})
        if not ticket:
            await interaction.response.send_message("❌ Ticket not found.", ephemeral=True)
            return

        panel = ticket_panels_col.find_one({"_id": ObjectId(ticket["panel_id"])})
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

        tickets_col.update_one({"_id": ObjectId(ticket_id)}, {"$set": {"claimed_by": interaction.user.id}})

        channel = interaction.guild.get_channel(ticket["channel_id"])
        if channel:
            creator_mention = f"<@{ticket['user_id']}>"
            
            embed_claim = discord.Embed(
                title="🖐️ Ticket Claimed",
                description=f"{interaction.user.mention} has claimed this ticket. {creator_mention}",
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
        ticket = tickets_col.find_one({"_id": ObjectId(ticket_id)})
        if not ticket:
            await interaction.response.send_message("❌ Ticket not found.", ephemeral=True)
            return

        panel = ticket_panels_col.find_one({"_id": ObjectId(ticket["panel_id"])})
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

        tickets_col.update_one({"_id": ObjectId(ticket_id)}, {"$set": {"closed": True, "closed_at": datetime.utcnow(), "closed_by": interaction.user.id}})

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
    result = ticket_panels_col.insert_one(panel_data)
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

# ========== VERIFICATION SYSTEM ==========

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
        config = verification_config_col.find_one({"guild_id": interaction.guild.id})
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
    verification_config_col.update_one(
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

@bot.event
async def on_ready():
    print(f"✅ Logged in as: {bot.user}")
    try:
        await bot.tree.sync()
        print("✅ Slash commands synced globally")
    except Exception as e:
        print(f"⚠️ Failed to sync slash commands: {e}")

    panels = ticket_panels_col.find()
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

    configs = verification_config_col.find()
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

    await bot.change_presence(activity=discord.Activity(type=discord.ActivityType.watching, name=".cmds | /ping | /channel_* | /ticket | /verify_system | /level-up-system | .level"))
    if db is not None:
        print(f"✅ Database Ready: {db.name}")

def get_allowed_channel():
    if settings_col is None:
        return None
    doc = settings_col.find_one({"key": "command_channel"})
    if doc:
        return doc.get("value")
    return None

def set_allowed_channel(channel_id):
    if settings_col is not None:
        settings_col.update_one(
            {"key": "command_channel"},
            {"$set": {"value": channel_id}},
            upsert=True
        )

def clear_allowed_channel():
    if settings_col is not None:
        settings_col.delete_one({"key": "command_channel"})

@bot.check
async def global_channel_check(ctx):
    if ctx.author.id == OWNER_ID:
        return True
    if ctx.guild is None:
        await ctx.send("⚠️ You are not allowed to use commands in DMs.")
        return False
    allowed = get_allowed_channel()
    if allowed is None:
        return True
    if ctx.channel.id == allowed:
        return True
    await ctx.send(f"⚠️ Commands are restricted to <#{allowed}>. Please use them there.")
    return False

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

@bot.tree.command(name="channel_set", description="Set the channel where commands are allowed")
@app_commands.describe(channel="The channel to allow commands in")
@app_commands.default_permissions(administrator=True)
async def channel_set(interaction: discord.Interaction, channel: discord.TextChannel):
    set_allowed_channel(channel.id)
    await interaction.response.send_message(f"✅ Commands are now restricted to {channel.mention}.", ephemeral=True)

@bot.tree.command(name="channel_view", description="View the currently allowed channel")
async def channel_view(interaction: discord.Interaction):
    allowed = get_allowed_channel()
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
    clear_allowed_channel()
    await interaction.response.send_message("✅ Channel restriction removed. Commands are now allowed everywhere.", ephemeral=True)

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

class EnvBypassDumper:
    def __init__(self):
        self.removed_snippets = []

    def remove_anti_env_checks(self, src):
        patterns_remove = [
            (r'if\s*_?G\s*[=!]=?\s*nil\s*then.*?end', '--[[G check removed]]'),
            (r'if\s*_?ENV\s*[=!]=?\s*nil\s*then.*?end', '--[[ENV check removed]]'),
            (r'if\s*getgenv\s*[=!]=?\s*nil\s*then.*?end', '--[[getgenv check removed]]'),
            (r'if\s*type\s*\(\s*getgenv\s*\)\s*~=\s*["\']function["\'].*?end', '--[[type check removed]]'),
            (r'_?\._?LOADED\s*[=!]=?\s*true.*?return', '--[[LOADED check removed]]'),
            (r'_?\._?ENVLOG.*?Kick\(.*?\)', '--[[ENVLOG kick removed]]'),
            (r'_?\._?GALACTIC.*?Kick\(.*?\)', '--[[GALACTIC kick removed]]'),
            (r'_?\._?LOGGER.*?Kick\(.*?\)', '--[[LOGGER kick removed]]'),
            (r'_?\._?UNOBF.*?Kick\(.*?\)', '--[[UNOBF kick removed]]'),
            (r'_?\._?INTERCEPT.*?Kick\(.*?\)', '--[[INTERCEPT kick removed]]'),
            (r'if\s*debug\s*~=\s*nil.*?then.*?error.*?end', '--[[debug error removed]]'),
            (r'for\s+_+,\s+v\s+in\s+pairs\s*\(\s*debug\s*\)\s+do.*?end', '--[[debug pairs removed]]'),
            (r'if\s*type\s*\(\s*rawget\s*\)\s*~=', '--[[rawget type check removed]]'),
            (r'if\s*loadstring\s*~=\s*nil\s+and\s+_l\s*~=\s*loadstring', '--[[loadstring check removed]]'),
            (r'if\s*_p\s*~=\s*nil\s+or\s+_j\s*~=\s*nil', '--[[_p/_j check removed]]'),
            (r'local\s+_v_logDetect\s*=\s*function\(\)\s*_v_p\(_v_err,\s*"logging detected"\);\s*while\s+true\s+do\s+end;\s*end;', '--[[logDetect removed]]'),
            (r'_v_logDetect\(\)', '--[[logDetect call removed]]'),
            (r'if\s+not\s+_c_v\(_v_t\)\s+then\s*_v_logDetect\(\)\s*end;?', '--[[_v_t check removed]]'),
            (r'if\s+not\s+_c_v\(_v_p\)\s+then\s*_v_logDetect\(\)\s*end;?', '--[[_v_p check removed]]'),
            (r'if\s+not\s+_c_v\(_v_xp\)\s+then\s*_v_logDetect\(\)\s*end;?', '--[[_v_xp check removed]]'),
            (r'if\s+not\s+_c_v\(_v_sm\)\s+then\s*_v_logDetect\(\)\s*end;?', '--[[_v_sm check removed]]'),
            (r'if\s+not\s+_c_v\(_v_req\)\s+then\s*_v_logDetect\(\)\s*end;?', '--[[_v_req check removed]]'),
            (r'if\s+not\s+_c_v\(_v_r\)\s+then\s*_v_logDetect\(\)\s*end;?', '--[[_v_r check removed]]'),
            (r'if\s+not\s+_c_v\(_v_rs\)\s+then\s*_v_logDetect\(\)\s*end;?', '--[[_v_rs check removed]]'),
            (r'_v_tamperCheck\(\)', '--[[tamperCheck removed]]'),
            (r'_proxy_active\s*=\s*true;?', '--[[proxy activation removed]]'),
            (r'local\s+_s_set,\s*_setfenv\s*=\s*_v_p\(function\(\)\s*return\s*_v_g\["setfenv"\]\s*end\);?.*?end;?', '--[[setfenv spoof removed]]'),
            (r'return\s+_self_ref;?', 'return _self_ref; --[[spoofed]]'),
        ]
        out = src
        for pat, repl in patterns_remove:
            matches = list(re.finditer(pat, out, re.DOTALL | re.IGNORECASE))
            for m in matches:
                snippet = out[m.start():m.end()]
                if snippet not in self.removed_snippets:
                    self.removed_snippets.append(snippet)
            out = re.sub(pat, repl, out, flags=re.DOTALL | re.IGNORECASE)
        return out

    def patch_function_checks(self, src):
        repl = [
            (r'local\s+_l\s*=\s*loadstring.*?local\s+_l\s*=\s*loadstring', 'local _l = loadstring or load'),
            (r'local\s+_g\s*=\s*game\.HttpGet', 'local _g = function() return "" end'),
            (r'if\s+_l\s*~=\s*loadstring.*?then\s*__:Kick.*?end', '--[[loadstring kick removed]]'),
            (r'if\s+_g\s*~=\s*game\.HttpGet.*?then\s*__:Kick.*?end', '--[[HttpGet kick removed]]')
        ]
        out = src
        for old, new in repl:
            out = re.sub(old, new, out, flags=re.DOTALL)
        return out

    def inject_dummy_returns(self, src):
        block = [
            "writefile", "readfile", "listfiles", "makefolder",
            "delfile", "getfenv", "setfenv", "getgenv",
            "debug.getupvalue", "debug.setupvalue", "debug.getlocal",
            "debug.setlocal", "debug.getregistry", "hookfunction",
            "rawset", "rawget", "rawequal", "newcclosure",
            "loadstring", "load", "require"
        ]
        out = src
        for name in block:
            out = re.sub(
                rf'if\s+type\s*\(\s*{name}\s*\)\s*[=!]=?\s*["\']?nil["\']?\s+then.*?(Kick|error|return).*?end',
                f'--[[{name} check removed]]',
                out, flags=re.DOTALL
            )
        return out

    def full_bypass(self, code):
        out = code
        self.removed_snippets = []
        out = self.remove_anti_env_checks(out)
        out = self.patch_function_checks(out)
        out = self.inject_dummy_returns(out)
        out = re.sub(r'local\s+function\s+_v_logDetect\(\)[^;]*;', '--[[logDetect removed]]', out, flags=re.DOTALL)
        return {
            "patched_code": out.strip(),
            "bypassed_count": len(self.removed_snippets)
        }

def make_result_embed(ctx, title: str, deobf: dict=None, raw: str=None, env_bypass: dict=None):
    if env_bypass:
        desc = f"{ctx.author.mention}\n**Anti-env checks bypassed:** `{env_bypass['bypassed_count']}`\n**Size:** `{round(len(env_bypass['patched_code'].encode('utf-8'))/1024, 2)} KB`\n\n**Protection Snippets:**\n```lua\n"
        snippets = env_bypass.get("snippets", [])
        if snippets:
            snippet_text = ""
            for i, snippet in enumerate(snippets[:3]):
                snippet_text += f"-- Removed {i+1}:\n{snippet}\n\n"
            if len(snippet_text) > 500:
                snippet_text = snippet_text[:500] + "\n... [truncated]"
            desc += snippet_text + "```"
        else:
            desc += "No specific protection snippets found.\n```"
        content = env_bypass["patched_code"]
    elif deobf:
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
    if env_bypass:
        preview_len = int(len(content) * 0.3)
        preview_len = min(preview_len, 500)
        if preview_len < 50:
            preview_len = min(150, len(content))
        preview = content[:preview_len]
        if len(content) > preview_len:
            preview += "... [truncated]"
        desc += f"\n\n**Patched Code Preview (30%):**\n```lua\n{preview}\n```"
    elif deobf:
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

@bot.group(name="db", invoke_without_command=True)
async def db_group(ctx):
    await delete_cmds_only(ctx)
    emb = discord.Embed(title="Database Commands", color=0x2b2d31, description=f"Hey {ctx.author.mention}\nUse these sub-commands:")
    emb.add_field(name="`db status`", value="Check database connection", inline=False)
    emb.add_field(name="`db clear`", value="Clear stored data", inline=False)
    await ctx.reply(embed=emb, mention_author=True)

@db_group.command(name="status")
async def db_status(ctx):
    await delete_cmds_only(ctx)
    if db is not None:
        emb = discord.Embed(title="Database Status", color=0x2ecc71, description=f"✅ {ctx.author.mention}\nConnected")
    else:
        emb = discord.Embed(title="Database Status", color=0xe74c3c, description=f"❌ {ctx.author.mention}\nNot available")
    await ctx.reply(embed=emb, mention_author=True)

@db_group.command(name="clear")
@commands.is_owner()
async def db_clear(ctx):
    await delete_cmds_only(ctx)
    if settings_col is not None and logs_col is not None:
        settings_col.delete_many({})
        logs_col.delete_many({})
    emb = discord.Embed(title="Database Status", color=0x2ecc71, description=f"✅ {ctx.author.mention}\nAll data cleared")
    await ctx.reply(embed=emb, mention_author=True)

@bot.command(name="cmds")
async def show_commands(ctx):
    await delete_cmds_only(ctx)
    emb = discord.Embed(
        title="RblXLua Tool Commands",
        color=0x9b59b6,
        description=f"Hello {ctx.author.mention}"
    )
    emb.add_field(
        name="`Lua Deobf [.l]`",
        value="Deobfuscate Lua (Prometheus, WeAreDevs, then enhanced fallback).",
        inline=False
    )
    emb.add_field(
        name="`Fetch Lua [.get]`",
        value="Fetch and decode raw source from URL or attachment.",
        inline=False
    )
    emb.add_field(
        name="`Env Logger [.env]`",
        value="Bypass anti-env checks and unpack the script.",
        inline=False
    )
    emb.add_field(
        name="`Obfuscate [.obf]`",
        value="Obfuscate Lua code using Prometheus (single base64 chunk, stable).",
        inline=False
    )
    emb.add_field(
        name="`Commands [.cmds]`",
        value="Show this help menu.",
        inline=False
    )
    emb.add_field(
        name="`Database [.db]`",
        value="Database commands: `status`, `clear` (owner only).",
        inline=False
    )
    emb.add_field(
        name="**Slash Commands**",
        value="`/ping` - Check bot latency\n`/channel_set` - Restrict commands to a channel\n`/channel_view` - View current restriction\n`/channel_clear` - Remove restriction\n`/ticket` - Create a ticket panel (admin only)\n`/verify_system` - Set up verification system (admin only)\n`/level-up-system` - Configure level-up roles (admin only)",
        inline=False
    )
    emb.add_field(
        name="**Prefix Commands**",
        value="`.level` - Check your current level and XP",
        inline=False
    )
    emb.set_footer(text="Owner can use commands anywhere. Channel restriction applies to others.")
    await ctx.send(embed=emb, mention_author=True)

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
                logs_col.insert_one({"uid": ctx.author.id, "act": "deobf", "obf": "Prometheus", "url": extract_url(link if link else ctx.message.content), "at": discord.utils.utcnow()})
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
                logs_col.insert_one({"uid": ctx.author.id, "act": "deobf", "obf": "WeAreDevs", "url": extract_url(link if link else ctx.message.content), "at": discord.utils.utcnow()})
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
            logs_col.insert_one({"uid": ctx.author.id, "act": "deobf", "obf": obfuscator_name, "url": extract_url(link if link else ctx.message.content), "at": discord.utils.utcnow()})
    except asyncio.TimeoutError:
        try: await proc.delete()
        except: pass
        await ctx.reply(embed=discord.Embed(title="⏱️ Timeout", color=0xe74c3c, description=f"{ctx.author.mention}\nDeobfuscation took too long. Try a smaller file."), mention_author=True)
    except Exception as e:
        try: await proc.delete()
        except: pass
        await ctx.reply(embed=discord.Embed(title="❌ Error", color=0xe74c3c, description=f"{ctx.author.mention}\n{str(e)[:500]}"), mention_author=True)
        print(f"Deobf error: {e}")

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
        if logs_col is not None:
            logs_col.insert_one({"uid": ctx.author.id, "act": "fetch", "url": extract_url(link), "at": discord.utils.utcnow()})
    except Exception as e:
        await proc.delete()
        await ctx.reply(embed=discord.Embed(title="❌ Error", color=0xe74c3c, description=f"{ctx.author.mention}\n{str(e)[:500]}"), mention_author=True)

@bot.command(name="env")
async def env_command(ctx, *, link=None):
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

    proc = await ctx.reply(f"🛡️ Bypassing anti-env checks {ctx.author.mention}...", mention_author=True)
    try:
        dumper = EnvBypassDumper()
        bypass_result = dumper.full_bypass(content)
        patched_code = bypass_result["patched_code"]
        bypassed = bypass_result["bypassed_count"]
        snippets = dumper.removed_snippets[:10]

        if not patched_code:
            patched_code = "-- Bypass resulted in empty script, original code may be fully anti-tamper"

        env_report = {
            "patched_code": patched_code,
            "bypassed_count": bypassed,
            "snippets": snippets
        }
        emb, file = make_result_embed(ctx, "🛡️ Anti-env Bypass Complete", env_bypass=env_report)
        await proc.delete()
        if file:
            await ctx.reply(embed=emb, file=file, mention_author=True)
        else:
            await ctx.reply(embed=emb, mention_author=True)
        if logs_col is not None:
            logs_col.insert_one({"uid": ctx.author.id, "act": "envbypass", "url": extract_url(link if link else ctx.message.content), "at": discord.utils.utcnow()})
    except Exception as e:
        await proc.delete()
        await ctx.reply(embed=discord.Embed(title="❌ Error", color=0xe74c3c, description=f"{ctx.author.mention}\n{str(e)[:500]}"), mention_author=True)
        print(f"Env error: {e}")

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
            logs_col.insert_one({"uid": ctx.author.id, "act": "obfuscate", "url": extract_url(link if link else ctx.message.content), "at": discord.utils.utcnow()})
    except Exception as e:
        await proc.delete()
        await ctx.reply(embed=discord.Embed(title="❌ Error", color=0xe74c3c, description=f"{ctx.author.mention}\n{str(e)[:500]}"), mention_author=True)

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
