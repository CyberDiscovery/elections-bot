import base64
from os import environ


DEPLOY = bool(environ.get("DEPLOY"))


def getenv(name: str, fallback: str = "") -> str:
    """Return an (optionally base64-encoded) env var."""
    variable = environ.get(name)
    if DEPLOY and variable is not None:
        variable = base64.b64decode(variable).decode()
    return variable or fallback


class PostgreSQL:
    PGHOST = getenv("PGHOST")
    PGPORT = getenv("PGPORT")
    PGUSER = getenv("PGUSER")
    PGDATABASE = getenv("PGDATABASE")
    PGPASSWORD = getenv("PGPASSWORD")


BOT_TOKEN = getenv("BOT_TOKEN")
ROOT_ROLE_ID = int(environ.get("ROOT_MEMBERS_ID", "450113490590629888"))
SUDO_ROLE_ID = int(environ.get("SUDO_MEMBERS_ID", "450113682542952451"))
LOGGING_CHANNEL_ID = int(environ.get("LOGGING_CHANNEL_ID", "683722827718852656"))
CYBERDISC_ICON_URL = (
    "https://pbs.twimg.com/profile_images/921313066515615745/fLEl2Gfa_400x400.jpg"
)

EMOJI_SERVER_ID = int(environ.get("EMOJI_SERVER_ID", "683722025608675527"))
VOTE_SERVER_ID = int(environ.get("VOTE_SERVER_ID", "409851296116375565"))

LEVEL_ROLE_ID = int(environ.get("LEVEL_ROLE_ID", "450407751387054081"))
DTB_ROLE_ID = int(environ.get("DTB_ROLE_ID", "464048499219103745"))
MUTED_ROLE_ID = int(environ.get("MUTED_ROLE_ID", "450402574047248384"))
