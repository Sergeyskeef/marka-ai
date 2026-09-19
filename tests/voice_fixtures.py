"""Tiny structural Opus fixtures; deliberately not a speech/codec quality test."""
import hashlib
import struct


def page(packet, sequence, flags, serial=1, granule=0):
    sizes = [255] * (len(packet) // 255) + [len(packet) % 255]
    data = bytearray(b"OggS\0" + bytes([flags]) + struct.pack("<QII", granule, serial, sequence) + b"\0" * 4 + bytes([len(sizes)]) + bytes(sizes) + packet)
    crc = 0
    for value in data:
        crc ^= value << 24
        for _ in range(8):
            crc = ((crc << 1) ^ (0x04C11DB7 if crc & 0x80000000 else 0)) & 0xFFFFFFFF
    struct.pack_into("<I", data, 22, crc)
    return bytes(data)


OGG = (page(b"OpusHead" + bytes([1, 1]) + struct.pack("<HIhB", 0, 48000, 0, 0), 0, 2)
       + page(b"OpusTags" + struct.pack("<II", 0, 0), 1, 0)
       + page(bytes.fromhex("f8fffe"), 2, 4, granule=960))


def transcript(data=OGG, text="Создай заметку про число сорок два"):
    return {"text": text, "sha256": hashlib.sha256(data).hexdigest(), "duration_seconds": 1.0,
            "engine": "openai", "model": "gpt-4o-transcribe", "language": "ru"}


def voice_update(number=1, *, user=17, duration=1, caption="", data=OGG):
    return {"update_id": number, "message": {"message_id": number, "from": {"id": user, "is_bot": False},
            "chat": {"id": user, "type": "private"}, "caption": caption,
            "voice": {"file_id": "voice-id", "file_unique_id": "unique-id", "mime_type": "audio/ogg",
                      "file_size": len(data), "duration": duration}}}
