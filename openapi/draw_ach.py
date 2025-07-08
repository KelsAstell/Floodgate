import asyncio
import base64
import hashlib
import math
import os
from io import BytesIO
from typing import Tuple

import aiohttp
import time
from PIL import Image, ImageDraw, ImageFont
from functools import lru_cache
from async_lru import alru_cache

from openapi.constant import ACHIEVEMENT_IDMAP, ACHIEVEMENT_DATA


async def download_or_load_image(path_part: str, fallback_path: str = "default.png") -> Image.Image:
    """
    异步下载 mcmod 图标，若本地存在则加载本地文件，否则下载后保存。

    参数:
        path_part (str): 例如 "5/59463"
        fallback_path (str): 默认图像路径，用于下载失败时返回

    返回:
        PIL.Image.Image 对象
    """
    base_url = "https://i.mcmod.cn/item/icon/32x32/"
    full_url = base_url + path_part + ".png"
    os.makedirs("./icons", exist_ok=True)
    file_name = path_part.replace("/", "_") + ".png"
    save_path = os.path.join("./icons", file_name)

    # 如果文件存在，尝试加载本地图像
    if os.path.exists(save_path):
        try:
            return Image.open(save_path)
        except Exception as e:
            print(f"加载本地图片失败: {e}")

    # 异步下载
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(full_url, timeout=10) as resp:
                if resp.status == 200:
                    data = await resp.read()
                    image = Image.open(BytesIO(data))
                    image.save(save_path)
                    return image
                else:
                    print(f"HTTP错误: 状态码 {resp.status}")
    except Exception as e:
        print(f"下载失败: {e}")

    # 加载默认图片
    try:
        return Image.open(fallback_path)
    except Exception as e:
        print(f"加载默认图片失败: {e}")
        return Image.new("RGBA", (32, 32), (255, 0, 0, 128))  # 占位图像




# === 缓存字体 ===
@lru_cache(maxsize=4)
def get_font(size: int, font_path: str = "./static/font.ttf") -> ImageFont.FreeTypeFont:
    try:
        return ImageFont.truetype(font_path, size)
    except Exception as e:
        print(f"字体加载失败: {e}")
        return ImageFont.load_default()

# === 缓存背景 ===
@lru_cache(maxsize=1)
def get_background(path: str = "./static/background.png") -> Image.Image:
    try:
        return Image.open(path).convert("RGBA")
    except Exception as e:
        print(f"背景加载失败: {e}")
        return Image.new("RGBA", (320, 64), (0, 0, 0, 255))  # 备用纯黑背景

# === 主函数 ===
CACHE_TTL = 600
CACHE_MAXSIZE = 32


# === 异步 LRU 缓存函数：返回 (timestamp, bytes) ===
@alru_cache(maxsize=CACHE_MAXSIZE)
async def _generate_achievement_image_raw_cached(id) -> Tuple[float, str]:
    ach = ACHIEVEMENT_DATA.get(id, {})
    icon = await download_or_load_image(ACHIEVEMENT_IDMAP.get(ach.get("id",1), "5/59463"))
    rarity = ach.get("rarity", "common")
    title, description = ach.get("title", "空成就"), ach.get("description", "怎么回事呢...")
    title_color = {
        "common": (255, 255, 0),
        "uncommon": (0, 255, 0),
        "rare": (0, 112, 221),
        "epic": (163, 53, 238),
    }.get(rarity.lower(), (255, 255, 255))

    background = get_background().copy()
    icon = icon.resize((32, 32), Image.Resampling.LANCZOS)
    background.paste(icon, (16, 16), icon if icon.mode == 'RGBA' else None)

    draw = ImageDraw.Draw(background)
    draw.text((56, 12), title, font=get_font(18), fill=title_color)
    draw.text((56, 34), description, font=get_font(16), fill=(255, 255, 255))

    buffer = BytesIO()
    background.save(
        buffer,
        format='GIF',
        optimize=True,
        save_all=True,
        loop=0,
        disposal=2
    )
    img_bytes = buffer.getvalue()
    return time.time(), base64.b64encode(img_bytes).decode('ascii')

