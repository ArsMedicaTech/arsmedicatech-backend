from flask import Blueprint, jsonify, request

from lib.services.metrics_service import (get_user_metric_sets,
                                          save_user_metric_set)

metrics_bp = Blueprint('metrics', __name__)

# TODO: Replace with real authentication decorator
# from lib.services.auth_decorators import login_required

def get_authenticated_user_id():
    # TODO: Replace with real session/user lookup
    return request.headers.get('X-User-Id', None)

@metrics_bp.route('/api/users/<user_id>/metrics', methods=['POST'])
def post_user_metrics(user_id: str):
    # user_id from URL must match authenticated user
    auth_user_id = get_authenticated_user_id()
    if not auth_user_id or auth_user_id != user_id:
        return jsonify({'error': 'Unauthorized'}), 401
    data = request.get_json()
    date = data.get('date')
    metrics = data.get('metrics', [])
    if not date or not metrics:
        return jsonify({'error': 'Missing date or metrics'}), 400
    save_user_metric_set(user_id, date, metrics)
    return jsonify({'status': 'success'}), 201

@metrics_bp.route('/api/users/<user_id>/metrics', methods=['GET'])
def get_user_metrics(user_id: str):
    auth_user_id = get_authenticated_user_id()
    if not auth_user_id or auth_user_id != user_id:
        return jsonify({'error': 'Unauthorized'}), 401
    metric_sets = get_user_metric_sets(user_id)
    return jsonify({'metrics': metric_sets}) 