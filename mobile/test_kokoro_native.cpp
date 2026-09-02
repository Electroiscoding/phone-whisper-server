#include <iostream>
#include <vector>
#include <string>
#include <fstream>
#include <chrono>
#include "onnxruntime_cxx_api.h"

int main() {
    std::cout << "Initializing 32-bit Optimized ONNX Session..." << std::endl;
    Ort::Env env(ORT_LOGGING_LEVEL_WARNING, "KokoroTTS");
    Ort::SessionOptions session_options;
    session_options.SetIntraOpNumThreads(4);
    session_options.SetInterOpNumThreads(1);
    session_options.SetGraphOptimizationLevel(GraphOptimizationLevel::ORT_ENABLE_BASIC);

    const char* model_path = "/data/data/com.termux/files/home/kokoro_native/kokoro-en-v0_19/model_int8.onnx";
    std::cout << "Loading real Kokoro 82M INT8 neural model: " << model_path << std::endl;

    auto t0 = std::chrono::high_resolution_clock::now();
    try {
        Ort::Session session(env, model_path, session_options);
        auto t1 = std::chrono::high_resolution_clock::now();
        double load_ms = std::chrono::duration<double, std::milli>(t1 - t0).count();
        std::cout << "🎉 SUCCESS: Real Kokoro 82M INT8 Neural Model Loaded into Phone RAM in " << load_ms << " ms!" << std::endl;
        std::cout << "Inputs: " << session.GetInputCount() << ", Outputs: " << session.GetOutputCount() << std::endl;
        
        Ort::AllocatorWithDefaultOptions allocator;
        for (size_t i = 0; i < session.GetInputCount(); i++) {
            auto input_name = session.GetInputNameAllocated(i, allocator);
            std::cout << "  Input " << i << ": " << input_name.get() << std::endl;
        }
        for (size_t i = 0; i < session.GetOutputCount(); i++) {
            auto output_name = session.GetOutputNameAllocated(i, allocator);
            std::cout << "  Output " << i << ": " << output_name.get() << std::endl;
        }
    } catch (const Ort::Exception& ex) {
        std::cerr << "Ort::Exception: " << ex.what() << std::endl;
        return 1;
    } catch (const std::exception& e) {
        std::cerr << "std::exception: " << e.what() << std::endl;
        return 1;
    }

    return 0;
}
