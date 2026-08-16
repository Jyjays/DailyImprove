from app.plugins.base import ChannelPlugin
from app.plugins.channels.feishu_channel import FeishuDocChannel
from app.plugins.channels.file_channel import FileChannel
from app.plugins.channels.telegram_channel import TelegramChannel
from app.plugins.channels.wechat_channel import WechatChannel

CHANNEL_PLUGINS: dict[str, ChannelPlugin] = {
    cls.name: cls()
    for cls in [FileChannel, WechatChannel, FeishuDocChannel, TelegramChannel]
}


def get_channel_plugin(name: str) -> ChannelPlugin:
    if name not in CHANNEL_PLUGINS:
        raise KeyError(f"未知推送渠道: {name}，已注册: {list(CHANNEL_PLUGINS)}")
    return CHANNEL_PLUGINS[name]
