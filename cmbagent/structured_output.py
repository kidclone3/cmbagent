from pydantic import BaseModel, Field
from typing import List, Optional


# engineer response

class EngineerResponse(BaseModel):
    # steps: list[Step]
    # step: Step
    code_explanation: str = Field(..., description="The code explanation")
    python_code:  str = Field(..., description="The Python code in a form ready to execute")
    current_status_and_next_step_suggestion: str = Field(..., description="Current status and next step suggestion")
    next_agent_suggestion: str = Field(..., description="The name of the next agent to consult")

    def format(self) -> str:
        return f"""
**Code Explanation:**

{self.code_explanation}

**Python Code:**

```python
{self.python_code}
```

**Current Status and Next Step Suggestion:**

{self.current_status_and_next_step_suggestion}

**Next Agent Suggestion:**

{self.next_agent_suggestion}
        """

# planner response

class Subtasks(BaseModel):
    sub_task: str
    sub_task_agent: str


class PlannerResponse(BaseModel):
    main_task: str
    sub_tasks: list[Subtasks]
    next_step_suggestion: str
    next_agent_suggestion: str

    def format(self) -> str:
        plant_output = "\n".join(
            f"\n- Step {i + 1}:\n\t * sub-task: {step.sub_task}\n\t * agent in charge: {step.sub_task_agent}\n\t" for i, step in enumerate(self.sub_tasks)
        )
        message = f"""
**PLAN**

- Main task: {self.main_task}

{plant_output}

**Next Step Suggestion:**

{self.next_step_suggestion}

**Next Agent Suggestion:**

{self.next_agent_suggestion}
        """
        return message

class SubtaskSummary(BaseModel):
    sub_task: str
    result: str
    feedback: str
    agent: str

class SummarizerResponse(BaseModel):
    main_task: str
    results: str
    summary: List[SubtaskSummary]

    def format(self) -> str:
        summary_output = "\n".join(
            f"- {step.sub_task}:\n\t * result: {step.result}\n\t * feedback: {step.feedback}\n\t * agent: {step.agent}\n"
            for step in self.summary
        )
        return f"""
**SUMMARY REPORT:**

- Main task: {self.main_task}

- Overall Results:

{self.results}

**Detailed Summary:**

{summary_output}
        """


### GPT RAG assistant response


class FileResult(BaseModel):
    file_name: str = Field(..., description="The name of the consulted file")

class RetrievalTask(BaseModel):
    description: str = Field(..., description="The retrieval task being performed")

class CodeExplanation(BaseModel):
    explanation: Optional[str] = Field(None, description="Explanation of the Python code")

class PythonCode(BaseModel):
    code: Optional[str] = Field(None, description="The Python code retrieved or generated")

class CurrentStatusAndNextStep(BaseModel):
    status_and_next_step_suggestion: str = Field(..., description="""
    State where we are in the PLAN and suggest what to do next according to the PLAN or based on previous <admin> feedback. If the suggestion doesnt follow the PLAN, a justification must be provided. 
    Start with: 'We are on Step <i> of the PLAN. Next, if you would like, let us ...'. 
    If we are at the last step of the PLAN, then <current_status_and_next_step_suggestion> should be 'We are at the last step of the PLAN. Unless you have further requests, we can end the session. What would you like to do?' 
    It must end with: 'Should we proceed?'
    """)

class RagSoftwareFormatterResponse(BaseModel):
    retrieval_task: RetrievalTask = Field(..., description="Details of the retrieval task")
    files_consulted: List[FileResult] = Field(..., description="List of consulted files")
    code_explanation: CodeExplanation = Field(..., description="Explanation of the retrieved or generated code")
    python_code: PythonCode = Field(..., description="The Python code block")
    current_status_and_next_step: CurrentStatusAndNextStep = Field(..., description="Current status and next step suggestion")
    next_agent_suggestion: str = Field(..., description="The name of the next agent to consult")

    def format(self) -> str:
        files = "\n".join(f"- {file.file_name}" for file in self.files_consulted)
        code_explanation = self.code_explanation.explanation or "No explanation provided."
        python_code = self.python_code.code or "No code provided."
        current_status_and_next_step_suggestion = self.current_status_and_next_step.status_and_next_step_suggestion 
        next_agent_suggestion = self.next_agent_suggestion

        return f"""
**File Search Results:**

{self.retrieval_task.description}

**Files Consulted:**

{files}

**Code Explanation:**

{code_explanation}

**Python Code:**

```python
{python_code}
```
\n
**Current Status and Next Step Suggestion:**

{current_status_and_next_step_suggestion}

**Next Agent Suggestion:**

{next_agent_suggestion}
        """