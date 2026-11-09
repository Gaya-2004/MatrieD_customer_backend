"""
speech_service.py

Universal Speech-to-Text for MaitreD Voice Agent.
Transcribes audio data (WAV, PCM, WebM) in English, Tamil, and Tanglish.
Uses Google Public Speech Recognition via SpeechRecognition library with zero billing/key requirements.
"""

import base64
import io
import logging
import wave
from typing import Optional

logger = logging.getLogger(__name__)


def transcribe_audio_base64(audio_b64: str, lang_hint: str = "en-IN") -> str:
    """
    Transcribes base64-encoded audio to text.
    Handles WAV PCM audio directly.
    Checks for silence before making network calls.
    """
    if not audio_b64:
        return ""

    try:
        raw_bytes = base64.b64decode(audio_b64)
    except Exception as e:
        logger.warning(f"[SpeechService] Base64 decode failed: {e}")
        return ""

    try:
        import speech_recognition as sr
        r = sr.Recognizer()
        r.energy_threshold = 300
        r.dynamic_energy_threshold = True

        audio_file = io.BytesIO(raw_bytes)

        # Check if valid WAV
        try:
            with sr.AudioFile(audio_file) as source:
                audio_data = r.record(source)
        except Exception as wav_err:
            try:
                audio_data = sr.AudioData(raw_bytes, 16000, 2)
            except Exception as pcm_err:
                logger.error(f"[SpeechService] Failed to parse audio data: {pcm_err}")
                return ""

        # Check for silence using RMS volume
        pcm_bytes = audio_data.get_raw_data()
        if len(pcm_bytes) < 3200:  # < 0.1s
            return ""

        try:
            import audioop
            rms = audioop.rms(pcm_bytes, 2)
            if rms < 200:
                logger.info(f"[SpeechService] Audio is silent (RMS={rms}), skipping network STT.")
                return ""
        except Exception:
            pass

        # Try recognition with primary language
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

        # Fallback to alternate language if not English
        alt_lang = "en-IN" if primary_lang != "en-IN" else "ta-IN"
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
