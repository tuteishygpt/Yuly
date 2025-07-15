import unittest
from unittest.mock import patch, MagicMock, AsyncMock
import os
import sys

# Adjust the Python path to include the parent directory (telegram_bot)
# This allows a direct import of 'bot' when running tests from the 'telegram_bot' directory
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Now we can import from bot
from bot import identify_language, interpret_gemini_response, get_text_from_update, language_command, send_reply

# Import LangDetectException for mocking
from langdetect import LangDetectException

class TestBotFunctions(unittest.TestCase):

    def test_identify_language(self):
        self.assertEqual(identify_language("Hello, how are you?"), ('en', 'English'))
        self.assertEqual(identify_language("Hola, como estas?"), ('es', 'Spanish'))
        self.assertEqual(identify_language("Bonjour"), ('fr', 'French'))
        self.assertEqual(identify_language("ok"), (None, None)) # Too short / ambiguous
        self.assertEqual(identify_language("cv"), (None, None)) # Too short / ambiguous
        self.assertEqual(identify_language("12345"), (None, None)) # Numbers / No real language
        self.assertEqual(identify_language(""), (None, None)) # Empty string
        self.assertEqual(identify_language(None),(None,None)) # None input

        # Test case where pycountry might not find a name (e.g., 'fy' is Frisian)
        # Assuming 'fy' is detected and pycountry has 'Frisian'
        # If langdetect detects 'fy' for "Wat is dyn namme?", pycountry should find 'Frisian'
        # This depends on langdetect's model and pycountry's database
        # For a more robust test, we could mock pycountry.languages.get if needed
        # For now, let's test a common one that should be present
        self.assertEqual(identify_language("Wie geht es Ihnen?"), ('de', 'German'))


    @patch('bot.detect')
    def test_identify_language_langdetect_exception(self, mock_detect):
        mock_detect.side_effect = LangDetectException(code=0, message="Mocked LangDetect Error")
        self.assertEqual(identify_language("This will cause an exception"), (None, None))

    def test_interpret_gemini_response(self):
        self.assertEqual(interpret_gemini_response("Scam"), "Scam")
        self.assertEqual(interpret_gemini_response("Likely Scam"), "Likely Scam")
        self.assertEqual(interpret_gemini_response("Safe"), "Safe")
        self.assertEqual(interpret_gemini_response("Uncertain"), "Uncertain")

        # Test with surrounding text
        self.assertEqual(interpret_gemini_response("This message is a Scam."), "Scam")
        self.assertEqual(interpret_gemini_response("I think this is Likely Scam, be careful."), "Likely Scam")
        self.assertEqual(interpret_gemini_response("The message seems Safe to me."), "Safe")
        self.assertEqual(interpret_gemini_response("I'm Uncertain about this one."), "Uncertain")

        # Test with error messages from detect_scam
        self.assertEqual(interpret_gemini_response("Error contacting AI model"), "Uncertain (due to error or missing input)")
        self.assertEqual(interpret_gemini_response("Error: No content from AI model"), "Uncertain (due to error or missing input)")
        self.assertEqual(interpret_gemini_response("Uncertain - API key missing"), "Uncertain (due to error or missing input)")
        self.assertEqual(interpret_gemini_response("Uncertain - No text provided"), "Uncertain (due to error or missing input)")


        # Test with completely unrelated text
        self.assertEqual(interpret_gemini_response("This is a normal message."), "Uncertain") # Default for unrelated
        self.assertEqual(interpret_gemini_response("Malicious"), "Uncertain") # Contains 'Malicious' but not a verdict

    def test_get_text_from_update(self):
        # Mock Update and Message objects
        mock_update = MagicMock()

        # Test case 1: Command with text
        mock_update.message = MagicMock()
        mock_update.message.text = "/command some text here"
        mock_update.message.reply_to_message = None
        self.assertEqual(get_text_from_update(mock_update), "some text here")

        # Test case 2: Command with text and extra spaces
        mock_update.message.text = "/command   some more text  "
        mock_update.message.reply_to_message = None
        self.assertEqual(get_text_from_update(mock_update), "some more text")

        # Test case 3: Reply to a message
        mock_update.message.text = "/command" # Command itself
        mock_update.message.reply_to_message = MagicMock()
        mock_update.message.reply_to_message.text = "this is the replied text"
        self.assertEqual(get_text_from_update(mock_update), "this is the replied text")

        # Test case 4: Command with no text and not a reply
        mock_update.message.text = "/command"
        mock_update.message.reply_to_message = None
        self.assertIsNone(get_text_from_update(mock_update))
        
        # Test case 5: Message is None
        mock_update.message = None
        self.assertIsNone(get_text_from_update(mock_update))

        # Test case 6: Update is None
        self.assertIsNone(get_text_from_update(None))

        # Test case 7: Forwarded message (text directly in update.message.text, no command)
        mock_update.message = MagicMock()
        mock_update.message.text = "This is a forwarded message."
        mock_update.message.reply_to_message = None
        # This scenario is tricky for get_text_from_update as it's designed for command args.
        # The current implementation might return it or None based on whether it looks like a command.
        # If it doesn't start with '/', it will be returned.
        self.assertEqual(get_text_from_update(mock_update), "This is a forwarded message.")

        # Test case 8: Command with no text but with reply_to_message that has no text
        mock_update.message.text = "/command"
        mock_update.message.reply_to_message = MagicMock()
        mock_update.message.reply_to_message.text = None
        self.assertIsNone(get_text_from_update(mock_update))
        
        # Test case 9: Command with text, but reply_to_message also exists (command text should take precedence)
        mock_update.message.text = "/command some text here"
        mock_update.message.reply_to_message = MagicMock()
        mock_update.message.reply_to_message.text = "this is the replied text"
        self.assertEqual(get_text_from_update(mock_update), "some text here")


