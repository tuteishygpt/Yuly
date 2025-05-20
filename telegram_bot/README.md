# Telegram Scam Detector Bot

A Telegram bot that analyzes messages for potential scams using AI (Google Gemini) and identifies the language of the text.

## Features

*   **Scam Detection**: Classifies messages as "Scam", "Likely Scam", "Safe", or "Uncertain" using the Google Gemini API.
*   **Language Identification**: Detects the language of the message using the `langdetect` library.
*   **Interactive Commands**: Provides various commands for on-demand analysis, help, feedback, and more.
*   **Direct Message Analysis**: Automatically analyzes general text messages sent directly to the bot (if configured and the message is deemed a potential risk).

## Prerequisites

*   Python 3.8+
*   Pip (Python package installer)

## Setup & Configuration

1.  **Clone the repository** (or download the `bot.py` and `requirements.txt` files into a directory named `telegram_bot`).
    ```bash
    # Example if you have git installed
    # git clone <repository_url>
    # cd <repository_name>/telegram_bot
    ```
    If you only have the files, create a `telegram_bot` directory and place `bot.py` and `requirements.txt` inside it.

2.  **Navigate to the `telegram_bot` directory.**
    ```bash
    cd telegram_bot
    ```

3.  **Create a virtual environment** (recommended):
    ```bash
    python3 -m venv venv
    ```
    Activate the virtual environment:
    *   On macOS and Linux:
        ```bash
        source venv/bin/activate
        ```
    *   On Windows:
        ```bash
        venv\Scripts\activate
        ```

4.  **Install dependencies**:
    Make sure your virtual environment is activated, then run:
    ```bash
    pip install -r requirements.txt
    ```

5.  **Set Environment Variables**:
    The bot requires two environment variables to be set:

    *   `TELEGRAM_TOKEN`: Your Telegram Bot Token.
        *   To get a Telegram Bot Token, you need to talk to the "BotFather" on Telegram.
        *   1. Open Telegram and search for "BotFather".
        *   2. Start a chat with BotFather by typing `/start`.
        *   3. Create a new bot by typing `/newbot`. Follow the instructions to choose a name and username for your bot.
        *   4. BotFather will then provide you with an API token. This is your `TELEGRAM_TOKEN`.
        *   Set it in your terminal (for the current session) or add it to your shell's configuration file (e.g., `.bashrc`, `.zshrc`) for persistence:
            ```bash
            export TELEGRAM_TOKEN="your_actual_telegram_bot_token"
            ```
            (On Windows, use `set TELEGRAM_TOKEN="your_actual_telegram_bot_token"` for Command Prompt or `$env:TELEGRAM_TOKEN="your_actual_telegram_bot_token"` for PowerShell).

    *   `GEMINI_API_KEY`: Your Google Gemini API Key.
        *   To get a Gemini API Key, you need to go to Google AI Studio (previously known as MakerSuite).
        *   1. Visit [https://aistudio.google.com/](https://aistudio.google.com/).
        *   2. Sign in with your Google account.
        *   3. Create a new API key by clicking "Get API key" or navigating to the API key section.
        *   Set it in your terminal or shell configuration file:
            ```bash
            export GEMINI_API_KEY="your_actual_gemini_api_key"
            ```
            (Use Windows-specific commands as shown above if applicable).
        *   **Note**: If the `GEMINI_API_KEY` is not provided or is invalid, the scam detection functionality will be disabled. The bot will still run and perform language identification.

## Running the Bot

1.  Ensure your virtual environment is activated and the environment variables (`TELEGRAM_TOKEN`, `GEMINI_API_KEY`) are set.
2.  Navigate to the `telegram_bot` directory if you are not already there.
3.  Execute the bot script:
    ```bash
    python bot.py
    ```
4.  The bot will start polling for messages. You should see log output in the console, including a message indicating "Starting bot polling...".

## Available Commands

You can interact with the bot using the following commands in your Telegram chat:

*   `/start` - Displays a welcome message and basic instructions.
*   `/help` - Shows a detailed help message explaining all available commands and their usage.
*   `/analyze [text_to_analyze]` - Analyzes the provided text for potential scams and identifies its language. You can also reply to a message with just `/analyze` to analyze the replied-to message.
    *   Example: `/analyze Check out this amazing free crypto offer!`
*   `/language [text_to_identify]` - Identifies the language of the provided text. You can also reply to a message with just `/language`.
    *   Example: `/language Bonjour le monde`
*   `/feedback [your_feedback_message]` - Allows you to send feedback about the bot to the bot operator (logged).
    *   Example: `/feedback This bot is very helpful for checking suspicious links.`
*   `/privacy` - Displays the bot's privacy policy.
*   `/report [message_content_to_report]` - Manually report a message you believe to be a scam. The report will be logged by the bot operator.
    *   Example: `/report Received a message asking for my login details.`

You can also send any text message directly to the bot. If the Gemini API key is configured, the bot will attempt to analyze it for scams and reply if it's deemed a potential risk or if the analysis is uncertain.

## Logging

The bot outputs logs to the console. This includes information about its operations, received commands, analysis results, and any errors encountered. The log level and format are configured at the beginning of the `bot.py` script using Python's `logging` module. By default, the log level is set to `INFO`.

---

For any issues or contributions, please refer to the repository where this bot is hosted.
