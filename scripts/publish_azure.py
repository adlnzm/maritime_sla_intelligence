import argparse
import json

from maritime.azure_store import AzureStore
from maritime.pipeline import load_json

parser = argparse.ArgumentParser(description="Publish a verified Fabric Gold serving copy to Azure")
parser.add_argument("--folder", required=True)
parser.add_argument("--report", required=True)
args = parser.parse_args()
print(json.dumps(AzureStore().publish(args.folder, load_json(args.report)), indent=2))
