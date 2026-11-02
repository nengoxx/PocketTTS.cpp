#!/usr/bin/env python3
"""Exercise a running, disposable server with real synthesis (stdlib only)."""
import argparse
import io
import json
from pathlib import Path
import struct
import urllib.request
import wave


def request(base_url, endpoint, payload):
    req = urllib.request.Request(base_url.rstrip("/") + endpoint,
                                 data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=180) as response:
        body = response.read()
        headers = dict(response.headers)
        assert response.status == 200
        if response.headers.get("Content-Length") is not None:
            assert int(response.headers["Content-Length"]) == len(body)
        return body, headers


def check_wav(body):
    assert body[:4] == b"RIFF" and body[8:12] == b"WAVE"
    assert struct.unpack_from("<I", body, 4)[0] == len(body) - 8
    assert body[12:16] == b"fmt " and body[36:40] == b"data"
    fields = struct.unpack_from("<IHHIIHH", body, 16)
    assert fields == (16, 1, 1, 24000, 48000, 2, 16), fields
    assert struct.unpack_from("<I", body, 40)[0] == len(body) - 44
    with wave.open(io.BytesIO(body), "rb") as audio:
        assert (audio.getnchannels(), audio.getsampwidth(), audio.getframerate()) == (1, 2, 24000)
        assert audio.getnframes() > 0
        frames = audio.readframes(audio.getnframes())
    assert any(struct.unpack("<" + "h" * (len(frames) // 2), frames))
    return len(frames) // 2


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--voice", required=True)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--check-float-stream", action="store_true")
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    receipts = []
    for fmt in ("wav", "pcm", None, "mp3", "opus", "flac", "unknown-format"):
        payload = {"input": "The voice connection is working.", "voice": args.voice}
        if fmt is not None:
            payload["response_format"] = fmt
        body, headers = request(args.base_url, "/v1/audio/speech", payload)
        name = fmt or "default"
        (args.output_dir / (name + ".bin")).write_bytes(body)
        (args.output_dir / (name + ".headers.json")).write_text(json.dumps(headers, indent=2) + "\n")
        if fmt == "pcm":
            assert headers["Content-Type"] == "audio/pcm"
            assert len(body) > 0 and len(body) % 2 == 0
            assert not body.startswith(b"RIFF")
            assert any(struct.unpack("<" + "h" * (len(body) // 2), body))
            samples = len(body) // 2
        else:
            assert headers["Content-Type"] == "audio/wav"
            samples = check_wav(body)
        receipts.append({"format": name, "bytes": len(body), "samples": samples,
                         "seconds": samples / 24000, "content_type": headers["Content-Type"]})
    if args.check_float_stream:
        import math
        body, headers = request(args.base_url, "/tts", {
            "text": "The float stream is unchanged.", "voice": args.voice})
        assert headers["Content-Type"] == "audio/pcm;rate=24000;encoding=float;bits=32"
        assert headers["Transfer-Encoding"] == "chunked"
        assert len(body) > 0 and len(body) % 4 == 0
        samples = struct.unpack("<" + "f" * (len(body) // 4), body)
        assert all(math.isfinite(s) for s in samples) and any(samples)
        (args.output_dir / "float-stream.f32le").write_bytes(body)
        receipts.append({"path": "/tts", "bytes": len(body), "samples": len(samples),
                         "content_type": headers["Content-Type"]})
    (args.output_dir / "receipt.json").write_text(json.dumps(receipts, indent=2) + "\n")
    print(json.dumps(receipts, indent=2))


if __name__ == "__main__":
    main()
