import re
import time

from config import BOT_NAME, TRANSPARENT_OPENID, ACHIEVEMENT_PERSIST
from openapi.database import get_dau_today, get_achievement_list, get_or_create_digit_id
from openapi.draw_ach import generate_achievement_page_image
from openapi.network import post_floodgate_message, post_im_message, post_floodgate_rich_message
from openapi.tool import is_user_admin, set_maintaining_message, get_health, get_dau_history


async def parse_floodgate_cmd(start_time,connected_clients,payload,headers): #直接传个d进来应该够用，我错了
    d = payload.get("d", {})
    cmd = d.get("content", "").strip()
    cmd = re.sub(r'<@![0-9A-Za-z]+>', '', cmd).strip()
    if not cmd.startswith("~"):
        return
    cmd = cmd[1:]
    if cmd.startswith("fg"):
        data = await get_health(start_time, connected_clients)
        cache = data.get('cache')
        x_timestamp = int(headers.get('x-signature-timestamp',0))
        current_ts = time.time()
        delta_ms = abs((current_ts - x_timestamp) * 1000)
        if delta_ms > 1000:
            pushdown_time =  f"{delta_ms / 1000:.2f} 秒"
        else:
            pushdown_time =  f"{delta_ms:.2f} 毫秒"
        if await is_user_admin(d):
            msg = (
                f"Floodgate：{'✅已连接' if data['clients'] > 0 else '❌未连接'}({data['clients']}个实例)\n版本号：{data['version']}-{data['env']}\n"
                f"运行时长：{data['uptime']}\nToken有效期：{data['access_token']['remain_seconds']}秒\n"
                f"消息补发：成功({data['send_failed'].get('success', 0)}) | 失败({data['send_failed'].get('failed', 0)})\n"
                f"内存缓存利用率：{100 * cache['message']['seq_cache_size'] / cache['message']['seq_cache_size_max']:.2f}%\n"
                f"待提交的统计：{cache['usage']['flush_size']}\n消息下发：{'✅正常' if delta_ms < 2000 else '❌异常'}({pushdown_time})")
        else:
            msg = (
                f"Floodgate：{'✅已连接' if data['clients'] > 0 else '❌未连接'}({data['clients']}个实例)\n版本号：{data['version']}\n"
                f"运行时长：{data['uptime']}\n"
                f"消息下发：{'✅正常' if delta_ms < 2000 else '❌异常'}({pushdown_time})")
        return await post_floodgate_message(msg, d)
    elif cmd.startswith("offline"):
        if await is_user_admin(d):
            parts = cmd.split(maxsplit=1)
            if len(parts) > 1:
                maintenance_message = parts[1]
            else:
                maintenance_message = "当前暂时没有具体维护信息"
            await set_maintaining_message(maintenance_message)
            return await post_floodgate_message(f"成功将维护信息设置为：{maintenance_message}", d)
    elif cmd.startswith("dau"):
        if await is_user_admin(d):
            dau_data = await get_dau_today()
            history_dau_msg = await get_dau_history()
            return await post_floodgate_message(f"---{BOT_NAME}数据统计---\n活跃用户数：{dau_data.get('dau', 0)}\n总调用数：{dau_data.get('dai', 0)}\n{history_dau_msg}", d)
    elif cmd.startswith("成就"):
        match = re.search(r"成就\s*(\d*)", cmd)
        page = 1  # 默认页
        if match:
            try:
                page = int(match.group(1)) if match.group(1) else 1
            except ValueError:
                page = 1  # fallback
        user_id = d.get("author", {}).get("union_openid") if TRANSPARENT_OPENID else await get_or_create_digit_id(d.get("author", {}).get("union_openid"))
        user_achievements = await get_achievement_list(str(user_id)) if ACHIEVEMENT_PERSIST else []
        base64_img = await generate_achievement_page_image(user_achievements, page=page)
        return await post_floodgate_rich_message(f"命令：~成就 x 可查看指定的页\n例如：\n~成就 2", base64_img, d)