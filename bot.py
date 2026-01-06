import os
import os.path as osp
import random
import time
import asyncio

import discord
from discord.ext import commands

from util.data.hashing import Hashing

print("Starting...")

# --- Load .env if present ---
try:
    from dotenv import load_dotenv
    load_dotenv()
    print("Loaded .env")
except Exception as e:
    print(f"[WARN] dotenv not loaded (this is OK if you set env vars another way): {e}")

current_dir = osp.dirname(__file__)
data_path = "data"

extensions = ["background", "errors", "misc", "reactor", "utility", "verification"]

intents = discord.Intents.default()
intents.guilds = True
intents.members = True
intents.messages = True
intents.reactions = True

do_run = True

bot_token = None
used_emails = None
bot_key = None
hash_key = None

try:
    print("Loading config...")

    bot_token = os.environ["token"]
    bot_key = os.environ["key"]
    used_emails = os.environ["used_emails"]
    hash_key = os.environ["hash_key"]

    do_run = True
except KeyError as e:
    print(f"Config error.\n\tKey Not Loaded: {e}")
    do_run = False

# Seed RNG
random.seed(int(time.time()))

# Only build paths if config loaded successfully
if do_run:
    used_emails = osp.join(current_dir, data_path, used_emails)


def prefix(bot, message):
    pfx = bot_key
    if str(message.content).startswith(f"{pfx} "):
        pfx = f"{pfx} "
    return pfx


bot = commands.Bot(command_prefix=prefix, intents=intents)

# Only set hashing if config loaded
if do_run:
    hashing = Hashing(hash_key)
    setattr(bot, "current_dir", current_dir)
    setattr(bot, "data_path", data_path)
    setattr(bot, "hashing", hashing)

bot.remove_command("help")


@bot.event
async def on_ready():
    await bot.change_presence(
        activity=discord.Activity(
            name=f"{bot_key}vhelp for verification help",
            type=discord.ActivityType.watching,
        )
    )
    print(f"We have logged in as {bot.user}")


@bot.event
async def on_message(message):
    if message.author == bot.user:
        return
    await bot.process_commands(message)


async def main():
    count = 0
    for extension in extensions:
        try:
            await bot.load_extension(f"cogs.{extension}")
            print(f"Cog | Loaded {extension}")
            count += 1
        except Exception as error:
            print(f"{extension} cannot be loaded. \n\t[{error}]")

    print(f"Loaded {count}/{len(extensions)} cogs")

    if do_run:
        await bot.start(bot_token)
    else:
        print("Startup aborted (missing config).")


if __name__ == "__main__":
    asyncio.run(main())

