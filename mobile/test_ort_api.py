import ctypes
import os
import struct
import numpy as np
import time

LIB_PATH = "/data/data/com.termux/files/home/kokoro_native/jni/armeabi-v7a/libonnxruntime.so"
MODEL_PATH = "/data/data/com.termux/files/home/kokoro_native/kokoro-en-v0_19/model.onnx"
VOICES_PATH = "/data/data/com.termux/files/home/kokoro_native/kokoro-en-v0_19/voices.bin"
TOKENS_PATH = "/data/data/com.termux/files/home/kokoro_native/kokoro-en-v0_19/tokens.txt"

class OrtApi(ctypes.Structure):
    pass

class OrtApiBase(ctypes.Structure):
    _fields_ = [
        ("GetApi", ctypes.CFUNCTYPE(ctypes.POINTER(OrtApi), ctypes.c_uint32)),
        ("GetVersionString", ctypes.CFUNCTYPE(ctypes.c_char_p)),
    ]

# Load library
ort_lib = ctypes.CDLL(LIB_PATH)
ort_lib.OrtGetApiBase.restype = ctypes.POINTER(OrtApiBase)
api_base = ort_lib.OrtGetApiBase().contents
api_ptr = api_base.GetApi(18) # ONNX Runtime version 1.18/1.19
print("OrtApi pointer obtained successfully:", api_ptr)
