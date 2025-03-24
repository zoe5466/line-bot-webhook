# LINE Card Bot

A LINE Bot that processes user messages with specific keywords, handles image uploads, and stores data in Google Sheets and Google Drive.

## Features

- Detects specific keywords in messages
- Processes and uploads images to Google Drive
- Records data in Google Sheets
- Responds to users with confirmation messages

## Requirements

- Python 3.8 or higher
- LINE Messaging API Channel
- Google Cloud project with Sheets and Drive API enabled
- Google Service Account with appropriate permissions

## Setup

### 1. Clone the repository

```bash
git clone https://github.com/your-username/line-card-bot.git
cd line-card-bot
```

### 2. Set up a virtual environment

```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 3. Configure environment variables

Copy the `.env.example` file to `.env` and fill in your credentials:

```bash
cp .env.example .env
```

Then edit the `.env` file with your actual credentials:

```
LINE_CHANNEL_ACCESS_TOKEN=your_line_channel_access_token
LINE_CHANNEL_SECRET=your_line_channel_secret
LINE_BOT_SPREADSHEET_ID=your_google_spreadsheet_id
LINE_BOT_PHOTO_FOLDER_ID=your_google_drive_folder_id
GOOGLE_CREDENTIALS_PATH=path/to/your-credentials.json
```

### 4. Google API Setup

1. Create a Google Cloud project
2. Enable Google Sheets API and Google Drive API
3. Create a service account with appropriate permissions
4. Download the service account key as JSON
5. Place the JSON file in a secure location and update `GOOGLE_CREDENTIALS_PATH` in your `.env` file

### 5. LINE Bot Setup

1. Create a LINE Messaging API channel in the [LINE Developers Console](https://developers.line.biz/console/)
2. Configure the webhook URL to point to your server's `/callback` endpoint
3. Enable the necessary messaging permissions
4. Copy the Channel Secret and Channel Access Token to your `.env` file

## Running the Application

### Local Development

```bash
python app.py
```

The server will start on port 8000 by default.

### Production Deployment

This application is ready for deployment on platforms like Heroku.

#### Heroku Deployment

```bash
git push heroku main
```

Make sure to set the environment variables in your Heroku dashboard or using the Heroku CLI:

```bash
heroku config:set LINE_CHANNEL_ACCESS_TOKEN=your_line_channel_access_token
heroku config:set LINE_CHANNEL_SECRET=your_line_channel_secret
# Set other variables...
```

For platforms that don't support file storage, you can use the Base64-encoded credentials approach:

```bash
cat your-credentials.json | base64 > credentials.base64
```

Then set the `GOOGLE_CREDENTIALS_BASE64` environment variable with the contents of `credentials.base64`.

## Usage

1. Add your LINE Bot as a friend using its QR code
2. Send a message containing one of the configured keywords (like "@開卡")
3. The bot will respond and confirm the text is recorded
4. Within 2 minutes, send an image, and the bot will upload it and provide a link

## Customization

- Modify the list of keywords in the `keywords` list in `app.py`
- Adjust the keyword valid duration by changing `keyword_valid_duration` (in seconds)
- Customize the response messages in the `send_reply` method calls

## License

[MIT License](LICENSE)

## Contributing

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add some amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request
