import os
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
import json
from typing import Generator

class ChatAgent:
    def __init__(self, model_name="deepseek-chat"):
        """Initialize the ChatAgent with specified model."""
        self.model = ChatOpenAI(
            model_name=model_name, 
            temperature=0.7, 
            streaming=True,
            openai_api_key=os.getenv("DEEPSEEK_API_KEY"),
            openai_api_base="https://api.deepseek.com/v1"
        )
        # Define required fields (these must be filled)
        self.required_fields = ["name", "city", "days", "budget", "people", "kids", "health", "hobbies", "start_date", "accommodation_preference"]
        # Define all fields, including optional ones
        self.all_fields = self.required_fields + ["specificRequirements"]
        self.conversation_history = []
        
    def _init_system_message(self):
        """Initialize system message for the conversation."""
        return SystemMessage(content="""
        You are a helpful travel assistant. Your job is to collect information about the user's travel plans.
        Be friendly, conversational, and help the user plan their trip. Collect all necessary information.
        Also pay attention to any specific requirements the traveler mentions, such as accessibility needs,
        food restrictions, special interests, or any constraints that might affect their trip. Remind always answer in English.
        """)
        
    def collect_info(self, user_input: str, state: dict = None) -> dict:
        """Check for missing information and ask user questions to complete the required information."""
        if state is None:
            state = {}
        
        # Initialize conversation if it's empty
        if not self.conversation_history:
            self.conversation_history.append(self._init_system_message())
        
        # Merge new inputs into state
        if user_input and user_input.strip():
            new_info = self.extract_info_from_message(user_input)
            print(f"[DEBUG] Extracted info: {new_info}")  # Debug extracted info
            for field, value in new_info.items():
                if value:
                    state[field] = value
                    print(f"[DEBUG] Updated state: {field} = {value}")  # Debug log
            
            # Debug: Check current state after update
            print(f"[DEBUG] Current state after update: {state}")
            print(f"[DEBUG] Missing fields: {[f for f in self.required_fields if not state.get(f)]}")
            print(f"[DEBUG] Complete status: {len([f for f in self.required_fields if not state.get(f)]) == 0}")
        
        # Add user input to conversation if not empty
        if user_input and user_input.strip():
            self.conversation_history.append(HumanMessage(content=user_input))
        
        # Get AI response based on current state and conversation history
        messages = self.conversation_history.copy()
        
        missing_fields = [f for f in self.required_fields if not state.get(f)]
        
        # Only prompt for missing information if there are actually missing fields
        if missing_fields:
            messages.append(SystemMessage(content=f"""
            Current state: {json.dumps(state, ensure_ascii=False)}
            Required fields: {json.dumps(self.required_fields, ensure_ascii=False)}
            Missing fields: {json.dumps(missing_fields, ensure_ascii=False)}
            Please help the user complete the missing information in a natural way.
            Remember to acknowledge information that has already been provided.
            Tell the user that they can write \"not decided\" for the start date if they don't have a specific date in mind.
            Also pay attention to any specific requirements they mention and reflect these in your responses.
            """))
        else:
            # All required information is complete - move to next step
            messages.append(SystemMessage(content=f"""
            All required travel information has been collected. Current state: {json.dumps(state, ensure_ascii=False)}
            
            Please provide helpful travel recommendations based on the user's preferences.
            Acknowledge that their information is complete and move forward with suggestions.
            Focus on their specific interests: {state.get('hobbies', '')} and any other preferences they mentioned.
            
            Do not ask for confirmation of information that has already been provided.
            Do not repeat the information back to the user unless it's relevant to your recommendations.
            """))
        
        try:
            response = self.model.stream(messages)
            return {
                "stream": response,
                "missing_fields": [f for f in self.required_fields if not state.get(f)],
                "complete": len([f for f in self.required_fields if not state.get(f)]) == 0,
                "state": state.copy()
            }
        except Exception as e:
            print(f"Error getting AI response: {e}")
            return {
                "stream": None,
                "missing_fields": [f for f in self.required_fields if not state.get(f)],
                "complete": False,
                "state": state.copy(),
                "error": str(e)
            }
    
    def interact_with_user(self, message: str, state: dict = None) -> Generator:
        """Process user message and generate a streaming response."""
        if state is None:
            state = {}
            
        # Add user message to conversation
        self.conversation_history.append(HumanMessage(content=message))
        
        # Generate streaming response based on the conversation history
        try:
            return self.model.stream(self.conversation_history)
        except Exception as e:
            print(f"Error in interact_with_user: {e}")
            return None
    
    def extract_info_from_message(self, message: str) -> dict:
        """Use LLM to extract structured travel information from user message."""
        system_prompt = f"""Extract the following travel information from the user's message and return JSON.
        Carefully analyze the message to understand both explicit and implicit information.
        
        For example, if the user says "without kids" or "no children", set "kids" to "no".
        If they mention "all adults", also set "kids" to "no".
        If they mention family with children, set "kids" to "yes".
        If the user mentions hotel preference, like "budget hostel" or "with swimming pool", enter them into the “accommodation preference” field.
        The people field should be an integer.
        Specifically, if the user gives a start date, set "start_date" in YYYY-MM-DD format string. Otherwise, set "start_date" to "not decided".
        Pay attention to negations and context. Don't just look for keywords, understand the meaning.
        
        IMPORTANT: Also extract any specific requirements, constraints, or special requests the user mentions. 
        This includes but is not limited to:
        - Accessibility needs (e.g., wheelchair access, limited mobility)
        - Food restrictions or dietary preferences
        - Special interests or experiences they want to have
        - Particular constraints (e.g., fear of heights, need quiet accommodations)
        - Any important preferences not covered by other fields
        
        Return the following JSON structure:
        {{
        {', '.join([f'"{field}": ""' for field in self.all_fields])}
        }}
        
        For required fields, if any information is missing or unclear, leave it as an empty string.
        For specificRequirements, capture any important preferences or constraints mentioned by the user.
        
        IMPORTANT: Return ONLY the JSON object, without any code block markers like ```json or ```.
        """
        
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=message)
        ]

        try:
            llm_response = self.model.invoke(messages)
            
            # 添加JSON解析的容错处理
            content = llm_response.content.strip()
            
            # 清理代码块标记
            if content.startswith('```json'):
                content = content[7:]  # 移除 ```json
            if content.startswith('```'):
                content = content[3:]  # 移除 ```
            if content.endswith('```'):
                content = content[:-3]  # 移除结尾的 ```
            content = content.strip()
            
            print(f"[DEBUG] Cleaned LLM content: {content}")  # 调试清理后的内容
            
            # 尝试解析JSON，如果失败则返回空结果
            try:
                extracted_info = json.loads(content)
            except json.JSONDecodeError as e:
                print(f"JSON解析错误: {e}")
                print(f"LLM返回内容: {content}")
                return {}

            # Only update fields that have non-empty values
            filtered_info = {}
            for field in self.all_fields:
                value = extracted_info.get(field, "")
                if value:  # Only include non-empty values
                    filtered_info[field] = value

            return filtered_info 
        except Exception as e:
            print("Error in extract_info_from_message:", e)
            return {}
        

    