import random
import re
import urllib.error
import urllib.request
from asyncio import sleep
from datetime import datetime
from json import load

import asyncpg
import discord
from discord import Embed, User
from discord.ext import commands
from electionsbot.constants import DTB_ROLE_ID, EMOJI_SERVER_ID, LEVEL_ROLE_ID, MUTED_ROLE_ID, PostgreSQL,\
    ROOT_ROLE_ID, VOTE_SERVER_ID


async def connectPostgres():
    connection = await asyncpg.connect(
        host=PostgreSQL.PGHOST,
        port=PostgreSQL.PGPORT,
        user=PostgreSQL.PGUSER,
        password=PostgreSQL.PGPASSWORD,
        database=PostgreSQL.PGDATABASE,
    )
    await connection.execute(
        "CREATE TABLE IF NOT EXISTS votes \
        (voter_id bigint PRIMARY KEY, vote_1 bigint, vote_2 bigint, datetime timestamp)"
    )
    return connection


class ElectionCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        data = load(open("electionsbot/applications.json", "r", encoding="UTF-8"))
        self.candidateData = data["candidates"]
        self.candidates = {}
        self.voteSessions = {}
        # CONFIG SETTINGS
        self.CHOICE_MINIMUM = 2
        self.CHOICE_MAXIMUM = 2
        self.ready = False
        self.START_TIME = datetime.utcfromtimestamp(data["starttime"])
        self.END_TIME = datetime.utcfromtimestamp(data["endtime"])
        self.CREATION_CUTOFF = datetime.utcfromtimestamp(data["creationcutoff"])
        # This will be automatically disabled if the number of candidates reaches 20.
        self.REACTION_INTERFACE = False

    @commands.Cog.listener()
    async def on_ready(self):
        # Load up all the relevant candidates!
        self.backendGuild = self.bot.get_guild(EMOJI_SERVER_ID)
        emoji = await self.backendGuild.fetch_emojis()
        for id, info in self.candidateData.items():
            candidate = Candidate(id)
            user = self.bot.get_user(int(id))
            if user:
                candidate.discorduser = user
                candidate.username = user.name + "#" + user.discriminator
                candidate.avatar = user.avatar_url_as(format='png', size=32)
                emojiimage = await candidate.avatar.read()
                emojiname = re.sub(r"\W+", "", (user.name[:28] + user.discriminator).replace(" ", "_"))
                for x in emoji:
                    if x.name == emojiname:
                        candidate.emoji = x
                        break
                else:
                    candidate.emoji = await self.backendGuild.create_custom_emoji(
                        name=emojiname, image=emojiimage
                    )
            else:
                candidate.username = info.get("username")
                candidate.avatar = info.get("avatar")
                try:
                    if candidate.avatar:
                        emojiimage = urllib.request.urlopen(url=candidate.avatar)
                    else:
                        emojiimage = urllib.request.urlopen(url="https://cdn.beano.dev/question-mark.png")
                except urllib.error.HTTPError:
                    emojiimage = urllib.request.urlopen(
                        url="https://cdn.beano.dev/question-mark.png"
                    )
                emojiname = re.sub(r"\W+", "", candidate.username.replace(" ", "_"))
                for x in emoji:
                    if x.name == emojiname:
                        candidate.emoji = x
                        break
                else:
                    candidate.emoji = await self.backendGuild.create_custom_emoji(
                        name=emojiname, image=emojiimage.read()
                    )
            candidate.campaign = info.get("campaign")
            self.candidates[int(id)] = candidate
        print(self.candidates)
        if len(self.candidates) >= 20:
            self.REACTION_INTERFACE = False
        self.ready = True

    def getCandidate(self, candidateID):
        return self.candidates.get(int(candidateID))

    def getCandidateFromName(self, candidateName):
        for c in self.candidates.values():
            if c.username == candidateName:
                return c
        return None

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

    @commands.command(aliases=["list"])
    async def candidateList(self, ctx):
        names = [
            str(candidate.emoji) + " " + candidate.username
            for candidate in self.getAllCandidates()
        ]
        await ctx.send(
            f"In a random order, the candidates currently standing are:\n"
            f"{chr(10).join(names)}"
        )

    @commands.check_any(commands.has_role(ROOT_ROLE_ID), commands.dm_only())
    @commands.command(aliases=["listAll"])
    async def allCandidateDetails(self, ctx):
        for candidate in self.getAllCandidates():
            await ctx.send(embed=candidate.getEmbed())

    @commands.has_role(ROOT_ROLE_ID)
    @commands.command(aliases=["electiontotals"])
    async def viewTotals(self, ctx):
        votes = await (await connectPostgres()).fetch(
            """select candidate, count(*) as votecount from (
        select vote_1 as candidate from votes
        union all select vote_2 from votes
    ) t1 group by candidate order by votecount DESC"""
        )
        out = ""
        for candidateid, count in votes:
            candidate = self.getCandidate(candidateid)
            out += f"{str(candidate.emoji)} {candidate.username}[{candidate.id}]: {count}\n"
        await ctx.send(
            f"The following is each member, followed by their number of votes.\n {out}"
        )

    # @commands.has_role(ROOT_ROLE_ID)
    @commands.command(aliases=["myvote"])
    async def viewMyVote(self, ctx):
        if not isinstance(ctx.channel, discord.DMChannel):
            return await ctx.channel.send("You can only use this command in DMs.")
        votes = await (await connectPostgres()).fetch(
            "SELECT voter_id, vote_1, vote_2, datetime FROM votes WHERE voter_id=$1",
            ctx.author.id,
        )
        if len(votes) > 0:
            vote = votes[0]
            chosen = [vote[1], vote[2]]
            candidates = [c for c in self.getAllCandidates() if int(c.id) in chosen]
            names = [
                str(candidate.emoji) + " " + candidate.username
                for candidate in candidates
            ]
            return await ctx.send("You voted for: \n" + chr(10).join(names))
        else:
            return await ctx.send("You haven't voted yet!")

    @commands.command(aliases=["start"])
    async def vote(self, ctx):
        if not self.ready:
            return await ctx.send("I'm just getting ready, hold on!")
        if not isinstance(ctx.channel, discord.DMChannel):
            return await ctx.send(
                "You can only use this command in DMs.", delete_after=20
            )
        if self.START_TIME > datetime.utcnow() or self.END_TIME < datetime.utcnow():
            return await ctx.send("Voting is currently closed.")
        if self.CREATION_CUTOFF < ctx.author.created_at:
            return await ctx.send(
                "This account was created after the cutoff, and is therefore not eligible to vote."
            )
        guild = self.bot.get_guild(VOTE_SERVER_ID)
        member = guild.get_member(ctx.author.id)
        # If the member exists on the server, the user has a role equal to or greater than the level 5 role in list
        # OR has Death To Bots; and Muted isn't the greatest role, continue, else return a message and abort vote.
        if not (member and (guild.get_role(LEVEL_ROLE_ID) <= member.top_role or guild.get_role(DTB_ROLE_ID) in
                            member.roles) and not guild.get_role(MUTED_ROLE_ID) == member.top_role):
            return await ctx.send(
                "In order to be eligible to vote, you must have reached at least Mee6 Level 5, "
                "and not currently be muted."
            )
        if (
            len(
                await (await connectPostgres()).fetch(
                    "SELECT voter_id FROM votes WHERE voter_id=$1", ctx.author.id
                )
            ) > 0
        ):
            return await ctx.send("You have already voted!")
        currentSession = self.voteSessions.get(ctx.author.id)
        if currentSession and not currentSession.hasTimedOut():
            return await ctx.send(
                "You already have an active voting session! Please use that, or wait for it to expire."
            )
        # Check to see if the person has already voted
        self.voteSessions[ctx.author.id] = VoteSession(user=ctx.author, timeout=300)

        if self.REACTION_INTERFACE:
            message = await ctx.send(
                "Click on the reactions representing the users you wish to vote for. Once you're "
                "done, react with a ✅ to confirm. If you need more time to decide, just ignore this message.\n\n"
                "**Remember, you can only vote for exactly two candidates, and "
                "you can't change your mind once you confirm!**\n\n"
                "*This prompt will expire in 5 minutes.*"
            )
            for emoji in [candidate.emoji for candidate in self.getAllCandidates()]:
                await message.add_reaction(emoji)
            self.voteSessions[ctx.author.id].setMessage(message)
            await message.add_reaction("✅")
        else:
            names = [
                str(candidate.emoji) + " " + candidate.username
                for candidate in self.getAllCandidates()
            ]
            message = await ctx.send(
                "Run the `:choose <candidate>` command, specifying the Discord Name of the user you wish to "
                "vote for; and repeat this for each choice you wish to make.\n"
                "If you want to cancel a choice, use `unchoose <candidate>`. \nOnce you're "
                "done, run the `confirm` command to confirm. To view a candidate's statement, use "
                "`candidate <candidate>`, or `listall` if you want them all at once."
                " If you need more time to decide, just ignore this message.\n\n"
                "**Remember, you can only vote for exactly two candidates, and"
                " you can't change your mind once you confirm!**\n\n"
                "As a reminder, in a random order, the candidates currently standing are:\n"
                f"**{chr(10).join(names)}**\n\n"
                "*This session will expire in 5 minutes.*"
            )

    @commands.command(aliases=["lock", "submit"])
    async def confirm(self, ctx):
        await self.confirm_callback(ctx.channel, ctx.author)

    async def confirm_callback(self, channel, author):
        if not self.ready:
            return await channel.send("I'm just getting ready, hold on!")
        if not isinstance(channel, discord.DMChannel):
            return await channel.send(
                "You can only use this command in DMs.", delete_after=20
            )
        voteSession = self.voteSessions.get(author.id)
        if not voteSession:
            return await author.send("You don't have a vote session active to confirm.")
        user = author
        chosenCandidates = voteSession.choices
        await user.send(
            f"You are about to vote for the following candidates:\n** "
            f'{chr(10).join([str(c.emoji) + " " + c.username for c in chosenCandidates])}**'
        )
        if len(chosenCandidates) > self.CHOICE_MAXIMUM:
            return await user.send(
                f"""You've selected too many candidates. You can only select a maximum of {self.CHOICE_MAXIMUM} \
                candidates.
                Please modify your choices, and confirm again once done."""
            )
        if len(chosenCandidates) < self.CHOICE_MINIMUM:
            return await user.send(
                f"""You've selected too few candidates! You need to select a minimum of {self.CHOICE_MINIMUM} \
                candidates.
                Please modify your choices, and confirm again once done."""
            )
        else:
            m = await user.send(
                "Are you sure you wish to vote this way? React with a ✅ to finalise, or a 🚫 to cancel.\n"
                "*This prompt will expire in 90 seconds. Reactions will appear after 5 seconds.*"
            )
            self.voteSessions[user.id].setMessage(m)
            self.voteSessions[user.id].confirm()
            self.voteSessions[user.id].setTimeout(95)

            await sleep(5)
            await m.add_reaction("✅")
            await m.add_reaction("🚫")

    @commands.command(aliases=["info", "candidate"])
    async def candidateInfo(self, ctx, *, candidate: User):
        info = self.candidates.get(int(candidate.id))
        print(info)
        if not info:
            await ctx.send(
                "We couldn't find any information on that candidate! They may not be running, or we might "
                "have identified the wrong user (We think you're asking about "
                f"`{candidate.name + '#' + candidate.discriminator}`)."
            )
        else:
            await ctx.send(embed=info.getEmbed())

    @commands.command(aliases=["pick", "select"])
    async def choose(self, ctx, *, candidate: User):
        if not isinstance(ctx.channel, discord.DMChannel):
            await ctx.message.delete()
            return await ctx.send(
                "You can only use this command in DMs.", delete_after=20
            )
        info = self.candidates.get(int(candidate.id))
        voteSession = self.voteSessions.get(ctx.author.id)
        if not voteSession:
            return await ctx.send(
                "You must have an active votesession to make a choice. Use the vote "
                "command to start a votesession."
            )
        if voteSession.state != "PICK":
            return await ctx.send(
                "You cannot modify your choices if you are confirming them."
            )
        if not info:
            await ctx.send(
                "We couldn't find that candidate! (We think you're asking about "
                f"`{candidate.name + '#' + candidate.discriminator}`)."
            )
        else:
            voteSession.addChoice(info)
            await ctx.send(f"Added {info.username} as a choice.")

    @commands.command(aliases=["unpick", "deselect"])
    async def unchoose(self, ctx, *, candidate: User):
        if not isinstance(ctx.channel, discord.DMChannel):
            await ctx.message.delete()
            return await ctx.send(
                "You can only use this command in DMs.", delete_after=20
            )
        info = self.candidates.get(int(candidate.id))
        voteSession = self.voteSessions.get(ctx.author.id)
        if not voteSession:
            return await ctx.send(
                "You must have an active votesession to make a choice. Use the vote "
                "command to start a votesession."
            )
        if voteSession.state != "PICK":
            return await ctx.send(
                "You cannot modify your choices if you are confirming them."
            )
        if not info:
            await ctx.send(
                "We couldn't find that candidate! (We think you're asking about "
                f"`{candidate.name + '#' + candidate.discriminator}`)."
            )
        else:
            voteSession.removeChoice(info)
            await ctx.send(f"Removed {info.username} as a choice.")

    @commands.has_role(ROOT_ROLE_ID)
    @commands.command()
    async def clearvote(self, ctx, voter: User):
        await (await connectPostgres()).execute(
            "DELETE FROM votes WHERE voter_id=$1", voter.id
        )
        await ctx.send(f"{voter.mention}'s votes have been cleared")
        return await voter.send(
            f"Your votes were cleared by <@{ctx.author.id}> - you can now place a new set."
        )

    @commands.Cog.listener()
    async def on_reaction_add(self, reaction, user):
        """Reaction interface - Suited for under 20 members"""
        voteSession = self.voteSessions.get(user.id)
        if not voteSession or not self.ready:
            return
        if voteSession.message.id != reaction.message.id:
            return
        if (
            reaction.emoji == "✅" and not voteSession.hasTimedOut() and voteSession.state == "PICK"
        ):
            voteSession.clearChoice()
            reactions = reaction.message.reactions
            for reaction in reactions:
                if user in await reaction.users().flatten():
                    choice = self.getCandidateFromEmoji(reaction.emoji)
                    if choice:
                        voteSession.addChoice(choice)
            await self.confirm_callback(reaction.channel, user)
        elif not voteSession.hasTimedOut() and voteSession.state == "CONFIRM":
            if reaction.emoji == "✅":
                # Votes have been confirmed. Go for it!
                await self.voteSessions[user.id].commit()
                # Committed the vote, now delete the session
                del self.voteSessions[user.id]
                await user.send("Your vote has been confirmed! Thank you :)")
            elif reaction.emoji == "🚫":
                # Vote was canceled, just delete the session without committing.
                del self.voteSessions[user.id]
                await user.send(
                    "OK, I've canceled the voting session. When you've made up your mind, use the command again."
                )
        elif voteSession.hasTimedOut():
            del self.voteSessions[user.id]
            await user.send(
                "The voting session you had has now expired; you need to start a new one."
            )

    @commands.Cog.listener()
    async def on_user_update(self, before, after):
        # Check if the user is a candidate
        if after.id in self.candidates.keys():
            # Update the relevant candidate information
            candidate = self.getCandidate(after.id)
            user = after
            await self.backendGuild.fetch_emojis()
            candidate.discorduser = after
            candidate.username = user.name + "#" + user.discriminator
            candidate.avatar = user.avatar_url.avatar_url_as(format='png', size=32)
            emojiimage = await candidate.avatar.read()
            emojiname = re.sub(r"\W+", "", candidate.username.replace(" ", "_"))
            await candidate.emoji.delete()
            candidate.emoji = await self.backendGuild.create_custom_emoji(
                name=emojiname, image=emojiimage
            )


