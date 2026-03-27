import json
import os
from pathlib import Path
from typing import Any
from src import analysis

def process_json_files(source_folder: str, target_folder: str) -> None:
    """
    Process all txt files in source folder containing JSON data.
    Execute analysis and save results to target folder.
    
    Args:
        source_folder: Path to folder containing txt files with JSON data
        target_folder: Path to folder where results will be saved
    """
    source_path = Path(source_folder)
    target_path = Path(target_folder)
    
    # Create target folder if it doesn't exist
    target_path.mkdir(parents=True, exist_ok=True)
    
    # Process all txt files
    for txt_file in source_path.glob("*.txt"):
        try:
            # Load JSON from txt file
            with open(txt_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # Execute analysis (replace with your analysis logic)
            result = analysis.DocumentValidator(data).run()
            
            # Generate output filename
            output_name = txt_file.stem.replace(" ", "_") + "_analysis.json"
            output_path = target_path / output_name
            
            # Save results
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(result, f, indent=2)
            
            print(f"✓ Processed: {txt_file.name} -> {output_name}")
        
        except json.JSONDecodeError:
            print(f"✗ Invalid JSON in {txt_file.name}")
        except Exception as e:
            print(f"✗ Error processing {txt_file.name}: {e}")


def analyze_data(data: Any) -> dict:
    """
    Perform analysis on loaded JSON data.
    Replace this with your actual analysis logic.
    """
    return {
        "status": "completed",
        "data": data,
        "analysis": "Add your analysis here"
    }


if __name__ == "__main__":
    SOURCE = "res/fascicoli_test/t"
    TARGET = "res/fascicoli_test/t/o/fascicoli_test_output"
    
    process_json_files(SOURCE, TARGET)