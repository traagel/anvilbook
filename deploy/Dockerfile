FROM python:3.13-slim
WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir '.[server]' && useradd --create-home anvilbook
USER anvilbook
ENV PORT=8000 ANVILBOOK_DATA=/data
EXPOSE 8000
CMD ["anvilbook-server"]