class Candidate:
    def __init__(self, id, username=None, campaign=None, avatar=None):
        self.id = id
        self.username = username
        self.campaign = campaign
        self.avatar = avatar
        self.emoji = None
        self.discorduser = None

    def getEmbed(self):
        output = Embed()
        output.colour = 0x00daff
        if self.avatar:
            output.set_author(name=self.username, icon_url=self.avatar)
        else:
            output.set_author(name=self.username)
        output.description = self.campaign
        output.set_footer(text=f"")
        return output


class VoteSession:
    def __init__(self, user, timeout):
        self.user = user
        self.exp = datetime.utcnow().timestamp() + timeout
        self.state = "PICK"
        self.choices = []
        # CONFIG
        self.MAX_CHOICES = 2

    def setMessage(self, msg):
        self.message = msg

    def setTimeout(self, secs):
        self.exp = datetime.utcnow().timestamp() + secs

    def hasTimedOut(self):
        return self.exp < datetime.utcnow().timestamp()

    def addChoice(self, choice):
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

    async def commit(self):
        await (await connectPostgres()).execute(
            "INSERT INTO votes(voter_id, vote_1, vote_2, datetime) VALUES($1, $2, $3, $4) ON CONFLICT DO NOTHING;",
            self.user.id,
            int(self.choices[0].id),
            int(self.choices[1].id),
            datetime.now(),
        )


def setup(bot: commands.Bot):
    bot.add_cog(ElectionCog(bot))
