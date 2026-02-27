FROM python:3.12-slim

WORKDIR /app
COPY requirements-ui.txt /tmp/requirements-ui.txt
RUN pip install --no-cache-dir -r /tmp/requirements-ui.txt
ENV STREAMLIT_SERVER_ADDRESS=0.0.0.0 \
    STREAMLIT_SERVER_PORT=8501 \
    STREAMLIT_SERVER_HEADLESS=true \
    STREAMLIT_SERVER_ENABLE_CORS=false \
    STREAMLIT_SERVER_ENABLE_XSRF_PROTECTION=false \
    STREAMLIT_BROWSER_GATHER_USAGE_STATS=false \
    STREAMLIT_CLIENT_TOOLBAR_MODE=minimal \
    STREAMLIT_CLIENT_SHOW_ERROR_DETAILS=true
COPY ui /app/ui
COPY ui/.streamlit /app/.streamlit

EXPOSE 8501
CMD ["streamlit", "run", "/app/ui/app.py", "--server.address=0.0.0.0", "--server.port=8501", "--server.headless=true", "--server.enableCORS=false", "--server.enableXsrfProtection=false", "--server.enableWebsocketCompression=false", "--browser.gatherUsageStats=false"]
