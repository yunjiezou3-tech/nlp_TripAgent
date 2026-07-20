from flask import Flask, render_template, request, jsonify, session, send_from_directory, send_file, Response
from flask_session import Session
from flask_cors import CORS
import os
import json
import math
from dotenv import load_dotenv
from workflows.travel_graph import TravelGraph
import requests
import time

# Load environment variables
load_dotenv('.env.development')

app = Flask(__name__, static_folder="frontend/static", template_folder="frontend/templates")
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "travel-ai-secret")

# Configure session
app.config['SESSION_TYPE'] = 'filesystem'
app.config['SESSION_PERMANENT'] = True
app.config['PERMANENT_SESSION_LIFETIME'] = 3600  # 1 hour
app.config['SESSION_COOKIE_SECURE'] = False
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'

# Initialize Flask-Session
Session(app)

# Configure CORS - Allow all localhost ports for development
CORS(app, origins=["http://localhost:5173", "http://localhost:3000", "http://localhost:8080", "http://localhost:8081", "http://localhost:8082", "http://localhost:8083", "http://localhost:8084", "http://localhost:8085", "http://127.0.0.1:5173", "http://127.0.0.1:3000", "http://127.0.0.1:8080", "http://127.0.0.1:8081", "http://127.0.0.1:8082", "http://127.0.0.1:8083", "http://127.0.0.1:8084", "http://127.0.0.1:8085"], supports_credentials=True)

# Add static file configuration
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0  # Disable caching
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size

# Create a session store for workflows
workflows = {}
PUBLIC_INTERNAL_ERROR = {
    'code': 'internal_error',
    'error': '处理请求失败，请稍后重试。',
}
PUBLIC_INVALID_REQUEST = {
    'code': 'invalid_request',
    'error': '请求格式无效。',
}
PUBLIC_STREAM_ERROR = {
    'type': 'error',
    'code': 'stream_error',
    'error': '流式响应失败，请稍后重试。',
}
PUBLIC_ERROR_CODES = frozenset({
    'internal_error',
    'invalid_provider_response',
    'invalid_request',
    'invalid_selection',
    'invalid_stay_criteria',
    'no_offers',
    'past_date',
    'provider_unavailable',
    'recommendation_error',
    'selection_unavailable',
    'stream_error',
    'unrecognized_date',
})

API_COMPLETION_FIELDS = (
    'attractions',
    'restaurants',
    'hotels',
    'selected_attractions',
    'selected_restaurants',
    'selected_hotel',
    'place_errors',
    'map_data',
    'itinerary',
    'budget',
    'response',
    'optimal_route',
    'rental_post',
    'ai_recommendation_generated',
    'user_input_processed',
    'hotel_candidates',
    'hotel_recommendations',
    'recommended_hotel_id',
    'booking_context',
    'booking_drafts',
    'booking_missing_fields',
    'booking_mode',
    'booking_candidates',
    'active_draft_type',
    'traveler_profiles',
    'candidate_delta',
    'information_refinement',
    'information_message',
    'candidate_search_state',
    'candidate_price_context',
    'current_date',
    'trip_date_status',
)


def _completion_fields(result, state):
    state = state if isinstance(state, dict) else {}
    return {
        field: result[field] if field in result else state.get(field)
        for field in API_COMPLETION_FIELDS
    }


def _json_safe(value, *, _seen=None, _depth=0):
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if _depth >= 50:
        return None

    if _seen is None:
        _seen = set()
    value_id = id(value)
    if value_id in _seen:
        return None

    if isinstance(value, dict):
        _seen.add(value_id)
        projected = {
            key: _json_safe(item, _seen=_seen, _depth=_depth + 1)
            for key, item in value.items()
            if isinstance(key, str)
        }
        _seen.remove(value_id)
        return projected
    if isinstance(value, (list, tuple)):
        _seen.add(value_id)
        projected = [
            _json_safe(item, _seen=_seen, _depth=_depth + 1)
            for item in value
        ]
        _seen.remove(value_id)
        return projected
    return None


