import base64
import hashlib
import os
from io import BytesIO
from typing import Tuple

import aiohttp
import asyncio
import time
from PIL import Image, ImageDraw, ImageFont
from functools import lru_cache
from async_lru import alru_cache

from openapi.constant import ACHIEVEMENT_IDMAP


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
async def _generate_achievement_image_raw_cached(achievement_id: int, title: str, description: str, rarity: str) -> Tuple[float, str]:
    icon = await download_or_load_image(ACHIEVEMENT_IDMAP.get(achievement_id, "5/59463"))
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

# === 对外主函数 ===
async def generate_achievement_image(
        achievement_id: int,
        title: str,
        description: str,
        rarity: str = "common"
) -> str:
    """
    异步生成成就图片（带异步 LRU 缓存 + 过期判断）。
    """
    timestamp, base64_image = await _generate_achievement_image_raw_cached(
        achievement_id, title, description, rarity
    )

    if time.time() - timestamp > CACHE_TTL:
        # 缓存过期，强制刷新：使用 cache.invalidate() 重建
        _generate_achievement_image_raw_cached.cache_invalidate(
            achievement_id, title, description, rarity
        )
        timestamp, base64_image = await _generate_achievement_image_raw_cached(
            achievement_id, title, description, rarity
        )

    return base64_image

# b64_data = asyncio.run(generate_achievement_image("5/59463", "测试", "这是测试", "common"))
# print(b64_data)
