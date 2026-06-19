# ai_handlers/voice_simple.py
import speech_recognition as sr

def transcribe_voice(audio_path: str) -> str:
    recognizer = sr.Recognizer()
    
    with sr.AudioFile(audio_path) as source:
        audio = recognizer.record(source)
    
    try:
        text = recognizer.recognize_google(audio, language="fa-IR")
        return text
    except Exception as e:
        return f"خطا: {e}"

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        text = transcribe_voice(sys.argv[1])
        print(f"متن: {text}")