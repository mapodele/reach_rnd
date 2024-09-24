from crewai_tools import BaseTool
from pydantic import Field
from typing import Any, List, Dict
import os
import pandas as pd

class ImageAnalysisTool(BaseTool):
    name: str = "ImageAnalysisTool"
    description: str = (
        "Processes images without descriptions one by one from a CSV file, provides image data to an agent for analysis, "
        "updates the CSV with the agent's description, and moves to the next image automatically."
    )
    base_file_path: str = Field(default="crew_io_files")
    csv_file: str = Field(default="images_metadata.csv")
    file_path: str = Field(default="")
    current_index: int = Field(default=0)
    df: Any = Field(default=None)
    last_filename: str = Field(default="")

    def __init__(self, **data):
        super().__init__(**data)
        self.file_path = os.path.join(self.base_file_path, self.csv_file)

    def _load_csv(self) -> pd.DataFrame:
        if not os.path.exists(self.file_path):
            return pd.DataFrame(columns=['filename', 'file_path', 'width', 'height', 'format', 'dominant_color', 'description'])
        df = pd.read_csv(self.file_path)
        if 'description' not in df.columns:
            df['description'] = ""
        return df

    def _run(self, description: str = "") -> Dict[str, Any]:
        if self.df is None:
            self.df = self._load_csv()

        # If there's a description for the last processed image, update it in the CSV
        if self.last_filename and description:
            self._update_description(self.last_filename, description)
        
        # Get the next image without a description to process
        result = self._get_next_image_without_description()
        
        # If all images are processed, reset the index to start over
        if result.get('complete', False):
            self.current_index = 0
            self.last_filename = ""
            result = self._get_next_image_without_description()

        return result

    def _get_next_image_without_description(self) -> Dict[str, Any]:
        if self.df.empty:
            return {
                "message": "No images available for processing",
                "complete": True
            }

        # Search for the next image that doesn't have a description or has an empty description
        for index, row in self.df.iterrows():
            if pd.isna(row['description']) or row['description'].strip() == "":
                self.current_index = index
                self.last_filename = row['filename']
                
                return {
                    "filename": row['filename'],
                    "file_path": row['file_path'],
                    "width": row['width'],
                    "height": row['height'],
                    "format": row['format'],
                    "dominant_color": row['dominant_color'],
                    "complete": False
                }

        return {
            "message": "All images have descriptions and are processed",
            "complete": True
        }

    def _update_description(self, filename: str, description: str) -> Dict[str, Any]:
        # Locate the image by filename and update its description
        mask = self.df['filename'] == filename
        if not mask.any():
            return {"error": f"Image with filename '{filename}' not found in the CSV."}

        self.df.loc[mask, 'description'] = description
        self.df.to_csv(self.file_path, index=False)

        return {
            "message": f"Description updated for image: {filename}",
            "updated": True
        }

    def reset(self) -> None:
        # Reset the tool for a new session
        self.current_index = 0
        self.last_filename = ""
        self.df = self._load_csv()