"""Audio, video and subtitle conversion through ffmpeg.

ffmpeg is one binary that decodes practically every media container. The
target list is derived at run time from ``ffmpeg -encoders`` and
``ffmpeg -muxers``: a format is offered only when both its container muxer
and at least one suitable encoder are compiled in.
"""

from __future__ import annotations

import functools
from pathlib import Path

from omniconv.core import formats
from omniconv.core.engine import Job
from omniconv.core.errors import ConversionError
from omniconv.core.procs import run
from omniconv.core.registry import converter
from omniconv.core.requirements import Tool
from omniconv.converters._common import parse_time, tool_output

FFMPEG = Tool("ffmpeg", package="ffmpeg")
FFPROBE = Tool("ffprobe", package="ffmpeg")

# target format -> (muxer, audio encoder candidates in preference order)
AUDIO_TARGETS: dict[str, tuple[str, tuple[str, ...]]] = {
    "mp3": ("mp3", ("libmp3lame", "libshine")),
    "wav": ("wav", ("pcm_s16le",)),
    "flac": ("flac", ("flac",)),
    "ogg": ("ogg", ("libvorbis", "vorbis")),
    "opus": ("opus", ("libopus", "opus")),
    "aac": ("adts", ("aac", "libfdk_aac")),
    "m4a": ("ipod", ("aac", "libfdk_aac")),
    "m4b": ("ipod", ("aac",)),
    "alac": ("ipod", ("alac",)),
    "wma": ("asf", ("wmav2", "wmav1")),
    "aiff": ("aiff", ("pcm_s16be",)),
    "au": ("au", ("pcm_s16be",)),
    "ac3": ("ac3", ("ac3", "ac3_fixed")),
    "eac3": ("eac3", ("eac3",)),
    "dts": ("dts", ("dca",)),
    "amr": ("amr", ("libopencore_amrnb",)),
    "mka": ("matroska", ("libvorbis", "flac", "aac")),
    "caf": ("caf", ("pcm_s16le",)),
    "w64": ("w64", ("pcm_s16le",)),
    "mp2": ("mp2", ("mp2", "libtwolame", "mp2fixed")),
    "wv": ("wv", ("wavpack",)),
    "tta": ("tta", ("tta",)),
    "spx": ("ogg", ("libspeex",)),
    "gsm": ("gsm", ("libgsm",)),
    "voc": ("voc", ("pcm_u8",)),
    "mlp": ("mlp", ("mlp",)),
    "weba": ("webm", ("libopus", "libvorbis")),
    "pcm": ("s16le", ("pcm_s16le",)),
    "sbc": ("sbc", ("sbc",)),
    "aptx": ("aptx", ("aptx",)),
    "g722": ("g722", ("g722",)),
    "oma": ("oma", ("atrac3",)),
}

# target -> (muxer, video encoder candidates, audio encoder candidates)
VIDEO_TARGETS: dict[str, tuple[str, tuple[str, ...], tuple[str, ...]]] = {
    "mp4": ("mp4", ("libx264", "libx265", "mpeg4"), ("aac", "libmp3lame")),
    "mkv": ("matroska", ("libx264", "libvpx-vp9", "mpeg4"), ("aac", "libvorbis", "flac")),
    "webm": ("webm", ("libvpx-vp9", "libvpx", "libaom-av1"), ("libopus", "libvorbis")),
    "avi": ("avi", ("mpeg4", "libx264", "libxvid"), ("libmp3lame", "mp2", "ac3")),
    "mov": ("mov", ("libx264", "mpeg4", "prores_ks"), ("aac", "pcm_s16le")),
    "flv": ("flv", ("flv", "libx264"), ("libmp3lame", "aac")),
    "wmv": ("asf", ("wmv2", "wmv1", "msmpeg4"), ("wmav2", "wmav1")),
    "mpeg": ("mpeg", ("mpeg2video", "mpeg1video"), ("mp2",)),
    "ts": ("mpegts", ("libx264", "mpeg2video"), ("aac", "mp2")),
    "3gp": ("3gp", ("libx264", "mpeg4", "h263"), ("aac", "libopencore_amrnb")),
    "ogv": ("ogg", ("libtheora",), ("libvorbis",)),
    "vob": ("vob", ("mpeg2video",), ("ac3", "mp2")),
    "mxf": ("mxf", ("mpeg2video", "dnxhd"), ("pcm_s16le",)),
    "y4m": ("yuv4mpegpipe", ("rawvideo",), ()),
    "dv": ("dv", ("dvvideo",), ("pcm_s16le",)),
    "swf": ("swf", ("flv",), ("libmp3lame",)),
    "f4v": ("f4v", ("libx264",), ("aac",)),
    "h264": ("h264", ("libx264",), ()),
    "hevc": ("hevc", ("libx265",), ()),
    "ivf": ("ivf", ("libvpx-vp9", "libvpx", "libaom-av1"), ()),
    "nut": ("nut", ("libx264", "mpeg4", "ffv1"), ("aac", "libvorbis", "flac")),
    "divx": ("avi", ("mpeg4",), ("libmp3lame",)),
    "gif": ("gif", ("gif",), ()),
    "apng": ("apng", ("apng",), ()),
    "webp": ("webp", ("libwebp_anim", "libwebp"), ()),
    "rm": ("rm", ("rv10", "rv20"), ("ac3",)),
}

