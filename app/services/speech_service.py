"""
speech_service.py

Universal Speech-to-Text for MaitreD Voice Agent.
Transcribes audio data (WAV, PCM, OGG, FLAC) in English, Tamil, and Tanglish.
Uses Google Public Speech Recognition via SpeechRecognition library with zero billing/key requirements.
Supports multi-format decoding via soundfile + scipy.
"""

import base64
import io
import logging
from typing import Optional

logger = logging.getLogger(__name__)


def transcribe_audio_base64(audio_b64: str, lang_hint: str = "en-IN") -> str:
    """
    Transcribes base64-encoded audio to text.
    Handles WAV, PCM, OGG, FLAC.
    Supports English (en-IN) and Tamil (ta-IN).
    """
    if not audio_b64:
        return ""

    try:
        raw_bytes = base64.b64decode(audio_b64)
    except Exception as e:
        logger.warning(f"[SpeechService] Base64 decode failed: {e}")
        return ""

    if len(raw_bytes) < 1000:
        logger.info(f"[SpeechService] Audio data too small ({len(raw_bytes)} bytes), skipping.")
        return ""

    try:
        import speech_recognition as sr
        r = sr.Recognizer()
        r.energy_threshold = 150
        r.dynamic_energy_threshold = True

        audio_data: Optional[sr.AudioData] = None

        # 1. Try reading directly as WAV/AIFF/FLAC
        try:
            with sr.AudioFile(io.BytesIO(raw_bytes)) as source:
                audio_data = r.record(source)
        except Exception as wav_err:
            logger.info(f"[SpeechService] Direct WAV read failed ({wav_err}), trying soundfile decoder...")

        # 2. Try soundfile decoding (supports OGG, FLAC, RAW, etc.)
        if audio_data is None:
            try:
                import soundfile as sf
                import numpy as np
                import scipy.signal

                data_arr, sr_in = sf.read(io.BytesIO(raw_bytes))
                if len(data_arr.shape) > 1:
                    # Convert stereo to mono
                    data_arr = data_arr.mean(axis=1)

                # Resample to 16kHz
                if sr_in != 16000:
                    target_len = int(len(data_arr) * 16000 / sr_in)
                    data_arr = scipy.signal.resample(data_arr, target_len)

                # Convert float to int16
                if data_arr.dtype != np.int16:
                    data_arr = (np.clip(data_arr, -1.0, 1.0) * 32767).astype(np.int16)

                buf = io.BytesIO()
                sf.write(buf, data_arr, 16000, format='WAV', subtype='PCM_16')
                buf.seek(0)

                with sr.AudioFile(buf) as source:
                    audio_data = r.record(source)
                logger.info(f"[SpeechService] Successfully decoded audio with soundfile (sr={sr_in} -> 16000)")
            except Exception as sf_err:
                logger.warning(f"[SpeechService] soundfile decode failed: {sf_err}")

        # 3. Fallback: treat as raw 16kHz 16-bit mono PCM
        if audio_data is None:
            try:
                audio_data = sr.AudioData(raw_bytes, 16000, 2)
            except Exception as pcm_err:
                logger.error(f"[SpeechService] Raw PCM fallback failed: {pcm_err}")
                return ""

        # Check RMS volume
        pcm_bytes = audio_data.get_raw_data()
        if len(pcm_bytes) < 3200:  # < 0.1s
            return ""

        try:
            import audioop
            rms = audioop.rms(pcm_bytes, 2)
            if rms < 40:
                logger.info(f"[SpeechService] Audio is essentially silent (RMS={rms} < 40), skipping.")
                return ""
            logger.info(f"[SpeechService] Processing audio (len={len(pcm_bytes)} bytes, RMS={rms})")
        except Exception:
            pass

        # Primary language recognition
        primary_lang = lang_hint or "en-IN"
        try:
            text = r.recognize_google(audio_data, language=primary_lang)
            if text and text.strip():
                logger.info(f"[SpeechService] Recognized text ({primary_lang}): '{text}'")
                return text.strip()
        except sr.UnknownValueError:
            pass
        except sr.RequestError as req_err:
            logger.warning(f"[SpeechService] Google Speech API request error for {primary_lang}: {req_err}")
            return ""

        # Alternate language fallback (ta-IN or en-IN)
        alt_lang = "ta-IN" if primary_lang == "en-IN" else "en-IN"
        try:
            text = r.recognize_google(audio_data, language=alt_lang)
            if text and text.strip():
                logger.info(f"[SpeechService] Recognized text ({alt_lang}): '{text}'")
                return text.strip()
        except Exception:
            pass

    except Exception as e:
        logger.error(f"[SpeechService] Unexpected transcription error: {e}")

    return ""
