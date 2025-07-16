from datetime import datetime
import requests
from utils.config import PAGE_ID, ACCESS_TOKEN
from services.database_service import execute_query, insert_many, insert_many_resolving_fk
# from services.sentiment_service import analizar_sentimiento
from services.sentiment import AnalizadorTransformers


analizar_sentimiento = AnalizadorTransformers()


def get_user_access_data(user_id: int):
    result = execute_query(
        """
        SELECT u.access_token, p.page_external_id, p.page_id
        FROM users u
        JOIN pages p ON u.user_id = p.user_id
        WHERE u.user_id = %s
        """,
        (user_id,),
        fetch=True
    )
    if not result:
        raise Exception("Usuario o página no encontrados.")
    return result[0]  # acceso_token, page_external_id, page_id


def fb_api(path, method="GET", params=None, access_token=None):
    url = f"https://graph.facebook.com/v18.0{path}"
    if params is None:
        params = {}
    params["access_token"] = access_token

    try:
        response = requests.request(method, url, params=params)
        response.raise_for_status()
        data = response.json()

        if "error" in data:
            raise Exception(data["error"].get("message", "Unknown error"))
        return data
    except requests.exceptions.RequestException as e:
        raise Exception(f"Error en la solicitud HTTP: {str(e)}")


def sync_posts(user_id: int):
    try:
        user_data = get_user_access_data(user_id)
        access_token = user_data["access_token"]
        page_external_id = user_data["page_external_id"]

        fb_posts = fb_api(f"/{page_external_id}/posts", "GET", {
            "fields": "id,message,created_time"
        }, access_token=access_token).get("data", [])

        existing = execute_query(
            "SELECT post_external_id FROM posts WHERE page_id = %s",
            (user_data["page_id"],),
            fetch=True
        )
        existing_ids = [p["post_external_id"] for p in existing]

        new_posts = [{
            "post_external_id": post["id"],
            "page_id": user_data["page_id"],
            "message": post.get("message"),
            "created_time": post["created_time"]
        } for post in fb_posts if post["id"] not in existing_ids]

        if new_posts:
            insert_many("posts", new_posts)

    except Exception as e:
        print(f"Error en sync_posts: {str(e)}")
        raise


def sync_reactions(user_id: int):
    try:
        user_data = get_user_access_data(user_id)
        access_token = user_data["access_token"]

        posts = execute_query(
            "SELECT post_external_id FROM posts WHERE page_id = %s",
            (user_data["page_id"],),
            fetch=True
        )

        for post in posts:
            post_external_id = post["post_external_id"]

            fb_reactions = fetch_all_fb_data(
                f"/{post_external_id}/reactions",
                {"fields": "id,name,type,profile_type"},
                access_token
            )

            existing_reactions = execute_query(
                """
                SELECT user_external_id, reaction_type
                FROM reactions
                WHERE post_external_id = %s
                """,
                (post_external_id,),
                fetch=True
            )

            existing_set = {
                (r["user_external_id"], r["reaction_type"])
                for r in existing_reactions
            }

            new_reactions = []
            for reaction in fb_reactions:
                user_external_id = reaction["id"]
                reaction_type = reaction["type"]
                key = (user_external_id, reaction_type)

                if key not in existing_set:
                    new_reactions.append({
                        "post_external_id": post_external_id,
                        "user_external_id": user_external_id,
                        "user_name": reaction.get("name"),
                        "reaction_type": reaction_type,
                        "profile_type": reaction.get("profile_type"),
                        "created_time": datetime.utcnow()
                    })

            if new_reactions:
                print(
                    f"📥 Insertando {len(new_reactions)} nuevas reacciones para post {post_external_id}")
                insert_many("reactions", new_reactions)

    except Exception as e:
        print(f"❌ Error en sync_reactions: {str(e)}")
        raise


def fetch_all_fb_data(endpoint, params=None, access_token=None):
    all_data = []
    while endpoint:
        res = fb_api(endpoint, "GET", params, access_token=access_token)
        data = res.get("data", [])
        all_data.extend(data)
        endpoint = res.get("paging", {}).get("next")
        params = None
    return all_data