SUBTITLE_TARGETS: dict[str, tuple[str, str]] = {
    "srt": ("srt", "subrip"),
    "vtt": ("webvtt", "webvtt"),
    "ass": ("ass", "ass"),
    "ssa": ("ass", "ssa"),
    "ttml": ("ttml", "ttml"),
    "lrc": ("lrc", "text"),
}

# Still-image targets for frame extraction from videos.
FRAME_TARGETS = ("png", "jpeg", "bmp", "tiff", "webp", "ppm", "pgm", "pam", "tga", "dpx", "exr", "qoi", "xbm", "sgi", "pcx", "jp2", "hdr", "wbmp", "fits", "pfm")
_FRAME_CODEC = {"jpeg": "mjpeg", "tiff": "tiff", "png": "png", "bmp": "bmp", "webp": "libwebp", "ppm": "ppm", "pgm": "pgm", "pam": "pam", "tga": "targa", "dpx": "dpx", "exr": "exr", "qoi": "qoi", "xbm": "xbm", "sgi": "sgi", "pcx": "pcx", "jp2": "jpeg2000", "hdr": "hdr", "wbmp": "wbmp", "fits": "fits", "pfm": "pfm"}

# Format-specific constraints (channel/sample-rate) enforced before encoding.
_CONSTRAINTS: dict[str, dict[str, int]] = {
    "amr": {"ar": 8000, "ac": 1},
    "gsm": {"ar": 8000, "ac": 1},
    "g722": {"ar": 16000, "ac": 1},
    "swf": {"ar": 44100},
    "dv": {"ar": 48000, "ac": 2},
    "sbc": {"ac": 2},
    "aptx": {"ar": 48000, "ac": 2},
    "spx": {"ar": 16000, "ac": 1},
    "mlp": {"ar": 48000, "ac": 2},
    "voc": {"ac": 1},
}


@functools.lru_cache(maxsize=1)
def _encoders() -> set[str]:
    exe = FFMPEG.path()
    if not exe:
        return set()
    out: set[str] = set()
    for line in tool_output(exe, "-hide_banner", "-encoders").splitlines():
        parts = line.split()
        if len(parts) >= 2 and len(parts[0]) == 6 and parts[0][0] in "VAS" and parts[0] != "------":
            out.add(parts[1])
    return out


@functools.lru_cache(maxsize=1)
def _muxers() -> set[str]:
    exe = FFMPEG.path()
    if not exe:
        return set()
    out: set[str] = set()
    for line in tool_output(exe, "-hide_banner", "-muxers").splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[0] in ("E", "DE"):
            for name in parts[1].split(","):
                out.add(name)
    return out


def _pick(candidates: tuple[str, ...]) -> str | None:
    encs = _encoders()
    for c in candidates:
        if c in encs:
            return c
    return None


def _audio_targets() -> set[str]:
    muxers = _muxers()
    return {fmt for fmt, (muxer, encs) in AUDIO_TARGETS.items() if muxer in muxers and _pick(encs)}


