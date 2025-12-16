import io
import os
import asyncio
import httpx
import base64
from contextlib import asynccontextmanager
from fastapi import FastAPI, Response, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from PIL import Image, ImageDraw, ImageFont
from concurrent.futures import ThreadPoolExecutor

# ================= ADJUSTMENT SETTINGS =================
AVATAR_ZOOM = 1.26
AVATAR_SHIFT_Y = 0
AVATAR_SHIFT_X = 0

BANNER_START_X = 0.25
BANNER_START_Y = 0.29
BANNER_END_X = 0.81
BANNER_END_Y = 0.65
# ======================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    await client.aclose()
    process_pool.shutdown()

app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

INFO_API_URL = "https://fffinfo.tsunstudio.pw/get"

BASE64 = "aHR0cHM6Ly9jZG4uanNkZWxpdnIubmV0L2doL1NoYWhHQ3JlYXRvci9pY29uQG1haW4vUE5H"
info_URL = base64.b64decode(BASE64).decode("utf-8")

FONT_FILE = "arial_unicode_bold.otf"
FONT_CHEROKEE = "NotoSansCherokee.ttf"

client = httpx.AsyncClient(
    headers={"User-Agent": "Mozilla/5.0"},
    timeout=10.0,
    follow_redirects=True
)

process_pool = ThreadPoolExecutor(max_workers=4)

def load_unicode_font(size, font_file=FONT_FILE):
    try:
        font_path = os.path.join(os.path.dirname(__file__), font_file)
        if os.path.exists(font_path):
            return ImageFont.truetype(font_path, size)
    except:
        pass
    return ImageFont.load_default()

async def fetch_image_bytes(item_id):
    if not item_id or str(item_id) == "0":
        return None
    try:
        url = f"{info_URL}/{item_id}.png"
        r = await client.get(url)
        if r.status_code == 200:
            return r.content
    except:
        pass
    return None

def bytes_to_image(img_bytes):
    if img_bytes:
        return Image.open(io.BytesIO(img_bytes)).convert("RGBA")
    return Image.new("RGBA", (100, 100), (0, 0, 0, 0))

