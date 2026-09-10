import os
import time
import asyncio
import threading
import sqlite3
import urllib.parse
import hashlib
import base64

import requests
from flask import Flask, request
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

import discord
from discord.ext import commands

from cryptography.fernet import Fernet

# ============ CONFIG ============
CLIENT_ID = os.environ.get("CLIENT_ID")
CLIENT_SECRET = os.environ.get("CLIENT_SECRET")
REDIRECT_URI = os.environ.get("REDIRECT_URI")
BOT_TOKEN = os.environ.get("BOT_TOKEN")

BACKGROUND_IMAGE_URL = "https://i.ibb.co/PzGWTPDX/file-0000000038447209a7fe0ab84d413e2a.png"
BOT_BRAND_NAME = "remouse.pmt"

OWNER_GUILD_IDS = []
AUTHORIZED_USER_IDS = [
    1526937904423764030,  # 👈 เปลี่ยนเป็น ID ของคุณ
]

def is_authorized():
    async def predicate(ctx):
        return ctx.author.id in AUTHORIZED_USER_IDS
    return commands.check(predicate)

# ============ ENCRYPTION ============
MASTER_KEY = BOT_TOKEN

def get_key_from_token(token):
    hash_obj = hashlib.sha256(token.encode())
    return base64.urlsafe_b64encode(hash_obj.digest())

def encrypt_data(data, token=MASTER_KEY):
    key = get_key_from_token(token)
    cipher = Fernet(key)
    return cipher.encrypt(data.encode()).decode()

def decrypt_data(encrypted_data, token=MASTER_KEY):
    key = get_key_from_token(token)
    cipher = Fernet(key)
    return cipher.decrypt(encrypted_data.encode()).decode()

# ============ DATABASE ============
conn = sqlite3.connect("data.db", check_same_thread=False)

# แก้ตาราง user_tokens ให้เก็บ user_id เป็นข้อความธรรมดา
conn.execute("""
CREATE TABLE IF NOT EXISTS user_tokens (
    user_id TEXT PRIMARY KEY,
    access_token TEXT NOT NULL,
    refresh_token TEXT NOT NULL,
    expires_at INTEGER NOT NULL
)
""")
conn.commit()

# แก้ตาราง verified_users ให้เก็บ user_id เป็นข้อความธรรมดา
conn.execute("""
CREATE TABLE IF NOT EXISTS verified_users (
    user_id TEXT PRIMARY KEY,
    encrypted_data TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
""")
conn.commit()

def save_user_token(user_id, access_token, refresh_token, expires_in):
    expires_at = int(time.time()) + expires_in
    # user_id เก็บธรรมดา, Token เข้ารหัส
    conn.execute(
        "INSERT OR REPLACE INTO user_tokens (user_id, access_token, refresh_token, expires_at) VALUES (?, ?, ?, ?)",
        (str(user_id), encrypt_data(access_token), encrypt_data(refresh_token), expires_at)
    )
    conn.commit()

