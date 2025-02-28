import os
from sheets_service import GoogleSheetsService
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_sheets_connection():
    """Test the connection to Google Sheets"""
    try:
        # Initialize the service
        service = GoogleSheetsService()
        logger.info("Successfully initialized Google Sheets service")

        # Set the spreadsheet ID and range
        spreadsheet_id = "1iWPhDOwO54ocsc4XdbgJ6ddWe7LBxWG-9oYN0fGWWws"
        range_name = "'Дом Итог'!A1:N"  # Adjust range based on your data

        # Try to fetch data
        data = service.get_sheet_data(spreadsheet_id, range_name)

        if data:
            logger.info(f"Successfully retrieved {len(data)} rows of data")
            # Print the headers
            if len(data) > 0:
                logger.info("Headers: " + ", ".join(data[0]))

                # Print first row of data as example
                if len(data) > 1:
                    logger.info("First row of data: " + ", ".join(str(x) for x in data[1]))
        else:
            logger.warning("No data found in the specified range")

    except Exception as e:
        logger.error(f"Error testing Google Sheets connection: {str(e)}")
        raise

if __name__ == "__main__":
    test_sheets_connection()