Add the .env and mcp_config based off .env.example and mcp_config.example.json

run with:
docker run --name arsmedicatech-backend --pull always -p 8700:8000 -v ./mydata:/mydata -w /mydata surrealdb/surrealdb:latest-dev  start --user root --pass root

[setup uv](https://docs.astral.sh/uv/getting-started/installation/)

.\.venv\Scripts\activate
uv sync
python app.py --host=0.0.0.0 --port=3123