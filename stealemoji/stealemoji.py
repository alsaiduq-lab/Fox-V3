import asyncio
import logging
from typing import Union

import discord
from redbot.core import Config, checks, commands
from redbot.core.bot import Red
from redbot.core.commands import Cog
from redbot.core.utils.chat_formatting import pagify

log = logging.getLogger("red.fox_v3.stealemoji")

class StealEmoji(Cog):
    """
    This cog steals emojis and creates servers for them
    """

    def __init__(self, red: Red):
        super().__init__()
        self.bot = red
        self.config = Config.get_conf(self, identifier=11511610197108101109111106105)
        default_global = {
            "stolemoji": {},
            "guildbanks": [],
            "autobanked_guilds": [],
            "on": False,
            "notify": 0,
            "autobank": False,
            "admins": [],
        }

        self.config.register_global(**default_global)

        self.is_on = None

    async def check_guild(self, guild, emoji):
        if len(guild.emojis) >= 2 * guild.emoji_limit:
            return False

        if len(guild.emojis) < guild.emoji_limit:
            return True

        if emoji.animated:
            return sum(e.animated for e in guild.emojis) < guild.emoji_limit
        else:
            return sum(not e.animated for e in guild.emojis) < guild.emoji_limit

    async def red_delete_data_for_user(self, **kwargs):
        """Nothing to delete"""
        return

    @commands.group()
    async def stealemoji(self, ctx: commands.Context):
        """
        Base command for this cog. Check help for the commands list.
        """
        pass

    @checks.is_owner()
    @stealemoji.command(name="clearemojis")
    async def se_clearemojis(self, ctx: commands.Context, confirm: bool = False):
        """Removes the history of all stolen emojis. Will not delete emojis from server banks"""
        if not confirm:
            await ctx.maybe_send_embed(
                "This will reset all stolen emoji data.\n"
                "If you want to continue, run this command again as:\n"
                "`[p]stealemoji clearemojis True`"
            )
            return

        await self.config.stolemoji.clear()
        await ctx.tick()

    @checks.is_owner()
    @stealemoji.command(name="print")
    async def se_print(self, ctx: commands.Context):
        """Prints all the emojis that have been stolen so far"""
        stolen = await self.config.stolemoji()
        id_list = [v.get("saveid") for k, v in stolen.items()]

        emoj = " ".join(str(e) for e in self.bot.emojis if e.id in id_list)

        if not emoj:
            await ctx.maybe_send_embed("No stolen emojis yet")
            return

        for page in pagify(emoj, delims=[" "]):
            await ctx.maybe_send_embed(page)

    @checks.is_owner()
    @stealemoji.command(name="notify")
    async def se_notify(self, ctx: commands.Context):
        """Cycles between notification settings for when an emoji is stolen

        None (Default)
        DM Owner
        Msg in server channel
        """
        curr_setting = await self.config.notify()

        if not curr_setting:
            await self.config.notify.set(1)
            await ctx.maybe_send_embed("Bot owner will now be notified when an emoji is stolen")
        elif curr_setting == 1:
            channel: discord.TextChannel = ctx.channel
            await self.config.notify.set(channel.id)
            await ctx.maybe_send_embed("This channel will now be notified when an emoji is stolen")
        else:
            await self.config.notify.set(0)
            await ctx.maybe_send_embed("Notifications are now off")

    @checks.is_owner()
    @stealemoji.command(name="collect")
    async def se_collect(self, ctx):
        """Toggles whether emoji's are collected or not"""
        curr_setting = await self.config.on()
        await self.config.on.set(not curr_setting)

        self.is_on = await self.config.on()

        await ctx.maybe_send_embed("Collection is now " + str(not curr_setting))

    @checks.is_owner()
    @stealemoji.command(name="autobank")
    async def se_autobank(self, ctx):
        """Toggles automatically creating new guilds as emoji banks"""
        curr_setting = await self.config.autobank()
        await self.config.autobank.set(not curr_setting)

        self.is_on = await self.config.autobank()

        await ctx.maybe_send_embed("AutoBanking is now " + str(not curr_setting))

    @checks.is_owner()
    @commands.guild_only()
    @stealemoji.command(name="deleteserver", aliases=["deleteguild"])
    async def se_deleteserver(self, ctx: commands.Context, guild_id=None):
        """Delete servers the bot is the owner of.

        Useful for auto-generated guildbanks."""
        if guild_id is None:
            guild = ctx.guild
        else:
            guild = await self.bot.get_guild(guild_id)

        if guild is None:
            await ctx.maybe_send_embed("Failed to get guild, cancelling")
            return
        guild: discord.Guild
        await ctx.maybe_send_embed(
            f"Will attempt to delete {guild.name} ({guild.id})\n" f"Okay to continue? (yes/no)"
        )

        def check(m):
            return m.author == ctx.author and m.channel == ctx.channel

        try:
            answer = await self.bot.wait_for("message", timeout=120, check=check)
        except asyncio.TimeoutError:
            await ctx.send("Timed out, canceling")
            return

        if answer.content.upper() not in ["Y", "YES"]:
            await ctx.maybe_send_embed("Cancelling")
            return
        try:
            await guild.delete()
        except discord.Forbidden:
            log.exception("No permission to delete. I'm probably not the guild owner")
            await ctx.maybe_send_embed("No permission to delete. I'm probably not the guild owner")
        except discord.HTTPException:
            log.exception("Unexpected error when deleting guild")
            await ctx.maybe_send_embed("Unexpected error when deleting guild")
        else:
            await self.bot.send_to_owners(f"Guild {guild.name} deleted")

    @checks.is_owner()
    @commands.guild_only()
    @stealemoji.command(name="bank")
    async def se_bank(self, ctx):
        """Add or remove current server as emoji bank"""

        def check(m):
            return (
                m.content.upper() in ["Y", "YES", "N", "NO"]
                and m.channel == ctx.channel
                and m.author == ctx.author
            )

        already_a_guildbank = ctx.guild.id in (await self.config.guildbanks())

        if already_a_guildbank:
            await ctx.maybe_send_embed(
                "This is already an emoji bank\n"
                "Are you sure you want to remove the current server from the emoji bank list? (y/n)"
            )
        else:
            await ctx.maybe_send_embed(
                "This will upload custom emojis to this server\n"
                "Are you sure you want to make the current server an emoji bank? (y/n)"
            )

        msg = await self.bot.wait_for("message", check=check)

        if msg.content.upper() in ["N", "NO"]:
            await ctx.maybe_send_embed("Cancelled")
            return

        async with self.config.guildbanks() as guildbanks:
            if already_a_guildbank:
                guildbanks.remove(ctx.guild.id)
            else:
                guildbanks.append(ctx.guild.id)

        if already_a_guildbank:
            await ctx.maybe_send_embed("This server has been removed from being an emoji bank")
        else:
            await ctx.maybe_send_embed("This server has been added to be an emoji bank")

    @commands.Cog.listener()
    async def on_reaction_add(self, reaction: discord.Reaction, user: discord.User):
        """Event handler for reaction watching"""
        try:
            if not reaction.custom_emoji or user.bot:
                return
        except AttributeError:
            return  # Not a custom emoji

        if self.is_on is None:
            self.is_on = await self.config.on()

        if not self.is_on:
            return

        guild: discord.Guild = user.guild
        if await self.bot.cog_disabled_in_guild(self, guild):  # Handles None guild just fine
            return

        emoji: discord.Emoji = reaction.emoji
        stolen_emojis = await self.config.stolemoji()

        # Check if the emoji has already been registered
        if str(emoji) in stolen_emojis:
            return

        # Get list of admins from config (replace 'admins' with actual key)
        admins = await self.config.admins()

        def check(m):
            return m.author == admin and m.channel.type == discord.ChannelType.private and m.content.lower() in ['yes',
                                                                                                                 'no',
                                                                                                                 'y',
                                                                                                                 'n']

        for admin_id in admins:
            try:
                admin = self.bot.get_user(admin_id)
                if not admin:
                    admin = await self.bot.fetch_user(admin_id)
            except Exception as e:
                log.error("Failed to fetch user %s, error: %s", admin_id, e)
                continue

            embed = discord.Embed(
                title="New Emoji Detected!",
                description="Someone just used an emoji I don't recognize. If you want me to "
                            "add it to my collection, please respond with 'yes' or 'no'.",
                color=discord.Color.gold())

            # Embed message containing custom emoji reaction image URL
            embed.set_image(url=emoji.url)

            try:
                message = await admin.send(embed=embed)  # Send DM instead of mentioning in a channel
            except discord.Forbidden:
                log.warning("Couldn't send DM to user %s", admin_id)
                continue

            try:
                msg = await self.bot.wait_for('message', check=check, timeout=60)
                if msg.content.lower() in ['yes', 'y']:
                    # Add emoji to collection
                    async with self.config.stolemoji() as emojis:
                        emojis[str(emoji)] = str(emoji.url)
            except asyncio.TimeoutError:
                await admin.send(
                    "You didn't respond in time, please react to the message again if you want"
                    " to add the emoji.")

    @checks.is_owner()
    @stealemoji.command(name="addadmin")
    async def se_add_admin(self, ctx: commands.Context, user: discord.Member):
        """Add a user to the list of admins who can manage emojis."""

        async with self.config.admins() as admins:
            if user.id not in admins:
                admins.append(user.id)

        await ctx.send(f"Added {user.name} to the list of admins.")

    @checks.is_owner()
    @stealemoji.command(name="removeadmin")
    async def se_remove_admin(self, ctx: commands.Context, user: discord.Member):
        """Remove a user from the list of admins who can manage emojis."""

        async with self.config.admins() as admins:
            if user.id in admins:
                admins.remove(user.id)

        await ctx.send(f"Removed {user.name} from the list of admins.")
