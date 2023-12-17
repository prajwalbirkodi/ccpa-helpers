import os
import glob
from ccpa_helpers import CCPAAnonymizer


# Change the current working directory if needed
if not os.getcwd().endswith('ccpa-helpers'):
    os.chdir('ccpa-helpers')

# Set the search pattern for datasets
search_pattern = "data/adventure-works-bike-buying.csv"

# Initialize the Anonymizer object with the API key
am = CCPAAnonymizer(
    project_name="ccpa-workflow",
    run_mode="cloud",
    transforms_config="src/config/transforms_config.yaml",
    synthetics_config="src/config/synthetics_config.yaml",
    endpoint="https://api.gretel.cloud",
)
# Manually set the API key attribute
# am.project._session.api_key = api_key

# Anonymize each dataset matching the search pattern
for dataset_path in glob.glob(search_pattern):
    am.anonymize(dataset_path=dataset_path)