"""
Generates clean, realistic cabin chimes for the DEFAULT sound pack.
Uses pure Python standard library (wave, math, struct) - no external tools needed.
"""
import wave
import struct
import math
import os

def create_tone(freqs, duration_s, sample_rate=44100, decay_rate=3.0, volume=0.5):
    """Generates audio samples for one or more mixed frequencies with natural decay."""
    samples = []
    num_samples = int(duration_s * sample_rate)
    for i in range(num_samples):
        t = i / sample_rate
        # Exponential decay envelope
        envelope = math.exp(-decay_rate * t)
        val = 0.0
        for f in freqs:
            val += math.sin(2.0 * math.pi * f * t)
        val = (val / len(freqs)) * envelope * volume
        # Clamp to 16-bit PCM range
        val = max(-1.0, min(1.0, val))
        samples.append(int(val * 32767))
    return samples

def write_wav(file_path, samples, sample_rate=44100):
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    with wave.open(file_path, "w") as wf:
        wf.setnchannels(1)  # Mono
        wf.setsampwidth(2)  # 16-bit
        wf.setframerate(sample_rate)
        raw_bytes = struct.pack(f"<{len(samples)}h", *samples)
        wf.writeframes(raw_bytes)

def generate_default_pack(target_dir):
    sample_rate = 44100
    
    # 1. High Chime (880 Hz) - Arm Doors / Disarm Doors / Fasten Seatbelt
    chime_high = create_tone([880.0], duration_s=1.2, sample_rate=sample_rate, decay_rate=2.8, volume=0.6)
    
    # 2. Ding-Dong Two-Tone Chime (F5: 698.46 Hz -> C#5 / A4: 587.33 Hz) - Airbus/Boeing PA chime
    ding = create_tone([698.46, 1396.9], duration_s=0.7, sample_rate=sample_rate, decay_rate=2.5, volume=0.55)
    pause = [0] * int(sample_rate * 0.05)
    dong = create_tone([587.33, 1174.6], duration_s=1.8, sample_rate=sample_rate, decay_rate=2.0, volume=0.55)
    ding_dong = ding + pause + dong
    
    # 3. Triple Chime (High - Mid - Low) - Cabin emergency or prepare for takeoff
    c1 = create_tone([784.0], duration_s=0.4, sample_rate=sample_rate, decay_rate=3.0, volume=0.5)
    c2 = create_tone([659.25], duration_s=0.4, sample_rate=sample_rate, decay_rate=3.0, volume=0.5)
    c3 = create_tone([523.25], duration_s=1.5, sample_rate=sample_rate, decay_rate=2.0, volume=0.5)
    triple_chime = c1 + pause + c2 + pause + c3
    
    # 4. Low-High Seatbelt Chime
    sb1 = create_tone([523.25], duration_s=0.35, sample_rate=sample_rate, decay_rate=3.5, volume=0.5)
    sb2 = create_tone([784.0], duration_s=1.2, sample_rate=sample_rate, decay_rate=2.5, volume=0.55)
    seatbelt_chime = sb1 + pause + sb2

    # Map Fenix sound names to generated chimes
    sounds = {
        "BoardingWelcome.wav": ding_dong,
        "ArmDoors.wav": chime_high,
        "SafetyBriefing.wav": ding_dong,
        "CrewSeatsTakeoff.wav": triple_chime,
        "CabinDimTakeoff.wav": chime_high,
        "CallCabinSecureTakeoff.wav": chime_high,
        "AfterTakeoff.wav": ding_dong,
        "FastenSeatbelt.wav": seatbelt_chime,
        "TopOfClimbPilot.wav": ding_dong,
        "CruiseElapsed.wav": ding_dong,
        "TopOfDescentPilot.wav": ding_dong,
        "Descent.wav": ding_dong,
        "AfterLanding.wav": ding_dong,
        "DisarmDoors.wav": chime_high,
        "Deboarding.wav": ding_dong
    }

    for filename, audio in sounds.items():
        out_path = os.path.join(target_dir, filename)
        write_wav(out_path, audio, sample_rate)
        print(f"Generated default audio: {out_path}")

if __name__ == "__main__":
    import sys
    out = sys.argv[1] if len(sys.argv) > 1 else "airlines/DEFAULT"
    generate_default_pack(out)
