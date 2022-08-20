FROM python:3.10-slim

RUN pip install pipx
RUN pipx install poetry

# Required to add pipx vars to the path
ENV PATH="/root/.local/bin:$PATH"

WORKDIR /app

ADD poetry.lock poetry.lock
ADD pyproject.toml pyproject.toml
RUN poetry install

ADD . /app
RUN poetry install