def _sanitize_diagnostic_value(value, fallback_code):
    if value is None:
        return None
    if isinstance(value, str) and value in PUBLIC_ERROR_CODES:
        return value
    if isinstance(value, dict):
        return {
            key: _sanitize_diagnostic_value(item, fallback_code)
            for key, item in value.items()
            if isinstance(key, str)
        }
    if isinstance(value, (list, tuple)):
        return [
            _sanitize_diagnostic_value(item, fallback_code) for item in value
        ]
    return fallback_code


def _sanitize_public_payload(value):
    if isinstance(value, dict):
        sanitized = {}
        for key, item in value.items():
            if not isinstance(key, str):
                continue
            if key == 'error':
                if item is None:
                    sanitized[key] = None
                elif isinstance(item, str) and item in PUBLIC_ERROR_CODES:
                    sanitized[key] = item
                else:
                    sanitized[key] = PUBLIC_INTERNAL_ERROR['error']
            elif key == 'errors':
                sanitized[key] = _sanitize_diagnostic_value(
                    item, 'internal_error'
                )
            elif key in {
                'place_errors',
                'last_error',
                'diagnostic',
                'diagnostics',
            } or key.endswith('_error'):
                sanitized[key] = _sanitize_diagnostic_value(
                    item, 'provider_unavailable'
                )
            else:
                sanitized[key] = _sanitize_public_payload(item)
        return sanitized
    if isinstance(value, (list, tuple)):
        return [_sanitize_public_payload(item) for item in value]
    return value


def _project_public_payload(value):
    return _sanitize_public_payload(_json_safe(value))


def _valid_session_id(value):
    return value.strip() if isinstance(value, str) and value.strip() else None


def _resolve_session_id(
    explicit_session_id=None, *, generate=True, create_workflow=True
):
    session_id = _valid_session_id(explicit_session_id) or _valid_session_id(
        session.get('session_id')
    )
    if session_id is None and generate:
        session_id = os.urandom(16).hex()
    if session_id is not None:
        session['session_id'] = session_id
    if create_workflow and session_id not in workflows:
        workflows[session_id] = TravelGraph()
    return session_id

@app.route('/test-image')
def test_image():
    return send_file('frontend/static/images/background.jpg', mimetype='image/jpeg')

@app.route('/static/images/<path:filename>')
def serve_image(filename):
    return send_from_directory('frontend/static/images', filename)

@app.route('/')
def index():
    """Render the main page"""
    # Initialize a new workflow for this session if needed
    session_id = session.get('session_id', None)
    if not session_id:
        session_id = os.urandom(16).hex()
        session['session_id'] = session_id
        workflows[session_id] = TravelGraph()
        print(f"[DEBUG] Created new session: {session_id}")
    else:
        print(f"[DEBUG] Using existing session: {session_id}")
    
    # Load popular attractions
    try:
        with open('frontend/data/popular_attractions.json', 'r') as f:
            popular_attractions = json.load(f)
    except FileNotFoundError:
        popular_attractions = []
    
    return render_template('index.html', popular_attractions=popular_attractions)

@app.route('/api/process', methods=['POST'])
def process():
    """Process a step in the travel planning workflow"""
    try:
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            return jsonify(PUBLIC_INVALID_REQUEST), 400
        request_session_id = _resolve_session_id(data.get('session_id'))
        
        workflow = workflows[request_session_id]
        # Keep only critical step information for logging
        app.logger.debug("processing workflow step")
        # Process the current step
        step_name = data.get('step', 'chat')
        process_data = dict(data)
        process_data.pop('step', None)
        process_data.pop('session_id', None)
        result = workflow.process_step(
            step_name, session_id=request_session_id, **process_data
        )
        
        # Handle stream generator - convert to list of messages
        if 'stream' in result and result['stream']:
            stream_content = []
            for chunk in result['stream']:
                if hasattr(chunk, 'content'):
                    stream_content.append(chunk.content)
                elif isinstance(chunk, str):
                    stream_content.append(chunk)
            result['stream'] = stream_content
        
        # Add the current state to the result
        result['state'] = workflow.get_current_state()
        result.update(_completion_fields(result, result['state']))
        return jsonify(_project_public_payload(result))
    except Exception as error:
        app.logger.error("process request failed: %s", type(error).__name__)
        return jsonify(PUBLIC_INTERNAL_ERROR), 500

