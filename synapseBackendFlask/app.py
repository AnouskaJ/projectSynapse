# synapse/app.py
from flask import Flask
from flask_cors import CORS

from synapseBackendFlask.config import CORS_ORIGINS
from synapseBackendFlask.services.llm import llm
from synapseBackendFlask.agent import SynapseAgent
from synapseBackendFlask.http_headers.api import create_api_routes   
from synapseBackendFlask.logger import setup_logging, log

def create_app():
    app = Flask(__name__)
    setup_logging()
    log.info("Starting Synapse Flask application...")
    CORS(app, origins=CORS_ORIGINS if CORS_ORIGINS != ["*"] else "*", supports_credentials=True)

    agent = SynapseAgent(llm)
    create_api_routes(app, agent)
    return app

def main():
    app = create_app()
    app.run(host="0.0.0.0", port=5000, debug=False)

if __name__ == "__main__":
    main()
