from cmbagent.utils import *

from cmbagent.assistants.base_agent import BaseAgent

logger = logging.getLogger(__name__)

class ActAgent(BaseAgent):

    def __init__(self, llm_config=None, **kwargs):

        agent_id = os.path.splitext(os.path.abspath(__file__))[0]

        super().__init__(llm_config=llm_config, agent_id=agent_id, **kwargs)


    def set_agent(self, additional_param=None):
        # Call the superclass set_agent method if needed
        super().set_agent()

        # Additional logic specific to ClassyAgent
        if additional_param:
            self.agent.additional_param = additional_param



