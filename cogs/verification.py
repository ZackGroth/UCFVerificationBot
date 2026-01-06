import os
import os.path as osp
import smtplib
import ssl
import random
import discord
from discord import app_commands
from discord.ext import commands
from email.mime.text import MIMEText
from email.header import Header
from datetime import datetime, timedelta, timezone
import time

# --- ZoneInfo with fallback (cross-platform DST support) ---
try:
    from zoneinfo import ZoneInfo
except ImportError:
    from zoneinfo import ZoneInfo

from util.email import is_valid_email

# --- Google Sheets Integration ---
import gspread
from google.oauth2.service_account import Credentials


class Verification(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

        try:
            # Load environment variables
            self.used_emails = os.environ["used_emails"]
            self.warn_emails = os.environ["warn_emails"]
            self.moderator_email = os.environ["moderator_email"]
            self.sample_username = os.environ["sample"]
            self.verify_domain = os.environ["domain"]
            self.email_from = os.environ["from"]
            self.email_password = os.environ["password"]
            self.email_subject = os.environ["subject"]
            self.email_server = os.environ["server"]
            self.email_port = int(os.environ["port"])
            self.role = os.environ["server_role"]
            self.channel_id = int(os.environ["channel_id"])
            self.notify_id = int(os.environ["notify_id"])  # Admin log channel
            self.admin_id = int(os.environ["admin_id"])
            self.admin_ids = [
                int(x) for x in os.environ.get("admin_ids", str(self.admin_id)).split(",") if x.strip()
            ]
            self.author_name = os.environ["author_name"]
            self.webmail_link = os.environ["webmail_link"]
            self.guild_id = int(os.environ["guild_id"])
            self.lock_role_id = int(os.environ["lock_role_id"])

            # Optional ticket channel
            try:
                self.ticket_id = int(os.environ["ticket_id"])
                self.ticket_loaded = True
            except KeyError:
                print("ticket_id not loaded. Defaulting to admin_id for reverification messages.")
                self.ticket_loaded = False

            # Resolve file paths
            self.used_emails = osp.join(self.bot.current_dir, self.bot.data_path, self.used_emails)
            self.warn_emails = osp.join(self.bot.current_dir, self.bot.data_path, self.warn_emails)

        except KeyError as e:
            print(f"Config error.\n\tKey Not Loaded: {e}")

        # Runtime state
        self.token_list = {}
        self.email_list = {}
        self.email_attempts = {}
        self.verify_attempts = {}

        # Ensure data folder exists
        data_dir = osp.join(self.bot.current_dir, self.bot.data_path)
        if not os.path.exists(data_dir):
            os.makedirs(data_dir)

        # --- Google Sheets Setup ---
        try:
            scope = [
                "https://www.googleapis.com/auth/spreadsheets",
                "https://www.googleapis.com/auth/drive"
            ]
            creds = Credentials.from_service_account_file("service_account.json", scopes=scope)
            gc = gspread.authorize(creds)
            self.sheet = gc.open_by_key("1ZQkRDQoDov65On7ppg9hTbWVtOQWu2EYJBdsnMafd0g").sheet1
            print("Google Sheets connected successfully.")
        except Exception as e:
            print(f"[WARN] Google Sheets setup failed: {e}")
            self.sheet = None

    # ----------------------------------------------------------------------
    # Helpers
    # ----------------------------------------------------------------------
    def _in_verify_channel_or_thread(self, channel: discord.abc.GuildChannel | discord.Thread) -> bool:
        """Allow /email and /verify in the verification channel OR in threads under that channel."""
        try:
            if channel.id == self.channel_id:
                return True
            if isinstance(channel, discord.Thread) and channel.parent_id == self.channel_id:
                return True
            return False
        except Exception:
            return False

    async def _get_notify_channel(self, guild: discord.Guild) -> discord.abc.Messageable | None:
        """Robustly resolve the notify channel, even if not cached."""
        try:
            ch = guild.get_channel(self.notify_id)
            if ch:
                return ch
            return await self.bot.fetch_channel(self.notify_id)
        except Exception as e:
            print(f"[WARN] Could not resolve notify channel: {e}")
            return None

    def _now_eastern_str(self) -> str:
        """Cross-platform Eastern Time timestamp."""
        try:
            return datetime.now(ZoneInfo("America/New_York")).strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            is_dst = time.localtime().tm_isdst
            offset = -4 if is_dst else -5
            eastern = timezone(timedelta(hours=offset))
            return datetime.now(eastern).strftime("%Y-%m-%d %H:%M:%S")

    def _discord_display_name(self, user: discord.User | discord.Member) -> str:
        if getattr(user, "discriminator", "0") != "0":
            return f"{user.name}#{user.discriminator}"
        return user.name

    # ----------------------------------------------------------------------
    # /help (ephemeral)
    # ----------------------------------------------------------------------
    @app_commands.command(name="help", description="Instructions on how to verify your UCF account.")
    async def slash_help(self, interaction: discord.Interaction):
        verify_channel = interaction.guild.get_channel(self.channel_id)
        msg = (
            f"To verify your UCF account:\n"
            f"1) Run `/email {self.sample_username}@{self.verify_domain}` in {verify_channel.mention}.\n"
            f"2) Check your inbox (and junk folder) for a 4-digit token.\n"
            f"3) Run `/verify ####` in {verify_channel.mention} to complete verification.\n\n"
            f"Access webmail: {self.webmail_link}"
        )
        await interaction.response.send_message(msg, ephemeral=True)

    # ----------------------------------------------------------------------
    # /email
    # ----------------------------------------------------------------------
    @app_commands.command(name="email", description="Send a verification email to your UCF address.")
    @app_commands.describe(email="Your @ucf.edu email address")
    async def slash_email(self, interaction: discord.Interaction, email: str):
        await interaction.response.defer(ephemeral=True)

        # Allow usage in the verification channel or any thread inside it
        if not self._in_verify_channel_or_thread(interaction.channel):
            print(
                f"[DEBUG] Blocked /email: Channel={interaction.channel.id}, "
                f"Parent={getattr(interaction.channel, 'parent_id', None)}, Expected={self.channel_id}"
            )
            return await interaction.followup.send(
                f"Please use this command in the verification channel (<#{self.channel_id}>) or one of its threads.",
                ephemeral=True
            )

        print(f"Emailing user {interaction.user.name}, email {email}")

        # Too many attempts
        if self.email_attempts.get(interaction.user.id, 0) >= 5:
            await interaction.followup.send(
                "You have exceeded the maximum number of verification attempts. Please contact a moderator.",
                ephemeral=True,
            )
            notify = await self._get_notify_channel(interaction.guild)
            if notify:
                await notify.send(f"⚠️ {interaction.user.mention} exceeded /email limit.")
            return

        # Validate email
        if not is_valid_email(email) or not email.endswith(f"@{self.verify_domain}"):
            return await interaction.followup.send(
                f"Invalid email. Must end with `@{self.verify_domain}`.",
                ephemeral=True
            )

        if email.lower().startswith(self.sample_username.lower()):
            return await interaction.followup.send(
                "Use your real email, not the sample.",
                ephemeral=True
            )

        # Warn-list check
        try:
            with open(self.warn_emails, "r") as f:
                if any(email.lower() == line.strip().lower() for line in f):
                    notify = await self._get_notify_channel(interaction.guild)
                    if notify:
                        await notify.send(f"⚠️ Warning: email `{email}` used by {interaction.user.mention}")
        except FileNotFoundError:
            pass
        except Exception as e:
            print(f"[WARN] warn_emails check failed: {e}")

        # Used email check (blocks reuse)
        if await self.check_emails_file(interaction, email):
            return

        # Send verification email
        try:
            await interaction.followup.send("Sending verification email...", ephemeral=True)

            with smtplib.SMTP(self.email_server, self.email_port) as server:
                server.ehlo()
                if self.email_port in (465, 587):
                    context = ssl.SSLContext(ssl.PROTOCOL_TLSv1_2)
                    server.starttls(context=context)
                    server.ehlo()

                server.login(self.email_from, self.email_password)

                token = random.randint(1000, 9999)
                self.token_list[interaction.user.id] = str(token)
                self.email_list[interaction.user.id] = email

                verify_channel = interaction.guild.get_channel(self.channel_id)

                message_text = (
                    f"Hello! Thank you for joining our Discord server!\n\n"
                    f"The command to use in #{verify_channel.name} is: /verify {token}\n\n"
                    f"Copy and paste that command to complete verification.\n\n"
                    f"If you didn’t request this, contact {self.moderator_email}."
                )
                msg = MIMEText(message_text, "plain", "utf-8")
                msg["Subject"] = Header(self.email_subject, "utf-8")
                msg["From"] = self.email_from
                msg["To"] = email

                server.sendmail(self.email_from, [email], msg.as_string())
                server.quit()

        except Exception as e:
            print(f"Email error: {e}")
            notify = await self._get_notify_channel(interaction.guild)
            if notify:
                await notify.send(f"⚠️ Email send failed: {e}")
            return await interaction.followup.send(
                "Error sending verification email. Moderators have been notified.",
                ephemeral=True,
            )

        self.email_attempts[interaction.user.id] = self.email_attempts.get(interaction.user.id, 0) + 1
        await interaction.followup.send(
            f"Verification email sent to **{email}**! Use `/verify ####` (the token from your inbox). "
            f"Check your junk folder if missing.",
            ephemeral=True
        )

    # ----------------------------------------------------------------------
    # /verify
    # ----------------------------------------------------------------------
    @app_commands.command(name="verify", description="Verify your account using your 4-digit token.")
    @app_commands.describe(token="The 4-digit token sent to your UCF email.")
    async def slash_verify(self, interaction: discord.Interaction, token: str):
        await interaction.response.defer(ephemeral=True)

        # Allow usage in the verification channel or any thread inside it
        if not self._in_verify_channel_or_thread(interaction.channel):
            print(
                f"[DEBUG] Blocked /verify: Channel={interaction.channel.id}, "
                f"Parent={getattr(interaction.channel, 'parent_id', None)}, Expected={self.channel_id}"
            )
            return await interaction.followup.send(
                f"Please use this command in the verification channel (<#{self.channel_id}>) or one of its threads.",
                ephemeral=True
            )

        if self.verify_attempts.get(interaction.user.id, 0) >= 5:
            await interaction.followup.send("Too many invalid attempts. Contact a moderator.", ephemeral=True)
            notify = await self._get_notify_channel(interaction.guild)
            if notify:
                await notify.send(f"⚠️ {interaction.user.mention} exceeded /verify limit.")
            return

        email = self.email_list.get(interaction.user.id)
        if not email:
            return await interaction.followup.send(
                "No email found. Please run `/email` first.",
                ephemeral=True
            )

        if await self.check_emails_file(interaction, email):
            return

        if self.token_list.get(interaction.user.id) != token:
            self.verify_attempts[interaction.user.id] = self.verify_attempts.get(interaction.user.id, 0) + 1
            return await interaction.followup.send("Invalid token. Please try again.", ephemeral=True)

        # ---------------- SUCCESS PATH ----------------
        # Assign verified role
        role = discord.utils.get(interaction.guild.roles, name=self.role)
        if not role:
            role = discord.utils.find(lambda r: str(r.id) == str(self.role), interaction.guild.roles)
        if role:
            await interaction.user.add_roles(role)

        # Remove lock/unverified role
        try:
            lock_role = interaction.guild.get_role(self.lock_role_id)
            if lock_role and lock_role in interaction.user.roles:
                await interaction.user.remove_roles(lock_role)
                print(f"🔓 Removed unverified role from {interaction.user.display_name}")
        except Exception as e:
            print(f"[WARN] Could not remove lock role: {e}")

        # Record locally
        try:
            with open(self.used_emails, "a") as f:
                hashed = self.bot.hashing.hash(email)
                display_name = self._discord_display_name(interaction.user)
                f.write(f"{interaction.user.id}:{display_name}:{hashed}\n")
        except Exception as e:
            print(f"[WARN] Failed writing used_emails: {e}")

        # Google Sheet logging
        if self.sheet:
            try:
                display_name = self._discord_display_name(interaction.user)
                timestamp = self._now_eastern_str()
                self.sheet.append_row([str(interaction.user.id), display_name, email, timestamp])
                print(f"Logged verification for {display_name} to Google Sheet.")
            except Exception as e:
                print(f"[WARN] Could not log to Google Sheet: {e}")

        # Clear token state
        self.token_list.pop(interaction.user.id, None)
        self.email_list.pop(interaction.user.id, None)

        # 1) Confirm to user FIRST (thread still exists)
        try:
            await interaction.followup.send("✅ You have been verified!", ephemeral=True)
        except Exception as e:
            print(f"[WARN] Could not send ephemeral confirmation: {e}")

        # 2) Admin log SECOND (robust)
        try:
            notify = await self._get_notify_channel(interaction.guild)
            if notify:
                await notify.send(
                    f"✅ **Verification complete:** {interaction.user.mention} verified with `{email}`"
                )
                print(f"📢 Sent verification log for {interaction.user.display_name}")
        except Exception as e:
            print(f"[WARN] Could not send verification log: {e}")

        # 3) Delete verification thread LAST (so it doesn't break followups/logging)
        try:
            if isinstance(interaction.channel, discord.Thread):
                await interaction.channel.delete(reason="User verified successfully")
                print(f"🗑️ Deleted verification thread for {interaction.user.display_name}")
        except Exception as e:
            print(f"[WARN] Could not delete verification thread: {e}")

    # ----------------------------------------------------------------------
    # /revoke (multi-admin + file + sheet sync)
    # ----------------------------------------------------------------------
    @app_commands.command(name="revoke", description="Admin only — revoke a user's verification globally.")
    @app_commands.describe(user="The user to revoke (mention or ID).")
    async def slash_revoke(self, interaction: discord.Interaction, user: discord.User):
        # Permission check
        if interaction.user.id not in self.admin_ids:
            return await interaction.response.send_message(
                "You do not have permission to run this command.",
                ephemeral=True
            )

        # Local file cleanup (remove any line starting with "<user_id>:")
        try:
            if os.path.exists(self.used_emails):
                with open(self.used_emails, "r") as f:
                    lines = f.readlines()

                new_lines = []
                removed = False
                for line in lines:
                    if not line.strip():
                        continue
                    parts = line.strip().split(":")
                    if parts and parts[0] == str(user.id):
                        removed = True
                        continue
                    new_lines.append(line)

                with open(self.used_emails, "w") as f:
                    f.writelines(new_lines)

                if removed:
                    print(f"Removed {user.name} ({user.id}) from used_emails.txt")
                else:
                    print(f"No entry found for {user.name} in used_emails.txt")
            else:
                print("used_emails.txt not found — skipping local cleanup.")
        except Exception as e:
            print(f"[WARN] Failed to update used_emails.txt: {e}")

        # Google Sheet cleanup
        if not self.sheet:
            return await interaction.response.send_message("Google Sheet not available.", ephemeral=True)

        try:
            all_records = self.sheet.get_all_values()
            if not all_records or len(all_records) < 2:
                return await interaction.response.send_message("No records found in sheet.", ephemeral=True)

            header = all_records[0]
            id_col = header.index("Discord ID") if "Discord ID" in header else 0

            row_to_delete = None
            for i, row in enumerate(all_records[1:], start=2):
                if str(row[id_col]) == str(user.id):
                    row_to_delete = i
                    break

            if not row_to_delete:
                return await interaction.response.send_message("User not found in Google Sheet.", ephemeral=True)

            self.sheet.delete_rows(row_to_delete)
            print(f"Removed {user.name} ({user.id}) from Google Sheet.")
        except Exception as e:
            print(f"[WARN] Failed to remove from Google Sheet: {e}")
            return await interaction.response.send_message(f"Error updating Google Sheet: {e}", ephemeral=True)

        # Role cleanup (remove verified role if present)
        try:
            member = interaction.guild.get_member(user.id)
            if member:
                verified_role = discord.utils.get(interaction.guild.roles, name=self.role)
                if not verified_role:
                    verified_role = discord.utils.find(lambda r: str(r.id) == str(self.role), interaction.guild.roles)

                if verified_role and verified_role in member.roles:
                    await member.remove_roles(verified_role)
                    print(f"Removed verified role from {member.display_name}")

                # Optionally re-apply lock role (if they are still in server)
                lock_role = interaction.guild.get_role(self.lock_role_id)
                if lock_role and lock_role not in member.roles:
                    await member.add_roles(lock_role)
        except Exception as e:
            print(f"[WARN] Could not update roles on revoke: {e}")

        # Confirmation
        await interaction.response.send_message(
            f"Revoked verification for {user.mention}.\n"
            f"Removed from both the Google Sheet and local file.",
            ephemeral=True
        )

        # Log to admin channel
        notify = await self._get_notify_channel(interaction.guild)
        if notify:
            await notify.send(f"🗑️ **Verification revoked:** {user.mention} by {interaction.user.mention}")

    # ----------------------------------------------------------------------
    # Auto-verify returning members OR assign verification lock + create thread
    # ----------------------------------------------------------------------
    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        try:
            if member.bot:
                return

            guild = member.guild
            verify_channel = guild.get_channel(self.channel_id)

            # Assign the verification lock role first
            lock_role = guild.get_role(self.lock_role_id)
            if lock_role and lock_role not in member.roles:
                await member.add_roles(lock_role)
                print(f"🔒 Assigned verification lock role to {member.display_name}")

            # Check if user already verified in file or sheet (auto-reverify)
            verified = False

            # Local file check
            try:
                if os.path.exists(self.used_emails):
                    with open(self.used_emails, "r") as f:
                        for line in f:
                            if line.strip().startswith(str(member.id) + ":"):
                                verified = True
                                break
            except Exception as e:
                print(f"[WARN] used_emails file check failed: {e}")

            # Sheet check if not verified by file
            if not verified and self.sheet:
                try:
                    all_records = self.sheet.get_all_values()
                    if any(str(row[0]) == str(member.id) for row in all_records[1:]):
                        verified = True
                except Exception as e:
                    print(f"[WARN] Google Sheet check failed on rejoin: {e}")

            # Auto-reverify returning members
            if verified:
                verified_role = discord.utils.get(guild.roles, name=self.role)
                if not verified_role:
                    verified_role = discord.utils.find(lambda r: str(r.id) == str(self.role), guild.roles)

                if verified_role and verified_role not in member.roles:
                    await member.add_roles(verified_role)

                # Remove lock role (since they are already verified)
                if lock_role and lock_role in member.roles:
                    await member.remove_roles(lock_role)

                print(f"✅ Auto-reverified returning member {member.display_name}")

                notify = await self._get_notify_channel(guild)
                if notify:
                    await notify.send(f"♻️ **Auto-reverified:** {member.mention} (previously verified)")
                return

            # Create private verification thread for new (unverified) members
            if verify_channel:
                try:
                    thread = await verify_channel.create_thread(
                        name=f"verify-{member.display_name}",
                        type=discord.ChannelType.private_thread,
                        reason="Private verification thread for new member"
                    )
                    await thread.add_user(member)

                    await thread.send(
                        f"Hi {member.mention}, welcome to the server.\n\n"
                        f"To gain full access:\n"
                        f"1) Set your nickname to your real name (First Last).\n"
                        f"2) Use `/email yourNID@ucf.edu` in this thread to get a verification token.\n"
                        f"3) Use `/verify ####` here once you receive the email.\n\n"
                        f"Only you and the bot can see this thread."
                    )
                    print(f"🧵 Created private verification thread for {member.display_name}")
                except Exception as e:
                    print(f"[WARN] Could not create private thread for {member.display_name}: {e}")
                    # Fallback message if threads unavailable
                    try:
                        await verify_channel.send(
                            f"{member.mention}, please verify your UCF email using `/email yourNID@ucf.edu`."
                        )
                    except Exception as e2:
                        print(f"[WARN] Could not send fallback message: {e2}")

        except Exception as e:
            print(f"[WARN] on_member_join setup failed: {e}")

    # ----------------------------------------------------------------------
    # UTIL
    # ----------------------------------------------------------------------
    async def check_emails_file(self, interaction: discord.Interaction, email: str):
        """
        Blocks re-use of an email that has already been used (hashed in used_emails.txt).
        """
        try:
            with open(self.used_emails, "r") as f:
                for line in f:
                    parts = line.strip().split(":")
                    if not parts:
                        continue
                    hashed = parts[-1]
                    if self.bot.hashing.check_hash(email.lower(), hashed):
                        if self.ticket_loaded:
                            ticket_channel = interaction.guild.get_channel(self.ticket_id)
                            msg = (
                                "That email has already been used. If you believe this is an error, "
                                f"please open a ticket in {ticket_channel.mention}."
                            )
                        else:
                            admin = await self.bot.fetch_user(self.admin_id)
                            msg = f"That email has already been used. Contact {admin.mention} for help."
                        await interaction.followup.send(msg, ephemeral=True)
                        return True
            return False
        except FileNotFoundError:
            return False
        except Exception as e:
            print(f"[WARN] check_emails_file error: {e}")
            return False


# ----------------------------------------------------------------------
# SYNC FIX (guild-level sync)
# ----------------------------------------------------------------------
async def setup(bot):
    cog = Verification(bot)
    await bot.add_cog(cog)
    try:
        guild = discord.Object(id=cog.guild_id)
        await bot.tree.sync(guild=guild)
        print(f"✅ Synced slash commands instantly for guild ID {cog.guild_id}")
        print("Loaded slash commands:", [c.name for c in bot.tree.get_commands(guild=guild)])
    except Exception as e:
        print(f"[WARN] Slash command sync failed: {e}")