def apply_grayscale(image: Image.Image) -> Image.Image:
    return image.convert("LA").convert("RGBA")

# === 对外主函数 ===
async def generate_achievement_image(
        achievement_id: int
) -> str:
    timestamp, base64_image = await _generate_achievement_image_raw_cached(achievement_id)
    if time.time() - timestamp > CACHE_TTL:
        _generate_achievement_image_raw_cached.cache_invalidate(achievement_id)
        timestamp, base64_image = await _generate_achievement_image_raw_cached(achievement_id)
    return base64_image

async def generate_achievement_page_image(user_achievements, page: int = 1, page_size: int = 10) -> str:
    all_achievements = list(ACHIEVEMENT_DATA.values())
    total_pages = math.ceil(len(all_achievements) / page_size)
    page = max(1, min(page, total_pages))
    page_achievements = all_achievements[(page - 1) * page_size: page * page_size]
    padding = 5         # 左右边距
    h_spacing = 5        # 两个成就之间的间距
    item_width, item_height = 320, 64
    columns = 2
    grid_width = item_width * columns + h_spacing + padding * 2
    rows = math.ceil(page_size / columns)
    grid_height = item_height * rows
    header_height = 40
    footer_height = 40
    canvas_width = grid_width
    canvas_height = header_height + grid_height + footer_height

    # 纯黑背景
    canvas = Image.new("RGBA", (canvas_width, canvas_height), (0, 0, 0, 255))
    draw_canvas = ImageDraw.Draw(canvas)

    # === 顶部标题 ===
    completed = sum(1 for ach in page_achievements if ach.get("id") in user_achievements)
    title_text = f"成就列表 {page}/{total_pages} - 已完成 {completed}/{len(page_achievements)}"
    title_font = get_font(26)
    title_width = draw_canvas.textlength(title_text, font=title_font)
    draw_canvas.text(((canvas_width - title_width) // 2, 6), title_text, font=title_font, fill=(255, 255, 255))

    # === 绘制每个成就 ===
    for idx, ach in enumerate(page_achievements):
        icon = await download_or_load_image(ACHIEVEMENT_IDMAP.get(ach.get("id", 1), "5/59463"))
        icon = icon.resize((32, 32), Image.Resampling.LANCZOS)
        rarity = ach.get("rarity", "common")
        if ach.get("id") not in user_achievements:
            icon = apply_grayscale(icon)
            rarity = "unfinished"

        background = get_background().copy()
        background.paste(icon, (16, 16), icon if icon.mode == 'RGBA' else None)

        title_color = {
            "unfinished": (192, 192, 192),
            "common": (255, 255, 0),
            "uncommon": (0, 255, 0),
            "rare": (0, 112, 221),
            "epic": (163, 53, 238),
        }.get(rarity.lower(), (255, 255, 255))

        draw = ImageDraw.Draw(background)
        draw.text((56, 12), ach.get("title", "空成就"), font=get_font(18), fill=title_color)
        draw.text((56, 34), ach.get("description", "怎么回事呢..."), font=get_font(16), fill=(255, 255, 255))

        row = idx // columns
        col = idx % columns
        x = padding + col * (item_width + h_spacing)
        y = header_height + row * item_height
        canvas.paste(background, (x, y))

    # === 底部标语 ===
    footer_text = "DeluxeBOT-冒险旅程 | By 大以巴狼艾斯，使用 Floodgate 进行渲染计算"
    footer_font = get_font(18)
    footer_width = draw_canvas.textlength(footer_text, font=footer_font)
    draw_canvas.text(((canvas_width - footer_width) // 2, header_height + grid_height + 10), footer_text, font=footer_font, fill=(255, 255, 0))

    # === 输出图像 ===
    canvas = canvas.convert("RGB")
    buffer = BytesIO()
    canvas.save(buffer, format='JPEG')
    return base64.b64encode(buffer.getvalue()).decode('ascii')

#b64_data = asyncio.run(generate_achievement_image(5))
# b64_data = asyncio.run(generate_achievement_page_image([11,7,8,10],1))
# print(b64_data)
