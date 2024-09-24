import pandas as pd
import csv
import os
from typing import ClassVar
from crewai_tools import BaseTool

class CopyReaderTool(BaseTool):
    name: str = "CopyReaderTool"
    description: str = (
        "Reads a CSV file for a specific persona, calculates the length of each copy, "
        "and returns the lines that exceed the character limits along with the difference "
        "in characters and words, formatted with labels for each metric."
    )
    base_file_path: ClassVar[str] = 'crew_io_files'

    def _run(self, persona_number: int = None) -> list:
        try:
            # Construct the file path based on the persona number
            if persona_number is not None:
                file_name = f"ad_copy_persona_{persona_number}.csv"
            else:
                file_name = "copy_items.csv"  # Default file name for backwards compatibility
            
            file_path = os.path.join(self.base_file_path, file_name)

            # Check if the file exists
            if not os.path.exists(file_path):
                return {"error": f"File not found: {file_path}"}

            # Read the CSV file
            with open(file_path, 'r', newline='', encoding='utf-8') as file:
                csv_reader = csv.reader(file, quotechar='"', delimiter=',', quoting=csv.QUOTE_ALL, skipinitialspace=True)
                data = list(csv_reader)

            # Convert the data to a Pandas DataFrame
            df = pd.DataFrame(data, columns=['Type', 'Copy'])

            # Calculate the length of each copy item
            df['Length'] = df['Copy'].apply(len)

            # Define character limits for different types
            limits = {
                'Headline': 30,
                'Description': 90,
                'Long Description': 90
            }

            # Identify rows where the copy exceeds the limits and calculate differences
            df['ExceedsLimit'] = df.apply(
                lambda row: row['Length'] > limits.get(row['Type'], float('inf')), axis=1
            )
            df['CharDiff'] = df.apply(
                lambda row: row['Length'] - limits.get(row['Type'], 0) if row['ExceedsLimit'] else 0, axis=1
            )
            df['WordDiff'] = (df['CharDiff'] / 5).apply(round)  # Assuming average word length of 5 characters

            # Filter rows that exceed the limit
            offending_rows = df[df['ExceedsLimit']]

            # Format the result with labels for each metric
            result = []
            for _, row in offending_rows.iterrows():
                formatted_row = (
                    row['Type'],
                    row['Copy'],
                    f"Length:{row['Length']}",
                    f"Characters to remove:{row['CharDiff']}",
                    f"Words to remove:{row['WordDiff']}"
                )
                result.append(formatted_row)

            return result

        except Exception as e:
            return {"error": f"An error occurred: {str(e)}"}