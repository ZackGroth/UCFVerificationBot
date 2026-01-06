import os
import os.path as osp
import random
import time
import asyncio
import discord
from discord import app_commands
from discord.ext import commands
from util.data.hashing import Hashing
from dotenv import load_dotenv

load_dotenv()
print("Starting...")

# ---------------------------------------------------------------------------
# CONFIG AND BASIC SETUP
# ---------------------------------------------------------------------------

current_dir = osp.dirname(__file__)
data_path = "data"
extensions = ["verification"]  # you can add others later once converted

intents = discord.Intents.default()
intents.guilds = True
intents.members = True

do_run = True
bot_token = bot_key = used_emails = hash_key = None

try:
    print("Loading config...")
    bot_token = os.environ["token"]
    used_emails = os.environ["used_emails"]
    hash_key = os.environ["hash_key"]
except KeyError as e:
    print(f"Config error.\n\tKey Not Loaded: {e}")
    do_run = False

random.seed(int(time.time()))
used_emails = osp.join(current_dir, data_path, used_emails)

# ---------------------------------------------------------------------------
# BOT INITIALIZATION (no prefix commands)
# ---------------------------------------------------------------------------

class VerificationBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix=None, intents=intents)
        self.current_dir = current_dir
        self.data_path = data_path
        self.hashing = Hashing(hash_key)

    async def setup_hook(self):
        for extension in extensions:
            try:
                await self.load_extension(f"cogs.{extension}")
                print(f"Cog | Loaded {extension}")
            except Exception as e:
                print(f"{extension} failed to load: {e}")
        try:
            synced = await self.tree.sync()
            print(f"✅ Synced {len(synced)} slash commands globally.")
        except Exception as e:
            print(f"❌ Slash-command sync failed: {e}")

bot = VerificationBot()

# ---------------------------------------------------------------------------
# EVENTS
# ---------------------------------------------------------------------------

@bot.event
async def on_ready():
    await bot.change_presence(activity=discord.Activity(
        name="/email to verify your UCF account",
        type=discord.ActivityType.watching
    ))
    print(f"We have logged in as {bot.user}")

# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------

async def main():
    if do_run:
        async with bot:
            await bot.start(bot_token)
    else:
        print("Startup aborted.")

if __name__ == "__main__":
    asyncio.run(main())