class TestBotCommands(unittest.IsolatedAsyncioTestCase):

    @patch('bot.identify_language')
    @patch('bot.send_reply', new_callable=AsyncMock) # Mocking the async send_reply
    async def test_language_command_with_text(self, mock_send_reply, mock_identify_language):
        mock_update = MagicMock()
        mock_context = MagicMock()

        # Configure mock_update for get_text_from_update
        mock_update.message = MagicMock()
        mock_update.message.text = "/language Hello world"
        mock_update.message.reply_to_message = None
        
        # Configure mock for identify_language
        mock_identify_language.return_value = ('en', 'English')

        await language_command(mock_update, mock_context)

        mock_identify_language.assert_called_once_with("Hello world")
        mock_send_reply.assert_called_once_with(mock_update, "Detected Language: English (en)")

    @patch('bot.identify_language')
    @patch('bot.send_reply', new_callable=AsyncMock)
    async def test_language_command_no_text(self, mock_send_reply, mock_identify_language):
        mock_update = MagicMock()
        mock_context = MagicMock()

        mock_update.message = MagicMock()
        mock_update.message.text = "/language" # No text provided after command
        mock_update.message.reply_to_message = None

        await language_command(mock_update, mock_context)

        mock_identify_language.assert_not_called() # Should not be called if no text
        mock_send_reply.assert_called_once_with(mock_update, "Please provide text for language identification, either after the command or by replying to a message. Example: `/language Bonjour le monde`")

    @patch('bot.identify_language')
    @patch('bot.send_reply', new_callable=AsyncMock)
    async def test_language_command_detection_fails(self, mock_send_reply, mock_identify_language):
        mock_update = MagicMock()
        mock_context = MagicMock()

        mock_update.message = MagicMock()
        mock_update.message.text = "/language ---"
        mock_update.message.reply_to_message = None
        
        mock_identify_language.return_value = (None, None) # Simulate detection failure

        await language_command(mock_update, mock_context)
        
        mock_identify_language.assert_called_once_with("---")
        mock_send_reply.assert_called_once_with(mock_update, "Could not detect language.")


if __name__ == '__main__':
    unittest.main()

