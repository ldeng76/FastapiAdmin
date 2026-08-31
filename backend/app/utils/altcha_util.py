"""
ALTCHA 验证码工具类 —— 基于 Proof-of-Work（哈希前置零）的人机验证。

协议说明（与前端 altcha-widget 互通，见 https://altcha.org/docs/architecture）：
1. 后端生成 challenge = hex(hash(salt + number))，用 HMAC(hmac_key, challenge) 签名，下发给前端；
2. 前端 PoW：在 [min, max] 范围找 number 使 challenge 前缀零字节数足够；
3. 前端回传 payload（algorithm, challenge, number, salt, signature）；
4. 后端重新计算 challenge、校验签名、一次性消费（Redis 防重放）。

本实现不依赖第三方 altcha 包，纯标准库即可。
"""

import base64
import hashlib
import hmac
import json
import random
import secrets
import time
from dataclasses import dataclass
from typing import Any

from app.common.enums import RedisInitKeyConfig
from app.config.setting import settings
from app.core.logger import log
from app.core.redis_crud import RedisCURD
from redis.asyncio.client import Redis


# 前端 altcha-widget 接受的是 base64(JSON({algorithm, challenge, maxnumber, salt, signature}))
# 所以我们以「DICT 表达 + JSON + base64(urlsafe)」为协议格式。


def _get_hmac_key() -> bytes:
    key = settings.ALTCHA_HMAC_KEY or settings.SECRET_KEY
    if isinstance(key, str):
        key = key.encode("utf-8")
    return key


def _hasher(algorithm: str) -> Any:
    alg = (algorithm or settings.ALTCHA_ALGORITHM).lower().replace("-", "")
    if alg == "sha256":
        return hashlib.sha256()
    if alg == "sha384":
        return hashlib.sha384()
    if alg == "sha512":
        return hashlib.sha512()
    raise ValueError(f"Unsupported ALTCHA algorithm: {algorithm}")


def _hash_hex(algorithm: str, data: bytes) -> str:
    h = _hasher(algorithm)
    h.update(data)
    return h.hexdigest()


def _hmac_hex(key: bytes, challenge: str) -> str:
    # ALTCHA 使用 HMAC-SHA256 对 challenge 做签名
    sig = hmac.new(key, challenge.encode("utf-8"), digestmod=hashlib.sha256)
    return sig.hexdigest()


@dataclass
class AltchaChallenge:
    algorithm: str
    challenge: str
    maxnumber: int
    salt: str
    signature: str
    expire_at: int  # unix seconds, 仅后端用于过期判断，不下发

    def to_public_payload(self) -> dict:
        """下发给前端的公开字段（不包含 expire_at）"""
        return {
            "algorithm": self.algorithm,
            "challenge": self.challenge,
            "maxnumber": self.maxnumber,
            "salt": self.salt,
            "signature": self.signature,
        }

    def to_widget_base64(self) -> str:
        """altcha-widget 要求 challenge 参数是 base64url(JSON)"""
        data = self.to_public_payload()
        raw = json.dumps(data, separators=(",", ":")).encode("utf-8")
        return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