def get_valid_access_token(user_id):
    # ค้นหาด้วย user_id ธรรมดา
    row = conn.execute(
        "SELECT access_token, refresh_token, expires_at FROM user_tokens WHERE user_id = ?",
        (str(user_id),)
    ).fetchone()
    
    if not row:
        return None
    
    enc_access, enc_refresh, expires_at = row
    try:
        access_token = decrypt_data(enc_access)
        refresh_token = decrypt_data(enc_refresh)
    except:
        return None
    
    if time.time() < expires_at - 60:
        return access_token
    
    # Refresh token
    try:
        res = requests.post(
            "https://discord.com/api/oauth2/token",
            data={
                "client_id": CLIENT_ID, "client_secret": CLIENT_SECRET,
                "grant_type": "refresh_token", "refresh_token": refresh_token,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"}, timeout=10
        )
        data = res.json()
        new_access = data.get("access_token")
        if not new_access:
            return None
        save_user_token(user_id, new_access, data.get("refresh_token"), data.get("expires_in"))
        return new_access
    except:
        return None

def join_user_to_guild(user_id, guild_id, role_id=None):
    access_token = get_valid_access_token(user_id)
    if not access_token:
        return False, "ไม่พบข้อมูลการยืนยันตัวตน หรือ Token หมดอายุ กรุณากดปุ่มใหม่"
    
    payload = {"access_token": access_token}
    if role_id:
        payload["roles"] = [role_id]
        
    try:
        res = requests.put(
            f"https://discord.com/api/guilds/{guild_id}/members/{user_id}",
            headers={"Authorization": f"Bot {BOT_TOKEN}", "Content-Type": "application/json"},
            json=payload, timeout=15
        )
        if res.status_code in (201, 204):
            return True, "✅ สำเร็จ"
        elif res.status_code == 403:
            return False, "❌ บอทไม่มีสิทธิ์ (Forbidden)"
        elif res.status_code == 404:
            return False, "❌ ไม่พบเซิร์ฟเวอร์ (Not Found)"
        else:
            return False, f"❌ Error {res.status_code}: {res.text[:100]}"
    except Exception as e:
        return False, f"❌ เกิดข้อผิดพลาด: {str(e)[:50]}"

def save_verified_user(user_id, username, access_token):
    raw_data = f"{username}:{access_token}"
    conn.execute(
        "INSERT OR REPLACE INTO verified_users (user_id, encrypted_data) VALUES (?, ?)",
        (str(user_id), encrypt_data(raw_data))
    )
    conn.commit()

def get_all_verified_users():
    rows = conn.execute("SELECT user_id, encrypted_data FROM verified_users").fetchall()
    users = []
    for row in rows:
        try:
            user_id, encrypted_data = row
            decrypted = decrypt_data(encrypted_data)
            parts = decrypted.split(":", 1)
            users.append({
                "user_id": user_id,
                "username": parts[0],
                "access_token": parts[1] if len(parts) > 1 else None
            })
        except:
            continue
    return users

# ============ FLASK ============
app = Flask(__name__)
limiter = Limiter(get_remote_address, app=app, default_limits=["30 per minute"])

def render_page(success, message="", guild_name="BONTEN COMMUNITY", username=None, guild_icon=None, user_avatar=None):
    if success:
        return f"""<!DOCTYPE html><html><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"><title>ยืนยันตัวตนสำเร็จ</title>
        <style>body {{font-family: 'Segoe UI', sans-serif; min-height: 100vh; display: flex; justify-content: center; align-items: center; background: radial-gradient(circle, #1a7a1a 0%, #0d2f0d 60%, #000 100%); padding: 20px; margin:0;}}
        .card {{background: rgba(26,46,26,0.6); backdrop-filter: blur(16px); border-radius: 30px; padding: 40px 30px; max-width: 380px; width: 100%; text-align: center; border: 1px solid rgba(74,222,128,0.2); box-shadow: 0 20px 60px rgba(0,0,0,0.6);}}
        .icon {{width: 64px; height: 64px; border-radius: 50%; margin: 0 auto 12px; border: 2px solid #4ade80; object-fit: cover; display: block;}}
        .welcome {{color: #86ef86; font-size: 13px; letter-spacing: 3px; text-transform: uppercase; margin-bottom: 2px;}}
        h1 {{color: #fff; font-size: 24px; margin-bottom: 18px;}} .user-box {{background: rgba(255,255,255,0.05); border-radius: 24px; padding: 16px; display: inline-flex; flex-direction: column; align-items: center; gap: 6px; border: 1px solid rgba(74,222,128,0.15); margin-bottom: 16px;}}
        .avatar {{width: 70px; height: 70px; border-radius: 50%; border: 2px solid #4ade80; object-fit: cover;}} .username {{color: #f0fdf0; font-size: 18px; font-weight: 600;}}
        .msg {{color: #a0d6a0; font-size: 14px; margin-bottom: 22px;}} .btn {{display: inline-block; width: 100%; padding: 14px; border-radius: 50px; text-decoration: none; font-weight: 700; background: linear-gradient(135deg, #22c55e, #16a34a); color: #fff; box-shadow: 0 8px 30px rgba(34,197,94,0.25);}}
        .footer {{color: #4a7a4a; font-size: 11px; margin-top: 18px;}}</style></head><body>
        <div class="card"><img class="icon" src="{guild_icon or 'https://cdn.discordapp.com/embed/avatars/0.png'}"><div class="welcome">WELCOME 🎉</div><h1>ยืนยันตัวตนสำเร็จแล้ว</h1>
        <div class="user-box"><img class="avatar" src="{user_avatar or 'https://cdn.discordapp.com/embed/avatars/0.png'}"><span class="username">@{username or 'ผู้ใช้'}</span></div>
        <div class="msg">ยืนยันตัวตนสำเร็จ<br>กลับเข้าสู่หน้าหลัก Discord</div><a href="https://discord.com/channels/@me" class="btn">กลับสู่ Discord</a>
        <div class="footer">© 2026 {guild_name}<br>Powered by {BOT_BRAND_NAME}</div></div></body></html>"""
    else:
        return f"""<!DOCTYPE html><html><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"><title>Verify Failed</title>
        <style>body {{font-family: 'Segoe UI', sans-serif; min-height: 100vh; display: flex; justify-content: center; align-items: center; background: #1a0d0d; padding: 20px; margin:0;}}
        .card {{background: rgba(46,26,26,0.6); backdrop-filter: blur(16px); border-radius: 30px; padding: 40px; max-width: 380px; text-align: center; border: 1px solid rgba(239,68,68,0.2);}}
        .logo {{width: 80px; height: 80px; border-radius: 50%; margin: 0 auto 16px; background: radial-gradient(circle, rgba(255,70,70,0.15), #1a0505); border: 2px solid #ef4444; display: flex; align-items: center; justify-content: center; font-size: 32px; color: #ef4444;}}
        h1 {{color: #fff; font-size: 26px; margin-bottom: 8px;}} .desc {{color: #ef8686; font-size: 15px; margin-bottom: 4px;}} .sub {{color: #d6a0a0; font-size: 14px; margin-bottom: 20px;}}
        .btn {{display: inline-block; width: 100%; padding: 14px; border-radius: 50px; text-decoration: none; font-weight: 700; background: linear-gradient(135deg, #ef4444, #dc2626); color: #fff;}}</style></head><body>
        <div class="card"><div class="logo">❌</div><h1>Verify Failed</h1><div class="desc">{message}</div><div class="sub">กรุณาลองใหม่อีกครั้ง</div>
        <a href="https://discord.com/channels/@me" class="btn">กลับสู่ Discord</a><div class="footer">© 2026 BONTEN COMMUNITY<br>Powered by {BOT_BRAND_NAME}</div></div></body></html>"""

@app.route("/")
def home():
    return "Bot verify server is running."

@app.route("/callback")
@limiter.limit("10 per minute")
def callback():
    code = request.args.get("code")
    state = request.args.get("state")
    if not code:
        return render_page(False, "ไม่พบรหัสยืนยัน"), 400

    guild_id = role_id = guild_name = None
    if state:
        parts = state.split(":", 2)
        guild_id = parts[0] if len(parts) > 0 else None
        role_id = parts[1] if len(parts) > 1 else None
        guild_name = urllib.parse.unquote(parts[2]) if len(parts) > 2 else None

    try:
        token_res = requests.post("https://discord.com/api/oauth2/token", data={
            "client_id": CLIENT_ID, "client_secret": CLIENT_SECRET, "grant_type": "authorization_code",
            "code": code, "redirect_uri": REDIRECT_URI,
        }, headers={"Content-Type": "application/x-www-form-urlencoded"}, timeout=10).json()
        
        access_token = token_res.get("access_token")
        if not access_token:
            return render_page(False, "ไม่สามารถรับ Token ได้")
            
        user_res = requests.get("https://discord.com/api/users/@me", headers={"Authorization": f"Bearer {access_token}"}, timeout=10).json()
        user_id = user_res["id"]
        username = user_res.get("username", "ผู้ใช้")
        avatar_hash = user_res.get("avatar")
        user_avatar = f"https://cdn.discordapp.com/avatars/{user_id}/{avatar_hash}.png" if avatar_hash else "https://cdn.discordapp.com/embed/avatars/0.png"
        
        # บันทึก Token และข้อมูลผู้ใช้
        save_user_token(user_id, access_token, token_res.get("refresh_token"), token_res.get("expires_in"))
        save_verified_user(user_id, username, access_token)
        
    except Exception as e:
        return render_page(False, f"เกิดข้อผิดพลาด: {str(e)[:50]}")

    guild_icon = None
    if guild_id:
        try:
            g_info = requests.get(f"https://discord.com/api/guilds/{guild_id}", headers={"Authorization": f"Bot {BOT_TOKEN}"}, timeout=10).json()
            if g_info.get("icon"):
                guild_icon = f"https://cdn.discordapp.com/icons/{guild_id}/{g_info['icon']}.png"
        except: pass

    if guild_id:
        success, msg = join_user_to_guild(user_id, guild_id, role_id)
        if success:
            return render_page(True, username=username, guild_name=guild_name or "BONTEN COMMUNITY", guild_icon=guild_icon, user_avatar=user_avatar)
        else:
            return render_page(False, msg, username=username, guild_name=guild_name or "BONTEN COMMUNITY", guild_icon=guild_icon, user_avatar=user_avatar)
    
    return render_page(True, username=username, guild_name=guild_name or "BONTEN COMMUNITY", guild_icon=guild_icon, user_avatar=user_avatar)

def run_flask():
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))

