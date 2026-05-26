FROM python:3.11-slim

LABEL description="pwgen — Password candidate list generator (authorized testing only)"

WORKDIR /app

# Install dependencies first (layer cache)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy project
COPY pwgen/       ./pwgen/
COPY config/      ./config/
COPY wordlists/   ./wordlists/
COPY pyproject.toml .

# Install the package itself (no dev deps)
RUN pip install --no-cache-dir -e .

# Output goes here — mount a volume for real runs
RUN mkdir -p /output
VOLUME ["/output"]

ENTRYPOINT ["pwgen"]
CMD ["--help"]
