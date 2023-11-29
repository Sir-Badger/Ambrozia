import asyncio # asynchronous funcionality
import discord # basic discord functions
from discord.ext import commands, tasks # discord bot functions
import mysql.connector # mysql functions
import time # for time purposes
from apscheduler.schedulers.asyncio import AsyncIOScheduler # async scheduler
from apscheduler.triggers.cron import CronTrigger # timed trigger
import yaml
import rp_word_counter as rp # word counting

# ---------------------- general setup --------------------- #
print(f"Setting up...")

# global vars/constants
print(" - setting vars")
with open('stuff.txt', 'r') as file:
    conf = yaml.safe_load(file)

debug_mode=conf["debug"]

# scheduler things
sched = AsyncIOScheduler()

print(" - making dictionaries")
level_req={
        1:0,
        2:300,
        3:900,
        4:2700,
        5:6500,
        6:14000,
        7:23000,
        8:34000,
        9:48000,
        10:64000,
        11:85000,
        12:100000,
        13:120000,
        14:140000,
        15:165000,
        16:195000,
        17:225000,
        18:265000,
        19:305000,
        20:355000}
level_rates={
    1:2,
    2:2,
    3:2,
    4:2,
    5:2,
    6:2,
    7:2,
    8:2,
    9:1,
    10:1,
    11:1,
    12:1,
    13:1,
    14:1,
    15:1,
    16:1,
    17:1,
    18:1,
    19:1,
    20:1
}
rp_cap={
    1:3500,
    2:3500,
    3:3500,
    4:3500,
    5:7700,
    6:7700,
    7:7700,
    8:7700,
    9:14000,
    10:14000,
    11:14000,
    12:14000,
    13:17500,
    14:17500,
    15:17500,
    16:17500,
    17:17500,
    18:17500,
    19:17500,
    20:17500
}
default_account={
                "xp":0,
                "word_cache":0,
                "level":1,
                "lvl_notification":True,
                "weekly_xp":0
                }

# discord.py things
print(" - building bot")
intents = discord.Intents.default()
intents.message_content = True
QuestBored = commands.Bot(command_prefix="!", help_command=None, intents=intents) # bot object

# psycopg2 things
print(" - establishing connection to db")
database = mysql.connector.connect(
    host=conf["db_credentials"]["host"],
    port=conf["db_credentials"]["port"],
    user=conf["db_credentials"]["user"],
    password=conf["db_credentials"]["password"],
    database=conf["db_credentials"]["database"]
) # database object

# -------------------- define functions ------------------- #
def checkDMrole(member): # check whether the user has a DM role
    for role in member.roles: # loop through all the roles the member has
        if role.id in conf["mod_roles"]: # is the current role a DM role?
            return True # return true
    return False # if we loop through all roles without getting a DM role, return false

async def reset_weekly_cap():
    query = database.cursor() # query object
    print("====== Reseting word limits ======")
    t=time.time()

    query.execute(f"""UPDATE {conf['tables']['xp']} SET weekly_xp = 0""")
    database.commit()

    print(f"time to reset: {time.time()-t}")
    print("\n")
    query.close()

    await notify(msg="Reset XP limits")

async def notify_blaze_biweekly():
    await notify(msg="Crime reset, you nerd <@916415828151398420>")

def keep_alive():
    query = database.cursor()
    query.close()

async def proccess_msg_for_rp(msg): # processes msg in terms of rp
    global debug_mode

    if debug_mode: # Number of substrings in the message (Debug)
        num_of_stars=msg.content.count('*')
        num_of_quotes=msg.content.count('"')
        num_of_double_stars=msg.content.count('**')

    t0=time.time()
    
    word_count=rp.count(msg.content)

    await add_xp(word_count, msg.author, rp=True) # add xp to database

