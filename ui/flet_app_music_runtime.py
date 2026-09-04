from __future__ import annotations

from typing import Any

from ui.flet_app_music import SenaFletUI as _BaseSenaFletUI


class SenaFletUI(_BaseSenaFletUI):
    """Music UI runtime fixes.

    Live polling must never overwrite the editable volume field while the user is typing.
    The actual runtime volume remains visible in Now Playing and is synced into the input only
    when the selected guild changes or after Set volume succeeds.
    """

    async def _music_guild_changed(self, e: Any = None) -> None:
        await super()._music_guild_changed(e)
        if self.ctx.music is None or not self.music_guild.value:
            return
        try:
            snapshot = await self.ctx.music.snapshot(int(self.music_guild.value))
            self.music_volume.value = str(snapshot.volume_percent)
        except Exception:
            pass
        if self.page:
            self.page.update()

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
            lines = [
                f"{index}. {track.title} · {track.platform} · {track.duration_text}"
                for index, track in enumerate(snapshot.queue, start=1)
            ]
            self.music_queue_text.value = "\n".join(lines) or "Queue kosong."

            # IMPORTANT: do not assign self.music_volume.value here. This method is called
            # by the 0.9s live poll; assigning it would erase what the user is typing.
        except Exception as error:
            self.music_now.value = f"Refresh gagal · {type(error).__name__}: {error}"

        if self.page:
            self.page.update()
