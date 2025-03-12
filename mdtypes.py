from typing import List, Dict, Union

# Define a type for the filter dictionary
FilterDict = Dict[str, Union[float, int]]

# Define a type for the essential metadata dictionary
EssentialMetadataDict = Dict[str, Union[float, List[FilterDict]]]

# Example essential metadata structure
example_metadata: EssentialMetadataDict = {
    "original_duration": 300.0,
    "filters": [
        {"location": 0, "duration": 60, "intensity": 5.0},
        {"location": 60, "duration": 45, "intensity": 4.0}
    ]
}
