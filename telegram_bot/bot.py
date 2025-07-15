import logging
import os
import google.generativeai as genai
from langdetect import detect, LangDetectException
import pycountry

from telegram import Update
from telegram.error import TelegramError
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# --- Logging Configuration ---
# Configure logging at the module level for early use if needed
# Basic configuration will be in main() for application-level settings
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- Environment Variable Checks ---
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

if not TELEGRAM_TOKEN:
    logger.critical("TELEGRAM_TOKEN environment variable not set. Bot cannot start.")
    # Consider exiting here if running in a context where the bot must start
    # For now, main() will handle the exit.

if GEMINI_API_KEY:
    try:
        genai.configure(api_key=GEMINI_API_KEY)
        logger.info("Gemini API key configured successfully.")
    except Exception as e:
        logger.error(f"Failed to configure Gemini API key: {e}. Scam detection will be disabled.")
        GEMINI_API_KEY = None # Ensure it's treated as None if configuration fails
else:
    logger.warning("GEMINI_API_KEY environment variable not set. Scam detection features will be limited or disabled.")


# --- Utility Functions ---
def get_text_from_update(update: Update) -> str | None:
    """
    Extracts text from a command message, replied-to message, or forwarded message.
    Returns None if no relevant text is found.
    """
    if not update or not update.message:
        return None
    
    message_text = update.message.text
    
    if message_text and message_text.startswith('/'):
        # For commands like /analyze text, text is after command
        parts = message_text.split(' ', 1)
        if len(parts) > 1 and parts[1].strip():
            return parts[1].strip()
            
    # Check for reply
    if update.message.reply_to_message and update.message.reply_to_message.text:
        return update.message.reply_to_message.text.strip()
        
    # If it's a command with no arguments and not a reply, return None
    # This prevents the command itself (e.g., "/analyze") from being used as text.
    if message_text and ' ' not in message_text and not update.message.reply_to_message:
        return None
        
    # Fallback for forwarded messages (text is directly in update.message.text)
    # or simple messages without a command structure.
    # This case should generally be handled by the main message handler, not command text extraction.
    # However, if a command is invoked without arguments and IS a reply, reply_to_message text is already caught.
    # If it's just the command itself (e.g. user types "/analyze" and hits send), we want None.
    # The original check `if update.message and update.message.text and ' ' not in update.message.text and not update.message.reply_to_message:`
    # was good for this.
    # If it's a forwarded message, update.message.text will contain the forwarded text.
    # Let's refine to make sure we only return text if it's clearly payload.
    
    # If the message text is just the command itself (e.g. /analyze) and not a reply, return None.
    if message_text and message_text.startswith('/') and ' ' not in message_text and not update.message.reply_to_message:
        return None

    # If it's a reply, that's handled. If it has args, that's handled.
    # If it's a forwarded message, the text is in update.message.text without the command part.
    # If it's a direct message (not a command), it's handled by handle_message.
    # This function is primarily for extracting arguments *for a command*.
    # So, if the text is just the command itself, it means no argument was provided.
    if update.message.text and not update.message.text.startswith('/'): # Forwarded message text
        return update.message.text.strip()

    return None


def identify_language(message_text: str) -> tuple[str | None, str | None]:
    if not message_text or len(message_text.strip()) < 3:
        logger.info("identify_language: No message text provided or text too short for reliable detection.")
        return None, None
    try:
        lang_code = detect(message_text)
        language = pycountry.languages.get(alpha_2=lang_code)
        lang_name = language.name if language else lang_code
        logger.info(f"identify_language: Detected language code='{lang_code}', name='{lang_name}' for text: '{message_text[:50]}...'")
        return lang_code, lang_name
    except LangDetectException as e:
        logger.warning(f"identify_language: Language detection failed for text: '{message_text[:50]}...': {e}")
        return None, None
    except Exception as e:
        logger.error(f"identify_language: Unexpected error for text '{message_text[:50]}...': {e}", exc_info=True)
        return None, None


