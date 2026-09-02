import asyncio
import shutil
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

import aiohttp

from voice.models import RVCModel


class WOkadaAPIError(RuntimeError):
    pass


class WOkadaRequestRejectedError(WOkadaAPIError):
    pass


@dataclass(frozen=True)
class WOkadaModel:
    slot_index: int
    name: str
    model_file: str


class WOkadaClient:
    def __init__(
        self,
        base_url: str,
        timeout_seconds: float,
        chunk_seconds: float,
        retry_count: int,
        retry_delay_seconds: float,
    ) -> None:
        self.base_url: str = base_url.rstrip("/")
        self.timeout_seconds: float = timeout_seconds
        self.chunk_seconds: float = chunk_seconds
        self.retry_count: int = retry_count
        self.retry_delay_seconds: float = retry_delay_seconds
        self.sample_rate: int = 48_000
        self.temp_folder: Path = Path("temp/converter")
        self.temp_folder.mkdir(parents=True, exist_ok=True)

    async def list_rvc_models(self) -> list[WOkadaModel]:
        slots_value: object = await self._get_json_value("/api/slot-manager/slots")
        if not isinstance(slots_value, list):
            raise WOkadaAPIError("Respons daftar slot w-okada bukan array.")
        models: list[WOkadaModel] = []
        for item in slots_value:
            if not isinstance(item, dict) or item.get("voice_changer_type") != "RVC":
                continue
            slot_index: object = item.get("slot_index")
            name: object = item.get("name")
            model_file: object = item.get("model_file")
            if not isinstance(slot_index, int):
                raise WOkadaAPIError("Slot RVC tidak memiliki slot_index integer.")
            if not isinstance(name, str) or not isinstance(model_file, str):
                raise WOkadaAPIError(
                    f"Slot RVC {slot_index} tidak memiliki name/model_file yang valid."
                )
            models.append(WOkadaModel(slot_index, name, model_file))
        return models

    async def import_model(self, model: RVCModel, backend_folder: Path) -> WOkadaModel:
        existing: list[WOkadaModel] = await self.list_rvc_models()
        matches: list[WOkadaModel] = [item for item in existing if item.name == model.name]
        if matches:
            return matches[0]

        upload_folder: Path = backend_folder / "upload_dir"
        if not upload_folder.is_dir():
            raise FileNotFoundError(
                f"Folder upload w-okada tidak ditemukan: {upload_folder.resolve()}"
            )
        uploaded_weight: Path = upload_folder / model.weight_file.name
        uploaded_index: Path | None = None
        if model.index_file is not None:
            uploaded_index = upload_folder / model.index_file.name
        if uploaded_weight.exists() or (
            uploaded_index is not None and uploaded_index.exists()
        ):
            raise FileExistsError(
                "Folder upload w-okada sudah memiliki file dengan nama model yang sama."
            )

        await asyncio.to_thread(shutil.copy2, model.weight_file, uploaded_weight)
        if model.index_file is not None and uploaded_index is not None:
            await asyncio.to_thread(shutil.copy2, model.index_file, uploaded_index)
        payload: dict[str, object] = {
            "slot_index": None,
            "voice_changer_type": "RVC",
            "name": model.name,
            "model_file": uploaded_weight.name,
            "index_file": uploaded_index.name if uploaded_index is not None else None,
            "embedder": None,
        }
        try:
            await self._request_json("POST", "/api/slot-manager/slots", payload)
        except Exception:
            if uploaded_weight.exists():
                uploaded_weight.unlink()
            if uploaded_index is not None and uploaded_index.exists():
                uploaded_index.unlink()
            raise

        imported: list[WOkadaModel] = await self.list_rvc_models()
        imported_matches: list[WOkadaModel] = [
            item for item in imported if item.name == model.name
        ]
        if len(imported_matches) != 1:
            raise WOkadaAPIError(
                f"Model '{model.name}' selesai dikirim tetapi slot backend tidak ditemukan."
            )
        return imported_matches[0]

    async def convert(
        self,
        input_audio: Path,
        model: str | None,
        pitch: int,
        index_ratio: float,
        protect: float,
    ) -> Path:
        configuration: dict[str, object] = await self._get_json(
            "/api/configuration-manager/configuration"
        )
        slot_index: int = await self._resolve_slot(model, configuration)
        await self._configure_slot(slot_index, pitch, index_ratio, protect)
        await self._select_slot(configuration, slot_index)

        identifier: str = uuid.uuid4().hex
        input_raw: Path = self.temp_folder / f"{identifier}-input.f32"
        output_raw: Path = self.temp_folder / f"{identifier}-output.f32"
        output_wav: Path = self.temp_folder / f"{identifier}.wav"
        try:
            await self._run_ffmpeg(
                (
                    "ffmpeg",
                    "-v",
                    "error",
                    "-i",
                    str(input_audio),
                    "-f",
                    "f32le",
                    "-ar",
                    str(self.sample_rate),
                    "-ac",
                    "1",
                    "-y",
                    str(input_raw),
                )
            )
            converted: bytes = await self._convert_audio(input_raw.read_bytes())
            output_raw.write_bytes(converted)
            await self._run_ffmpeg(
                (
                    "ffmpeg",
                    "-v",
                    "error",
                    "-f",
                    "f32le",
                    "-ar",
                    str(self.sample_rate),
                    "-ac",
                    "1",
                    "-i",
                    str(output_raw),
                    "-y",
                    str(output_wav),
                )
            )
        finally:
            if input_raw.exists():
                input_raw.unlink()
            if output_raw.exists():
                output_raw.unlink()

        if not output_wav.is_file() or output_wav.stat().st_size == 0:
            raise WOkadaAPIError("w-okada menghasilkan file audio kosong.")
        return output_wav

    async def _resolve_slot(
        self,
        model: str | None,
        configuration: dict[str, object],
    ) -> int:
        if model is None:
            return self._require_int(configuration, "current_slot_index")
        if model.isdecimal():
            slot_index: int = int(model)
            await self._get_slot(slot_index)
            return slot_index

        for backend_model in await self.list_rvc_models():
            if backend_model.name == model:
                return backend_model.slot_index
        raise WOkadaAPIError(
            f"Model '{model}' tidak ditemukan pada slot backend w-okada. "
            "Impor model melalui UI w-okada atau gunakan nomor slot."
        )

    async def _configure_slot(
        self,
        slot_index: int,
        pitch: int,
        index_ratio: float,
        protect: float,
    ) -> None:
        slot: dict[str, object] = await self._get_slot(slot_index)
        if slot.get("voice_changer_type") != "RVC":
            raise WOkadaAPIError(f"Slot w-okada {slot_index} bukan model RVC.")
        slot["pitch_shift"] = pitch
        slot["index_ratio"] = index_ratio
        slot["protect_ratio"] = protect
        await self._put_json(f"/api/slot-manager/slots/{slot_index}", slot)

    async def _select_slot(
        self,
        configuration: dict[str, object],
        slot_index: int,
    ) -> None:
        if configuration.get("current_slot_index") == slot_index:
            return
        configuration["current_slot_index"] = slot_index
        await self._put_json("/api/configuration-manager/configuration", configuration)

    async def _get_slot(self, slot_index: int) -> dict[str, object]:
        return await self._get_json(f"/api/slot-manager/slots/{slot_index}")

    async def _convert_audio(self, audio: bytes) -> bytes:
        if not audio or len(audio) % 4 != 0:
            raise ValueError("Audio float32 untuk w-okada kosong atau tidak valid.")
        chunk_size: int = int(self.sample_rate * self.chunk_seconds) * 4
        if chunk_size <= 0:
            raise ValueError("Ukuran chunk w-okada harus lebih besar dari nol.")
        output: bytearray = bytearray()
        for offset in range(0, len(audio), chunk_size):
            chunk: bytes = audio[offset : offset + chunk_size]
            padded_chunk: bytes = chunk.ljust(chunk_size, b"\x00")
            converted: bytes = await self._post_chunk(padded_chunk)
            if len(converted) % 4 != 0:
                raise WOkadaAPIError(
                    f"Respons audio w-okada bukan float32 valid: {len(converted)} byte."
                )
            output.extend(converted)
        if not output:
            raise WOkadaAPIError("w-okada tidak menghasilkan data audio.")
        if len(output) > len(audio):
            valid_size: int = len(audio) - (len(audio) % 4)
            return bytes(output[:valid_size])
        return bytes(output)

    async def _post_chunk(self, chunk: bytes) -> bytes:
        endpoint: str = "/api/voice-changer/convert_chunk"
        last_error: Exception | None = None
        for attempt in range(1, self.retry_count + 1):
            form: aiohttp.FormData = aiohttp.FormData()
            form.add_field(
                "waveform",
                chunk,
                filename="waveform.bin",
                content_type="application/octet-stream",
            )
            try:
                timeout: aiohttp.ClientTimeout = aiohttp.ClientTimeout(
                    total=self.timeout_seconds
                )
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    async with session.post(
                        self.base_url + endpoint,
                        data=form,
                        headers={"x-timestamp": str(int(time.time() * 1000))},
                    ) as response:
                        body: bytes = await response.read()
                        if response.status != 200:
                            detail: str = body.decode("utf-8", errors="replace")
                            error_message: str = (
                                f"w-okada POST {endpoint} gagal: status={response.status}, "
                                f"body={detail}"
                            )
                            if 400 <= response.status < 500:
                                raise WOkadaRequestRejectedError(error_message)
                            raise WOkadaAPIError(error_message)
                        if not body:
                            raise WOkadaAPIError(
                                f"w-okada POST {endpoint} menghasilkan respons kosong."
                            )
                        return body
            except WOkadaRequestRejectedError:
                raise
            except (aiohttp.ClientError, asyncio.TimeoutError, WOkadaAPIError) as error:
                last_error = error
                if attempt < self.retry_count:
                    print(
                        "PERINGATAN: request w-okada gagal; "
                        f"endpoint={endpoint}, percobaan={attempt}, detail={error}"
                    )
                    await asyncio.sleep(self.retry_delay_seconds)
        if last_error is None:
            raise WOkadaAPIError(f"Request w-okada {endpoint} berhenti tanpa hasil.")
        raise WOkadaAPIError(
            f"Request w-okada {endpoint} gagal setelah {self.retry_count} percobaan: "
            f"{last_error}"
        ) from last_error

    async def _get_json(self, endpoint: str) -> dict[str, object]:
        value: object = await self._request_json("GET", endpoint, None)
        if not isinstance(value, dict):
            raise WOkadaAPIError(f"Respons w-okada {endpoint} bukan object JSON.")
        return value

    async def _get_json_value(self, endpoint: str) -> object:
        return await self._request_json("GET", endpoint, None)

    async def _put_json(self, endpoint: str, payload: dict[str, object]) -> object:
        return await self._request_json("PUT", endpoint, payload)

    async def _request_json(
        self,
        method: str,
        endpoint: str,
        payload: dict[str, object] | None,
    ) -> object:
        last_error: Exception | None = None
        for attempt in range(1, self.retry_count + 1):
            try:
                timeout: aiohttp.ClientTimeout = aiohttp.ClientTimeout(
                    total=self.timeout_seconds
                )
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    async with session.request(
                        method,
                        self.base_url + endpoint,
                        json=payload,
                    ) as response:
                        body: str = await response.text()
                        if response.status != 200:
                            raise WOkadaAPIError(
                                f"w-okada {method} {endpoint} gagal: "
                                f"status={response.status}, body={body}"
                            )
                        try:
                            return await response.json(content_type=None)
                        except ValueError as error:
                            raise WOkadaAPIError(
                                f"w-okada {method} {endpoint} tidak menghasilkan JSON: {body}"
                            ) from error
            except (aiohttp.ClientError, asyncio.TimeoutError, WOkadaAPIError) as error:
                last_error = error
                if attempt < self.retry_count:
                    print(
                        "PERINGATAN: request w-okada gagal; "
                        f"method={method}, endpoint={endpoint}, "
                        f"percobaan={attempt}, detail={error}"
                    )
                    await asyncio.sleep(self.retry_delay_seconds)
        if last_error is None:
            raise WOkadaAPIError(f"Request w-okada {method} {endpoint} berhenti tanpa hasil.")
        raise WOkadaAPIError(
            f"Request w-okada {method} {endpoint} gagal setelah "
            f"{self.retry_count} percobaan: {last_error}"
        ) from last_error

    async def _run_ffmpeg(self, arguments: tuple[str, ...]) -> None:
        process: asyncio.subprocess.Process = await asyncio.create_subprocess_exec(
            *arguments,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await process.communicate()
        if process.returncode != 0:
            detail: str = stderr.decode("utf-8", errors="replace")
            raise RuntimeError(
                f"FFmpeg gagal: exit_code={process.returncode}, args={arguments}, stderr={detail}"
            )

    def _require_int(self, data: dict[str, object], key: str) -> int:
        value: object = data.get(key)
        if not isinstance(value, int):
            raise WOkadaAPIError(f"Field integer '{key}' tidak ditemukan pada respons w-okada.")
        return value
