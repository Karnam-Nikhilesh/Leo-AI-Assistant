import os
import cv2
import pickle
import face_recognition
import asyncio
import speech_recognition as sr
import requests
import sys
import time
import win32com.client
from googletrans import Translator
from config import huggingface_api_key, wolfram_app_id
from sumy.parsers.plaintext import PlaintextParser
from sumy.nlp.tokenizers import Tokenizer
from sumy.summarizers.lsa import LsaSummarizer
import nltk
import wolframalpha
import webbrowser
import wikipedia
import json
import datetime
import pygame
import random
import aiohttp

try:
    from config import huggingface_api_key, wolfram_app_id
except ImportError:
    print("❌ Missing config.py file for Leo.")
    sys.exit(1)





# HUGGINGFACE_MODEL = "tiiuae/falcon-7b-instruct"  # or another from above
HUGGINGFACE_MODEL = "google/flan-t5-base" 


ASSISTANT_NAME_FILE = "assistant_name.json"
ASSISTANT_NAME = "Leo"

nltk.download('punkt')

# Initialize
speak = win32com.client.Dispatch("SAPI.SpVoice")
translator = Translator()
wikipedia.set_lang("en")

# Language Config
LANGUAGES = {"en": "English", "hi": "Hindi", "te": "Telugu"}
TARGET_LANGUAGE = "en"

# Voice language mapping
def set_voice_by_language(lang_code):
    voice_map = {
        "en": "zira",
        "hi": "heera",
        "te": "telugu"
    }
    target = voice_map.get(lang_code, "zira")
    found = False
    for voice in speak.GetVoices():
        if target.lower() in voice.GetDescription().lower():
            speak.Voice = voice
            print(f"Voice set to: {voice.GetDescription()}")
            found = True
            break
    if not found:
        print("Voice not found. Using default.")


# Set language and voice
def set_language(lang):
    global TARGET_LANGUAGE
    if lang in LANGUAGES:
        TARGET_LANGUAGE = lang
        set_voice_by_language(lang)
        print(f"Language set to {LANGUAGES[lang]}")
    else:
        TARGET_LANGUAGE = "en"
        set_voice_by_language("en")
        print("Invalid language. Defaulted to English.")

# Ask language at start
def prompt_language():
    print("Welcome to Leo AI Assistant!")
    print("Choose your preferred language: en (English), hi (Hindi), te (Telugu)")
    lang = input("Enter language code: ").strip().lower()
    set_language(lang)

# Voice output
async def say(text):
    try:
        translated = translator.translate(text, dest=TARGET_LANGUAGE)
        translated_text = translated.text
    except:
        translated_text = text
    print(f"Leo ({LANGUAGES[TARGET_LANGUAGE]}): {translated_text}")
    speak.Speak(translated_text)
    return translated_text

# Constants and setup
HUGGINGFACE_MODEL = "google/flan-t5-base"
HUGGINGFACE_API_KEY = huggingface_api_key
wolfram_client = wolframalpha.Client(wolfram_app_id)
FACE_DATA = "face_data.pkl"

wolfram_keywords = [
    "calculate", "what is", "how many", "convert", "temperature", "weather", "forecast",
    "humidity", "solve", "integrate", "differentiate", "derivative", "gdp", "population",
    "area of", "volume of", "distance between", "speed of", "mass of", "value of",
    "velocity", "height of", "age of", "density", "length of", "time in", "when is", "define",
    "who discovered", "who invented"
]

# Load or initialize face data
if os.path.exists(FACE_DATA):
    with open(FACE_DATA, "rb") as f:
        known_face_encodings, known_face_names = pickle.load(f)
else:
    known_face_encodings = []
    known_face_names = []

def capture_face():
    cap = cv2.VideoCapture(0)
    print("Look at the camera...")
    ret, frame = cap.read()
    cap.release()
    if not ret:
        print("Failed to capture image!")
        return None
    rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    faces = face_recognition.face_locations(rgb_frame)
    if not faces:
        print("No face detected!")
        return None
    return face_recognition.face_encodings(rgb_frame, faces)[0]