async def add_xp(xp, user, rp=False): # add xp to cache
    query = database.cursor() # query object
    query.execute(f"""SELECT * FROM {conf['tables']['xp']} WHERE account_id = {user.id}""") # lookup user
    
    account = query.fetchone() # access account info
    if account: # if the account already has logged xp
        if rp==True: # processing rp xp
            word_cache = account[2]
            overflow = (xp + word_cache) % level_rates[account[3]] # get overflow XP to be stored used cache next time
            xp = ( xp + word_cache - overflow) / level_rates[account[3]] # divide XP + cache (no overflow) & get the actual XP increase. Should only ever be whole numbers

            # weekly cap
            if xp + account[5] > rp_cap[account[3]]:
                if account[5]==rp_cap[account[3]]:
                    xp=0 # we've already reached cap
                else:
                    xp=rp_cap[account[3]] - account[5] # xp = remaining available xp

            query.execute(f"""UPDATE {conf['tables']['xp']}
SET xp = {account[1]+xp}, word_cache = {overflow}, weekly_xp = {account[5]+xp}
WHERE account_id = {user.id};""")
            
        else: # regular xp
            query.execute(f"""UPDATE {conf['tables']['xp']}
SET xp = {account[1]+xp}
WHERE account_id = {user.id};""")
        # commit to changes

        if account[1]+xp>=level_req[account[3]+1] and account[4]: # if they can lvl, notify them
            await notify([user], f"You have enough experience to level up to lvl **{account[3]+1}**! :sparkles:")
            query.execute(f"""UPDATE {conf['tables']['xp']}
                            SET lvl_notification = False
                            WHERE account_id = {account[0]}""") # set lvl lvl_notification to False
        database.commit() # commit to changes

        return f"{account[1]} -> {account[1]+xp}"
    else: # add account to database
        if rp==True: # processing rp xp
            overflow = xp % 4 # get overflow XP to be stored used cache next time
            xp = ( xp - overflow ) / 4 # divide valid xp by four, store overflow as cache

            add_account_to_db(id=user.id, xp=xp, word_cache=overflow) # add acc to db
        else: # regular xp
            add_account_to_db(id=user.id, xp=xp)
    query.close() # close querying

async def notify(member_list=[], msg="You have been notified!"): # notify role/member of something
    notify_channel = QuestBored.get_channel(918373129326317568) # set notify channel

    mention_text="> "
    for m in member_list: # loop through members to @
        mention_text+=m.mention+" "

    if mention_text != "> ":
        await notify_channel.send(f"{mention_text}\n{msg}") # mention
    else:
        await notify_channel.send(f"{mention_text}{msg}") # mention

# add account to db using default template
def add_account_to_db(id, xp=default_account['xp'], word_cache=default_account['word_cache'], level=default_account['level'], lvl_notification=default_account['lvl_notification']):
    query = database.cursor() # query object
    cap=rp_cap[level]
    query.execute(f"""INSERT INTO {conf['tables']['xp']}(account_id, xp, word_cache, level, lvl_notification, weekly_xp)
                VALUES ({id}, {xp}, {word_cache}, {level}, {lvl_notification}, 0)""")
    database.commit()
    query.close() # close querying

# --------------------- discord events -------------------- #
@QuestBored.event
async def on_ready(): # login msg + ping
    sched.start() #start scheduler
    sched.add_job(reset_weekly_cap, CronTrigger(day_of_week="0",minute="0",second="0",hour="0"))
    sched.add_job(notify_blaze_biweekly, CronTrigger(week="*/2", day_of_week="sat",minute="0",second="0",hour="0"))
    sched.add_job(keep_alive, CronTrigger(minute="0",second="0",hour="*/6"))

    print(f"""
-----------
Logged in as {QuestBored.user}
Ping {QuestBored.latency * 1000}ms
-----------
""")

@QuestBored.event
async def on_message(message): # recieves msg
    if message.author.bot == False: # ignore bot users
        t0=time.time()
        print(f"Message by {message.author} in {message.channel} ({message.channel.category}):\n{message.content}") # basic debug

        if message.content.startswith(QuestBored.command_prefix): # if the msg is a cmd
            await QuestBored.process_commands(message)
        elif message.channel.category.id in conf['rp_categories']: # the msg is not a cmd & is in an rp cathegory
            await proccess_msg_for_rp(message)
        print(f" - processing time: {time.time()-t0}")
        print("\n")

# ---------------------- discord cmds --------------------- #
# ---------- miscellaneous ---------- #
@QuestBored.command()
async def ping(ctx): # pong
    await ctx.send(f"Pong;\n{QuestBored.latency * 1000}ms")

