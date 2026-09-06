import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from scheduler.control import ScheduleBucket, classify_job, list_jobs, retry_failed
from scheduler.manager import SchedulerManager


class DummyClient:
    def get_channel(self, channel_id: int):
        return None

    async def fetch_channel(self, channel_id: int):
        raise RuntimeError(f"unused channel {channel_id}")


class SchedulerControlTests(unittest.IsolatedAsyncioTestCase):
    async def test_retry_failed_reactivates_and_resets_failure_state(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            manager = SchedulerManager(
                DummyClient(),  # type: ignore[arg-type]
                Path(folder) / "schedule.db",
            )

            async def failing_job(job) -> None:
                del job
                raise RuntimeError("network down")

            manager.register_job_type("test.fail", "always fails", failing_job)
            await manager.start()
            item = await manager.create_job(
                guild_id=1,
                channel_id=2,
                creator_id=10,
                job_type="test.fail",
                payload={"x": 1},
                delay_seconds=3600,
                max_retries=1,
            )

            now = datetime(2026, 9, 6, 6, 0, tzinfo=timezone.utc)
            await manager._execute_due(item, now)
            failed = await manager.store.get(item.id)
            self.assertIsNotNone(failed)
            assert failed is not None
            self.assertFalse(failed.active)
            self.assertIsNotNone(failed.failed_at)
            self.assertEqual(failed.retry_count, 1)
            self.assertEqual(classify_job(failed), ScheduleBucket.FAILED)

            with self.assertRaises(PermissionError):
                await retry_failed(
                    manager,
                    item.id,
                    requester_id=999,
                    is_owner=False,
                )

            self.assertTrue(
                await retry_failed(
                    manager,
                    item.id,
                    requester_id=10,
                    is_owner=False,
                )
            )
            recovered = await manager.store.get(item.id)
            self.assertIsNotNone(recovered)
            assert recovered is not None
            self.assertTrue(recovered.active)
            self.assertIsNone(recovered.failed_at)
            self.assertIsNone(recovered.last_error)
            self.assertEqual(recovered.retry_count, 0)
            self.assertEqual(classify_job(recovered), ScheduleBucket.UPCOMING)

            due = await manager.store.due(datetime.now(timezone.utc).isoformat())
            self.assertIn(item.id, [job.id for job in due])
            await manager.close()

    async def test_list_jobs_exposes_active_failed_and_completed_history(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            manager = SchedulerManager(
                DummyClient(),  # type: ignore[arg-type]
                Path(folder) / "schedule.db",
            )
            await manager.start()

            upcoming = await manager.create_job(
                guild_id=1,
                channel_id=2,
                creator_id=10,
                job_type="discord.message",
                payload={"message": "upcoming"},
                delay_seconds=3600,
            )
            recurring = await manager.create_job(
                guild_id=1,
                channel_id=2,
                creator_id=10,
                job_type="discord.message",
                payload={"message": "repeat"},
                delay_seconds=3600,
                recurrence_seconds=120,
            )
            completed = await manager.create_job(
                guild_id=1,
                channel_id=2,
                creator_id=10,
                job_type="discord.message",
                payload={"message": "done"},
                delay_seconds=3600,
            )
            await manager.store.mark_complete(
                completed.id,
                datetime.now(timezone.utc).isoformat(),
            )

            failed = await manager.create_job(
                guild_id=1,
                channel_id=2,
                creator_id=10,
                job_type="discord.message",
                payload={"message": "failed"},
                delay_seconds=3600,
            )
            await manager.store.mark_failed(
                failed.id,
                datetime.now(timezone.utc).isoformat(),
                retry_count=5,
                last_error="RuntimeError: boom",
            )

            items = await list_jobs(manager, 10, include_all=False)
            buckets = {item.id: classify_job(item) for item in items}
            self.assertEqual(buckets[upcoming.id], ScheduleBucket.UPCOMING)
            self.assertEqual(buckets[recurring.id], ScheduleBucket.RECURRING)
            self.assertEqual(buckets[completed.id], ScheduleBucket.COMPLETED)
            self.assertEqual(buckets[failed.id], ScheduleBucket.FAILED)

            other = await manager.create_job(
                guild_id=1,
                channel_id=2,
                creator_id=99,
                job_type="discord.message",
                payload={"message": "other"},
                delay_seconds=3600,
            )
            user_items = await list_jobs(manager, 10, include_all=False)
            self.assertNotIn(other.id, [item.id for item in user_items])
            owner_items = await list_jobs(manager, 10, include_all=True)
            self.assertIn(other.id, [item.id for item in owner_items])
            await manager.close()


if __name__ == "__main__":
    unittest.main()
