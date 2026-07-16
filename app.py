import os
from flask import Flask, render_template
from backend.routes.web import web_bp
from backend.routes.auth import auth_bp
from backend.routes.items import items_bp
from backend.services.aws_service import AWSService
from backend.services.matching_service import MatchingService

# Load environment variables
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

def create_app():
    # Setup template and static folders
    app = Flask(
        __name__,
        static_folder="static",
        template_folder="templates"
    )
    
    # Configure secrets & cookie sessions
    app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "reunite-production-secret-99118")
    
    # Initialize DB & AWS Integrations
    aws_service = AWSService()
    matching_service = MatchingService(aws_service)
    
    # Store services globally in context
    app.config["AWS_SERVICE"] = aws_service
    app.config["MATCHING_SERVICE"] = matching_service
    
    # Register blueprints
    app.register_blueprint(web_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(items_bp)
    
    # Add custom formatting filters
    @app.template_filter("format_date")
    def format_date(value):
        if not value:
            return ""
        try:
            import datetime
            # Parse ISO date string
            # Handle possible fractional seconds and Z suffix
            clean_val = value.replace("Z", "+00:00")
            dt = datetime.datetime.fromisoformat(clean_val)
            return dt.strftime("%b %d, %Y at %I:%M %p")
        except Exception:
            return value

    # Global Error Handlers
    @app.errorhandler(404)
    def page_not_found(e):
        return render_template(
            "layout.html", 
            error_title="404 - Page Not Found", 
            error_message="The requested catalog item or portal page could not be located."
        ), 404
        
    @app.errorhandler(500)
    def internal_server_error(e):
        return render_template(
            "layout.html", 
            error_title="500 - Server Error", 
            error_message="A system processing error occurred. Please refresh or try again shortly."
        ), 500

    return app

app = create_app()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)