def _video_targets() -> set[str]:
    muxers = _muxers()
    return {fmt for fmt, (muxer, vencs, _) in VIDEO_TARGETS.items() if muxer in muxers and _pick(vencs)}


def _subtitle_targets() -> set[str]:
    muxers, encs = _muxers(), _encoders()
    return {fmt for fmt, (muxer, enc) in SUBTITLE_TARGETS.items() if muxer in muxers and enc in encs}


def _media_sources() -> set[str]:
    # ffmpeg reads every container in the table except MIDI, which is a
    # score rather than sampled audio and needs a synthesiser.
    return ({f.name for f in formats.all_formats("audio")} | {f.name for f in formats.all_formats("video")}) - {"midi"}


def _video_sources() -> set[str]:
    return {f.name for f in formats.all_formats("video")} | {"gif", "apng", "mng", "fli"}


def _subtitle_sources() -> set[str]:
    return {f.name for f in formats.all_formats("subtitle")} | {f.name for f in formats.all_formats("video")}


def _common_args(job: Job) -> list[str]:
    args: list[str] = []
    start = parse_time(job.opt("start"))
    duration = parse_time(job.opt("duration"))
    if start is not None:
        args += ["-ss", str(start)]
    if duration is not None:
        args += ["-t", str(duration)]
    return args


def _audio_filters(job: Job, tgt: str) -> list[str]:
    filters: list[str] = []
    if job.opt("normalize"):
        filters.append("loudnorm=I=-16:TP=-1.5:LRA=11")
    vol = job.opt("volume")
    if vol:
        filters.append(f"volume={vol}")
    return ["-af", ",".join(filters)] if filters else []


_EXPERIMENTAL = {"dca", "vorbis", "opus", "mlp", "truehd", "sonic", "sonicls", "s302m", "aptx_hd"}


def _audio_codec_args(job: Job, tgt: str) -> list[str]:
    muxer, encs = AUDIO_TARGETS[tgt]
    codec = job.opt("audio_codec") or _pick(encs)
    if codec is None:
        raise ConversionError(f"no encoder available for {tgt}")
    args = ["-vn", "-c:a", codec]
    if codec in _EXPERIMENTAL:
        args += ["-strict", "-2"]
    constraints = _CONSTRAINTS.get(tgt, {})
    ar = job.opt("sample_rate") or constraints.get("ar")
    ac = job.opt("channels") or constraints.get("ac")
    if ar:
        args += ["-ar", str(int(ar))]
    if ac:
        args += ["-ac", str(int(ac))]
    bitrate = job.opt("bitrate")
    if bitrate and codec not in ("flac", "alac", "wavpack", "tta", "mlp") and not codec.startswith("pcm_"):
        args += ["-b:a", str(bitrate)]
    if codec in ("libmp3lame",) and not bitrate:
        args += ["-q:a", "2"]
    if codec == "libvorbis" and not bitrate:
        args += ["-q:a", "5"]
    if job.opt("strip_metadata"):
        args += ["-map_metadata", "-1"]
    args += ["-f", muxer]
    return args


@converter(
    "ffmpeg-audio",
    _media_sources,
    _audio_targets,
    requires=(FFMPEG,),
    cost=10,
    options=("bitrate", "sample_rate", "channels", "normalize", "volume", "start", "duration", "audio_codec", "strip_metadata"),
    description="Audio transcoding and audio extraction from video with ffmpeg",
    same_format=True,
)
def ffmpeg_audio(job: Job) -> list[Path]:
    exe = FFMPEG.path()
    assert exe
    tgt = job.tgt_format.name
    cmd = [exe, "-hide_banner", "-loglevel", "error", "-y", "-i", str(job.source), *_common_args(job), *_audio_filters(job, tgt), *_audio_codec_args(job, tgt), str(job.target)]
    run(cmd)
    return [job.target]


