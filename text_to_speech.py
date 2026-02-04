import pyttsx3
import platform
import re
import tempfile
import os
from gtts import gTTS
from playsound import playsound

# Initialize pyttsx3 engine
engine = pyttsx3.init()

# Set female voice if available
voices = engine.getProperty('voices')
for voice in voices:
    if "female" in voice.name.lower() or "zira" in voice.name.lower():
        engine.setProperty('voice', voice.id)
        break

engine.setProperty('rate', 175)  # Speech rate

def speak(text):
    """
    Primary text-to-speech function using pyttsx3.
    """
    try:
        print(f"[TTS] Speaking: {text}")
        cleaned_text = re.sub(r'[^\x00-\x7F]+', '', text)
        cleaned_text = re.sub(r'[^\w\s.,?!\'"-]', '', cleaned_text)
        engine.say(cleaned_text)
        engine.runAndWait()
    except Exception as e:
        print(f"[TTS Error] pyttsx3 failed: {e}")
        fallback_tts(text)

def fallback_tts(text):
    """
    Fallback TTS using gTTS + playsound.
    """
    try:
        print("[Fallback TTS] Using gTTS as backup...")
        cleaned_text = re.sub(r'[^\x00-\x7F]+', '', text)
        cleaned_text = re.sub(r'[^\w\s.,?!\'"-]', '', cleaned_text)
        tts = gTTS(cleaned_text, lang='en')
        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as fp:
            temp_path = fp.name
        tts.save(temp_path)
        playsound(temp_path)
        os.remove(temp_path)
    except Exception as e:
        print(f"[Fallback TTS Error] {e}")
