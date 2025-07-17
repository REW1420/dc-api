from datetime import datetime, timedelta
from flask import Blueprint, jsonify, request
from services.database_service import execute_query
from utils.config import PAGE_ID
from services.facebook_service import fb_api
from services.sentiment import AnalizadorTransformers
from services.facebook_service import fetch_page_metric
api_blueprint = Blueprint('api', __name__)
analizador = AnalizadorTransformers()


def get_user_page_data(user_id: int):
    result = execute_query(
        """
        SELECT p.page_id, p.page_external_id, u.access_token
        FROM pages p
        JOIN users u ON u.user_id = p.user_id
        WHERE u.user_id = %s
        """,
        (user_id,),
        fetch=True
    )
    if not result:
        raise Exception("Usuario o página no encontrada")
    return result[0]


@api_blueprint.route("/posts")
def get_posts():
    try:
        user_id = request.args.get("user_id", type=int)
        if not user_id:
            return jsonify({"error": "user_id es requerido"}), 400

        user_data = get_user_page_data(user_id)

        posts = execute_query(
            """
            SELECT p.* 
            FROM posts p 
            WHERE p.page_id = %s
            ORDER BY p.created_time DESC
            """,
            (user_data["page_id"],),
            fetch=True
        )
        return jsonify(posts)
    except Exception as e:
        print("Error al obtener posts:", e)
        return jsonify({"error": "Error al obtener posts"}), 500


@api_blueprint.route("/comments")
def get_all_comments():
    """
    Obtiene todos los comentarios desde la API de Facebook para los posts del usuario.
    No guarda en la base de datos, solo analiza sentimiento y retorna.
    """
    try:
        user_id = request.args.get("user_id", type=int)
        if not user_id:
            return jsonify({"error": "user_id es requerido"}), 400

        # Obtener access_token y page_external_id desde la base de datos
        user_data = get_user_page_data(user_id)
        access_token = user_data["access_token"]
        page_external_id = user_data["page_external_id"]

        # Obtener posts de la página
        posts_data = fb_api(f"/{page_external_id}/posts", "GET", {
            "fields": "id"
        }, access_token=access_token)

        all_comments = []

        # Para cada post, obtener sus comentarios
        for post in posts_data.get("data", []):
            post_id = post["id"]
            comments = fb_api(f"/{post_id}/comments", "GET", {
                "fields": "id,message,created_time"
            }, access_token=access_token).get("data", [])

            for comment in comments:
                texto = comment.get("message", "")
                sentimiento = analizador.analizar(
                    texto) if texto.strip() else "neutral"

                all_comments.append({
                    "text": texto,
                    "sentiment": sentimiento
                })

        return jsonify(all_comments)

    except Exception as e:
        print(f"❌ Error al obtener comentarios desde la API: {e}")
        return jsonify({"error": str(e)}), 500


@api_blueprint.route("/metrics/impressions")
def get_page_impressions():
    return _serve_metric("page_impressions")


@api_blueprint.route("/metrics/fans")
def get_page_fans():
    return _serve_metric("page_fans")


@api_blueprint.route("/metrics/views")
def get_page_views():
    return _serve_metric("page_views_total")


def _serve_metric(metric_name):
    try:
        user_id = request.args.get("user_id", type=int)
        only_today = request.args.get("today", "false").lower() == "true"

        if not user_id:
            return jsonify({"error": "user_id es requerido"}), 400

        data = get_insights_from_db(user_id, metric_name, only_today)
        return jsonify(data)

    except Exception as e:
        return jsonify({"error": str(e)}), 500


def get_insights_from_db(user_id: int, metric_name: str, only_today=False):
    user_data = get_user_page_data(user_id)
    page_id = user_data["page_id"]

    query = """
        SELECT name, period, value, end_time
        FROM insights
        WHERE page_id = %s AND name = %s
    """
    params = [page_id, metric_name]

    if only_today:
        query += " AND end_time >= %s"
        today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        params.append(today)

    query += " ORDER BY end_time DESC"

    return execute_query(query, tuple(params), fetch=True)
