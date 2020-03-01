import discord
from discord import Embed, Member, User
from discord.ext import commands
from json import load
from asyncio import sleep
from ..constants import EMOJI_SERVER_ID
import random
import urllib.request
import re
import time
import asyncpg
from electionsbot.constants import EMOJI_SERVER_ID, PostgreSQL


class ElectionCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.candidateData = load(open("testdata.json", "r"))
        self.candidates = {}
        self.voteSessions = {}
        # CONFIG SETTINGS
        self.CHOICE_MAXIMUM = 2
        self.ready = False





    @commands.Cog.listener()
    async def on_ready(self):
        # Load up all the relevant candidates!
        self.backendGuild = self.bot.get_guild(EMOJI_SERVER_ID)
        emoji = await self.backendGuild.fetch_emojis()
        for id, info in self.candidateData.items():
            candidate = Candidate(id)
            user = self.bot.get_user(int(id))
            if user:
                candidate.username = user.name + "#" + user.discriminator
                candidate.avatar = user.avatar_url
                emojiimage = await candidate.avatar.read()
                emojiname = re.sub(r'\W+', '', candidate.username.replace(" ","_"))
                for x in emoji:
                    if x.name == emojiname:
                        candidate.emoji = x
                        break
                else:
                    candidate.emoji = await self.backendGuild.create_custom_emoji(name=emojiname,image=emojiimage)
            else:
                candidate.username = info.get("username")
                candidate.avatar = info.get("avatar")
                emojiimage = urllib.request.urlopen(url=candidate.avatar)
                emojiname = re.sub(r'\W+', '', candidate.username.replace(" ", "_"))
                for x in emoji:
                    if x.name == emojiname:
                        candidate.emoji = x
                        break
                else:
                    candidate.emoji = await self.backendGuild.create_custom_emoji(name=emojiname, image=emojiimage)
            candidate.campaign = info.get("campaign")
            self.candidates[int(id)] = candidate
        print(self.candidates)
        self.ready = True

    def getCandidate(self, candidateID):
        return self.candidates.get(candidateID)

    def getCandidateFromEmoji(self, emoji):
        for c in self.candidates.values():
            if c.emoji == emoji:
                return c
        return None

    def getAllCandidates(self):
        candidates = list(self.candidates.values())
        print(candidates)
        random.shuffle(candidates)  # Randomise the order each time for neutrality.
        return candidates

    async def connectPostgres(self):
        connection = await asyncpg.connect(
            host=PostgreSQL.PGHOST,
            port=PostgreSQL.PGPORT,
            user=PostgreSQL.PGUSER,
            password=PostgreSQL.PGPASSWORD,
            database=PostgreSQL.PGDATABASE,
        )
        await connection.execute(
            "CREATE TABLE IF NOT EXISTS votes (voter_id bigint PRIMARY KEY, vote_1 bigint, vote_2 bigint)"
        )
        return connection

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
        if not self.ready:
            return await ctx.send(
                "I'm just getting ready, hold on!")
        if not isinstance(ctx.channel,discord.DMChannel):
            return await ctx.send(
                "You can only use this command in DMs.")
        if self.voteSessions.get(ctx.author.id):
            return await ctx.send("You already have an active voting session! Please use that, or wait for it to expire.")
        message = await ctx.send("Click on the reactions representing the users you wish to vote for. Once you're"
                            " done, react with a ✅ to confirm. If you need more time to decide, just ignore this message. \n"
                           "**Remember, you can only vote for two candidates, and"
                            " you can't change your mind once you confirm!**"
                           "\n*This prompt will expire in 5 minutes.*")
        self.voteSessions[ctx.author.id] = VoteSession(user=ctx.author,timeout=300)
        self.voteSessions[ctx.author.id].setMessage(message)
        for emoji in [candidate.emoji for candidate in self.getAllCandidates()]:
            await message.add_reaction(emoji)
        await message.add_reaction("✅")

    @commands.Cog.listener()
    async def on_reaction_add(self,reaction, user):
        voteSession = self.voteSessions.get(user.id)
        if not voteSession or not self.ready:
            return
        if voteSession.message.id != reaction.message.id:
            return
        if reaction.emoji == "✅" and not voteSession.hasTimedOut() and voteSession.state == "PICK":
            reactions = reaction.message.reactions
            print(reactions)
            chosenCandidates = voteSession.choices
            for reaction in reactions:
                if user in await reaction.users().flatten():
                    x = self.getCandidateFromEmoji(reaction.emoji)
                    if x:
                        voteSession.addChoice(x)
            chosenCandidates = voteSession.choices
            if len(chosenCandidates) > self.CHOICE_MAXIMUM:
                voteSession.clearChoice()
                return await user.send(f"You've selected too many candidates. You can only select a maximum of {self.CHOICE_MAXIMUM} candidates.\n"
                                 f"Please modify your choices, and retoggle the ✅ reaction once done.")
            if len(chosenCandidates) == 0:
                voteSession.clearChoice()
                return await user.send(
                    f"You've not chosen anyone! You need to select at least one candidate in order to vote.\n"
                    f"Please modify your choices, and retoggle the ✅ reaction once done.")
            else:
                txt = "You are about to vote for the following candidates:**\n" + "\n".join([c.username for c in chosenCandidates])
            m = await user.send(txt
                + "**\nAre you sure you wish to vote this way? React with a ✅ to finalise, or a 🚫 to cancel."
                  "\n*This prompt will expire in 90 seconds. Reactions will appear after 5 seconds.*")
            self.voteSessions[user.id].setMessage(m)
            self.voteSessions[user.id].confirm()
            self.voteSessions[user.id].setTimeout(95)

            await sleep(5)
            await m.add_reaction("✅")
            await m.add_reaction("⬜")
            await m.add_reaction("🚫")
        elif not voteSession.hasTimedOut() and voteSession.state == "CONFIRM":
            if reaction.emoji == "✅":
                # Votes have been confirmed. Go for it!
                self.voteSessions[user.id].commit()
                # Committed the vote, now delete the session
                del self.voteSessions[user.id]
                m = await user.send("Your vote has been confirmed! Thank you :)")
            elif reaction.emoji == "🚫":
                # Vote was canceled, just delete the session without committing.
                del self.voteSessions[user.id]
                m = await user.send("OK, I've canceled the voting session. When you've made up your mind, use the command again.")
        elif voteSession.hasTimedOut():
            del self.voteSessions[user.id]
            m = await user.send("The voting session you had has now expired; you need to start a new one.")


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

class VoteSession:
    def __init__(self, user, timeout):
        self.user = user
        self.exp = time.time() + timeout
        self.state = "PICK"
        self.choices = []
        # CONFIG
        self.MAX_CHOICES = 2

    def setMessage(self,msg):
        self.message = msg

    def setTimeout(self,secs):
        self.exp = time.time() + secs

    def hasTimedOut(self):
        return self.exp < time.time()

    def addChoice(self, choice):
        #len(self.choices) >= self.MAX_CHOICES or
        if self.state == "LOCK" or choice in self.choices:
            return False
        self.choices.append(choice)
        return True

    def removeChoice(self, choice):
        if self.state == "LOCK" or choice not in self.choices:
            return False
        self.choices.remove(choice)
        return True

    def clearChoice(self):
        self.choices = []
        return True

    def confirm(self):
        self.state = "CONFIRM"

    def lock(self):
        self.state = "LOCK"

    def commit(self):
        # TODO: Database Logic
        # Here, the votes chosen within this session should be committed to the database.
        # Useful: self.user gives the voting user; self.choices should give an array of Candidates chosen.
        connection = self.connectPostgres()


def setup(bot: commands.Bot):
    bot.add_cog(ElectionCog(bot))