# ------------ XP related ----------- #
@QuestBored.command(aliases=['Stats','info','Info'])
async def stats(ctx, member:discord.Member=None): # show member stats
    query = database.cursor() # query object
    if not member: # default to author
        member=ctx.author

    if member.bot==True: # msg for bots
        tembed=discord.Embed(
            title=f"**{member.name}'s stats:**",
            description=f"**This is a bot user, and therefore does not have any XP stats :v**",
            color=member.color
        ) # fancy emb
    else: # msg for players
        query.execute(f"""SELECT * FROM {conf['tables']['xp']} WHERE account_id = {member.id}""") # look up player in db

        account=query.fetchone() # get account info
        if account: # if the player is in the database
            query.execute(f"""SELECT account_id, xp FROM {conf['tables']['xp']} ORDER BY xp DESC""")
            ordered = query.fetchall()
            if account[3]==20:
                next_lvl=''
            else:
                next_lvl=f"({level_req[account[3]+1]-account[1]}xp remaining until lvl {account[3]+1})\n"

            tembed=discord.Embed(
                title=f"**{member.name}'s stats:**",
                description=f"**Level:** `{account[3]}`\n**xp:**  `{account[1]}`\n{next_lvl}**Word Cache:** `{account[2]}/{level_rates[account[3]]}`\n**XP from rp this week: `{account[5]}/{rp_cap[account[3]]}`**",
                color=member.color
            ) # fancy emb
            
            # reference rank
            rank_txt=""
            for rank in range(len(ordered)): # get main user rank
                if ordered[rank][0]==account[0]:
                    r=rank
                    break
            
            for rank in range(r-1,r+2):
                if rank>=0:
                    if rank==r:
                        rank_txt+=f"> {rank+1}. **<@{ordered[rank][0]}> - {ordered[rank][1]} xp**"
                    else:
                        rank_txt+=f"> {rank+1}. <@{ordered[rank][0]}> - {ordered[rank][1]} xp"

                    rank_txt+="\n"

            tembed.add_field(
                name=f"Rank: {r+1} / {len(ordered)}",
                value=rank_txt
            )
        else: # the player is not yet in the database
            tembed=discord.Embed(
                title=f"**{member.name}'s stats:**",
                description=f"This user has no XP stats yet!",
                color=member.color
            ) # fancy emb

    query.close() # close querying
    tembed.set_thumbnail(url=member.display_avatar.url) # add general fanciness
    await ctx.send(embed=tembed) # send the fancy

@QuestBored.command(aliases=['add_xp','Add','Add_xp'])
async def add(ctx, xp=0, member:discord.Member=None): # add xp to user
    if checkDMrole(ctx.author): # check whether or not the person who invoked the cmd has a dm role
        if not member: # default to author
            member=ctx.author

        if member.bot==True: # trying to give xp to bot
            tembed=discord.Embed(description=f"{member.name} is a bot user, cannot add {xp} xp", color=member.color, title="Cannot add xp")
        else: # give xp to player
            new_xp = await add_xp(xp, member)
            if new_xp:
                tembed=discord.Embed(description=f"Added {xp}xp to {member.mention}!\n ( {new_xp} )", color=member.color, title="Adding xp")
            else:
                tembed=discord.Embed(description=f"Added {xp}xp to {member.mention}!\n ( 0 -> {xp} )", color=member.color, title="Adding xp")
    else: # if they don't have a DM role
        member=ctx.author
        tembed=discord.Embed(description=f"In order to add XP to someone, you need to be a DM!\n(Myrmidon, Acolyte, Disciple)", color=member.color, title="Cannot add xp")

    await ctx.send(embed=tembed) # send the fancy

