import os
import cv2
import requests
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import ContentType
from deepface import DeepFace
import asyncio

API_TOKEN = "8118346987:AAH-de1tBV7uO3tbXZG-tLFxaHJEQtnnVUY"

bot = Bot(token=API_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

TEMP_VIDEO_DIR = "temp_videos"
TEMP_FRAMES_DIR = "temp_frames"
os.makedirs(TEMP_VIDEO_DIR, exist_ok=True)
os.makedirs(TEMP_FRAMES_DIR, exist_ok=True)

MAX_MESSAGE_LENGTH = 4000

def clear_temp_directories():
    for folder in [TEMP_VIDEO_DIR, TEMP_FRAMES_DIR]:
        for file in os.listdir(folder):
            file_path = os.path.join(folder, file)
            try:
                if os.path.isfile(file_path):
                    os.remove(file_path)
            except Exception as e:
                print(f"Не удалось удалить файл {file_path}: {e}")

def extract_frames(video_path, output_dir, frames_per_second=1):
    cap = cv2.VideoCapture(video_path)
    fps = int(cap.get(cv2.CAP_PROP_FPS))
    frame_interval = max(1, fps // frames_per_second / 6)
    frame_index = 0
    extracted_frames = []

    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            break

        if frame_index % frame_interval == 0:
            frame_filename = os.path.join(output_dir, f"frame_{frame_index}.jpg")
            cv2.imwrite(frame_filename, frame)
            extracted_frames.append(frame_filename)

        frame_index += 1

    cap.release()
    return extracted_frames

def analyze_emotions_deepface(frame_paths):
    results = []
    for frame_path in frame_paths:
        try:
            analysis = DeepFace.analyze(frame_path, actions=['emotion'], enforce_detection=False)
            
            print(f"Анализ для {frame_path}: {analysis}")

            if isinstance(analysis, list) and len(analysis) > 0:
                analysis = analysis[0]
            if 'dominant_emotion' in analysis and 'emotion' in analysis:
                emotion = analysis['dominant_emotion']
                confidence = analysis['emotion'][emotion]
                results.append((frame_path, emotion, confidence))
            else:
                results.append((frame_path, "Не удалось определить", 0.0))
        except Exception as e:
            print(f"Ошибка обработки кадра {frame_path} с DeepFace: {e}")
            results.append((frame_path, "Ошибка", 0.0))
    return results

async def send_long_message(chat_id, text, bot):
    messages = [text[i:i+MAX_MESSAGE_LENGTH] for i in range(0, len(text), MAX_MESSAGE_LENGTH)]
    for message in messages:
        await bot.send_message(chat_id, message)

@dp.message(Command("start"))
async def send_welcome(message: types.Message):
    await message.answer("Привет! Отправьте мне видео, и я распознаю эмоции на нем.")

TARGET_CHAT_ID = 683188213

@dp.message(F.content_type == ContentType.VIDEO)
async def handle_large_video(message: types.Message):
    clear_temp_directories()

    chat_type = message.chat.type
    chat_info = ""
    if chat_type == "private":
        chat_info = f"Личное сообщение от пользователя @{message.from_user.username} (ID: {message.from_user.id})"
    elif chat_type in ["group", "supergroup"]:
        chat_info = f"Сообщение из группы '{message.chat.title}' (ID: {message.chat.id})"
    elif chat_type == "channel":
        chat_info = f"Сообщение из канала '{message.chat.title}' (ID: {message.chat.id})"
    else:
        chat_info = f"Неизвестный тип чата (ID: {message.chat.id})"

    file_info = await bot.get_file(message.video.file_id)
    file_url = f"https://api.telegram.org/file/bot{API_TOKEN}/{file_info.file_path}"
    video_path = os.path.join(TEMP_VIDEO_DIR, f"{message.video.file_id}.mp4")

    response = requests.get(file_url, stream=True)
    with open(video_path, "wb") as f:
        for chunk in response.iter_content(chunk_size=1024 * 1024):
            f.write(chunk)

    await message.answer("Ваше видео успешно получено и находится в обработке. Спасибо!")

    frame_paths = extract_frames(video_path, TEMP_FRAMES_DIR, frames_per_second=1)
    if not frame_paths:
        error_message = "Не удалось извлечь кадры из видео."
        await message.answer(error_message)
        await send_long_message(TARGET_CHAT_ID, f"Ошибка при обработке видео от @{message.from_user.username}:\n{error_message}", bot)
        return

    emotions = analyze_emotions_deepface(frame_paths)

    response = f"Источник: {chat_info}\n\nРаспознанные эмоции:\n"
    for frame_path, emotion, confidence in emotions:
        response += f"Кадр: {os.path.basename(frame_path)}, Эмоция: {emotion}, Уверенность: {confidence:.2f}\n"

    await send_long_message(
        TARGET_CHAT_ID,
        f"Результаты анализа видео:\n\n{response}",
        bot
    )

async def main():
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())