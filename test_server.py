"""Tests for channel list seeding. Standard library only, like the service.

Run with: python3 -m unittest discover -v
"""
import os
import tempfile
import unittest

import server


class ResolveChannelsFile(unittest.TestCase):
    """The volume holds the live list; the image holds the shipped one.

    A refreshed image must reach the volume, but a list the operator edited
    by hand must survive. The seed stamp records which shipped list produced
    the file, which is what tells those two cases apart.
    """

    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.volume = os.path.join(self.dir.name, "data", "channels.txt")
        self.bundled = os.path.join(self.dir.name, "app", "channels.txt")
        os.makedirs(os.path.dirname(self.bundled))
        self.write(self.bundled, "LA 1 HD\nLA 2 HD\n")

    def write(self, path, text):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)

    def read(self, path):
        with open(path, encoding="utf-8") as fh:
            return fh.read()

    def resolve(self):
        return server.resolve_channels_file(self.volume, self.bundled)

    def test_seeds_an_empty_volume(self):
        self.assertEqual(self.resolve(), self.volume)
        self.assertEqual(self.read(self.volume), self.read(self.bundled))

    def test_leaves_an_up_to_date_volume_alone(self):
        self.resolve()
        os.utime(self.volume, (0, 0))
        before = os.stat(self.volume).st_mtime
        self.resolve()
        self.assertEqual(os.stat(self.volume).st_mtime, before)

    def test_reseeds_when_the_image_ships_a_new_list(self):
        """The bug this fixes: a redeploy used to leave the old list in place."""
        self.resolve()
        self.write(self.bundled, "LA 1 HD\nLA 2 HD\nETB1\n")
        self.resolve()
        self.assertEqual(self.read(self.volume), self.read(self.bundled))

    def test_keeps_a_hand_edited_list(self):
        self.resolve()
        self.write(self.volume, "ONLY MINE\n")
        self.write(self.bundled, "LA 1 HD\nLA 2 HD\nETB1\n")
        self.resolve()
        self.assertEqual(self.read(self.volume), "ONLY MINE\n")

    def test_adopts_a_volume_seeded_before_stamps_existed(self):
        """Volumes already deployed carry no stamp; they still need the refresh."""
        self.write(self.volume, "LA 1 HD\n")
        self.resolve()
        self.assertEqual(self.read(self.volume), self.read(self.bundled))
        self.assertEqual(self.read(self.volume + ".bak"), "LA 1 HD\n")

    def test_falls_back_to_the_bundled_list_when_the_volume_is_read_only(self):
        os.makedirs(os.path.dirname(self.volume))
        os.chmod(os.path.dirname(self.volume), 0o500)
        self.addCleanup(os.chmod, os.path.dirname(self.volume), 0o700)
        self.assertEqual(self.resolve(), self.bundled)

    def test_reports_when_no_list_exists_at_all(self):
        os.remove(self.bundled)
        with self.assertRaises(RuntimeError):
            self.resolve()


if __name__ == "__main__":
    unittest.main()
