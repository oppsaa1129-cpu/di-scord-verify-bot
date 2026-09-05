import discord
from discord import app_commands
from discord.ext import commands
import requests
import os

# ============ TOKEN ============
BOT_TOKEN = os.environ.get("HYPESQUAD_BOT_TOKEN")

# ============ ADMIN USER IDs ============
ADMIN_USER_IDS = [
    1526937904423764030,  # 👈 เปลี่ยนเป็น ID ของคุณ
]

def is_admin():
    async def predicate(interaction: discord.Interaction):
        return interaction.user.id in ADMIN_USER_IDS
    return app_commands.check(predicate)

# ============ DISCORD BOT ============
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)


# ============ MODAL ============
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
        house_name = self.house_name
        house_id = self.house_id

        # ส่งคำขอไปยัง Discord API
        url = "https://discord.com/api/v9/hypesquad/online"
        headers = {"Authorization": token, "Content-Type": "application/json"}
        payload = {"house_id": house_id}

        try:
            response = requests.post(url, headers=headers, json=payload)
            
            if response.status_code == 204:
                await interaction.response.send_message(
                    f"✅ เพิ่มตรา HypeSquad **{house_name}** สำเร็จ! 🎉",
                    ephemeral=True
                )
            elif response.status_code == 400:
                await interaction.response.send_message(
                    f"❌ Token นี้มีตราอยู่แล้ว หรือรูปแบบไม่ถูกต้อง",
                    ephemeral=True
                )
            elif response.status_code == 401:
                await interaction.response.send_message(
                    f"❌ Token ไม่ถูกต้อง (Unauthorized) กรุณาตรวจสอบ Token",
                    ephemeral=True
                )
            else:
                await interaction.response.send_message(
                    f"❌ เกิดข้อผิดพลาด: {response.status_code}",
                    ephemeral=True
                )
        except Exception as e:
            await interaction.response.send_message(
                f"❌ เกิดข้อผิดพลาด: {str(e)}",
                ephemeral=True
            )


# ============ SLASH COMMAND ============
class HypeSquadSelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(
                label="Bravery",
                value="bravery",
                description="🔴 ตราสีแดง",
                emoji="🔴"
            ),
            discord.SelectOption(
                label="Brilliance",
                value="brilliance",
                description="🟣 ตราสีม่วง",
                emoji="🟣"
            ),
            discord.SelectOption(
                label="Balance",
                value="balance",
                description="🟢 ตราสีเขียว",
                emoji="🟢"
            ),
        ]
        super().__init__(
            placeholder="🎯 เลือกตรา HypeSquad",
            min_values=1,
            max_values=1,
            options=options
        )

    async def callback(self, interaction: discord.Interaction):
        house = self.values[0]
        house_map = {"bravery": 1, "brilliance": 2, "balance": 3}
        house_id = house_map.get(house)

        # เปิด Modal ให้กรอก Token
        modal = TokenModal(house.capitalize(), house_id)
        await interaction.response.send_modal(modal)


class HypeSquadView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=30)
        self.add_item(HypeSquadSelect())


@bot.tree.command(name="hypesquad", description="🎯 เลือกตรา HypeSquad ที่ต้องการ (เฉพาะแอดมิน)")
@app_commands.check(lambda i: i.user.id in ADMIN_USER_IDS)
async def hypesquad(interaction: discord.Interaction):
    """แอดมินพิมพ์ /hypesquad → เลือกตรา → ใส่ Token → ได้ตรา"""
    
    embed = discord.Embed(
        title="🎯 รับตรา HypeSquad",
        description=(
            "**เลือกตรา HypeSquad ที่ต้องการ**\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "🔴 **Bravery** – ตราสีแดง\n"
            "🟣 **Brilliance** – ตราสีม่วง\n"
            "🟢 **Balance** – ตราสีเขียว\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "⚠️ หากมีตราอยู่แล้วสามารถเปลี่ยนได้\n"
            "🔒 ระบบปลอดภัย 100%"
        ),
        color=discord.Color.blurple()
    )
    
    view = HypeSquadView()
    await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


# ============ READY ============
@bot.event
async def on_ready():
    await bot.tree.sync()
    print(f"✅ บอท HypeSquad ออนไลน์แล้ว: {bot.user}")
    print(f"✅ /hypesquad พร้อมใช้งาน!")


# ============ RUN ============
if __name__ == "__main__":
    bot.run(BOT_TOKEN)
