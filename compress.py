import logging
import re
import asyncio
import io
from aiogram import Bot, Dispatcher, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile
from docx import Document
from uuid import uuid4
from os import getenv
from dotenv import load_dotenv

load_dotenv()

API_TOKEN = getenv('BOT_TOKEN')

if not API_TOKEN:
    raise ValueError("Не указан токен бота. Проверьте файл .env")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

bot = Bot(token=API_TOKEN)
dp = Dispatcher()

user_compression_types = {}
temp_storage = {}

def summarize_text(text, sentence_count=3):
    text = re.sub(r'<.*?>', '', text)
    sentences = re.split(r'(?<=[.!?])\s+', text)

    word_frequency = {}
    words = re.findall(r'\w+', text.lower())
    
    for word in words:
        word_frequency[word] = word_frequency.get(word, 0) + 1

    sentence_scores = {}
    for sentence in sentences:
        score = sum(word_frequency.get(word.lower(), 0) for word in re.findall(r'\w+', sentence))
        sentence_scores[sentence] = score

    important_sentences = sorted(sentence_scores, key=sentence_scores.get, reverse=True)[:sentence_count]
    return ' '.join(important_sentences)

def strong_summarize_text(text, sentence_count=1):
    text = re.sub(r'<.*?>', '', text)
    sentences = re.split(r'(?<=[.!?])\s+', text)

    if len(sentences) <= 1:
        return text

    word_frequency = {}
    words = re.findall(r'\w+', text.lower())
    
    for word in words:
        word_frequency[word] = word_frequency.get(word, 0) + 1

    sentence_scores = {}
    for sentence in sentences:
        words_in_sentence = re.findall(r'\w+', sentence)
        if len(words_in_sentence) < 3:
            continue
            
        score = sum(word_frequency.get(word.lower(), 0) for word in words_in_sentence)
        score *= len(words_in_sentence)
        score /= max(len(sentence), 1)
        sentence_scores[sentence] = score

    important_sentences = sorted(sentence_scores, key=sentence_scores.get, reverse=True)[:sentence_count]
    return ' '.join(important_sentences)

@dp.message()
async def handle_message(message: types.Message):
    if message.text == '/start':
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="Обычное сжатие", callback_data="normal"),
                InlineKeyboardButton(text="Сильное сжатие", callback_data="strong")
            ]
        ])
        await message.reply("Привет! Отправьте текст или файл (TXT/DOCX) для сжатия. Выберите тип сжатия:", reply_markup=keyboard)
        return

    compression_type = user_compression_types.get(message.from_user.id)
    
    if compression_type is None:
        await message.reply("Пожалуйста, сначала выберите тип сжатия, используя /start.")
        return

    text = ""
    original_filename = ""

    if message.text and not message.text.startswith('/'):
        text = message.text
        original_filename = "compressed_text"

    elif message.document:
        file_name = message.document.file_name
        original_filename = file_name.rsplit('.', 1)[0]
        
        file = await bot.get_file(message.document.file_id)
        file_path = file.file_path
        file_content = await bot.download_file(file_path)
        
        if file_name.lower().endswith('.txt'):
            text = file_content.read().decode('utf-8')
        elif file_name.lower().endswith('.docx'):
            doc = Document(io.BytesIO(file_content.read()))
            text = '\n'.join([paragraph.text for paragraph in doc.paragraphs])
        else:
            await message.reply("Поддерживаются только файлы TXT и DOCX.")
            return

    if not text:
        await message.reply("Не удалось получить текст из файла.")
        return

    if compression_type == "normal":
        summary = summarize_text(text)
    else:
        summary = strong_summarize_text(text)

    result_file = io.BytesIO()
    result_file.write(summary.encode('utf-8'))
    result_file.seek(0)
    
    try:
        await message.reply_document(
            document=FSInputFile(
                path=result_file,
                filename=f"{original_filename}_compressed.txt"
            ),
            caption="Вот ваш сжатый текст:"
        )
    except Exception as e:
        logger.error(f"Ошибка при отправке файла: {e}")
        await message.reply(
            f"Сжатый текст:\n\n{summary}\n\n(Не удалось отправить файлом)",
        )

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Сжать ещё", callback_data="more")]
    ])
    
    await message.reply("Хотите сжать другой текст?", reply_markup=keyboard)

@dp.callback_query()
async def handle_compression_choice(callback_query: types.CallbackQuery):
    if callback_query.data in ["normal", "strong"]:
        await bot.answer_callback_query(callback_query.id)
        user_compression_types[callback_query.from_user.id] = callback_query.data
        await bot.send_message(callback_query.from_user.id, "Пожалуйста, отправьте текст для сжатия:")
    elif callback_query.data == "more":
        await bot.answer_callback_query(callback_query.id)
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="Обычное сжатие", callback_data="normal"),
                InlineKeyboardButton(text="Сильное сжатие", callback_data="strong")
            ]
        ])
        await bot.send_message(
            callback_query.from_user.id,
            "Выберите тип сжатия:",
            reply_markup=keyboard
        )

async def main():
    try:
        await dp.start_polling(bot, skip_updates=True)
    finally:
        await bot.session.close()

if __name__ == '__main__':
    asyncio.run(main())