@app.route('/api/attractions/<city>')
def get_attractions(city):
    """Get attractions for a specific city"""
    session_id = session.get('session_id')
    
    if not session_id or session_id not in workflows:
        return jsonify({"error": "Session not found"}), 404
    
    workflow = workflows[session_id]
    info_agent = workflow.info_agent
    
    attractions = info_agent.get_attractions(city)
    return jsonify(attractions)

@app.route('/api/reset')
def reset_session():
    """Reset the current session"""
    explicit_session_id = _valid_session_id(request.args.get('session_id'))
    active_session_id = _valid_session_id(session.get('session_id'))
    target_session_id = explicit_session_id or active_session_id

    if target_session_id:
        workflows.pop(target_session_id, None)
    if target_session_id == active_session_id:
        session.pop('session_id', None)
    return jsonify({"status": "session reset"})

@app.route('/api/stream')
def stream():
    """Handle streaming responses"""
    request_session_id = _resolve_session_id(request.args.get('session_id'))
    workflow = workflows[request_session_id]
    
    # Keep only critical step information for logging
    app.logger.debug("streaming workflow step")
    
    # Get parameters from request
    step_name = request.args.get('step', 'chat')
    user_input = request.args.get('user_input', '')
    selected_attraction_ids = request.args.get('selected_attraction_ids')
    selected_restaurant_ids = request.args.get('selected_restaurant_ids')
    selected_hotel_id = request.args.get('selected_hotel_id')
    ai_recommendation_generated = request.args.get('ai_recommendation_generated')
    user_input_processed = request.args.get('user_input_processed')
    
    def parse_json_list(value):
        if not value:
            return None
        try:
            parsed_value = json.loads(value)
            return parsed_value if isinstance(parsed_value, list) else None
        except json.JSONDecodeError:
            return None

    selected_attraction_ids = parse_json_list(selected_attraction_ids)
    selected_restaurant_ids = parse_json_list(selected_restaurant_ids)
    
    def parse_bool(value):
        if value is None:
            return None
        return str(value).lower() in ('true', '1', 'yes')
    
    ai_recommendation_generated = parse_bool(ai_recommendation_generated)
    user_input_processed = parse_bool(user_input_processed)
            
    # Check if the user is confirming satisfaction with the recommendation
    satisfaction_message = 'satisfied with your recommendation' in user_input.lower()
    
    if satisfaction_message:
        app.logger.debug("satisfaction message detected")
    
    def generate():
        try:
            # Process the step
            result = workflow.process_step(
                step_name, 
                session_id=request_session_id,
                user_input=user_input,
                selected_attraction_ids=selected_attraction_ids,
                selected_restaurant_ids=selected_restaurant_ids,
                selected_hotel_id=selected_hotel_id,
                ai_recommendation_generated=ai_recommendation_generated,
                user_input_processed=user_input_processed
            )
            
            app.logger.debug("workflow step processed")
            
            # Handle streaming response
            if 'stream' in result and result['stream']:
                for chunk in result['stream']:
                    content = chunk if isinstance(chunk, str) else getattr(
                        chunk, 'content', None
                    )
                    if content:
                        safe_content = _project_public_payload(content)
                        if safe_content is None:
                            raise TypeError("Unsafe stream chunk")
                        chunk_data = {'type': 'chunk', 'content': safe_content}
                        yield f"data: {json.dumps(chunk_data, ensure_ascii=False)}\n\n"
                        time.sleep(0.01)
            
            # Send completion data
            result_state = result.get('state')
            if not isinstance(result_state, dict):
                result_state = workflow.get_current_state()
            completion_data = {
                'type': 'complete',
                'next_step': result.get('next_step'),
                'missing_fields': result.get('missing_fields', []),
                'state': result_state,
                **_completion_fields(result, result_state),
            }
            
            # Only override next_step in specific cases
            if step_name == 'strategy':
                current_state = workflow.get_current_state()
                current_ai_recommendation_generated = current_state.get('ai_recommendation_generated', False)
                should_rent_car = current_state.get('should_rent_car', False)
                
                app.logger.debug("evaluating strategy stream transition")
                
                # If the AI has provided recommendations (whether through initial selection or satisfaction confirmation)
                if current_ai_recommendation_generated or satisfaction_message:
                    # IMPORTANT: Double-check the should_rent_car value from the current state
                    next_step = 'communication' if should_rent_car else 'route'
                    completion_data['next_step'] = next_step
                    app.logger.debug("strategy stream transition selected")
                    
                    # Add explicit note about car recommendation decision
                    if should_rent_car:
                        app.logger.debug("strategy selected communication step")
                    else:
                        app.logger.debug("strategy selected route step")
                
            public_completion = _project_public_payload(completion_data)
            yield f"data: {json.dumps(public_completion, ensure_ascii=False)}\n\n"
            
            # Verify the final decision after sending the completion data
            app.logger.debug("stream completion sent")
            
        except Exception as error:
            app.logger.error("stream request failed: %s", type(error).__name__)
            yield f"data: {json.dumps(PUBLIC_STREAM_ERROR, ensure_ascii=False)}\n\n"
    return Response(generate(), mimetype='text/event-stream')

