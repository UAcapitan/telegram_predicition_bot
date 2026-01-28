# Telegram Prediction Bot

Simple Telegram bot built with Aiogram. It sends random prediction images with clickable buttons and supports admin broadcasts and link updates.

## Features
- Random prediction image from `data/images`
- Inline buttons for affiliate + contact link
- Admin broadcast command
- Admin commands to update links
- Language selection with `/lng` (translations in `data/translations.json`)

## Setup
1. Create a `.env` file from `.env.example` and set your bot token, admin IDs, and `DATABASE_URL`.
2. Create the PostgreSQL database (example):

```bash
createdb -U postgres tg_prediction_bot
```

3. Add prediction images to `data/images` (jpg/png/gif).
4. Install dependencies:

```bash
pip install -r requirements.txt
```

## Run
```bash
python main.py
```

## Commands
- `/start` subscribe the user
- `/predict` send random prediction image
- `/lng` change language
- `/broadcast your message` send to all subscribers (admin only)
- `/setlink https://your-link` update affiliate link (admin only)
- `/setcontact https://t.me/your_contact` update contact link (admin only)
