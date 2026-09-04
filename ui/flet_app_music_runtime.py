from __future__ import annotations

import asyncio
from typing import Any

from ui.flet_app_music import SenaFletUI as _BaseSenaFletUI


class SenaFletUI(_BaseSenaFletUI):
    """Keep Flet Music synchronized with the shared runtime state.

    Discord actions and Flet controls operate on the same MusicManager. The UI mirrors
    runtime changes continuously, but an actively edited volume field is protected until
    the user applies it or changes server.
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._music_volume_dirty = False
        self._music_last_revision: tuple[object, ...] | None = None

        # Programmatic value updates from runtime do not normally fire on_change, while
        # actual typing in the browser does. This lets Discord volume changes update the
        # field without erasing a value the user is currently preparing to apply.
        self.music_volume.on_change = self._music_volume_changed
        self.music_volume.on_submit = self._music_set_volume

    async def _music_volume_changed(self, e: Any = None) -> None:
        del e
        self._music_volume_dirty = True

    async def _music_guild_changed(self, e: Any = None) -> None:
        self._music_volume_dirty = False
        await super()._music_guild_changed(e)
        if self.ctx.music is None or not self.music_guild.value:
            return
        try:
            snapshot = await self.ctx.music.snapshot(int(self.music_guild.value))
            self.music_volume.value = str(snapshot.volume_percent)
            self._music_last_revision = self._snapshot_revision(snapshot)
        except Exception:
            pass
        if self.page:
            self.page.update()

    async def _music_set_volume(self, e: Any = None) -> None:
        # Apply first, then allow live runtime synchronization again. If applying fails,
        # the next poll restores the actual runtime value instead of leaving stale UI.
        self._music_volume_dirty = False
        await super()._music_set_volume(e)

    @staticmethod
    def _snapshot_revision(snapshot: Any) -> tuple[object, ...]:
        current = snapshot.current
        current_key = None
        if current is not None:
            current_key = (
                getattr(current, "webpage_url", ""),
                getattr(current, "title", ""),
            )
        queue_key = tuple(
            (
                getattr(track, "webpage_url", ""),
                getattr(track, "title", ""),
            )
            for track in snapshot.queue
        )
        return (
            snapshot.guild_id,
            snapshot.connected,
            snapshot.voice_channel_id,
            current_key,
            queue_key,
            snapshot.paused,
            snapshot.playing,
            snapshot.volume_percent,
        )

    async def _music_refresh(self, e: Any = None) -> None:
        del e
        if self.ctx.music is None or not self.music_guild.value:
            self.music_now.value = "Music Manager offline atau server belum dipilih."
            self.music_queue_text.value = "Queue kosong."
            if self.page:
                self.page.update()
            return

        try:
            manager = self._music_manager()
            snapshot = await manager.snapshot(int(self.music_guild.value))
            revision = self._snapshot_revision(snapshot)
            self.music_backend.value = manager.backend_status()
            state = (
                "PAUSED"
                if snapshot.paused
                else "PLAYING"
                if snapshot.playing
                else "IDLE"
            )

            if snapshot.current is None:
                self.music_now.value = (
                    f"{state} · VC={snapshot.voice_channel_name or '-'} · "
                    f"volume={snapshot.volume_percent}%\n"
                    "Tidak ada track aktif."
                )
            else:
                track = snapshot.current
                self.music_now.value = (
                    f"{state} · VC={snapshot.voice_channel_name or '-'} · "
                    f"volume={snapshot.volume_percent}%\n"
                    f"{track.title}\n{track.platform} · {track.duration_text}\n"
                    f"{track.webpage_url}"
                )

            # Show current playback in the queue panel too. Previously a single Discord
            # music.play immediately became `current`, so the Queue panel looked empty
            # even though Discord had successfully changed the runtime state.
            lines: list[str] = []
            if snapshot.current is not None:
                current = snapshot.current
                marker = "⏸" if snapshot.paused else "▶"
                lines.append(
                    f"{marker} NOW · {current.title} · {current.platform} · {current.duration_text}"
                )
            for index, track in enumerate(snapshot.queue, start=1):
                lines.append(
                    f"{index}. {track.title} · {track.platform} · {track.duration_text}"
                )
            self.music_queue_text.value = "\n".join(lines) or "Queue kosong."

            # Two-way sync: Discord `music.volume` updates the Flet input automatically,
            # except while the browser user has typed an unapplied value.
            if not self._music_volume_dirty:
                self.music_volume.value = str(snapshot.volume_percent)

            self._music_last_revision = revision
        except Exception as error:
            self.music_now.value = f"Refresh gagal · {type(error).__name__}: {error}"

        if self.page:
            self.page.update()

    async def _log_pump(self) -> None:
        # Keep the Music controls synchronized from the shared manager while the Music
        # page is visible. Other tabs retain the existing lightweight behavior.
        while self.page is not None:
            if self._selected_index == 4:
                await self._music_refresh()
            elif self._selected_index == 7:
                await self._refresh_logs()
            await asyncio.sleep(0.6)