def _video_filters(job: Job, tgt: str) -> list[str]:
    filters: list[str] = []
    w, h = job.opt("width"), job.opt("height")
    if w or h:
        filters.append(f"scale={int(w) if w else -2}:{int(h) if h else -2}")
    elif tgt in ("mp4", "mkv", "mov", "ts", "f4v", "h264", "hevc", "3gp") and not job.opt("video_codec"):
        # H.264/H.265 require even dimensions.
        filters.append("scale=trunc(iw/2)*2:trunc(ih/2)*2")
    fps = job.opt("fps")
    if fps:
        filters.append(f"fps={float(fps)}")
    elif tgt == "gif":
        filters.append("fps=12")
    if job.opt("grayscale"):
        filters.append("format=gray")
    if tgt == "gif":
        filters.append("split[s0][s1];[s0]palettegen=stats_mode=diff[p];[s1][p]paletteuse=dither=bayer")
    if tgt == "dv":
        filters.append("scale=720:576,fps=25")
    return ["-vf" if tgt != "gif" else "-filter_complex", ",".join(filters)] if filters else []


@converter(
    "ffmpeg-video",
    _video_sources,
    _video_targets,
    requires=(FFMPEG,),
    cost=10,
    options=("video_bitrate", "crf", "fps", "width", "height", "no_audio", "video_codec", "audio_codec", "bitrate", "sample_rate", "channels", "start", "duration", "grayscale", "strip_metadata"),
    description="Video transcoding with ffmpeg (also GIF/APNG/WebP animations)",
    same_format=True,
)
def ffmpeg_video(job: Job) -> list[Path]:
    exe = FFMPEG.path()
    assert exe
    tgt = job.tgt_format.name
    muxer, vencs, aencs = VIDEO_TARGETS[tgt]
    vcodec = job.opt("video_codec") or _pick(vencs)
    if vcodec is None:
        raise ConversionError(f"no video encoder available for {tgt}")
    cmd = [exe, "-hide_banner", "-loglevel", "error", "-y", "-i", str(job.source), *_common_args(job)]
    cmd += _video_filters(job, tgt)
    cmd += ["-c:v", vcodec]
    if vcodec in ("libx264", "libx265", "libvpx-vp9", "libvpx", "libaom-av1"):
        crf = job.opt("crf")
        if crf is not None:
            cmd += ["-crf", str(int(crf))]
            if vcodec in ("libvpx-vp9", "libvpx", "libaom-av1"):
                cmd += ["-b:v", "0"]
        elif vcodec in ("libx264", "libx265"):
            cmd += ["-crf", "23", "-preset", "medium"]
        elif vcodec == "libvpx-vp9":
            cmd += ["-crf", "32", "-b:v", "0"]
    if vcodec in ("libx264", "libx265"):
        cmd += ["-pix_fmt", "yuv420p"]
    if vcodec == "rawvideo" and tgt == "y4m":
        cmd += ["-pix_fmt", "yuv420p"]
    vb = job.opt("video_bitrate")
    if vb:
        cmd += ["-b:v", str(vb)]
    if tgt in ("gif", "apng", "webp", "y4m", "h264", "hevc", "ivf") or job.opt("no_audio") or not aencs:
        cmd += ["-an"]
        if tgt in ("gif", "apng", "webp"):
            cmd += ["-loop", "0"]
    else:
        acodec = job.opt("audio_codec") or _pick(aencs)
        if acodec is None:
            cmd += ["-an"]
        else:
            cmd += ["-c:a", acodec]
            constraints = _CONSTRAINTS.get(tgt, {})
            ar = job.opt("sample_rate") or constraints.get("ar")
            ac = job.opt("channels") or constraints.get("ac")
            if ar:
                cmd += ["-ar", str(int(ar))]
            if ac:
                cmd += ["-ac", str(int(ac))]
            if job.opt("bitrate") and not acodec.startswith("pcm_"):
                cmd += ["-b:a", str(job.opt("bitrate"))]
    if tgt in ("mp4", "mov", "m4v", "f4v"):
        cmd += ["-movflags", "+faststart"]
    if job.opt("strip_metadata"):
        cmd += ["-map_metadata", "-1"]
    cmd += ["-f", muxer, str(job.target)]
    run(cmd)
    return [job.target]


