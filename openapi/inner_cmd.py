import re
import time

from config import BOT_NAME, TRANSPARENT_OPENID, ACHIEVEMENT_PERSIST, OAUTH_LOGIN_TOKEN_TTL, log
from openapi.database import get_dau_today, get_achievement_list, get_or_create_digit_id, get_gm_blacklist, add_group_to_gm_blacklist, remove_group_from_gm_blacklist, get_gm_whitelist, add_group_to_gm_whitelist, remove_group_from_gm_whitelist
from openapi.draw_ach import generate_achievement_page_image
from openapi.network import post_floodgate_message, post_im_message, post_floodgate_rich_message, post_floodgate_markdown_message
from openapi.tool import is_user_admin, set_maintaining_message, get_health, get_dau_history


async def parse_floodgate_cmd(start_time,connected_clients,payload,headers): #直接传个d进来应该够用，我错了
    d = payload.get("d", {})
    cmd = d.get("content", "").strip()
    cmd = re.sub(r'<@!?[0-9A-Za-z]+>\s*', '', cmd).strip()
    if not cmd.startswith("~"):
        return
    cmd = cmd[1:]
    if cmd.startswith("health"):
        data = await get_health(start_time, connected_clients)
        cache = data.get('cache')
        x_timestamp = int(headers.get('x-signature-timestamp',0))
        current_ts = time.time()
        delta_ms = abs((current_ts - x_timestamp) * 1000)
        if delta_ms > 1000:
            pushdown_time =  f"{delta_ms / 1000:.2f} 秒"
        else:
            pushdown_time =  f"{delta_ms:.2f} 毫秒"
        msg = (
                f"Floodgate：{'✅已连接' if data['clients'] > 0 else '❌未连接'}({data['clients']}个实例)\n版本号：{data['version']}-{data['env']}\n"
                f"运行时长：{data['uptime']}\nToken有效期：{data['access_token']['remain_seconds']}秒\n"
                f"消息补发：成功({data['send_failed'].get('success', 0)}) | 失败({data['send_failed'].get('failed', 0)})\n"
                f"内存缓存利用率：{100 * cache['message']['seq_cache_size'] / cache['message']['seq_cache_size_max']:.2f}%\n"
                f"待提交的统计：{cache['usage']['flush_size']}\n消息下发：{'✅正常' if delta_ms < 1000 else '❌缓慢'}({pushdown_time})")
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
    elif cmd.startswith("gm_blacklist"):
        if not await is_user_admin(d):
            return await post_floodgate_message("权限不足，仅管理员可管理全量消息黑名单", d)
        parts = cmd.split(maxsplit=1)
        if len(parts) <= 1:
            group_list = await get_gm_blacklist()
            if not group_list:
                return await post_floodgate_message("全量消息黑名单为空\n用法：\n~gm_blacklist add <群数字ID>  - 拉黑群\n~gm_blacklist remove <群数字ID> - 解除拉黑\n~gm_blacklist list - 列出黑名单", d)
            return await post_floodgate_message(f"全量消息黑名单（{len(group_list)}个群）：\n" + "\n".join(group_list), d)
        sub_cmd = parts[1].strip()
        if sub_cmd == "list":
            group_list = await get_gm_blacklist()
            if not group_list:
                return await post_floodgate_message("全量消息黑名单为空", d)
            return await post_floodgate_message(f"全量消息黑名单（{len(group_list)}个群）：\n" + "\n".join(group_list), d)
        elif sub_cmd.startswith("add"):
            add_parts = sub_cmd.split(maxsplit=1)
            if len(add_parts) <= 1:
                return await post_floodgate_message("请提供要拉黑的群数字ID\n例：~gm_blacklist add 123456", d)
            group_id = add_parts[1].strip()
            await add_group_to_gm_blacklist(group_id)
            log.success(f"管理员将群 {group_id} 加入全量消息黑名单")
            return await post_floodgate_message(f"已将群 {group_id} 加入全量消息黑名单", d)
        elif sub_cmd.startswith("remove"):
            remove_parts = sub_cmd.split(maxsplit=1)
            if len(remove_parts) <= 1:
                return await post_floodgate_message("请提供要解除拉黑的群数字ID\n例：~gm_blacklist remove 123456", d)
            group_id = remove_parts[1].strip()
            await remove_group_from_gm_blacklist(group_id)
            log.success(f"管理员将群 {group_id} 从全量消息黑名单中移除")
            return await post_floodgate_message(f"已将群 {group_id} 从全量消息黑名单中移除", d)
        else:
            return await post_floodgate_message("未知子命令，可用：add <群ID> | remove <群ID> | list", d)
    elif cmd.startswith("gm_whitelist"):
        if not await is_user_admin(d):
            return await post_floodgate_message("权限不足，仅管理员可管理全量消息白名单", d)
        parts = cmd.split(maxsplit=1)
        if len(parts) <= 1:
            group_list = await get_gm_whitelist()
            if not group_list:
                return await post_floodgate_message("全量消息白名单为空\n用法：\n~gm_whitelist add <群数字ID>  - 添加到白名单\n~gm_whitelist remove <群数字ID> - 从白名单移除\n~gm_whitelist list - 列出白名单", d)
            return await post_floodgate_message(f"全量消息白名单（{len(group_list)}个群）：\n" + "\n".join(group_list), d)
        sub_cmd = parts[1].strip()
        if sub_cmd == "list":
            group_list = await get_gm_whitelist()
            if not group_list:
                return await post_floodgate_message("全量消息白名单为空", d)
            return await post_floodgate_message(f"全量消息白名单（{len(group_list)}个群）：\n" + "\n".join(group_list), d)
        elif sub_cmd.startswith("add"):
            add_parts = sub_cmd.split(maxsplit=1)
            if len(add_parts) <= 1:
                return await post_floodgate_message("请提供要添加到白名单的群数字ID\n例：~gm_whitelist add 123456", d)
            group_id = add_parts[1].strip()
            await add_group_to_gm_whitelist(group_id)
            log.success(f"管理员将群 {group_id} 加入全量消息白名单")
            return await post_floodgate_message(f"已将群 {group_id} 加入全量消息白名单", d)
        elif sub_cmd.startswith("remove"):
            remove_parts = sub_cmd.split(maxsplit=1)
            if len(remove_parts) <= 1:
                return await post_floodgate_message("请提供要从白名单移除的群数字ID\n例：~gm_whitelist remove 123456", d)
            group_id = remove_parts[1].strip()
            await remove_group_from_gm_whitelist(group_id)
            log.success(f"管理员将群 {group_id} 从全量消息白名单中移除")
            return await post_floodgate_message(f"已将群 {group_id} 从全量消息白名单中移除", d)
        else:
            return await post_floodgate_message("未知子命令，可用：add <群ID> | remove <群ID> | list", d)
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
    elif cmd.startswith("login"):
        # 安全性限制：仅允许在私聊环境执行
        group_openid = d.get("group_openid") or d.get("channel_id")
        if group_openid:
            return await post_floodgate_message("为保护您的安全，请在私聊中使用 ~login 命令", d)
        
        from openapi.oauth import oauth_manager
        user_openid = d.get("author", {}).get("union_openid")
        if not user_openid:
            return await post_floodgate_message("无法获取用户身份，请稍后重试", d)
        token = oauth_manager.generate_login_token(user_openid)
        markdown_content = {"content": f"Oauth登录令牌：<qqbot-cmd-input text=\"{token}\" show=\"点击后，在底部输入框内显示\"/>\n有效期{OAUTH_LOGIN_TOKEN_TTL}秒，谨防泄露。"}
        return await post_floodgate_markdown_message(markdown_content, d)