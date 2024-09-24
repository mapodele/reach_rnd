import os
import csv
from typing import List, Union
from crewai_tools import BaseTool

class CopySaverTool(BaseTool):
    name: str = "CopySaverTool"
    description: str = (
        "Saves the provided ad copy into a CSV file. "
        "Takes input as a list of lists or tuples where each item contains 'Type' and 'Copy'. "
        "No additional processing is performed, the file is saved directly."
    )
    base_file_path: str = 'crew_io_files'

    def _run(self, input_data: List[Union[List[str], tuple]], persona_number: int = None) -> dict:
        """
        Writes the input data to a CSV file.

        Args:
            input_data (List[Union[List[str], tuple]]): List of items to save, each containing 'Type' and 'Copy'.
            persona_number (int, optional): If provided, saves the file with a persona-specific name.

        Returns:
            dict: Success status and file path if successful, or error message if something went wrong.
        """
        try:
            # Construct the file path based on the persona number (if provided)
            if persona_number is not None:
                file_name = f"ad_copy_persona_{persona_number}.csv"
            else:
                file_name = "copy_items.csv"  # Default file name

            file_path = os.path.join(self.base_file_path, file_name)

            # Ensure the directory exists
            os.makedirs(self.base_file_path, exist_ok=True)

            # Write the input data to CSV
            with open(file_path, 'w', newline='', encoding='utf-8') as file:
                writer = csv.writer(file, quotechar='"', delimiter=',', quoting=csv.QUOTE_ALL)

                # Ensure each item is written as a row in the CSV
                for item in input_data:
                    if len(item) == 2:  # Expecting ['Type', 'Copy']
                        writer.writerow(item)
                    else:
                        return {"error": f"Invalid item format: {item}. Expected exactly 2 elements ('Type', 'Copy')."}

            # Return success with the file path
            return {
                "success": True,
                "message": "Ad copy successfully saved to CSV.",
                "file_path": file_path
            }

        except Exception as e:
            return {
                "error": f"An error occurred while saving the ad copy to CSV: {str(e)}"
            }
