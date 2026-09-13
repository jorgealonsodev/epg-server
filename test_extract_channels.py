"""Tests for the channel extraction tool. Standard library only.

Run with: python3 -m unittest discover -v
"""
import os
import tempfile
import unittest

import extract_channels as ex

PLAYLIST = """#EXTM3U
#EXTINF:-1 tvg-id="" tvg-name="LA 1 HD" group-title="[ES] TDT",LA 1 HD
http://host:25461/user/pass/1
#EXTINF:-1 tvg-id="" tvg-name="LA 2 HD" group-title="[ES] TDT",LA 2 HD
http://host:25461/user/pass/2
#EXTINF:-1 tvg-name="Alien, el octavo pasajero" group-title="VOD ES",Alien, el octavo pasajero
http://host:8800/movie/user/pass/3
#EXTINF:-1 tvg-name="#DAZN 1 FULL HD" group-title="[ES] SPORT",#DAZN 1 FULL HD
http://host:25461/user/pass/4
#EXTINF:-1 tvg-name="LA 1 HD" group-title="[ES] 4K",LA 1 HD
http://host:25461/user/pass/5
"""


class ParseNames(unittest.TestCase):
    def test_keeps_only_the_live_groups(self):
        self.assertNotIn("Alien, el octavo pasajero", ex.parse_names(PLAYLIST))

    def test_reads_the_name_after_the_last_quoted_attribute(self):
        """Titles contain commas, so splitting on the first one is wrong."""
        vod = ex.parse_names(PLAYLIST, group_prefix="VOD ES")
        self.assertEqual(vod, ["Alien, el octavo pasajero"])

    def test_keeps_a_name_that_starts_with_a_hash(self):
        self.assertIn("#DAZN 1 FULL HD", ex.parse_names(PLAYLIST))

    def test_drops_duplicates_and_sorts_case_insensitively(self):
        self.assertEqual(ex.parse_names(PLAYLIST),
                         ["#DAZN 1 FULL HD", "LA 1 HD", "LA 2 HD"])


class Render(unittest.TestCase):
    def test_writes_the_header_and_one_name_per_line(self):
        out = ex.render(["LA 1 HD", "LA 2 HD"])
        self.assertTrue(out.startswith("# "))
        self.assertEqual(out.splitlines()[-2:], ["LA 1 HD", "LA 2 HD"])

    def test_refuses_to_emit_a_stream_url(self):
        """The whole point of this file is that it is safe to commit."""
        with self.assertRaises(ValueError):
            ex.render(["LA 1 HD", "http://host:25461/user/pass/1"])


class Diff(unittest.TestCase):
    def test_reports_what_the_provider_added_and_removed(self):
        added, removed = ex.diff(["A", "B"], ["B", "C"])
        self.assertEqual((added, removed), (["C"], ["A"]))


class Main(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.src = os.path.join(self.dir.name, "playlist.m3u")
        self.out = os.path.join(self.dir.name, "channels.txt")
        with open(self.src, "w", encoding="utf-8") as fh:
            fh.write(PLAYLIST)

    def test_writes_the_list_from_a_local_playlist(self):
        self.assertEqual(ex.main(["--file", self.src, "--out", self.out]), 0)
        with open(self.out, encoding="utf-8") as fh:
            self.assertIn("LA 1 HD", fh.read())

    def test_dry_run_leaves_the_file_alone(self):
        ex.main(["--file", self.src, "--out", self.out, "--dry-run"])
        self.assertFalse(os.path.exists(self.out))

    def test_reports_what_changed_against_the_existing_list(self):
        with open(self.out, "w", encoding="utf-8") as fh:
            fh.write(ex.render(["LA 1 HD", "CANAL VIEJO"]))
        report = ex.Report()
        ex.main(["--file", self.src, "--out", self.out], report=report)
        self.assertEqual(report.added, ["#DAZN 1 FULL HD", "LA 2 HD"])
        self.assertEqual(report.removed, ["CANAL VIEJO"])

    def test_reports_a_source_it_cannot_reach(self):
        missing = os.path.join(self.dir.name, "nope.m3u")
        self.assertNotEqual(ex.main(["--file", missing, "--out", self.out]), 0)

    def test_needs_a_source(self):
        self.assertNotEqual(ex.main(["--out", self.out]), 0)


class SubscriptionUrl(unittest.TestCase):
    """The URL was recorded nowhere once, and regenerating the list stalled."""

    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.env = os.path.join(self.dir.name, ".env")

    def test_reads_it_from_the_env_file(self):
        with open(self.env, "w", encoding="utf-8") as fh:
            fh.write("# comment\nADMIN_TOKEN=xyz\nPLAYLIST_URL=http://panel/get\n")
        self.assertEqual(ex.read_env_file(self.env).get("PLAYLIST_URL"),
                         "http://panel/get")

    def test_strips_quotes_the_way_compose_does(self):
        with open(self.env, "w", encoding="utf-8") as fh:
            fh.write('PLAYLIST_URL="http://panel/get"\n')
        self.assertEqual(ex.read_env_file(self.env).get("PLAYLIST_URL"),
                         "http://panel/get")

    def test_survives_a_missing_env_file(self):
        self.assertEqual(ex.read_env_file(self.env), {})


if __name__ == "__main__":
    unittest.main()
