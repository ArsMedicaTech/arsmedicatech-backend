#!/usr/bin/env python3
# In: manage.py (in your project root)

import argparse
import sys

print("Starting manage.py...")
# Import the main function from your now-import-friendly utility script
from utils.api_keys.debug_api_key_step_by_step import main as debug_api_key

print("Imported debug_api_key successfully.")


def main():
    """The main entry point for the command-line orchestrator."""

    # 1. Create the top-level parser
    parser = argparse.ArgumentParser(
        description="A central utility script for managing the project."
    )

    # 2. Create subparsers to handle different commands
    # This is what allows you to have `manage.py <command>`
    subparsers = parser.add_subparsers(
        dest="command", help="Available commands", required=True
    )

    # 3. Create the parser for the "debug-api-key" command
    parser_debug_api = subparsers.add_parser(
        "debug-api-key", help="Run the step-by-step API key debugger."
    )
    # This command doesn't need extra arguments, but you could add them here if you wanted
    # parser_debug_api.add_argument(...)

    # You can add more commands here for other utilities
    # parser_another_command = subparsers.add_parser("another-cmd", help="Does something else.")

    # 4. Parse the arguments from the command line
    args = parser.parse_args()

    # 5. Call the correct function based on the command provided
    if args.command == "debug-api-key":
        print("🚀 Orchestrator: starting API key debugger...")
        success = debug_api_key()  # Call the imported function
        if not success:
            print("❌ Orchestrator: The API key debugger finished with errors.")
            sys.exit(1)
        else:
            print("✅ Orchestrator: The API key debugger finished successfully.")

    # elif args.command == "another-cmd":
    #     run_another_utility()


if __name__ == "__main__":
    main()
