import os
import logging
import importlib
import requests
import autogen 
import ast
import json
import sys
import pandas as pd
import copy
import datetime
from typing import Any, Dict
from IPython.display import display
from collections import defaultdict
from .utils import work_dir as work_dir_default
from .utils import path_to_assistants,config_list_from_json,path_to_apis,OpenAI,Image,default_chunking_strategy,default_top_p,default_temperature,default_select_speaker_prompt_template,default_select_speaker_message_template
from .utils import default_max_round, default_groupchat_intro_message,default_llm_model,default_llm_config_list
from pprint import pprint
from .base_agent import CmbAgentGroupChat, CmbAgentSwarmAgent
from .rag_utils import import_rag_agents, make_rag_agents,push_vector_stores
from .utils import path_to_agents, update_yaml_preserving_format
from .hand_offs import register_all_hand_offs
from .functions import register_functions_to_agents



def import_non_rag_agents():
    imported_non_rag_agents = {}
    for subdir in os.listdir(path_to_agents):
        # Skip rag_agents folder and non-directories
        if subdir == "rag_agents":
            continue
        subdir_path = os.path.join(path_to_agents, subdir)
        if os.path.isdir(subdir_path):
            for filename in os.listdir(subdir_path):
                if filename.endswith(".py") and filename != "__init__.py" and filename[0] != ".":
                    module_name = filename[:-3]  # Remove the .py extension
                    class_name = ''.join([part.capitalize() for part in module_name.split('_')]) + 'Agent'
                    # Assuming the module path is agents.<subdir>.<module_name>
                    module_path = f"cmbagent.agents.{subdir}.{module_name}"
                    module = importlib.import_module(module_path)
                    agent_class = getattr(module, class_name)
                    imported_non_rag_agents[class_name] = {
                        'agent_class': agent_class,
                        'agent_name': module_name,
                    }
    return imported_non_rag_agents


# from cmbagent.engineer.engineer import EngineerAgent
# from cmbagent.planner.planner import PlannerAgent
# from cmbagent.executor.executor import ExecutorAgent
# from cmbagent.admin.admin import AdminAgent
# from cmbagent.summarizer.summarizer import SummarizerAgent
# from cmbagent.rag_software_formatter.rag_software_formatter import RagSoftwareFormatterAgent




from pydantic import BaseModel
# import yaml
from ruamel.yaml import YAML
from typing import List
from autogen import  AfterWorkOption, AFTER_WORK, ON_CONDITION, SwarmResult, initiate_swarm_chat, SwarmAgent
from autogen.cmbagent_utils import cmbagent_debug
from cmbagent.cmbagent_swarm_agent import initiate_cmbagent_swarm_chat
from cmbagent.structured_output import EngineerResponse, PlannerResponse, SummarizerResponse, RagSoftwareFormatterResponse
from cmbagent.context import shared_context as shared_context_default
from sys import exit




