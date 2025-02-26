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
ENV UID=1001

# Container User's Cred Setup
RUN useradd -G root -u $UID -d /home/arjuna arjuna
RUN mkdir -p /home/arjuna/.local/bin
RUN chown -R arjuna:arjuna /home/arjuna
ENV PATH="/home/arjuna/.local/bin:$PATH"

# Copy Repo
COPY . $DOCUMENT_ROOT/
RUN ls -lah $DOCUMENT_ROOT
RUN chown -R arjuna:arjuna $DOCUMENT_ROOT

# Finalization
USER arjuna
RUN pip install --upgrade pip
RUN pip install -r $DOCUMENT_ROOT/requirements.txt
WORKDIR $DOCUMENT_ROOT
EXPOSE 21280