import os
import subprocess
import streamlit as st

sys.path.append(os.path.join(os.path.dirname(__file__), 'src', 'ccpa_helpers'))

from ccpaanonymizer import CCPAAnonymizer
import pandas as pd

# Debugging information
st.write("Python Path:", sys.path)
st.write("Installed Packages:", subprocess.run(["pip", "freeze"], capture_output=True).stdout.decode())


# Define the Streamlit app
def main():

    st.title("CCPA Anonymizer")

    st.info("Before anonymizing the dataset, please make sure Docker is running on your system.")

    st.sidebar.header("Configuration")
    project_name = st.sidebar.text_input("Project Name", value="ccpa-anonymized")
    transforms_config = st.sidebar.text_input("Transforms Config", value="src/config/transforms_config.yaml")
    synthetics_config = st.sidebar.text_input("Synthetics Config", value="src/config/synthetics_config.yaml")
    endpoint = st.sidebar.text_input("Endpoint", value="https://api.gretel.cloud")

    st.sidebar.header("Dataset")
    uploaded_files = st.sidebar.file_uploader("Upload Dataset", type=["csv", "xlsx"], accept_multiple_files=True)

    st.sidebar.header("Options")
    overwrite = st.sidebar.checkbox("Overwrite", value=False)

    transform_locally = st.checkbox("Transform Locally")
    transform_in_cloud = st.checkbox("Transform in Cloud", value=not transform_locally, key="transform_in_cloud_key", disabled=transform_locally)
    synthesize_locally = st.checkbox("Synthesize Locally")
    synthesize_in_cloud = st.checkbox("Synthesize in Cloud", value=not synthesize_locally, key="synthesize_in_cloud_key", disabled=synthesize_locally)

    if transform_locally:
        transform_in_cloud = False
    elif transform_in_cloud:
        transform_locally = False
    
    if synthesize_locally:
        synthesize_in_cloud = False
    elif synthesize_in_cloud:
        synthesize_locally = False

    if st.button("Anonymize"):
        if uploaded_files is not None:
            for uploaded_file in uploaded_files:
                # Save the uploaded file to a temporary directory
                with open(uploaded_file.name, "wb") as f:
                    f.write(uploaded_file.getvalue())
                
                # Initialize the CCPAAnonymizer object
                anonymizer = CCPAAnonymizer(
                    project_name=project_name,
                    transforms_config=transforms_config,
                    synthetics_config=synthetics_config,
                    endpoint=endpoint,
                    overwrite=overwrite
                )

                with st.spinner("Anonymization in progress..."):

                    anonymizer.anonymize(
                        dataset_path=uploaded_file.name,
                        transform_locally=transform_locally,
                        transform_in_cloud=transform_in_cloud,
                        synthesize_locally=synthesize_locally,
                        synthesize_in_cloud=synthesize_in_cloud
                )
                
                st.success("Anonymization Complete")

                if transform_locally or transform_in_cloud:
                    st.subheader("First 10 records from the transformed file:")
                    transformed_df = pd.read_csv(anonymizer.deidentified_path)
                    st.write(transformed_df.head(10))

                    # Display the first 10 records from the synthesized file if applicable
                if synthesize_locally or synthesize_in_cloud:
                    st.subheader("First 10 records from the synthesized file:")
                    synthesized_df = pd.read_csv(anonymizer.anonymized_path)
                    st.write(synthesized_df.head(10))
        else:
            st.error("Please upload a dataset file.")

if __name__ == "__main__":
    main()