def detect_scam(message_text: str, api_key: str | None) -> str:
    if not api_key:
        logger.warning("detect_scam: Gemini API key not available.")
        return "Uncertain - API key missing"
    if not message_text:
        logger.info("detect_scam: No message text provided.")
        return "Uncertain - No text provided"

    try:
        model = genai.GenerativeModel('gemini-pro')
        prompt = (
            "Analyze the following message and determine if it is a scam. "
            "Respond with only one of these exact terms: Scam, Likely Scam, Safe, or Uncertain. "
            f"Message: {message_text}"
        )
        response = model.generate_content(prompt)
        if response.parts:
            return response.text.strip()
        else:
            logger.warning("detect_scam: Gemini API returned no content.")
            return "Error: No content from AI model"
    except Exception as e:
        logger.error(f"detect_scam: Error contacting Gemini API for text '{message_text[:50]}...': {e}", exc_info=True)
        return "Error contacting AI model"


def interpret_gemini_response(response_text: str) -> str:
    # Check longer verdict phrases first when parsing partial matches
    valid_verdicts = ["Likely Scam", "Scam", "Safe", "Uncertain"]
    if response_text.startswith("Error") or response_text == "Uncertain - API key missing" or response_text == "Uncertain - No text provided":
        logger.info(f"interpret_gemini_response: Returning '{response_text}' as is (error or missing input).")
        return "Uncertain (due to error or missing input)"

    if response_text in valid_verdicts:
        logger.info(f"interpret_gemini_response: Gemini response is a valid verdict: '{response_text}'")
        return response_text
    else:
        logger.warning(f"interpret_gemini_response: Gemini response '{response_text}' is not an expected verdict. Attempting to parse.")
        for verdict in valid_verdicts:
            if verdict.lower() in response_text.lower():
                logger.info(f"interpret_gemini_response: Parsed '{verdict}' from response: '{response_text}'")
                return verdict
        logger.warning(f"interpret_gemini_response: Could not parse valid verdict from '{response_text}'. Defaulting to Uncertain.")
        return "Uncertain"

# --- Helper for sending messages ---
async def send_reply(update: Update, text: str, **kwargs):
    """Helper to send replies and handle Telegram API errors."""
    if not update or not update.message:
        logger.error("send_reply: Update or update.message is None, cannot send reply.")
        return
    try:
        await update.message.reply_text(text, **kwargs)
    except TelegramError as e:
        logger.error(f"send_reply: Failed to send message to user {update.effective_user.id if update.effective_user else 'Unknown'}. Error: {e}", exc_info=True)
        # Optionally, try to send a generic error to the user if this specific message failed
        try:
            await update.message.reply_text("Sorry, I encountered an issue trying to send that message.")
        except TelegramError as e_fallback:
            logger.error(f"send_reply: Fallback error message also failed for user {update.effective_user.id if update.effective_user else 'Unknown'}. Error: {e_fallback}", exc_info=True)
    except Exception as e: # Catch any other unexpected errors
        logger.error(f"send_reply: Unexpected error for user {update.effective_user.id if update.effective_user else 'Unknown'}: {e}", exc_info=True)


# --- Command Handlers ---
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.info(f"Command /start triggered by user {update.effective_user.id if update.effective_user else 'Unknown'}")
    welcome_message = (
        "Hello! I am your Telegram Scam Detector Bot.\n\n"
        "I can help you by:\n"
        "- Analyzing messages for potential scams.\n"
        "- Identifying the language of a message.\n\n"
        "You can interact with me using commands. Use /help to see a list of all available commands."
    )
    await send_reply(update, welcome_message)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.info(f"Command /help triggered by user {update.effective_user.id if update.effective_user else 'Unknown'}")
    help_text = (
        "Here are the commands you can use:\n\n"
        "/start - Shows the welcome message.\n"
        "/help - Shows this help message.\n"
        "/analyze [text_to_analyze] - Analyzes the provided text (or a replied-to message) for scams and identifies its language. "
        "Example: `/analyze Check out this amazing offer!` or reply to a message with `/analyze`.\n"
        "/language [text_to_identify] - Identifies the language of the provided text (or a replied-to message). "
        "Example: `/language Hello world` or reply to a message with `/language`.\n"
        "/feedback [your_feedback] - Allows you to send feedback about the bot. "
        "Example: `/feedback This bot is very helpful!`\n"
        "/privacy - Shows the bot's privacy policy.\n"
        "/report [message_to_report] - Reports a message you believe to be a scam. "
        "Example: `/report This user is sending phishing links.`\n\n"
        "You can also just send me any text message directly, and I will try to analyze it for scams."
    )
    await send_reply(update, help_text)

