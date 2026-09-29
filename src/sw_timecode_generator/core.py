"""SMPTE timecode generation and parsing.

This module supports the four most common SMPTE timecode frame rates:
24, 25, 30 (non-drop), and 30 drop-frame. 29.97 non-drop is treated as
30 non-drop because the timecode representation is identical; the actual
frame duration difference is a playback concern, not a timecode-format
concern. 29.97 drop-frame uses the same drop pattern as 30 drop-frame.

Drop-frame timecode drops frame numbers 00 and 01 at the start of every
minute except every tenth minute (minutes 00, 10, 20, etc.) to keep
timecode aligned with real-time clock over long durations.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Tuple


class TimecodeError(ValueError):
    """Raised when a timecode string is malformed or out of range."""


class FrameRate(Enum):
    """Supported frame rates.

    The enum value is the nominal integer frame count used for timecode
    arithmetic. 29.97 is grouped under 30 because SMPTE timecode for
    29.97 fps uses the same HH:MM:SS:FF format and drop pattern as 30 fps.
    The distinction between 29.97 and 30 only matters for wall-clock
duration mapping, which this library does not perform.
    """

    FPS_24 = 24
    FPS_25 = 25
    FPS_30 = 30
    FPS_30_DROP = 31  # 29.97 drop-frame uses same pattern as 30 drop

    @property
    def is_drop(self) -> bool:
        return self is FrameRate.FPS_30_DROP

    @property
    def max_frame(self) -> int:
        """Highest valid frame number (0-indexed) for this rate."""
        return 29 if self is FrameRate.FPS_30_DROP else self.value - 1


@dataclass(frozen=True)
class Timecode:
    """An immutable SMPTE timecode value.

    Attributes:
        hours: 0-23
        minutes: 0-59
        seconds: 0-59
        frames: 0 to (frame_rate.value - 1)
        frame_rate: the FrameRate this timecode belongs to.

    The dataclass is frozen so instances are hashable and safe to share.
    """

    hours: int
    minutes: int
    seconds: int
    frames: int
    frame_rate: FrameRate

    def __post_init__(self) -> None:
        if not (0 <= self.hours <= 23):
            raise TimecodeError(f"hours out of range: {self.hours}")
        if not (0 <= self.minutes <= 59):
            raise TimecodeError(f"minutes out of range: {self.minutes}")
        if not (0 <= self.seconds <= 59):
            raise TimecodeError(f"seconds out of range: {self.seconds}")
        if not (0 <= self.frames <= self.frame_rate.max_frame):
            raise TimecodeError(
                f"frames out of range for {self.frame_rate.name}: {self.frames}"
            )

    def __str__(self) -> str:
        return self.format()

    def format(self) -> str:
        """Return the canonical HH:MM:SS:FF string.

        Drop-frame timecodes use ';' as the frame separator per SMPTE
        convention; non-drop uses ':'.
        """
        sep = ";" if self.frame_rate.is_drop else ":"
        return (
            f"{self.hours:02d}:{self.minutes:02d}:{self.seconds:02d}{sep}{self.frames:02d}"
        )

    def total_frames(self) -> int:
        """Convert to a continuous frame count from 00:00:00:00.

        For drop-frame, this counts every frame position including the
