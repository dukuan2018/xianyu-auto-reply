import json
import re
import time
from typing import Any, Dict, Optional, Tuple

import aiohttp
from loguru import logger

from db_manager import db_manager
from utils.xianyu_utils import generate_sign, trans_cookies


APP_KEY = "34839810"
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; WOW64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/139.0.0.0 VER-AN00"
)


def _as_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, ensure_ascii=False, default=str)
    except Exception:
        return str(value)


def is_token_expired_response(body: Any) -> bool:
    text = _as_text(body)
    return "FAIL_SYS_TOKEN_EXOIRED" in text or "FAIL_SYS_TOKEN_EXPIRED" in text or "令牌过期" in text


def is_session_expired_response(body: Any) -> bool:
    text = _as_text(body)
    return "FAIL_SYS_SESSION_EXPIRED" in text or "Session过期" in text


def is_risk_or_validate_response(body: Any) -> bool:
    text = _as_text(body)
    return (
        "FAIL_SYS_USER_VALIDATE" in text
        or "RGV587_ERROR" in text
        or "被挤爆" in text
        or "验证" in text and "滑" in text
    )


def extract_set_cookies(response: aiohttp.ClientResponse) -> Dict[str, str]:
    cookies: Dict[str, str] = {}
    try:
        for name, morsel in response.cookies.items():
            cookies[name] = morsel.value
    except Exception:
        pass

    raw_values = []
    try:
        raw_values.extend(response.headers.getall("Set-Cookie", []))
    except Exception:
        raw = response.headers.get("Set-Cookie")
        if raw:
            raw_values.append(raw)

    for raw in raw_values:
        for part in re.split(r",\s*(?=[^;,=\s]+=[^;]+)", raw or ""):
            pair = part.split(";", 1)[0].strip()
            if not pair or "=" not in pair:
                continue
            name, value = pair.split("=", 1)
            if name:
                cookies[name.strip()] = value.strip()
    return cookies


def merge_cookie_string(old_cookie: str, new_cookies: Dict[str, str]) -> str:
    cookie_dict = trans_cookies(old_cookie or "")
    changed = False
    for key, value in (new_cookies or {}).items():
        if not key:
            continue
        if cookie_dict.get(key) != value:
            cookie_dict[key] = value
            changed = True
    if not changed:
        return old_cookie or ""
    return "; ".join(f"{key}={value}" for key, value in cookie_dict.items())


def persist_cookie(cookie_id: str, cookie_value: str) -> None:
    if not cookie_id or not cookie_value:
        return
    try:
        db_manager.save_cookie(cookie_id, cookie_value)
    except Exception as exc:
        logger.warning(f"[MTOP] save merged cookie failed: cookie_id={cookie_id}, error={exc}")


def build_mtop_request(
    cookie_value: str,
    api: str,
    data_obj: Dict[str, Any],
    *,
    v: str = "1.0",
    response_type: str = "json",
    extra_params: Optional[Dict[str, str]] = None,
) -> Tuple[str, Dict[str, str], Dict[str, str]]:
    cookie_dict = trans_cookies(cookie_value or "")
    token_value = cookie_dict.get("_m_h5_tk", "")
    token = token_value.split("_", 1)[0] if token_value else ""
    if not token:
        raise ValueError("_m_h5_tk token not found in cookie")

    timestamp = str(int(time.time() * 1000))
    data_val = json.dumps(data_obj or {}, ensure_ascii=False, separators=(",", ":"))
    params = {
        "jsv": "2.7.2",
        "appKey": APP_KEY,
        "t": timestamp,
        "sign": generate_sign(timestamp, token, data_val),
        "v": v,
        "type": response_type,
        "accountSite": "xianyu",
        "dataType": "json",
        "timeout": "20000",
        "api": api,
        "sessionOption": "AutoLoginOnly",
    }
    if extra_params:
        params.update({k: v for k, v in extra_params.items() if v is not None})
    return data_val, params, cookie_dict


async def mtop_call(
    *,
    cookie_id: str,
    cookie_value: str,
    api: str,
    url: str,
    data_obj: Dict[str, Any],
    response_type: str = "json",
    extra_params: Optional[Dict[str, str]] = None,
    extra_headers: Optional[Dict[str, str]] = None,
    timeout_seconds: int = 20,
    retry_on_token_expired: bool = True,
    save_cookie_on_refresh: bool = True,
    log_stage: str = "direct",
) -> Dict[str, Any]:
    current_cookie = cookie_value or ""
    last_body: Any = None
    last_status = 0
    refreshed_cookie = current_cookie
    token_refreshed = False

    for attempt in range(2 if retry_on_token_expired else 1):
        data_val, params, _ = build_mtop_request(
            current_cookie,
            api,
            data_obj,
            response_type=response_type,
            extra_params=extra_params,
        )
        headers = {
            "accept": "application/json",
            "accept-language": "zh-CN,zh;q=0.9",
            "content-type": "application/x-www-form-urlencoded",
            "cookie": current_cookie,
            "idle_site_biz_code": "COMMONPRO",
            "origin": "https://seller.goofish.com",
            "referer": "https://seller.goofish.com/",
            "user-agent": DEFAULT_USER_AGENT,
        }
        if extra_headers:
            headers.update(extra_headers)

        timeout = aiohttp.ClientTimeout(total=timeout_seconds)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(url, params=params, data={"data": data_val}, headers=headers) as response:
                response_text = await response.text()
                last_status = response.status
                try:
                    last_body = json.loads(response_text)
                except Exception:
                    last_body = response_text

                set_cookies = extract_set_cookies(response)
                merged_cookie = merge_cookie_string(current_cookie, set_cookies)
                if merged_cookie != current_cookie:
                    refreshed_cookie = merged_cookie
                    current_cookie = merged_cookie
                    token_refreshed = True
                    if save_cookie_on_refresh:
                        persist_cookie(cookie_id, merged_cookie)
                    logger.info(
                        f"[MTOP] merged Set-Cookie: cookie_id={cookie_id}, api={api}, "
                        f"stage={log_stage}, attempt={attempt + 1}, keys={list(set_cookies.keys())}"
                    )

                if is_token_expired_response(last_body) and attempt == 0 and current_cookie != cookie_value:
                    logger.info(f"[MTOP] token expired, retry once: cookie_id={cookie_id}, api={api}, stage={log_stage}")
                    continue

                break

    if is_session_expired_response(last_body):
        logger.warning(f"[MTOP] session expired: cookie_id={cookie_id}, api={api}, stage={log_stage}, ret={_as_text(last_body)[:300]}")
    elif is_risk_or_validate_response(last_body):
        logger.warning(f"[MTOP] risk/validate response: cookie_id={cookie_id}, api={api}, stage={log_stage}, ret={_as_text(last_body)[:300]}")

    return {
        "http_status": last_status,
        "body": last_body,
        "cookie": refreshed_cookie,
        "token_refreshed": token_refreshed,
        "session_expired": is_session_expired_response(last_body),
        "token_expired": is_token_expired_response(last_body),
        "risk_or_validate": is_risk_or_validate_response(last_body),
    }