async def analyze_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.info(f"Command /analyze triggered by user {update.effective_user.id if update.effective_user else 'Unknown'}")
    text_to_analyze = get_text_from_update(update)

    if not text_to_analyze:
        await send_reply(update, "Please provide text to analyze, either after the command or by replying to a message. Example: `/analyze suspicious message`")
        return

    scam_verdict = "Unavailable"
    if not GEMINI_API_KEY:
        logger.warning(f"/analyze: GEMINI_API_KEY not set. Scam detection skipped for user {update.effective_user.id if update.effective_user else 'Unknown'}.")
        scam_verdict = "Unavailable (AI service not configured)"
    else:
        gemini_raw_response = detect_scam(text_to_analyze, GEMINI_API_KEY)
        scam_verdict = interpret_gemini_response(gemini_raw_response)

    lang_code, lang_name = identify_language(text_to_analyze)
    language_info = "Could not detect language"
    if lang_name:
        language_info = f"{lang_name} ({lang_code})" if lang_code and lang_code != lang_name else lang_name


    reply_message = (
        f"Analysis Complete:\n"
        f"Detected Language: {language_info}\n"
        f"Scam Analysis: {scam_verdict}"
    )
    await send_reply(update, reply_message)

async def language_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.info(f"Command /language triggered by user {update.effective_user.id if update.effective_user else 'Unknown'}")
    text_to_identify = get_text_from_update(update)

    if not text_to_identify:
        await send_reply(update, "Please provide text for language identification, either after the command or by replying to a message. Example: `/language Bonjour le monde`")
        return

    lang_code, lang_name = identify_language(text_to_identify)
    reply_message = f"Detected Language: {lang_name} ({lang_code})" if lang_name and lang_code and lang_code != lang_name else lang_name
    if not reply_message:
        reply_message = "Could not detect language."
        
    await send_reply(update, reply_message)

async def feedback_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.info(f"Command /feedback triggered by user {update.effective_user.id if update.effective_user else 'Unknown'}")
    feedback_text = get_text_from_update(update) # Use the helper

    if not feedback_text:
        await send_reply(update, "Please provide your feedback after the /feedback command. Example: `/feedback I like this bot!`")
        return

    logger.info(f"Feedback from user {update.effective_user.id} ({update.effective_user.username if update.effective_user else 'Unknown'}): {feedback_text}")
    await send_reply(update, "Thank you for your feedback!")

async def privacy_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.info(f"Command /privacy triggered by user {update.effective_user.id if update.effective_user else 'Unknown'}")
    privacy_policy = (
        "**Privacy Policy**\n\n"
        "This bot is designed to help detect potential scams and identify message languages.\n\n"
        "1.  **Data We Process:** When you send a message to the bot (either directly or via a command like `/analyze`), the text of that message is processed. If you use the `/feedback` or `/report` command, that text is also processed.\n"
        "2.  **How We Use Data:**\n"
        "    *   Message text is sent to the Google Gemini API for scam detection analysis if the `GEMINI_API_KEY` is configured.\n"
        "    *   Message text is analyzed locally for language identification using the `langdetect` library.\n"
        "    *   Feedback and reported messages are logged for review and service improvement.\n"
        "    *   User IDs and usernames may be logged with feedback/reports for context.\n"
        "3.  **Data Logging:** We log messages, analysis results, feedback, and reports to monitor bot performance, improve accuracy, and address issues. These logs are treated confidentially.\n"
        "4.  **Third-Party Services:** Scam analysis relies on the Google Gemini API. Please refer to Google's privacy policies for information on how they handle data.\n"
        "5.  **Data Retention:** Logged data is retained as necessary for the bot's operation and improvement.\n"
        "6.  **Your Consent:** By using this bot, you consent to the processing of your messages as described in this policy.\n\n"
        "We are committed to user privacy and will not share your personal data with unauthorized third parties."
    )
    await send_reply(update, privacy_policy, parse_mode='Markdown')

