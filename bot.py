import html
import logging
import os
import urllib.parse
from uuid import uuid4

import requests
import vertexai
import wolframalpha
from dotenv import load_dotenv
from more_itertools import peekable
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, InlineQueryResultArticle, InputTextMessageContent, \
    Update, InlineQueryResultPhoto
from telegram.constants import ParseMode
from telegram.ext import ApplicationBuilder, CallbackContext, CallbackQueryHandler, CommandHandler, ContextTypes, \
    InlineQueryHandler
from telegram.helpers import mention_html
from vertexai.generative_models import GenerativeModel

from langdetect import detect
from deep_translator import GoogleTranslator

# Use any translator you like, in this example GoogleTranslator
translator = GoogleTranslator(source='auto', target='en')

load_dotenv()

os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = '/home/Icarussiano/provagemini-417819-7eb2582ee0d4.json'
project_id = "provagemini-417819"
location = "us-central1"
vertexai.init(project=project_id, location=location)
model = GenerativeModel("gemini-1.0-pro")

# setup logger
logging.basicConfig(
    filename='app.log',
    filemode='a',
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
# set higher logging level for httpx to avoid all GET and POST requests being logged
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

TOKEN = os.getenv('TOKEN2')
appid = os.getenv('APPID')
wolfram_client = wolframalpha.Client(appid)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a message when the command /start is issued."""
    user_id = update.effective_user.id
    name = update.effective_user.full_name
    menzione = mention_html(user_id, name)
    await update.message.reply_html(
        f"Ciao {menzione}! Sono un bot che ti aiuta a rispondere alle domande usando WolframAlpha. Scrivi /help per "
        f"sapere come usarmi.")


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a message when the command /help is issued."""
    help_text = "Puoi usare i seguenti comandi:\n\n"
    help_text += "/short <query>: Risponderò usando l'API short answers di WolframAlpha\n"
    help_text += "/img <query>: Risponderò con l'immagine del risultato di WolframAlpha\n"
    help_text += ("/query <query>: Risponderò in modo dettagliato, riportando tutte le informazioni testuali "
                  "disponibili\n")
    help_text += "\nPuoi anche usare il bot inline, scrivendo @simplewolframbot <query> e poi selezionando uno dei " \
                 "bottoni oppure direttamente @simplewolframbot img <query> per inviare inline l'immagine "
    await update.message.reply_text(help_text)


async def simple_query(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle the /simple command. This is run when you type: /simple <query>"""
    query = ' '.join(update.message.text.split()[1:])
    query_url = urllib.parse.quote_plus(query)
    short_url = f"http://api.wolframalpha.com/v1/result?appid={appid}&i={query_url}"
    res = requests.get(short_url).text
    await update.message.reply_text(res)


async def img(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle the /img command. This is run when you type: /img <query>"""
    query = ' '.join(update.message.text.split()[1:])
    query_url = urllib.parse.quote_plus(query)
    photo_url = f"http://api.wolframalpha.com/v1/simple?appid={appid}&i={query_url}"
    res = requests.get(photo_url)
    with open('output.png', 'wb') as f:
        f.write(res.content)
    await update.message.reply_photo(open('output.png', 'rb'))


async def reply_query(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle the /query command. This is run when you type: /query <query>"""
    query = ' '.join(update.message.text.split()[1:])
    res = wolfram_client.query(query)
    result_text = ""
    if peekable(res.results):
        for pod in res.results:
            for subpod in pod.subpods:
                result_text += f"{subpod.plaintext}\n"
    else:
        for pod in res.pods:
            result_text += f"\n{pod.title}\n"
            for subpod in pod.subpods:
                result_text += f"{subpod.plaintext}\n"
    if len(result_text) > 4096:
        result_text = result_text[:4096]
    await update.message.reply_text(result_text)


async def inline_query(update: Update, context: CallbackContext) -> None:
    """Handle the inline query. This is run when you type: @simplewolframbot <query>"""
    query = update.inline_query.query
    user_id = update.inline_query.from_user.id
    if query.startswith("img "):
        query = query[4:]
        query_url = urllib.parse.quote_plus(query)
        photo_url = f"http://api.wolframalpha.com/v1/simple?appid={appid}&i={query_url}"
        results = [
            InlineQueryResultPhoto(
                id=str(uuid4()),
                photo_url=photo_url,
                thumbnail_url="https://www.wolframalpha.com/_next/static/images/share_3eSzXbxb.png",
            )
        ]
        await update.inline_query.answer(results)
    # create keyboard with three buttons named Risposta, Immagine , LaTeX(sperimentale)
    keyboard = [
        [
            InlineKeyboardButton("Risposta", callback_data=f"1:{query}:{user_id}"),
            InlineKeyboardButton("Risposta breve", callback_data=f"2:{query}:{user_id}"),
        ],
        [InlineKeyboardButton("LaTeX(Sperimentale)", callback_data=f"3:{query}:{user_id}"),
         InlineKeyboardButton("Immagine", switch_inline_query_current_chat=f"img {query}"), ],
        [
            InlineKeyboardButton("Modifica query", switch_inline_query_current_chat=f"{query}"),
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    results = [

        InlineQueryResultArticle(
            id=str(uuid4()),
            title="Risultati",
            input_message_content=InputTextMessageContent(
                f"Seleziona l'opzione per cercare <code>{html.escape(query)}</code>", parse_mode=ParseMode.HTML),
            reply_markup=reply_markup
        ),
    ]

    await context.bot.answer_inline_query(update.inline_query.id, results=results)


async def button(update: Update, CallbackContext) -> None:
    """Parses the CallbackQuery and updates the message text."""
    query = update.callback_query
    callback_user_id = query.data.split(":")[2]
    user_id = query.from_user.id
    if callback_user_id != str(user_id):
        await query.answer("NON SEI AUTORIZZATO, SOLO L'UTENTE CHE HA FATTO LA QUERY PUÒ USARE I BOTTONI PER OTTENERE LE RISPOSTE. ", show_alert=True)
        return
    global chunks
    keyboard = []
    # CallbackQueries need to be answered, even if no notification to the user is needed
    # Some clients may have trouble otherwise. See https://core.telegram.org/bots/api#callbackquery
    await query.answer()
    search_query = query.data.split(":")[1]
    if detect(search_query)=="it":
        search_query=translator.translate(search_query)

    answer = "No answer"
    if query.data.startswith("1:"):
        res = wolfram_client.query(search_query)
        result_text = ""
        if peekable(res.results):
            for pod in res.results:
                for subpod in pod.subpods:
                    result_text += f"{subpod.plaintext}\n"
        else:
            for pod in res.pods:
                result_text += f"\n<b>{pod.title}</b>\n"
                for subpod in pod.subpods:
                    result_text += f"{subpod.plaintext}\n"
        if len(result_text) > 4000:
            chunks = (result_text[i:i + 4000] for i in range(0, len(result_text), 4000))
            keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("Next", callback_data=f"4")], ])
            await query.edit_message_text(f"<b>{html.escape(search_query)}</b>\n{next(chunks)}", reply_markup=keyboard,
                                          parse_mode=ParseMode.HTML)
        else:
            await query.edit_message_text(f"<b>{html.escape(search_query)}</b>\n{result_text}",
                                          parse_mode=ParseMode.HTML)
    elif query.data.startswith("2:"):
        query_url = urllib.parse.quote_plus(search_query)
        short_url = f"http://api.wolframalpha.com/v1/result?appid={appid}&i={query_url}"
        res = requests.get(short_url).text
        await query.edit_message_text(f"<b>{html.escape(search_query)}</b>\n{res}", parse_mode=ParseMode.HTML)
    elif query.data.startswith("3:"):
        query_url = urllib.parse.quote_plus(search_query)
        short_url = f"http://api.wolframalpha.com/v1/result?appid={appid}&i={query_url}"
        res = requests.get(short_url).text
        latex = f"Convert the following text in LaTex inline expression. Answer only with the LaTex code delimited by dollar sign. \nText: {search_query}={res}"
        responses = model.generate_content(latex, stream=True)
        latex_text = ''.join([response.text for response in responses])
        latex_text = latex_text.lstrip('$')
        latex_text = latex_text.rstrip('$')
        latex_text = f"${latex_text}$"
        await query.edit_message_text(latex_text)
    elif query.data.startswith("4"):
        await query.edit_message_text(next(chunks), parse_mode=ParseMode.HTML)


app = ApplicationBuilder().token(TOKEN).build()
app.add_handler(CommandHandler("query", reply_query))
app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("help", help_command))
app.add_handler(CommandHandler("img", img))
app.add_handler(CommandHandler("short", simple_query))
app.add_handler(CallbackQueryHandler(button))
app.add_handler(InlineQueryHandler(inline_query))
app.run_polling()
