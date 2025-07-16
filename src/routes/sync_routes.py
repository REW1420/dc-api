from flask import request, jsonify, Blueprint
from services.facebook_service import sync_posts, sync_comments, sync_post_reactions_summary, sync_all_page_metrics

sync_blueprint = Blueprint('sync', __name__)


@sync_blueprint.route("/sync-data", methods=["POST"])
def sync_data():
    try:
        user_id = request.args.get("user_id", type=int)
        if not user_id:
            return jsonify({"error": "user_id es requerido"}), 400

        sync_posts(user_id)
        sync_comments(user_id)
        sync_post_reactions_summary(user_id)
        sync_all_page_metrics(user_id)

        return jsonify({"status": "success", "message": "Datos sincronizados correctamente"})
    except Exception as e:
        print(f"❌ Error en sync_data: {str(e)}")
        return jsonify({"error": str(e)}), 500
