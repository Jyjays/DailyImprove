"""上传微信永久缩略图素材，获取 thumb_media_id。

用法:
    python3 scripts/get_wechat_thumb.py 封面图.jpg
    python3 scripts/get_wechat_thumb.py 封面图.jpg --type image

先在 .env 配置 WECHAT_APP_ID 和 WECHAT_APP_SECRET。
默认按 type=thumb 上传；如果微信返回类型错误，可尝试 --type image。
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx

from app.config import settings


def get_access_token() -> str:
    resp = httpx.get(
        "https://api.weixin.qq.com/cgi-bin/token",
        params={
            "grant_type": "client_credential",
            "appid": settings.wechat_app_id,
            "secret": settings.wechat_app_secret,
        },
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    if "access_token" not in data:
        errcode = data.get("errcode")
        if errcode == 40164:
            raise RuntimeError(
                f"获取 access_token 失败：{data}\n"
                "原因：当前服务器公网 IP 未加入微信 IP 白名单。\n"
                "解决：登录微信开发者平台/公众平台 → 开发配置/基本配置 → IP 白名单，"
                "把错误信息里的 IP（如 112.8.182.222）添加进去，保存后 5-10 分钟生效。"
            )
        raise RuntimeError(f"获取 access_token 失败: {data}")
    return data["access_token"]


def upload_thumb(file_path: Path, material_type: str = "thumb") -> str:
    token = get_access_token()
    url = f"https://api.weixin.qq.com/cgi-bin/material/add_material"
    with file_path.open("rb") as f:
        resp = httpx.post(
            url,
            params={"access_token": token, "type": material_type},
            files={"media": (file_path.name, f)},
            timeout=60,
        )
    resp.raise_for_status()
    data = resp.json()
    print("微信返回:", data)
    if "media_id" not in data:
        raise RuntimeError(f"上传失败: {data}")
    return data["media_id"]


def main() -> None:
    parser = argparse.ArgumentParser(description="上传微信封面缩略图，获取 thumb_media_id")
    parser.add_argument("image", help="图片路径")
    parser.add_argument("--type", default="thumb", choices=["thumb", "image"],
                        help="素材类型，默认 thumb（永久缩略图）；失败时可试 image")
    args = parser.parse_args()

    if not settings.wechat_app_id or not settings.wechat_app_secret:
        print("请先在 .env 中配置 WECHAT_APP_ID 和 WECHAT_APP_SECRET")
        sys.exit(1)

    image = Path(args.image).resolve()
    if not image.exists():
        print(f"文件不存在: {image}")
        sys.exit(1)

    media_id = upload_thumb(image, args.type)
    print(f"\n✅ thumb_media_id: {media_id}")
    print("把它填到 .env：")
    print(f"  WECHAT_THUMB_MEDIA_ID={media_id}")


if __name__ == "__main__":
    main()
