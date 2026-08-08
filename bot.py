import os
import time
import asyncio
import threading
import sqlite3
import secrets
import urllib.parse

import requests
from flask import Flask, request, redirect
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

import discord
from discord.ext import commands

CLIENT_ID = os.environ.get("CLIENT_ID")
CLIENT_SECRET = os.environ.get("CLIENT_SECRET")
REDIRECT_URI = os.environ.get("REDIRECT_URI")
BOT_TOKEN = os.environ.get("BOT_TOKEN")

BACKGROUND_IMAGE_URL = "https://i.ibb.co/PzGWTPDX/file-0000000038447209a7fe0ab84d413e2a.png"
BOT_BRAND_NAME = "remouse.pmt"

SOCIAL_LINKS = {
    "discord": "https://discord.gg/3UgwZhKsp3",
    "instagram": "https://www.instagram.com/remousepmt",
    "youtube": "https://www.youtube.com/@JoDobig",
    "website": "https://discord-bot-final-1-pzlz.onrender.com/",
}

OWNER_GUILD_IDS = []

AUTHORIZED_USER_IDS = [1526937904423764030, 1526503693690601592]


def is_authorized():
    async def predicate(ctx):
        return ctx.author.id in AUTHORIZED_USER_IDS
    return commands.check(predicate)


conn = sqlite3.connect("data.db", check_same_thread=False)
conn.execute("""
CREATE TABLE IF NOT EXISTS user_tokens (
    user_id TEXT PRIMARY KEY,
    access_token TEXT NOT NULL,
    refresh_token TEXT NOT NULL,
    expires_at INTEGER NOT NULL
)
""")
conn.commit()


def save_user_token(user_id, access_token, refresh_token, expires_in):
    expires_at = int(time.time()) + expires_in
    conn.execute(
        "INSERT OR REPLACE INTO user_tokens (user_id, access_token, refresh_token, expires_at) VALUES (?, ?, ?, ?)",
        (user_id, access_token, refresh_token, expires_at)
    )
    conn.commit()


