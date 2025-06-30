import re

from openapi.network import post_floodgate_message
from openapi.tool import is_user_admin, set_maintaining_message, get_health


async def parse_floodgate_cmd(start_time,connected_clients,d): #直接传个d进来应该够用
    cmd = d.get("content", "").strip()
    cmd = re.sub(r'<@![0-9A-Za-z]+>', '', cmd).strip()
    if cmd.startswith("floodgate"):
        data = await get_health(start_time, connected_clients)
        cache = data.get('cache')
        msg = (
                f"Floodgate：{'已连接' if data['clients'] > 0 else '未连接'}机器人({data['clients']}个)\n环境：{data['env']}\n版本号：{data['version']}\n"
                f"运行时长：{data['uptime']}\nToken有效期：{data['access_token']['remain_seconds']}秒\n"
                f"内存缓存利用率：{100 * cache['message']['seq_cache_size'] / cache['message']['seq_cache_size_max']:.2f}%\n"
                f"待提交的统计数据：{cache['usage']['flush_size']}")
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