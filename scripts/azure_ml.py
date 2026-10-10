"""Submit real Azure ML v2 jobs; never report cloud validation from local execution."""

import argparse
import json
import os
import tempfile
from pathlib import Path

from maritime.ml_contract import export_features
from maritime.models import stable_id
from maritime.pipeline import load_json, write_json
from maritime.store import Store


def client(config):
    from azure.ai.ml import MLClient
    from azure.identity import DefaultAzureCredential

    values = [
        os.getenv(env) or config[key]
        for env, key in (
            ("AZURE_SUBSCRIPTION_ID", "subscription_id"),
            ("AZURE_RESOURCE_GROUP", "resource_group"),
            ("AZURE_ML_WORKSPACE", "workspace_name"),
        )
    ]
    if not all(values):
        raise ValueError(
            "ENVIRONMENT_DEPENDENT: Azure subscription, resource group and ML workspace required"
        )
    return MLClient(DefaultAzureCredential(), *values)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=["export", "train", "promote", "batch", "monitor"])
    parser.add_argument("--config", default="configs/azure.json")
    parser.add_argument("--data", default="data/azure-features")
    parser.add_argument("--data-dir", default="data")
    parser.add_argument("--model-version")
    parser.add_argument("--approver")
    parser.add_argument("--predictions")
    parser.add_argument("--output", default="data/azure-results")
    args = parser.parse_args()
    config = load_json(args.config)
    if args.mode == "export":
        store = Store(args.data_dir)
        print(
            json.dumps(
                export_features(store.read("activity"), args.data, store.metadata("published_run"))
            )
        )
        return
    ml = client(config)
    from azure.ai.ml import Input, Output, command
    from azure.ai.ml.entities import Data, Environment, Model

    if args.mode == "promote":
        if not args.model_version or not args.approver:
            raise ValueError("Promotion requires a pinned model version and approver")
        model = ml.models.get(config["model_name"], version=args.model_version)
        if model.tags.get("promotion_eligible") != "true":
            raise ValueError("Model has not passed evaluation policy")
        model.tags.update({"promotion": "approved", "approved_by": args.approver})
        result = ml.models.create_or_update(model)
        write_json(
            Path(args.output) / "promotion.json",
            {"model_id": result.id, "approver": args.approver, "status": "PROMOTED_IN_AZURE_ML"},
        )
        return
    # Only whitelisted application code is uploaded, never local data, keys or reports.
    import shutil

    with tempfile.TemporaryDirectory() as temp:
        code = Path(temp)
        shutil.copytree("src", code / "src", ignore=shutil.ignore_patterns("__pycache__"))
        shutil.copytree("configs", code / "configs")
        shutil.copy2("pyproject.toml", code / "pyproject.toml")
        shutil.copy2("uv.lock", code / "uv.lock")
        environment = Environment(
            name="maritime-ml",
            image="mcr.microsoft.com/azureml/openmpi4.1.0-ubuntu22.04:latest",
            conda_file={
                "name": "maritime",
                "channels": ["conda-forge"],
                "dependencies": [
                    "python=3.11",
                    "pip",
                    {"pip": ["mlflow>=2.19,<4", "azureml-mlflow>=1.59,<2"]},
                ],
            },
        )
        from maritime.ml_contract import load_features

        _, manifest = load_features(args.data)
        asset = ml.data.create_or_update(
            Data(
                name="maritime-gold-features",
                version=stable_id(manifest),
                type="uri_folder",
                path=args.data,
                description="Fabric Gold observed-port-activity feature contract",
                tags={
                    "feature_version": manifest["feature_version"],
                    "fabric_run_id": manifest["fabric_run_id"],
                },
            )
        )
        inputs = {"data": Input(type="uri_folder", path=asset.id)}
        cmd = f"pip install uv==0.12.18 && uv sync --frozen --extra ml --no-editable && uv run --no-sync python -m maritime.azure_ml_job {args.mode} --data ${{{{inputs.data}}}} --output ${{{{outputs.results}}}}"
        if args.mode == "batch":
            if not args.model_version:
                raise ValueError("Batch inference requires a pinned promoted model version")
            model = ml.models.get(config["model_name"], version=args.model_version)
            if model.tags.get("promotion") != "approved":
                raise ValueError("Only an approved registered model may score production data")
            inputs["model"] = Input(type="custom_model", path=model.id)
            cmd += " --model ${{inputs.model}}"
        if args.mode == "monitor":
            if not args.predictions:
                raise ValueError("Monitoring requires prior predictions")
            inputs["predictions"] = Input(type="uri_file", path=args.predictions)
            cmd += " --predictions ${{inputs.predictions}}"
        job = command(
            code=str(code),
            command=cmd,
            inputs=inputs,
            outputs={"results": Output(type="uri_folder")},
            environment=environment,
            compute=config["compute"],
            experiment_name=config["experiment_name"],
            display_name="maritime-" + args.mode,
            tags={
                "feature_version": manifest["feature_version"],
                "fabric_run_id": manifest["fabric_run_id"],
                "classification": "OBSERVED_INPUT_PREDICTED_OUTPUT",
            },
        )
        submitted = ml.jobs.create_or_update(job)
    ml.jobs.stream(submitted.name)
    finished = ml.jobs.get(submitted.name)
    write_json(
        Path(args.output) / "job.json",
        {"name": finished.name, "status": finished.status, "mode": args.mode},
    )
    if finished.status != "Completed":
        raise RuntimeError(f"Azure ML job did not succeed: {finished.status}")
    job_output = Path(args.output) / submitted.name
    ml.jobs.download(submitted.name, download_path=str(job_output), output_name="results")
    if args.mode == "train":
        reports = list(job_output.rglob("evaluation.json"))
        report = load_json(next(p for p in reports if p.parent.name != "model"))
        model = ml.models.create_or_update(
            Model(
                name=config["model_name"],
                version=report["model_version"],
                type="custom_model",
                path=f"azureml://jobs/{submitted.name}/outputs/results/paths/model",
                tags={
                    "feature_version": report["feature_version"],
                    "promotion": "candidate",
                    "promotion_eligible": str(report["promotion"]["eligible"]).lower(),
                    "training_job": submitted.name,
                },
            )
        )
        write_json(
            Path(args.output) / "registration.json",
            {
                "model_id": model.id,
                "model_version": model.version,
                "status": "REGISTERED_IN_AZURE_ML",
            },
        )
    print(json.dumps({"job": submitted.name, "status": finished.status, "output": args.output}))


if __name__ == "__main__":
    main()
