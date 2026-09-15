import tempfile
import unittest
from pathlib import Path

from expression.loader import empty_catalog
from expression.local_gif_pack import CURATED_GIFS, curated_local_assets, merge_curated_gifs


class CuratedLocalGifPackTests(unittest.TestCase):
    def test_manifest_keys_filenames_and_urls_are_unique(self) -> None:
        self.assertGreaterEqual(len(CURATED_GIFS), 8)
        self.assertEqual(len({item.key for item in CURATED_GIFS}), len(CURATED_GIFS))
        self.assertEqual(
            len({item.filename for item in CURATED_GIFS}),
            len(CURATED_GIFS),
        )
        self.assertEqual(
            len({item.source_url for item in CURATED_GIFS}),
            len(CURATED_GIFS),
        )
        for item in CURATED_GIFS:
            self.assertTrue(item.filename.endswith(".gif"))
            self.assertTrue(item.source_url.startswith("https://"))
            self.assertTrue(item.source_page.startswith("https://tenor.com/"))

    def test_only_valid_local_files_become_expression_assets(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            first = CURATED_GIFS[0]
            (root / first.filename).write_bytes(b"GIF89a")

            assets = curated_local_assets(root)
            self.assertEqual(len(assets), 1)
            self.assertEqual(assets[0].key, first.key)
            self.assertEqual(assets[0].local_path, (root / first.filename).resolve())
            self.assertTrue(assets[0].animated)
            self.assertTrue(assets[0].safe)

    def test_merge_is_idempotent_for_curated_keys(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            first = CURATED_GIFS[0]
            (root / first.filename).write_bytes(b"GIF87a")

            catalog = merge_curated_gifs(empty_catalog(), root)
            catalog = merge_curated_gifs(catalog, root)
            self.assertEqual([asset.key for asset in catalog.gifs], [first.key])


if __name__ == "__main__":
    unittest.main()