# To run tests:
# 1. Navigate to the project root directory (the one containing the `telegram_bot` folder).
# 2. Run: python -m unittest telegram_bot/tests/test_bot.py
# OR
# 1. Navigate to the `telegram_bot` directory.
# 2. Run: python -m unittest tests.test_bot
# Make sure telegram_bot/tests/__init__.py and telegram_bot/__init__.py exist.
# Also ensure bot.py and other necessary files are in the telegram_bot directory.
# The sys.path modification at the top of this file helps with imports if running the test file directly for debugging.
# For organized test discovery (python -m unittest discover), ensure your project structure and __init__.py files are correct.
# e.g., from project root: python -m unittest discover -s telegram_bot
# or from telegram_bot dir: python -m unittest discover -s tests
#
# If using `python -m unittest telegram_bot.tests.test_bot` from root,
# then the imports in test_bot.py should be like `from ..bot import identify_language`
# The current sys.path hack is to make `python telegram_bot/tests/test_bot.py` work directly too.
# A more robust way for imports is to ensure the package structure is correctly installed or PYTHONPATH is set.
# For this exercise, the sys.path modification is a pragmatic choice for direct execution and simple discovery.
# The provided `python -m unittest telegram_bot/tests/test_bot.py` (from root) should work with the current setup.
# Or `python -m unittest tests.test_bot` (from telegram_bot dir).
# The path adjustment is primarily for `python telegram_bot/tests/test_bot.py` from root.
# If running with `python -m unittest tests.test_bot` from `telegram_bot` dir, the path hack isn't strictly needed
# if `telegram_bot` is treated as the top-level package for that command.
# However, `from bot import ...` requires `telegram_bot` to be in sys.path.
# The current setup with sys.path.insert(0, ...) targets running from the parent of `telegram_bot` (project root)
# or making `telegram_bot.tests.test_bot` directly runnable.
# The most standard way to run tests if `telegram_bot` is a package is:
# From parent_of_telegram_bot: `python -m unittest telegram_bot.tests.test_bot`
# In this case, imports in `test_bot.py` should be `from ..bot import ...`
#
# Given the current structure and the `sys.path.insert` for `bot.py` itself (in the test file),
# running `python -m unittest telegram_bot.tests.test_bot` from the project root directory
# is the most consistent way to ensure `from bot import ...` works as intended by the path manipulation.
#
# The instructions in the file itself are:
# python -m unittest telegram_bot/tests/test_bot.py (from project root)
# OR
# python -m unittest tests.test_bot (from telegram_bot directory)
# Both should work with the `sys.path.insert`
#
# Final check:
# Project Root/
#   telegram_bot/
#     __init__.py
#     bot.py
#     tests/
#       __init__.py
#       test_bot.py
#
# Command from Project Root: `python -m unittest telegram_bot.tests.test_bot`
# This makes `telegram_bot` a package, so `from bot import ...` in `test_bot.py` should be `from ..bot import ...`
#
# Command from Project Root: `python telegram_bot/tests/test_bot.py`
# This runs the file directly. The `sys.path.insert` makes `from bot import ...` work.
#
# Command from Project Root: `python -m unittest discover -s telegram_bot`
# This should work if `from bot import ...` is changed to `from ..bot import ...` or if `telegram_bot` itself is added to PYTHONPATH.
#
# Let's stick to the provided instructions for this environment:
# `python -m unittest telegram_bot/tests/test_bot.py` from project root.
# The `sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))`
# adds `telegram_bot` to the path, so `from bot import ...` works.
# This is a common pattern for making test files runnable directly while also being discoverable.
#
# To make `python -m unittest telegram_bot.tests.test_bot` (from root) work without path hacks,
# the test file imports would need to be relative: `from ..bot import identify_language`.
# I will keep the current path hack as it's simpler for this context and allows direct execution.I have created the `telegram_bot/tests/test_bot.py` file with the unit tests as described in the previous turn.
# 
# Here's a summary of what's included in `test_bot.py`:
# 
# 1.  **Setup**:
#     *   Imports `unittest`, `patch`, `MagicMock`, `AsyncMock` from `unittest.mock`.
#     *   Includes `sys.path.insert` to allow `from bot import ...` to work when running the test file, assuming `bot.py` is in the parent directory of `tests/`.
#     *   Imports the necessary functions (`identify_language`, `interpret_gemini_response`, `get_text_from_update`, `language_command`, `send_reply`) and `LangDetectException`.
# 
# 2.  **`TestBotFunctions(unittest.TestCase)`**:
#     *   **`test_identify_language`**:
#         *   Tests with English, Spanish, French text.
#         *   Tests with short/ambiguous text ("ok", "cv"), empty string, None, and numeric input, expecting `(None, None)`.
#         *   Includes a test for German.
#     *   **`test_identify_language_langdetect_exception`**:
#         *   Mocks `langdetect.detect` to raise `LangDetectException`.
#         *   Asserts that `identify_language` returns `(None, None)`.
#     *   **`test_interpret_gemini_response`**:
#         *   Tests exact valid verdicts ("Scam", "Likely Scam", "Safe", "Uncertain").
#         *   Tests verdicts with surrounding text.
#         *   Tests error messages from `detect_scam` (e.g., "Error contacting AI model"), expecting "Uncertain (due to error or missing input)".
#         *   Tests unrelated text, expecting "Uncertain".
#     *   **`test_get_text_from_update`**:
#         *   Uses `MagicMock` to create mock `Update` and `Message` objects.
#         *   Tests various scenarios:
#             *   Command with text (`/command some text`).
#             *   Command with text and extra spaces.
#             *   Command replying to a message.
#             *   Command with no text and not a reply.
#             *   `update.message` being `None`.
#             *   `update` itself being `None`.
#             *   Forwarded message text.
#             *   Command with no text but replying to a message with no text.
#             *   Command with text taking precedence over a replied-to message.
# 
# 3.  **`TestBotCommands(unittest.IsolatedAsyncioTestCase)`**:
#     *   Uses `IsolatedAsyncioTestCase` for async command handlers.
#     *   **`test_language_command_with_text`**:
#         *   Mocks `identify_language` and `send_reply` (using `AsyncMock`).
#         *   Creates mock `Update` and `Context` objects.
#         *   Simulates a `/language Hello world` command.
#         *   Asserts `identify_language` is called with "Hello world".
#         *   Asserts `send_reply` is called with the expected formatted string "Detected Language: English (en)".
#     *   **`test_language_command_no_text`**:
#         *   Simulates `/language` with no text.
#         *   Asserts `identify_language` is not called.
#         *   Asserts `send_reply` is called with the prompt to provide text.
#     *   **`test_language_command_detection_fails`**:
#         *   Mocks `identify_language` to return `(None, None)`.
#         *   Asserts `send_reply` is called with "Could not detect language."

# ----------------------------
# Additional Notes (ignored by test runner)
#
# 4.  **Running Tests**:
#     *   Includes an `if __name__ == '__main__': unittest.main()` block.
#     *   Extensive comments are added at the end of the file explaining various
#         ways to run the tests and considerations about Python's import system
#         and path manipulation. Run `python -m unittest telegram_bot/tests/test_bot.py`
#         from the project root for consistency.
#
# This section originally included an explanatory summary of the test file.
