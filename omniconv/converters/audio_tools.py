"""Stand-alone audio encoders and SoX.

These duplicate what ffmpeg does and are registered at a higher cost, so
they only take over on systems without ffmpeg (or when ffmpeg lacks a
particular encoder, e.g. a build without libmp3lame).
"""

from __future__ import annotations

from pathlib import Path

from omniconv.core.engine import Job
from omniconv.core.procs import run
from omniconv.core.registry import converter
from omniconv.core.requirements import Tool
from omniconv.converters._common import tool_output

SOX = Tool("sox", package="sox")

_SOX_MAP = {
    "wav": "wav", "aiff": "aiff", "au": "au", "voc": "voc", "8svx": "8svx", "gsm": "gsm", "flac": "flac",
    "ogg": "ogg", "mp3": "mp3", "caf": "caf", "w64": "w64", "amr": "amr-nb", "opus": "opus", "pcm": "raw",
    "wv": "wv", "spx": "spx",
}


def _sox_formats() -> tuple[set[str], set[str]]:
    exe = SOX.path()
    if not exe:
        return set(), set()
    text = tool_output(exe, "--help")
    supported: set[str] = set()
    grab = False
    for line in text.splitlines():
        if line.startswith("AUDIO FILE FORMATS:"):
            grab = True
            supported.update(line.split(":", 1)[1].split())
            continue
        if grab:
            if line.startswith("PLAYLIST") or line.startswith("AUDIO DEVICE"):
                break
            supported.update(line.split())
    readable = {fmt for fmt, sox in _SOX_MAP.items() if sox in supported}
    writable = set(readable) - {"opus", "amr"}
    return readable, writable


@converter(
    "sox",
    lambda: _sox_formats()[0],
    lambda: _sox_formats()[1],
    requires=(SOX,),
    cost=25,
    options=("sample_rate", "channels", "volume", "start", "duration", "normalize"),
    description="Audio conversion with SoX",
)
def sox_convert(job: Job) -> list[Path]:
    exe = SOX.path()
    assert exe
    cmd = [exe, "-V1"]
    if job.src_format.name == "pcm":
        cmd += ["-t", "raw", "-r", "44100", "-e", "signed", "-b", "16", "-c", "2"]
    cmd.append(str(job.source))
    if job.opt("volume"):
        cmd += ["-v", str(job.opt("volume"))]
    ar, ac = job.opt("sample_rate"), job.opt("channels")
    if job.tgt_format.name == "pcm":
        cmd += ["-t", "raw", "-e", "signed", "-b", "16"]
    cmd.append(str(job.target))
    if ar:
        cmd += ["rate", str(int(ar))]
    if ac:
        cmd += ["channels", str(int(ac))]
    if job.opt("start") or job.opt("duration"):
        cmd += ["trim", str(job.opt("start") or 0)]
        if job.opt("duration"):
            cmd.append(str(job.opt("duration")))
    if job.opt("normalize"):
        cmd += ["gain", "-n"]
    run(cmd)
    return [job.target]


@converter("lame", ("wav", "mp3"), ("mp3", "wav"), requires=(Tool("lame", package="lame"),), cost=30, options=("bitrate", "sample_rate"), same_format=False, description="MP3 encoding/decoding with LAME")
def lame_convert(job: Job) -> list[Path]:
    exe = Tool("lame").path()
    assert exe
    if job.tgt_format.name == "mp3":
        cmd = [exe, "--silent"]
        if job.opt("bitrate"):
            cmd += ["-b", str(job.opt("bitrate")).lower().rstrip("k")]
        else:
            cmd += ["-V", "2"]
        if job.opt("sample_rate"):
            cmd += ["--resample", str(int(job.opt("sample_rate")) / 1000)]
        cmd += [str(job.source), str(job.target)]
    else:
        cmd = [exe, "--silent", "--decode", str(job.source), str(job.target)]
    run(cmd)
    return [job.target]


@converter("flac-cli", ("wav", "aiff", "flac"), ("flac", "wav", "aiff"), requires=(Tool("flac", package="flac"),), cost=30, options=("compress",), description="FLAC encoding/decoding with the reference encoder", predicate=lambda s, t: (s == "flac") != (t == "flac"))
def flac_convert(job: Job) -> list[Path]:
    exe = Tool("flac").path()
    assert exe
    if job.tgt_format.name == "flac":
        level = job.opt("compress")
        cmd = [exe, "-s", "-f", f"-{int(level)}" if level is not None else "-5", "-o", str(job.target), str(job.source)]
    else:
        cmd = [exe, "-s", "-f", "-d", "-o", str(job.target), str(job.source)]
        if job.tgt_format.name == "aiff":
            cmd.insert(3, "--force-aiff-format")
    run(cmd)
    return [job.target]


@converter("oggenc", ("wav", "aiff", "flac"), ("ogg",), requires=(Tool("oggenc", package="vorbis-tools"),), cost=30, options=("bitrate", "quality", "sample_rate", "channels", "title", "author"), description="Ogg Vorbis encoding with oggenc")
def oggenc_convert(job: Job) -> list[Path]:
    exe = Tool("oggenc").path()
    assert exe
    cmd = [exe, "-Q", "-o", str(job.target)]
    if job.opt("bitrate"):
        cmd += ["-b", str(job.opt("bitrate")).lower().rstrip("k")]
    elif job.opt("quality"):
        cmd += ["-q", str(round(int(job.opt("quality")) / 10))]
    if job.opt("sample_rate"):
        cmd += ["--resample", str(int(job.opt("sample_rate")))]
    if job.opt("channels") == 1:
        cmd += ["--downmix"]
    if job.opt("title"):
        cmd += ["-t", str(job.opt("title"))]
    if job.opt("author"):
        cmd += ["-a", str(job.opt("author"))]
    cmd.append(str(job.source))
    run(cmd)
    return [job.target]


@converter("oggdec", ("ogg",), ("wav",), requires=(Tool("oggdec", package="vorbis-tools"),), cost=30, description="Ogg Vorbis decoding with oggdec")
def oggdec_convert(job: Job) -> list[Path]:
    exe = Tool("oggdec").path()
    assert exe
    run([exe, "-Q", "-o", str(job.target), str(job.source)])
    return [job.target]


@converter("opusenc", ("wav", "aiff", "flac"), ("opus",), requires=(Tool("opusenc", package="opus-tools"),), cost=30, options=("bitrate", "title", "author"), description="Opus encoding with opusenc")
def opusenc_convert(job: Job) -> list[Path]:
    exe = Tool("opusenc").path()
    assert exe
    cmd = [exe, "--quiet"]
    if job.opt("bitrate"):
        cmd += ["--bitrate", str(job.opt("bitrate")).lower().rstrip("k")]
    if job.opt("title"):
        cmd += ["--title", str(job.opt("title"))]
    if job.opt("author"):
        cmd += ["--artist", str(job.opt("author"))]
    cmd += [str(job.source), str(job.target)]
    run(cmd)
    return [job.target]


@converter("opusdec", ("opus",), ("wav",), requires=(Tool("opusdec", package="opus-tools"),), cost=30, description="Opus decoding with opusdec")
def opusdec_convert(job: Job) -> list[Path]:
    exe = Tool("opusdec").path()
    assert exe
    run([exe, "--quiet", str(job.source), str(job.target)])
    return [job.target]
