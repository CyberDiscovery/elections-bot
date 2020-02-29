import discord
from discord import Embed, Member, User
from discord.ext import commands
from json import load
import random
import urllib.request
import re
from electionsbot.constants import EMOJI_SERVER_ID


class ElectionCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.candidateData = load(open("testdata.json", "r"))
        self.candidates = {}

    @commands.Cog.listener()
    async def on_ready(self):
        # Load up all the relevant candidates!
        self.backendGuild = self.bot.get_guild(EMOJI_SERVER_ID)
        for emoji in await self.backendGuild.fetch_emojis():
            if emoji.user == self.bot.user:
                await emoji.delete()
        for id, info in self.candidateData.items():
            candidate = Candidate(id)
            user = self.bot.get_user(int(id))
            if user:
                candidate.username = user.name + "#" + user.discriminator
                candidate.avatar = user.avatar_url
                emojiimage = await candidate.avatar.read()
                emojiname = re.sub(r'\W+', '', candidate.username.replace(" ", "_"))
                candidate.emoji = await self.backendGuild.create_custom_emoji(name=emojiname, image=emojiimage)
            else:
                candidate.username = info.get("username")
                candidate.avatar = info.get("avatar")
                emojiimage = urllib.request.urlopen(url=candidate.avatar)
                emojiname = re.sub(r'\W+', '', candidate.username.replace(" ", "_"))
                candidate.emoji = await self.backendGuild.create_custom_emoji(name=emojiname, image=emojiimage)
            candidate.campaign = info.get("campaign")
            self.candidates[int(id)] = candidate
        print(self.candidates)

    def getCandidate(self, candidateID):
        return self.candidates.get(candidateID)

    def getAllCandidates(self):
        candidates = list(self.candidates.values())
        print(candidates)
        random.shuffle(candidates)  # Randomise the order each time for neutrality.
        return candidates

    @commands.command()
    async def candidateInfo(self, ctx, candidate: User):
        info = self.candidates.get(int(candidate.id))
        print(info)
        if not info:
            await ctx.send("We couldn't find any information on that candidate! They may not be running, or we might"
                           " have identified the wrong user (We think you're asking about"
                           f" `{candidate.name + '#' + candidate.discriminator}`).")
        else:
            await ctx.send(embed=info.getEmbed())

    @commands.command()
    async def candidateList(self, ctx):
        names = [candidate.username for candidate in self.getAllCandidates()]
        print(names)
        await ctx.send("In a random order, the candidates currently standing are: \n" + "\n".join(names))

    @commands.command()
    async def vote(self, ctx):
        if ctx.channel.guild:
            await ctx.message.author.send("")
            await ctx.send("Voting takes place in DMs - I've sent you one explaining the process just now!")

    @commands.command()
    async def voteDM(self, ctx):
        message = await ctx.send("Click on the reactions representing the users you wish to vote for. Once you're"
                           " done, react with a ✅ to confirm. **Remember, you can only vote for two candidates, and"
                           " you can't change your mind once you confirm!**"
                           "\n*This prompt will expire in 5 minutes.*")
        for emoji in [candidate.emoji for candidate in self.getAllCandidates()]:
            await message.add_reaction(emoji)
        await message.add_reaction("✅")


class Candidate:
    def __init__(self, id, username=None, campaign=None, avatar=None):
        self.id = id
        self.username = username
        self.campaign = campaign
        self.avatar = avatar
        self.emoji = None

    def getEmbed(self):
        output = Embed()
        output.set_author(name=self.username, icon_url=self.avatar)
        output.description = self.campaign
        output.set_footer(text="To vote for this candidate, do XYZ.")
        return output


def setup(bot: commands.Bot):
    bot.add_cog(ElectionCog(bot))
