from __future__ import annotations

import importlib.util
from dataclasses import replace
from typing import Any

import flet as ft

from config import STT_SETTINGS_FILE, VOICE_SETTINGS_FILE
from stt.settings import load_configured_settings, save_settings as save_stt_settings
from ui.flet_app import BORDER, ERROR, MUTED, SUCCESS, TEXT, WARNING
from ui.flet_app_music_bandwidth import SenaFletUI as _BaseSenaFletUI
from voice.converters.settings import VoiceConverterSettings
from voice.manager import VoiceManager
from voice.settings_store import VoicePreferences, save_preferences


class SenaFletUI(_BaseSenaFletUI):
    """Keep TTS usable independently from STT/voice-receive dependencies.

    gTTS synthesis works without discord-ext-voice-recv. Discord VC playback still
    requires a working Discord voice transport, while STT additionally requires the
    receive backend. Keeping these boundaries separate prevents an unavailable STT
    stack from making the TTS controls look unavailable on Android/Termux.
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.tts_text = ft.TextField(
            label="Teks TTS",
            hint_text="Contoh: halo semuanya, Sena sedang online.",
            multiline=True,
            border_color=BORDER,
        )
        self.tts_runtime_status = ft.Text("TTS idle", color=MUTED, size=11)

    def _tts_preferences_from_controls(self) -> VoicePreferences:
        language = (self.tts_language.value or "").strip().lower()
        if not language:
            raise ValueError("Bahasa TTS tidak boleh kosong.")
        return VoicePreferences(
            provider_name=str(self.tts_provider.value or "gtts"),
            language=language,
            converter=VoiceConverterSettings(
                enabled=bool(self.converter_enabled.value),
                converter=str(self.converter_name.value or "passthrough"),
                model=(self.converter_model.value or "").strip() or None,
                pitch=int(self.converter_pitch.value or "0"),
                index_ratio=float(self.converter_index.value or "0"),
                protect=float(self.converter_protect.value or "0"),
            ),
        )

    def _tts_manager_from_controls(self) -> VoiceManager:
        prefs = self._tts_preferences_from_controls()
        return VoiceManager(
            prefs.provider_name,
            prefs.language,
            prefs.converter,
            VOICE_SETTINGS_FILE,
        )

    async def _save_tts_settings(self, e: Any = None) -> None:
        del e
        try:
            prefs = self._tts_preferences_from_controls()
            save_preferences(VOICE_SETTINGS_FILE, prefs)
            self.tts_runtime_status.value = (
                "TTS + Voice Converter settings disimpan. STT tidak diubah."
            )
            self.tts_runtime_status.color = SUCCESS
        except Exception as error:
            self.tts_runtime_status.value = (
                f"Save TTS gagal · {type(error).__name__}: {error}"
            )
            self.tts_runtime_status.color = ERROR
        if self.page:
            self.page.update()

    async def _tts_generate_test(self, e: Any = None) -> None:
        del e
        text = (self.tts_text.value or "").strip()
        if not text:
            self.tts_runtime_status.value = "Isi teks TTS dulu."
            self.tts_runtime_status.color = WARNING
            if self.page:
                self.page.update()
            return

        manager: VoiceManager | None = None
        prepared = None
        try:
            self.tts_runtime_status.value = "Generating TTS..."
            self.tts_runtime_status.color = MUTED
            if self.page:
                self.page.update()

            manager = self._tts_manager_from_controls()
            prepared = await manager.prepare(text)
            size_kb = prepared.path.stat().st_size / 1024 if prepared.path.exists() else 0.0
            self.tts_runtime_status.value = (
                f"TTS berhasil dibuat · provider={manager.provider_name} · "
                f"language={manager.language} · {size_kb:.1f} KB. "
                "Tes ini tidak membutuhkan STT/voice_recv."
            )
            self.tts_runtime_status.color = SUCCESS
        except Exception as error:
            self.tts_runtime_status.value = (
                f"Generate TTS gagal · {type(error).__name__}: {error}"
            )
            self.tts_runtime_status.color = ERROR
        finally:
            if manager is not None:
                if prepared is not None:
                    try:
                        await manager.cleanup_prepared(prepared)
                    except Exception:
                        pass
                try:
                    await manager.close()
                except Exception:
                    pass
        if self.page:
            self.page.update()

    async def _tts_speak_in_vc(self, e: Any = None) -> None:
        del e
        text = (self.tts_text.value or "").strip()
        if not text:
            self.tts_runtime_status.value = "Isi teks TTS dulu."
            self.tts_runtime_status.color = WARNING
            if self.page:
                self.page.update()
            return

        manager: VoiceManager | None = None
        try:
            guild = (
                self.ctx.client.get_guild(int(self.voice_guild.value))
                if self.voice_guild.value
                else None
            )
            voice = guild.voice_client if guild is not None else None
            if voice is None or not voice.is_connected():
                raise RuntimeError(
                    "Bot belum terhubung ke VC. gTTS synthesis tetap tersedia, "
                    "tetapi playback Discord membutuhkan voice transport yang aktif."
                )

            self.tts_runtime_status.value = "Preparing & speaking TTS..."
            self.tts_runtime_status.color = MUTED
            if self.page:
                self.page.update()

            manager = self._tts_manager_from_controls()
            await manager.speak(voice, text)
            self.tts_runtime_status.value = "TTS selesai diputar di VC."
            self.tts_runtime_status.color = SUCCESS
        except Exception as error:
            self.tts_runtime_status.value = (
                f"Speak TTS gagal · {type(error).__name__}: {error}"
            )
            self.tts_runtime_status.color = ERROR
        finally:
            if manager is not None:
                try:
                    await manager.close()
                except Exception:
                    pass
        if self.page:
            self.page.update()

    async def _save_voice_settings(self, e: Any) -> None:
        """The inherited STT button now saves STT only.

        TTS/provider/converter settings are persisted by _save_tts_settings(), so a
        broken/unavailable STT configuration cannot block TTS settings on Android.
        """
        del e
        try:
            current_stt = load_configured_settings()
            stt = replace(
                current_stt,
                enabled=bool(self.stt_enabled.value),
                model=(self.stt_model.value or "").strip(),
                language=(self.stt_language.value or "").strip(),
                vad_enabled=bool(self.stt_vad.value),
                min_speech_seconds=float(self.stt_min_speech.value or "0"),
                end_silence_seconds=float(self.stt_end_silence.value or "0"),
                max_utterance_seconds=float(self.stt_max_utterance.value or "0"),
                vad_rms_threshold=int(self.stt_rms.value or "0"),
                voice_session_timeout_seconds=float(
                    self.stt_session_timeout.value or "0"
                ),
                wake_words=tuple(
                    item.strip().casefold()
                    for item in (self.stt_wake_words.value or "").split(",")
                    if item.strip()
                ),
                queue_size=int(self.stt_queue.value or "0"),
                workers=int(self.stt_workers.value or "0"),
                log_transcript=bool(self.stt_log_transcript.value),
                listen_mode=str(self.stt_listen_mode.value),
                save_audio=False,
            )
            save_stt_settings(STT_SETTINGS_FILE, stt)
            self.voice_save_status.value = "STT settings disimpan. TTS tidak diubah."
            self.voice_save_status.color = SUCCESS
        except Exception as error:
            self.voice_save_status.value = (
                f"Save STT gagal · {type(error).__name__}: {error}"
            )
            self.voice_save_status.color = ERROR
        if self.page:
            self.page.update()

    def _voice(self) -> ft.Control:
        # Let the base class construct and initialize all existing controls/settings,
        # then arrange the same controls with explicit TTS/STT subsystem boundaries.
        super()._voice()

        tts_feature = self.feature_results.get("tts")
        voice_feature = self.feature_results.get("voice")
        tts_ready = (
            bool(tts_feature and tts_feature.available)
            if tts_feature is not None
            else importlib.util.find_spec("gtts") is not None
        )
        stt_ready = bool(voice_feature and voice_feature.available)
        tts_detail = (
            tts_feature.detail
            if tts_feature is not None
            else ("gTTS import available" if tts_ready else "gTTS unavailable")
        )
        stt_detail = voice_feature.detail if voice_feature else "not registered"

        health = ft.ResponsiveRow(
            controls=[
                ft.Container(
                    col={"xs": 12, "md": 6},
                    content=self._panel(
                        ft.Column(
                            controls=[
                                ft.Text(
                                    "TTS synthesis · READY" if tts_ready else "TTS synthesis · UNAVAILABLE",
                                    color=SUCCESS if tts_ready else ERROR,
                                    weight=ft.FontWeight.W_600,
                                ),
                                ft.Text(tts_detail, color=MUTED, size=10),
                                ft.Text(
                                    "gTTS berjalan terpisah dari STT. Generate/Test tidak membutuhkan voice_recv.",
                                    color=MUTED,
                                    size=10,
                                ),
                            ],
                            spacing=5,
                        )
                    ),
                ),
                ft.Container(
                    col={"xs": 12, "md": 6},
                    content=self._panel(
                        ft.Column(
                            controls=[
                                ft.Text(
                                    "STT receive · READY" if stt_ready else "STT receive · DEGRADED",
                                    color=SUCCESS if stt_ready else WARNING,
                                    weight=ft.FontWeight.W_600,
                                ),
                                ft.Text(stt_detail, color=MUTED, size=10),
                                ft.Text(
                                    "STT membutuhkan Discord voice receive backend dan provider transkripsi yang kompatibel.",
                                    color=MUTED,
                                    size=10,
                                ),
                            ],
                            spacing=5,
                        )
                    ),
                ),
            ],
            spacing=10,
            run_spacing=10,
        )

        transport_panel = self._panel(
            ft.Column(
                controls=[
                    ft.Text("Discord Voice Transport", color=TEXT, weight=ft.FontWeight.W_600),
                    ft.ResponsiveRow(
                        controls=[
                            ft.Container(col={"xs": 12, "md": 6}, content=self.voice_guild),
                            ft.Container(col={"xs": 12, "md": 6}, content=self.voice_channel),
                        ]
                    ),
                    self.voice_status,
                    ft.Row(
                        wrap=True,
                        controls=[
                            ft.Button("Join", icon=ft.Icons.CALL, on_click=self._voice_join),
                            ft.Button("Leave", icon=ft.Icons.CALL_END, on_click=self._voice_leave),
                        ],
                    ),
                    ft.Text(
                        "TTS synthesis bisa tetap diuji ketika transport ini unavailable; hanya playback ke VC yang membutuhkan transport.",
                        color=MUTED,
                        size=10,
                    ),
                ],
                spacing=10,
            )
        )

        tts_panel = self._panel(
            ft.Column(
                controls=[
                    ft.Text("Text-to-Speech (TTS)", color=TEXT, weight=ft.FontWeight.W_600),
                    ft.Text(
                        "Subsystem TTS mandiri. Provider saat ini dapat menggunakan gTTS di Android/Termux selama koneksi internet tersedia.",
                        color=MUTED,
                        size=10,
                    ),
                    ft.ResponsiveRow(
                        controls=[
                            ft.Container(col={"xs": 12, "md": 6}, content=self.tts_provider),
                            ft.Container(col={"xs": 12, "md": 6}, content=self.tts_language),
                        ]
                    ),
                    ft.Divider(color=BORDER),
                    ft.Text("Voice Converter", color=TEXT, weight=ft.FontWeight.W_600),
                    self.converter_enabled,
                    ft.ResponsiveRow(
                        controls=[
                            ft.Container(col={"xs": 12, "md": 6}, content=self.converter_name),
                            ft.Container(col={"xs": 12, "md": 6}, content=self.converter_model),
                            ft.Container(col={"xs": 12, "md": 4}, content=self.converter_pitch),
                            ft.Container(col={"xs": 12, "md": 4}, content=self.converter_index),
                            ft.Container(col={"xs": 12, "md": 4}, content=self.converter_protect),
                        ]
                    ),
                    ft.Button(
                        "Save TTS / Converter settings",
                        icon=ft.Icons.SAVE_OUTLINED,
                        on_click=self._save_tts_settings,
                    ),
                    ft.Divider(color=BORDER),
                    self.tts_text,
                    ft.Row(
                        wrap=True,
                        controls=[
                            ft.Button("Generate / Test TTS", on_click=self._tts_generate_test),
                            ft.Button("Speak in VC", icon=ft.Icons.PLAY_ARROW, on_click=self._tts_speak_in_vc),
                        ],
                    ),
                    self.tts_runtime_status,
                ],
                spacing=11,
            )
        )

        stt_panel = self._panel(
            ft.Column(
                controls=[
                    ft.Text("Speech-to-Text (STT)", color=TEXT, weight=ft.FontWeight.W_600),
                    ft.Text(
                        "STT terpisah dari TTS. Jika voice_recv/Faster Whisper tidak tersedia, panel TTS di atas tetap dapat digunakan.",
                        color=MUTED,
                        size=10,
                    ),
                    ft.Row(
                        wrap=True,
                        controls=[self.stt_enabled, self.stt_vad, self.stt_log_transcript],
                    ),
                    ft.ResponsiveRow(
                        controls=[
                            ft.Container(col={"xs": 12, "md": 6}, content=self.stt_model),
                            ft.Container(col={"xs": 12, "md": 6}, content=self.stt_language),
                            ft.Container(col={"xs": 12, "md": 4}, content=self.stt_min_speech),
                            ft.Container(col={"xs": 12, "md": 4}, content=self.stt_end_silence),
                            ft.Container(col={"xs": 12, "md": 4}, content=self.stt_max_utterance),
                            ft.Container(col={"xs": 12, "md": 4}, content=self.stt_rms),
                            ft.Container(col={"xs": 12, "md": 4}, content=self.stt_queue),
                            ft.Container(col={"xs": 12, "md": 4}, content=self.stt_workers),
                            ft.Container(col={"xs": 12, "md": 6}, content=self.stt_session_timeout),
                            ft.Container(col={"xs": 12, "md": 6}, content=self.stt_listen_mode),
                            ft.Container(col=12, content=self.stt_wake_words),
                        ]
                    ),
                    ft.Button(
                        "Save STT settings",
                        icon=ft.Icons.SAVE_OUTLINED,
                        on_click=self._save_voice_settings,
                    ),
                    self.voice_save_status,
                ],
                spacing=11,
            )
        )

        return self._body(
            [
                self._title(
                    "Voice",
                    "Discord transport dengan TTS dan STT sebagai subsystem independen",
                ),
                health,
                transport_panel,
                tts_panel,
                stt_panel,
            ]
        )