@QuestBored.command(aliases=['Reset','reset_xp','Reset_xp'])
async def reset(ctx): # reset user's stats
    query = database.cursor() # query object
    member=ctx.author # default to self

    query.execute(f"""SELECT * FROM {conf['tables']['xp']} WHERE account_id = {member.id}""") # lookup user in db
    account=query.fetchone() # get user info lmao
    if account: # found user in db
        query.execute(f"""UPDATE {conf['tables']['xp']}
            SET xp = {default_account['xp']}, word_cache = {default_account['word_cache']}, level = {default_account['level']}, lvl_notification = {default_account['lvl_notification']}, weekly_xp = {default_account['weekly_xp']}
            WHERE account_id = {member.id}""") # reset lvl & xp
        database.commit() # commit db
        tembed=discord.Embed(description=f"Reset {member.mention}'s xp and level\n{account[1]} -> 0 xp", color=member.color, title="Reset user XP")
    else: # user not in db
        tembed=discord.Embed(description=f"{member.name} doesn't have any server statistics yet, so they cannot be reset", title="Cannot reset xp", color=member.color)

    query.close() # close querying
    await ctx.send(embed=tembed) # send the fancy

@QuestBored.command(aliases=['lvl_up','Level_up','Lvl_up'])
async def level_up(ctx):
    query = database.cursor() # query object

    query.execute(f"""SELECT * FROM {conf['tables']['xp']} WHERE account_id = {ctx.author.id}""") # lookup user in db
    account=query.fetchone() # access user info
    if account: # user in db
        if account[1]>=level_req[account[3]+1]: # user has anough xp to lvl up
            query.execute(f"""UPDATE {conf['tables']['xp']}
                            SET level = {account[3]+1}
                            WHERE account_id = {account[0]}""") # increase lvl by one
            database.commit() # commit to changes

            if account[1]>=level_req[account[3]+2]: # user has enough xp to lvl up again
                tembed=discord.Embed(title=f"Leveled up to {account[3]+1}!",
                    color=ctx.author.color,
                    description=f"You have enough experience to level up to {account[3]+2}!")
            else: # not enough xp to lvl up again
                query.execute(f"""UPDATE {conf['tables']['xp']}
                    SET lvl_notification = True
                    WHERE account_id = {account[0]}""") # enable lvl up notific
                database.commit() # commit to changes
                tembed=discord.Embed(title=f"Leveled up to {account[3]+1}!",
                    color=ctx.author.color,
                    description=f"{level_req[account[3]+2]-account[1]} remaining until lvl {account[3]+2}!")
        else: # not enough xp to lvl up
            tembed=discord.Embed(title="Cannot level up!", description=f"You don't have enough experience to level up just yet!\n({level_req[account[3]+1]-account[1]} xp remaining)", color=ctx.author.color)
    else: # user not in db
        tembed=discord.Embed(title="Cannot level up!", description="You don't have any server statistics yet, so you sadly cannot level up!", color=ctx.author.color)

    query.close() # close querying
    await ctx.send(embed=tembed) # send the fancy

@QuestBored.command()
async def top(ctx): # looks up the top 5 folks
    query = database.cursor() # query object
    member=ctx.author
    top_list=""
    author_rank=0

    query.execute(f"""SELECT account_id, xp FROM {conf['tables']['xp']} ORDER BY xp DESC""")
    ordered = query.fetchall()
    for rank in range(0, len(ordered)): # loop through all accounts
        account = ordered[rank] # get reference to the current account
        if account[0]==member.id: # get the rank of the author
            author_rank=rank+1
        if rank<5: # fill up the top X list
            top_list+=f"**{rank+1}.** <@{account[0]}> - {account[1]} xp" # append account

            # add a little flare to the top 3 & the viewer
            if rank==0:
                top_list+=" :first_place:"
            elif rank==1:
                top_list+=" :second_place:"
            elif rank==2:
                top_list+=" :third_place:"
            if rank==author_rank-1:
                top_list+=" **•**"

            top_list+="\n" # end the line

    tembed=discord.Embed(title="TOP 5 USERS BY XP", description=f"{top_list}\n**Your rank:** {author_rank}", color=member.color) # make the fancy
    tembed.set_thumbnail(url="https://images.emojiterra.com/twitter/v14.0/512px/1f3c6.png") # add general fanciness

    query.close() # close querying
    await ctx.send(embed=tembed) # send the fancy

# ----------------------- python main --------------------- #
def main():
    # run tha bot :D
    print(f"Logging into discord...")
    QuestBored.run(conf['token'])
    database.close() # close db connection
if __name__ == "__main__":
    main()