@app.route('/api/nearby/<attraction_id>')
def get_nearby_places(attraction_id):
    """Get nearby restaurants and street information for an attraction"""
    request_session_id = request.args.get('session_id')
    session_id = request_session_id or session.get('session_id')
    
    if not session_id:
        return jsonify({"error": "Session not found"}), 404
    
    if session_id not in workflows:
        workflows[session_id] = TravelGraph()
    session['session_id'] = session_id
    
    workflow = workflows[session_id]
    info_agent = workflow.info_agent
    
    # Parse coordinates from attraction_id
    try:
        lat_str, lng_str = attraction_id.split(',')
        lat, lng = float(lat_str), float(lng_str)
    except Exception:
        return jsonify({"error": "Invalid coordinates format. Use 'lat,lng'."}), 400
    
    try:
        result = info_agent.search_nearby_places(lat, lng)
        return jsonify(_project_public_payload(result))
    except Exception as error:
        app.logger.error("nearby request failed: %s", type(error).__name__)
        return jsonify(PUBLIC_INTERNAL_ERROR), 500
    
def find_available_port(start_port=8000, max_attempts=10):
    """查找可用的端口"""
    import socket
    
    for port in range(start_port, start_port + max_attempts):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind(('127.0.0.1', port))
                return port
        except OSError:
            continue
    raise RuntimeError(f"无法在端口 {start_port} 到 {start_port + max_attempts - 1} 之间找到可用端口")

if __name__ == '__main__':
    # Create data directory if it doesn't exist
    os.makedirs('data', exist_ok=True)
    
    # Create a sample attractions.json file if it doesn't exist
    if not os.path.exists('data/attractions.json'):
        sample_data = {
            "Paris": [
                {
                    "id": "eiffel_tower",
                    "name": "Eiffel Tower",
                    "category": "landmark",
                    "location": {"lat": 48.8584, "lng": 2.2945},
                    "estimated_duration": 3,
                    "price_level": 3
                },
                {
                    "id": "louvre_museum",
                    "name": "Louvre Museum",
                    "category": "museum",
                    "location": {"lat": 48.8606, "lng": 2.3376},
                    "estimated_duration": 4,
                    "price_level": 2
                }
            ],
            "New York": [
                {
                    "id": "central_park",
                    "name": "Central Park",
                    "category": "nature",
                    "location": {"lat": 40.7812, "lng": -73.9665},
                    "estimated_duration": 3,
                    "price_level": 0
                },
                {
                    "id": "empire_state_building",
                    "name": "Empire State Building",
                    "category": "landmark",
                    "location": {"lat": 40.7484, "lng": -73.9857},
                    "estimated_duration": 2,
                    "price_level": 3
                }
            ]
        }
        
        with open('data/attractions.json', 'w') as f:
            json.dump(sample_data, f)
    
    # 获取端口配置
    import os
    base_port = int(os.environ.get('PORT', 8002))
    
    # 查找可用端口
    port = find_available_port(base_port)
    
    # 如果端口与默认值不同，打印提示信息
    if port != base_port:
        print(f"[INFO] 端口 {base_port} 被占用，使用端口 {port}")
    
    print(f"[INFO] 后端服务启动在: http://127.0.0.1:{port}")
    
    # 运行应用
    app.run(host="127.0.0.1", port=port, debug=False)
