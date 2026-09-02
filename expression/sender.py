from pathlib import Path

import discord

from expression.enums import AssetType
from expression.models import (
    DEFAULT_EXPRESSION,
    ExpressionAsset,
    ExpressionConversationKey,
    ExpressionContext,
    ExpressionRequest,
    PrimaryExpression,
    RuntimeEmoji,
)
from expression.resolver import ExpressionResolver


def split_with_primary(text: str, primary: str, limit: int) -> list[str]:
    if limit <= len(primary) + 1:
        raise ValueError("Batas Discord terlalu kecil untuk primary emoji.")
    clean_text: str = text.strip()
    if not clean_text:
        return [primary]
    text_limit: int = limit - len(primary) - 1
    chunks: list[str] = []
    remaining: str = clean_text
    while len(remaining) > text_limit:
        cut: int = remaining.rfind(" ", 0, text_limit + 1)
        if cut <= 0:
            cut = text_limit
        chunks.append(remaining[:cut].rstrip())
        remaining = remaining[cut:].lstrip()
    chunks.append(f"{remaining} {primary}" if remaining else primary)
    return chunks


class DiscordExpressionSender:
    def __init__(
        self,
        client: discord.Client,
        resolver: ExpressionResolver,
    ) -> None:
        self._client: discord.Client = client
        self._resolver: ExpressionResolver = resolver

    def refresh_runtime_emojis(self) -> None:
        runtime: list[RuntimeEmoji] = [
            RuntimeEmoji(
                discord_id=emoji.id,
                name=emoji.name,
                guild_id=emoji.guild_id,
                animated=emoji.animated,
                available=emoji.available,
            )
            for emoji in self._client.emojis
        ]
        self._resolver.replace_runtime_emojis(runtime)
        print(
            f"[SENNA EXPRESSION] runtime emoji cache refreshed count={len(runtime)}"
        )

    async def send(
        self,
        message: discord.Message,
        text: str,
        request: ExpressionRequest | None,
        is_owner: bool,
        conversation_key: ExpressionConversationKey,
    ) -> None:
        expression: ExpressionRequest = request or DEFAULT_EXPRESSION
        context = ExpressionContext(
            conversation_key=conversation_key,
            guild_id=message.guild.id if message.guild is not None else None,
            channel_id=message.channel.id,
            is_owner=is_owner,
        )
        primary: PrimaryExpression = self._resolver.resolve_primary(
            expression, context
        )
        bonus: ExpressionAsset | None = self._resolver.resolve_bonus(
            expression, context
        )
        sent_primary: PrimaryExpression = await self._send_main(
            message, text, primary
        )
        self._resolver.record_primary_success(context, sent_primary)
        if bonus is not None:
            await self._send_bonus(message, bonus, context)

    async def _send_main(
        self, message: discord.Message, text: str, primary: PrimaryExpression
    ) -> PrimaryExpression:
        chunks: list[str] = split_with_primary(text, primary.rendered, 2000)
        allowed_mentions: discord.AllowedMentions = discord.AllowedMentions.none()
        for index, chunk in enumerate(chunks):
            is_last: bool = index == len(chunks) - 1
            try:
                if index == 0:
                    await message.reply(
                        chunk,
                        mention_author=False,
                        allowed_mentions=allowed_mentions,
                    )
                else:
                    await message.channel.send(
                        chunk, allowed_mentions=allowed_mentions
                    )
            except discord.Forbidden as error:
                if is_last and primary.asset is not None:
                    await self._retry_unicode(message, index, chunk, primary)
                    self._resolver.record_failure(primary.asset, "forbidden")
                    return PrimaryExpression(
                        primary.unicode_fallback, None, primary.unicode_fallback
                    )
                raise PermissionError(
                    f"Senna tidak memiliki izin mengirim response ke channel {message.channel.id}."
                ) from error
            except discord.HTTPException as error:
                if is_last and primary.asset is not None and error.code == 10014:
                    await self._retry_unicode(message, index, chunk, primary)
                    self._resolver.record_failure(primary.asset, "unknown_emoji")
                    return PrimaryExpression(
                        primary.unicode_fallback, None, primary.unicode_fallback
                    )
                raise RuntimeError(
                    f"Discord gagal mengirim response expression: status={error.status}, "
                    f"code={error.code}, detail={error.text}"
                ) from error
        return primary

    async def _retry_unicode(
        self,
        message: discord.Message,
        chunk_index: int,
        failed_chunk: str,
        primary: PrimaryExpression,
    ) -> None:
        content_without_custom: str = (
            failed_chunk[: -len(primary.rendered)].rstrip()
            if failed_chunk.endswith(primary.rendered)
            else failed_chunk
        )
        fallback: str = (
            f"{content_without_custom} {primary.unicode_fallback}"
            if content_without_custom
            else primary.unicode_fallback
        )
        allowed_mentions: discord.AllowedMentions = discord.AllowedMentions.none()
        if chunk_index == 0:
            await message.reply(
                fallback,
                mention_author=False,
                allowed_mentions=allowed_mentions,
            )
        else:
            await message.channel.send(fallback, allowed_mentions=allowed_mentions)

    async def _send_bonus(
        self,
        message: discord.Message,
        asset: ExpressionAsset,
        context: ExpressionContext,
    ) -> None:
        try:
            if asset.type is AssetType.STICKER and asset.discord_id is not None:
                sticker = self._client.get_sticker(asset.discord_id)
                if sticker is None:
                    raise LookupError(f"Sticker tidak tersedia: id={asset.discord_id}")
                await message.channel.send(
                    stickers=[sticker], allowed_mentions=discord.AllowedMentions.none()
                )
            elif asset.type is AssetType.GIF and asset.local_path is not None:
                path: Path = asset.local_path
                if not path.is_file():
                    raise FileNotFoundError(f"GIF expression hilang: {path}")
                await message.channel.send(
                    file=discord.File(path),
                    allowed_mentions=discord.AllowedMentions.none(),
                )
            else:
                raise LookupError(f"Bonus asset tidak dapat dikirim: key={asset.key}")
        except (
            OSError,
            LookupError,
            discord.Forbidden,
            discord.HTTPException,
        ) as error:
            self._resolver.record_failure(asset, type(error).__name__)
            return
        self._resolver.record_bonus_success(context, asset)