@converter(
    "ffmpeg-frames",
    _video_sources,
    FRAME_TARGETS,
    requires=(FFMPEG,),
    cost=12,
    options=("start", "fps", "duration", "width", "height", "quality", "grayscale"),
    description="Extract a still frame (or a frame sequence with --fps) from a video",
)
def ffmpeg_frames(job: Job) -> list[Path]:
    exe = FFMPEG.path()
    assert exe
    tgt = job.tgt_format.name
    codec = _FRAME_CODEC[tgt]
    if codec not in _encoders():
        raise ConversionError(f"ffmpeg has no encoder for {tgt} frames")
    filters: list[str] = []
    w, h = job.opt("width"), job.opt("height")
    if w or h:
        filters.append(f"scale={int(w) if w else -1}:{int(h) if h else -1}")
    if job.opt("grayscale"):
        filters.append("format=gray")
    fps = job.opt("fps")
    start = parse_time(job.opt("start"))
    duration = parse_time(job.opt("duration"))
    cmd = [exe, "-hide_banner", "-loglevel", "error", "-y"]
    if start is not None:
        cmd += ["-ss", str(start)]
    cmd += ["-i", str(job.source)]
    if duration is not None:
        cmd += ["-t", str(duration)]
    q = job.opt("quality")
    quality_args = ["-q:v", str(max(2, min(31, round(31 - int(q) * 29 / 100))))] if q and tgt == "jpeg" else []
    if fps:
        filters.append(f"fps={float(fps)}")
        pattern = job.target.with_name(f"{job.target.stem}-%04d{job.target.suffix}")
        cmd += ["-vf", ",".join(filters)] if filters else []
        cmd += ["-c:v", codec, *quality_args, "-f", "image2", str(pattern)]
        run(cmd)
        outputs = sorted(job.target.parent.glob(f"{job.target.stem}-[0-9][0-9][0-9][0-9]{job.target.suffix}"))
        if not outputs:
            raise ConversionError("ffmpeg produced no frames")
        return outputs
    cmd += ["-vf", ",".join(filters)] if filters else []
    cmd += ["-frames:v", "1", "-c:v", codec, *quality_args, "-f", "image2", str(job.target)]
    run(cmd)
    return [job.target]


@converter(
    "ffmpeg-subtitles",
    _subtitle_sources,
    _subtitle_targets,
    requires=(FFMPEG,),
    cost=10,
    description="Subtitle format conversion and subtitle extraction from video",
)
def ffmpeg_subtitles(job: Job) -> list[Path]:
    exe = FFMPEG.path()
    assert exe
    tgt = job.tgt_format.name
    muxer, enc = SUBTITLE_TARGETS[tgt]
    cmd = [exe, "-hide_banner", "-loglevel", "error", "-y", "-i", str(job.source)]
    if job.src_format.category == "video":
        cmd += ["-map", "0:s:0"]
    cmd += ["-c:s", enc, "-f", muxer, str(job.target)]
    run(cmd)
    return [job.target]


@converter(
    "ffmpeg-concat",
    _media_sources,
    lambda: _audio_targets() | _video_targets(),
    requires=(FFMPEG,),
    cost=15,
    many_to_one=True,
    options=("bitrate", "sample_rate", "channels", "video_bitrate", "crf", "width", "height"),
    description="Concatenate several audio or video files into one",
    predicate=lambda s, t: (formats.get(s).category == "audio") == (t in AUDIO_TARGETS),
)
def ffmpeg_concat(job: Job) -> list[Path]:
    exe = FFMPEG.path()
    assert exe
    tgt = job.tgt_format.name
    n = len(job.sources)
    cmd = [exe, "-hide_banner", "-loglevel", "error", "-y"]
    for src in job.sources:
        cmd += ["-i", str(src)]
    if tgt in AUDIO_TARGETS:
        chain = "".join(f"[{i}:a:0]" for i in range(n)) + f"concat=n={n}:v=0:a=1[a]"
        cmd += ["-filter_complex", chain, "-map", "[a]", *_audio_codec_args(job, tgt)]
    else:
        muxer, vencs, aencs = VIDEO_TARGETS[tgt]
        vcodec = job.opt("video_codec") or _pick(vencs)
        acodec = _pick(aencs) if aencs else None
        w, h = job.opt("width") or 1280, job.opt("height") or 720
        scale = "".join(f"[{i}:v:0]scale={w}:{h}:force_original_aspect_ratio=decrease,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=30[v{i}];" for i in range(n))
        if acodec:
            chain = scale + "".join(f"[v{i}][{i}:a:0]" for i in range(n)) + f"concat=n={n}:v=1:a=1[v][a]"
            cmd += ["-filter_complex", chain, "-map", "[v]", "-map", "[a]", "-c:v", vcodec, "-c:a", acodec]
        else:
            chain = scale + "".join(f"[v{i}]" for i in range(n)) + f"concat=n={n}:v=1:a=0[v]"
            cmd += ["-filter_complex", chain, "-map", "[v]", "-c:v", vcodec, "-an"]
        if vcodec in ("libx264", "libx265"):
            cmd += ["-pix_fmt", "yuv420p"]
        cmd += ["-f", muxer]
    cmd.append(str(job.target))
    run(cmd)
    return [job.target]