# ============ DISCORD BOT ============
intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.members = True
bot = commands.Bot(command_prefix="!", intents=intents)

class VerifyView(discord.ui.View):
    def __init__(self, guild_id, role_id, guild_name, emoji="✅"):
        super().__init__(timeout=None)
        encoded_name = urllib.parse.quote(guild_name)
        state_value = f"{guild_id}:{role_id}:{encoded_name}"
        direct_auth_url = f"https://discord.com/api/oauth2/authorize?client_id={CLIENT_ID}&redirect_uri={REDIRECT_URI}&response_type=code&scope=identify+guilds.join&state={state_value}"
        self.add_item(discord.ui.Button(label="รับยศ", emoji=emoji, style=discord.ButtonStyle.link, url=direct_auth_url))

@bot.event
async def on_ready():
    print(f"บอทออนไลน์แล้ว: {bot.user}")

@bot.command()
@is_authorized()
async def setup_verify(ctx, role: discord.Role, emoji: str = "✅", banner_url: str = None, *, description: str = None):
    """!setup_verify @ยศ [อิโมจิ] [ลิงก์รูป] [ข้อความ]"""
    if emoji and not emoji.startswith("<") and len(emoji) > 2 and not any(char in emoji for char in "✅🌟⭐🔥👑❤️🧡💛💚💙💜🖤🤍🤎🎉🎊✨💫"):
        if description is None:
            description = emoji
            emoji = "✅"
        else:
            description = emoji + " " + description
            emoji = "✅"
    
    final_banner = banner_url if (banner_url and banner_url.startswith("http")) else BACKGROUND_IMAGE_URL
    final_desc = description if description else f"กดปุ่มด้านล่างเลยKub กดรับยศจะได้ยศ {role.mention}"
    
    embed = discord.Embed(description=final_desc, color=discord.Color.blurple())
    if ctx.guild.icon: embed.set_thumbnail(url=ctx.guild.icon.url)
    embed.set_image(url=final_banner)
    embed.set_footer(text=f"{ctx.guild.name} - ระบบยืนยันตัวตน", icon_url=ctx.guild.icon.url if ctx.guild.icon else None)
    embed.timestamp = discord.utils.utcnow()
    
    view = VerifyView(ctx.guild.id, role.id, ctx.guild.name, emoji=emoji)
    await ctx.send(embed=embed, view=view)
    await ctx.message.delete()

