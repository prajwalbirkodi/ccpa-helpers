import json
import pickle
from pathlib import Path
from shutil import rmtree
from typing import Optional

import pandas as pd
from gretel_client import configure_session, submit_docker_local
from gretel_client.projects import create_or_get_unique_project
from gretel_client.projects.models import read_model_config
from pkg_resources import resource_filename
from smart_open import open

from . import reports
from .helpers import quiet_poll

PREVIEW_RECS = 100

class CCPAAnonymizer:
    def __init__(
        self,
        project_name: str = "ccpa-anonymized",
        transforms_config: str = resource_filename(
            __name__, "../config/transforms_config.yaml"
        ),
        synthetics_config: str = resource_filename(
            __name__, "../config/synthetics_config.yaml"
        ),
        run_mode: str = "cloud",
        preview_recs: int = PREVIEW_RECS,
        show_real_data: bool = True,
        output_dir: str = None,
        tmp_dir: str = "tmp",
        overwrite: bool = False,
        endpoint: str = None,
    ):
        self.project_name = project_name
        self.synthetics_config = synthetics_config
        self.transforms_config = transforms_config
        self.run_mode = run_mode
        self.preview_recs = preview_recs
        self.show_real_data = show_real_data
        self.output_dir = Path("~/Documents/anonymizer/artifacts").expanduser() if output_dir is None else Path(output_dir)
        self.tmp_dir = Path(tmp_dir)
        self.anonymization_report_path = None
        self.anonymized_path = None
        self.deidentified_path = None
        self.dataset_path = None
        self.training_path = Path(self.tmp_dir / "training_data.csv")
        self.preview_path = Path(self.tmp_dir / "preview.csv")
        self._cache_ner_report = None
        self._cache_run_report = None
        self._cache_syn_report = None
        self.dataset_path: Optional[Path] = None
        self.deid_df = None
        self.synthetic_df = None
        self.ner_report = {}
        self.run_report = {}
        self.syn_report = {}
        self.project = None

        if overwrite:
            if self.tmp_dir.exists() and self.tmp_dir.is_dir():
                rmtree(self.tmp_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.tmp_dir.mkdir(parents=True, exist_ok=True)

        try:
            self.project = create_or_get_unique_project(name=self.project_name)
            if self.project:
                print(f"Project initialized successfully. Follow along with model training at: {self.project.get_console_url()}")
            else:
                raise RuntimeError("Failed to create or get project")
        except Exception as e:
            print(f"Error initializing project: {e}")
            self.project = None  # Ensure project is None if initialization fails

    def anonymize(self, dataset_path: str, transform_locally: bool, transform_in_cloud: bool, synthesize_locally: bool, synthesize_in_cloud: bool, endpoint: Optional[str] = None):
        if not self.project:
            raise RuntimeError("Project initialization failed. Cannot proceed with anonymization.")

        print(f"Anonymizing '{dataset_path}'")
        print(f"Transform Locally: {transform_locally}")
        print(f"Transform in Cloud: {transform_in_cloud}")
        print(f"Synthesize Locally: {synthesize_locally}")
        print(f"Synthesize in Cloud: {synthesize_in_cloud}")

        self.dataset_path = dataset_path
        self._preprocess_data(dataset_path)
        if transform_locally:
            self.transform_locally()
        elif transform_in_cloud:
            self.transform_cloud()
        if synthesize_locally:
            self.synthesize_locally()
        elif synthesize_in_cloud:
            self.synthesize_cloud()
        print("Anonymization complete")
        print(f" -- Synthetic data stored to: {self.anonymized_path}")
        print(f" -- Anonymization report stored to: {self.anonymization_report_path}")

    def _save_reports(self, output_path: Path):
        compare_html = reports.compare(
            training_path=self.training_path,
            deidentified_path=self.deidentified_path,
            anonymized_path=self.anonymized_path,
            show_real_data=self.show_real_data,
        )
        r = (
            f"<h1>{self.dataset_path}</h1>"
            f"<p>{reports.get_header()}</p>"
            f"{reports.ner_report(self.ner_report)['html']}"
            f"{reports.transform_report(self.run_report)['html']}"
            f"{reports.synthesis_report(self.syn_report)['html']}"
            f"{compare_html}"
        )
        self.anonymization_report_path.write_text(reports.style_html(r))

    def _preprocess_data(self, ds: str) -> str:
        df = pd.read_csv(ds)
        nan_columns = df.columns[df.isna().any()].tolist()
        print(
            f"Warning: Found NaN values in training data columns: {nan_columns}. Replacing NaN values with ''."
        )
        df = df.fillna("")
        df.to_csv(self.training_path, index=False)

        prefix = Path(ds).stem
        self.anonymization_report_path = Path(
            self.output_dir / f"{prefix}-anonymization_report.html"
        )
        self.anonymized_path = Path(self.output_dir / f"{prefix}-synthetic_data.csv")
        self.deidentified_path = Path(
            self.output_dir / f"{prefix}-transformed_data.csv"
        )
        self._cache_ner_report = Path(self.tmp_dir / f"{prefix}-ner_report.pkl")
        self._cache_run_report = Path(self.tmp_dir / f"{prefix}-run_report.pkl")
        self._cache_syn_report = Path(self.tmp_dir / f"{prefix}-syn_report.pkl")

    def _transform_local(self, config: dict):
        df = pd.read_csv(self.training_path)
        df.head(self.preview_recs).to_csv(self.preview_path, index=False)

        if self.project:
            transform_train = self.project.create_model_obj(config, str(self.preview_path))
        else:
            print("Project is not initialized correctly.")
            return

        run = submit_docker_local(transform_train, output_dir=str(self.tmp_dir))
        self.ner_report = json.loads(open(self.tmp_dir / "report_json.json.gz").read())

        transform_go = transform_train.create_record_handler_obj(
            data_source=str(self.training_path)
        )
        run = submit_docker_local(
            transform_go,
            model_path=str(self.tmp_dir / "model.tar.gz"),
            output_dir=str(self.tmp_dir),
        )
        self.run_report = json.loads(open(self.tmp_dir / "report_json.json.gz").read())
        self.deid_df = pd.read_csv(self.tmp_dir / "data.gz")
        self.deid_df.to_csv(self.deidentified_path, index=False)

    def _transform_cloud(self, config: dict):
        df = pd.read_csv(self.training_path)
        model = self.project.create_model_obj(
            config, data_source=df.head(self.preview_recs)
        )
        model.submit_cloud()
        quiet_poll(model)
        with open(model.get_artifact_link("report_json.json")) as fh:
            self.ner_report = json.loads(fh.read())

        rh = model.create_record_handler_obj(data_source=df)
        rh.submit_cloud()
        quiet_poll(rh)
        with open(rh.get_artifact_link("report_json.json")) as fh:
            self.run_report = json.loads(fh.read())
        self.deid_df = pd.read_csv(rh.get_artifact_link("data"), compression="gzip")
        self.deid_df.to_csv(self.deidentified_path, index=False)

    def transform_locally(self):
        config = read_model_config(self.transforms_config)
        self._transform_local(config)
    
    def transform_cloud(self):
        config = read_model_config(self.transforms_config)
        self._transform_cloud(config)

    def synthesize_cloud(self):
        config = read_model_config(self.synthetics_config)

        model_config = config["models"][0]
        model_type = next(iter(model_config.keys()))

        model_config[model_type]["generate"] = {"num_records": len(self.deid_df)}
        model_config[model_type]["data_source"] = str(self.deidentified_path)

        if self._cache_syn_report.exists():
            self.syn_report = pickle.load(open(self._cache_syn_report, "rb"))
            self.synthetic_df = pd.read_csv(self.anonymized_path)
        else:
            self._synthesize_cloud(config=config)

        print(reports.synthesis_report(self.syn_report)["html"])
        self._save_reports(self.anonymization_report_path)

    def _synthesize_cloud(self, config):
        model = self.project.create_model_obj(config, data_source=self.deid_df)
        model.submit_cloud()
        quiet_poll(model)
        with open(model.get_artifact_link("report_json.json")) as fh:
            self.syn_report = json.loads(fh.read())
        self.synthetic_df = pd.read_csv(model.get_artifact_link("data"), compression="gzip")
        self.synthetic_df.to_csv(self.anonymized_path, index=False)
        pickle.dump(self.syn_report, open(self._cache_syn_report, "wb"))

    def synthesize_locally(self):
        config = read_model_config(self.synthetics_config)

        model_config = config["models"][0]
        model_type = next(iter(model_config.keys()))

        model_config[model_type]["generate"] = {"num_records": len(self.deid_df)}
        model_config[model_type]["data_source"] = str(self.deidentified_path)

        if self._cache_syn_report.exists():
            self.syn_report = pickle.load(open(self._cache_syn_report, "rb"))
            self.synthetic_df = pd.read_csv(self.anonymized_path)
        else:
            self._synthesize_local(config=config)

        print(reports.synthesis_report(self.syn_report)["html"])
        self._save_reports(self.anonymization_report_path)

    def _synthesize_local(self, config):
        model = self.project.create_model_obj(config, data_source=self.deid_df)
        run = submit_docker_local(model, output_dir=str(self.tmp_dir))
        self.syn_report = json.loads(open(self.tmp_dir / "report_json.json.gz").read())
        self.synthetic_df = pd.read_csv(self.tmp_dir / "data.gz")
        self.synthetic_df.to_csv(self.anonymized_path, index=False)
        pickle.dump(self.syn_report, open(self._cache_syn_report, "wb"))