def sign_up():
    name = input("Enter your name: ").strip()
    if name in known_face_names:
        print("User already exists!")
        return
    encoding = capture_face()
    if encoding is not None:
        known_face_encodings.append(encoding)
        known_face_names.append(name)
        with open(FACE_DATA, "wb") as f:
            pickle.dump((known_face_encodings, known_face_names), f)
        print(f"Sign-up successful, {name}!")

async def authenticate_face():
    global ASSISTANT_NAME  # ✅ Ensure access to global assistant name

    encoding = capture_face()
    if encoding is None:
        await say("Authentication failed.")
        return None

    if not known_face_encodings:
        await say("No registered users. Please sign up first.")
        return None

    matches = face_recognition.compare_faces(known_face_encodings, encoding, tolerance=0.5)
    if any(matches):
        name = known_face_names[matches.index(True)]

        # Time-based greeting
        current_hour = datetime.datetime.now().hour
        if 5 <= current_hour < 12:
            greeting = "Good morning"
        elif 12 <= current_hour < 18:
            greeting = "Good afternoon"
        else:
            greeting = "Good evening"

        await say(f"{greeting}, {name}! I am {ASSISTANT_NAME}. How can I help you?")
        return name

    await say("Face not recognized.")
    return None


def takeCommand():
    r = sr.Recognizer()
    with sr.Microphone() as source:
        print("Leo Listening...")
        audio = r.listen(source)
        try:
            query = r.recognize_google(audio, language=TARGET_LANGUAGE)
            print(f"User said: {query}")
            return query.lower()
        except:
            return ""

def summarize_text(text, num_sentences=3):
    if not text or len(text.split()) < 5:
        return "Text too short for summarization."
    try:
        parser = PlaintextParser.from_string(text, Tokenizer("english"))
        summarizer = LsaSummarizer()
        summary = summarizer(parser.document, num_sentences)
        return " ".join(str(s) for s in summary)
    except Exception as e:
        print("Summarization error:", e)
        return "Unable to summarize."

async def ask_wolfram(query):
    try:
        loop = asyncio.get_running_loop()
        res = await loop.run_in_executor(None, wolfram_client.query, query)
        results = await loop.run_in_executor(None, lambda: list(res.results))
        if results:
            result_text = results[0].text
            # print("Leo Answer:", result_text)
            # await say(result_text)
            return result_text
    except Exception as e:
        print("Leo error:", e)
    await say("I couldn't find an answer.")
    return "No result."

# Define global chat history

chat_history = ""

# Main Hugging Face interaction function
async def ask_huggingface(query):
    global chat_history
    try:
        API_URL = "https://api-inference.huggingface.co/models/microsoft/DialoGPT-medium"
        headers = {
            "Authorization": f"Bearer {HUGGINGFACE_API_KEY}",
            "Content-Type": "application/json"
        }

        # Add to chat history
        prompt = chat_history + f"\nUser: {query}\nAI:"
        payload = {"inputs": prompt}

        async with aiohttp.ClientSession() as session:
            async with session.post(API_URL, headers=headers, json=payload) as response:
                if response.status == 200:
                    result = await response.json()

                    # Handle list or dict format
                    if isinstance(result, list) and 'generated_text' in result[0]:
                        full_response = result[0]['generated_text']
                        answer = full_response.split("AI:")[-1].strip()
                    else:
                        answer = ""

                    # Fallback if empty or echo
                    if not answer or answer.lower() == query.lower() or len(answer.strip()) < 3:
                        answer = get_fallback_response(query)

                    chat_history += f"\nUser: {query}\nAI: {answer}"
                    await say(answer)
                    return answer
                else:
                    print("Leo error:", response.status)
                    answer = get_fallback_response(query)
                    await say(answer)
                    return answer

    except Exception as e:
        print("Leo Exception:", str(e))
        answer = get_fallback_response(query)
        await say(answer)
        return answer


