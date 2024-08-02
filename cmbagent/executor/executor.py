import os
from cmbagent.assistants.base_agent import BaseAgent

class ExecutorAgent(BaseAgent):
    
    def __init__(self, llm_config=None, **kwargs):

        agent_id = os.path.splitext(os.path.abspath(__file__))[0]

        super().__init__(llm_config=llm_config, agent_id=agent_id, **kwargs)


    def set_agent(self):

        super().set_coder_agent()



