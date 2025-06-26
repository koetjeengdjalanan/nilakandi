FROM python:3.12-slim

# Labelling
LABEL author="Martin Sambulare <martin.sambulare@nttindonesia.com>"
LABEL maintainer="Martin Sambulare <martin.sambulare@nttindonesia.com>"
LABEL organization="NTT Data Indonesia"
SHELL ["/bin/bash", "-c"]

# Environment Variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV DOCUMENT_ROOT=/app
ENV POETRY_VERSION=2.1.1
ENV POETRY_NO_INTERACTION=1
ENV DEPLOYMENT=dev
ENV LOG_DIRECTORY=/var/log/nilakandi

# ARGUMENTS
ARG USER=arjuna
ARG UID=1001

# Pre-Req Install
RUN apt-get update && apt-get install -y curl libpq-dev gcc

# Container User's Cred Setup
RUN useradd -G root -u $UID -d /home/$USER $USER
RUN mkdir -p /home/$USER/.local/bin $DOCUMENT_ROOT $LOG_DIRECTORY
RUN chown -R $USER:$USER /home/$USER $DOCUMENT_ROOT $LOG_DIRECTORY

# Create directories for volumes and set proper permissions
RUN mkdir -p /app/staticfiles/azure-reports /tmp && chown -R $USER:$USER /app/staticfiles /tmp

# Change User & WorkDir
WORKDIR $DOCUMENT_ROOT
USER $USER

# Copy Repo
COPY --chown=$USER:$USER . .
# RUN chown -R $USER:$USER $DOCUMENT_ROOT

# Install Poetry
RUN curl -sSL https://install.python-poetry.org | python3 -
ENV PATH="/home/$USER/.local/bin:$PATH"

# Finalization
RUN poetry install $(test "$DEPLOYMENT" == production && echo "--only=main") --no-interaction --no-ansi