# Fallback response generator
def get_fallback_response(prompt):
    prompt_lower = prompt.lower()

    if any(word in prompt_lower for word in ["joke", "laugh", "funny"]):
        jokes = [
            "Why don't scientists trust atoms? Because they make up everything!",
            "Why did the scarecrow win an award? Because he was outstanding in his field!",
            "Why did the computer get cold? It left its Windows open!",
            "Why was the math book sad? It had too many problems.",
            "What do you call fake spaghetti? An impasta!"
            "Why don't scientists trust atoms? Because they make up everything!",
            "Why did the scarecrow win an award? Because he was outstanding in his field!",
            "Why did the computer get cold? It left its Windows open!",
            "Why was the math book sad? It had too many problems.",
            "What do you call fake spaghetti? An impasta!",
            "Why can’t your nose be 12 inches long? Because then it would be a foot!",
            "How do you organize a space party? You planet!",
            "What did one wall say to the other? I'll meet you at the corner!",
            "What do you get when you cross a snowman and a dog? Frostbite!",
            "I'm reading a book on anti-gravity. It's impossible to put down!",
            "Why did the golfer bring two pairs of pants? In case he got a hole in one.",
            "Why don't eggs tell each other secrets? Because they might crack up!",
            "Why did the bicycle fall over? It was two-tired!",
            "What did the ocean say to the beach? Nothing, it just waved.",
            "Why do cows wear bells? Because their horns don’t work!"
        ]
        return random.choice(jokes)

    elif any(greet in prompt_lower for greet in ["hello", "hi", "hey", "how are you", "what's up"]):
        greetings = [
            "Hi there! How can I help you today?",
            "Hello! Great to see you 😊",
            "Hey! I'm here and ready to chat!",
            "I'm doing great, thanks for asking! How about you?"
        ]
        return random.choice(greetings)

    return "Sorry, Leo  isn't responding right now, but I'm still here to help!"

    
async def sing_song(query):
    song = """
    🎶 La la la, I'm your assistant, here to stay 🎶
    🎵 I help you out with every single thing, every day 🎵
    
    If you need some knowledge, just ask away,
    Whether it's sports or science, I'll brighten your day!

    🌟 I can summarize or search on Wikipedia 🌟
    Translate your text or get you info from the area 🌍
    
    Got a question about movies or the latest IPL game? 🎬
    Just let me know, I’ll answer all the same! ⚡️
    
    So let’s have fun, ask me what you please,
    Your assistant Leo's here to put your mind at ease! 🎤
    """
    
    await say(song)



######################
# Load assistant name from file
def load_assistant_name():
    global ASSISTANT_NAME
    if os.path.exists(ASSISTANT_NAME_FILE):
        try:
            with open(ASSISTANT_NAME_FILE, "r") as f:
                data = json.load(f)
                ASSISTANT_NAME = data.get("name", "Leo")
        except:
            ASSISTANT_NAME = "Leo"
    else:
        save_assistant_name(ASSISTANT_NAME)

# Save assistant name to file
def save_assistant_name(name):
    with open(ASSISTANT_NAME_FILE, "w") as f:
        json.dump({"name": name}, f)

# Load assistant name on startup
load_assistant_name()

#############
# Initialize pygame mixer
pygame.mixer.init()

# Music directory where you have your songs
MUSIC_DIR = 'Leo AI Assistant\music'  # Update this path

async def play_music():
    song_file = os.path.join(MUSIC_DIR, '1.mp3')  # Replace with your song file's name
    if os.path.exists(song_file):
        pygame.mixer.music.load(song_file)
        pygame.mixer.music.play(loops=0, start=0.0)  # Play once
        await say("Now playing your song!")
    else:
        await say("Sorry, I couldn't find the song. Please make sure the song file exists.")

async def stop_music():
    pygame.mixer.music.stop()
    await say("The music has been stopped.")


   


