# Test Bot Setup and Usage

This document explains how to set up and use the test bot for the Fitness Coach Bot project.

## Setup

1. **Create a test bot on Telegram:**
   - Open Telegram and search for the BotFather (@BotFather)
   - Use the `/newbot` command to create a new bot
   - Choose a name for your bot (e.g., "Fitness Coach Test Bot")
   - Choose a username for your bot (e.g., "fitness_coach_test_bot")
   - BotFather will provide you with a token. Copy this token.

2. **Configure the test environment:**
   - Open the `.env.test` file in the `fitness_coach_bot` directory
   - Replace `your_test_telegram_bot_token_here` with the token you received from BotFather
   - Save the file

## Running the Test Bot

There are two ways to run the test bot:

### Option 1: Full Bot with Google Sheets Integration

If you have Google Sheets credentials, add them to your `.env.test` file:
```
GOOGLE_PRIVATE_KEY=your_private_key_here
GOOGLE_CLIENT_EMAIL=your_client_email_here
GOOGLE_SHEET_ID=your_sheet_id_here
```

Then run:
```bash
cd fitness-coach-bot/fitness_coach_bot
python3 run_test_bot.py
```

### Option 2: Test Bot with Mock Google Sheets (Recommended for Testing)

This option uses a mock Google Sheets service, which is ideal for testing without needing real credentials:
```bash
cd fitness-coach-bot/fitness_coach_bot
python3 run_test_bot_no_sheets.py
```

### Checking the Bot Status

To check if your test bot is running:
```bash
cd fitness-coach-bot/fitness_coach_bot
python3 check_test_bot.py
```

## Interacting with the Bot

- Open Telegram and search for your test bot using the username you created
- Start a conversation and test your changes

## Testing Workflow

1. Make changes to the codebase
2. Run the test bot to see if your changes work as expected
3. If everything works correctly, commit your changes to GitHub and deploy the production bot
4. If there are issues, fix them and test again

## Important Notes

- The test bot uses the same code and files as the production bot, but with a different token
- The mock Google Sheets version is useful for testing bot functionality without real credentials
- Make sure you're running the test bot and not the production bot when testing changes
- Remember to stop the test bot when you're done testing
- The test bot uses the same database as the production bot by default. If you need separate data, modify the database configuration in the test environment.

## Troubleshooting

- If the test bot doesn't start, check that you've entered the correct token in the `.env.test` file
- Make sure you don't have another instance of the bot running (check for lock files in `/tmp`)
- Check the bot's logs for any error messages
- If you're having issues with Google Sheets authentication, try the mock version instead 