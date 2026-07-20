import os
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage
import json

class CommunicationAgent:
    def __init__(self, model_name="deepseek-chat"):
        """Initialize the CommunicationAgent with specified model."""
        self.model = ChatOpenAI(
            model_name=model_name, 
            temperature=0.7,
            openai_api_key=os.getenv("DEEPSEEK_API_KEY"),
            openai_api_base="https://api.deepseek.com/v1"
        )
    
    def post_car_rental_request(self, location, duration, user_prefs):
        """Generate car rental request post."""
        # Convert duration to integer if it's a string
        duration = int(duration) if isinstance(duration, str) else duration
        
        # Get user preferences with defaults and proper type conversion
        num_people = int(user_prefs.get('people', 1)) if isinstance(user_prefs.get('people'), str) else user_prefs.get('people', 1)
        has_kids = user_prefs.get('kids', False)
        if isinstance(has_kids, str):
            has_kids = has_kids.lower() == 'yes' or has_kids.lower() == 'true'
        budget_level = user_prefs.get('budget', 'medium')
        
        # Format the prompt with consistent information
        prompt = f"""
        Generate a car rental request post for the following trip:
        
        Location: {location}
        Duration: {duration} days
        Number of people: {num_people}
        Kids: {'Yes' if has_kids else 'No'}
        Budget level: {budget_level}
        
        The post should be polite, clear, and include all necessary information.
        {f'Include a request for child seats if available.' if has_kids else ''}
        Make sure the information about kids and budget matches exactly with the provided details.
        """
        
        messages = [
            SystemMessage(content="You are a helpful assistant creating a car rental request post. Ensure all information is accurate and matches the provided details exactly."),
            HumanMessage(content=prompt)
        ]
        
        response = self.model.invoke(messages)
        
        # Return structured data with consistent information
        return {
            "post_content": response.content,
            "location": location,
            "duration": duration,
            "status": "pending",
            "user_prefs": {
                "num_people": num_people,
                "has_kids": has_kids,
                "budget_level": budget_level
            }
        }
    
    def handle_rental_response(self, rental_post, response_message):
        """Handle response to car rental request."""
        prompt = f"""
        A car rental company has responded to the following car rental request:
        
        Original request:
        {rental_post['post_content']}
        
        Their response:
        {response_message}
        
        Please draft a polite reply that:
        1. Thanks them for their response
        2. Asks any necessary follow-up questions about pricing, car type, pickup details, etc.
        3. Is friendly and professional
        """
        
        messages = [
            SystemMessage(content="You are a helpful assistant handling communications about car rentals."),
            HumanMessage(content=prompt)
        ]
        
        response = self.model.invoke(messages)
        
        return {
            "reply_content": response.content,
            "original_post": rental_post,
            "response_message": response_message
        }
    
    def generate_booking_confirmation(self, itinerary, budget_estimate, car_rental=None, user_name=None):
        """Generate booking confirmation message."""
        itinerary_summary = f"{len(itinerary)} days, starting on {itinerary[0]['date'] if itinerary else 'N/A'}"
        attractions_count = sum(len(day['spots']) for day in itinerary) if itinerary else 0
        name = user_name if user_name else "Traveler"
        itinerary_json = json.dumps(itinerary, ensure_ascii=False, indent=2)
        
        # Only include car rental information if it's recommended
        car_rental_prompt = f"\nCar rental: {'Yes' if car_rental else 'No'}" if car_rental else ""
        
        prompt = f"""
        请为 {name} 生成中文旅行规划结果，不要写邮件，不要写 Subject，不要说附件。
        这不是订单确认邮件，而是产品结果页展示的最终旅行计划说明。
        
        Itinerary: {itinerary_summary}
        Number of attractions: {attractions_count}
        Estimated budget: ${budget_estimate['total']}{car_rental_prompt}

        完整每日行程 JSON：
        {itinerary_json}

        输出必须使用中文，并严格包含以下结构：
        ## 行程概览
        - 用 2-4 句话概括目的地、日期、天数、预算与整体节奏。

        ## 温馨提示
        - 给出实用提醒，例如天气、交通、预算、餐厅预约、酒店入住、体力安排。

        ## 每日具体行程
        - 每天单独列出。
        - 每一天必须尽量包含：时间、地点、午饭、晚饭。
        - 如果 JSON 里没有午饭或晚饭，请基于当天地点给出餐饮类型建议，不要编造已预订餐厅。

        禁止输出英文邮件格式、主题行、英文问候、英文落款、附件提示等表达。
        """
        
        messages = [
            SystemMessage(content="你是中文旅行规划助手 TripAgent。必须输出中文，且严格包含：行程概览、温馨提示、每日具体行程。每日具体行程必须写清时间、地点、午饭、晚饭。不要输出邮件格式，不要写 Subject，不要提附件。"),
            HumanMessage(content=prompt)
        ]
        
        response = self.model.invoke(messages)
        
        return response.content
