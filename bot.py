import os
import discord
from discord.ext import commands
from dotenv import load_dotenv

# ------------------------------------------------------------
# Load environment variables
# ------------------------------------------------------------
load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")
if not TOKEN:
    raise RuntimeError("DISCORD_TOKEN is not set in the environment.")

# ------------------------------------------------------------
# Intents
# ------------------------------------------------------------
intents = discord.Intents.default()
intents.members = True          # REQUIRED for on_member_join
intents.guilds = True
intents.messages = True

# ------------------------------------------------------------
# Bot class
# ------------------------------------------------------------
class VerificationBot(commands.Bot):
    def __init__(self):
        super().__init__(
            command_prefix="!",
            intents=intents,
            help_command=None
        )

        # Paths used by verification.py
        self.current_dir = os.path.dirname(os.path.abspath(__file__))
        self.data_path = "data"

        # Hashing helper (required by verification.py)
        from util.hashing import Hashing
        self.hashing = Hashing()

    async def setup_hook(self):
        """
        Called once on startup.
        Loads cogs and syncs commands.
        """
        print("🔧 Loading cogs...")

        await self.load_extension("cogs.verification")

        print("✅ Cogs loaded.")

    async def on_ready(self):
        print("====================================")
        print(f"🤖 Logged in as: {self.user}")
        print(f"🆔 Bot ID: {self.user.id}")
        print(f"🌐 Connected to {len(self.guilds)} guild(s)")
        print("====================================")

# ------------------------------------------------------------
# Run bot
# ------------------------------------------------------------
def main():
    bot = VerificationBot()
    bot.run(TOKEN)

if __name__ == "__main__":
    main()
