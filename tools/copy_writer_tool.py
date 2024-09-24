import pandas as pd
import csv
import os
from typing import ClassVar, Union, List, Dict, Tuple
from crewai_tools import BaseTool

class CopyWriterTool(BaseTool):
    name: str = "CopyWriterTool"
    description: str = (
        "Calculates length differences between original and refined copy items, "
        "updates the CSV file with refined copies, and confirms if all items are within character limits."
    )
    base_file_path: ClassVar[str] = 'crew_io_files'
    character_limits: ClassVar[Dict[str, int]] = {
        "Headline": 30,
        "Description": 90,
        "Long Description": 90
    }

    def _run(self, input_data: Union[List[Union[List, Tuple]], Dict[str, List[Union[List, Tuple]]]], persona_number: int = None) -> dict:
        if isinstance(input_data, dict):
            input_data = input_data.get('input_data', [])

        # Construct the file path based on the persona number
        if persona_number is not None:
            file_name = f"ad_copy_persona_{persona_number}.csv"
        else:
            file_name = "copy_items.csv"  # Default file name for backwards compatibility
        
        file_path = os.path.join(self.base_file_path, file_name)

        # Check if the file exists
        if not os.path.exists(file_path):
            return {"error": f"File not found: {file_path}"}

        length_diff_results = self._calculate_length_differences(input_data)
        
        if length_diff_results.get('success'):
            csv_update_results = self._update_csv(input_data, length_diff_results['results'], file_path)
            
            all_within_limits = all(result['refined_length'] <= self.character_limits.get(result['type'], float('inf')) 
                                    for result in length_diff_results['results'])
            
            combined_results = {
                "success": True,
                "message": "Length differences calculated and CSV updated",
                "all_within_limits": all_within_limits,
                "length_diff_results": length_diff_results['results'],
                "updates_made": csv_update_results.get('updates_made', 0)
            }
            if csv_update_results.get('error'):
                combined_results['csv_update_error'] = csv_update_results['error']
            return combined_results
        else:
            return {
                "success": False,
                "message": "Failed to calculate length differences",
                "error": length_diff_results.get('error')
            }

    def _calculate_length_differences(self, input_data: List[Union[List, Tuple]]) -> dict:
        try:
            results = []
            for item in input_data:
                if len(item) != 3:
                    return {"error": f"Invalid item format: {item}. Each item should contain 3 elements."}
                
                copy_type, original_copy, refined_copy = item
                original_length = len(original_copy)
                refined_length = len(refined_copy)
                length_difference = original_length - refined_length
                
                results.append({
                    "type": copy_type,
                    "original_length": original_length,
                    "refined_length": refined_length,
                    "difference": length_difference,
                    "within_limit": refined_length <= self.character_limits.get(copy_type, float('inf'))
                })

            return {"success": True, "results": results}
        except Exception as e:
            return {"error": f"An error occurred while calculating length differences: {str(e)}"}

    def _update_csv(self, input_data: List[Union[List, Tuple]], length_diff_results: List[Dict], file_path: str) -> dict:
        try:
            # Read CSV file with proper handling of quotes and commas
            with open(file_path, 'r', newline='', encoding='utf-8') as file:
                reader = csv.reader(file, quotechar='"', delimiter=',', quoting=csv.QUOTE_ALL, skipinitialspace=True)
                data = list(reader)

            # Convert to DataFrame
            df = pd.DataFrame(data, columns=['Type', 'Copy'])
            
            updates_made = 0
            for item, result in zip(input_data, length_diff_results):
                copy_type, original_copy, refined_copy = item
                if result['difference'] > 0:  # Only update if the refined copy is actually shorter
                    mask = (df['Type'] == copy_type) & (df['Copy'] == original_copy)
                    df.loc[mask, 'Copy'] = refined_copy
                    updates_made += mask.sum()

            # Write updated DataFrame back to CSV only if updates were made
            if updates_made > 0:
                with open(file_path, 'w', newline='', encoding='utf-8') as file:
                    writer = csv.writer(file, quotechar='"', delimiter=',', quoting=csv.QUOTE_ALL)
                    writer.writerows(df.values)
            
            return {
                "success": True,
                "updates_made": updates_made
            }
        except Exception as e:
            return {"error": f"Failed to update CSV: {str(e)}"}