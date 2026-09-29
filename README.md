# SW Timecode Generator

Generates and parses SMPTE timecodes (HH:MM:SS:FF) for 24, 25, 30 non-drop, and 30 drop-frame frame rates.

## Usage

```python
from sw_timecode_generator import Timecode, FrameRate

tc = Timecode(0, 1, 0, 0, FrameRate.FPS_30_DROP)
print(tc)              # 00:01:00;00
print(tc.format())     # 00:01:00;00

parsed = Timecode.parse("01:02:03:04", FrameRate.FPS_24)
print(parsed.total_frames())  # 93724

next_tc = tc.add_frames(1)
print(next_tc)         # 00:01:00;02

from_zero = Timecode.from_frames(1798, FrameRate.FPS_30_DROP)
print(from_zero)       # 00:01:00;00
```

## Why this exists

Video and audio production tools exchange timecodes constantly, and the string format is simple enough that hand-rolling a parser is tempting — until you hit drop-frame. Drop-frame timecode skips frame numbers 00 and 01 at the start of every minute except every tenth minute, which makes naive frame arithmetic wrong by ~108 frames per hour. This library handles that arithmetic correctly so callers don't have to.

The trade-off: this library only handles timecode as a *label*. It does not map timecodes to wall-clock duration, because that requires knowing the true frame rate (29.97 vs 30) and whether the media is NTSC or exact. If you need real-time duration, convert `total_frames()` and divide by your actual playback fps yourself.

## Edge cases you will hit

- **29.97 non-drop** is treated as 30 non-drop. The timecode strings are identical; the difference is only in playback speed. `FrameRate.FPS_30` covers both.
- **29.97 drop-frame** uses `FrameRate.FPS_30_DROP`. The drop pattern is the same as 30 drop-frame.
- **Parsing is lenient about separators.** `Timecode.parse("00;01;00;00", FrameRate.FPS_30)` works even though non-drop conventionally uses colons. The `frame_rate` argument, not the separator, determines validation.
- **24-hour limit.** Timecodes beyond 23:59:59:(max-frame) raise `TimecodeError`. SMPTE timecode is not defined past 24 hours.
- **Drop-frame formatting uses `;`** between seconds and frames per SMPTE convention. Non-drop uses `:`.

## Exports

- `Timecode` — frozen dataclass with `hours`, `minutes`, `seconds`, `frames`, `frame_rate` fields. Methods: `format()`, `total_frames()`, `add_frames(n)`, classmethods `parse(text, frame_rate)` and `from_frames(total, frame_rate)`.
- `FrameRate` — enum: `FPS_24`, `FPS_25`, `FPS_30`, `FPS_30_DROP`.
- `TimecodeError` — subclass of `ValueError`, raised on all parse and range errors.
