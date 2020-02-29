"""Initialise electionsbot as a package for poetry."""

from .bot import bot
from .constants import BOT_TOKEN


def main():
    """Entry point for poetry script."""
    bot.run(BOT_TOKEN)
