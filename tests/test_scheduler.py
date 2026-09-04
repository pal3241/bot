import tempfile
import unittest
from pathlib import Path

from scheduler.manager import SchedulerManager


class FakeChannel:
    def __init__(self, channel_id: int) -> None:
        self.id = channel_id
        self.sent: list[tuple[str, object]] = []

    async def send(self, content: str, *, allowed_mentions: object) -> None:
        self.sent.append((content, allowed_mentions))


class FakeClient:
    def __init__(self, channel: FakeChannel) -> None:
        self.channel = channel

    def get_channel(self, channel_id: int):
        return self.channel if channel_id == self.channel.id else None

    async def fetch_channel(self, channel_id: int):
        if channel_id != self.channel.id:
            raise LookupError(channel_id)
        return self.channel


class SchedulerTests(unittest.IsolatedAsyncioTestCase):
    async def test_create_persist_cancel_ownership_and_mention_send(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            channel = FakeChannel(10)
            client = FakeClient(channel)
            manager = SchedulerManager(client, Path(folder) / "schedule.db")
            await manager.start()

            item = await manager.create(
                guild_id=1,
                channel_id=10,
                creator_id=100,
                content="jangan lupa tugas",
                mention_user_id=200,
                delay_seconds=60,
            )
            self.assertEqual(item.creator_id, 100)
            self.assertEqual(item.mention_user_id, 200)
            self.assertEqual(len(await manager.list_for_user(100)), 1)
            self.assertEqual(len(await manager.list_for_user(999)), 0)

            with self.assertRaises(PermissionError):
                await manager.cancel(item.id, 999, is_owner=False)

            await manager._send_schedule(item)
            self.assertEqual(channel.sent[0][0], "<@200> jangan lupa tugas")

            self.assertTrue(await manager.cancel(item.id, 100, is_owner=False))
            self.assertEqual(len(await manager.list_for_user(100)), 0)
            await manager.close()

            restarted = SchedulerManager(client, Path(folder) / "schedule.db")
            await restarted.start()
            self.assertEqual(len(await restarted.list_for_user(100)), 0)
            await restarted.close()


if __name__ == "__main__":
    unittest.main()
