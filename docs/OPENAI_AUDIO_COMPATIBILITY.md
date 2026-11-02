# OpenAI audio compatibility carry

This fork changes only serialization at `POST /v1/audio/speech`:

- `response_format: "pcm"` returns headerless signed 16-bit little-endian PCM,
  mono at the existing 24 kHz model rate.
- `wav` and the omitted format return PCM16 WAV (format tag 1), with matching
  RIFF/data sizes, byte rate, block alignment and bit depth.
- The existing permissive fallback is retained: `mp3`, `opus`, `flac` and other
  unrecognized formats return WAV bytes with `Content-Type: audio/wav`. This is
  **not** compressed-format encoding; consumers must sniff or transcode it.

One conversion implementation serves PCM and WAV. It silences NaN/infinity,
clamps finite input to [-1, 1], scales by 32768, rounds ties away from zero and
saturates to [-32768, 32767]. Sample bytes and WAV integer fields are explicitly
little-endian. Each response allocates its final byte buffer once and writes
samples directly into it; no intermediate PCM buffer is copied into WAV.

Inference, internal floats, models, voice conditioning and caches are unchanged.
`/tts` remains chunked float32 PCM; CLI WAV/stdout and FFI buffers remain float.
The tradeoff is PCM16 wire quantization, not lower inference precision. This
boundary-only carry adds no dependencies or settings.

## Focused checks

With existing Linux CMake dependencies already prepared under `.build`, compile
the native test directly into a disposable directory (set `out` first):

```sh
mkdir -p "$out"
deps="$PWD/.build/_deps"
c++ -O2 -std=c++17 -fsanitize=undefined,float-cast-overflow \
  -fno-sanitize-recover=all \
  -I"$deps/onnxruntime-src/include" -I"$deps/sentencepiece-src/src" \
  -I"$deps/dr_libs-src" tests/test_pcm16.cpp -o "$out/test-pcm16" \
  -Wl,-rpath,"$deps/onnxruntime-src/lib" \
  "$deps/onnxruntime-src/lib/libonnxruntime.so" \
  "$deps/sentencepiece-build/src/libsentencepiece.a" -lpthread -ldl
"$out/test-pcm16" "$out/cli-float.wav"
```

The native test includes the actual runtime using its existing FFI build guard;
it tests exact conversion edge bytes and the separate float CLI WAV writer,
without source-text extraction or model loading.

Against a **disposable candidate server**, using copied voice inputs and
`--no-cache` (replace the URL and voice filename):

```sh
python3 tests/test_openai_audio.py --base-url http://127.0.0.1:PORT \
  --voice example.wav --output-dir "$out/http" --check-float-stream
```

This synthesizes real audio and checks WAV headers/decoding, raw PCM framing,
default and compressed/unknown-format fallbacks, MIME/lengths, and `/tts` float
streaming. The native test supplies deterministic PCM byte assertions. These
checks do not establish audible quality, phone playback or in-game acceptance.
The stock CMake build writes `pocket-tts` into the source root; do not use it to
build a candidate over an active executable. Direct compilation can use the same
includes/libraries above with `pocket_tts.cpp` and `-o "$out/pocket-tts"`.

## Reapply and retirement

The output mismatch exists in upstream
`VolgaGerm/PocketTTS.cpp@e801e7d6c2692121a39e80ae525cb5265174a495`.
When rebasing, carry the serializer and its two OpenAI output call sites, plus
the existing permissive-format fallback; rerun the focused checks and consumer
decoding/transcoding smoke. Retire each carry only when a pinned upstream
implementation passes the corresponding contracts. An update alone is not a
retirement signal.