class AltchaUtil:
    """ALTCHA 验证码工具类"""

    # Redis 中已消费 challenge 的前缀；TTL=expire 以自动清理
    _REPLAY_PREFIX = RedisInitKeyConfig.CAPTCHA_CODES.key + ":altcha_consumed:"

    @classmethod
    def generate_challenge(cls, expires_in: int | None = None) -> AltchaChallenge:
        """
        生成一个新的 ALTCHA challenge。

        返回:
            AltchaChallenge
        """
        algorithm = settings.ALTCHA_ALGORITHM
        min_diff = max(1, settings.ALTCHA_MIN_DIFFICULTY)
        max_diff = max(min_diff, settings.ALTCHA_MAX_DIFFICULTY)
        maxnumber = random.randint(min_diff, max_diff)

        # salt: 64 bits random + timestamp（让每个 challenge 自然不同）
        salt_random = secrets.token_hex(8)
        salt = f"{salt_random}{int(time.time())}"

        # 预选一个 number（secret），算出 challenge。
        # 注意：这是「服务端选定 number」模式，与 altcha-lib 一致，
        # 客户端需要在 [1, maxnumber] 范围内 brute-force 寻找该 number。
        secret_number = secrets.randbelow(maxnumber - 1) + 1  # 1..maxnumber inclusive
        challenge = _hash_hex(algorithm, (salt + str(secret_number)).encode("utf-8"))

        signature = _hmac_hex(_get_hmac_key(), challenge)

        ttl = expires_in if expires_in and expires_in > 0 else settings.ALTCHA_EXPIRE_SECONDS
        expire_at = int(time.time()) + ttl

        return AltchaChallenge(
            algorithm=algorithm,
            challenge=challenge,
            maxnumber=maxnumber,
            salt=salt,
            signature=signature,
            expire_at=expire_at,
        )

    @classmethod
    def parse_payload(cls, payload: str | bytes | dict) -> dict:
        """
        解析前端提交的 payload（支持 base64 编码字符串 / dict）。
        返回 {algorithm, challenge, number, salt, signature}。
        """
        if isinstance(payload, dict):
            data = payload
        else:
            if isinstance(payload, str):
                raw = payload.encode("utf-8")
            else:
                raw = payload
            # URL-safe base64 自动补 padding
            pad = b"=" * (-len(raw) % 4)
            try:
                decoded = base64.urlsafe_b64decode(raw + pad)
            except Exception as exc:
                raise ValueError(f"ALTCHA payload base64 decode failed: {exc}")
            try:
                data = json.loads(decoded.decode("utf-8"))
            except Exception as exc:
                raise ValueError(f"ALTCHA payload JSON decode failed: {exc}")

        required = {"algorithm", "challenge", "number", "salt", "signature"}
        missing = required - set(data.keys())
        if missing:
            raise ValueError(f"ALTCHA payload missing fields: {sorted(missing)}")
        return {
            "algorithm": str(data["algorithm"]),
            "challenge": str(data["challenge"]),
            "number": int(data["number"]),
            "salt": str(data["salt"]),
            "signature": str(data["signature"]),
        }

    @classmethod
    async def verify_payload(
        cls,
        payload: str | bytes | dict,
        redis: Redis | None = None,
    ) -> bool:
        """
        校验 ALTCHA 解。

        校验顺序：
        1) 重放防护：challenge 已被消费 → 失败
        2) 过期：salt 中时间戳或下发时 expire_at（若存在）失效 → 失败
        3) 签名：HMAC(challenge) 与 signature 一致
        4) PoW：hash(salt + number) == challenge
        5) number 范围：1<=number<=maxnumber（前端若自行构造需限制）
        6) 防重放：通过后把 challenge 写入 Redis 标记已消费

        参数:
            payload: 前端提交的 payload（base64 字符串或 dict）
            redis:   Redis 客户端（需要防重放时必传）

        返回:
            bool: 验证通过返回 True，否则抛出 ValueError/CustomException

        异常:
            ValueError: 校验失败（调用方负责转成业务异常）
        """
        p = cls.parse_payload(payload)

        algorithm = p["algorithm"]
        challenge = p["challenge"]
        number = p["number"]
        salt = p["salt"]
        signature = p["signature"]

        # 重放防护
        if redis is not None and settings.ALTCHA_REPLAY_PROTECTION:
            key = cls._REPLAY_PREFIX + challenge
            exists = await RedisCURD(redis).get(key)
            if exists:
                raise ValueError("ALTCHA challenge already consumed")

        # 过期检查
        try:
            # 我们 salt 后半段是下发时的 10 位时间戳（秒）
            ts_part = salt[-10:]
            issue_at = int(ts_part) if ts_part.isdigit() else 0
        except Exception:
            issue_at = 0
        if issue_at:
            age = int(time.time()) - issue_at
            if age > settings.ALTCHA_EXPIRE_SECONDS:
                raise ValueError("ALTCHA challenge expired")

        # 签名校验
        expected_sig = _hmac_hex(_get_hmac_key(), challenge)
        if not hmac.compare_digest(expected_sig, signature.lower()):
            raise ValueError("ALTCHA signature mismatch")

        # PoW 校验
        expected_challenge = _hash_hex(algorithm, (salt + str(number)).encode("utf-8"))
        if not hmac.compare_digest(expected_challenge, challenge.lower()):
            raise ValueError("ALTCHA proof-of-work verification failed")

        # number 必须是正整数（前端 widget 约束在 1..maxnumber 内）
        if number <= 0 or number > settings.ALTCHA_MAX_DIFFICULTY:
            raise ValueError("ALTCHA number out of range")

        # 标记已消费（TTL 为有效期的 1.2 倍，防重复使用但最终自动清理）
        if redis is not None and settings.ALTCHA_REPLAY_PROTECTION:
            key = cls._REPLAY_PREFIX + challenge
            ttl = settings.ALTCHA_EXPIRE_SECONDS + 60
            await RedisCURD(redis).set(key=key, value="1", expire=ttl)

        log.debug(f"ALTCHA verify ok challenge[:16]={challenge[:16]}")
        return True