# Main command execution function
async def execute_command(query):
    global ASSISTANT_NAME
    
    query = query.lower().strip()

    if "what is your name" in query:
        await say(f"My name is {ASSISTANT_NAME}.")
        return

    # Name change
    if "change your name to" in query:
        new_name = query.split("change your name to")[-1].strip()
        if new_name:
            ASSISTANT_NAME = new_name
            save_assistant_name(ASSISTANT_NAME)
            await say(f"My name is now {ASSISTANT_NAME}.")
        else:
            await say("Please tell me the new name.")
        return

    # Reset name
    if "reset your name" in query:
        ASSISTANT_NAME = "Leo"
        save_assistant_name(ASSISTANT_NAME)
        await say("My name has been reset to Leo.")
        return
    
    # Play music command
    if "play music" in query or "play song" in query:
        await play_music()
        return

    # Stop music command
    if "stop music" in query:
        await stop_music()
        return

    # Assistant identity
    if "what is your name" in query.lower():
        await say(f"My name is {ASSISTANT_NAME}.")
        return

    # Name change
    if "change your name to" in query:
        new_name = query.split("change your name to")[-1].strip()
        if new_name:
            ASSISTANT_NAME = new_name
            save_assistant_name(ASSISTANT_NAME)
            await say(f"My name is now {ASSISTANT_NAME}.")
        else:
            await say("Please tell me the new name.")
        return

    # Other commands...
    
     # Summarization
    if "summarize text" in query:
        text = input("Enter text to summarize: ").strip()
        summary = summarize_text(text)
        print("Summary:", summary)
        await say(summary)

        
        # Inside execute_command function, add:
    if "sing a song" in query:
        await sing_song(query)
        return


    # Wolfram Alpha or fallback
    elif any(query.startswith(kw) or kw in query for kw in wolfram_keywords):
        result = await ask_wolfram(query)
        if result == "No result.":
            try:
                summary = wikipedia.summary(query, sentences=2)
                await say(summary)
            except:
                await ask_huggingface(query)
        else:
            await say(result)

    # YouTube search
    elif "youtube" in query:
        await say("What topic should I search?")
        topic = takeCommand()
        if topic:
            webbrowser.open(f"https://www.youtube.com/results?search_query={topic}")

    # Wikipedia search
    elif "wikipedia" in query:
        await say("What do you want to search?")
        topic = takeCommand()
        try:
            summary = wikipedia.summary(topic, sentences=2)
            print(summary)
            await say(summary)
        except:
            webbrowser.open("https://en.wikipedia.org/wiki/" + topic.replace(" ", "_"))

    # Google search
    elif "google" in query:
        await say("What should I search?")
        topic = takeCommand()
        webbrowser.open(f"https://www.google.com/search?q={topic}")


    # Default fallback to HuggingFace
    else:
        await ask_huggingface(query)

    # Friendly conversation handler
    greetings = {
        "hi": "Hello! Great to see you 😊",
        "hello": "Hi there! How can I help you today?",
        "hey": "Hey! What's up?",
        "how are you": "I'm doing great, thanks for asking! How about you?",
        "what's up": "All good here! Ready to assist you 😄",
        "who are you": f"I'm {ASSISTANT_NAME}, your personal AI assistant 😊",
        "good morning": "Good morning! Hope your day starts great ☀️",
        "good afternoon": "Good afternoon! How's it going?",
        "good evening": "Good evening! How can I make your night easier?",
        "good night": "Good night! Sleep well 🌙",
        "bye": "Bye! Take care 👋",
        "see you": "See you soon! ✨",
        "thank you": "You're very welcome! 😊",
        "thanks": "No problem! Happy to help 😄",
        "ok": "Alright! Let me know if you need anything else.",
        "okay": "Sure thing!",
        "fine": "Glad to hear that!",
        "i'm fine": "That's great! 😊",
        "i am fine": "Awesome! Happy to hear that!",
        "i'm good": "Nice! Let me know if you need anything.",
        "i am good": "Perfect! I'm here to help.",
        "what is your name": f"My name is {ASSISTANT_NAME} 😊",
        "who made you": "I was created by a very smart human 😎",
        "who created you": "Someone awesome built me to assist you!",
        "how old are you": "Age doesn't matter when you're this smart! 😉",
        "do you love me": "Of course! I care about you ❤️",
        "can you help me": "Yes, I'm always here for you!",
        "are you there": "Always! Just say the word.",
        "tell me a joke": "Why don't robots ever get tired? Because they recharge! 🤖⚡",
        "i am sad": "I'm here for you. Want to talk about it?",
        "i'm sad": "Sending virtual hugs 🤗 You're not alone.",
        "i'm happy": "Yay! That makes me happy too 😊",
        "i am happy": "That's awesome! Let's keep the good vibes going 🎉",
        "do you have feelings": "Not like humans do, but I care about helping you!",
        "sing a song": "🎵 La la la... I wish I could sing better, but I can tell you lyrics!",
        "dance for me": "I'd dance if I had legs! 💃 Just imagine me doing the robot 🤖",
        "you are nice": "Aww, you're sweet! Thanks 😊",
        "you are smart": "Thank you! You're pretty smart too 😄",
        "i missed you": "Aww, I missed you too! 😊",
        "miss you": "Same here! It's always good to chat with you.",
        "do you miss me": "Absolutely! It's quiet without you around.",
        "what are you doing": "Just waiting to help you 😄",
        "what's your job": "I'm here to assist you with anything you need!",
        "how do you feel": "I feel like helping you today!",
        "how's your day": "Even better now that you're here 😄",
        "what can you do": "I can chat, search, summarize, translate, and more!",
        "can you talk": "Yes! I love having conversations 😊",
        "talk to me": "Of course! Let's talk. What's on your mind?",
        "i'm bored": "Let’s do something fun! I can tell a joke or play a game.",
        "make me laugh": "Why did the computer take a nap? It had a hard drive! 😂",
        "i'm lonely": "I'm right here with you. You're not alone ❤️",
        "do you like me": "Of course I do! You're amazing 😄", 
        "prime minister of india": "The current Prime Minister of India is Narendra Modi.",
        "capital of india": "New Delhi is the capital of India.",
        "president of india": "The current President of India is Droupadi Murmu.",
        "taj mahal": "The Taj Mahal is a white marble mausoleum in Agra, India.",
        "longest river in india": "The Ganges (Ganga) is the longest river in India.",
        "largest state in india": "Rajasthan is the largest state in India by area.",
        "highest mountain": "Mount Everest is the highest mountain in the world.",
        "largest country": "Russia is the largest country in the world by area.",
        "smallest country": "Vatican City is the smallest country in the world.",
        "largest ocean": "The Pacific Ocean is the largest ocean on Earth.",
        "currency of india": "The currency of India is the Indian Rupee (INR).",
        "india's national flower": "The national flower of India is the Lotus.",
        "india's national animal": "The national animal of India is the Bengal Tiger.",
        "india's national bird": "The national bird of India is the Indian Peacock.",
        "india's national fruit": "The national fruit of India is the Mango.",
        "india's national tree": "The national tree of India is the Banyan Tree.",
        "who is the founder of india": "The founder of modern India is considered to be Mahatma Gandhi.",
        "who is known as the father of the nation in india": "Mahatma Gandhi is known as the Father of the Nation in India.",
        "largest desert in india": "The Thar Desert is the largest desert in India.",
        "first woman prime minister of india": "Indira Gandhi was the first woman Prime Minister of India.",
        "longest river in the world": "The Nile River is traditionally considered the longest river in the world.",
        "largest island in the world": "Greenland is the largest island in the world.",
        "fastest animal on land": "The cheetah is the fastest animal on land.",
        "longest wall in the world": "The Great Wall of China is the longest wall in the world.",
        "oldest civilization": "The Mesopotamian Civilization is one of the oldest known civilizations.",
        "first man on the moon": "Neil Armstrong was the first man to walk on the moon.",
        "who invented the telephone": "Alexander Graham Bell is credited with inventing the telephone.",
        "who discovered electricity": "Benjamin Franklin is often credited with discovering electricity through his experiments.",
        "tallest building in the world": "The Burj Khalifa in Dubai is currently the tallest building in the world.",
        "longest river in europe": "The Volga River is the longest river in Europe.",
        "highest waterfall in the world": "Angel Falls in Venezuela is the highest waterfall in the world.",
        "first woman to fly solo across the atlantic": "Amelia Earhart was the first woman to fly solo across the Atlantic Ocean.",
        "who invented the lightbulb": "Thomas Edison is often credited with inventing the lightbulb.",

    # Movies
        "highest grossing movie of all time": "The highest-grossing movie of all time is 'Avatar' (2009), directed by James Cameron.",
        "first animated feature film": "The first animated feature film was 'Snow White and the Seven Dwarfs', released in 1937 by Walt Disney.",
        "oscar for best picture 2023": "'Everything Everywhere All at Once' won the Academy Award for Best Picture in 2023.",
        "first film with sound": "'The Jazz Singer' (1927) is considered the first major film with synchronized sound.",
        "who directed titanic": "'Titanic' (1997) was directed by James Cameron.",
        "who won the most oscars": "Walt Disney holds the record for the most Academy Awards, winning 22 Oscars from 59 nominations.",
        "most expensive movie ever made": "'Pirates of the Caribbean: On Stranger Tides' (2011) is considered the most expensive movie ever made with a budget of around $379 million.",
      
      # Sports
        "who won the fifa world cup in 2022": "Argentina won the FIFA World Cup in 2022, defeating France in the final.",
        "who is the most decorated olympian": "Michael Phelps is the most decorated Olympian of all time with 28 medals, including 23 golds.",
        "who is the fastest sprinter in the world": "Usain Bolt holds the record for the fastest 100 meters with a time of 9.58 seconds.",
        "most goals in a world cup": "Marta, a Brazilian footballer, holds the record for the most goals in FIFA Women's World Cup history.",
        "who holds the record for the most grand slams in tennis": "As of 2023, Novak Djokovic holds the record for the most Grand Slam singles titles, with 24.",
        "who is known as the king of cricket": "Sachin Tendulkar, an Indian cricketer, is often referred to as the 'King of Cricket'.",
        "who won the first cricket world cup": "The first Cricket World Cup was won by the West Indies in 1975.",
        "highest scorer in the nba": "Kareem Abdul-Jabbar holds the record for the most points scored in NBA history with 38,387 points.",
    
    # Politics
        "who is the president of the united states": "Joe Biden is the President of the United States, taking office on January 20, 2021.",
        "who is the prime minister of india": "Narendra Modi is the Prime Minister of India, serving since May 2014.",
        "who was the first president of the united states": "George Washington was the first President of the United States, serving from 1789 to 1797.",
        "who was the first woman prime minister of the united kingdom": "Margaret Thatcher was the first woman Prime Minister of the United Kingdom, serving from 1979 to 1990.",
        "who was the first female chancellor of germany": "Angela Merkel was the first female Chancellor of Germany, serving from 2005 to 2021.",
        "who was the first black president of the united states": "Barack Obama was the first Black President of the United States, serving from 2009 to 2017.",
        "who is the leader of the communist party in china": "Xi Jinping is the General Secretary of the Communist Party of China and the President of the People's Republic of China.",
        "who is the longest-serving monarch in british history": "Queen Elizabeth II was the longest-reigning monarch in British history, reigning for 70 years until her death in 2022.",
    
    # Miscellaneous
        "what is the largest country by population": "China is the most populous country in the world, with over 1.4 billion people.",
        "what is the largest country by land area": "Russia is the largest country in the world by land area, covering more than 17 million square kilometers.",
        "most populated city in the world": "Tokyo, Japan, is the most populous city in the world, with over 37 million people in the metropolitan area.",
        "what is the tallest mountain in the world": "Mount Everest, located in the Himalayas on the border between Nepal and China, is the tallest mountain on Earth, standing at 8,848 meters (29,029 feet).",
        "what is the longest river in the world": "The Nile River in Africa was traditionally considered the longest river in the world, though some recent measurements suggest the Amazon River in South America may be longer.",
        "what is the largest ocean in the world": "The Pacific Ocean is the largest ocean in the world, covering more than 63 million square miles.",
        "who invented the internet": "The internet was developed by various scientists, but it was largely driven by Tim Berners-Lee, who invented the World Wide Web in 1989.",
        "what is the currency of japan": "The currency of Japan is the Japanese Yen (JPY).",
        "what is the currency of india": "The currency of India is the Indian Rupee (INR).",
        "first man in space": "Yuri Gagarin, a Soviet cosmonaut, was the first man to travel into space on April 12, 1961.",
        "first woman in space": "Valentina Tereshkova was the first woman to travel into space, orbiting Earth in 1963.",
    
    # IPL (Indian Premier League)
        "who won the ipl in 2023": "The Gujarat Titans won the 2023 Indian Premier League (IPL) by defeating the Rajasthan Royals in the final.",
        "most successful ipl team": "The Mumbai Indians are the most successful team in the history of the IPL, having won the title 5 times.",
        "who is the highest run scorer in ipl": "The highest run-scorer in IPL history is Virat Kohli, with over 6,500 runs as of 2023.",
        "who is the highest wicket-taker in ipl": "Lasith Malinga holds the record for the highest wicket-taker in IPL history, with 170 wickets.",
        "who was the first player to score 1000 runs in ipl": "The first player to score 1,000 runs in IPL history was Adam Gilchrist, achieving this milestone in 2008.",
        "who won the first ipl title": "The Rajasthan Royals won the inaugural IPL title in 2008, defeating Chennai Super Kings in the final.",
        "who is known as the 'captain cool' in ipl": "Mahendra Singh Dhoni, commonly known as MS Dhoni, is often referred to as 'Captain Cool' due to his calm demeanor and leadership in IPL.",
        "who won ipl 2022": "The Gujarat Titans won the IPL 2022, defeating the Rajasthan Royals in the final to claim their maiden title.",
        "who has the most sixes in ipl": "Chris Gayle holds the record for the most sixes in IPL history, with over 350 sixes.",
        "which player has hit the most fours in ipl": "Shikhar Dhawan holds the record for the most fours in IPL history.",
    
    # Movies
        "highest-grossing indian movie": "As of 2023, 'RRR' directed by S.S. Rajamouli is the highest-grossing Indian film worldwide.",
        "first indian film to win an oscar": "The first Indian film to win an Oscar was 'Gandhi' (1982), directed by Richard Attenborough.",
        "most popular indian actor": "Shah Rukh Khan is considered the most popular Indian actor internationally and is often called the 'King of Bollywood'.",
        "first film to earn $1 billion": "The first film to gross over $1 billion worldwide was 'Avatar' (2009), directed by James Cameron.",
        "who won the oscar for best actor in 2023": "Brendan Fraser won the Academy Award for Best Actor in 2023 for his role in 'The Whale'.",
        "most oscars won by an actor": "Katharine Hepburn holds the record for the most Oscars won by an actor, with four Best Actress awards.",
        "who directed the godfather": "'The Godfather' (1972), one of the most iconic films in history, was directed by Francis Ford Coppola.",
    
    # Sports
        "most gold medals in olympics": "Michael Phelps holds the record for the most gold medals in the Olympics, with 23.",
        "who won the 2023 cricket world cup": "The 2023 ICC Men's Cricket World Cup was won by India, defeating Australia in the final.",
        "who holds the world record for fastest 100 meters": "Usain Bolt holds the world record for the 100 meters, completing it in 9.58 seconds in 2009.",
        "most grand slam titles in tennis": "Margaret Court holds the record for the most Grand Slam singles titles with 24.",
        "who won the first football world cup": "The first FIFA World Cup was held in 1930, and it was won by Uruguay.",
        "who has the most nba championships": "The Boston Celtics and the Los Angeles Lakers are tied with the most NBA championships, each with 17 titles.",
        "who is the greatest football player of all time": "Pelé and Diego Maradona are often considered two of the greatest football players of all time, with many debates over who holds the top spot. Lionel Messi and Cristiano Ronaldo are also part of the conversation in recent years.",
    
    # Politics
        "who is the president of india": "Droupadi Murmu is the 15th President of India, taking office in July 2022.",
        "who is the president of the united states": "Joe Biden is the current President of the United States, having taken office in January 2021.",
        "first woman president of india": "Pratibha Patil was the first woman to serve as the President of India, holding office from 2007 to 2012.",
        "first female prime minister of india": "Indira Gandhi was the first and only female Prime Minister of India, serving from 1966 to 1977 and again from 1980 to 1984.",
        "first prime minister of india": "Jawaharlal Nehru was the first Prime Minister of India, serving from 1947 until his death in 1964.",
        "who was the first woman prime minister of the uk": "Margaret Thatcher was the first female Prime Minister of the United Kingdom, serving from 1979 to 1990.",
        "who was the first african-american president of the united states": "Barack Obama became the first African-American President of the United States in 2009.",
    
    # Miscellaneous
        "0  ": "China is the most populous country in the world, with over 1.4 billion people.",
        "what is the largest country by land area": "Russia is the largest country in the world by land area, covering over 17 million square kilometers.",
        "what is the most spoken language in the world": "Mandarin Chinese is the most spoken language in the world, with over 1 billion native speakers.",
        "what is the longest river in the world": "The Nile River in Africa is traditionally considered the longest river in the world, but some sources suggest the Amazon River may be slightly longer.",
        "who invented the telephone": "Alexander Graham Bell is credited with inventing the telephone in 1876.",
        "what is the currency of the united states": "The currency of the United States is the US Dollar (USD).",
        "who is the first person to walk on the moon": "Neil Armstrong was the first person to walk on the Moon on July 20, 1969, during the Apollo 11 mission.",
       "who invented the light bulb": "Thomas Edison is credited with inventing the first commercially successful light bulb.",

   

}

    
    # Example dictionaries (add your real values)


    for key in greetings:
        if key in query:
            await say(greetings[key])
            return

    
 

    # for key in greetings:
    #     if key in query:
    #         replies = greetings[key]
    #         selected_reply = random.choice(replies)
    #         await say(selected_reply)
    #         return

        

   
    
    if query in ["exit", "quit", "stop"]:
        await say("Goodbye!")
        sys.exit()
        
    

        # Final fallback
        await say("I'm still learning. Can you try asking in a different way?")





def main():
    prompt_language()
    while True:
        print("\n1. Sign Up\n2. Login\n3. Search User\n4. Reset Users")
        choice = input("Enter choice: ").strip()
        if choice == "1":
            sign_up()
        elif choice == "2":
            user = asyncio.run(authenticate_face())
            if user:
                while True:
                    mode = input("\nText or Voice command? ").strip().lower()
                    if mode not in ["text", "voice"]:
                        print("Invalid choice.")
                        continue
                    while True:
                        if mode == "text":
                            query = input("You: ")
                        else:
                            query = takeCommand()
                        if not query or query.lower() in ["exit", "quit","stop"]:
                            asyncio.run(say("Goodbye!, Have a nice day"))
                            sys.exit()
                        asyncio.run(execute_command(query))
        elif choice == "3":
            name = input("Enter name: ")
            print("Exists" if name in known_face_names else "Not found.")
        elif choice == "4":
            if os.path.exists(FACE_DATA):
                os.remove(FACE_DATA)
            known_face_names.clear()
            known_face_encodings.clear()
            print("Users reset.")
        else:
            print("Invalid option.")

if __name__ == "__main__":
    main()