async def report_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.info(f"Command /report triggered by user {update.effective_user.id if update.effective_user else 'Unknown'}")
    reported_text = get_text_from_update(update) # Use the helper

    if not reported_text:
        await send_reply(update, "Please provide the message you want to report after the /report command. Example: `/report This is a scam message I received.`")
        return

    logger.warning(f"Manual scam report from user {update.effective_user.id} ({update.effective_user.username if update.effective_user else 'Unknown'}): {reported_text}")
    await send_reply(update, "Thank you for your report. We will review it.")

# --- General Message Handler ---
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.message.text: # Should not happen with TEXT filter but good practice
        return
        
    message_text = update.message.text
    user_id = update.effective_user.id if update.effective_user else "Unknown"
    logger.info(f"handle_message: Received general message from user {user_id}: '{message_text[:50]}...'")
    
    if not GEMINI_API_KEY:
        logger.info(f"handle_message: GEMINI_API_KEY not set. General message from user {user_id} will not be analyzed for scams.")
        # No reply to user to avoid being too noisy, unless specific behavior is desired
        return

    # Avoid processing own replies or messages that might be commands without a leading /
    if message_text.startswith("Analysis Complete:") or \
       message_text.startswith("Detected Language:") or \
       message_text.startswith("Scam detection result:") or \
       message_text.startswith("Automated Scam Analysis:"):
        logger.info(f"handle_message: Ignoring likely bot reply message from user {user_id}.")
        return

    gemini_raw_response = detect_scam(message_text, GEMINI_API_KEY)
    interpreted_result = interpret_gemini_response(gemini_raw_response)
    
    reply_needed = False
    reply_text = ""

    if interpreted_result in ["Scam", "Likely Scam"]:
        reply_text = f"Automated Scam Analysis: This message looks like a '{interpreted_result}'. Please be cautious."
        reply_needed = True
    elif interpreted_result == "Uncertain" or interpreted_result.startswith("Error"):
        reply_text = f"Automated Scam Analysis: The analysis result is '{interpreted_result}'. Please be cautious."
        reply_needed = True
    else: # Safe
        logger.info(f"handle_message: General message from user {user_id} analyzed as Safe: '{message_text[:50]}...'")

    if reply_needed:
        await send_reply(update, reply_text)


# --- Global Error Handler ---
async def global_error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Log Errors caused by Updates and send a generic message to the user."""
    logger.error(f"Global error_handler: Unhandled error processing update {update}", exc_info=context.error)
    
    if isinstance(update, Update) and update.effective_message:
        try:
            await send_reply(update, "Sorry, an unexpected error occurred. The issue has been logged.")
        except Exception as e:
            logger.error(f"Global error_handler: Failed to send generic error message to user: {e}", exc_info=True)


# --- Main Function ---
def main() -> None:
    """Start the bot."""
    # Logging is configured at the top, but ensure level for application if needed
    # logging.basicConfig already called, so this would be redundant unless changing config
    # logger.setLevel(logging.INFO) # Or from env var

    if not TELEGRAM_TOKEN:
        # Critical log already made. Exit if this is a script context.
        print("TELEGRAM_TOKEN is not set. Bot cannot start. Exiting.", file=os.sys.stderr)
        return # Or sys.exit(1)

    application = Application.builder().token(TELEGRAM_TOKEN).build()

    # Register command handlers
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("analyze", analyze_command))
    application.add_handler(CommandHandler("language", language_command))
    application.add_handler(CommandHandler("feedback", feedback_command))
    application.add_handler(CommandHandler("privacy", privacy_command))
    application.add_handler(CommandHandler("report", report_command))

    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_error_handler(global_error_handler) # Register the global error handler

    logger.info("Starting bot polling...")
    try:
        application.run_polling()
    except Exception as e: # Catch errors during polling start or during polling itself if not caught by global_error_handler
        logger.critical(f"Main: Bot polling failed critically: {e}", exc_info=True)

if __name__ == "__main__":
    main()
