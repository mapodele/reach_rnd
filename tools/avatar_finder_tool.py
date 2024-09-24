import pandas as pd
from crewai_tools import BaseTool

class AvatarFinderTool(BaseTool):
    name: str = "AvatarFinderTool"
    description: str = "Fetches 50 random rows from the avatar_images_db.csv file and returns them as a dictionary."

    def _run(self, argument: str) -> dict:
        # Read the CSV file
        df = pd.read_csv('crew_io_files/avatar_images_db.csv')
        
        # Get 10 random rows
        random_rows = df.sample(n=50)
        
        # Convert the random rows to a dictionary
        result = random_rows.to_dict(orient='records')
        
        return result