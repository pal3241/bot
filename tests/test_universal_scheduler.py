import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from scheduler.manager import SchedulerManager


class DummyClient:
    def get_channel(self, channel_id: int):
        return None

    async def fetch_channel(self, channel_id: int):
        raise RuntimeError(f"unused channel {channel_id}")


class UniversalSchedulerTests(unittest.IsolatedAsyncioTestCase):
    async def test_custom_job_is_persisted_and_dispatchable(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            manager = SchedulerManager(
                DummyClient(),  # type: ignore[arg-type]
                Path(folder) / "schedule.db",
            )
            executed: list[tuple[str, dict[str, object]]] = []

            async def music_play(job) -> None:
                executed.append((job.job_type, dict(job.payload)))

            manager.register_job_type(
                "music.play",
                "test music job",
                music_play,
            )
            await manager.start()
            item = await manager.create_job(
                guild_id=1,
                channel_id=2,
                creator_id=3,
                job_type="music.play",
                payload={"query": "Yoasobi Idol"},
                delay_seconds=3600,
            )

            self.assertEqual(item.job_type, "music.play")
            self.assertEqual(item.payload, {"query": "Yoasobi Idol"})
            loaded = await manager.store.get(item.id)
            self.assertIsNotNone(loaded)
            if loaded is None:
                self.fail("Scheduled job hilang setelah persist.")
            self.assertEqual(loaded.job_type, "music.play")
            self.assertEqual(loaded.payload["query"], "Yoasobi Idol")

            await manager.registry.execute(loaded)
            self.assertEqual(
                executed,
                [("music.play", {"query": "Yoasobi Idol"})],
            )
            await manager.close()

    async def test_unregistered_job_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            manager = SchedulerManager(
                DummyClient(),  # type: ignore[arg-type]
                Path(folder) / "schedule.db",
            )
            await manager.start()
            with self.assertRaises(ValueError):
                await manager.create_job(
                    guild_id=1,
                    channel_id=2,
                    creator_id=3,
                    job_type="music.play",
                    payload={"query": "x"},
                    delay_seconds=10,
                )
            await manager.close()

    async def test_legacy_message_api_maps_to_discord_message_job(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            manager = SchedulerManager(
                DummyClient(),  # type: ignore[arg-type]
                Path(folder) / "schedule.db",
            )
            await manager.start()
            item = await manager.create(
                guild_id=1,
                channel_id=2,
                creator_id=3,
                content="test reminder",
                mention_user_id=99,
                delay_seconds=10,
            )
            self.assertEqual(item.job_type, "discord.message")
            self.assertEqual(item.content, "test reminder")
            self.assertEqual(item.mention_user_id, 99)
            await manager.close()

    async def test_failed_job_uses_backoff_then_marks_failed(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            manager = SchedulerManager(
                DummyClient(),  # type: ignore[arg-type]
                Path(folder) / "schedule.db",
            )

            async def failing_job(job) -> None:
                del job
                raise RuntimeError("network down")

            manager.register_job_type("music.play", "test music job", failing_job)
            await manager.start()
            item = await manager.create_job(
                guild_id=1,
                channel_id=2,
                creator_id=3,
                job_type="music.play",
                payload={"query": "x"},
                delay_seconds=3600,
                max_retries=2,
            )

            now = datetime(2026, 9, 5, 10, 0, tzinfo=timezone.utc)
            await manager._execute_due(item, now)
            first = await manager.store.get(item.id)
            self.assertIsNotNone(first)
            assert first is not None
            self.assertTrue(first.active)
            self.assertEqual(first.retry_count, 1)
            self.assertEqual(
                first.next_run_at,
                (now + timedelta(seconds=30)).isoformat(),
            )
            self.assertEqual(first.last_error, "RuntimeError: network down")

            await manager._execute_due(first, now + timedelta(seconds=30))
            final = await manager.store.get(item.id)
            self.assertIsNotNone(final)
            assert final is not None
            self.assertFalse(final.active)
            self.assertEqual(final.retry_count, 2)
            self.assertEqual(final.failed_at, (now + timedelta(seconds=30)).isoformat())
            await manager.close()

    async def test_run_now_moves_active_job_to_current_time(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            manager = SchedulerManager(
                DummyClient(),  # type: ignore[arg-type]
                Path(folder) / "schedule.db",
            )
            await manager.start()
            item = await manager.create_job(
                guild_id=1,
                channel_id=2,
                creator_id=3,
                job_type="discord.message",
                payload={"message": "soon"},
                delay_seconds=3600,
            )

            self.assertTrue(await manager.run_now(item.id, 3, is_owner=False))
            updated = await manager.store.get(item.id)
            self.assertIsNotNone(updated)
            assert updated is not None
            due = await manager.store.due(datetime.now(timezone.utc).isoformat())
            self.assertIn(updated.id, [job.id for job in due])
            await manager.close()


if __name__ == "__main__":
    unittest.main()