def get_valid_access_token(user_id):
    row = conn.execute(
        "SELECT access_token, refresh_token, expires_at FROM user_tokens WHERE user_id = ?",
        (user_id,)
    ).fetchone()

    if not row:
        return None

    access_token, refresh_token, expires_at = row

    if time.time() < expires_at - 60:
        return access_token

    res = requests.post(
        "https://discord.com/api/oauth2/token",
        data={
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    data = res.json()
    new_access = data.get("access_token")
    new_refresh = data.get("refresh_token")
    expires_in = data.get("expires_in")

    if not new_access:
        return None

    save_user_token(user_id, new_access, new_refresh, expires_in)
    return new_access


def join_user_to_guild(user_id, guild_id, role_id=None):
    access_token = get_valid_access_token(user_id)
    if not access_token:
        return False, "ไม่พบข้อมูลการยืนยันตัวตน หรือ token ใช้ไม่ได้แล้ว"

    payload = {"access_token": access_token}
    if role_id:
        payload["roles"] = [role_id]

    res = requests.put(
        f"https://discord.com/api/guilds/{guild_id}/members/{user_id}",
        headers={
            "Authorization": f"Bot {BOT_TOKEN}",
            "Content-Type": "application/json",
        },
        json=payload,
    )

    debug_msg = f"[step1] status={res.status_code} body={res.text[:200]}"

    if res.status_code not in (201, 204):
        return False, debug_msg

    if role_id:
        role_res = requests.put(
            f"https://discord.com/api/guilds/{guild_id}/members/{user_id}/roles/{role_id}",
            headers={"Authorization": f"Bot {BOT_TOKEN}"},
        )
        debug_msg += f" | [step2] status={role_res.status_code} body={role_res.text[:200]}"

        if role_res.status_code != 204:
            return False, debug_msg

    return True, debug_msg


def get_all_verified_users():
    rows = conn.execute("SELECT user_id FROM user_tokens").fetchall()
    return [row[0] for row in rows]


def render_result_page(guild_name, success=True, error_message=None, username=None, guild_icon_url=None, user_avatar_url=None):
    guild_display = guild_name if guild_name else "Discord Server"

    if not guild_icon_url:
        guild_icon_url = "https://cdn.discordapp.com/embed/avatars/0.png"
    if not user_avatar_url:
        user_avatar_url = "https://cdn.discordapp.com/embed/avatars/0.png"

    if success:
        html_out = f"""<!DOCTYPE html>
<html lang="th">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>ยืนยันตัวตนสำเร็จ</title>
    <style>
        * {{ margin:0; padding:0; box-sizing:border-box; }}
        body {{
            font-family: 'Segoe UI', Tahoma, sans-serif;
            min-height: 100vh;
            display: flex;
            justify-content: center;
            align-items: center;
            background: radial-gradient(circle at center, #1a7a1a 0%, #0d2f0d 60%, #000000 100%);
            padding: 20px;
            position: relative;
            overflow: hidden;
        }}
        .card {{
            background: rgba(26, 46, 26, 0.6);
            backdrop-filter: blur(16px);
            -webkit-backdrop-filter: blur(16px);
            border-radius: 30px;
            padding: 40px 30px 30px 30px;
            max-width: 380px;
            width: 100%;
            text-align: center;
            border: 1px solid rgba(74, 222, 128, 0.2);
            box-shadow: 0 20px 60px rgba(0,0,0,0.6);
            position: relative;
            z-index: 2;
        }}
        .guild-icon {{
            width: 64px;
            height: 64px;
            border-radius: 50%;
            margin: 0 auto 12px;
            border: 2px solid #4ade80;
            object-fit: cover;
            display: block;
            background: #1a2e1a;
        }}
        .welcome {{
            color: #86ef86;
            font-size: 13px;
            letter-spacing: 3px;
            text-transform: uppercase;
            margin-bottom: 2px;
            opacity: 0.9;
        }}
        h1 {{
            color: #ffffff;
            font-size: 24px;
            font-weight: 700;
            margin-bottom: 18px;
        }}
        .user-box {{
            background: rgba(255,255,255,0.05);
            backdrop-filter: blur(8px);
            -webkit-backdrop-filter: blur(8px);
            border-radius: 24px;
            padding: 16px 20px 14px 20px;
            display: inline-flex;
            flex-direction: column;
            align-items: center;
            gap: 6px;
            border: 1px solid rgba(74,222,128,0.15);
            margin-bottom: 16px;
            min-width: 150px;
        }}
        .user-avatar {{
            width: 70px;
            height: 70px;
            border-radius: 50%;
            border: 2px solid #4ade80;
            object-fit: cover;
        }}
        .username {{
            color: #f0fdf0;
            font-size: 18px;
            font-weight: 600;
        }}
        .message {{
            color: #a0d6a0;
            font-size: 14px;
            line-height: 1.6;
            margin-bottom: 22px;
            opacity: 0.85;
        }}
        .btn-primary {{
            display: inline-block;
            width: 100%;
            padding: 14px 20px;
            border-radius: 50px;
            text-decoration: none;
            font-weight: 700;
            font-size: 15px;
            background: linear-gradient(135deg, #22c55e, #16a34a);
            color: #ffffff;
            box-shadow: 0 8px 30px rgba(34,197,94,0.25);
            transition: all 0.3s ease;
            border: none;
            cursor: pointer;
        }}
        .btn-primary:hover {{
            transform: translateY(-2px);
            box-shadow: 0 12px 40px rgba(34,197,94,0.4);
        }}
        .footer {{
            color: #4a7a4a;
            font-size: 11px;
            margin-top: 18px;
            letter-spacing: 1px;
            text-transform: uppercase;
        }}
        .snowflake {{
            position: fixed;
            top: -10px;
            color: white;
            user-select: none;
            pointer-events: none;
            z-index: 1;
            opacity: 0.7;
            font-size: 1.2rem;
            animation: fall linear infinite;
        }}
        @keyframes fall {{
            to {{ transform: translateY(110vh) rotate(360deg); }}
        }}
    </style>
</head>
<body>
    <script>
        (function() {{
            const snowflakeCount = 40;
            const body = document.body;
            for (let i = 0; i < snowflakeCount; i++) {{
                const flake = document.createElement('div');
                flake.className = 'snowflake';
                flake.textContent = '❄';
                flake.style.left = Math.random() * 100 + 'vw';
                flake.style.fontSize = (Math.random() * 14 + 10) + 'px';
                flake.style.opacity = Math.random() * 0.6 + 0.3;
                flake.style.animationDuration = (Math.random() * 8 + 6) + 's';
                flake.style.animationDelay = (Math.random() * 10) + 's';
                body.appendChild(flake);
            }}
        }})();
    </script>

    <div class="card">
        <img class="guild-icon" src="{guild_icon_url}" alt="Server Icon">
        <div class="welcome">WELCOME 🎉</div>
        <h1>ยืนยันตัวตนสำเร็จแล้ว</h1>

        <div class="user-box">
            <img class="user-avatar" src="{user_avatar_url}" alt="User Avatar">
            <span class="username">@{(username if username else 'ผู้ใช้')}</span>
        </div>

        <div class="message">
            ยืนยันตัวตนสำเร็จ<br>
            กลับเข้าสู่หน้าหลัก Discord
        </div>

        <a href="https://discord.com/channels/@me" class="btn-primary">กลับสู่ Discord</a>

        <div class="footer">&copy; 2026 {guild_display}<br>Powered by {BOT_BRAND_NAME}</div>
    </div>
</body>
</html>"""
        return html_out
    else:
        html_out = f"""<!DOCTYPE html>
<html lang="th">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Verify Failed</title>
    <style>
        * {{ margin:0; padding:0; box-sizing:border-box; }}
        body {{
            font-family: 'Segoe UI', Tahoma, sans-serif;
            min-height: 100vh;
            display: flex;
            justify-content: center;
            align-items: center;
            background: #1a0d0d;
            padding: 20px;
        }}
        .card {{
            background: rgba(46, 26, 26, 0.6);
            backdrop-filter: blur(16px);
            border-radius: 30px;
            padding: 40px 30px 30px 30px;
            max-width: 380px;
            width: 100%;
            text-align: center;
            border: 1px solid rgba(239, 68, 68, 0.2);
            box-shadow: 0 20px 60px rgba(0,0,0,0.6);
        }}
        .logo {{
            width: 80px;
            height: 80px;
            border-radius: 50%;
            margin: 0 auto 16px;
            background: radial-gradient(circle, rgba(255,70,70,0.15), #1a0505);
            border: 2px solid #ef4444;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 32px;
            font-weight: bold;
            color: #ef4444;
        }}
        .label {{
            color: #ef8686;
            font-size: 13px;
            letter-spacing: 2px;
            text-transform: uppercase;
            margin-bottom: 6px;
            opacity: 0.9;
        }}
        h1 {{
            color: #ffffff;
            font-size: 26px;
            font-weight: 700;
            margin-bottom: 8px;
        }}
        .desc {{
            color: #ef8686;
            font-size: 15px;
            font-weight: 600;
            margin-bottom: 4px;
        }}
        .sub {{
            color: #d6a0a0;
            font-size: 14px;
            margin-bottom: 20px;
            opacity: 0.85;
        }}
        .btn {{
            display: inline-block;
            width: 100%;
            padding: 14px 20px;
            border-radius: 50px;
            text-decoration: none;
            font-weight: 700;
            font-size: 15px;
            background: linear-gradient(135deg, #ef4444, #dc2626);
            color: #ffffff;
            box-shadow: 0 8px 30px rgba(239,68,68,0.25);
            transition: all 0.3s ease;
            border: none;
            cursor: pointer;
        }}
        .btn:hover {{
            transform: translateY(-2px);
            box-shadow: 0 12px 40px rgba(239,68,68,0.4);
        }}
        .footer {{
            color: #7a4a4a;
            font-size: 11px;
            margin-top: 18px;
            letter-spacing: 1px;
            text-transform: uppercase;
        }}
    </style>
</head>
<body>
    <div class="card">
        <div class="logo">❌</div>
        <div class="label">SERVER VERIFY</div>
        <h1>Verify Failed</h1>
        <div class="desc">{error_message if error_message else 'เกิดข้อผิดพลาด'}</div>
        <div class="sub">กรุณาลองใหม่อีกครั้ง</div>
        <a href="/" class="btn">🔄 ลองใหม่</a>
        <div class="footer">&copy; 2026 {guild_display}<br>Powered by {BOT_BRAND_NAME}</div>
    </div>
</body>
</html>"""
        return html_out


app = Flask(__name__)

limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=["30 per minute"]
)


@app.route("/")
def home():
    return "Bot verify server is running."


@app.route("/callback")
@limiter.limit("10 per minute")
def callback():
    code = request.args.get("code")
    state = request.args.get("state")

    if not code:
        return render_result_page(None, success=False, error_message="ไม่สามารถแจกยศได้"), 400

    guild_id = None
    role_id = None
    guild_name = None
    if state:
        parts = state.split(":", 2)
        if len(parts) >= 1:
            guild_id = parts[0]
        if len(parts) >= 2:
            role_id = parts[1]
        if len(parts) >= 3:
            guild_name = urllib.parse.unquote(parts[2])

    token_res = requests.post(
        "https://discord.com/api/oauth2/token",
        data={
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": REDIRECT_URI,
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    token_data = token_res.json()
    access_token = token_data.get("access_token")
    refresh_token = token_data.get("refresh_token")
    expires_in = token_data.get("expires_in")

    if not access_token:
        return render_result_page(guild_name, success=False, error_message="ไม่สามารถแจกยศได้"), 400

    user_res = requests.get(
        "https://discord.com/api/users/@me",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    user_data = user_res.json()
    user_id = user_data["id"]
    username = user_data.get("username", "ผู้ใช้")
    user_avatar_hash = user_data.get("avatar")
    user_avatar_url = f"https://cdn.discordapp.com/avatars/{user_id}/{user_avatar_hash}.png" if user_avatar_hash else "https://cdn.discordapp.com/embed/avatars/0.png"

    save_user_token(user_id, access_token, refresh_token, expires_in)

    guild_icon_url = None
    if guild_id:
        guild_info = requests.get(
            f"https://discord.com/api/guilds/{guild_id}",
            headers={"Authorization": f"Bot {BOT_TOKEN}"}
        )
        if guild_info.status_code == 200:
            guild_data = guild_info.json()
            icon_hash = guild_data.get("icon")
            if icon_hash:
                guild_icon_url = f"https://cdn.discordapp.com/icons/{guild_id}/{icon_hash}.png"

    if guild_id:
        success, message = join_user_to_guild(user_id, guild_id, role_id)
        if success:
            return render_result_page(guild_name, success=True, username=username, guild_icon_url=guild_icon_url, user_avatar_url=user_avatar_url)
        else:
            return render_result_page(guild_name, success=False, error_message="ไม่สามารถแจกยศได้")

    return render_result_page(guild_name, success=True, username=username, guild_icon_url=guild_icon_url, user_avatar_url=user_avatar_url)


@app.errorhandler(429)
def ratelimit_handler(e):
    return render_result_page(None, success=False, error_message="คำขอถี่เกินไป กรุณาลองใหม่ภายหลัง"), 429


def run_flask():
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)


intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)


class VerifyView(discord.ui.View):
    def __init__(self, guild_id, role_id, guild_name, emoji="✅"):
        super().__init__(timeout=None)

        encoded_name = urllib.parse.quote(guild_name)
        state_value = f"{guild_id}:{role_id}:{encoded_name}"

        direct_auth_url = (
            f"https://discord.com/api/oauth2/authorize"
            f"?client_id={CLIENT_ID}"
            f"&redirect_uri={REDIRECT_URI}"
            f"&response_type=code"
            f"&scope=identify+guilds.join"
            f"&state={state_value}"
        )

        self.add_item(discord.ui.Button(
            label="รับยศ",
            emoji=emoji,
            style=discord.ButtonStyle.link,
            url=direct_auth_url
        ))


@bot.event
async def on_ready():
    print(f"บอทออนไลน์แล้ว: {bot.user}")


@bot.event
async def on_guild_join(guild):
    if OWNER_GUILD_IDS and guild.id not in OWNER_GUILD_IDS:
        print(f"บอทถูกเชิญเข้าเซิร์ฟที่ไม่อนุญาต: {guild.name} ({guild.id}) — กำลังออก...")
        await guild.leave()


@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CheckFailure):
        await ctx.send("คุณไม่มีสิทธิ์ใช้คำสั่งนี้")
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(f"ใส่ข้อมูลไม่ครบ: ขาด {error.param.name}")
    elif isinstance(error, commands.RoleNotFound):
        await ctx.send(f"ไม่พบยศที่ระบุ: {error.argument}")
    elif isinstance(error, commands.MemberNotFound):
        await ctx.send(f"ไม่พบสมาชิกที่ระบุ: {error.argument}")
    elif isinstance(error, commands.CommandNotFound):
        pass
    else:
        await ctx.send(f"เกิดข้อผิดพลาด: {error}")
        print(f"Unhandled error: {error}")


@bot.command()
@is_authorized()
async def setup_verify(ctx, role: discord.Role, emoji: str = "✅", banner_url: str = None, *, description: str = None):
    final_banner = banner_url if banner_url else BACKGROUND_IMAGE_URL
    if not (final_banner.startswith("http://") or final_banner.startswith("https://")):
        final_banner = BACKGROUND_IMAGE_URL

    final_description = description if description else f"กดปุ่มด้านล่างเลยKub กดรับยศจะได้ยศ {role.mention}"

    embed = discord.Embed(
        description=final_description,
        color=discord.Color.blurple()
    )

    if ctx.guild.icon:
        embed.set_thumbnail(url=ctx.guild.icon.url)

    embed.set_image(url=final_banner)
    embed.set_footer(
        text=f"{ctx.guild.name} - ระบบยืนยันตัวตน",
        icon_url=ctx.guild.icon.url if ctx.guild.icon else None
    )
    embed.timestamp = discord.utils.utcnow()

    try:
        view = VerifyView(ctx.guild.id, role.id, ctx.guild.name, emoji=emoji)
    except Exception:
        view = VerifyView(ctx.guild.id, role.id, ctx.guild.name, emoji="✅")

    await ctx.send(embed=embed, view=view)


@bot.command()
@is_authorized()
async def pull(ctx, member: discord.Member, guild_id: str, role_id: str = None):
    success, message = join_user_to_guild(str(member.id), guild_id, role_id)
    if success:
        await ctx.send(f"ดึง {member.mention} เข้าเซิร์ฟ {guild_id} สำเร็จแล้ว")
    else:
        await ctx.send(f"ล้มเหลว: {message}")


@bot.command()
@is_authorized()
async def pullall(ctx, guild_id: str, role_id: str = None):
    user_ids = get_all_verified_users()
    total = len(user_ids)

    if total == 0:
        await ctx.send("ยังไม่มีใครยืนยันตัวตนไว้เลย")
        return

    await ctx.send(f"กำลังดึง {total} คนเข้าเซิร์ฟ {guild_id} ...")

    success_count = 0
    fail_count = 0
    fail_list = []

    for user_id in user_ids:
        success, message = join_user_to_guild(user_id, guild_id, role_id)
        if success:
            success_count += 1
        else:
            fail_count += 1
            fail_list.append(f"{user_id}: {message}")
        await asyncio.sleep(1)

    result_text = f"สำเร็จ {success_count} คน / ล้มเหลว {fail_count} คน"
    await ctx.send(result_text)

    if fail_list:
        chunk = "\n".join(fail_list[:5])
        await ctx.send(f"รายละเอียด:\n{chunk}")


@bot.command()
@is_authorized()
async def countverified(ctx):
    count = len(get_all_verified_users())
    await ctx.send(f"มีผู้ยืนยันตัวตนแล้วทั้งหมด {count} คน")


@bot.command()
@is_authorized()
async def removerole(ctx, role: discord.Role):
    members_with_role = [m for m in ctx.guild.members if role in m.roles]
    total = len(members_with_role)

    if total == 0:
        await ctx.send(f"ไม่มีใครมียศ {role.mention} เลยตอนนี้")
        return

    await ctx.send(f"กำลังลบยศ {role.mention} ออกจาก {total} คน...")

    success_count = 0
    fail_count = 0

    for member in members_with_role:
        try:
            await member.remove_roles(role)
            success_count += 1
        except Exception:
            fail_count += 1
        await asyncio.sleep(0.5)

    await ctx.send(f"ลบยศออกสำเร็จ {success_count} คน / ล้มเหลว {fail_count} คน")


def run_bot():
    bot.run(BOT_TOKEN)


if __name__ == "__main__":
    flask_thread = threading.Thread(target=run_flask)
    flask_thread.start()
    run_bot()
