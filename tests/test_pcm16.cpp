// Include the real single-file runtime; the existing FFI build guard omits main.
#define PTT_SHARED_LIB
#include "../pocket_tts.cpp"

static void require(bool condition, const char* message) {
    if (!condition) throw std::runtime_error(message);
}

int main(int argc, char** argv) {
    try {
        require(argc == 2, "Pass a disposable output WAV path");
        const float half_lsb = 1.0f / 65536.0f;
        const float samples[] = {
            -std::numeric_limits<float>::max(), -2, -1, -0.5f,
            -half_lsb, -0.0f, 0, half_lsb, 0.5f,
            std::nextafter(1.0f, 0.0f), 1, 2, std::numeric_limits<float>::max(),
            std::numeric_limits<float>::quiet_NaN(),
            std::numeric_limits<float>::infinity(),
            -std::numeric_limits<float>::infinity(),
            std::numeric_limits<float>::denorm_min()
        };
        const std::vector<uint8_t> expected = {
            0x00,0x80, 0x00,0x80, 0x00,0x80, 0x00,0xc0,
            0xff,0xff, 0x00,0x00, 0x00,0x00, 0x01,0x00, 0x00,0x40,
            0xff,0x7f, 0xff,0x7f, 0xff,0x7f, 0xff,0x7f,
            0x00,0x00, 0x00,0x00, 0x00,0x00, 0x00,0x00
        };
        std::vector<uint8_t> bytes(expected.size() + 2, 0xa5);
        pocket_tts::encode_pcm16_le(samples, sizeof(samples) / sizeof(samples[0]), bytes.data() + 1);
        require(bytes.front() == 0xa5 && bytes.back() == 0xa5, "Serializer overrun");
        require(std::equal(expected.begin(), expected.end(), bytes.begin() + 1),
                "PCM16 saturation/rounding/nonfinite/little-endian bytes differ");
        pocket_tts::encode_pcm16_le(nullptr, 0, nullptr);

        // The CLI's separate WAV writer must still preserve float32 samples.
        pocket_tts::AudioData audio{{-0.5f, 0, 0.25f}, pocket_tts::PocketTTS::SR};
        pocket_tts::PocketTTS::save_audio(audio, argv[1]);
        drwav wav;
        require(drwav_init_file(&wav, argv[1], nullptr), "Read CLI WAV");
        require(wav.translatedFormatTag == DR_WAVE_FORMAT_IEEE_FLOAT && wav.bitsPerSample == 32 &&
                wav.channels == 1 && wav.sampleRate == 24000, "CLI WAV lost float32 format");
        float decoded[3] = {};
        require(drwav_read_pcm_frames_f32(&wav, 3, decoded) == 3, "CLI WAV sample count");
        drwav_uninit(&wav);
        require(std::equal(audio.samples.begin(), audio.samples.end(), decoded), "CLI float samples changed");
        std::cout << "PASS: PCM16 edge bytes and unchanged CLI float32 WAV writer\n";
    } catch (const std::exception& error) {
        std::cerr << "FAIL: " << error.what() << '\n';
        return 1;
    }
}
