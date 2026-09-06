import asyncio
import unittest

from ui.flet_app_runtime_compat import SenaFletUI


class _FakePage:
    def __init__(self) -> None:
        self.dialog = None
        self.show_calls = 0
        self.pop_calls = 0
        self.update_calls = 0

    def show_dialog(self, dialog) -> None:
        self.dialog = dialog
        self.show_calls += 1

    def pop_dialog(self) -> None:
        self.dialog = None
        self.pop_calls += 1

    def update(self) -> None:
        self.update_calls += 1


class FletDialogCompatTests(unittest.IsolatedAsyncioTestCase):
    async def test_process_confirmation_uses_show_dialog(self) -> None:
        ui = object.__new__(SenaFletUI)
        ui.page = _FakePage()
        ui._restart_requested = False
        ui._shutdown_event = asyncio.Event()

        await ui._show_process_confirmation(restart=False)

        self.assertEqual(ui.page.show_calls, 1)
        self.assertIsNotNone(ui.page.dialog)
        self.assertEqual(ui.page.update_calls, 1)


if __name__ == "__main__":
    unittest.main()
