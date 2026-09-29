import unittest

from sw_timecode_generator import Timecode, TimecodeError, FrameRate


class TestFormat(unittest.TestCase):
    def test_format_nondrop_24(self):
        tc = Timecode(1, 2, 3, 4, FrameRate.FPS_24)
        self.assertEqual(str(tc), "01:02:03:04")

    def test_format_nondrop_25(self):
        tc = Timecode(0, 0, 0, 0, FrameRate.FPS_25)
        self.assertEqual(tc.format(), "00:00:00:00")

    def test_format_drop_uses_semicolon(self):
        tc = Timecode(0, 1, 0, 0, FrameRate.FPS_30_DROP)
        self.assertEqual(tc.format(), "00:01:00;00")

    def test_format_30_nondrop_uses_colon(self):
        tc = Timecode(0, 1, 0, 0, FrameRate.FPS_30)
        self.assertEqual(tc.format(), "00:01:00:00")


class TestValidation(unittest.TestCase):
    def test_hours_too_high(self):
        with self.assertRaises(TimecodeError):
            Timecode(24, 0, 0, 0, FrameRate.FPS_24)

    def test_frames_out_of_range_24(self):
        with self.assertRaises(TimecodeError):
            Timecode(0, 0, 0, 24, FrameRate.FPS_24)

    def test_frames_out_of_range_30(self):
        with self.assertRaises(TimecodeError):
            Timecode(0, 0, 0, 30, FrameRate.FPS_30)

    def test_negative_frames(self):
        with self.assertRaises(TimecodeError):
            Timecode(0, 0, 0, -1, FrameRate.FPS_24)


class TestParse(unittest.TestCase):
    def test_parse_basic(self):
        tc = Timecode.parse("01:02:03:04", FrameRate.FPS_24)
        self.assertEqual((tc.hours, tc.minutes, tc.seconds, tc.frames), (1, 2, 3, 4))

    def test_parse_accepts_semicolon_for_nondrop(self):
        tc = Timecode.parse("00;01;00;00", FrameRate.FPS_30)
        self.assertEqual(tc.minutes, 1)

    def test_parse_accepts_colon_for_drop(self):
        tc = Timecode.parse("00:01:00:00", FrameRate.FPS_30_DROP)
        self.assertEqual(tc.frame_rate, FrameRate.FPS_30_DROP)

    def test_parse_bad_length(self):
        with self.assertRaises(TimecodeError):
            Timecode.parse("01:02:03", FrameRate.FPS_24)

    def test_parse_non_integer(self):
        with self.assertRaises(TimecodeError):
            Timecode.parse("01:02:03:ab", FrameRate.FPS_24)

    def test_parse_out_of_range_frames(self):
        with self.assertRaises(TimecodeError):
            Timecode.parse("00:00:00:30", FrameRate.FPS_30)

    def test_parse_strips_whitespace(self):
        tc = Timecode.parse("  01:02:03:04  ", FrameRate.FPS_24)
        self.assertEqual(tc.hours, 1)


class TestNonDropArithmetic(unittest.TestCase):
    def test_total_frames_24(self):
        tc = Timecode(1, 0, 0, 0, FrameRate.FPS_24)
        self.assertEqual(tc.total_frames(), 86400)

    def test_total_frames_with_remainder(self):
        tc = Timecode(0, 1, 1, 1, FrameRate.FPS_30)
        # 61 seconds * 30 + 1 = 1831
        self.assertEqual(tc.total_frames(), 1831)

    def test_from_frames_roundtrip_24(self):
        tc = Timecode.from_frames(86400 + 5, FrameRate.FPS_24)
        self.assertEqual(str(tc), "01:00:00:05")

    def test_add_frames_positive(self):
        tc = Timecode(0, 0, 0, 22, FrameRate.FPS_24)
        result = tc.add_frames(3)
        self.assertEqual(str(result), "00:00:01:01")

    def test_add_frames_negative(self):
        tc = Timecode(0, 0, 1, 0, FrameRate.FPS_24)
        result = tc.add_frames(-2)
        self.assertEqual(str(result), "00:00:00:22")

    def test_add_frames_before_zero(self):
        tc = Timecode(0, 0, 0, 0, FrameRate.FPS_24)
        with self.assertRaises(TimecodeError):
            tc.add_frames(-1)

    def test_rollover_at_24_hours(self):
        tc = Timecode(23, 59, 59, 23, FrameRate.FPS_24)
        with self.assertRaises(TimecodeError):
            tc.add_frames(1)


class TestDropFrameArithmetic(unittest.TestCase):
    def test_drop_first_minute_skips_00_01(self):
        # At 00:01:00;00 we should have advanced 1798 frames from 00:00:00:00.
        tc = Timecode(0, 1, 0, 0, FrameRate.FPS_30_DROP)
        self.assertEqual(tc.total_frames(), 1798)

    def test_drop_tenth_minute_no_drop(self):
        # 00:10:00;00 should be 10 * 1798 + 2*9 ... let's compute directly.
        # 9 drop-minutes * 1798 + 1 no-drop minute * 1800 = 16182 + 1800 = 17982
        tc = Timecode(0, 10, 0, 0, FrameRate.FPS_30_DROP)
        self.assertEqual(tc.total_frames(), 17982)

    def test_drop_roundtrip(self):
        for total in [0, 1, 1797, 1798, 1799, 1800, 17981, 17982, 17983]:
            tc = Timecode.from_frames(total, FrameRate.FPS_30_DROP)
            self.assertEqual(
                tc.total_frames(),
                total,
                f"roundtrip failed for total={total}, got {tc}",
            )

    def test_drop_add_frames_cross_minute(self):
        tc = Timecode(0, 0, 59, 29, FrameRate.FPS_30_DROP)
        result = tc.add_frames(1)
        # 00:00:59;29 + 1 frame -> 00:01:00;02 (frames 00 and 01 are dropped)
        self.assertEqual(str(result), "00:01:00;02")

    def test_drop_add_frames_cross_tenth_minute(self):
        tc = Timecode(0, 9, 59, 29, FrameRate.FPS_30_DROP)
        result = tc.add_frames(1)
        # 00:09:59;29 + 1 -> 00:10:00;00 (no drop on tenth minute)
        self.assertEqual(str(result), "00:10:00;00")

    def test_drop_parse_and_format(self):
        tc = Timecode.parse("01:00:00;00", FrameRate.FPS_30_DROP)
        self.assertEqual(tc.hours, 1)
        self.assertEqual(tc.format(), "01:00:00;00")


class TestFromFramesValidation(unittest.TestCase):
    def test_negative_frame_count(self):
        with self.assertRaises(TimecodeError):
            Timecode.from_frames(-1, FrameRate.FPS_24)


class TestImmutability(unittest.TestCase):
    def test_frozen(self):
        tc = Timecode(0, 0, 0, 0, FrameRate.FPS_24)
        with self.assertRaises(Exception):
            tc.hours = 1  # type: ignore

    def test_hashable(self):
        tc1 = Timecode(1, 2, 3, 4, FrameRate.FPS_24)
        tc2 = Timecode(1, 2, 3, 4, FrameRate.FPS_24)
        self.assertEqual(hash(tc1), hash(tc2))
        self.assertEqual(tc1, tc2)


if __name__ == "__main__":
    unittest.main()
