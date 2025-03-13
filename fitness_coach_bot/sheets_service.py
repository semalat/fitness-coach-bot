from google.oauth2.credentials import Credentials
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
import os
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class GoogleSheetsService:
    def __init__(self):
        self.service = None
        self.setup_service()

    def setup_service(self):
        """Initialize the Google Sheets service"""
        try:
            # First check if we have all required credentials
            required_keys = [
                "GOOGLE_TYPE", 
                "GOOGLE_PROJECT_ID", 
                "GOOGLE_PRIVATE_KEY_ID",
                "GOOGLE_PRIVATE_KEY", 
                "GOOGLE_CLIENT_EMAIL", 
                "GOOGLE_CLIENT_ID",
                "GOOGLE_CLIENT_X509_CERT_URL"
            ]
            
            missing_keys = [key for key in required_keys if not os.getenv(key)]
            if missing_keys:
                logger.error(f"Missing required Google credentials: {', '.join(missing_keys)}")
                self.service = None
                return
                
            # Get private key and handle potential None value
            private_key = os.getenv("GOOGLE_PRIVATE_KEY")
            if not private_key:
                logger.error("GOOGLE_PRIVATE_KEY is empty or not set")
                self.service = None
                return
                
            # Format the private key properly
            private_key = private_key.replace('\\n', '\n')
            
            # Create credentials
            credentials = service_account.Credentials.from_service_account_info(
                {
                    "type": os.getenv("GOOGLE_TYPE", "service_account"),
                    "project_id": os.getenv("GOOGLE_PROJECT_ID", ""),
                    "private_key_id": os.getenv("GOOGLE_PRIVATE_KEY_ID", ""),
                    "private_key": private_key,
                    "client_email": os.getenv("GOOGLE_CLIENT_EMAIL", ""),
                    "client_id": os.getenv("GOOGLE_CLIENT_ID", ""),
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token",
                    "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
                    "client_x509_cert_url": os.getenv("GOOGLE_CLIENT_X509_CERT_URL", "")
                },
                scopes=['https://www.googleapis.com/auth/spreadsheets.readonly']
            )
            
            # Build the service
            self.service = build('sheets', 'v4', credentials=credentials)
            logger.info("Google Sheets service initialized successfully")
        except Exception as e:
            logger.error(f"Error setting up Google Sheets service: {str(e)}")
            self.service = None

    def get_sheet_data(self, spreadsheet_id, range_name):
        """
        Fetch data from a specific Google Sheet
        
        Args:
            spreadsheet_id (str): The ID of the spreadsheet
            range_name (str): The A1 notation of the range to retrieve
            
        Returns:
            list: The values from the specified range or empty list if error
        """
        if not self.service:
            logger.warning("Google Sheets service not available")
            return []
            
        try:
            result = self.service.spreadsheets().values().get(
                spreadsheetId=spreadsheet_id,
                range=range_name
            ).execute()
            
            values = result.get('values', [])
            if not values:
                logger.warning('No data found in the specified range')
                return []
                
            logger.info(f"Successfully retrieved {len(values)} rows from Google Sheet")
            return values
            
        except HttpError as e:
            logger.error(f"Error fetching data from Google Sheet: {str(e)}")
            return []
        except Exception as e:
            logger.error(f"Unexpected error accessing Google Sheets: {str(e)}")
            return []
