import json
import base64
import urllib.parse
from io import BytesIO
from app import app

def lambda_handler(event, context):
    """
    AWS Lambda entrypoint. Maps API Gateway Proxy events (v1 or v2)
    to the Flask WSGI application environment and returns the formatted response.
    """
    # Check for keep-warm pings
    if event.get("source") == "aws.events" or event.get("detail-type") == "Scheduled Event":
        return {"statusCode": 200, "body": "warmed"}
        
    try:
        # Determine API Gateway Event Version
        # HTTP APIs (Payload format 2.0) vs REST APIs (Payload format 1.0)
        is_v2 = "requestContext" in event and "http" in event["requestContext"]
        
        # 1. Parse request path
        if is_v2:
            path = event["rawPath"]
            method = event["requestContext"]["http"]["method"]
            headers = event.get("headers", {})
            query_string = event.get("rawQueryString", "")
        else:
            path = event["path"]
            method = event["httpMethod"]
            headers = event.get("headers", {}) or {}
            # Flatten multiValueHeaders if present
            query_params = event.get("queryStringParameters") or {}
            query_string = urllib.parse.urlencode(query_params) if query_params else ""

        # Normalize header keys to lowercase
        headers = {k.lower(): v for k, v in headers.items()}
        
        # 2. Extract and decode body
        body = event.get("body", "")
        is_base64 = event.get("isBase64Encoded", False)
        
        if body:
            body_bytes = base64.b64decode(body) if is_base64 else body.encode("utf-8")
        else:
            body_bytes = b""
            
        # 3. Build WSGI Environment
        script_name = ""
        path_info = path
        
        # Extract host
        host = headers.get("host", "localhost")
        server_name, _, server_port = host.partition(":")
        server_port = int(server_port) if server_port.isdigit() else (443 if headers.get("x-forwarded-proto") == "https" else 80)
        
        environ = {
            "REQUEST_METHOD": method,
            "SCRIPT_NAME": script_name,
            "PATH_INFO": path_info,
            "QUERY_STRING": query_string,
            "SERVER_NAME": server_name,
            "SERVER_PORT": str(server_port),
            "SERVER_PROTOCOL": "HTTP/1.1",
            "wsgi.version": (1, 0),
            "wsgi.url_scheme": headers.get("x-forwarded-proto", "http"),
            "wsgi.input": BytesIO(body_bytes),
            "wsgi.errors": BytesIO(),
            "wsgi.multithread": False,
            "wsgi.multiprocess": False,
            "wsgi.run_once": False,
        }
        
        # Add headers to WSGI environment
        for key, val in headers.items():
            wsgi_key = "HTTP_" + key.upper().replace("-", "_")
            if key == "content-type":
                environ["CONTENT_TYPE"] = val
            elif key == "content-length":
                environ["CONTENT_LENGTH"] = val
            environ[wsgi_key] = val

        # 4. Run WSGI application
        response_status = []
        response_headers = []
        
        def start_response(status, headers, exc_info=None):
            response_status.append(status)
            response_headers.extend(headers)
            return lambda x: None
            
        # Invoke Flask application
        response_body_iterable = app.wsgi_app(environ, start_response)
        response_body = b"".join(response_body_iterable)
        
        # Parse status code
        status_code_str = response_status[0].split()[0]
        status_code = int(status_code_str)
        
        # 5. Format response headers
        headers_dict = {}
        for k, v in response_headers:
            headers_dict[k] = v
            
        # Binary check (images, fonts, zip files, etc.)
        content_type = headers_dict.get("Content-Type", "").lower()
        is_binary = any(t in content_type for t in ["image/", "font/", "application/octet-stream", "zip", "pdf"])
        
        # Format response body
        if is_binary:
            encoded_body = base64.b64encode(response_body).decode("utf-8")
            body_is_b64 = True
        else:
            encoded_body = response_body.decode("utf-8", errors="replace")
            body_is_b64 = False
            
        return {
            "statusCode": status_code,
            "headers": headers_dict,
            "body": encoded_body,
            "isBase64Encoded": body_is_b64
        }
        
    except Exception as e:
        import traceback
        print(f"Error handling request: {e}")
        print(traceback.format_exc())
        return {
            "statusCode": 500,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({"error": "Internal Server Error", "details": str(e)})
        }
