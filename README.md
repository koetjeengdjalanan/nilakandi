# Nilakandi

Nilakandi is a web application for Cloud management data gathering. Up until this point, it is mainly used for Microsoft Azure Cost Gathering and analysis.

## Table of Contents

- [Introduction](#introduction)
- [Features](#features)
- [Prerequisites](#prerequisites)
- [Installation](#installation)
- [Usage](#usage)
- [Contributing](#contributing)
- [License](#license)

## Introduction

Nilakandi is designed to help organizations manage and analyze their cloud costs effectively. By gathering data from Microsoft Azure, Nilakandi provides insights and analytics to optimize cloud spending.

## Features

- Microsoft Azure Cost Gathering
- Data Analysis and Visualization
- Cost Optimization Recommendations
- User-friendly Web Interface

## Prerequisites 

- Docker:

    > [!IMPORTANT]
    > If you are using Windows, You need ``wsl2`` to run Docker Desktop!
    
    Follow this step to install Docker in your operating system: [Docker installation guide](https://docs.docker.com/engine/install/)


## Installation

To install Nilakandi, follow these steps:

1. Clone the repository:
    ```bash
    git clone https://github.com/koetjeengdjalanan/nilakandi.git
    ```
2. Navigate to the project `.docker` directory:
    ```bash
    cd nilakandi/.docker
    ```
3. Run Docker Compose:
    ```bash
    docker compose up -d --build
    ```
4. Install the dependencies for the web application:
    ```bash
    docker exec -td Nilakandi-web pip install -r /workspace/requirements.txt
    ```

## Usage

To start using Nilakandi, follow these steps:

1. Start the application:
    ```bash
    docker exec -td Nilakandi-web bash -c "python /workspace/manage.py runserver '0.0.0.0:8000'"
    ```
2. Open your web browser and navigate to `http://localhost:8000`.


## Contributing

We welcome contributions to Nilakandi! To contribute, please follow these steps:

1. Clone the repository.
2. Create a new branch:
    ```bash
    git checkout -b feature-branch
    ```
3. Make your changes and commit them:
    ```bash
    git commit -m "Description of your changes"
    ```
4. Create a pull request.


### Semantic Dev Branch Naming

When creating a new branch, please use the following naming convention:

- `<name>-dev`: For private / self branch
- `feature/<description>`: For new features
- `bugfix/<description>`: For bug fixes
- `hotfix/<description>`: For urgent fixes
- `chore/<description>`: For maintenance tasks
- `docs/<description>`: For documentation updates

Examples:
- `koetjeeng-dev`
- `feature/add-user-authentication`
- `bugfix/fix-login-issue`
- `hotfix/patch-security-vulnerability`
- `chore/update-dependencies`
- `docs/update-readme`

This helps in maintaining a clear and organized repository structure.

> [!CAUTION]
> Don't Make a pull Request to `master` from self branch!