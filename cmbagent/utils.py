# cmbagent/utils.py
import os
from pprint import pprint

from autogen.coding import LocalCommandLineCodeExecutor

import autogen
from autogen import AssistantAgent
from autogen.agentchat.contrib.retrieve_user_proxy_agent import RetrieveUserProxyAgent




from autogen import UserProxyAgent, config_list_from_json
from autogen.agentchat.contrib.gpt_assistant_agent import GPTAssistantAgent


from cmbagent.yaml import yaml_load_file, yaml_load

import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='[%(name)s] %(message)s')
logger = logging.getLogger(__name__)


def helper_function():
    return "This is a helper function."


# Get the path of the current file
path_to_basedir = os.path.dirname(os.path.abspath(__file__))
# Construct the path to the APIs directory
path_to_apis = os.path.join(path_to_basedir, "apis")

# Construct the path to the assistants directory
path_to_assistants = os.path.join(path_to_basedir, "assistants")
path_to_engineer = os.path.join(path_to_basedir, "engineer")
path_to_planner = os.path.join(path_to_basedir, "planner")
path_to_executor = os.path.join(path_to_basedir, "executor")

work_dir = os.path.join(path_to_basedir, "../output")
