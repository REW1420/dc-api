from flask import Flask
from dotenv import load_dotenv
from routes.api_routes import api_blueprint
from routes.sync_routes import sync_blueprint

load_dotenv()

app = Flask(__name__)

# Registrar blueprints
app.register_blueprint(api_blueprint)
app.register_blueprint(sync_blueprint)

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=3000)