# ================= IMAGE PROCESS =================
def process_banner_image(data, avatar_bytes, banner_bytes, pin_bytes):
    avatar_img = bytes_to_image(avatar_bytes)
    banner_img = bytes_to_image(banner_bytes)
    pin_img = bytes_to_image(pin_bytes)

    level = str(data.get("AccountLevel", "0"))
    name = data.get("AccountName", "Unknown")
    guild = data.get("GuildName", "")

    TARGET_HEIGHT = 400

    # ---------- Avatar crop ----------
    zoom_size = int(TARGET_HEIGHT * AVATAR_ZOOM)
    avatar_img = avatar_img.resize((zoom_size, zoom_size), Image.LANCZOS)

    cx = zoom_size // 2
    cy = zoom_size // 2
    half = TARGET_HEIGHT // 2

    avatar_img = avatar_img.crop((
        cx - half - AVATAR_SHIFT_X,
        cy - half - AVATAR_SHIFT_Y,
        cx + half - AVATAR_SHIFT_X,
        cy + half - AVATAR_SHIFT_Y
    ))

    av_w, av_h = avatar_img.size

    # ---------- Banner crop ----------
    b_w, b_h = banner_img.size
    if b_w > 50 and b_h > 50:
        banner_img = banner_img.rotate(3, expand=True)
        b_w, b_h = banner_img.size

        banner_img = banner_img.crop((
            b_w * BANNER_START_X,
            b_h * BANNER_START_Y,
            b_w * BANNER_END_X,
            b_h * BANNER_END_Y
        ))

    b_w, b_h = banner_img.size
    new_banner_w = int(TARGET_HEIGHT * (b_w / b_h) * 2) if b_h else 800
    banner_img = banner_img.resize((new_banner_w, TARGET_HEIGHT), Image.LANCZOS)

    final_w = av_w + new_banner_w
    combined = Image.new("RGBA", (final_w, TARGET_HEIGHT))

    combined.paste(avatar_img, (0, 0))
    combined.paste(banner_img, (av_w, 0))

    draw = ImageDraw.Draw(combined)

    font_large = load_unicode_font(125)
    font_large_c = load_unicode_font(125, FONT_CHEROKEE)
    font_small = load_unicode_font(95)
    font_small_c = load_unicode_font(95, FONT_CHEROKEE)
    font_level = load_unicode_font(50)

    def is_cherokee(c):
        return 0x13A0 <= ord(c) <= 0x13FF or 0xAB70 <= ord(c) <= 0xABBF

    # ---------- Name draw with max width (NO CUT ISSUE) ----------
    MAX_NAME_WIDTH = final_w - (av_w + 120)

    def draw_text_limited(x, y, text, f_main, f_alt, stroke, max_width):
        cur_x = x
        for ch in text:
            f = f_alt if is_cherokee(ch) else f_main
            ch_w = f.getlength(ch)
            if cur_x + ch_w > x + max_width:
                break
            for dx in range(-stroke, stroke + 1):
                for dy in range(-stroke, stroke + 1):
                    draw.text((cur_x + dx, y + dy), ch, font=f, fill="black")
            draw.text((cur_x, y), ch, font=f, fill="white")
            cur_x += ch_w

    draw_text_limited(av_w + 65, 40, name, font_large, font_large_c, 4, MAX_NAME_WIDTH)
    draw_text_limited(av_w + 65, 220, guild, font_small, font_small_c, 3, MAX_NAME_WIDTH)

    # ---------- Pin ----------
    if pin_img.size != (100, 100):
        pin_img = pin_img.resize((130, 130), Image.LANCZOS)
        combined.paste(pin_img, (0, TARGET_HEIGHT - 130), pin_img)

    # ---------- Level (NO BLACK BOX, TRANSPARENT) ----------
    lvl_text = f"Lvl.{level}"
    w, h = draw.textbbox((0, 0), lvl_text, font=font_level)[2:]
    draw.text(
        (final_w - w - 30, TARGET_HEIGHT - h - 40),
        lvl_text,
        font=font_level,
        fill="white"
    )

    out = io.BytesIO()
    combined.save(out, "PNG")
    out.seek(0)
    return out

# ================= ROUTES =================
@app.get("/")
async def home():
    return {
        "status": "Banner API Running",
        "endpoint": "/profile?uid=UID",
        "credit": "This Banner API Developed & Managed by OfficialShubhamKumar • Terminator API"
    }

@app.get("/profile")
async def get_banner(uid: str):
    if not uid:
        raise HTTPException(status_code=400, detail="UID required")

    r = await client.get(f"{INFO_API_URL}?uid={uid}")
    if r.status_code != 200:
        raise HTTPException(status_code=502, detail="Info API Error")

    data = r.json()
    account = data.get("AccountInfo", {})
    equip = data.get("EquippedItemsInfo", {})
    guild = data.get("GuildInfo", {})

    if not account:
        raise HTTPException(status_code=404, detail="Account not found")

    avatar_task = fetch_image_bytes(equip.get("EquippedAvatarId"))
    banner_task = fetch_image_bytes(equip.get("EquippedBannerId"))
    pin_task = fetch_image_bytes(equip.get("pinId"))

    avatar, banner, pin = await asyncio.gather(avatar_task, banner_task, pin_task)

    banner_data = {
        "AccountLevel": account.get("AccountLevel", "0"),
        "AccountName": account.get("AccountName", "Unknown"),
        "GuildName": guild.get("GuildName", "")
    }

    loop = asyncio.get_event_loop()
    img = await loop.run_in_executor(
        process_pool,
        process_banner_image,
        banner_data,
        avatar,
        banner,
        pin
    )

    return Response(content=img.getvalue(), media_type="image/png", headers={
        "Cache-Control": "public, max-age=300"
    })
