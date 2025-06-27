from config import log
async def check_config():
    from config import BOT_SECRET, BOT_APPID, SANDBOX_CHANNEL_ID
    errors = []
    warnings = []
    if not isinstance(BOT_SECRET, str) or len(BOT_SECRET.strip()) == 0:
        errors.append("BOT_SECRET 未填写")
    if not isinstance(BOT_APPID, int) or BOT_APPID <= 0:
        errors.append("BOT_APPID 必须为正整数")
    if not isinstance(SANDBOX_CHANNEL_ID, int):
        errors.append("SANDBOX_CHANNEL_ID 必须为整数")
    if SANDBOX_CHANNEL_ID == 0:
        warnings.append("SANDBOX_CHANNEL_ID 未填，使用 /upload_image 接口时需要在请求体里提供 channel_id，或填写配置中的 SANDBOX_CHANNEL_ID")
    if errors:
        for error in errors:
            log.error(f"[配置错误] {error}")
        log.error(f"[配置错误] 请在config.py中填写正确信息后重试！")
        exit(1)
    log.success("已通过基础配置检查")
    return True
