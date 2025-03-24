import os
from dotenv import load_dotenv
import json
import logging
import requests
import time
import base64
from datetime import datetime
from flask import Flask, request, abort
from linebot.v3.messaging import (
    Configuration,
    ApiClient,
    MessagingApi,
    MessagingApiBlob,
    ReplyMessageRequest,
    TextMessage
)
from linebot.v3.webhook import WebhookHandler, MessageEvent
from linebot.exceptions import InvalidSignatureError
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
import gspread
import filetype
from io import BytesIO
from logging_config import setup_logging

# Setup logging
logger = setup_logging()

load_dotenv()  # Load .env file

class LineBot:
    
    def __init__(self):
        self.load_config()
        self.setup_line_api()
        self.setup_google_apis()
        self.keywords = ["@幫開卡", "@開卡", "@營運開卡", "@專員開卡","＠幫開卡", "＠開卡", "＠卡卡", "@卡", "@卡卡", "＠卡"]  # Different formats
        self.user_keyword_timestamp = {}
        self.keyword_valid_duration = 120  # Keyword validity duration (seconds)

    def load_config(self):
        """Load configuration"""
        self.config = {
            "LINE_CHANNEL_ACCESS_TOKEN": os.getenv("LINE_CHANNEL_ACCESS_TOKEN"),
            "LINE_CHANNEL_SECRET": os.getenv("LINE_CHANNEL_SECRET"),
            "LINE_BOT_SPREADSHEET_ID": os.getenv("LINE_BOT_SPREADSHEET_ID"),
            "LINE_BOT_PHOTO_FOLDER_ID": os.getenv("LINE_BOT_PHOTO_FOLDER_ID")
        }
        missing_vars = [k for k, v in self.config.items() if not v]
        if missing_vars:
            logger.error(f"[CONFIG] Missing environment variables: {', '.join(missing_vars)}")
            raise ValueError(f"Missing environment variables: {', '.join(missing_vars)}")
        logger.info("[CONFIG] Configuration loaded successfully")

    def setup_line_api(self):
        """Setup LINE API"""
        self.configuration = Configuration(access_token=self.config["LINE_CHANNEL_ACCESS_TOKEN"])
        self.api_client = ApiClient(self.configuration)
        self.messaging_api = MessagingApi(self.api_client)
        self.messaging_api_blob = MessagingApiBlob(self.api_client)
        self.handler = WebhookHandler(self.config["LINE_CHANNEL_SECRET"])

        # Add message event handler
        @self.handler.add(MessageEvent)
        def handle_message(event):
            self.handle_message(event)

        logger.info("[LINE API] Successfully initialized")

    def setup_google_apis(self):
        """Setup Google APIs"""
        scopes = [
            'https://www.googleapis.com/auth/spreadsheets',
            'https://www.googleapis.com/auth/drive'
        ]
        try:
            base64_credentials = os.getenv("GOOGLE_CREDENTIALS_BASE64")
            if base64_credentials:
                try:
                    credentials_json = base64.b64decode(base64_credentials).decode('utf-8')
                    credentials_dict = json.loads(credentials_json)
                    self.creds = Credentials.from_service_account_info(credentials_dict, scopes=scopes)
                except Exception as e:
                    logger.error(f"[GOOGLE APIs] Failed to decode Base64 credentials: {e}")
                    raise ValueError("Invalid GOOGLE_CREDENTIALS_BASE64 format")
            else:
                credentials_path = os.getenv("GOOGLE_CREDENTIALS_PATH")
                if not credentials_path or not os.path.exists(credentials_path):
                    raise FileNotFoundError("Google credentials file is missing.")
                self.creds = Credentials.from_service_account_file(credentials_path, scopes=scopes)

            self.drive_service = build('drive', 'v3', credentials=self.creds)
            self.gc = gspread.authorize(self.creds)
            self.sheet = self.gc.open_by_key(self.config["LINE_BOT_SPREADSHEET_ID"]).sheet1
            logger.info("[GOOGLE APIs] Successfully initialized")
        except Exception as e:
            logger.error(f"[GOOGLE APIs] Failed to initialize: {e}")
            raise

    def record_to_sheet(self, user_name: str, content_type: str, content: str):
        """Record to Google Sheets"""
        try:
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            row = [timestamp, user_name, content_type, content]
            self.sheet.append_row(row)
            logger.info(f"[SHEET] Recorded {content_type} from {user_name}")
        except Exception as e:
            logger.error(f"[SHEET] Failed to record to sheet: {e}")
            raise

    def upload_to_drive(self, image_content: bytes, user_name: str) -> str:
        """Upload image to Google Drive and return image URL"""
        try:
            # Verify service is correctly initialized
            if not self.drive_service:
                raise Exception("Drive service not properly initialized")

            # Verify folder exists
            try:
                folder = self.drive_service.files().get(
                    fileId=self.config["LINE_BOT_PHOTO_FOLDER_ID"]
                ).execute()
                logger.info(f"[DRIVE] Folder exists: {folder.get('name')}")
            except Exception as folder_error:
                logger.error(f"[DRIVE] Failed to access folder: {folder_error}")
                raise Exception(f"Cannot access folder: {folder_error}")

            # Prepare file metadata
            kind_of_file = filetype.guess(image_content)
            file_extension = kind_of_file.extension
            file_mime_type = kind_of_file.mime
            file_name = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{user_name}.{file_extension}"
            file_metadata = {
                'name': file_name,
                'parents': [self.config["LINE_BOT_PHOTO_FOLDER_ID"]],
                'mimeType': file_mime_type
            }
            media = MediaIoBaseUpload(BytesIO(image_content), mimetype=file_mime_type)

            # Upload file
            file = self.drive_service.files().create(
                body=file_metadata, media_body=media, fields='id, webViewLink'
            ).execute()

            # Set sharing permissions
            self.drive_service.permissions().create(
                fileId=file['id'], body={'role': 'reader', 'type': 'anyone'}
            ).execute()

            # Return successful upload link
            web_view_link = file.get('webViewLink')
            if not web_view_link:
                raise ValueError("Failed to retrieve the webViewLink from the uploaded file.")

            logger.info(f"[DRIVE] Uploaded successfully: {file_name} (Link: {web_view_link})")
            return web_view_link

        except Exception as e:
            error_message = f"[DRIVE] Failed to upload image to Google Drive. Error: {e}"
            if "insufficientFilePermissions" in str(e):
                error_message += " (Service account lacks necessary permissions)"
            elif "notFound" in str(e):
                error_message += " (Folder ID not found or inaccessible)"
            logger.error(error_message)
            raise

    def get_image_content(self, message_id: str) -> bytes:
        """Get image content"""
        try:
            response = self.messaging_api_blob.get_message_content(message_id)
            if not response or not hasattr(response, 'content'):
                raise ValueError("Failed to get valid image content from LINE API.")

            image_content = response.content
            logger.info(f"[IMAGE] Downloaded content for message ID {message_id}")
            return image_content
        except requests.exceptions.RequestException as e:
            logger.error(f"[IMAGE] Failed to get image content: {e}")
            raise

    def get_user_name(self, user_id: str) -> str:
        """Try to get user name from LINE API, use user_id if failed"""
        try:
            profile = self.messaging_api.get_profile(user_id)
            return profile.display_name
        except Exception as e:
            logger.error(f"[PROFILE] Failed to get user profile: {e}")
            return f"User-{user_id[:6]}"  # Fall back to part of userId as substitute name

    def send_reply(self, reply_token: str, message: str):
        """Send reply message"""
        try:
            self.messaging_api.reply_message(
                ReplyMessageRequest(reply_token=reply_token, messages=[TextMessage(text=message)])
            )
            logger.info(f"[REPLY] Sent reply: {message}")
        except Exception as e:
            logger.error(f"[REPLY] Failed to send reply: {e}")

    def handle_message(self, event):
        """Handle message"""
        try:
            user_id = event.source.user_id
            reply_token = event.reply_token
            message_type = event.message.type
            user_name = self.get_user_name(user_id)

            if message_type == "text":
                message_text = event.message.text
                matched_keyword = next((kw for kw in self.keywords if kw in message_text), None)
                if matched_keyword:
                    clean_message = message_text.replace(matched_keyword, "").strip()
                    self.user_keyword_timestamp[user_id] = time.time()
                    self.record_to_sheet(user_name, "關鍵字", clean_message)
                    self.send_reply(reply_token, f"已記錄: {clean_message}")

            elif message_type == "image":
                if user_id in self.user_keyword_timestamp:
                    current_time = time.time()
                    if current_time - self.user_keyword_timestamp[user_id] <= self.keyword_valid_duration:
                        try:
                            image_content = self.get_image_content(event.message.id)
                            drive_url = self.upload_to_drive(image_content, user_name)
                            self.record_to_sheet(user_name, "圖片", drive_url)
                            self.send_reply(reply_token, f"已紀錄您的圖片: {drive_url}")
                        except Exception as e:
                            logger.error(f"[IMAGE] Error handling image: {e}")
                            self.send_reply(reply_token, "圖片上傳失敗，請稍後再試")
                else:
                    logger.info(f"[IGNORE] Ignored image from user {user_id} without valid keyword.")

        except Exception as e:
            logger.error(f"[MESSAGE] Error handling message: {e}")
            self.send_reply(reply_token, "處理訊息時發生錯誤，請稍後再試")

    def handle_webhook(self, body, signature):
        """Handle Webhook request"""
        try:
            self.handler.handle(body, signature)
        except InvalidSignatureError:
            logger.error("[WEBHOOK] Invalid signature detected.")
            raise
        except Exception as e:
            logger.error(f"[WEBHOOK] Error handling webhook: {e}")
            raise

# Flask Web Application
app = Flask(__name__)
line_bot = LineBot()

@app.route("/callback", methods=["POST"])
def callback():
    """Handle Webhook requests from LINE"""
    signature = request.headers.get("X-Line-Signature")
    body = request.get_data(as_text=True)
    try:
        line_bot.handle_webhook(body, signature)
        return "OK", 200
    except InvalidSignatureError:
        logger.error("[WEBHOOK] Invalid signature detected.")
        return "Invalid signature", 400
    except Exception as e:
        logger.error(f"[WEBHOOK] Error handling webhook: {e}", exc_info=True)
        return f"Internal server error: {str(e)}", 500

@app.route("/", methods=["GET"])
def health_check():
    """Simple health check endpoint"""
    return "LINE Bot server is running!", 200

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    app.run(host="0.0.0.0", port=port, debug=False)