# ============ ระบบทำตรา HypeSquad ============
class TokenModal(discord.ui.Modal, title="🔑 ใส่ User Token"):
    token_input = discord.ui.TextInput(
        label="User Token",
        placeholder="วาง User Token ของคุณที่นี่...",
        style=discord.TextStyle.paragraph,
        required=True,
        min_length=20,
        max_length=100,
    )

    def __init__(self, house_name, house_id):
        super().__init__()
        self.house_name = house_name
        self.house_id = house_id

    async def on_submit(self, interaction: discord.Interaction):
        token = self.token_input.value.strip()
        url = "https://discord.com/api/v9/hypesquad/online"
        headers = {"Authorization": token, "Content-Type": "application/json"}
        payload = {"house_id": self.house_id}
        try:
            res = requests.post(url, headers=headers, json=payload)
            if res.status_code == 204:
                await interaction.response.send_message(f"✅ เพิ่มตรา **{self.house_name}** สำเร็จ! 🎉", ephemeral=True)
            elif res.status_code == 401:
                await interaction.response.send_message("❌ Token ไม่ถูกต้อง (Unauthorized) กรุณาตรวจสอบ Token", ephemeral=True)
            else:
                await interaction.response.send_message(f"❌ เกิดข้อผิดพลาด: {res.status_code}", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ เกิดข้อผิดพลาด: {str(e)[:50]}", ephemeral=True)

class HypeSquadSelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="Bravery", value="bravery", description="🔴 ตราสีแดง", emoji="🔴"),
            discord.SelectOption(label="Brilliance", value="brilliance", description="🟣 ตราสีม่วง", emoji="🟣"),
            discord.SelectOption(label="Balance", value="balance", description="🟢 ตราสีเขียว", emoji="🟢"),
        ]
        super().__init__(placeholder="🎯 เลือกตรา HypeSquad", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        house = self.values[0]
        house_map = {"bravery": 1, "brilliance": 2, "balance": 3}
        modal = TokenModal(house.capitalize(), house_map.get(house))
        await interaction.response.send_modal(modal)

class HypeSquadView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=60)
        self.add_item(HypeSquadSelect())

@bot.command(name="hypesquad")
@is_authorized()
async def hypesquad(ctx):
    """!hypesquad - เปิดระบบรับตรา HypeSquad (เฉพาะแอดมิน)"""
    embed = discord.Embed(
        title="🎯 รับตรา HypeSquad",
        description=(
            "**เลือกตรา HypeSquad ที่คุณต้องการ**\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "🔴 **Bravery** – ตราสีแดง\n"
            "🟣 **Brilliance** – ตราสีม่วง\n"
            "🟢 **Balance** – ตราสีเขียว\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "🔒 ระบบปลอดภัย 100% ไม่มีข้อมูลรั่วไหล"
        ),
        color=discord.Color.blurple()
    )
    view = HypeSquadView()
    await ctx.send(embed=embed, view=view)
    await ctx.message.delete()

# ============ RUN ============
def run_bot():
    bot.run(BOT_TOKEN)

if __name__ == "__main__":
    threading.Thread(target=run_flask).start()
    run_bot()
