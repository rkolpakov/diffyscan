import difflib
import sys
import time
import argparse
import os

from utils.common import load_config, load_env
from utils.constants import DIFFS_DIR, START_TIME, DEFAULT_CONFIG_PATH
from utils.explorer import get_contract_from_explorer
from utils.github import get_file_from_github, resolve_dep
from utils.helpers import create_dirs
from utils.logger import logger


EXPLORER_API_TOKEN = load_env("ETHERSCAN_TOKEN", masked=True)
GITHUB_API_TOKEN = load_env("GITHUB_API_TOKEN", masked=True)

CONTRACT_ADDRESS = load_env("CONTRACT_ADDRESS", required=False)
CONTRACT_NAME = load_env("CONTRACT_NAME", required=False)

g_skip_user_input: bool = False


def run_diff(config, name, address, explorer_api_token, github_api_token):
    logger.divider()
    logger.okay("Contract", address)
    logger.okay("Blockchain explorer Hostname", config["explorer_hostname"])
    logger.okay("Repo", config["github_repo"]["url"])
    logger.okay("Repo commit", config["github_repo"]["commit"])
    logger.okay("Repo relative root", config["github_repo"]["relative_root"])

    logger.divider()

    logger.info(
        f"Fetching source code from blockchain explorer {config['explorer_hostname']} ..."
    )
    contract_name, source_files = get_contract_from_explorer(
        token=explorer_api_token,
        explorer_hostname=config["explorer_hostname"],
        contract=address,
    )

    if contract_name != name:
        logger.error(
            "Contract name in config does not match with Blockchain explorer",
            f"{address}: {name} != {contract_name}",
        )
        sys.exit(1)

    files_count = len(source_files)
    logger.okay("Contract", contract_name)
    logger.okay("Files", files_count)

    if not g_skip_user_input:
        input("Press Enter to proceed...")
        logger.divider()

    logger.info("Diffing...")

    report = []

    for index, (path_to_file, source_code) in enumerate(source_files):
        file_number = index + 1
        split_path_to_file = path_to_file.split("/")
        origin = split_path_to_file[0]
        filename = split_path_to_file[-1]

        logger.update_info(f"File {file_number} / { files_count}", filename)

        repo = None
        dep_name = None

        (repo, dep_name) = resolve_dep(path_to_file, config)
        if not dep_name:
            repo = config["github_repo"]

        diff_report_filename = None
        diffs_count = None

        if not repo:
            logger.error("File not found", path_to_file)
            sys.exit()

        file_found = bool(repo)

        github_file = get_file_from_github(
            github_api_token, repo, path_to_file, dep_name
        )
        if not github_file:
            github_file = "<!-- No file content -->"
            file_found = False

        github_lines = github_file.splitlines()
        explorer_lines = source_code["content"].splitlines()

        diff_html = difflib.HtmlDiff().make_file(github_lines, explorer_lines)
        diff_report_filename = f"{DIFFS_DIR}/{address}/{filename}.html"

        create_dirs(diff_report_filename)
        with open(diff_report_filename, "w") as f:
            f.write(diff_html)

        diffs = difflib.unified_diff(github_lines, explorer_lines)
        diffs_count = len(list(diffs))

        report_data = [
            file_number,
            filename,
            file_found,
            diffs_count,
            origin,
            diff_report_filename,
        ]

        report.append(report_data)

    logger.divider()

    files_found = len([row for row in report if row[2]])
    logger.info(f"Files found: {files_found} / {files_count}")

    identical_files = len([row for row in report if row[3] == 0])
    logger.info(f"Identical files: {identical_files} / {files_found}")

    logger.report_table(report)


def process_config(path: str):
    logger.info(f"Loading config {path}...")
    config = load_config(path)

    if CONTRACT_ADDRESS is not None:
        if CONTRACT_NAME is None:
            logger.error(
                "Please set the 'CONTRACT_NAME' env var for address",
                f"{CONTRACT_ADDRESS}",
            )
            sys.exit(1)

        logger.info(
            f"Running diff for a single contract {CONTRACT_NAME} deployed at {CONTRACT_ADDRESS}..."
        )
        run_diff(
            config,
            CONTRACT_NAME,
            CONTRACT_ADDRESS,
            EXPLORER_API_TOKEN,
            GITHUB_API_TOKEN,
        )
    else:
        contracts = config["contracts"]
        logger.info(f"Running diff for contracts from config {contracts}...")
        for address, name in config["contracts"].items():
            run_diff(config, name, address, EXPLORER_API_TOKEN, GITHUB_API_TOKEN)


def parse_arguments():
    parser = argparse.ArgumentParser()
    parser.add_argument("path", nargs="?", default=None, help="Path to config or directory with configs")
    parser.add_argument("--yes", "-y", help="If set don't ask for input before validating each contract", action="store_true")
    return parser.parse_args()


def main():
    global g_skip_user_input

    args = parse_arguments()
    g_skip_user_input = args.yes

    logger.info("Welcome to Diffyscan!")
    logger.divider()

    if args.path is None:
        process_config(DEFAULT_CONFIG_PATH)
    elif os.path.isfile(args.path):
        process_config(args.path)
    elif os.path.isdir(args.path):
        for filename in os.listdir(args.path):
            config_path = os.path.join(args.path, filename)
            if os.path.isfile(config_path):
                process_config(config_path)

    execution_time = time.time() - START_TIME

    logger.okay(f"Done in {round(execution_time, 3)}s ✨" + " " * 100)


if __name__ == "__main__":
    main()