def probe(path: Path) -> dict:
    """Return ffprobe's JSON description of a media file (empty on failure)."""
    import json

    exe = FFPROBE.path()
    if not exe:
        return {}
    try:
        out = run([exe, "-v", "quiet", "-print_format", "json", "-show_format", "-show_streams", str(path)], timeout=60)
    except Exception:
        return {}
    try:
        return json.loads(out.stdout.decode("utf-8", "replace"))
    except ValueError:
        return {}


_SLIDESHOW_SOURCES = ("png", "jpeg", "bmp", "tiff", "webp", "gif", "ppm", "pgm", "tga", "pam", "dpx", "exr", "qoi", "sgi", "pcx", "jp2")


@converter(
    "ffmpeg-slideshow",
    _SLIDESHOW_SOURCES,
    _video_targets,
    requires=(FFMPEG,),
    cost=14,
    many_to_one=True,
    options=("fps", "width", "height", "crf", "video_bitrate", "video_codec"),
    description="Turn a sequence of images into a video or animation (--fps frames per second, default 1)",
)
def ffmpeg_slideshow(job: Job) -> list[Path]:
    exe = FFMPEG.path()
    assert exe
    tgt = job.tgt_format.name
    muxer, vencs, _ = VIDEO_TARGETS[tgt]
    vcodec = job.opt("video_codec") or _pick(vencs)
    if vcodec is None:
        raise ConversionError(f"no video encoder available for {tgt}")
    fps = float(job.opt("fps") or 1)
    # The concat demuxer takes a list file; each image is shown for 1/fps seconds.
    listing = job.workdir / "slides.txt"
    lines = []
    def entry(path: Path) -> str:
        # Forward slashes are accepted on every platform and avoid the concat
        # demuxer treating Windows backslashes as escape characters.
        text = str(path.resolve()).replace("\\", "/").replace("'", "'\\''")
        return f"file '{text}'"

    for src in job.sources:
        lines.append(entry(src))
        lines.append(f"duration {1 / fps}")
    if job.sources:
        lines.append(entry(job.sources[-1]))
    listing.write_text("\n".join(lines) + "\n", encoding="utf-8")
    w, h = job.opt("width") or 1280, job.opt("height") or 720
    filters = [f"scale={int(w)}:{int(h)}:force_original_aspect_ratio=decrease", f"pad={int(w)}:{int(h)}:(ow-iw)/2:(oh-ih)/2", "setsar=1", f"fps={max(fps, 1)}"]
    if tgt == "gif":
        filters.append("split[s0][s1];[s0]palettegen[p];[s1][p]paletteuse")
    cmd = [exe, "-hide_banner", "-loglevel", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(listing)]
    cmd += ["-filter_complex" if tgt == "gif" else "-vf", ",".join(filters)]
    cmd += ["-c:v", vcodec, "-an"]
    if vcodec in ("libx264", "libx265"):
        cmd += ["-pix_fmt", "yuv420p", "-crf", str(int(job.opt("crf") or 23))]
    elif vcodec in ("libvpx-vp9", "libvpx"):
        cmd += ["-crf", str(int(job.opt("crf") or 32)), "-b:v", "0"]
    if job.opt("video_bitrate"):
        cmd += ["-b:v", str(job.opt("video_bitrate"))]
    if tgt in ("gif", "apng", "webp"):
        cmd += ["-loop", "0"]
    if tgt in ("mp4", "mov", "f4v"):
        cmd += ["-movflags", "+faststart"]
    cmd += ["-f", muxer, str(job.target)]
    run(cmd)
    return [job.target]
