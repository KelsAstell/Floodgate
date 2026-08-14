"""指令面板与自定义菜单管理模块

封装 QQ 开放平台「指令面板 (panels)」与「自定义菜单 (menu)」相关接口，供 WebUI 调用。
参考文档:
- https://bot.q.qq.com/wiki/develop/api-v2/autogen/api/v2_panels.get.html
- https://bot.q.qq.com/wiki/develop/api-v2/autogen/api/v2_panels.post.html
- https://bot.q.qq.com/wiki/develop/api-v2/autogen/api/v2_panels_panel_id.get.html
- https://bot.q.qq.com/wiki/develop/api-v2/autogen/api/v2_panels_panel_id.put.html
- https://bot.q.qq.com/wiki/develop/api-v2/autogen/api/v2_panels_panel_id.delete.html
- https://bot.q.qq.com/wiki/develop/api-v2/autogen/api/v2_panels_panel_id_target.put.html
- https://bot.q.qq.com/wiki/develop/api-v2/autogen/api/v2_menu.get.html
- https://bot.q.qq.com/wiki/develop/api-v2/autogen/api/v2_menu.put.html
"""
import json

from fastapi import HTTPException

from config import *
from openapi.network import get_http_session
from openapi.token_manage import token_manager

# 面板生效场景
SCOPES = ["c2c", "group", "channel", "dm"]

# 面板/菜单接口频率限制（QPM），用于前端提示
QPM_LIMITS = {
    "get_panels": 30,
    "create_panel": 10,
    "get_panel_detail": 30,
    "update_panel": 10,
    "delete_panel": 10,
    "update_panel_target": 60,
    "get_menu": 30,
    "update_menu": 5,
}


async def _request(method: str, endpoint: str, payload: dict | None = None) -> dict:
    """调用面板/菜单相关 OpenAPI，统一处理鉴权、沙盒地址与空响应

    Args:
        method: HTTP 方法 (GET/POST/PUT/DELETE)
        endpoint: 接口路径，如 /v2/panels
        payload: 请求体

    Returns:
        响应 JSON 字典；接口无响应体时返回空字典

    Raises:
        HTTPException: 请求失败或鉴权失败
    """
    access_token = await token_manager.get_access_token(only_get_token=True)
    if not access_token:
        raise ValueError("无法获取 ACCESS_TOKEN，请尝试重启Floodgate")

    # 沙盒模式使用沙盒 API 地址
    base = QQ_API_BASE_SANDBOX if SANDBOX_MODE else QQ_API_BASE
    url = base + endpoint
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"QQBot {access_token}",
    }
    session = await get_http_session()
    try:
        async with session.request(
            method=method,
            url=url,
            json=payload,
            headers=headers,
            ssl=False,
        ) as response:
            if response.status == 200:
                body = await response.text()
                return json.loads(body) if body else {}
            error_text = await response.text()
            log.error(f"面板/菜单请求失败: {method} {url}, 状态码: {response.status}, 错误信息: {error_text}")
            try:
                err_data = json.loads(error_text)
                detail = f"{err_data.get('message', '未知错误')} (err_code={err_data.get('err_code', 'unknown')})"
            except json.JSONDecodeError:
                detail = error_text
            raise HTTPException(status_code=response.status, detail=detail)
    except HTTPException:
        raise
    except Exception as e:
        log.error(f"面板/菜单请求异常: {method} {url}: {e}")
        raise HTTPException(status_code=503, detail=f"请求OpenAPI时出现异常: {e}")


async def get_panels(scope: str, cursor: str = "", limit: int = 20) -> dict:
    """查询指令面板列表: GET /v2/panels?scope=&cursor=&limit=

    Args:
        scope: 生效场景，可选 c2c/group/channel/dm
        cursor: 分页游标，首次请求不传或传空串
        limit: 每页条数，默认 20，最大 50

    Returns:
        {"records": [...], "next_cursor": "...", "is_end": bool}
    """
    if scope not in SCOPES:
        raise HTTPException(status_code=400, detail=f"scope 仅支持 {'/'.join(SCOPES)}")
    limit = min(max(int(limit), 1), 50)
    query = f"scope={scope}&limit={limit}"
    if cursor:
        query += f"&cursor={cursor}"
    return await _request("GET", f"/v2/panels?{query}")


async def create_panel(panel_config: dict) -> dict:
    """创建指令面板: POST /v2/panels

    Args:
        panel_config: 请求体，包含 scope/target_type/user_openids/group_openids/panel

    Returns:
        {"panel_id": "..."}
    """
    scope = panel_config.get("scope", "")
    if scope not in SCOPES:
        raise HTTPException(status_code=400, detail=f"scope 仅支持 {'/'.join(SCOPES)}")
    return await _request("POST", "/v2/panels", panel_config)


async def get_panel_detail(panel_id: str) -> dict:
    """查询指令面板详情: GET /v2/panels/{panel_id}

    Returns:
        面板完整配置，specific 模式下含 user_openids/group_openids
    """
    return await _request("GET", f"/v2/panels/{panel_id}")


async def update_panel(panel_id: str, panel: dict) -> dict:
    """修改指令面板: PUT /v2/panels/{panel_id}

    Args:
        panel_id: 面板 ID
        panel: 面板配置 {"panel": {"items": [...], "remark": "..."}}

    Returns:
        {"version": int}
    """
    return await _request("PUT", f"/v2/panels/{panel_id}", panel)


async def delete_panel(panel_id: str) -> dict:
    """删除指令面板: DELETE /v2/panels/{panel_id}

    Returns:
        空字典
    """
    return await _request("DELETE", f"/v2/panels/{panel_id}")


async def update_panel_target(
    panel_id: str,
    op: str,
    user_openids: list[str] | None = None,
    group_openids: list[str] | None = None,
) -> dict:
    """修改指令面板关联对象: PUT /v2/panels/{panel_id}/target

    Args:
        panel_id: 面板 ID
        op: 操作类型，add（添加）或 del（移除）
        user_openids: 用户 openid 列表，仅 c2c 场景有效，一次最多 20 个
        group_openids: 群 openid 列表，仅 group 场景有效，一次最多 20 个

    Returns:
        空字典
    """
    if op not in ("add", "del"):
        raise HTTPException(status_code=400, detail="op 仅支持 add/del")
    if not user_openids and not group_openids:
        raise HTTPException(status_code=400, detail="user_openids 或 group_openids 至少提供一个")
    payload = {"op": op}
    if user_openids:
        payload["user_openids"] = user_openids
    if group_openids:
        payload["group_openids"] = group_openids
    return await _request("PUT", f"/v2/panels/{panel_id}/target", payload)


async def get_menu() -> dict:
    """查询全局自定义菜单: GET /v2/menu

    Returns:
        {"version": int, "menu": {"items": [...]}}
    """
    return await _request("GET", "/v2/menu")


async def update_menu(menu: dict) -> dict:
    """修改全局自定义菜单: PUT /v2/menu

    Args:
        menu: 菜单配置 {"menu": {"items": [...]}}，覆盖原有完整配置

    Returns:
        {"version": int}
    """
    return await _request("PUT", "/v2/menu", menu)
