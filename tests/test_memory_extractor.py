import unittest

from memory.extractor import parse_explicit_memory_command, parse_memory_response
from memory.models import MemoryActionType


class MemoryExtractorTests(unittest.TestCase):
    def test_structured_response_and_invalid_metadata(self) -> None:
        valid = parse_memory_response(
            '{"text":"oke","memory":{"action":"store","category":"preference",'
            '"content":"Owner prefers Python","importance":0.8,"confidence":0.9,'
            '"target_memory_id":null}}'
        )
        self.assertEqual(valid.text, "oke")
        self.assertIsNotNone(valid.candidate)
        invalid = parse_memory_response(
            '{"text":"tetap jawab","memory":{"action":"store","category":"bad",'
            '"content":"x","importance":2,"confidence":0.9}}'
        )
        self.assertEqual(invalid.text, "tetap jawab")
        self.assertIsNone(invalid.candidate)

    def test_explicit_store_and_forget(self) -> None:
        store = parse_explicit_memory_command("ingat bahwa gue lebih suka Python")
        delete = parse_explicit_memory_command("lupakan gue suka Valorant")
        self.assertIsNotNone(store)
        self.assertIsNotNone(delete)
        if store is None or delete is None:
            self.fail("Perintah memory eksplisit gagal dikenali.")
        self.assertEqual(store.action, MemoryActionType.STORE)
        self.assertEqual(delete.action, MemoryActionType.DELETE)


if __name__ == "__main__":
    unittest.main()