def sync_comments(user_id: int):
    try:
        user_data = get_user_access_data(user_id)
        access_token = user_data["access_token"]
        page_external_id = user_data["page_external_id"]
        page_id = user_data["page_id"]

        # 1. Obtener todos los posts de la página
        posts = execute_query(
            """
            SELECT post_id, post_external_id
            FROM posts
            WHERE page_id = %s
            """,
            (page_id,),
            fetch=True
        )

        for post in posts:
            post_id = post["post_id"]
            post_external_id = post["post_external_id"]

            # 2. Obtener comentarios desde la API de Facebook
            fb_comments = fb_api(f"/{post_external_id}/comments", "GET", {
                "fields": "id,message,created_time,from"
            }, access_token=access_token).get("data", [])

            # 3. Consultar comentarios ya existentes en la base de datos
            existing_comments = execute_query(
                """
                SELECT comment_external_id FROM comments
                WHERE post_id = %s
                """,
                (post_id,),
                fetch=True
            )
            existing_ids = {c["comment_external_id"]
                            for c in existing_comments}

            # 4. Preparar nuevos comentarios para insertar
            new_comments = []
            for comment in fb_comments:
                external_id = comment["id"]
                if external_id not in existing_ids:
                    texto = comment.get("message", "")
                    sentiment = "neutral"

                    if texto.strip():
                        try:
                            sentiment = analizar_sentimiento.analizar(texto)[
                                "sentimiento"]
                        except Exception as e:
                            print(f"⚠️ Error al analizar sentimiento: {e}")
                            sentiment = "error"

                    new_comments.append({
                        "comment_external_id": external_id,
                        "post_id": post_id,
                        "user_external_id": comment.get("from", {}).get("id"),
                        "user_name": comment.get("from", {}).get("name"),
                        "message": texto,
                        "created_time": comment["created_time"],
                        "sentiment": sentiment,
                    })

            # 5. Insertar en la base de datos
            if new_comments:
                print(
                    f"🟢 Insertando {len(new_comments)} comentarios nuevos para post {post_external_id}")
                insert_many("comments", new_comments)

    except Exception as e:
        print(f"❌ Error en sync_comments: {str(e)}")
        raise


def fetch_page_metric(user_id: int, metric_name: str):
    """
    Obtiene una métrica específica de página desde la API de Facebook
    para el usuario indicado. No depende de ninguna otra función auxiliar.
    """
    # Obtener access_token y page_external_id desde la base de datos
    user_data = get_user_access_data(user_id)
    access_token = user_data["access_token"]
    page_external_id = user_data["page_external_id"]

    if not access_token or not page_external_id:
        raise ValueError(
            "Faltan datos del usuario: access_token o page_external_id")

    # Construir URL y parámetros
    url = f"https://graph.facebook.com/v19.0/{page_external_id}/insights"
    params = {
        "metric": metric_name,
        "period": "day",
        "access_token": access_token
    }

    try:
        response = requests.get(url, params=params)
        response.raise_for_status()
        data = response.json()

        if "error" in data:
            raise Exception(data["error"].get(
                "message", "Error desconocido en la API de Facebook"))

        return data.get("data", [])

    except requests.exceptions.RequestException as e:
        raise Exception(f"❌ Error en la solicitud HTTP: {e}")


def sync_post_reactions_summary(user_id: int):
    """
    Sincroniza el resumen de reacciones por tipo (like, love, haha, etc.)
    para todos los posts de la página del usuario.
    """
    user_data = get_user_access_data(user_id)
    page_id = user_data["page_id"]

    # Obtener todos los posts de esta página
    posts = execute_query(
        "SELECT post_id, post_external_id FROM posts WHERE page_id = %s",
        (page_id,),
        fetch=True
    )

    if not posts:
        print("⚠️ No hay posts registrados para esta página.")
        return

    for post in posts:
        post_id = post["post_id"]
        post_external_id = post["post_external_id"]

        try:
            # Obtener métricas del post desde la API
            url = f"https://graph.facebook.com/v19.0/{post_external_id}/insights"
            params = {
                "metric": "post_reactions_by_type_total",
                "period": "lifetime",
                "access_token": user_data["access_token"]
            }

            response = requests.get(url, params=params)
            response.raise_for_status()
            metrics = response.json().get("data", [])

            new_summaries = []

            for item in metrics:
                if item["name"] != "post_reactions_by_type_total":
                    continue

                values = item.get("values", [])
                if not values:
                    continue

                value_entry = values[0]
                reaction_data = value_entry.get("value", {})
                end_time = value_entry.get("end_time") or datetime.utcnow()

                for reaction_type, count in reaction_data.items():
                    new_summaries.append({
                        "post_id": post_id,
                        "reaction_type": reaction_type,
                        "reaction_count": count,
                        "collected_at": end_time
                    })

            if new_summaries:
                insert_many("post_reactions_summary", new_summaries)
                print(
                    f"✅ Reacciones resumidas insertadas para post {post_external_id}")

        except Exception as e:
            print(f"❌ Error al procesar post {post_external_id}: {e}")


METRICAS_PAGE = [
    "page_impressions",
    "page_fans",
    "page_views_total"
]


def sync_all_page_metrics(user_id: int):
    """
    Obtiene todas las métricas definidas para una página desde la API de Facebook
    y las guarda en la tabla `insights`.
    """
    user_data = get_user_access_data(user_id)
    page_id = user_data["page_id"]

    for metric_name in METRICAS_PAGE:
        try:
            metric_data = fetch_page_metric(user_id, metric_name)
            rows_to_insert = []

            for metric in metric_data:
                name = metric.get("name")
                period = metric.get("period")
                for val in metric.get("values", []):
                    value = val.get("value")
                    end_time = val.get("end_time")
                    if value is None or end_time is None:
                        continue

                    rows_to_insert.append({
                        "page_id": page_id,
                        "name": name,
                        "period": period,
                        "value": value,
                        "end_time": end_time
                    })

            if rows_to_insert:
                insert_many("insights", rows_to_insert)
                print(
                    f"✅ Métrica {metric_name} guardada con {len(rows_to_insert)} registros")

        except Exception as e:
            print(f"❌ Error al sincronizar {metric_name}: {e}")