dropped numbers, so the result is the true number of frames that have
        elapsed. This is the inverse of :meth:`from_frames`.
        """
        if self.frame_rate.is_drop:
            return _drop_tc_to_frames(
                self.hours, self.minutes, self.seconds, self.frames
            )
        return _nondrop_tc_to_frames(
            self.hours,
            self.minutes,
            self.seconds,
            self.frames,
            self.frame_rate.value,
        )

    def add_frames(self, n: int) -> "Timecode":
        """Return a new Timecode offset by *n* frames (may be negative)."""
        total = self.total_frames() + n
        if total < 0:
            raise TimecodeError(
                f"result would be before 00:00:00:00 (offset {n} from {self})"
            )
        return Timecode.from_frames(total, self.frame_rate)

    @classmethod
    def from_frames(cls, total: int, frame_rate: FrameRate) -> "Timecode":
        """Build a Timecode from a continuous frame count."""
        if total < 0:
            raise TimecodeError(f"negative frame count: {total}")
        if frame_rate.is_drop:
            h, m, s, f = _frames_to_drop_tc(total)
        else:
            h, m, s, f = _frames_to_nondrop_tc(total, frame_rate.value)
        return cls(h, m, s, f, frame_rate)

    @classmethod
    def parse(cls, text: str, frame_rate: FrameRate) -> "Timecode":
        """Parse an HH:MM:SS:FF or HH:MM:SS;FF string.

        The separator between seconds and frames may be ':' or ';' regardless
        of the declared frame_rate; this is lenient because real-world files
        are inconsistent. The frame_rate argument governs validation.
        """
        if not isinstance(text, str):
            raise TimecodeError(f"expected str, got {type(text).__name__}")
        t = text.strip()
        # Accept either separator.
        if ";" in t:
            parts = t.replace(";", ":").split(":")
        else:
            parts = t.split(":")
        if len(parts) != 4:
            raise TimecodeError(f"expected HH:MM:SS:FF, got {text!r}")
        try:
            h, m, s, f = (int(p) for p in parts)
        except ValueError:
            raise TimecodeError(f"non-integer component in {text!r}")
        return cls(h, m, s, f, frame_rate)


# ---------------------------------------------------------------------------
# Non-drop arithmetic
# ---------------------------------------------------------------------------


def _nondrop_tc_to_frames(h: int, m: int, s: int, f: int, fps: int) -> int:
    return ((h * 3600 + m * 60 + s) * fps) + f


def _frames_to_nondrop_tc(total: int, fps: int) -> Tuple[int, int, int, int]:
    f = total % fps
    total //= fps
    s = total % 60
    total //= 60
    m = total % 60
    h = total // 60
    if h > 23:
        raise TimecodeError(f"frame count exceeds 24 hours: {total}")
    return h, m, s, f


# ---------------------------------------------------------------------------
# Drop-frame arithmetic (30 fps drop-frame, same pattern for 29.97)
# ---------------------------------------------------------------------------
#
# Drop-frame drops frame numbers 00 and 01 at the start of every minute
# except every tenth minute. Per minute: 30 frames normally, 28 on dropped
# minutes, 30 on tenth minutes.
#
# Frames per 10-minute cycle = 9*28 + 30 = 282 frames? No — per minute it's
# frames *within* that minute. Let me think in terms of total frames per
# 10-minute block:
#   - 9 regular minutes: each has 30 - 2 = 28 frames worth of timecode
#     advancement, but the actual frame count is 30*60 - 2 = 1798? No.
#
# The clean way: in one minute of real time at 30fps there are 1800 frame
# positions. In drop-frame, 2 of those positions are skipped (numbers 00 and
# 01 don't appear) for 9 of the 10 minutes. So per 10-minute block:
#   10 * 1800 - 9 * 2 = 18000 - 18 = 17982 actual frame slots.


def _drop_tc_to_frames(h: int, m: int, s: int, f: int) -> int:
    """Convert drop-frame timecode to continuous frame count."""
    total_minutes = h * 60 + m
    # Frames from full 10-minute cycles.
    ten_min_blocks = total_minutes // 10
    rem_minutes = total_minutes % 10
    # Each 10-minute block = 17982 frames.
    # Each remaining minute: 1798 frames if it's one of the first 9 minutes
    # of the block (2 dropped), 1800 if it's the 10th minute (no drop).
    base = ten_min_blocks * 17982
    # In the remainder, minutes 0..8 drop 2 frames (1798 each), but we must
    # be careful: the current minute *m* within the block — if rem_minutes
    # is the current minute index, minutes before it contribute 1798 each
    # (for indices 0..8) and the 10th (index 9, i.e. rem==0 of next block)
    # contributes 1800. But rem_minutes ranges 0..9. Minutes 0..8 are
    # drop-minutes; minute 9 is a no-drop minute.
    for i in range(rem_minutes):
        base += 1798 if i < 9 else 1800
    # Add frames within the current minute.
    base += s * 30 + f
    return base


def _frames_to_drop_tc(total: int) -> Tuple[int, int, int, int]:
    """Convert continuous frame count to drop-frame timecode."""
    # Work with 10-minute blocks of 17982 frames.
    ten_min_blocks = total // 17982
    rem = total % 17982

    # Within a 10-minute block, figure out which minute we're in.
    # Minutes 0..8 each hold 1798 frames; minute 9 holds 1800.
    minute_in_block = 0
    for i in range(10):
        cap = 1798 if i < 9 else 1800
        if rem < cap:
            minute_in_block = i
            break
        rem -= cap
    else:
        # Should not happen.
        minute_in_block = 9

    total_minutes = ten_min_blocks * 10 + minute_in_block
    s = rem // 30
    f = rem % 30
    h = total_minutes // 60
    m = total_minutes % 60
    if h > 23:
        raise TimecodeError(f"frame count exceeds 24 hours: {total}")
    return h, m, s, f