class CMBAgent:

    logging.disable(logging.CRITICAL)



    def __init__(self,
                 cache_seed=42,
                 temperature=default_temperature,
                 top_p=default_top_p,
                 timeout=1200,
                 max_round=default_max_round,
                 platform='oai',
                 model='gpt4o',
                 llm_api_key=None,
                 llm_api_type=None,
                 make_vector_stores=False, #set to True to update all vector_stores, or a list of agents to update only those vector_stores e.g., make_vector_stores= ['cobaya', 'camb'].
                 agent_list = ['classy_sz'],
                 verbose = False,
                 reset_assistant = False,
                 agent_instructions = {
                        "executor":
                        """
                        You execute python code provided to you by the engineer or save content provided by the researcher.
                        """,      
                    },
                 agent_descriptions = None,
                 agent_temperature = None,
                 agent_top_p = None,
                #  vector_store_ids = None,
                 chunking_strategy = {
                    'classy_sz_agent': 
                    {
                    "type": "static",
                    "static": {
                      "max_chunk_size_tokens": 800, # reduce size to ensure better context integrity
                      "chunk_overlap_tokens": 200 # increase overlap to maintain context across chunks
                    }
                }
                },
                 select_speaker_prompt = None,
                 select_speaker_message = None,
                 intro_message = None,
                 set_allowed_transitions = None,
                 skip_executor = False,
                 skip_memory = True,
                 skip_rag_software_formatter = True,
                 default_llm_config_list = default_llm_config_list,
                 agent_llm_configs = {
                    'engineer': {
                        "model": "o3-mini-2025-01-31",
                        "reasoning_effort": "high",
                        "api_key": os.getenv("OPENAI_API_KEY"),
                        "api_type": "openai",
                        },
                    'classy_sz': {
                        "model": "gpt-4o-mini",
                        "api_key": os.getenv("OPENAI_API_KEY"),
                        "api_type": "openai",
                        },
                    'planner': {
                        "model": "gpt-4o-2024-11-20",
                        "api_key": os.getenv("OPENAI_API_KEY"),
                        "api_type": "openai",
                        },
                    'control': {
                        "model": "gpt-4o-2024-11-20",
                        "api_key": os.getenv("OPENAI_API_KEY"),
                        "api_type": "openai",
                        },

                    'researcher': {
                        "model": "gemini-2.0-pro-exp-02-05",
                        "api_key": os.getenv("GEMINI_API_KEY"),
                        "api_type": "google",
                        },
                    'plan_reviewer': {
                        "model": "claude-3-7-sonnet-20250219",
                        "api_key": os.getenv("ANTHROPIC_API_KEY"),
                        "api_type": "anthropic",
                        },

                    "classy_sz_response_formatter": {
                        "model": "gpt-4o",
                        "api_key": os.getenv("OPENAI_API_KEY"),
                        "api_type": "openai",
                        },
                    "engineer_response_formatter": {
                        "model": "gpt-4o",
                        "api_key": os.getenv("OPENAI_API_KEY"),
                        "api_type": "openai",
                        },

                    },

                 agent_type = 'swarm',# None,# 'swarm',
                 shared_context = shared_context_default,
                #  make_new_rag_agents = False, ## can be a list of names for new rag agents to be created
                 **kwargs):
        """
        Initialize the CMBAgent.

        Args:
            cache_seed (int, optional): Seed for caching. Defaults to 42.
            temperature (float, optional): Temperature for LLM sampling. Defaults to 0.
            timeout (int, optional): Timeout for LLM requests in seconds. Defaults to 1200.
            max_round (int, optional): Maximum number of conversation rounds. Defaults to 50. If too small, the conversation stops.
            llm_api_key (str, optional): API key for LLM. If None, uses the key from the config file.
            make_vector_stores (bool or list of strings, optional): Whether to create vector stores. Defaults to False. For only subset, use, e.g., make_vector_stores= ['cobaya', 'camb'].
            agent_list (list of strings, optional): List of agents to include in the conversation. Defaults to all agents.
            chunking_strategy (dict, optional): Chunking strategy for vector stores. Defaults to None.
            #  example:
            #  chunking_strategy = {
            # 'planck_agent': 
            #     {
            #     "type": "static",
            #     "static": {
            #       "max_chunk_size_tokens": 3300, # reduce size to ensure better context integrity
            #       "chunk_overlap_tokens": 1000 # increase overlap to maintain context across chunks
            #     }
            # }
            # }
            # example for agent_temperature and agent_top_p:
            # agent_temperature = {
            # 'planck_agent': 0.000001
            # }
            # agent_top_p = {
            # 'planck_agent': 0.1,
            # }
            # agent instruction example:
            # agent_instructions = {
            # 'classy_sz_agent': "You are a clown. "
            # }
            reset_assistant (List of strings, optional): List of agents to reset the assistant. Defaults to False.
            # example:
            # reset_assistant = [
            # 'classy_sz',
            # ]
            
            make_new_rag_agents (list of strings, optional): List of names for new rag agents to be created. Defaults to False.
            
            **kwargs: Additional keyword arguments.

        Attributes:
            kwargs (dict): Additional keyword arguments.
            work_dir (str): Working directory for output.
            path_to_assistants (str): Path to the assistants directory.
            llm_api_key (str): OpenAI API key.
            engineer (engineer_agent): Agent for engineering tasks.
            planner (planner_agent): Agent for planning tasks.
            executor (executor_agent): Agent for executing tasks.

        Note:
            This class initializes various agents and configurations for cosmological data analysis.
        """


        self.kwargs = kwargs

        self.skip_executor = skip_executor

        self.skip_rag_software_formatter = skip_rag_software_formatter

        # self.make_new_rag_agents = make_new_rag_agents
        self.set_allowed_transitions = set_allowed_transitions

        self.vector_store_ids = None

        self.logger = logging.getLogger(__name__)

        # self.non_rag_agents = ['engineer', 'planner', 'executor', 'admin', 'summarizer', 'rag_software_formatter']

        self.agent_list = agent_list

        self.skip_memory = skip_memory

        if not self.skip_memory and 'memory' not in agent_list:
            self.agent_list.append('memory')


        self.verbose = verbose

        self.work_dir = work_dir_default
        # add the work_dir to the python path so we can import modules from it
        sys.path.append(self.work_dir)

        self.path_to_assistants = path_to_assistants

        self.logger.info(f"Autogen version: {autogen.__version__}")

        llm_config_list = default_llm_config_list.copy()

        if llm_api_key is not None:
            llm_config_list[0]['api_key'] = llm_api_key

        if llm_api_type is not None:
            llm_config_list[0]['api_type'] = llm_api_type


        self.llm_api_key = llm_config_list[0]['api_key']

        self.logger.info(f"Path to APIs: {path_to_apis}")

        self.cache_seed = cache_seed

        self.llm_config = {
                        "cache_seed": self.cache_seed,  # change the cache_seed for different trials
                        "temperature": temperature,
                        "top_p": top_p,
                        "config_list": llm_config_list,
                        "timeout": timeout,
                    }
        
        if cmbagent_debug:
            print('\n\n\n\nin cmbagent.py self.llm_config: ',self.llm_config)

        # self.llm_config =  {"model": "gpt-4o-mini", "cache_seed": None}

        self.logger.info("LLM Configuration:")

        for key, value in self.llm_config.items():

            self.logger.info(f"{key}: {value}")

        self.agent_type = agent_type

        self.init_agents(agent_llm_configs=agent_llm_configs) # initialize agents

        if cmbagent_debug:
            print("\n\n All agents instantiated!!!\n\n")

        if cmbagent_debug:  
            print("\n\n Checking assistants...\n\n")

        self.check_assistants(reset_assistant=reset_assistant) # check if assistants exist

        if cmbagent_debug:
            print("\n\n Assistants checked!!!\n\n")
            # sys.exit()


        if cmbagent_debug:
            print('\npushing vector stores...')
        push_vector_stores(self, make_vector_stores, chunking_strategy, verbose = verbose) # push vector stores

        if cmbagent_debug:
            print('\nsetting planner instructions currently not doing anything...')
            print('\nmodify if you want to tune the instruction prompt...')
        self.set_planner_instructions() # set planner instructions


        if self.verbose or cmbagent_debug:
            print("\nSetting up agents:----------------------------------")


        # then we set the agents, note that self.agents is set in init_agents
        for agent in self.agents:

            agent.agent_type = self.agent_type
            if cmbagent_debug:
                print(f"\t- {agent.name}")

            instructions = agent_instructions[agent.name] if agent_instructions and agent.name in agent_instructions else None
            description = agent_descriptions[agent.name] if agent_descriptions and agent.name in agent_descriptions else None
            agent_kwargs = {}

            if instructions is not None:
                agent_kwargs['instructions'] = instructions

            if description is not None:
                agent_kwargs['description'] = description


            if agent.name not in self.non_rag_agent_names: ## loop over all rag agents 

                vector_ids = self.vector_store_ids[agent.name] if self.vector_store_ids and agent.name in self.vector_store_ids else None
                temperature = agent_temperature[agent.name] if agent_temperature and agent.name in agent_temperature else None
                top_p = agent_top_p[agent.name] if agent_top_p and agent.name in agent_top_p else None

                if vector_ids is not None:
                    agent_kwargs['vector_store_ids'] = vector_ids

                if temperature is not None:
                    agent_kwargs['agent_temperature'] = temperature
                else:
                    agent_kwargs['agent_temperature'] = default_temperature

                if top_p is not None:
                    agent_kwargs['agent_top_p'] = top_p
                else:
                    agent_kwargs['agent_top_p'] = default_top_p

                # cmbagent debug --> removed this option, pass in make_vector_stores=True in kwargs
                # #### the files list is appended twice to the instructions.... TBD!!!
                # if agent.set_agent(**agent_kwargs) == 1:

                #     print(f"setting make_vector_stores=['{agent.name.removesuffix('_agent')}'],")
                    
                #     self.push_vector_stores([agent.name.removesuffix('_agent')], chunking_strategy, verbose = verbose)

                #     agent_kwargs['vector_store_ids'] = self.vector_store_ids[agent.name] 

                    
                #     agent.set_agent(**agent_kwargs) 

                # else:
                # see above for trick on how to make vector store if it is not found. 
                agent.set_agent(**agent_kwargs)

            else: ## set all non-rag agents
                
                agent.set_agent(**agent_kwargs)

            ## debug print to help debug
            #print('in cmbagent.py self.agents instructions: ',instructions)
            #print('in cmbagent.py self.agents description: ',description)



        if self.verbose or cmbagent_debug:
            print("Planner instructions:")
            print("\nAll agents:")
            for agent in self.agents:
                print("\n\n----------------------------------")
                print(f"- {agent.name}")
                print(dir(agent))
                print("\n\n----------------------------------")
            print()
            planner = self.get_agent_object_from_name('planner')
            print(planner.info['instructions'])



        select_speaker_prompt_template = select_speaker_prompt if select_speaker_prompt else default_select_speaker_prompt_template
        select_speaker_message_template = select_speaker_message if select_speaker_message else default_select_speaker_message_template
        groupchat_intro_message = intro_message if intro_message else default_groupchat_intro_message

        self.groupchat_intro_message = groupchat_intro_message

        if cmbagent_debug:
            print('\nregistering all hand_offs...')

        register_all_hand_offs(self)

        if cmbagent_debug:
            print('\nall hand_offs registered...')


        if cmbagent_debug:
            print('\nadding functions to agents...')

        register_functions_to_agents(self)

        if cmbagent_debug:
            print('\nfunctions added to agents...')

        self.shared_context = shared_context_default
        if shared_context is not None:
            self.shared_context.update(shared_context)

        if cmbagent_debug:
            print('\nshared_context: ', self.shared_context)

        # Define full paths
        database_full_path = os.path.join(self.work_dir, self.shared_context.get("database_path", "data"))
        codebase_full_path = os.path.join(self.work_dir, self.shared_context.get("codebase_path", "codebase"))
        
        # Create directories if they don't exist
        os.makedirs(database_full_path, exist_ok=True)
        os.makedirs(codebase_full_path, exist_ok=True)
    

    def display_cost(self):
        '''display full cost dictionary'''
        cost_dict = defaultdict(list)
        all_agents = [agent.agent for agent in self.agents] + self.groupchat.new_conversable_agents
        for agent in all_agents:
            if hasattr(agent, 'cost_dict') and agent.cost_dict['Agent']:
                name = agent.cost_dict['Agent'][0].replace('admin (', '').replace(')', '').replace('_', ' ')
                if name in cost_dict['Agent']:
                    idx = cost_dict['Agent'].index(name)
                    for field in ['Cost', 'Prompt Tokens', 'Completion Tokens', 'Total Tokens']:
                        cost_dict[field][idx] += sum(agent.cost_dict[field])
                else:
                    cost_dict['Agent'].append(name)
                    for field in ['Cost', 'Prompt Tokens', 'Completion Tokens', 'Total Tokens']:
                        cost_dict[field].append(sum(agent.cost_dict[field]))
        df = pd.DataFrame(cost_dict)
        columns_to_sum = df.select_dtypes(include='number').columns
        totals = df[columns_to_sum].sum()
        df.loc['Total'] = pd.concat([pd.Series({'Name': 'Total'}), totals])
        display(df)
        return
    

    def update_memory_agent(self):
        
        response = input('''Do you want to save this task summary to the "memory agent" vector stores? This will aid you and others in solving similar tasks in the future. Please only save the task if it has been completed successfully. Type "yes" or "no". ''').strip().lower()
        

        if 'yes' in response:
            print('Asking summarizer to generate summary')
            print('The summary will be json formatted.')
            print('\n\n')
            summary_message = """
            We will now summarize the session.
            """

            previous_state = f"{self.groupchat.messages}"

            # Convert string to Python dictionary
            dict_representation = ast.literal_eval(previous_state)

            # Convert dictionary to JSON string
            json_string = json.dumps(dict_representation)

            # print("previous state: ", json_string)
            # exit()
            last_agent, last_message = self.manager.resume(messages=json_string)

            self.manager.cmbagent_summarizer = True

            self.session = self.summarizer.agent.initiate_chat(recipient=self.manager,
                                                          message=summary_message,
                                                          clear_history=False)


            # Extract the content
            content = self.groupchat.messages[-1]['content']

            # Parse the content string to a Python dictionary
            content_dict = json.loads(content)

            # Save to a JSON file
            id = f'{datetime.datetime.now():%Y-%m-%d_%H:%M:%S}'
            with open(os.getenv('CMBAGENT_DATA')+ '/data/memory/' + f'summary_{id}.json', 'w') as json_file:
                json.dump(content_dict, json_file, indent=4)
            # Pretty-print the JSON
            pretty_json = json.dumps(content_dict, indent=4)

            print("Formatted JSON output:\n")
            print(pretty_json)
            # print("\nNested structure with pprint:\n")
            # pprint(content_dict)
            # id = f'{datetime.datetime.now():%Y-%m-%d_%H:%M:%S}'
            # with open(os.getenv('CMBAGENT_DATA')+ '/data/memory/' + f'summary_{id}.json', 'w') as json_file:
            #     json.dump(pretty_json, json_file, indent=4) 

            # Push to memory agent vector store
            push_vector_stores(self, ['memory'], None, verbose = True)

            print("The memory vector store has been updated. The session will now be closed.")
            # print('Updated memory agent\'s vector stores.')


        if 'yes' not in response:
            print('Task summary not added to memory agent\'s vector stores.')
            return
        
        # previous_state = f"{self.groupchat.messages}"

        # Convert string to Python dictionary
        # dict_representation = ast.literal_eval(previous_state)

        # Convert dictionary to JSON string and save file
        # json_string = json.dumps(dict_representation)
        # id = f'{datetime.datetime.now():%Y-%m-%d_%H:%M:%S}'
        # with open(os.getenv('CMBAGENT_DATA')+ '/data/memory/' + f'summary_{id}.json', 'w') as json_file:
        #     json.dump(json_string, json_file, indent=4)

        # Push to memory agent vector store
        # self.push_vector_stores(['memory'], None, verbose = False)
        # print('Updated memory agent\'s vector stores.')

        return
        


    def solve(self, task, initial_agent='planner', 
              shared_context=None,
              max_rounds=10):
        
        this_shared_context = copy.deepcopy(self.shared_context)
        if shared_context is not None:
            this_shared_context.update(shared_context)
        

        self.clear_cache()

        for agent in self.agents:
            agent.agent.reset()

        this_shared_context['main_task'] = task

        chat_result, context_variables, last_agent = initiate_swarm_chat(
            initial_agent=self.get_agent_from_name(initial_agent),
            agents=[agent.agent for agent in self.agents],
            messages=this_shared_context['main_task'],
            user_agent=self.get_agent_from_name("admin"),
            context_variables=this_shared_context,
            max_rounds = max_rounds,
            after_work=AfterWorkOption.REVERT_TO_USER,
        )


        self.final_context = copy.deepcopy(context_variables)

        self.last_agent = last_agent
        self.chat_result = chat_result



            

        

    def restore(self):
        """
        Restore the previous state of the group chat. 

        This method restores the previous state of the group chat by:
        1. Converting the stored messages back to a Python dictionary.
        2. Converting the dictionary to a JSON string.
        3. Resuming the group chat manager with the restored messages.
        4. Initiating a new chat session with the last active agent and message.

        Returns:
            None
        """

        

        previous_state = f"{self.groupchat.messages}"

        # Convert string to Python dictionary
        dict_representation = ast.literal_eval(previous_state)

        # Convert dictionary to JSON string
        json_string = json.dumps(dict_representation)

        # Prepare the group chat for resuming
        last_agent, last_message = self.manager.resume(messages=json_string)

        if self.agent_type == 'swarm':
            # Resume the chat using the last agent and message
            self.session = last_agent.initiate_cmbagent_swarm_chat(recipient=self.manager,
                                                    message=last_message,
                                                    clear_history=False)

        else:
            # Resume the chat using the last agent and message
            self.session = last_agent.initiate_chat(recipient=self.manager,
                                                message=last_message,
                                                clear_history=False)


    def get_agent_object_from_name(self,name):
        for agent in self.agents:
            if agent.info['name'] == name:
                return agent
        print(f"get_agent_from_name: agent {name} not found")
        sys.exit()

    def get_agent_from_name(self,name):
        for agent in self.agents:
            if agent.info['name'] == name:
                return agent.agent
        print(f"get_agent_from_name: agent {name} not found")
        sys.exit()

    def init_agents(self,agent_llm_configs=None):

        # this automatically loads all the agents from the assistants folder
        imported_rag_agents = import_rag_agents()
        imported_non_rag_agents = import_non_rag_agents()
        # print('imported_rag_agents: ', imported_rag_agents)
        # print("making new rag agents: ", self.make_new_rag_agents)
        # make_rag_agents(self.make_new_rag_agents)
        # imported_rag_agents = import_rag_agents()
        # print('imported_rag_agents: ', imported_rag_agents)

        ## this will store classes for each agents
        self.agent_classes = {}
        self.rag_agent_names = []
        self.non_rag_agent_names = []

        for k in imported_rag_agents.keys():
            self.agent_classes[imported_rag_agents[k]['agent_name']] = imported_rag_agents[k]['agent_class']
            self.rag_agent_names.append(imported_rag_agents[k]['agent_name'])

        for k in imported_non_rag_agents.keys():
            self.agent_classes[imported_non_rag_agents[k]['agent_name']] = imported_non_rag_agents[k]['agent_class']
            self.non_rag_agent_names.append(imported_non_rag_agents[k]['agent_name'])

        if cmbagent_debug:
            print('self.agent_classes: ', self.agent_classes)
            print('self.rag_agent_names: ', self.rag_agent_names)
            print('self.non_rag_agent_names: ', self.non_rag_agent_names)
            # import sys; sys.exit()



        if cmbagent_debug:
            print('self.agent_classes after update: ')
            print()
            for agent_class, value in self.agent_classes.items():
                print(f'{agent_class}: {value}')
                print()
            # sys.exit()

        # all agents

        self.agents = []


        if self.agent_list is None:
            self.agent_list = list(self.agent_classes.keys())

        # Drop entries from self.agent_classes that are not in self.agent_list
        self.agent_classes = {k: v for k, v in self.agent_classes.items() if k in self.agent_list or k in self.non_rag_agent_names}

        if cmbagent_debug:
            print('self.agent_classes after list update: ')
            print()
            for agent_class, value in self.agent_classes.items():
                print(f'{agent_class}: {value}')
                print()
            # sys.exit()

        # remove agents that are not set to be skipped
        if self.skip_memory:
            # self.agent_classes.pop('memory')
            self.agent_classes.pop('summarizer')
        
        if self.skip_executor:
            self.agent_classes.pop('executor')

        if self.skip_rag_software_formatter:
            self.agent_classes.pop('rag_software_formatter')

        if cmbagent_debug:
            print('self.agent_classes after skipping agents: ')
            print()
            for agent_class, value in self.agent_classes.items():
                print(f'{agent_class}: {value}')
                print()
            # sys.exit()

        # instantiate the agents and llm_configs
        if cmbagent_debug:
            print('self.llm_config: ', self.llm_config)


        for agent_name  in self.agent_classes:
            agent_class = self.agent_classes[agent_name]

            if cmbagent_debug:
                print('instantiating agent: ', agent_name)

            if agent_name in agent_llm_configs:
                llm_config = copy.deepcopy(self.llm_config)
                llm_config['config_list'][0].update(agent_llm_configs[agent_name])
                if "reasoning_effort" in llm_config['config_list'][0]:
                    llm_config.pop('temperature')
                    llm_config.pop('top_p')
                
                if cmbagent_debug:
                    print('in cmbagent.py: found agent_llm_configs for: ', agent_name)
                    print('in cmbagent.py: llm_config updated to: ', llm_config)
            else:
                llm_config = copy.deepcopy(self.llm_config)

            if cmbagent_debug:
                print('in cmbagent.py BEFORE agent_instance: llm_config: ', llm_config)

            agent_instance = agent_class(llm_config=llm_config,agent_type=self.agent_type, work_dir=self.work_dir)

            # sys.exit()

            if cmbagent_debug:
                print('agent_type: ', agent_instance.agent_type)

            # setattr(self, agent_name, agent_instance)

            self.agents.append(agent_instance)


        agent_keys = self.agent_classes.keys()

        self.agent_names =  [agent.name for agent in self.agents]

        if cmbagent_debug:
            for agent in self.agents:
                print('\n\nagent.name: ', agent.name)
                print('agent.llm_config: ', agent.llm_config)
                print('\n\n')

        # sys.exit()


        if self.verbose or cmbagent_debug:

            print("Using following agents: ", self.agent_names)
            print("Using following llm for agents: ")
            for agent in self.agents:
                print(f"{agent.name}: {agent.llm_config['config_list'][0]['model']}")
            print()
            # sys.exit()

    def create_assistant(self, client, agent):

        print(f"-->Creating assistant {agent.name}")

        print(f"--> llm_config: {self.llm_config}")

        print(f"--> agent.llm_config: {agent.llm_config}")

        new_assistant = client.beta.assistants.create(
            name=agent.name,
            instructions=agent.info['instructions'],
            tools=[{"type": "file_search"}],
            tool_resources={"file_search": {"vector_store_ids":[]}},
            model=agent.llm_config['config_list'][0]['model'],
            # tool_choice={"type": "function", "function": {"name": "file_search"}}, ## not possible to set tool_choice as argument as of 8/03/2025
            # response_format=agent.llm_config['config_list'][0]['response_format']
        )
        print("New assistant created.")
        print(f"--> New assistant id: {new_assistant.id}")
        print(f"--> New assistant model: {new_assistant.model}")
        # print(f"--> New assistant response format: {new_assistant.response_format}")
        # print(f"--> New assistant tool choice: {new_assistant.tool_choice}")
        print("\n")

        return new_assistant


    def check_assistants(self, reset_assistant=[]):

        client = OpenAI(api_key = self.llm_api_key)
        available_assistants = client.beta.assistants.list(
            order="desc",
            limit="100",
        )


        # Create a list of assistant names for easy comparison
        assistant_names = [d.name for d in available_assistants.data]
        assistant_ids = [d.id for d in available_assistants.data]
        assistant_models = [d.model for d in available_assistants.data]

        for agent in self.agents:

            if cmbagent_debug:
                print('in cmbagent.py check_assistants: agent: ', agent.name)
                print('non_rag_agent_names: ', self.non_rag_agent_names)

            if agent.name not in self.non_rag_agent_names:
                if cmbagent_debug:
                    print(f"Checking agent: {agent.name}")

                # Check if agent name exists in the available assistants
                if agent.name in assistant_names:
                    if cmbagent_debug:
                        print(f"in cmbagent.py check_assistants: Agent {agent.name} exists in available assistants with id: {assistant_ids[assistant_names.index(agent.name)]}")

                    if cmbagent_debug:
                        print('in cmbagent.py check_assistants: this assistant model from openai: ',assistant_models[assistant_names.index(agent.name)])
                        print('in cmbagent.py check_assistants: this assistant model from llm_config: ', agent.llm_config['config_list'][0]['model'])
                    if assistant_models[assistant_names.index(agent.name)] != agent.llm_config['config_list'][0]['model']:
                        if cmbagent_debug:
                            print(f"in cmbagent.py check_assistants: Assistant model from openai does not match the requested model. Updating the assistant model.")
                        client.beta.assistants.update(
                            assistant_id=assistant_ids[assistant_names.index(agent.name)],
                            model=agent.llm_config['config_list'][0]['model']
                        )

                    if reset_assistant and agent.name.replace('_agent', '') in reset_assistant:
                        
                        print("This agent is in the reset_assistant list. Resetting the assistant.")
                        print("Deleting the assistant...")
                        client.beta.assistants.delete(assistant_ids[assistant_names.index(agent.name)])
                        print("Assistant deleted. Creating a new one...")
                        new_assistant = self.create_assistant(client, agent)
                        agent.info['assistant_config']['assistant_id'] = new_assistant.id
                        

                    else:

                        assistant_id = agent.info['assistant_config']['assistant_id']

                        if assistant_id != assistant_ids[assistant_names.index(agent.name)]:
                            print(f"--> Assistant ID between yaml and openai do not match.")
                            print(f"--> Assistant ID from your yaml: {assistant_id}")
                            print(f"--> Assistant ID in openai: {assistant_ids[assistant_names.index(agent.name)]}")
                            print("--> We will use the assistant id from openai")
                            

                            agent.info['assistant_config']['assistant_id'] = assistant_ids[assistant_names.index(agent.name)]
                            print(f"--> Updating yaml file with new assistant id: {assistant_ids[assistant_names.index(agent.name)]}")
                            update_yaml_preserving_format(f"{path_to_assistants}/{agent.name.replace('_agent', '') }.yaml", agent.name, assistant_ids[assistant_names.index(agent.name)], field = 'assistant_id')
                    
                else:

                    new_assistant = self.create_assistant(client, agent)
                    agent.info['assistant_config']['assistant_id'] = new_assistant.id



    def show_plot(self,plot_name):

        return Image(filename=self.work_dir + '/' + plot_name)


    def clear_cache(self):
        autogen.Completion.clear_cache(self.cache_seed)



    def filter_and_combine_agent_names(self, input_list):
        # Filter the input list to include only entries in self.agent_names
        filtered_list = [item for item in input_list if item in self.agent_names]

        # Convert the filtered list of strings into one string
        combined_string = ', '.join(filtered_list)

        return combined_string


    def set_planner_instructions(self):

        # available agents and their roles:
        available_agents = "\n\n#### Available agents and their roles\n\n"
        
        for agent in self.agents:

            if agent.name in ['planner', 'engineer', 'executor', 'admin']:
                continue


            if 'description' in agent.info:

                role = agent.info['description']

            else:

                role = agent.info['instructions']

            available_agents += f"- *{agent.name}* : {role}\n"


        # # collect allowed transitions
        # all_allowed_transitions = "\n\n#### Allowed transitions\n\n"

        # for agent in self.agents:

        #     all_allowed_transitions += f"\t- {agent.name} -> {self.filter_and_combine_agent_names(agent.info['allowed_transitions'])}\n"



        # commenting for now
        # self.planner.info['instructions'] += available_agents + '\n\n' #+ all_allowed_transitions

        return





