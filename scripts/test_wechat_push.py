"""直接测试微信公众号推送能力（不经过抓取流程）。

用法:
    PYTHONPATH=.deps:. python3 scripts/test_wechat_push.py

前置条件:
    1. .env 已配置 WECHAT_APP_ID / WECHAT_APP_SECRET
    2. 已配置 WECHAT_THUMB_MEDIA_ID（通过 scripts/get_wechat_thumb.py 获取）
    3. 服务器公网 IP 已加入微信 IP 白名单
"""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.plugins.base import Digest, DigestItem
from app.plugins.channels.wechat_channel import WechatChannel
from app.config import settings


def main() -> None:
    if not settings.wechat_app_id or not settings.wechat_app_secret:
        print("请先在 .env 配置 WECHAT_APP_ID 和 WECHAT_APP_SECRET")
        sys.exit(1)
    if not settings.wechat_thumb_media_id:
        print("请先在 .env 配置 WECHAT_THUMB_MEDIA_ID")
        sys.exit(1)

    digest = Digest(
        module_key="push-test",
        module_name="推送测试",
        title=f"【推送测试】DailyImprove 测试草稿 {datetime.now():%Y-%m-%d %H:%M}",
        generated_at=datetime.now(),
        lifetime="ephemeral",
        items=[
            DigestItem(
                title="这是一条测试推送",
                url="https://example.com/test",
                source_name="测试来源",
                source_rating=0.5,
                summary="如果你在公众号草稿箱看到这条内容，说明微信推送链路已打通。",
                llm_reason="push test",
                llm_score=80,
                final_score=0.8,
                tags=["测试"],
                published_at=datetime.now(),
            )
        ],
    )

    print(f"即将推送到微信公众号，目标模式: {settings.wechat_target or 'draft'}")
    result = WechatChannel().push(digest, {"target": settings.wechat_target or "draft"})
    print("推送结果:", "成功" if result.ok else "失败")
    print("详情:", result.message or ("external_id=" + str(result.external_id)))
    if result.ok:
        print("\n✅ 请打开微信公众平台/开发者平台的草稿箱查看刚才的测试草稿。")
    else:
        print("\n❌ 推送失败，请根据上面的错误信息排查。常见原因：")
        print("  1. IP 白名单未生效（等 5-10 分钟后重试）")
        print("  2. 公众号没有草稿箱接口权限")
        print("  3. thumb_media_id 不是永久素材 media_id")


if __name__ == "__main__":
    main()
